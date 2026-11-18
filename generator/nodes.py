"""把 Clash / mihomo 格式的订阅（proxies 列表）转换为 sing-box 出站。
原则：不支持的协议或参数一律报告并跳过该节点——不静默删除关键参数、不改变协议、不放宽 TLS 校验。
两个内核对同一参数的缺省值不同时（例如 v2ray-plugin 的 mux / host），显式写出 mihomo 的取值，不靠“都省略”。
订阅内容只在用户本机处理，产物写入 dist/private/，不进入公开产物。"""
from __future__ import annotations

import base64
import datetime
import json
import re
import urllib.request
from typing import Dict, List, Tuple

import yaml

COMMON_IGNORED = {"name", "type", "server", "port"}


class Unsupported(Exception):
    pass


def _take(d: dict, used: set, key: str, default=None):
    used.add(key)
    return d.get(key, default)


def _bool_value(v, key: str) -> bool:
    """布尔字段只认真正的 true / false（和整数：mihomo 的解码器开着弱类型，整数按非零为真）。
    带引号的 "false" 在 Python 里是真，以前会被当成开启——例如 skip-cert-verify: "false" 反而跳过证书校验；
    mihomo 读到字符串直接报错（v1.19.31 common/structure/structure.go 的 decodeBool），这里也跳过这个节点（全项目复核 F02）。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    raise Unsupported(f"{key} 应该是 true / false，订阅里写的是 {json.dumps(v, ensure_ascii=False)}（mihomo 也读不了这种写法）")


def _bool(d: dict, used: set, key: str, default: bool = False) -> bool:
    used.add(key)
    v = d.get(key)
    return default if v is None else _bool_value(v, key)


def _text(v, key: str) -> str:
    """文字字段（密码、UUID、用户名、SNI、short-id……）。订阅里没加引号时，YAML 会把一些写法读成别的类型（第二份全项目复核 C3）：
      - 整数照 mihomo 写成十进制：mihomo 也是先读成整数（go.yaml.in/yaml/v3 v3.0.5 的 resolve.go；0123 这种也按八进制读成 83），
        再转成文字（common/structure/structure.go 的 decodeString，FormatInt），两边得到同一个值；
      - 小数、true / false、日期：mihomo 要么报错、要么写成科学计数法（同一个 decodeString），读不出订阅里原来的字，跳过这个节点。
    订阅按 mihomo 的读法解析（load_clash_proxies），yes / no / on / off 这类词在两边都是文字，不会变成 True / False。"""
    if isinstance(v, str):
        return v
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    shown = json.dumps(v, ensure_ascii=False, default=str)
    raise Unsupported(f"{key} 写成了 {shown}，读出来不是文字（订阅里没加引号）：mihomo 读这种写法会报错或者改成别的字，"
                      "这里不猜，请在订阅里给它加上引号")


def _req(d: dict, used: set, key: str) -> str:
    """必填字段：不存在、为 null 或空字符串都报告，不能写成 "None" 或空凭据（审核 F12）。"""
    used.add(key)
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, (dict, list, bool)):
        raise Unsupported(f"缺少必填字段 {key}")
    return _text(v, key)


# packet-encoding（VMess、VLESS 的 UDP 封装）：mihomo 把 packet 当成 packetaddr 的别名（v1.19.31 adapter/outbound/vmess.go、vless.go），
# sing-box 1.14.1、1.12.0 只认空、packetaddr、xudp，别的值在建立出站时报 unknown packet encoding（protocol/vmess、vless 的 outbound.go）。
# 以前原样写进去，配置生成成功、SFA 却建不起这个出站（全项目复核 F03）
PACKET_ENCODING = {"packetaddr": "packetaddr", "packet": "packetaddr", "xudp": "xudp"}


def _packet_encoding(d: dict, used: set, default: str | None) -> str | None:
    pe = _take(d, used, "packet-encoding")
    if pe is None or pe == "":
        return default
    if pe not in PACKET_ENCODING:
        raise Unsupported(f"packet-encoding={pe!r}：sing-box 只认 packetaddr、xudp（mihomo 另把 packet 当成 packetaddr），无法确定原意")
    return PACKET_ENCODING[pe]


# 原样写给 sing-box、取值有限的字段（全项目复核 F03 的同一类，2026-11-18）：sing-box 1.14.1、1.12.0 建出站时只认下面这些，
# 别的取值报错，整份配置都启动不了（不只是少一个节点）。取值表是拿两个官方程序逐个跑 sing-box check 得来的
# （handoff/notes/r22_singbox_enum_sweep.out）。不在表里的跳过这个节点、写进报告。例如 mihomo 文档列着的 aes-128-ccm、
# chacha8-ietf-poly1305、lea-128-gcm 等加密方式，mihomo 认的 chrome120、firefox120、safari16 指纹，sing-box 都不认
SS_METHODS = {"aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
              "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305", "none",
              "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
              "rc4-md5", "chacha20-ietf", "xchacha20"}
VMESS_SECURITY = {"auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-cfb"}
VLESS_FLOWS = {"xtls-rprx-vision"}
TUIC_CONGESTION = {"cubic", "new_reno", "bbr"}
UTLS_FINGERPRINTS = {"chrome", "firefox", "edge", "safari", "360", "qq", "ios", "android", "random", "randomized",
                     "chrome_psk", "chrome_psk_shuffle", "chrome_padding_psk_shuffle", "chrome_pq", "chrome_pq_psk"}
MUX_PROTOCOLS = {"smux", "yamux", "h2mux"}


def _enum(v, allowed: set, key: str):
    if not isinstance(v, str) or v not in allowed:
        raise Unsupported(f"{key}={json.dumps(v, ensure_ascii=False)}：sing-box 1.14.1、1.12.0 都不认这个取值"
                          "（建出站时报错，整份配置启动不了），跳过这个节点")
    return v


# sing-box 1.14 各出站是否有 multiplex 字段（option/*.go 的结构体；1.12.0 相同）
MULTIPLEX_TYPES = {"shadowsocks", "vmess", "vless", "trojan"}

# sing-box 1.14 各出站是否有 network 字段（option/*.go 的结构体）；http、anytls 没有（审核 F01）
NETWORK_FIELD = {"shadowsocks", "vmess", "vless", "trojan", "socks", "hysteria2", "tuic"}


def _tls(d: dict, used: set, *, sni_key: str, default_enabled: bool) -> dict | None:
    enabled = _bool(d, used, "tls", default_enabled)
    sni = _take(d, used, sni_key)
    insecure = _bool(d, used, "skip-cert-verify", False)
    alpn = _take(d, used, "alpn")
    cf = _take(d, used, "client-fingerprint")
    reality = _take(d, used, "reality-opts")
    if "fingerprint" in d:
        used.add("fingerprint")
        raise Unsupported("fingerprint（证书指纹固定）在 sing-box 中没有等效字段")
    if not enabled:
        if reality:
            raise Unsupported("提供了 reality-opts 却未启用 TLS，无法确定原意")
        return None          # 未启用 TLS 时 servername / alpn / 指纹在 mihomo 中同样不生效
    # client-fingerprint：没写、写 none 在 mihomo 里都是不用 uTLS（v1.19.31 component/tls/utls.go 的 GetFingerprint），
    # 以前把 none 原样写成 uTLS 指纹，sing-box 不认、整份配置启动不了（全项目复核 F03 的同一类）
    if cf in (None, "", "none"):
        cf = None
    else:
        _enum(cf, UTLS_FINGERPRINTS, "client-fingerprint")
    if reality and not cf:
        # sing-box 的 Reality 必须带 uTLS（不带时建出站报 uTLS is required by reality client）；
        # mihomo 也一样，连接时报 REALITY is based on uTLS（transport/vmess/tls.go）
        raise Unsupported("Reality 要有 client-fingerprint（uTLS 指纹）：订阅里没写或写的是 none，sing-box 建出站时报错，mihomo 连接时也报错")
    t = {"enabled": True}
    if sni:
        t["server_name"] = _text(sni, sni_key)
    if insecure:
        t["insecure"] = True          # 原订阅就要求跳过校验时才设置，不主动放宽
    if alpn:
        t["alpn"] = list(alpn) if isinstance(alpn, list) else [str(alpn)]
    if cf:
        t["utls"] = {"enabled": True, "fingerprint": str(cf)}
    if reality:
        if not isinstance(reality, dict):
            raise Unsupported("reality-opts 不是键值表")
        extra = set(reality) - {"public-key", "short-id"}
        if extra:
            raise Unsupported(f"reality-opts 不支持的字段 {sorted(extra)}")
        # 第二份全项目复核 C2：short-id 留空（YAML 读成 null）以前写成了字符串 "None"、公钥是 null 时写成 JSON null，
        # sing-box 1.14.1、1.12.0 建出站都报错，整份配置启动不了。mihomo 把留空的 short-id 当成空（解码时 null 不赋值），
        # 公钥和 short-id 都按 base64url（不带 =）、十六进制解（transport/vless 的 RealityOptions.Parse），sing-box 同样
        pk = reality.get("public-key")
        pk = _text(pk, "reality-opts.public-key") if pk is not None else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", pk) or len(base64.urlsafe_b64decode(pk + "=")) != 32:
            raise Unsupported("reality-opts.public-key 缺少，或者不是 32 字节的 base64url 公钥（sing-box、mihomo 都会报错）")
        sid = reality.get("short-id")
        sid = "" if sid is None else _text(sid, "reality-opts.short-id")
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){0,8}", sid):
            raise Unsupported(f"reality-opts.short-id={json.dumps(sid, ensure_ascii=False)}：要是空的，或者 2–16 位、偶数个的十六进制"
                              "（sing-box、mihomo 都会报错）")
        t["reality"] = {"enabled": True, "public_key": pk, "short_id": sid}
    return t


def _forced_tls(d: dict, used: set, notes: list, t: str) -> dict:
    """Trojan、Hysteria2、TUIC、AnyTLS 只能走 TLS。mihomo 的这四种节点没有 tls 开关（v1.19.31 adapter/outbound/ 下 trojan.go、hysteria2.go、
    tuic.go、anytls.go 的选项结构体里都没有这个字段，解码时不认的键直接忽略），订阅里写了什么都照样走 TLS；这里也总是开 TLS，
    和 mihomo 用同一份订阅时一样。以前 Trojan 按订阅里的 tls: false 把 TLS 关掉，转出来是不加密的 Trojan（全项目复核 F01）。
    订阅里写了 tls 又不是 true 时，在报告里提一句（不跳过：mihomo 照样能用这个节点）。"""
    if "tls" in d and d["tls"] is not True:
        notes.append(f"订阅里写了 tls: {json.dumps(d['tls'], ensure_ascii=False)}，但 {t} 只能走 TLS（mihomo 也不认这个字段），照常开 TLS")
    d2 = dict(d)
    d2["tls"] = True
    return _tls(d2, used, sni_key="sni", default_enabled=True)


def _hy2_ports(text: str) -> list:
    """Hysteria2 的 ports（第二份全项目复核 C2）。mihomo（v1.19.31 common/utils/ranges.go）逗号、斜杠都能分隔，每段是一个端口或 a-b，
    最多 28 段；sing-box 的 server_ports 每一项都要写成 a:b，单个端口写 p:p（1.14.1、1.12.0 写成单个数字都报 bad port range）。
    以前只按逗号分、单个端口原样写，整份配置启动不了。"""
    items = [x.strip() for x in re.split(r"[,/]", text) if x.strip()]
    if not items or len(items) > 28:
        raise Unsupported(f"ports={json.dumps(text, ensure_ascii=False)}：要 1–28 段端口或端口区间（mihomo 也是）")
    out = []
    for x in items:
        m = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", x)
        a, b = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (0, 0)
        if not 1 <= a <= b <= 65535:
            raise Unsupported(f"ports 里的 {json.dumps(x, ensure_ascii=False)} 不是 1–65535 的端口或端口区间")
        out.append(f"{a}:{b}")
    return out


def _hy2_hop(text: str) -> tuple:
    """hop-interval：秒数，或者“最短-最长”的区间（mihomo v1.19.31 adapter/outbound/hysteria2.go：0 当成缺省的 30，小于 5 按 5，
    最长小于最短时按最短）。返回 (最短, 最长)。"""
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", text)
    if not m:
        raise Unsupported(f"hop-interval={json.dumps(text, ensure_ascii=False)} 不是秒数或秒数区间")
    start, end = int(m.group(1)), int(m.group(2) or 0)
    start = 30 if start == 0 else max(start, 5)
    return start, max(end, start)


def _transport(d: dict, used: set) -> dict | None:
    net = _take(d, used, "network", "tcp")
    if net in (None, "tcp"):
        for k in ("ws-opts", "grpc-opts", "h2-opts", "http-opts"):
            if k in d:
                raise Unsupported(f"network=tcp 却有 {k}")
        return None
    if net == "ws":
        o = _take(d, used, "ws-opts", {}) or {}
        extra = set(o) - {"path", "headers", "max-early-data", "early-data-header-name", "v2ray-http-upgrade"}
        if extra:
            raise Unsupported(f"ws-opts 不支持的字段 {sorted(extra)}")
        headers = dict(o.get("headers") or {})
        if _bool_value(o.get("v2ray-http-upgrade", False), "ws-opts.v2ray-http-upgrade"):    # 按布尔读（全项目复核 F02 的同一类）
            # HTTP Upgrade：Host 单独成字段，其余请求头原样保留（审核 F03：以前只留 Host / path）
            if o.get("max-early-data") or o.get("early-data-header-name"):
                raise Unsupported("v2ray-http-upgrade 与 early-data 同时出现，sing-box 的 httpupgrade 没有等效写法")
            t = {"type": "httpupgrade", "path": o.get("path", "/")}
            host = headers.pop("Host", None)
            if host:
                t["host"] = host
            if headers:
                t["headers"] = headers
            return t
        path = o.get("path", "/")
        max_ed = int(o["max-early-data"]) if o.get("max-early-data") else 0
        ed_header = o.get("early-data-header-name") or ""
        # mihomo 会把路径里的 ?ed=N 解释成 early data（请求头 Sec-WebSocket-Protocol）并从路径中去掉；sing-box 不认，照搬 mihomo
        m = re.match(r"^([^?]*)\?(.*)$", str(path))
        if m:
            q = [kv for kv in m.group(2).split("&") if kv]
            ed = [kv for kv in q if kv.split("=", 1)[0] == "ed"]
            if ed:
                try:
                    max_ed = int(ed[0].split("=", 1)[1])
                except (IndexError, ValueError):
                    raise Unsupported(f"ws 路径里的 ed 参数无法解析：{path}")
                ed_header = "Sec-WebSocket-Protocol"
                rest = [kv for kv in q if kv.split("=", 1)[0] != "ed"]
                path = m.group(1) + ("?" + "&".join(rest) if rest else "")
        t = {"type": "ws", "path": path}
        if headers:
            t["headers"] = headers
        if max_ed:
            t["max_early_data"] = max_ed
            if ed_header:          # 不写时两个内核都把 early data 放在路径里；以前默认写成请求头，与 mihomo 不同
                t["early_data_header_name"] = ed_header
        return t
    if net == "grpc":
        o = _take(d, used, "grpc-opts", {}) or {}
        extra = set(o) - {"grpc-service-name"}
        if extra:
            raise Unsupported(f"grpc-opts 不支持的字段 {sorted(extra)}")
        return {"type": "grpc", "service_name": o.get("grpc-service-name", "")}
    if net == "h2":
        o = _take(d, used, "h2-opts", {}) or {}
        extra = set(o) - {"host", "path"}
        if extra:
            raise Unsupported(f"h2-opts 不支持的字段 {sorted(extra)}")
        t = {"type": "http"}
        if o.get("host"):
            t["host"] = list(o["host"])
        if o.get("path"):
            t["path"] = o["path"]
        return t
    if net == "http":
        o = _take(d, used, "http-opts", {}) or {}
        extra = set(o) - {"method", "path", "headers"}
        if extra:
            raise Unsupported(f"http-opts 不支持的字段 {sorted(extra)}")
        t = {"type": "http"}
        if o.get("method"):
            t["method"] = o["method"]
        paths = o.get("path") or []
        if len(paths) > 1:
            raise Unsupported("http-opts.path 多个路径在 sing-box 中无等效写法")
        if paths:
            t["path"] = paths[0]
        if o.get("headers"):
            hdr = dict(o["headers"])
            if "Host" in hdr:
                t["host"] = list(hdr.pop("Host")) if isinstance(hdr["Host"], list) else [hdr.pop("Host")]
            if hdr:
                t["headers"] = hdr
        return t
    raise Unsupported(f"不支持的传输 network={net}")


def _dial(d: dict, used: set, ob: dict, udp_capable_default: bool):
    udp = _bool(d, used, "udp", udp_capable_default)
    if not udp:
        if ob["type"] in NETWORK_FIELD:
            ob["network"] = "tcp"          # 保持原语义：订阅未开启 UDP 转发
        elif ob["type"] == "anytls":
            # sing-box 的 AnyTLS 出站总会转发 UDP（UoT），也没有 network 字段，无法保留“不转发 UDP”（审核 F01）
            raise Unsupported("订阅未开启 UDP，但 sing-box 的 AnyTLS 无法禁止 UDP 转发；需要时请在订阅里开启 udp")
        # http：sing-box 的 HTTP 出站本来只走 TCP，不写 network 语义相同
    if _bool(d, used, "tfo", False):
        ob["tcp_fast_open"] = True
    if _bool(d, used, "mptcp", False):
        ob["tcp_multi_path"] = True
    ipv = _take(d, used, "ip-version")
    if ipv not in (None, "dual"):
        raise Unsupported(f"ip-version={ipv} 暂未映射")
    for k in ("interface-name", "routing-mark", "dialer-proxy"):
        if k in d:
            used.add(k)
            raise Unsupported(f"{k} 暂未映射")
    smux = _take(d, used, "smux")
    if smux is not None and not isinstance(smux, dict):
        raise Unsupported("smux 不是键值表")
    if smux and _bool_value(smux.get("enabled", False), "smux.enabled"):
        if ob["type"] not in MULTIPLEX_TYPES:
            # 第二份全项目复核 C2：sing-box 只有这四种出站有 multiplex 字段（option/ 下的结构体），别的写了，
            # 1.14.1、1.12.0 读配置时都报 unknown field "multiplex"，整份配置启动不了
            raise Unsupported(f"订阅开了 smux，但 sing-box 的 {ob['type']} 出站没有多路复用（multiplex），无法表达")
        extra = set(smux) - {"enabled", "protocol", "max-connections", "min-streams", "max-streams", "padding"}
        if extra:
            raise Unsupported(f"smux 不支持的字段 {sorted(extra)}")
        mx = {"enabled": True, "protocol": _enum(smux.get("protocol", "h2mux"), MUX_PROTOCOLS, "smux.protocol")}
        for a, b in (("max-connections", "max_connections"), ("min-streams", "min_streams"), ("max-streams", "max_streams")):
            if a in smux:
                mx[b] = int(smux[a])
        if _bool_value(smux.get("padding", False), "smux.padding"):
            mx["padding"] = True
        ob["multiplex"] = mx


def _mbps(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    m = re.match(r"^\s*(\d+)\s*(mbps|m)?\s*$", str(v), re.I)
    if not m:
        raise Unsupported(f"无法解析带宽 {v!r}")
    return int(m.group(1))


MIHOMO_PLUGIN_DEFAULT_HOST = "bing.com"     # mihomo 的 obfs / v2ray-plugin 缺省 Host；sing-box 缺省值不同，所以显式写出


def _plugin_opts(opts, allowed: set) -> dict:
    if not isinstance(opts, dict):
        raise Unsupported("plugin-opts 不是键值表")
    extra = set(opts) - allowed
    if extra:
        raise Unsupported(f"plugin-opts 不支持的字段 {sorted(extra)}")
    return opts


def convert_one(d: dict, notes: list | None = None) -> dict:
    """notes：转换成功、但要在报告里提一句的事（例如 Trojan 写了 tls: false）。"""
    notes = [] if notes is None else notes
    used = set(COMMON_IGNORED)
    t = d.get("type")
    name, server = d.get("name"), d.get("server")
    if name is None or not str(name).strip():
        raise Unsupported("缺少节点名称")
    if server is None or not str(server).strip():
        raise Unsupported("缺少必填字段 server")
    try:
        port = int(d.get("port"))
    except (TypeError, ValueError):
        raise Unsupported(f"端口不是数字：{d.get('port')!r}")
    if not 1 <= port <= 65535:
        raise Unsupported(f"端口超出范围：{port}")
    ob = {"tag": str(name), "server": str(server), "server_port": port}
    if t == "ss":
        ob["type"] = "shadowsocks"
        ob["method"] = _enum(_req(d, used, "cipher"), SS_METHODS, "cipher")
        ob["password"] = _req(d, used, "password")
        plugin = _take(d, used, "plugin")
        opts = _take(d, used, "plugin-opts", {}) or {}
        if plugin == "obfs":
            o = _plugin_opts(opts, {"mode", "host"})
            if o.get("mode") not in ("http", "tls"):
                raise Unsupported(f"obfs 插件 mode={o.get('mode')!r}（mihomo 只接受 http / tls，缺省即报错）")
            ob["plugin"] = "obfs-local"
            ob["plugin_opts"] = f"obfs={o['mode']};obfs-host={o.get('host') or MIHOMO_PLUGIN_DEFAULT_HOST}"
        elif plugin == "v2ray-plugin":
            o = _plugin_opts(opts, {"mode", "tls", "host", "path", "mux", "skip-cert-verify", "headers",
                                    "fingerprint", "certificate", "private-key", "ech-opts", "name-cert-verify",
                                    "v2ray-http-upgrade", "v2ray-http-upgrade-fast-open"})
            if o.get("mode") != "websocket":
                raise Unsupported(f"v2ray-plugin mode={o.get('mode')!r}（mihomo 只接受 websocket，缺省即报错）")
            for k in ("skip-cert-verify", "headers", "fingerprint", "certificate", "private-key", "ech-opts",
                      "name-cert-verify", "v2ray-http-upgrade", "v2ray-http-upgrade-fast-open"):
                if o.get(k):
                    raise Unsupported(f"v2ray-plugin 的 {k} 在 sing-box 的插件参数里没有等效写法")
            host = o.get("host") or MIHOMO_PLUGIN_DEFAULT_HOST
            parts = ["mode=websocket"]
            if _bool_value(o.get("tls", False), "plugin-opts.tls"):
                parts.append("tls")
            parts.append(f"host={host}")
            if o.get("path"):
                parts.append(f"path={o['path']}")
            # mihomo 缺省开启 mux、写 false 才关闭；sing-box 缺省 mux=1。显式写出，避免 false 被当成缺省重新开启（审核 F03）
            # 2026-11-18：mux 也按布尔读，写成字符串的跳过（全项目复核 F02 的同一类；以前把 "false"、"0" 字符串当成关闭）
            parts.append("mux=" + ("1" if o.get("mux") is None or _bool_value(o["mux"], "plugin-opts.mux") else "0"))
            ob["plugin_opts"] = ";".join(parts)
            ob["plugin"] = "v2ray-plugin"
        elif plugin:
            raise Unsupported(f"ss 插件 {plugin} 不支持")
        if _bool(d, used, "udp-over-tcp", False):
            ob["udp_over_tcp"] = {"enabled": True, "version": int(_take(d, used, "udp-over-tcp-version", 2))}
        _dial(d, used, ob, False)
    elif t == "vmess":
        ob["type"] = "vmess"
        ob["uuid"] = _req(d, used, "uuid")
        ob["alter_id"] = int(_take(d, used, "alterId", 0))
        ob["security"] = _enum(_take(d, used, "cipher") or "auto", VMESS_SECURITY, "cipher")
        if _bool(d, used, "global-padding", False):
            ob["global_padding"] = True
        if _bool(d, used, "authenticated-length", False):
            ob["authenticated_length"] = True
        pe = _packet_encoding(d, used, None)
        if pe:
            ob["packet_encoding"] = pe
        tls = _tls(d, used, sni_key="servername", default_enabled=False)
        if tls:
            ob["tls"] = tls
        tr = _transport(d, used)
        if tr:
            ob["transport"] = tr
        _dial(d, used, ob, False)
    elif t == "vless":
        ob["type"] = "vless"
        ob["uuid"] = _req(d, used, "uuid")
        flow = _take(d, used, "flow")
        if flow:
            ob["flow"] = _enum(flow, VLESS_FLOWS, "flow")
        if d.get("encryption") not in (None, "", "none"):
            used.add("encryption")
            raise Unsupported("VLESS encryption 在 sing-box 中不支持")
        used.add("encryption")
        ob["packet_encoding"] = _packet_encoding(d, used, "xudp")
        tls = _tls(d, used, sni_key="servername", default_enabled=False)
        if tls:
            ob["tls"] = tls
        tr = _transport(d, used)
        if tr:
            ob["transport"] = tr
        _dial(d, used, ob, False)
    elif t == "trojan":
        ob["type"] = "trojan"
        ob["password"] = _req(d, used, "password")
        if "ss-opts" in d:
            used.add("ss-opts")
            raise Unsupported("trojan ss-opts（trojan-go）不支持")
        # 普通 TCP 和 ws 都总是走 TLS；以前按订阅里的 tls: false 把 TLS 关掉（全项目复核 F01），见 _forced_tls
        ob["tls"] = _forced_tls(d, used, notes, "Trojan")
        tr = _transport(d, used)
        if tr:
            ob["transport"] = tr
        _dial(d, used, ob, False)
    elif t == "hysteria2":
        ob["type"] = "hysteria2"
        pw = _take(d, used, "password") or _take(d, used, "auth")
        used.add("auth")
        if pw is None or not str(pw).strip():
            raise Unsupported("缺少必填字段 password")
        ob["password"] = _text(pw, "password")
        ports = _take(d, used, "ports")
        if ports is not None and ports != "":
            ob["server_ports"] = _hy2_ports(_text(ports, "ports"))
            hop = _take(d, used, "hop-interval")
            if hop is not None and hop != "":
                start, end = _hy2_hop(_text(hop, "hop-interval"))
                ob["hop_interval"] = f"{start}s"
                if end > start:
                    notes.append(f"hop-interval 是区间 {start}-{end} 秒：sing-box 1.12 没有区间的写法，这里按 {start} 秒固定间隔换端口")
        used.add("hop-interval")
        if "up" in d:
            ob["up_mbps"] = _mbps(_take(d, used, "up"))
        if "down" in d:
            ob["down_mbps"] = _mbps(_take(d, used, "down"))
        obfs = _take(d, used, "obfs")
        if obfs:
            if obfs != "salamander":
                raise Unsupported(f"hysteria2 obfs={obfs} 不支持")
            ob["obfs"] = {"type": "salamander", "password": _req(d, used, "obfs-password")}
        used.add("obfs-password")
        ob["tls"] = _forced_tls(d, used, notes, "Hysteria2")
        _dial(d, used, ob, True)
    elif t == "tuic":
        ob["type"] = "tuic"
        if "token" in d:
            used.add("token")
            raise Unsupported("TUIC v4（token）不支持，仅支持 v5")
        ob["uuid"] = _req(d, used, "uuid")
        ob["password"] = _req(d, used, "password")
        cc = _take(d, used, "congestion-controller")
        if cc:
            ob["congestion_control"] = _enum(cc, TUIC_CONGESTION, "congestion-controller")
        mode = _take(d, used, "udp-relay-mode")
        if mode:
            ob["udp_relay_mode"] = mode
        if _bool(d, used, "reduce-rtt", False):
            ob["zero_rtt_handshake"] = True
        hb = _take(d, used, "heartbeat-interval")
        if hb:
            ob["heartbeat"] = f"{int(hb)}ms"
        if _bool(d, used, "disable-sni", False):
            raise Unsupported("disable-sni 暂未映射")
        for k in ("request-timeout", "max-udp-relay-packet-size", "max-open-streams", "fast-open", "ip"):
            if k in d:
                used.add(k)
                raise Unsupported(f"tuic {k} 暂未映射")
        ob["tls"] = _forced_tls(d, used, notes, "TUIC")
        _dial(d, used, ob, True)
    elif t == "anytls":
        ob["type"] = "anytls"
        ob["password"] = _req(d, used, "password")
        for a, b in (("idle-session-check-interval", "idle_session_check_interval"),
                     ("idle-session-timeout", "idle_session_timeout")):
            v = _take(d, used, a)
            if v is not None:
                ob[b] = f"{int(v)}s"
        v = _take(d, used, "min-idle-session")
        if v is not None:
            ob["min_idle_session"] = int(v)
        ob["tls"] = _forced_tls(d, used, notes, "AnyTLS")
        _dial(d, used, ob, False)
    elif t in ("socks5", "http"):
        ob["type"] = "socks" if t == "socks5" else "http"
        if t == "socks5":
            ob["version"] = "5"
        u = _take(d, used, "username")
        pw = _take(d, used, "password")
        if u is not None and u != "":
            ob["username"] = _text(u, "username")
        if pw is not None and pw != "":
            ob["password"] = _text(pw, "password")
        if t == "http":
            tls = _tls(d, used, sni_key="sni", default_enabled=False)
            if tls:
                ob["tls"] = tls
            if "headers" in d:
                used.add("headers")
                raise Unsupported("http 代理自定义 headers 暂未映射")
        else:
            if _bool(d, used, "tls", False):
                raise Unsupported("socks5 over TLS 在 sing-box 中不支持")
            _bool(d, used, "skip-cert-verify", False)     # 没有 TLS 时用不到，只查写法（全项目复核 F02）
        _dial(d, used, ob, False)
    else:
        raise Unsupported(f"不支持的协议类型 {t}")

    leftover = set(d) - used
    if leftover:
        raise Unsupported(f"存在未映射的参数 {sorted(leftover)}")
    return ob


class SubscriptionLoader(yaml.SafeLoader):
    """按 mihomo 的读法解析订阅里不带引号的值（第二份全项目复核 C3）。mihomo v1.19.31 用 go.yaml.in/yaml/v3 v3.0.5（go.mod），
    它的 resolve.go 和 PyYAML 缺省的 YAML 1.1 读法有几处不同，这里改成和它一样：
      - 布尔只认 true / True / TRUE / false / False / FALSE；yes、no、on、off、y、n 都是文字（PyYAML 读成 True / False，
        以前 username: no 会被当成“没写用户名”丢掉，password: yes 会写成 "True"）；
      - 整数按 Go 的 strconv.ParseInt(基数 0) 读：0x、0o、0b 前缀，0 开头按八进制（0123 → 83，两边一样），下划线先去掉；
        没有 YAML 1.1 的六十进制（1:20 在两边都是文字）；
      - 0 开头、带 8 或 9 的数字（0089）读成小数（PyYAML 当成文字）：mihomo 再转成文字时写成 8.9E+01，_text 遇到小数就跳过这个节点。
    null、日期、合并键照 PyYAML 的。"""


SubscriptionLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float")]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
SubscriptionLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
SubscriptionLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^[-+]?(?:0[bB][01_]+|0[oO][0-7_]+|0[xX][0-9a-fA-F_]+|0[0-7_]*|[1-9][0-9_]*)$"),
    list("-+0123456789"))
SubscriptionLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"),
    list("-+0123456789."))


def _construct_go_int(loader, node):
    s = loader.construct_scalar(node).replace("_", "")
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    base = {"0b": 2, "0B": 2, "0o": 8, "0O": 8, "0x": 16, "0X": 16}.get(s[:2])
    if base:
        return sign * int(s[2:], base)
    return sign * (int(s, 8) if len(s) > 1 and s[0] == "0" else int(s))


SubscriptionLoader.add_constructor("tag:yaml.org,2002:int", _construct_go_int)


def load_clash_proxies(text: str) -> List[dict]:
    data = yaml.load(text, Loader=SubscriptionLoader)
    if isinstance(data, dict) and isinstance(data.get("proxies"), list):
        return data["proxies"]
    raise ValueError("不是 Clash / mihomo 格式的订阅（缺少 proxies 列表）。"
                     "请在机场处选择 Clash / mihomo 格式，或用 --singbox-sub-url 自动以 clash.meta UA 下载。")


def fetch_subscription(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "clash.meta"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def convert(proxies: List[dict], reserved=frozenset()) -> Tuple[List[dict], List[str], Dict[str, str]]:
    """返回 (sing-box 出站, 报告, 改名表 {新标签: 订阅里的原名})。
    reserved：配置里节点以外的出站标签（策略组、DIRECT、无可用节点）。节点与它们同名时 sing-box 会拒绝整份配置，
    所以改名并写进报告，筛选和固定节点仍按原名匹配（审核 F02）。"""
    out, report, seen, renamed = [], [], set(), {}
    taken = set(reserved)
    for i, d in enumerate(proxies, 1):
        if not isinstance(d, dict):
            report.append(f"跳过第 {i} 项：不是节点（{type(d).__name__}）")
            continue
        name = str(d.get("name", "?"))
        notes = []
        try:
            if name in seen:
                raise Unsupported("节点名称重复")
            ob = convert_one(d, notes)
        except Unsupported as e:
            report.append(f"跳过 {name}（{d.get('type')}）：{e}")
            continue
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            report.append(f"跳过 {name}（{d.get('type')}）：字段缺失或格式错误 {e}")
            continue
        seen.add(name)
        report += [f"提示 {name}（{d.get('type')}）：{x}" for x in notes]
        tag = name
        if tag in taken:
            n = 1
            tag = f"{name}（节点）"
            while tag in taken:
                n += 1
                tag = f"{name}（节点{n}）"
            renamed[tag] = name
            report.append(f"改名 {name} → {tag}：与配置里的策略组 / 出站同名，sing-box 不允许重名")
        ob["tag"] = tag
        taken.add(tag)
        out.append(ob)
    return out, report, renamed

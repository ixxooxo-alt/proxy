"""把 Clash / mihomo 格式的订阅（proxies 列表）转换为 sing-box 出站。
原则：不支持的协议或参数一律报告并跳过该节点——不静默删除关键参数、不改变协议、不放宽 TLS 校验。
两个内核对同一参数的缺省值不同时（例如 v2ray-plugin 的 mux / host），显式写出 mihomo 的取值，不靠“都省略”。
订阅内容只在用户本机处理，产物写入 dist/private/，不进入公开产物。"""
from __future__ import annotations

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


def _req(d: dict, used: set, key: str) -> str:
    """必填字段：不存在、为 null 或空字符串都报告，不能写成 "None" 或空凭据（审核 F12）。"""
    used.add(key)
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, (dict, list, bool)):
        raise Unsupported(f"缺少必填字段 {key}")
    return str(v)


# sing-box 1.14 各出站是否有 network 字段（option/*.go 的结构体）；http、anytls 没有（审核 F01）
NETWORK_FIELD = {"shadowsocks", "vmess", "vless", "trojan", "socks", "hysteria2", "tuic"}


def _tls(d: dict, used: set, *, sni_key: str, default_enabled: bool) -> dict | None:
    enabled = _take(d, used, "tls", default_enabled)
    sni = _take(d, used, sni_key)
    insecure = bool(_take(d, used, "skip-cert-verify", False))
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
    t = {"enabled": True}
    if sni:
        t["server_name"] = str(sni)
    if insecure:
        t["insecure"] = True          # 原订阅就要求跳过校验时才设置，不主动放宽
    if alpn:
        t["alpn"] = list(alpn) if isinstance(alpn, list) else [str(alpn)]
    if cf:
        t["utls"] = {"enabled": True, "fingerprint": str(cf)}
    if reality:
        extra = set(reality) - {"public-key", "short-id"}
        if extra:
            raise Unsupported(f"reality-opts 不支持的字段 {sorted(extra)}")
        t["reality"] = {"enabled": True, "public_key": reality["public-key"], "short_id": str(reality.get("short-id", ""))}
    return t


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
        if o.get("v2ray-http-upgrade"):
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
    udp = _take(d, used, "udp", udp_capable_default)
    if not udp:
        if ob["type"] in NETWORK_FIELD:
            ob["network"] = "tcp"          # 保持原语义：订阅未开启 UDP 转发
        elif ob["type"] == "anytls":
            # sing-box 的 AnyTLS 出站总会转发 UDP（UoT），也没有 network 字段，无法保留“不转发 UDP”（审核 F01）
            raise Unsupported("订阅未开启 UDP，但 sing-box 的 AnyTLS 无法禁止 UDP 转发；需要时请在订阅里开启 udp")
        # http：sing-box 的 HTTP 出站本来只走 TCP，不写 network 语义相同
    if _take(d, used, "tfo", False):
        ob["tcp_fast_open"] = True
    if _take(d, used, "mptcp", False):
        ob["tcp_multi_path"] = True
    ipv = _take(d, used, "ip-version")
    if ipv not in (None, "dual"):
        raise Unsupported(f"ip-version={ipv} 暂未映射")
    for k in ("interface-name", "routing-mark", "dialer-proxy"):
        if k in d:
            used.add(k)
            raise Unsupported(f"{k} 暂未映射")
    smux = _take(d, used, "smux")
    if smux and smux.get("enabled"):
        extra = set(smux) - {"enabled", "protocol", "max-connections", "min-streams", "max-streams", "padding"}
        if extra:
            raise Unsupported(f"smux 不支持的字段 {sorted(extra)}")
        mx = {"enabled": True, "protocol": smux.get("protocol", "h2mux")}
        for a, b in (("max-connections", "max_connections"), ("min-streams", "min_streams"), ("max-streams", "max_streams")):
            if a in smux:
                mx[b] = int(smux[a])
        if smux.get("padding"):
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


def convert_one(d: dict) -> dict:
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
        ob["method"] = _req(d, used, "cipher")
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
            if o.get("tls"):
                parts.append("tls")
            parts.append(f"host={host}")
            if o.get("path"):
                parts.append(f"path={o['path']}")
            # mihomo 缺省开启 mux、写 false 才关闭；sing-box 缺省 mux=1。显式写出，避免 false 被当成缺省重新开启（审核 F03）
            parts.append("mux=" + ("0" if o.get("mux") is False or str(o.get("mux")).lower() in ("false", "0") else "1"))
            ob["plugin_opts"] = ";".join(parts)
            ob["plugin"] = "v2ray-plugin"
        elif plugin:
            raise Unsupported(f"ss 插件 {plugin} 不支持")
        if _take(d, used, "udp-over-tcp", False):
            ob["udp_over_tcp"] = {"enabled": True, "version": int(_take(d, used, "udp-over-tcp-version", 2))}
        _dial(d, used, ob, False)
    elif t == "vmess":
        ob["type"] = "vmess"
        ob["uuid"] = _req(d, used, "uuid")
        ob["alter_id"] = int(_take(d, used, "alterId", 0))
        ob["security"] = _take(d, used, "cipher", "auto")
        if _take(d, used, "global-padding", False):
            ob["global_padding"] = True
        if _take(d, used, "authenticated-length", False):
            ob["authenticated_length"] = True
        pe = _take(d, used, "packet-encoding")
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
            ob["flow"] = flow
        if d.get("encryption") not in (None, "", "none"):
            used.add("encryption")
            raise Unsupported("VLESS encryption 在 sing-box 中不支持")
        used.add("encryption")
        ob["packet_encoding"] = _take(d, used, "packet-encoding", "xudp") or "xudp"
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
        ob["tls"] = _tls(d, used, sni_key="sni", default_enabled=True)
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
        ob["password"] = str(pw)
        ports = _take(d, used, "ports")
        if ports:
            ob["server_ports"] = [x.strip().replace("-", ":") for x in str(ports).split(",")]
            hop = _take(d, used, "hop-interval")
            if hop:
                ob["hop_interval"] = f"{int(hop)}s"
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
        d2 = dict(d)
        d2["tls"] = True
        ob["tls"] = _tls(d2, used, sni_key="sni", default_enabled=True)
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
            ob["congestion_control"] = cc
        mode = _take(d, used, "udp-relay-mode")
        if mode:
            ob["udp_relay_mode"] = mode
        if _take(d, used, "reduce-rtt", False):
            ob["zero_rtt_handshake"] = True
        hb = _take(d, used, "heartbeat-interval")
        if hb:
            ob["heartbeat"] = f"{int(hb)}ms"
        if _take(d, used, "disable-sni", False):
            raise Unsupported("disable-sni 暂未映射")
        for k in ("request-timeout", "max-udp-relay-packet-size", "max-open-streams", "fast-open", "ip"):
            if k in d:
                used.add(k)
                raise Unsupported(f"tuic {k} 暂未映射")
        d2 = dict(d)
        d2["tls"] = True
        ob["tls"] = _tls(d2, used, sni_key="sni", default_enabled=True)
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
        d2 = dict(d)
        d2["tls"] = True
        ob["tls"] = _tls(d2, used, sni_key="sni", default_enabled=True)
        _dial(d, used, ob, False)
    elif t in ("socks5", "http"):
        ob["type"] = "socks" if t == "socks5" else "http"
        if t == "socks5":
            ob["version"] = "5"
        u = _take(d, used, "username")
        pw = _take(d, used, "password")
        if u:
            ob["username"] = str(u)
        if pw:
            ob["password"] = str(pw)
        if t == "http":
            tls = _tls(d, used, sni_key="sni", default_enabled=False)
            if tls:
                ob["tls"] = tls
            if "headers" in d:
                used.add("headers")
                raise Unsupported("http 代理自定义 headers 暂未映射")
        else:
            if d.get("tls"):
                used.add("tls")
                raise Unsupported("socks5 over TLS 在 sing-box 中不支持")
            used.update({"tls", "skip-cert-verify"})
        _dial(d, used, ob, t == "socks5" and bool(d.get("udp")))
    else:
        raise Unsupported(f"不支持的协议类型 {t}")

    leftover = set(d) - used
    if leftover:
        raise Unsupported(f"存在未映射的参数 {sorted(leftover)}")
    return ob


def load_clash_proxies(text: str) -> List[dict]:
    data = yaml.safe_load(text)
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
        try:
            if name in seen:
                raise Unsupported("节点名称重复")
            ob = convert_one(d)
        except Unsupported as e:
            report.append(f"跳过 {name}（{d.get('type')}）：{e}")
            continue
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            report.append(f"跳过 {name}（{d.get('type')}）：字段缺失或格式错误 {e}")
            continue
        seen.add(name)
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

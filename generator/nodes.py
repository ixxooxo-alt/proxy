"""把 Clash / mihomo 格式的订阅（proxies 列表）转换为 sing-box 出站。
原则：不支持的协议或参数一律报告并跳过该节点——不静默删除关键参数、不改变协议、不放宽 TLS 校验。
两个内核对同一参数的缺省值不同时（例如 v2ray-plugin 的 mux / host），显式写出 mihomo 的取值，不靠“都省略”。
订阅内容只在用户本机处理，产物写入 dist/private/，不进入公开产物。"""
from __future__ import annotations

import base64
import datetime
import json
import math
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


# ---------------------------------------------------------------------------
# Go 的整数读法（strconv.ParseUint / ParseInt，基数 0）。订阅读法（go_plain_scalar）和整数字段（_go_int）共用
# ---------------------------------------------------------------------------

def _go_underscore_ok(s: str) -> bool:
    """Go strconv 的 underscoreOK：下划线只能夹在数字之间，或者紧跟在 0b / 0o / 0x 前缀后面（后面还得是数字）。"""
    saw, i, hexa = "^", 0, False
    if s[:1] in ("+", "-"):
        s = s[1:]
    if len(s) >= 2 and s[0] == "0" and s[1].lower() in "box":
        i, saw, hexa = 2, "0", s[1].lower() == "x"
    for c in s[i:]:
        if "0" <= c <= "9" or (hexa and c.isascii() and "a" <= c.lower() <= "f"):
            saw = "0"
        elif c == "_":
            if saw != "0":
                return False
            saw = "_"
        elif saw == "_":
            return False
        else:
            saw = "!"
    return saw != "_"


def _go_parse_uint(s: str, base: int = 0, bits: int = 64):
    """Go 的 strconv.ParseUint(s, base, bits)：读得出返回整数，写法不对或越界返回 None。
    基数 0 时：0b / 0o / 0x 前缀（后面至少一位）、0 开头按八进制、别的按十进制；下划线按 underscoreOK。"""
    if not s:
        return None
    s0, base0 = s, base == 0
    if base0:
        base = 10
        if s[0] == "0":
            if len(s) >= 3 and s[1].lower() in "box":
                base, s = {"b": 2, "o": 8, "x": 16}[s[1].lower()], s[2:]
            else:
                base, s = 8, s[1:]
    n, underscores, limit = 0, False, (1 << bits) - 1
    for c in s:
        if c == "_" and base0:
            underscores = True
            continue
        if "0" <= c <= "9":
            d = ord(c) - 48
        elif c.isascii() and c.isalpha():
            d = ord(c.lower()) - 87
        else:
            return None
        if d >= base:
            return None
        n = n * base + d
        if n > limit:
            return None
    if underscores and not _go_underscore_ok(s0):
        return None
    return n


def _go_parse_int(s: str, base: int = 0, bits: int = 64):
    """Go 的 strconv.ParseInt(s, base, bits)：前面可以有一个 + 或 -，其余同 _go_parse_uint，按有符号 64 位核对范围。"""
    if not s:
        return None
    neg = s[0] == "-"
    un = _go_parse_uint(s[1:] if s[0] in "+-" else s, base, bits)
    if un is None:
        return None
    cutoff = 1 << (bits - 1)
    if (not neg and un >= cutoff) or (neg and un > cutoff):
        return None
    return -un if neg else un


def _go_int(v, key: str) -> int:
    """mihomo 的整数字段（端口、alterId 等；common/structure/structure.go 的 decodeInt，解码器开着弱类型）：整数照用；
    小数去掉小数部分；文字按 Go 的 ParseInt(基数 0) 读——"0100" 是八进制 64、"0x01bb" 是 443、"08" 读不出来；
    true / false 读不了（mihomo 报错）。以前直接用 Python 的 int()：布尔当成 1，"0100" 当成十进制 100，"0x01bb" 读不出来
    （GPT 审核 r22 送审稿 R22-F14，另一个 AI 的 F03）。"""
    if isinstance(v, bool):
        raise Unsupported(f"{key} 应该是数字，订阅里写的是 {json.dumps(v)}（mihomo 也读不了这种写法）")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and math.isfinite(v):
        return int(v)
    if isinstance(v, str):
        n = _go_parse_int(v)
        if n is not None:
            return n
    raise Unsupported(f"{key} 写成了 {json.dumps(v, ensure_ascii=False, default=str)}，按 mihomo 的读法读不出数字")


# SS2022 的密钥（GPT 审核 r22 送审稿 R22-F07）：sing-box 1.14.1、1.12.0 都用 sing-shadowsocks2 v0.2.1，
# shadowaead_2022/method.go 的 NewMethod 把 password 按冒号分段，每段按标准 base64 解（要补齐 =），解出来 aes-128-gcm 要 16 字节、
# 另两种要 32 字节，chacha20-poly1305 只能有一段。不合就在建出站时报错（decode key / bad key length），整份配置启动不了。
# 以前只看加密方式在不在表里、密码非空，写盘前检查也放过（官方程序实测：两个版本的 check 都报 FATAL）
SS2022_KEY_BYTES = {"2022-blake3-aes-128-gcm": 16, "2022-blake3-aes-256-gcm": 32, "2022-blake3-chacha20-poly1305": 32}


def ss2022_key_problem(method: str, password) -> str | None:
    """合格返回 None，否则返回原因（不带密钥本身）。不是 SS2022 的加密方式时返回 None。转换器和写盘前检查共用。"""
    size = SS2022_KEY_BYTES.get(method)
    if size is None:
        return None
    if not isinstance(password, str):
        return "密钥不是文字"
    parts = password.split(":")
    if method == "2022-blake3-chacha20-poly1305" and len(parts) > 1:
        return "chacha20-poly1305 不支持用冒号连起来的多段密钥"
    for i, part in enumerate(parts, 1):
        try:
            key = base64.b64decode(part.replace("\r", "").replace("\n", ""), validate=True)
        except ValueError:
            return f"第 {i} 段不是标准 base64（字符不对或没有补齐 =）"
        if len(key) != size:
            return f"第 {i} 段解出来是 {len(key)} 字节，{method} 要 {size} 字节"
    return None


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
# 这五个名字 sing-box 认（check 能过），但 1.14.1、1.12.0 都当成普通 Chrome（common/tls/utls_client.go 的 uTLSClientHelloID：
# fallthrough 到 HelloChrome_Auto）；mihomo 各自用一种旧版 Chrome 的握手（component/tls/utls.go）。照写，在报告里说明
# （GPT 审核 r22 送审稿 R22-F11；没有照它的建议跳过：节点照样能连，跳过就少一个能用的节点）
UTLS_SINGBOX_CHROME_ALIASES = {"chrome_psk", "chrome_psk_shuffle", "chrome_padding_psk_shuffle", "chrome_pq", "chrome_pq_psk"}


def _enum(v, allowed: set, key: str):
    if not isinstance(v, str) or v not in allowed:
        raise Unsupported(f"{key}={json.dumps(v, ensure_ascii=False)}：sing-box 1.14.1、1.12.0 都不认这个取值"
                          "（建出站时报错，整份配置启动不了），跳过这个节点")
    return v


# sing-box 1.14 各出站是否有 multiplex 字段（option/*.go 的结构体；1.12.0 相同）
MULTIPLEX_TYPES = {"shadowsocks", "vmess", "vless", "trojan"}

# sing-box 1.14 各出站是否有 network 字段（option/*.go 的结构体）；http、anytls 没有（审核 F01）
NETWORK_FIELD = {"shadowsocks", "vmess", "vless", "trojan", "socks", "hysteria2", "tuic"}


def _tls(d: dict, used: set, *, sni_key: str, default_enabled: bool, notes: list | None = None) -> dict | None:
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
    # 以前把 none 原样写成 uTLS 指纹，sing-box 不认、整份配置启动不了（全项目复核 F03 的同一类）。
    # 订阅里不加引号写成数字（360）时，mihomo 先转成文字 "360" 再查表（decodeString），这里也先转（R22-F08）
    if cf is not None:
        cf = _text(cf, "client-fingerprint")
    if cf in (None, "", "none"):
        cf = None
    else:
        _enum(cf, UTLS_FINGERPRINTS, "client-fingerprint")
        if cf in UTLS_SINGBOX_CHROME_ALIASES and notes is not None:
            notes.append(f"client-fingerprint 是 {cf}：sing-box 认这个名字，但实际用的是普通 Chrome 的握手（mihomo 用的是这一种旧版 Chrome 的），"
                         "照写")
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


def _forced_tls(d: dict, used: set, notes: list, t: str, quic: bool = False) -> dict:
    """Trojan、Hysteria2、TUIC、AnyTLS 只能走 TLS。mihomo 的这四种节点没有 tls 开关（v1.19.31 adapter/outbound/ 下 trojan.go、hysteria2.go、
    tuic.go、anytls.go 的选项结构体里都没有这个字段，解码时不认的键直接忽略），订阅里写了什么都照样走 TLS；这里也总是开 TLS，
    和 mihomo 用同一份订阅时一样。以前 Trojan 按订阅里的 tls: false 把 TLS 关掉，转出来是不加密的 Trojan（全项目复核 F01）。
    订阅里写了 tls 又不是 true 时，在报告里提一句（不跳过：mihomo 照样能用这个节点）。"""
    if "tls" in d and d["tls"] is not True:
        notes.append(f"订阅里写了 tls: {json.dumps(d['tls'], ensure_ascii=False)}，但 {t} 只能走 TLS（mihomo 也不认这个字段），照常开 TLS")
    d2 = dict(d)
    d2["tls"] = True
    if quic:
        # TUIC、Hysteria2 走 QUIC：mihomo 的这两种节点没有 client-fingerprint 字段（adapter/outbound/tuic.go、hysteria2.go），
        # 写了也不用 uTLS；sing-box 却会真的开 uTLS，而 QUIC 拨号要的是标准 TLS 配置，uTLS 的那一种直接报错
        # （1.14.1 common/tls/utls_client.go 的 STDConfig：unsupported usage for uTLS），check 能过、一连就失败。
        # 这里照 mihomo 忽略它，在报告里说明（GPT 审核 r22 送审稿 R22-F10）
        used.add("client-fingerprint")
        cf = d2.pop("client-fingerprint", None)
        if cf not in (None, "", "none"):
            notes.append(f"写了 client-fingerprint，但 {t} 走 QUIC：mihomo 的 {t} 没有这个字段、不用 uTLS，"
                         "sing-box 在 QUIC 上用 uTLS 一连就报错，这里不写")
    return _tls(d2, used, sni_key="sni", default_enabled=True, notes=notes)


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
        max_ed = _go_int(o["max-early-data"], "ws-opts.max-early-data") if o.get("max-early-data") else 0
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
        mx = {"enabled": True, "protocol": _enum(_text(smux.get("protocol", "h2mux"), "smux.protocol"), MUX_PROTOCOLS, "smux.protocol")}
        for a, b in (("max-connections", "max_connections"), ("min-streams", "min_streams"), ("max-streams", "max_streams")):
            if a in smux:
                mx[b] = _go_int(smux[a], f"smux.{a}")
        if _bool_value(smux.get("padding", False), "smux.padding"):
            mx["padding"] = True
        ob["multiplex"] = mx


def _mbps(v) -> int:
    if isinstance(v, bool):           # mihomo 的带宽是文字字段，读不了 true / false（R22-F14 的同一类）
        raise Unsupported(f"带宽写成了 {json.dumps(v)}")
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
    port = _go_int(d.get("port"), "port")        # 带引号的 "0100" 是八进制 64，和 mihomo 一样（R22-F14）
    raw_port = d.get("port")
    if isinstance(raw_port, str) and not re.fullmatch(r"[+]?[1-9][0-9_]*", raw_port.strip()):
        notes.append(f"port 写成了 {json.dumps(raw_port)}：mihomo 按 Go 的规则读成 {port}（0 开头是八进制、0x 开头是十六进制），这里也是")
    if not 1 <= port <= 65535:
        raise Unsupported(f"端口超出范围：{port}")
    ob = {"tag": str(name), "server": str(server), "server_port": port}
    if t == "ss":
        ob["type"] = "shadowsocks"
        ob["method"] = _enum(_req(d, used, "cipher"), SS_METHODS, "cipher")
        ob["password"] = _req(d, used, "password")
        problem = ss2022_key_problem(ob["method"], ob["password"])
        if problem:
            raise Unsupported(f"password 不是 {ob['method']} 要的密钥（{problem}）：sing-box 建这个出站时报错，整份配置启动不了")
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
            ob["udp_over_tcp"] = {"enabled": True, "version": _go_int(_take(d, used, "udp-over-tcp-version", 2), "udp-over-tcp-version")}
        _dial(d, used, ob, False)
    elif t == "vmess":
        ob["type"] = "vmess"
        ob["uuid"] = _req(d, used, "uuid")
        ob["alter_id"] = _go_int(_take(d, used, "alterId", 0), "alterId")
        # mihomo 先把 cipher 转成小写（adapter/outbound/vmess.go 的 NewVmess：strings.ToLower），AES-128-GCM 和 aes-128-gcm 一样（R22-F08）
        cipher = _take(d, used, "cipher")
        ob["security"] = _enum("auto" if cipher is None or cipher == "" else _text(cipher, "cipher").lower(), VMESS_SECURITY, "cipher")
        if _bool(d, used, "global-padding", False):
            ob["global_padding"] = True
        if _bool(d, used, "authenticated-length", False):
            ob["authenticated_length"] = True
        pe = _packet_encoding(d, used, None)
        if pe:
            ob["packet_encoding"] = pe
        tls = _tls(d, used, sni_key="servername", default_enabled=False, notes=notes)
        if tls:
            ob["tls"] = tls
            if ob["security"] == "auto":
                # sing-box 1.14.1、1.12.0 遇到 auto 又开了 TLS，会把内层加密改成 zero（protocol/vmess/outbound.go），只靠外层 TLS；
                # mihomo 的 auto 按处理器架构选（MetaCubeX/sing-vmess v0.2.5 protocol.go 的 AutoSecurityType）：arm64、amd64 上是
                # aes-128-gcm，内层照样加密。这里照它写明 aes-128-gcm，在报告里说明（GPT 审核 r22 送审稿 R22-F09；没有照它的建议跳过：
                # 这种节点很常见，跳过就用不了。32 位 ARM 上 mihomo 选的是 chacha20-poly1305，写 aes-128-gcm 照样能连，只是慢一点）
                ob["security"] = "aes-128-gcm"
                notes.append("cipher 是 auto 又开了 TLS：sing-box 会把内层加密改成 zero（只靠外层 TLS），"
                             "mihomo 在 arm64 / amd64 上用的是 aes-128-gcm，这里照它写明 aes-128-gcm")
        tr = _transport(d, used)
        if tr:
            ob["transport"] = tr
        _dial(d, used, ob, False)
    elif t == "vless":
        ob["type"] = "vless"
        ob["uuid"] = _req(d, used, "uuid")
        flow = _take(d, used, "flow")
        if flow is not None and flow != "":
            # mihomo（adapter/outbound/vless.go 的 NewVless）：不到 16 个字符的 flow 当成没写；满 16 个的只取前 16 个，
            # 必须是 xtls-rprx-vision，不是就报错（R22-F08：xtls-rprx-vision-udp443 在 mihomo 里就是 xtls-rprx-vision）
            flow = _text(flow, "flow")
            if len(flow) < 16:
                notes.append(f"flow 写的是 {flow}，不到 16 个字符：mihomo 当成没写（普通 VLESS），这里也不写")
            elif flow[:16] != "xtls-rprx-vision":
                raise Unsupported(f"flow={json.dumps(flow, ensure_ascii=False)}：mihomo 只取前 16 个字符，不是 xtls-rprx-vision，"
                                  "mihomo 也建不起这个节点")
            else:
                if len(flow) > 16:
                    notes.append(f"flow 写的是 {flow}：mihomo 只取前 16 个字符，按 xtls-rprx-vision 处理")
                ob["flow"] = _enum("xtls-rprx-vision", VLESS_FLOWS, "flow")
        if d.get("encryption") not in (None, "", "none"):
            used.add("encryption")
            raise Unsupported("VLESS encryption 在 sing-box 中不支持")
        used.add("encryption")
        ob["packet_encoding"] = _packet_encoding(d, used, "xudp")
        tls = _tls(d, used, sni_key="servername", default_enabled=False, notes=notes)
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
        # 先看 password，没写或是空的再看 auth（以前用 or：不加引号的 password: 0 在 Python 里是假，被当成缺密码，另一个 AI 的 F03）
        pw = _take(d, used, "password")
        if pw is None or pw == "":
            pw = _take(d, used, "auth")
        used.add("auth")
        if pw is None or (isinstance(pw, str) and not pw.strip()) or isinstance(pw, (dict, list, bool)):
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
        ob["tls"] = _forced_tls(d, used, notes, "Hysteria2", quic=True)
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
            ob["congestion_control"] = _enum(_text(cc, "congestion-controller"), TUIC_CONGESTION, "congestion-controller")
        mode = _take(d, used, "udp-relay-mode")
        if mode:
            ob["udp_relay_mode"] = mode
        if _bool(d, used, "reduce-rtt", False):
            ob["zero_rtt_handshake"] = True
        hb = _take(d, used, "heartbeat-interval")
        if hb:
            ob["heartbeat"] = f"{_go_int(hb, 'heartbeat-interval')}ms"
        if _bool(d, used, "disable-sni", False):
            raise Unsupported("disable-sni 暂未映射")
        for k in ("request-timeout", "max-udp-relay-packet-size", "max-open-streams", "fast-open", "ip"):
            if k in d:
                used.add(k)
                raise Unsupported(f"tuic {k} 暂未映射")
        ob["tls"] = _forced_tls(d, used, notes, "TUIC", quic=True)
        _dial(d, used, ob, True)
    elif t == "anytls":
        ob["type"] = "anytls"
        ob["password"] = _req(d, used, "password")
        for a, b in (("idle-session-check-interval", "idle_session_check_interval"),
                     ("idle-session-timeout", "idle_session_timeout")):
            v = _take(d, used, a)
            if v is not None:
                ob[b] = f"{_go_int(v, a)}s"
        v = _take(d, used, "min-idle-session")
        if v is not None:
            ob["min_idle_session"] = _go_int(v, "min-idle-session")
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
            tls = _tls(d, used, sni_key="sni", default_enabled=False, notes=notes)
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
    """按 mihomo 的读法解析订阅（第二份全项目复核 C3；2026-11-19 按 r22 送审稿的两份审核重写：GPT 的 R22-F12、F13，
    另一个 AI 的 F01、F02）。mihomo v1.19.31 用 go.yaml.in/yaml/v3 v3.0.5（go.mod），它决定不带引号的值是什么类型的办法
    （resolve.go 的 resolve）和 PyYAML 的 YAML 1.1 读法不同，这里照它来，见 go_plain_scalar：
      - 布尔只认 true / True / TRUE / false / False / FALSE；yes、no、on、off、y、n 都是文字；
      - 以数字、+、-、. 开头的：先看是不是日期（四种写法，日期不存在的不算），再去掉下划线按 Go 的 ParseInt、ParseUint
        （64 位）读整数，再按小数读，都不是就保留原来的文字。以前 0x_、2026-02-30 这类值会让整份订阅读不下去，
        超过 64 位的整数照原样留成整数（mihomo 读成小数、再写成科学计数法）；
      - 同一个键在同一张表里写了两次：mihomo（go-yaml 的 decode.go）读这张表时报 mapping key already defined，订阅整份读不了，
        这里也整份不转换，只报键名和行号（以前悄悄用了后一个值，例如 skip-cert-verify 先 true 后 false）。查哪些表见 duplicate_keys。
    null、合并键（<<）照 PyYAML 的；“=”在 PyYAML 里是一个特别的值、SafeLoader 读到会出错，go-yaml 当文字，这里也当文字。
    年份是 0000 的日期 go-yaml 也读成时间（Go 的 time 有 0 年），Python 的日期表示不了，这里留成文字：只差在 mihomo 读不了这个节点、
    转换器把它当文字转出来。"""


MERGE_TAG = "tag:yaml.org,2002:merge"


def duplicate_keys(root) -> list:
    """订阅里同一张表写了两次的键：[(键, 第一次的行, 重复的行)]。在组装出节点树以后、构造之前查（load_clash_proxies）。
    照 mihomo 的范围：它用 proxy-providers 读订阅时只认 proxies 这一个字段（v1.19.31 adapter/provider/provider.go 的 ProxySchema），
    go-yaml 只在真正读进来的表上查重复——最外层和 proxies 里面（顺着锚点、合并用到的表也算）。别的部分（proxy-groups、rules、
    不认识的键）它不读也不查，转换也用不到，这里同样不查。比的是键的原文，合并（<<）进来的键被同名的键盖掉是合法的。
    2026-11-19 交送审稿前自查改的：以前在构造每张表时查，又查整份订阅——PyYAML 构造时会把合并展开进被引用的那张表，
    那张表要是自己也合并、又盖掉了继承来的键，轮到它时就被误认成重复；mihomo 不读的部分里有重复也会整份不转换（官方 mihomo 实测
    两种都能读，handoff/notes/r22b_review_probes.py）。"""
    found, walked, tops = [], set(), set()

    def own_keys(node):
        seen = {}
        for key_node, _ in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                line = key_node.start_mark.line + 1
                if key_node.value in seen:
                    found.append((key_node.value, seen[key_node.value], line))
                else:
                    seen[key_node.value] = line

    def walk(node):                                   # proxies 里面：每一张表都查
        if id(node) in walked:
            return
        walked.add(id(node))
        if isinstance(node, yaml.MappingNode):
            own_keys(node)
            for key_node, value_node in node.value:
                walk(key_node)
                walk(value_node)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item)

    def top(node):                                    # 最外层（和用 << 合并进最外层的表）：查它自己的键，往下只进 proxies
        if id(node) in tops:
            return
        tops.add(id(node))
        own_keys(node)
        for key_node, value_node in node.value:
            if key_node.tag == MERGE_TAG:
                for m in value_node.value if isinstance(value_node, yaml.SequenceNode) else [value_node]:
                    if isinstance(m, yaml.MappingNode):
                        top(m)
            elif isinstance(key_node, yaml.ScalarNode) and key_node.value == "proxies":
                walk(value_node)

    if isinstance(root, yaml.MappingNode):
        top(root)
    return found


GO_PLAIN_TAG = "tag:proxy-rules.local,2026:go-plain"
SubscriptionLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float",
                                                  "tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:value")]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
SubscriptionLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
SubscriptionLoader.add_implicit_resolver(GO_PLAIN_TAG, re.compile(r"^[-+.0-9]"), list("-+.0123456789"))

# go-yaml v3.0.5 resolve.go：yamlStyleFloat、resolveMap 里的特殊小数、allowedTimestampFormats
_YAML_STYLE_FLOAT = re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?")
_GO_SPECIAL_FLOATS = {**{x: math.nan for x in (".nan", ".NaN", ".NAN")},
                      **{x: math.inf for x in (".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF")},
                      **{x: -math.inf for x in ("-.inf", "-.Inf", "-.INF")}}
_GO_TIMESTAMPS = (   # 2006-1-2T15:4:5.999999999Z07:00、小写 t 的同一种、2006-1-2 15:4:5.999999999、2006-1-2（Go 的 time.Parse）
    # 数字只认 0–9（Python 的 \d 还认全角等别的数字，Go 不认；2026-11-19 交送审稿前自查改的）
    re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})T([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})(?:[.,][0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"),
    re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})t([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})(?:[.,][0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"),
    re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2}) ([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})(?:[.,][0-9]+)?()"),
    re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})()()()()"))


def _go_timestamp(s: str):
    """go-yaml 的 parseTimestamp：前四位是数字、接着是“-”，再按四种写法用 Go 的 time.Parse 试（日期、时间要真实存在）。
    认得出就返回 datetime.date，否则 None。"""
    if not re.match(r"[0-9]{4}-", s):
        return None
    for rx in _GO_TIMESTAMPS:
        m = rx.fullmatch(s)
        if not m:
            continue
        y, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        clock = [int(x) for x in m.group(4, 5, 6) if x]
        zone = m.group(7)
        if zone not in ("", "Z") and (int(zone[1:3]) > 24 or int(zone[4:6]) > 60):
            continue
        if clock and (clock[0] >= 24 or clock[1] >= 60 or clock[2] >= 60):
            continue
        try:
            return datetime.date(y, mo, day)
        except ValueError:
            continue
    return None


def _go_float(s: str):
    """Go 的 strconv.ParseFloat 在十进制写法上（调用前写法已经核对过）：得到无穷大就是越界，算读不出来。"""
    try:
        f = float(s.replace("_", ""))
    except ValueError:
        return None
    return None if math.isinf(f) else f


def go_plain_scalar(s: str):
    """不带引号、以数字、+、-、. 开头的值：照 go-yaml v3.0.5 的 resolve 依次试，返回 int、float、datetime.date，或者原来的文字。"""
    if s in _GO_SPECIAL_FLOATS:
        return _GO_SPECIAL_FLOATS[s]
    if s[0] == ".":                                                   # 只当小数试（带下划线时照 Go 的规则）
        if re.fullmatch(r"\.[0-9_]+(?:[eE][-+]?[0-9_]+)?", s) and _go_underscore_ok(s):
            f = _go_float(s)
            if f is not None:
                return f
        return s
    ts = _go_timestamp(s)
    if ts is not None:
        return ts
    plain = s.replace("_", "")
    for v in (_go_parse_int(plain), _go_parse_uint(plain)):
        if v is not None:
            return v
    if _YAML_STYLE_FLOAT.fullmatch(plain):
        f = _go_float(plain)
        if f is not None:
            return f
    for prefix, base in (("0b", 2), ("-0b", 2), ("0o", 8), ("-0o", 8)):
        if plain.startswith(prefix):
            digits = plain[len(prefix):]
            v = _go_parse_int(("-" if prefix[0] == "-" else "") + digits, base)
            if v is None and prefix[0] != "-":
                v = _go_parse_uint(digits, base)
            if v is not None:
                return v
    return s


SubscriptionLoader.add_constructor(GO_PLAIN_TAG, lambda loader, node: go_plain_scalar(loader.construct_scalar(node)))


def load_clash_proxies(text: str) -> List[dict]:
    loader = SubscriptionLoader(text)
    try:
        root = loader.get_single_node()
        dups = duplicate_keys(root)
        if dups:
            shown = "；".join(f"第 {line} 行的 {key}（第 {first} 行已经有了）" for key, first, line in dups[:5])
            more = f"等 {len(dups)} 处" if len(dups) > 5 else ""
            raise ValueError(f"订阅里同一个键在同一处写了两次：{shown}{more}。mihomo 读这样的订阅会整份报错（mapping key already defined），"
                             "这里也不猜用哪一个，整份不转换；请让机场修正订阅")
        data = loader.construct_document(root) if root is not None else None
    finally:
        loader.dispose()
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

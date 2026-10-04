"""把 Clash / mihomo 格式的订阅（proxies 列表）转换为 sing-box 出站。
原则：不支持的协议或参数一律报告并跳过该节点——不静默删除关键参数、不改变协议、不放宽 TLS 校验。
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
        if o.get("v2ray-http-upgrade"):
            t = {"type": "httpupgrade", "path": o.get("path", "/")}
            host = (o.get("headers") or {}).get("Host")
            if host:
                t["host"] = host
            return t
        t = {"type": "ws", "path": o.get("path", "/")}
        if o.get("headers"):
            t["headers"] = dict(o["headers"])
        if o.get("max-early-data"):
            t["max_early_data"] = int(o["max-early-data"])
            t["early_data_header_name"] = o.get("early-data-header-name", "Sec-WebSocket-Protocol")
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
        ob["network"] = "tcp"          # 保持原语义：订阅未开启 UDP 转发
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


def convert_one(d: dict) -> dict:
    used = set(COMMON_IGNORED)
    t = d.get("type")
    ob = {"tag": str(d["name"]), "server": str(d["server"]), "server_port": int(d["port"])}
    if t == "ss":
        ob["type"] = "shadowsocks"
        ob["method"] = _take(d, used, "cipher")
        ob["password"] = str(_take(d, used, "password"))
        plugin = _take(d, used, "plugin")
        opts = _take(d, used, "plugin-opts", {}) or {}
        if plugin == "obfs":
            ob["plugin"] = "obfs-local"
            s = f"obfs={opts.get('mode', 'http')}"
            if opts.get("host"):
                s += f";obfs-host={opts['host']}"
            ob["plugin_opts"] = s
        elif plugin == "v2ray-plugin":
            if opts.get("mode", "websocket") != "websocket":
                raise Unsupported("v2ray-plugin 仅支持 websocket 模式")
            parts = ["mode=websocket"]
            if opts.get("tls"):
                parts.append("tls")
            if opts.get("host"):
                parts.append(f"host={opts['host']}")
            if opts.get("path"):
                parts.append(f"path={opts['path']}")
            if opts.get("mux"):
                parts.append("mux=1")
            if opts.get("skip-cert-verify"):
                raise Unsupported("v2ray-plugin skip-cert-verify 无法在 plugin_opts 中等效表达")
            ob["plugin_opts"] = ";".join(parts)
            ob["plugin"] = "v2ray-plugin"
        elif plugin:
            raise Unsupported(f"ss 插件 {plugin} 不支持")
        if _take(d, used, "udp-over-tcp", False):
            ob["udp_over_tcp"] = {"enabled": True, "version": int(_take(d, used, "udp-over-tcp-version", 2))}
        _dial(d, used, ob, False)
    elif t == "vmess":
        ob["type"] = "vmess"
        ob["uuid"] = _take(d, used, "uuid")
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
        ob["uuid"] = _take(d, used, "uuid")
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
        ob["password"] = str(_take(d, used, "password"))
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
            ob["obfs"] = {"type": "salamander", "password": str(_take(d, used, "obfs-password"))}
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
        ob["uuid"] = _take(d, used, "uuid")
        ob["password"] = str(_take(d, used, "password"))
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
        ob["password"] = str(_take(d, used, "password"))
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


def convert(proxies: List[dict]) -> Tuple[List[dict], List[str]]:
    out, report, seen = [], [], set()
    for d in proxies:
        name = str(d.get("name", "?"))
        try:
            if name in seen:
                raise Unsupported("节点名称重复")
            ob = convert_one(d)
            out.append(ob)
            seen.add(name)
        except Unsupported as e:
            report.append(f"跳过 {name}（{d.get('type')}）：{e}")
        except (KeyError, ValueError, TypeError) as e:
            report.append(f"跳过 {name}（{d.get('type')}）：字段缺失或格式错误 {e}")
    return out, report

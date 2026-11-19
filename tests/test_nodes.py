"""Clash/mihomo 订阅 → sing-box 节点转换。期望按 sing-box 1.14 文档字段手写（示例值均为虚构）。"""
import json
import unittest

from helpers import build, model_and_plan
from generator import emit_singbox
from generator.nodes import convert, load_clash_proxies

SAMPLE = [
    {"name": "🇭🇰 香港 01", "type": "ss", "server": "hk1.example.net", "port": 8388,
     "cipher": "2022-blake3-aes-128-gcm", "password": "RVhBTVBMRS1LRVktMTIzNA==", "udp": True},
    {"name": "日本 东京 VLESS", "type": "vless", "server": "jp1.example.net", "port": 443,
     "uuid": "00000000-0000-4000-8000-000000000001", "flow": "xtls-rprx-vision", "tls": True,
     "servername": "www.example.com", "client-fingerprint": "chrome", "network": "tcp", "udp": True,
     "reality-opts": {"public-key": "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA", "short-id": "abcd"}},
    {"name": "美国 Trojan WS", "type": "trojan", "server": "us1.example.net", "port": 443,
     "password": "EXAMPLE", "sni": "us1.example.net", "network": "ws",
     "ws-opts": {"path": "/ws", "headers": {"Host": "us1.example.net"}}},
    {"name": "新加坡 HY2", "type": "hysteria2", "server": "sg1.example.net", "port": 443,
     "ports": "20000-30000", "password": "EXAMPLE", "sni": "sg1.example.net", "up": "50 Mbps", "down": 200,
     "obfs": "salamander", "obfs-password": "EXAMPLE-OBFS"},
    {"name": "台湾 TUIC", "type": "tuic", "server": "tw1.example.net", "port": 443,
     "uuid": "00000000-0000-4000-8000-000000000002", "password": "EXAMPLE", "sni": "tw1.example.net",
     "congestion-controller": "bbr", "udp-relay-mode": "native", "alpn": ["h3"]},
    {"name": "韩国 VMess gRPC", "type": "vmess", "server": "kr1.example.net", "port": 443,
     "uuid": "00000000-0000-4000-8000-000000000003", "alterId": 0, "cipher": "auto", "tls": True,
     "servername": "kr1.example.net", "network": "grpc", "grpc-opts": {"grpc-service-name": "svc"}, "udp": True},
    # 不支持：shadow-tls 插件、TUIC v4、未知参数 —— 必须报告并跳过
    {"name": "英国 SS ShadowTLS", "type": "ss", "server": "uk1.example.net", "port": 443, "cipher": "aes-128-gcm",
     "password": "EXAMPLE", "plugin": "shadow-tls", "plugin-opts": {"host": "www.example.com", "password": "x", "version": 3}},
    {"name": "德国 TUIC v4", "type": "tuic", "server": "de1.example.net", "port": 443, "token": "EXAMPLE"},
    {"name": "法国 奇怪参数", "type": "trojan", "server": "fr1.example.net", "port": 443, "password": "x",
     "some-future-option": True},
    {"name": "剩余流量：100GB", "type": "ss", "server": "127.0.0.1", "port": 1, "cipher": "aes-128-gcm", "password": "x"},
]


class NodeConversion(unittest.TestCase):
    def setUp(self):
        self.out, self.report, self.renamed = convert(SAMPLE)
        self.by = {o["tag"]: o for o in self.out}

    def test_supported_protocols(self):
        ss = self.by["🇭🇰 香港 01"]
        self.assertEqual(ss, {"tag": "🇭🇰 香港 01", "server": "hk1.example.net", "server_port": 8388,
                              "type": "shadowsocks", "method": "2022-blake3-aes-128-gcm", "password": "RVhBTVBMRS1LRVktMTIzNA=="})
        v = self.by["日本 东京 VLESS"]
        self.assertEqual(v["type"], "vless")
        self.assertEqual(v["flow"], "xtls-rprx-vision")
        self.assertEqual(v["tls"], {"enabled": True, "server_name": "www.example.com",
                                    "utls": {"enabled": True, "fingerprint": "chrome"},
                                    "reality": {"enabled": True, "public_key": "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA", "short_id": "abcd"}})
        self.assertNotIn("transport", v)
        t = self.by["美国 Trojan WS"]
        self.assertEqual(t["transport"], {"type": "ws", "path": "/ws", "headers": {"Host": "us1.example.net"}})
        self.assertEqual(t["network"], "tcp", "订阅未开启 UDP 时保持只走 TCP")
        self.assertEqual(t["tls"], {"enabled": True, "server_name": "us1.example.net"})
        h = self.by["新加坡 HY2"]
        self.assertEqual(h["server_ports"], ["20000:30000"])
        self.assertEqual((h["up_mbps"], h["down_mbps"]), (50, 200))
        self.assertEqual(h["obfs"], {"type": "salamander", "password": "EXAMPLE-OBFS"})
        tu = self.by["台湾 TUIC"]
        self.assertEqual((tu["congestion_control"], tu["udp_relay_mode"]), ("bbr", "native"))
        self.assertEqual(tu["tls"]["alpn"], ["h3"])
        vm = self.by["韩国 VMess gRPC"]
        self.assertEqual(vm["transport"], {"type": "grpc", "service_name": "svc"})
        self.assertEqual(vm["security"], "aes-128-gcm", "auto 加 TLS：照 mihomo 在 arm64 / amd64 上的选择写明（R22-F09）")

    def test_tls_never_relaxed(self):
        for o in self.out:
            if "tls" in o:
                self.assertNotIn("insecure", o["tls"], f"{o['tag']} 原订阅未要求跳过证书校验")

    def test_unsupported_reported_not_silently_changed(self):
        text = "\n".join(self.report)
        for name in ("英国 SS ShadowTLS", "德国 TUIC v4", "法国 奇怪参数"):
            self.assertIn(name, text)
            self.assertNotIn(name, self.by)
        self.assertIn("some-future-option", text)

    def test_nodes_land_in_regions_and_info_nodes_excluded(self):
        m, p = model_and_plan()
        conf = json.loads(emit_singbox.build(m, p, "1.14", self.out))
        ob = {o["tag"]: o for o in conf["outbounds"]}
        self.assertEqual(ob["香港·手动"]["outbounds"], ["🇭🇰 香港 01"])
        self.assertEqual(ob["日本·自动"]["outbounds"], ["日本 东京 VLESS"])
        self.assertEqual(ob["PayPal·美国固定"]["outbounds"], ["美国 Trojan WS"])
        for g in ob.values():
            if g["type"] in ("selector", "urltest"):
                self.assertNotIn("剩余流量：100GB", g["outbounds"])
        self.assertEqual(ob["其他地区"]["outbounds"], ["无可用节点"], "转换失败的欧洲节点不应出现")
        self.assertIn("无可用节点", ob)
        self.assertEqual(ob["无可用节点"]["type"], "block")


# sing-box v1.14.1 各出站允许的顶层字段（option/*.go 结构体的 json 标签；DialerOptions 只列本转换器会写的几项）。
# 用来离线防止 F01 这类“字段名在别的出站存在、但这个出站没有”的错误；最终以官方 sing-box check 为准。
DIAL = {"tag", "type", "server", "server_port", "tcp_fast_open", "tcp_multi_path"}
ALLOWED = {
    "shadowsocks": DIAL | {"method", "password", "plugin", "plugin_opts", "network", "udp_over_tcp", "multiplex"},
    "vmess": DIAL | {"uuid", "security", "alter_id", "global_padding", "authenticated_length", "network", "tls",
                     "packet_encoding", "multiplex", "transport"},
    "vless": DIAL | {"uuid", "flow", "network", "tls", "multiplex", "transport", "packet_encoding"},
    "trojan": DIAL | {"password", "network", "tls", "multiplex", "transport"},
    "hysteria2": DIAL | {"server_ports", "hop_interval", "up_mbps", "down_mbps", "obfs", "password", "network", "tls"},
    "tuic": DIAL | {"uuid", "password", "congestion_control", "udp_relay_mode", "udp_over_stream", "zero_rtt_handshake",
                    "heartbeat", "network", "tls"},
    "anytls": DIAL | {"tls", "password", "idle_session_check_interval", "idle_session_timeout", "min_idle_session"},
    "socks": DIAL | {"version", "username", "password", "network", "udp_over_tcp"},
    "http": DIAL | {"username", "password", "tls", "path", "headers"},
}


def one(d):
    out, report, renamed = convert([d])
    return (out[0] if out else None), "\n".join(report)


class NodeConversionNegative(unittest.TestCase):
    """审核 F01 / F02 / F03 / F12 的负向输入：要么等价转换，要么报告并跳过，不能静默改语义。"""

    def test_fields_exist_on_each_outbound_type(self):
        base = {"server": "x.example.net", "port": 443}
        samples = [
            {"name": "http 无 udp", "type": "http", **base},
            {"name": "http 带账号", "type": "http", "username": "u", "password": "p", "tls": True, **base},
            {"name": "socks 无 udp", "type": "socks5", **base},
            {"name": "anytls udp", "type": "anytls", "password": "p", "udp": True, **base},
            {"name": "trojan 无 udp", "type": "trojan", "password": "p", **base},
            {"name": "ss 无 udp", "type": "ss", "cipher": "aes-128-gcm", "password": "p", **base},
        ] + SAMPLE
        out, report, _ = convert(samples)
        for o in out:
            extra = set(o) - ALLOWED[o["type"]]
            self.assertFalse(extra, f"{o['tag']}（{o['type']}）写了该出站没有的字段 {sorted(extra)}")
        by = {o["tag"]: o for o in out}
        self.assertNotIn("network", by["http 无 udp"], "HTTP 出站没有 network 字段（F01）")
        self.assertEqual(by["socks 无 udp"]["network"], "tcp")

    def test_anytls_without_udp_is_reported(self):
        ob, rep = one({"name": "a", "type": "anytls", "server": "x.example.net", "port": 443, "password": "p"})
        self.assertIsNone(ob)
        self.assertIn("UDP", rep)

    def test_missing_required_fields_are_reported(self):
        base = {"server": "x.example.net", "port": 443}
        cases = [
            {"name": "ss 缺密码", "type": "ss", "cipher": "aes-128-gcm", **base},
            {"name": "ss 缺加密", "type": "ss", "password": "p", **base},
            {"name": "trojan 空密码", "type": "trojan", "password": "", **base},
            {"name": "vmess 缺 uuid", "type": "vmess", **base},
            {"name": "vless 缺 uuid", "type": "vless", **base},
            {"name": "hy2 缺密码", "type": "hysteria2", **base},
            {"name": "tuic 缺密码", "type": "tuic", "uuid": "u", **base},
            {"name": "anytls 缺密码", "type": "anytls", "udp": True, **base},
            {"name": "端口不是数字", "type": "ss", "cipher": "aes-128-gcm", "password": "p", "server": "x", "port": "abc"},
            {"name": "缺服务器", "type": "trojan", "password": "p", "port": 443},
        ]
        out, report, _ = convert(cases + ["不是字典", 42])
        self.assertEqual(out, [])
        text = "\n".join(report)
        for c in cases:
            self.assertIn(c["name"], text)
        self.assertNotIn('"None"', json.dumps(out))
        self.assertIn("第 12 项", text)

    def test_v2ray_plugin_mux_and_host_semantics(self):
        base = {"type": "ss", "server": "x.example.net", "port": 443, "cipher": "aes-128-gcm", "password": "p",
                "plugin": "v2ray-plugin"}
        off, _ = one({"name": "关 mux", **base, "plugin-opts": {"mode": "websocket", "mux": False}})
        self.assertIn("mux=0", off["plugin_opts"], "mux: false 不能被当成缺省重新开启（F03）")
        self.assertIn("host=bing.com", off["plugin_opts"], "缺省 Host 按 mihomo 的 bing.com 写出")
        on, _ = one({"name": "缺省 mux", **base, "plugin-opts": {"mode": "websocket", "host": "cdn.example.com"}})
        self.assertIn("mux=1", on["plugin_opts"])
        self.assertIn("host=cdn.example.com", on["plugin_opts"])
        for opts in ({"mode": "websocket", "headers": {"X-A": "1"}}, {"mode": "websocket", "some-new-key": 1},
                     {"host": "a.example.com"}, {"mode": "websocket", "v2ray-http-upgrade": True}):
            ob, rep = one({"name": "不支持", **base, "plugin-opts": opts})
            self.assertIsNone(ob, opts)
            self.assertIn("不支持", rep)

    def test_obfs_plugin_semantics(self):
        base = {"type": "ss", "server": "x.example.net", "port": 443, "cipher": "aes-128-gcm", "password": "p",
                "plugin": "obfs"}
        ob, _ = one({"name": "obfs", **base, "plugin-opts": {"mode": "tls"}})
        self.assertEqual(ob["plugin_opts"], "obfs=tls;obfs-host=bing.com")
        for opts in ({}, {"mode": "http", "extra": 1}):
            ob, rep = one({"name": "obfs 不支持", **base, "plugin-opts": opts})
            self.assertIsNone(ob, opts)

    def test_ws_early_data_and_http_upgrade(self):
        base = {"type": "vmess", "server": "x.example.net", "port": 443, "uuid": "u", "network": "ws", "udp": True}
        ob, _ = one({"name": "ed 在路径里", **base, "ws-opts": {"path": "/ray?ed=2048"}})
        self.assertEqual(ob["transport"], {"type": "ws", "path": "/ray", "max_early_data": 2048,
                                           "early_data_header_name": "Sec-WebSocket-Protocol"})
        ob, _ = one({"name": "ed 无头名", **base, "ws-opts": {"path": "/ray", "max-early-data": 2048}})
        self.assertNotIn("early_data_header_name", ob["transport"], "未写头名时两个内核都把 early data 放在路径里")
        ob, _ = one({"name": "httpupgrade", **base, "ws-opts": {"path": "/up", "v2ray-http-upgrade": True,
                                                              "headers": {"Host": "h.example.com", "X-Token": "t"}}})
        self.assertEqual(ob["transport"], {"type": "httpupgrade", "path": "/up", "host": "h.example.com",
                                           "headers": {"X-Token": "t"}})
        ob, rep = one({"name": "httpupgrade+ed", **base, "ws-opts": {"v2ray-http-upgrade": True, "max-early-data": 1}})
        self.assertIsNone(ob)

    def test_names_colliding_with_groups_are_renamed_and_still_filtered(self):
        m, p = model_and_plan()
        reserved = emit_singbox.reserved_tags(m)
        self.assertTrue({"日本", "DIRECT", "无可用节点", "Grok", "日本·自动"} <= reserved)
        nodes = [{"name": n, "type": "ss", "server": "x.example.net", "port": 443, "cipher": "aes-128-gcm",
                  "password": "p", "udp": True} for n in ("日本", "DIRECT", "无可用节点", "日本（节点）")]
        out, report, renamed = convert(nodes, reserved)
        tags = [o["tag"] for o in out]
        self.assertEqual(len(tags), 4)
        self.assertFalse(set(tags) & reserved)
        self.assertEqual(len(set(tags)), 4)
        self.assertEqual(sorted(renamed.values()), sorted(["日本", "DIRECT", "无可用节点", "日本（节点）"]))
        conf = json.loads(emit_singbox.build(m, p, "1.14", out, renamed))
        all_tags = [o["tag"] for o in conf["outbounds"]]
        self.assertEqual(len(all_tags), len(set(all_tags)), "整份配置不能有重名出站")
        ob = {o["tag"]: o for o in conf["outbounds"]}
        jp = [renamed.get(t, t) for t in ob["日本·手动"]["outbounds"]]
        self.assertIn("日本", jp, "改名后仍按订阅原名进入日本组")



class FullReview20261118(unittest.TestCase):
    """全项目复核（2026-11-18，docs/08 第 21 轮）F01–F03 和同一类：只能走 TLS 的协议、布尔字段的写法、packet-encoding 的取值。"""
    BASE = {"server": "x.example.net", "port": 443}

    def test_tls_only_protocols_keep_tls_whatever_the_subscription_says(self):
        """F01：mihomo 的 Trojan、Hysteria2、TUIC、AnyTLS 没有 tls 开关（不认这个字段），订阅里写了 tls: false 也照样走 TLS。
        以前 Trojan 按 tls: false 转成了不加密的出站。现在四种都开 TLS，并在报告里提一句。"""
        cases = [{"type": "trojan", "password": "p"},
                 {"type": "trojan", "password": "p", "network": "ws", "ws-opts": {"path": "/ws"}},
                 {"type": "hysteria2", "password": "p"},
                 {"type": "tuic", "uuid": "u", "password": "p"},
                 {"type": "anytls", "password": "p", "udp": True}]
        for c in cases:
            for v in (False, "false", 0, None):
                ob, rep = one({"name": "n", **self.BASE, **c, "tls": v, "sni": "x.example.net", "skip-cert-verify": False})
                self.assertIsNotNone(ob, (c, v, rep))
                self.assertEqual(ob["tls"], {"enabled": True, "server_name": "x.example.net"}, (c, v))
                self.assertIn("只能走 TLS", rep, (c, v))
            for extra in ({}, {"tls": True}):
                ob, rep = one({"name": "n", **self.BASE, **c, **extra})
                self.assertEqual(ob["tls"], {"enabled": True}, (c, extra))
                self.assertEqual(rep, "", "没写 tls、或者写了 true，不用提")
            ob, _ = one({"name": "n", **self.BASE, **c, "tls": False, "skip-cert-verify": True})
            self.assertIs(ob["tls"]["insecure"], True, "订阅要求跳过证书校验的，照旧跳过")
        # 真有 TLS 开关的协议（mihomo 的 VMess、VLESS、HTTP 有 tls 字段）：照订阅的开关
        for c in ({"type": "vmess", "uuid": "u"}, {"type": "vless", "uuid": "u"}, {"type": "http"}):
            ob, rep = one({"name": "n", **self.BASE, **c, "tls": False})
            self.assertNotIn("tls", ob, c)
            self.assertEqual(rep, "", c)
            ob, _ = one({"name": "n", **self.BASE, **c, "tls": True})
            self.assertEqual(ob["tls"], {"enabled": True}, c)

    def test_boolean_fields_must_really_be_booleans(self):
        """F02：带引号的 "false" 在 Python 里是真，以前 skip-cert-verify: "false" 反而跳过了证书校验。布尔字段只认 true / false
        （和整数：mihomo 的解码器把整数按非零为真）；别的写法 mihomo 也读不了，跳过这个节点并说明是哪个字段。"""
        ss = {"type": "ss", "cipher": "aes-128-gcm", "password": "p"}
        bad = [({"type": "http", "tls": True, "skip-cert-verify": "false"}, "skip-cert-verify"),
               ({"type": "trojan", "password": "p", "skip-cert-verify": "false"}, "skip-cert-verify"),
               ({"type": "vmess", "uuid": "u", "tls": "true"}, "tls"),
               ({"type": "vless", "uuid": "u", "tls": True, "skip-cert-verify": "no"}, "skip-cert-verify"),
               ({**ss, "udp": "false"}, "udp"),
               ({**ss, "tfo": "true"}, "tfo"),
               ({**ss, "mptcp": "false"}, "mptcp"),
               ({**ss, "udp-over-tcp": "false"}, "udp-over-tcp"),
               ({**ss, "smux": {"enabled": "false"}}, "smux.enabled"),
               ({**ss, "smux": {"enabled": True, "padding": "false"}}, "smux.padding"),
               ({**ss, "plugin": "v2ray-plugin", "plugin-opts": {"mode": "websocket", "tls": "false"}}, "plugin-opts.tls"),
               ({**ss, "plugin": "v2ray-plugin", "plugin-opts": {"mode": "websocket", "mux": "false"}}, "plugin-opts.mux"),
               ({"type": "vmess", "uuid": "u", "network": "ws", "ws-opts": {"path": "/", "v2ray-http-upgrade": "false"}},
                "ws-opts.v2ray-http-upgrade"),
               ({"type": "vmess", "uuid": "u", "global-padding": "false"}, "global-padding"),
               ({"type": "vmess", "uuid": "u", "authenticated-length": "false"}, "authenticated-length"),
               ({"type": "tuic", "uuid": "u", "password": "p", "reduce-rtt": "false"}, "reduce-rtt"),
               ({"type": "tuic", "uuid": "u", "password": "p", "disable-sni": "false"}, "disable-sni"),
               ({"type": "socks5", "tls": "false"}, "tls"),
               ({"type": "socks5", "skip-cert-verify": "false"}, "skip-cert-verify")]
        for c, key in bad:
            ob, rep = one({"name": "n", **self.BASE, **c})
            self.assertIsNone(ob, c)
            self.assertIn(f"{key} 应该是 true / false", rep, c)
        ob, rep = one({"name": "n", **self.BASE, **ss, "smux": "true"})
        self.assertIsNone(ob)
        self.assertIn("smux 不是键值表", rep)
        # 真正的布尔值和整数照常转换
        good = [({**ss, "udp": 0}, lambda o: o["network"] == "tcp"),
                ({**ss, "udp": 1}, lambda o: "network" not in o),
                ({**ss, "udp": False}, lambda o: o["network"] == "tcp"),
                ({"type": "http", "tls": True, "skip-cert-verify": False}, lambda o: o["tls"] == {"enabled": True}),
                ({"type": "http", "tls": True, "skip-cert-verify": 0}, lambda o: o["tls"] == {"enabled": True}),
                ({"type": "http", "tls": True, "skip-cert-verify": True}, lambda o: o["tls"]["insecure"] is True),
                ({"type": "trojan", "password": "p", "skip-cert-verify": 1}, lambda o: o["tls"]["insecure"] is True),
                ({"type": "socks5", "tls": False, "skip-cert-verify": False}, lambda o: "tls" not in o),
                ({**ss, "plugin": "v2ray-plugin", "plugin-opts": {"mode": "websocket", "mux": 0}},
                 lambda o: "mux=0" in o["plugin_opts"]),
                ({**ss, "plugin": "v2ray-plugin", "plugin-opts": {"mode": "websocket", "mux": True, "tls": True}},
                 lambda o: o["plugin_opts"] == "mode=websocket;tls;host=bing.com;mux=1"),
                ({**ss, "smux": {"enabled": False}}, lambda o: "multiplex" not in o)]
        for c, ok in good:
            ob, rep = one({"name": "n", **self.BASE, **c})
            self.assertIsNotNone(ob, (c, rep))
            self.assertTrue(ok(ob), (c, ob))

    def test_packet_encoding_values(self):
        """F03：packet 是 mihomo 对 packetaddr 的另一种写法（v1.19.31 adapter/outbound/vmess.go、vless.go），sing-box 1.14.1 / 1.12.0
        不认，建出站时报 unknown packet encoding。转换成 packetaddr；认不出的值跳过并报告。"""
        for t, absent in (("vmess", None), ("vless", "xudp")):
            base = {"name": "n", "type": t, **self.BASE, "uuid": "u", "udp": True}
            for v, want in (("packet", "packetaddr"), ("packetaddr", "packetaddr"), ("xudp", "xudp"), ("", absent), (None, absent)):
                ob, rep = one({**base, "packet-encoding": v})
                self.assertEqual(ob.get("packet_encoding"), want, (t, v))
                self.assertEqual(rep, "", (t, v))
            ob, _ = one(base)
            self.assertEqual(ob.get("packet_encoding"), absent, "没写时：VMess 不加，VLESS 照 mihomo 用 xudp")
            ob, rep = one({**base, "packet-encoding": "foo"})
            self.assertIsNone(ob)
            self.assertIn("packet-encoding", rep)
            # mihomo 另有 xudp、packet-addr 两个开关：没有映射，照旧报告并跳过
            for k in ("xudp", "packet-addr"):
                ob, rep = one({**base, k: True})
                self.assertIsNone(ob, (t, k))
                self.assertIn(k, rep)


class FullReviewsTwoAndThree(unittest.TestCase):
    """2026-11-18 的另两份全项目复核（docs/08 第 22、23 轮）和 F03 的同一类自查：sing-box 不认的取值、Reality、Hysteria2 的端口、
    多路复用、按 mihomo 的读法解析订阅。以前这些写法会被原样写进配置，sing-box 读配置或建出站时报错，整份配置启动不了。"""
    BASE = {"server": "x.example.net", "port": 443}
    UUID = {"uuid": "00000000-0000-4000-8000-000000000001"}
    PK = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA"

    def test_values_singbox_does_not_accept_are_skipped(self):
        """F03 的同一类：加密方式、flow、拥塞控制、uTLS 指纹、多路复用协议只放行 sing-box 1.14.1、1.12.0 都认的取值
        （handoff/notes/r22_singbox_enum_sweep.py 拿官方程序逐个核对）。"""
        u = self.UUID
        bad = [({"type": "ss", "cipher": "aes-128-ccm", "password": "p"}, "cipher"),
               ({"type": "ss", "cipher": "AES-128-GCM", "password": "p"}, "cipher"),
               ({"type": "ss", "cipher": "chacha20", "password": "p"}, "cipher"),
               ({"type": "vmess", **u, "cipher": "aes-128-ctr"}, "cipher"),
               ({"type": "tuic", **u, "password": "p", "congestion-controller": "bbr_meta_v1"}, "congestion-controller"),
               ({"type": "vless", **u, "tls": True, "client-fingerprint": "chrome120"}, "client-fingerprint"),
               ({"type": "trojan", "password": "p", "client-fingerprint": "randomizednoalpn"}, "client-fingerprint"),
               ({"type": "ss", "cipher": "aes-128-gcm", "password": "p", "smux": {"enabled": True, "protocol": "mplex"}},
                "smux.protocol")]
        for c, key in bad:
            ob, rep = one({"name": "n", **self.BASE, **c})
            self.assertIsNone(ob, c)
            self.assertIn(f"{key}=", rep, c)
            self.assertIn("sing-box 1.14.1、1.12.0 都不认", rep, c)
        good = [({"type": "ss", "cipher": "2022-blake3-aes-128-gcm", "password": "RVhBTVBMRS1LRVktMTIzNA=="},
                 lambda o: o["method"] == "2022-blake3-aes-128-gcm"),
                ({"type": "ss", "cipher": "none", "password": "p"}, lambda o: o["method"] == "none"),
                ({"type": "vmess", **u}, lambda o: o["security"] == "auto"),
                ({"type": "vmess", **u, "cipher": ""}, lambda o: o["security"] == "auto"),
                ({"type": "vmess", **u, "cipher": "zero"}, lambda o: o["security"] == "zero"),
                ({"type": "tuic", **u, "password": "p", "congestion-controller": "new_reno"},
                 lambda o: o["congestion_control"] == "new_reno"),
                ({"type": "vless", **u, "tls": True, "client-fingerprint": "chrome"},
                 lambda o: o["tls"]["utls"] == {"enabled": True, "fingerprint": "chrome"}),
                # none 在 mihomo 里是不用 uTLS（component/tls/utls.go）：不写 uTLS（以前写成指纹 none，sing-box 不认）
                ({"type": "vless", **u, "tls": True, "client-fingerprint": "none"}, lambda o: "utls" not in o["tls"]),
                # 没开 TLS 时指纹用不到，写了什么都不管
                ({"type": "vmess", **u, "client-fingerprint": "chrome120"}, lambda o: "tls" not in o),
                ({"type": "ss", "cipher": "aes-128-gcm", "password": "p", "smux": {"enabled": True, "protocol": "smux"}},
                 lambda o: o["multiplex"]["protocol"] == "smux")]
        for c, ok in good:
            ob, rep = one({"name": "n", **self.BASE, **c})
            self.assertIsNotNone(ob, (c, rep))
            self.assertTrue(ok(ob), (c, ob))

    def test_reality_needs_a_fingerprint_a_public_key_and_a_hex_short_id(self):
        """第二份复核 C2：short-id 留空以前写成 "None"、公钥 null 写成 JSON null；Reality 没有指纹时 sing-box 建出站就报错。"""
        base = {"name": "n", "type": "vless", **self.BASE, **self.UUID, "tls": True, "servername": "www.example.com",
                "flow": "xtls-rprx-vision", "client-fingerprint": "chrome"}
        for sid, want in ((None, ""), ("", ""), ("abcd", "abcd"), ("0123456789abcdef", "0123456789abcdef"), (12, "12")):
            ob, rep = one({**base, "reality-opts": {"public-key": self.PK, "short-id": sid}})
            self.assertEqual(ob["tls"]["reality"], {"enabled": True, "public_key": self.PK, "short_id": want}, (sid, rep))
        ob, _ = one({**base, "reality-opts": {"public-key": self.PK}})
        self.assertEqual(ob["tls"]["reality"]["short_id"], "")
        for opts, needle in (({"public-key": self.PK, "short-id": "abc"}, "short-id"),
                             ({"public-key": self.PK, "short-id": "0123456789abcdef01"}, "short-id"),
                             ({"public-key": self.PK, "short-id": "zz"}, "short-id"),
                             ({"short-id": "ab"}, "public-key"), ({"public-key": None}, "public-key"),
                             ({"public-key": "EXAMPLE"}, "public-key"), ({"public-key": self.PK + "="}, "public-key")):
            ob, rep = one({**base, "reality-opts": opts})
            self.assertIsNone(ob, opts)
            self.assertIn(needle, rep, opts)
        for extra in ({"client-fingerprint": None}, {"client-fingerprint": "none"}):
            ob, rep = one({**base, **extra, "reality-opts": {"public-key": self.PK}})
            self.assertIsNone(ob, extra)
            self.assertIn("Reality 要有 client-fingerprint", rep)

    def test_hysteria2_ports_and_hop_interval_like_mihomo(self):
        """第二份复核 C2：mihomo 的 ports 逗号、斜杠都能分隔，可以有单个端口；sing-box 每一项都要写成 a:b。
        hop-interval 可以是区间；mihomo 把 0 当成 30、小于 5 的按 5。"""
        base = {"name": "n", "type": "hysteria2", **self.BASE, "password": "p"}
        for ports, want in (("443,20000-30000/40000-40010", ["443:443", "20000:30000", "40000:40010"]),
                            (443, ["443:443"]), ("20000 - 30000", ["20000:30000"]), ("443,,444", ["443:443", "444:444"])):
            ob, rep = one({**base, "ports": ports})
            self.assertEqual(ob["server_ports"], want, (ports, rep))
            self.assertNotIn("hop_interval", ob)
        for ports in ("0-10", "443-70000", "30000-20000", "a-b", ",".join(str(1000 + i) for i in range(29))):
            ob, rep = one({**base, "ports": ports})
            self.assertIsNone(ob, ports)
            self.assertIn("ports", rep)
        for hop, want, note in (("30", "30s", False), (3, "5s", False), ("0", "30s", False), ("30-60", "30s", True),
                                ("60-30", "60s", False)):
            ob, rep = one({**base, "ports": "20000-30000", "hop-interval": hop})
            self.assertEqual(ob["hop_interval"], want, hop)
            self.assertEqual("区间" in rep, note, (hop, rep))
        ob, rep = one({**base, "ports": "20000-30000", "hop-interval": "x"})
        self.assertIsNone(ob)
        self.assertIn("hop-interval", rep)

    def test_multiplex_only_where_singbox_has_it(self):
        """第二份复核 C2：sing-box 只有 shadowsocks、vmess、vless、trojan 有 multiplex 字段，别的写了读配置就报错。"""
        smux = {"smux": {"enabled": True}}
        for c in ({"type": "socks5"}, {"type": "http"}, {"type": "hysteria2", "password": "p"},
                  {"type": "tuic", **self.UUID, "password": "p"}, {"type": "anytls", "password": "p", "udp": True}):
            ob, rep = one({"name": "n", **self.BASE, **c, **smux})
            self.assertIsNone(ob, c)
            self.assertIn("没有多路复用", rep)
            ob, _ = one({"name": "n", **self.BASE, **c, "smux": {"enabled": False}})
            self.assertNotIn("multiplex", ob, c)
        for c in ({"type": "ss", "cipher": "aes-128-gcm", "password": "p"}, {"type": "vmess", **self.UUID},
                  {"type": "vless", **self.UUID}, {"type": "trojan", "password": "p"}):
            ob, rep = one({"name": "n", **self.BASE, **c, **smux})
            self.assertEqual(ob["multiplex"], {"enabled": True, "protocol": "h2mux"}, (c, rep))

    def test_subscription_is_parsed_like_mihomo(self):
        """第二份复核 C3：mihomo 用 go.yaml.in/yaml/v3 v3.0.5 读订阅。0 开头的数字两边都按八进制读（审核方说 mihomo 保留前导零，
        核对源码不是这样）；不同的是 yes / no / on / off（PyYAML 读成布尔，mihomo 是文字）、六十进制（1:20）、0089 这种
        （mihomo 读成小数）。这里按 mihomo 的读法。"""
        text = "\n".join([
            "proxies:",
            "  - {name: a, type: ss, server: x.example.net, port: 0443, cipher: aes-128-gcm, password: 01234567, udp: true}",
            "  - {name: b, type: socks5, server: x.example.net, port: 1080, username: no, password: yes}",
            "  - {name: c, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 0089}",
            "  - {name: d, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: p, udp: on}",
            "  - {name: e, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 1:20}",
            "  - {name: f, type: ss, server: x.example.net, port: 0x1BB, cipher: aes-128-gcm, password: 1_000}",
            "  - {name: g, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 1.5}",
            "  - {name: h, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: true}",
            "  - {name: i, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 2026-11-18}",
            "  - {name: j, type: ss, server: x.example.net, port: 0o17, cipher: aes-128-gcm, password: 1e3, udp: ~}"])
        ps = {p["name"]: p for p in load_clash_proxies(text)}
        self.assertEqual((ps["a"]["password"], ps["a"]["port"], ps["a"]["udp"]), (342391, 291, True))
        self.assertEqual((ps["b"]["username"], ps["b"]["password"]), ("no", "yes"))
        self.assertEqual((ps["c"]["password"], ps["d"]["udp"], ps["e"]["password"]), (89.0, "on", "1:20"))
        self.assertEqual((ps["f"]["port"], ps["f"]["password"]), (443, 1000))
        self.assertEqual((ps["j"]["port"], ps["j"]["password"], ps["j"]["udp"]), (15, 1000.0, None))
        out, report, _ = convert(list(ps.values()))
        by = {o["tag"]: o for o in out}
        self.assertEqual(by["a"]["password"], "342391", "和 mihomo 一样：先读成整数，再写成十进制")
        self.assertEqual((by["b"]["username"], by["b"]["password"]), ("no", "yes"), "以前 username: no 被当成没写、password: yes 写成 True")
        self.assertEqual(by["e"]["password"], "1:20")
        self.assertEqual(by["f"]["password"], "1000")
        text = "\n".join(report)
        for name, needle in (("c", "password 写成了 89.0"), ("d", "udp 应该是 true / false"), ("g", "password 写成了 1.5"),
                             ("h", "缺少必填字段 password"), ("i", "password 写成了"), ("j", "password 写成了 1000.0")):
            self.assertNotIn(name, by)
            self.assertIn(needle, text, name)


class ReviewsOfR22Draft(unittest.TestCase):
    """2026-11-19 两份审核 r22 送审稿（docs/08 第 24、25 轮）：GPT 的 R22-F07–F14、另一个 AI 的 F01–F03。
    读订阅、整数字段、取值的归一化都照 mihomo v1.19.31 的实际做法（官方程序实测：handoff/notes/r22b_review_probes.py）；
    SS2022 密钥、QUIC 上的 uTLS、VMess 的 auto 加 TLS 照 sing-box 1.14.1、1.12.0 建出站的实际要求。"""
    BASE = {"server": "x.example.net", "port": 443}
    UUID = {"uuid": "00000000-0000-4000-8000-000000000001"}
    K16 = "RVhBTVBMRS1LRVktMTIzNA=="                       # 虚构：base64 的 16 字节
    K32 = "RVhBTVBMRS1LRVktMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="   # 虚构：base64 的 32 字节

    def node(self, **kw):
        return one({"name": "n", **self.BASE, **kw})

    def test_ss2022_keys_are_checked_like_singbox(self):
        """R22-F07：密钥按冒号分段、每段标准 base64、aes-128 16 字节、另两种 32 字节、chacha20 只能一段（sing-shadowsocks2 v0.2.1）。
        不合格的跳过、报告里只说原因不回显密钥；写盘前检查用同一个判据。"""
        bad = [("2022-blake3-aes-128-gcm", "NOT!BASE64!KEY", "不是标准 base64"),
               ("2022-blake3-aes-128-gcm", "RVhBTVBMRS1LRVktMTIzNA", "不是标准 base64"),      # 没补齐 =
               ("2022-blake3-aes-256-gcm", self.K16, "要 32 字节"),
               ("2022-blake3-chacha20-poly1305", f"{self.K32}:{self.K32}", "多段密钥")]
        for method, key, why in bad:
            ob, rep = self.node(type="ss", cipher=method, password=key)
            self.assertIsNone(ob, (method, key))
            self.assertIn(why, rep, (method, key))
            self.assertNotIn(key, rep.replace(f"{self.K32}:{self.K32}", ""), "报告里不回显密钥")
        for method, key in (("2022-blake3-aes-128-gcm", self.K16), ("2022-blake3-aes-256-gcm", self.K32),
                            ("2022-blake3-aes-128-gcm", f"{self.K16}:{self.K16}"), ("2022-blake3-chacha20-poly1305", self.K32)):
            ob, rep = self.node(type="ss", cipher=method, password=key)
            self.assertIsNotNone(ob, (method, rep))
        from generator import verify
        cfg = {"outbounds": [{"type": "shadowsocks", "tag": "s", "server": "x.example.net", "server_port": 443,
                              "method": "2022-blake3-aes-128-gcm", "password": "x"}, {"type": "direct", "tag": "direct"}]}
        self.assertTrue(any("SS2022 密钥不合格" in p for p in verify.check_singbox(json.dumps(cfg))))

    def test_values_are_normalized_like_mihomo_before_the_whitelist(self):
        """R22-F08：mihomo 先把 VMess 的 cipher 转小写、VLESS 的 flow 只取前 16 个字符、不加引号的数字指纹转成文字，再用。"""
        u = self.UUID
        ob, _ = self.node(type="vmess", **u, cipher="AES-128-GCM")
        self.assertEqual(ob["security"], "aes-128-gcm")
        ob, rep = self.node(type="vless", **u, tls=True, flow="xtls-rprx-vision-udp443")
        self.assertEqual(ob["flow"], "xtls-rprx-vision")
        self.assertIn("只取前 16 个字符", rep)
        ob, rep = self.node(type="vless", **u, tls=True, flow="abc")
        self.assertNotIn("flow", ob)
        self.assertIn("不到 16 个字符", rep)
        ob, rep = self.node(type="vless", **u, tls=True, flow="xtls-rprx-direct")
        self.assertIsNone(ob)
        self.assertIn("mihomo 也建不起", rep)
        ob, _ = self.node(type="trojan", password="p", **{"client-fingerprint": 360})
        self.assertEqual(ob["tls"]["utls"], {"enabled": True, "fingerprint": "360"})

    def test_vmess_auto_with_tls_gets_an_explicit_cipher(self):
        """R22-F09：sing-box 遇到 auto 加 TLS 会把内层改成 zero；mihomo 在 arm64 / amd64 上用 aes-128-gcm。照它写明，报告里说明。"""
        ob, rep = self.node(type="vmess", **self.UUID, cipher="auto", tls=True)
        self.assertEqual(ob["security"], "aes-128-gcm")
        self.assertIn("会把内层加密改成 zero", rep)
        ob, _ = self.node(type="vmess", **self.UUID, cipher="auto")
        self.assertEqual(ob["security"], "auto", "没有 TLS 时两个内核的 auto 都按架构选，照写")
        from generator import verify
        cfg = {"outbounds": [{"type": "vmess", "tag": "v", "server": "x.example.net", "server_port": 443, "uuid": self.UUID["uuid"],
                              "security": "auto", "tls": {"enabled": True}}, {"type": "direct", "tag": "direct"}]}
        self.assertTrue(any("auto 加 TLS" in p for p in verify.check_singbox(json.dumps(cfg))))

    def test_quic_protocols_do_not_get_utls(self):
        """R22-F10：TUIC、Hysteria2 写了浏览器指纹也不开 uTLS（mihomo 没有这个字段；sing-box 在 QUIC 上用 uTLS 拨号报错）。AnyTLS 走 TCP，照写。"""
        fp = {"client-fingerprint": "chrome"}
        for kw in ({"type": "tuic", **self.UUID, "password": "p", **fp}, {"type": "hysteria2", "password": "p", **fp}):
            ob, rep = self.node(**kw)
            self.assertIsNotNone(ob, rep)
            self.assertNotIn("utls", ob["tls"], kw["type"])
            self.assertIn("走 QUIC", rep, kw["type"])
        ob, _ = self.node(type="anytls", password="p", udp=True, **fp)
        self.assertEqual(ob["tls"]["utls"], {"enabled": True, "fingerprint": "chrome"})
        from generator import verify
        cfg = {"outbounds": [{"type": "tuic", "tag": "t", "server": "x.example.net", "server_port": 443, "uuid": self.UUID["uuid"],
                              "password": "p", "tls": {"enabled": True, "utls": {"enabled": True, "fingerprint": "chrome"}}},
                             {"type": "direct", "tag": "direct"}]}
        self.assertTrue(any("开了 uTLS" in p for p in verify.check_singbox(json.dumps(cfg))))

    def test_legacy_chrome_fingerprints_are_kept_with_a_note(self):
        """R22-F11：chrome_psk 这五个，sing-box 认名字、实际用普通 Chrome。照写（节点能用），报告里说明。"""
        ob, rep = self.node(type="trojan", password="p", **{"client-fingerprint": "chrome_pq"})
        self.assertEqual(ob["tls"]["utls"]["fingerprint"], "chrome_pq")
        self.assertIn("实际用的是普通 Chrome", rep)
        ob, rep = self.node(type="trojan", password="p", **{"client-fingerprint": "firefox"})
        self.assertNotIn("普通 Chrome", rep)

    def test_integer_fields_are_read_like_go(self):
        """R22-F14、另一个 AI 的 F03：整数字段按 mihomo 的 decodeInt——文字按 Go 的 ParseInt(基数 0)，布尔读不了；
        Hysteria2 不加引号的 password: 0 不是“缺密码”。"""
        for raw, want in (("0100", 64), ("0x01bb", 443), ("4_43", 443), (443.9, 443), ("443", 443)):
            ob, rep = self.node(type="trojan", password="p", port=raw)
            self.assertEqual(ob["server_port"], want, raw)
            if isinstance(raw, str) and raw[0] == "0":
                self.assertIn("按 Go 的规则读成", rep, raw)
        for raw in ("08", True, "abc"):
            ob, rep = self.node(type="trojan", password="p", port=raw)
            self.assertIsNone(ob, raw)
        ob, rep = self.node(type="vmess", **self.UUID, alterId=True)
        self.assertIsNone(ob)
        self.assertIn("alterId 应该是数字", rep)
        ob, rep = self.node(type="hysteria2", password=0)
        self.assertEqual(ob["password"], "0", rep)
        ob, rep = self.node(type="hysteria2", up=True, password="p")
        self.assertIsNone(ob)

    def test_scalars_are_resolved_like_go_yaml(self):
        """R22-F12、另一个 AI 的 F01、F02：不带引号的值照 go-yaml v3.0.5 的 resolve 读。左边的值都拿官方 mihomo v1.19.31
        实测过（放进节点名字，从控制接口读回来，handoff/notes/r22b_review_probes.py）。以前 0x_、2026-02-30、= 让整份订阅读不下去。"""
        import datetime
        cases = {"0x_": "0x_", "0b_": "0b_", "0o_": "0o_", "0_": 0, "1_000": 1000, "0x_20": 32, "1__0": 10, "0x1_": 1,
                 "_1": "_1", "01234567": 342391, "0o17": 15, "0089": 89.0, "1_0.5": 10.5, ".5": 0.5,
                 "123456789012345678901": 1.2345678901234568e20, "-9223372036854775809": -9.223372036854776e18,
                 "10000000000000000000": 10000000000000000000, "0x1FFFFFFFFFFFFFFFFF": "0x1FFFFFFFFFFFFFFFFF",
                 "2026-02-30": "2026-02-30", "2026-01-02T03:04:05": "2026-01-02T03:04:05", "2026-1-2": datetime.date(2026, 1, 2),
                 "=": "=", "1e400": "1e400", "0b2": "0b2"}
        for raw, want in cases.items():
            got = load_clash_proxies(f"proxies:\n  - {{name: n, password: {raw}}}\n")[0]["password"]
            self.assertEqual((type(got), got), (type(want), want), raw)
        text = "\n".join(["proxies:",
                          "  - {name: a, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 0x_}",
                          "  - {name: b, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 1_0.5}",
                          "  - {name: c, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 2026-1-2}",
                          "  - {name: d, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: 123456789012345678901}",
                          "  - {name: e, type: ss, server: x.example.net, port: 443, cipher: aes-128-gcm, password: ok}"])
        out, report, _ = convert(load_clash_proxies(text))
        self.assertEqual({o["tag"]: o["password"] for o in out}, {"a": "0x_", "e": "ok"}, "一个怪值只影响它自己那个节点")
        self.assertEqual(sum("读出来不是文字" in r for r in report), 3, report)

    def test_duplicate_keys_reject_the_subscription(self):
        """R22-F13：同一张表里同一个键写两次，mihomo（go-yaml）整份报错；这里也整份不转换，只报键名和行号、不回显值。
        合并（<<）继承来的键被同名的键盖掉是合法的。"""
        text = "\n".join(["proxies:", "  - name: a", "    type: trojan", "    server: x.example.net", "    port: 443",
                          "    password: SECRET-VALUE", "    skip-cert-verify: true", "    skip-cert-verify: false"])
        with self.assertRaises(ValueError) as cm:
            load_clash_proxies(text)
        msg = str(cm.exception)
        self.assertIn("第 8 行的 skip-cert-verify（第 7 行已经有了）", msg)
        self.assertNotIn("SECRET-VALUE", msg)
        text = "\n".join(["base: &b {type: trojan, server: x.example.net, port: 443, password: p, sni: a.example}",
                          "proxies:", "  - {<<: *b, name: a, sni: b.example}"])
        self.assertEqual(load_clash_proxies(text)[0]["sni"], "b.example")

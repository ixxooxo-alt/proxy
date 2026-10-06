"""Clash/mihomo 订阅 → sing-box 节点转换。期望按 sing-box 1.14 文档字段手写（示例值均为虚构）。"""
import json
import unittest

from helpers import build, model_and_plan
from generator import emit_singbox
from generator.nodes import convert

SAMPLE = [
    {"name": "🇭🇰 香港 01", "type": "ss", "server": "hk1.example.net", "port": 8388,
     "cipher": "2022-blake3-aes-128-gcm", "password": "EXAMPLE-KEY", "udp": True},
    {"name": "日本 东京 VLESS", "type": "vless", "server": "jp1.example.net", "port": 443,
     "uuid": "00000000-0000-4000-8000-000000000001", "flow": "xtls-rprx-vision", "tls": True,
     "servername": "www.example.com", "client-fingerprint": "chrome", "network": "tcp", "udp": True,
     "reality-opts": {"public-key": "EXAMPLE_PUBLIC_KEY", "short-id": "abcd"}},
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
                              "type": "shadowsocks", "method": "2022-blake3-aes-128-gcm", "password": "EXAMPLE-KEY"})
        v = self.by["日本 东京 VLESS"]
        self.assertEqual(v["type"], "vless")
        self.assertEqual(v["flow"], "xtls-rprx-vision")
        self.assertEqual(v["tls"], {"enabled": True, "server_name": "www.example.com",
                                    "utls": {"enabled": True, "fingerprint": "chrome"},
                                    "reality": {"enabled": True, "public_key": "EXAMPLE_PUBLIC_KEY", "short_id": "abcd"}})
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
        self.assertEqual(vm["security"], "auto")

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

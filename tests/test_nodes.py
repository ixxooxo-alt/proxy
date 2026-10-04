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
        self.out, self.report = convert(SAMPLE)
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


if __name__ == "__main__":
    unittest.main()

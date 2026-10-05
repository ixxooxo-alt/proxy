"""局域网名字的解析路径：四端都把局域网后缀交给系统 / 本地 DNS，而不是公共 DoH（审核 F04）；
sing-box 拨号时的解析也一样（审核 r9 的 F02）；以及 mihomo 订阅上的健康检查间隔与组一致（审核 3.4）。"""
import json
import unittest

from helpers import load_yaml, model_and_plan, parsed

from generator import emit_singbox, nodes as nodeconv, verify


class LanDns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m, _ = model_and_plan()
        cls.lan = list(m.project["lan"]["domain_suffix"])
        cls.hc = m.hc

    def test_mihomo_sends_lan_suffixes_to_system_dns_first(self):
        for client in ("mihomo-profile", "mihomo-core"):
            dns = parsed(client)["dns"]
            policy = list(dns["nameserver-policy"].items())
            key, servers = policy[0]
            # 必须是第一条：mihomo 按书写顺序匹配，geosite:private 也包含 lan / local
            self.assertEqual(key.split(","), ["+." + s for s in self.lan], client)
            self.assertEqual(servers, ["system"], client)
            self.assertTrue(dns.get("direct-nameserver-follow-policy"), f"{client}：DIRECT 连接的解析要跟随策略")
            for k, v in policy[1:]:
                self.assertNotIn("system", v)

    def test_singbox_uses_local_dns_for_lan_suffixes(self):
        for client in ("singbox-1.14", "singbox-1.12"):
            dns = parsed(client)["dns"]
            local_tags = {s["tag"] for s in dns["servers"] if s.get("type") == "local" or s.get("address") == "local"}
            first = dns["rules"][0]
            self.assertEqual(sorted(first.get("domain_suffix", [])), sorted(self.lan), client)
            self.assertIn(first["server"], local_tags, client)

    def test_singbox_dial_time_resolution_of_lan_names(self):
        """审核 r9 的 F02：sing-box 拨号时解析名字不经过 dns.rules，用的是出站自己的 domain_resolver，没有就用
        route.default_domain_resolver（国内 DoH）。所以：
          1. 节点的服务器地址是局域网里的名字 → 这个节点带 domain_resolver，指向系统 DNS；公网名字、IP 地址的节点不带；
          2. 域名形式的局域网目标 → 在交给直连之前，有一条用系统 DNS 解析它的 resolve 规则；
          3. 默认解析器不变（公网域名的节点仍由国内 DNS 解析，这是原来的设计）。
        期望来自 cases.yaml 的 singbox_dial（人工写的）；官方内核的实际拨号结果另在 test_real_data 里对快照核对。"""
        m, plan = model_and_plan()
        cases = load_yaml("cases.yaml")["singbox_dial"]
        node_cases = [c for c in cases if c["kind"] == "node"]
        proxies = [{"name": f"节点 {i}", "type": "socks5", "server": c["server"], "port": 1080} for i, c in enumerate(node_cases)]
        proxies += [{"name": "地址节点", "type": "socks5", "server": "192.0.2.7", "port": 1080},
                    {"name": "地址节点 v6", "type": "socks5", "server": "2001:db8::7", "port": 1080}]
        conv, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(m))
        self.assertEqual(report, [])
        for variant in ("1.14", "1.12"):
            text = emit_singbox.build(m, plan, variant, nodes=conv, renamed=renamed)
            conf = json.loads(text)
            self.assertEqual(verify.check_singbox(text), [], variant)
            local = [s["tag"] for s in conf["dns"]["servers"] if s.get("type") == "local"]
            self.assertEqual(local, [emit_singbox.LOCAL_DNS_TAG])
            by_server = {o["server"]: o for o in conf["outbounds"] if "server" in o}
            for c in node_cases:
                want = emit_singbox.LOCAL_DNS_TAG if c["expect"] == "dns-local" else None
                self.assertEqual(by_server[c["server"]].get("domain_resolver"), want, f"{variant} {c['server']}")
            for ip in ("192.0.2.7", "2001:db8::7"):
                self.assertNotIn("domain_resolver", by_server[ip], ip)
            self.assertEqual(conf["route"]["default_domain_resolver"], "dns-cn", "默认解析器不变")
            rules = conf["route"]["rules"]
            i_resolve = next(i for i, r in enumerate(rules)
                             if r.get("action") == "resolve" and r.get("server") == emit_singbox.LOCAL_DNS_TAG)
            self.assertEqual(sorted(rules[i_resolve]["domain_suffix"]), sorted(self.lan), variant)
            i_direct = next(i for i, r in enumerate(rules) if r.get("outbound") == "DIRECT" and "lan" in r.get("domain_suffix", []))
            self.assertLess(i_resolve, i_direct, "先解析、再交给直连")
            self.assertEqual([r for r in rules[:i_resolve] if "outbound" in r], [], "它前面只有 sniff / hijack-dns 这类动作")
        # 没有节点的公开模板里同样有这条 resolve 规则
        for client in ("singbox-1.14", "singbox-1.12"):
            self.assertTrue(any(r.get("action") == "resolve" and r.get("server") == emit_singbox.LOCAL_DNS_TAG
                                for r in parsed(client)["route"]["rules"]), client)

    def test_what_counts_as_a_lan_name(self):
        lan = self.lan
        for host in ("gateway.lan", "a.b.local", "proxy.home.arpa", "x.localdomain", "localhost", "nas", "ROUTER", "Gateway.LAN", "nas.lan."):
            self.assertTrue(emit_singbox.is_lan_name(host, lan), host)
        for host in ("node.example.com", "lan.example.com", "evil-lan.com", "notlan.org", "192.168.1.1", "::1", "[fe80::1]", ""):
            self.assertFalse(emit_singbox.is_lan_name(host, lan), host)

    def test_loon_and_qx_use_system_dns_for_lan_suffixes(self):
        host = parsed("loon")["sections"]["Host"]
        self.assertEqual([h for h in host if h.endswith("= server:system")],
                         [f"*.{s} = server:system" for s in self.lan])
        qx = parsed("quantumultx")["sections"]["dns"]
        self.assertEqual([x for x in qx if x.endswith("/system")], [f"server=/*.{s}/system" for s in self.lan])

    def test_mihomo_provider_health_check_matches_groups(self):
        for client in ("mihomo-profile", "mihomo-core"):
            conf = parsed(client)
            for name, prov in conf.get("proxy-providers", {}).items():
                self.assertEqual(prov["health-check"]["interval"], self.hc["interval_s"], f"{client} {name}")
            for g in conf["proxy-groups"]:
                if "interval" in g:
                    self.assertEqual(g["interval"], self.hc["interval_s"], f"{client} {g['name']}")


if __name__ == "__main__":
    unittest.main()

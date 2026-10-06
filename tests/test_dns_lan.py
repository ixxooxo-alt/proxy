"""局域网名字的解析路径：四端都把局域网后缀交给系统 / 本地 DNS，而不是公共 DoH（审核 F04）；
以及 mihomo 订阅上的健康检查间隔与组一致（审核 3.4）。"""
import unittest

from helpers import model_and_plan, parsed


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

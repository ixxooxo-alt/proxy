"""局域网名字的解析路径：四端都把局域网后缀交给系统 / 本地 DNS，而不是公共 DoH（审核 F04）；
sing-box 拨号时的解析也一样（审核 r9 的 F02）；mihomo 节点自己的服务器地址也一样（审核 r10 的 R10-F01）；
没被任何域名规则接住的域名只问境外 DNS（GPT 审核 r12 的第 10 点）；
以及 mihomo 订阅上的健康检查间隔与组一致（审核 3.4）。"""
import json
import unittest

import yaml

from helpers import ROOT, load_yaml, model_and_plan, parsed

from generator import emit_mihomo, emit_singbox, nodes as nodeconv, verify
from generator.model import build_plan, load


def mihomo_policy_matches(patterns, host: str) -> bool:
    """mihomo 域名通配符的含义，只实现策略里用到的两种写法（官方说明 https://wiki.metacubex.one/handbook/syntax/，
    v1.19.31 component/trie/domain.go）：“+.x” 匹配 x 本身和它下面任意多级；单独一个 “*” 只匹配不带点的名字。
    出现别的写法时报错——那时要先弄清它的含义，再决定这里怎么比。"""
    h = host.lower().rstrip(".")
    for pat in patterns:
        if pat == "*":
            if "." not in h:
                return True
        elif pat.startswith("+.") and not set("*+") & set(pat[2:]) and pat[2:]:
            if h == pat[2:] or h.endswith("." + pat[2:]):
                return True
        else:
            raise AssertionError(f"策略里出现了这里不认识的通配写法：{pat}")
    return False


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

    def test_mihomo_node_servers_in_the_lan_use_system_dns(self):
        """审核 r10 的 R10-F01：mihomo 解析节点自己的服务器地址用 proxy-server-nameserver，它的例外另写在
        proxy-server-nameserver-policy 里，不看 nameserver-policy；direct-nameserver-follow-policy 也只管直连出口。所以：
          1. 两份 mihomo 产物都有 proxy-server-nameserver-policy：局域网后缀（+.x 的写法）和不带点的名字（单独的 *）交给 system；
          2. proxy-server-nameserver 还在、还是国内 DoH——公网域名的节点照旧；respect-rules 和这条策略也都要求它不为空；
          3. nameserver-policy 里局域网那一条、direct-nameserver-follow-policy 不变（管访问目标的那一半，审核 F04）。
        期望是按设计人工写的；官方内核的实际拨号结果另在 test_real_data 里对快照核对。"""
        m, _ = model_and_plan()
        suffixes = ",".join("+." + s for s in self.lan)
        for client in ("mihomo-profile", "mihomo-core"):
            dns = parsed(client)["dns"]
            self.assertEqual(list(dns["proxy-server-nameserver-policy"].items()), [(suffixes, ["system"]), ("*", ["system"])], client)
            self.assertEqual(dns["proxy-server-nameserver"], list(m.dns["domestic_doh"]), client)
            self.assertTrue(dns["proxy-server-nameserver"], client)
            self.assertTrue(dns["respect-rules"], client)
            self.assertEqual(list(dns["nameserver-policy"].items())[0], (suffixes, ["system"]), client)
            self.assertNotIn("*", ",".join(dns["nameserver-policy"]),
                             "访问目标那条策略没有“不带点的名字”这一项（那是另一项已知限制，见 docs/06），不要顺手加上")
            self.assertTrue(dns["direct-nameserver-follow-policy"], client)

    def test_mihomo_and_singbox_agree_on_what_a_lan_name_is(self):
        """两个内核的写法不同（mihomo：策略里的通配符；sing-box：生成时用 is_lan_name 判断），对同一个节点服务器名字的
        归类必须相同。两份人工写的拨号用例（cases.yaml 的 mihomo_dial、singbox_dial）也必须是同一批名字、对应的期望。
        IP 地址形式的服务器不查 DNS，不在比较范围里。"""
        patterns = [x for key in parsed("mihomo-core")["dns"]["proxy-server-nameserver-policy"] for x in key.split(",")]
        names = ["gateway.lan", "a.b.local", "proxy.home.arpa", "x.localdomain", "localhost", "printer.localhost", "homeproxy", "nas",
                 "ROUTER", "Gateway.LAN", "lan", "local", "home.arpa", "nas.lan.",
                 "node.example.com", "lan.example.com", "evil-lan.com", "notlan.org", "example.arpa", "home.arpa.example.com",
                 "a.lan.cn", "localhost.example.com", "xn--fiqs8s.example"]
        lan_names = [h for h in names if emit_singbox.is_lan_name(h, self.lan)]
        self.assertEqual(len(lan_names), 14, lan_names)
        for host in names:
            self.assertEqual(mihomo_policy_matches(patterns, host), emit_singbox.is_lan_name(host, self.lan), host)
        cases = load_yaml("cases.yaml")
        same = {"dns-local": "system", "dns-cn": "domestic", "dns-foreign": "foreign", "none": "none"}
        self.assertEqual([(c["kind"], c.get("server"), c.get("host"), same[c["expect"]]) for c in cases["singbox_dial"]],
                         [(c["kind"], c.get("server"), c.get("host"), c["expect"]) for c in cases["mihomo_dial"]])
        nodes = [c for c in cases["mihomo_dial"] if c["kind"] == "node"]
        self.assertTrue(any("." not in c["server"] for c in nodes), "要有不带点的节点服务器名字")
        for c in nodes:
            self.assertEqual(mihomo_policy_matches(patterns, c["server"]), c["expect"] == "system", c["server"])
            self.assertEqual(emit_singbox.is_lan_name(c["server"], self.lan), c["expect"] == "system", c["server"])

    def test_lan_suffix_list_also_drives_node_server_resolution(self):
        """公司自己的内网后缀（不在默认那几个里）加进 lan.domain_suffix 之后：mihomo 的两条策略（访问目标的、节点服务器的）
        都带上它；sing-box 把这个后缀下的节点服务器也交给系统 DNS。“改一处、各端同步”对节点服务器同样成立。"""
        m = load(ROOT, include_local=False)
        m.project["lan"]["domain_suffix"] = list(m.project["lan"]["domain_suffix"]) + ["corp.example"]
        plan = build_plan(m)
        suffixes = ",".join("+." + s for s in self.lan + ["corp.example"])
        for flavor in ("core", "profile"):
            text = emit_mihomo.build(m, plan, flavor)
            self.assertEqual(verify.check_mihomo(text), [], flavor)
            dns = yaml.safe_load(text)["dns"]
            self.assertEqual(list(dns["nameserver-policy"])[0], suffixes, flavor)
            self.assertEqual(list(dns["proxy-server-nameserver-policy"]), [suffixes, "*"], flavor)
        proxies = [{"name": "公司里的节点", "type": "socks5", "server": "proxy.corp.example", "port": 1080},
                   {"name": "公网上的节点", "type": "socks5", "server": "proxy.corp.example.com", "port": 1080}]
        conv, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(m))
        self.assertEqual(report, [])
        conf = json.loads(emit_singbox.build(m, plan, "1.14", nodes=conv, renamed=renamed))
        by_server = {o["server"]: o for o in conf["outbounds"] if "server" in o}
        self.assertEqual(by_server["proxy.corp.example"].get("domain_resolver"), emit_singbox.LOCAL_DNS_TAG)
        self.assertNotIn("domain_resolver", by_server["proxy.corp.example.com"])
        # 没有改动公用的那份模型
        self.assertEqual(list(model_and_plan()[0].project["lan"]["domain_suffix"]), self.lan)

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
            direct = [o for o in conf["outbounds"] if o["type"] == "direct"]
            self.assertEqual(direct, [{"type": "direct", "tag": "DIRECT"}],
                             "直连出站不单独指定解析器：直连的公网域名用默认解析器（国内 DNS），局域网名字靠前面那条 resolve 规则")
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

    def test_mihomo_unmatched_names_ask_only_the_foreign_doh(self):
        """GPT 审核 r12 的第 10 点（交接时也列为下一版要补的）：没被任何域名规则接住的域名只问境外 DNS——把设计约束直接写成断言。
        以前这一条只靠官方内核的记录：把默认的 DNS 换成国内的（变异 M91），离线测试只报“官方内核的记录过期”，
        要重跑 tools/check_real_routes.py 才看得到具体错在哪。mihomo 上这类域名的查询（设备发来的地址以外的类型、
        为判断最后的 GEOIP,CN 而做的解析）都交给 nameserver，所以：
          1. nameserver 就是统一源里的境外 DoH（source/project.yaml 的 dns.foreign_doh）；
          2. respect-rules 开着：这些 DoH 连接按规则走，落到国外默认，从代理出去；
          3. 没有 fallback：境外查询失败时不安排别的服务器（mihomo v1.19.31 dns/resolver.go 的 ipExchange：没有 fallback 时直接返回）。
        官方内核的实际去向仍由 tools/check_real_routes.py 核对、记进快照。"""
        m, _ = model_and_plan()
        for client in ("mihomo-profile", "mihomo-core"):
            dns = parsed(client)["dns"]
            self.assertEqual(dns["nameserver"], list(m.dns["foreign_doh"]), f"{client}：默认的 nameserver 必须是境外 DoH")
            self.assertTrue(dns["respect-rules"], f"{client}：境外 DoH 的连接要按规则走（经代理）")
            for key in ("fallback", "fallback-filter"):
                self.assertNotIn(key, dns, f"{client}：境外查询不安排 {key}")

    def test_singbox_unmatched_names_ask_only_dns_foreign(self):
        """同上，sing-box 这一边（变异 M92、M99）。没被域名规则接住的域名，路由里靠一条不带匹配条件的 resolve 动作解析，
        再按解析出的 IP 判断是不是国内；设备发来的地址以外的查询类型落到 DNS 的 final。所以：
          1. 不带匹配条件的 resolve 正好一条，用 dns-foreign；它排在国内 / 国外域名集合之后、国内 IP 那条之前；
          2. 局域网专用的那条 resolve（带 domain_suffix）用 dns-local——它不在这条约束里，不能要求成 dns-foreign；
          3. dns-foreign 是统一源里的境外 DoH，经“国外默认”发出（detour），DNS 的 final 也是它。"""
        m, _ = model_and_plan()
        foreign_host = m.dns["foreign_doh"][0].split("://", 1)[1].split("/", 1)[0]
        for client in ("singbox-1.14", "singbox-1.12"):
            c = parsed(client)
            rules = c["route"]["rules"]
            resolves = [(i, r) for i, r in enumerate(rules) if r.get("action") == "resolve"]
            generic = [(i, r) for i, r in resolves if set(r) == {"action", "server"}]
            self.assertEqual(len(generic), 1, f"{client}：不带匹配条件的 resolve 应该正好一条")
            i, r = generic[0]
            self.assertEqual(r["server"], "dns-foreign", f"{client}：没被域名规则接住的域名只能交给境外 DNS 解析")
            at = {x["rule_set"]: k for k, x in enumerate(rules) if "rule_set" in x and "outbound" in x}
            self.assertLess(max(at["geosite-cn"], at["geosite-geolocation-!cn"]), i, f"{client}：先按域名集合判断，接不住的才解析")
            self.assertLess(i, at["geoip-cn"], f"{client}：解析完再判断是不是国内 IP")
            self.assertEqual([x["server"] for _, x in resolves if set(x) != {"action", "server"}], [emit_singbox.LOCAL_DNS_TAG],
                             f"{client}：带匹配条件的 resolve 只有局域网那一条，用系统 DNS")
            servers = {s["tag"]: s for s in c["dns"]["servers"]}
            fs = servers["dns-foreign"]
            self.assertEqual((fs["type"], fs["server"], fs.get("detour")), ("https", foreign_host, "国外默认"),
                             f"{client}：dns-foreign 必须是境外 DoH，并且经国外默认发出")
            self.assertEqual(c["dns"]["final"], "dns-foreign", client)

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

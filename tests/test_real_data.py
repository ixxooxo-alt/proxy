"""真实上游数据下的路由与 DNS 去向（2026-10-03 GPT 审核 F01 之后加的）。

tests/test_routing.py 里的“国内域名集合”“广告集合”只是 tests/fixtures.yaml 的几条样本，看不出
“某个域名在真实的集合里”这类问题（qwen.ai 就是这样漏掉的）。这里换成 tests/data/real_sets.json：
核对用到的每个主机在真实集合里的成员关系，加上官方内核（mihomo、sing-box）对同一批主机的判断记录。
它由 tools/check_real_routes.py --write-snapshot 生成（需要官方内核和上游数据文件；数据文件的 SHA-256 记在快照里）。

三样东西互相核对，期望都是人工写的（tests/cases.yaml、统一源里排除项的 to）。cases.yaml 的 upstream_followed
一节记的是“跟随上游数据的已知行为”（上游数据是这样、决定不更正），只在这里核对，同样参加下面三项：
  1. 模拟器按真实成员关系算出的结果 = 人工期望（四个客户端的六份产物）；
  2. 模拟器的结果 = 官方内核的记录（mihomo、sing-box；Loon / Quantumult X 没有可以在电脑上跑的官方内核）；
  3. 官方内核的记录 = 人工期望。
加了新的用例或排除项、或者改了规则让某个主机的去向变了，都要重新生成快照，否则这里会失败并提示。
解析结果仍是假定的（fixtures.yaml 的 dns；没列出的按境外 IP 算）：没有命中任何域名规则的主机，真实去向取决于当时解析到的 IP。
"""
import os
import sys
import unittest

from helpers import CLIENT_FILES, ROOT, emulate, family, load_yaml, model_and_plan, parsed, route, text

sys.path.insert(0, os.path.join(ROOT, "tools"))
import real_data as rd  # noqa: E402

FIX = load_yaml("fixtures.yaml")
CASES = load_yaml("cases.yaml")
HINT = "（重新运行 tools/check_real_routes.py --write-snapshot）"
NOT_PROXIED = {"国内直连", "DIRECT", "广告拦截"}


def snapshot():
    return rd.load_snapshot()


def fx_for(client):
    return emulate.SnapshotFixtures(snapshot(), family(client), FIX["dns"])


# 产物 → 快照里哪一份官方内核的记录。sing-box 的两个版本各有一份（1.14 版配置配 1.14 内核，1.12 兼容版配 1.12 内核）：
# 2026-10-04 审核 r9 指出，以前 1.12 的模拟器结果是拿去和 1.14 的记录比的
OFFICIAL_RECORD = {"mihomo-core": "mihomo", "mihomo-profile": "mihomo", "singbox-1.14": "singbox", "singbox-1.12": "singbox112"}


def want(probe, client):
    exp = probe["expect"][family(client)]
    return "REJECT" if family(client) == "singbox" and exp == "广告拦截" else exp


def conn(probe):
    return emulate.Conn(host=probe["host"], ip=probe["ip"])


class SnapshotCoverage(unittest.TestCase):
    def setUp(self):
        self.m, self.plan = model_and_plan()
        self.snap = snapshot()

    def test_every_needed_host_and_ip_is_recorded(self):
        missing = [h for h in rd.all_hosts(self.m) if h not in self.snap["hosts"]]
        missing += [i for i in rd.all_ips(self.m) if i not in self.snap["ips"]]
        self.assertEqual(missing, [], "快照里缺这些主机 / IP 的记录" + HINT)
        for rec in self.snap["hosts"].values():
            self.assertEqual(set(rec), set(rd.FAMILIES))

    def test_data_files_are_identified(self):
        for fam in rd.FAMILIES:
            self.assertTrue(self.snap["sources"].get(fam), fam)
            for name, info in self.snap["sources"][fam].items():
                self.assertRegex(info["sha256"], r"^[0-9a-f]{64}$", name)
        self.assertGreater(self.snap["sizes"]["mihomo"]["cn"], 1000)
        self.assertGreater(self.snap["sizes"]["singbox"]["geosite-cn"], 1000)

    def test_configs_reference_exactly_the_recorded_sets(self):
        """配置里引用的远程集合就是快照里记录的那几个：换了集合而没有重新核对时，这里会失败。"""
        geosite = [ln.split(",")[1] for ln in parsed("mihomo-core")["rules"] if ln.startswith("GEOSITE,")]
        self.assertEqual(sorted(geosite), sorted(rd.MIHOMO_SETS))
        for client in ("singbox-1.14", "singbox-1.12"):
            remote = [x["tag"] for x in parsed(client)["route"]["rule_set"] if x["type"] == "remote"]
            self.assertEqual(sorted(remote), sorted(rd.SINGBOX_SETS + rd.SINGBOX_IP_SETS), client)
        for client in ("loon", "quantumultx"):
            urls = [r["url"] for r in parsed(client)["remote"]]
            self.assertEqual(sorted(urls), sorted(self.snap["sizes"][client]), client + HINT)

    def test_loon_ad_list_has_its_domain_part(self):
        """blackmatrix7 把 Loon 版的 AdvertisingLite 拆成两个文件：只订阅 .list 的话只有关键词和 IP 段，
        三万多条域名都在 _Domain.list 里（2026-10-04 以前漏订了它）。"""
        sizes = self.snap["sizes"]["loon"]
        domains = sum(v["domain"] + v["suffix"] for v in sizes.values())
        qx = sum(v["domain"] + v["suffix"] for v in self.snap["sizes"]["quantumultx"].values())
        self.assertGreater(domains, 30000)
        self.assertEqual(domains, qx, "Loon 与 Quantumult X 订阅到的域名条数应该相同（同一份上游集合的两种格式）")


class RealRoutes(unittest.TestCase):
    def setUp(self):
        self.m, self.plan = model_and_plan()
        self.snap = snapshot()
        self.probes = rd.collect_probes(self.m)

    def test_probe_list_is_substantial(self):
        self.assertGreater(len(self.probes), 240)
        self.assertGreaterEqual(sum(1 for p in self.probes if p["src"].endswith("的排除项")), 40, "统一源里写了去向的排除项")

    def test_expectations_hold_with_real_sets(self):
        """全部用例与“写了去向的排除项”，在真实集合成员关系下，四个客户端的六份产物都符合人工期望。"""
        failures = []
        for client in CLIENT_FILES:
            fx = fx_for(client)
            for p in self.probes:
                got = route(client, conn(p), fx)
                if got != want(p, client):
                    failures.append(f"[{client}] {p['host'] or p['ip']}：期望 {want(p, client)}，实际 {got}（{p['src']}）")
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))

    def test_emulator_agrees_with_recorded_official_cores(self):
        """模拟器（真实成员关系）与官方内核的记录逐个主机相同。不同 = 规则改了但没重新核对，或者模拟器的语义不对。"""
        failures = []
        for client, key in OFFICIAL_RECORD.items():
            fx = fx_for(client)
            self.assertIn(key, self.snap["official"], f"快照里没有 {client} 对应的官方内核记录" + HINT)
            rec = self.snap["official"][key]["routes"]
            for p in self.probes:
                t = p["host"] or p["ip"]
                if t not in rec:
                    failures.append(f"[{client}] {t}：官方内核的记录里没有它" + HINT)
                    continue
                got = route(client, conn(p), fx)
                if got != rec[t][1]:
                    failures.append(f"[{client}] {t}：模拟器 {got}，官方内核记录 {rec[t][1]}（{rec[t][0]}）" + HINT)
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))

    def test_recorded_official_cores_meet_expectations(self):
        failures = []
        for client, key in (("mihomo-core", "mihomo"), ("singbox-1.14", "singbox"), ("singbox-1.12", "singbox112")):
            rec = self.snap["official"][key]["routes"]
            for p in self.probes:
                t = p["host"] or p["ip"]
                if t in rec and rec[t][1] != want(p, client):
                    failures.append(f"[{key}] {t}：期望 {want(p, client)}，官方内核记录 {rec[t][1]}（{rec[t][0]}）")
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))
        for key in ("mihomo", "singbox", "singbox112"):
            self.assertTrue(self.snap["official"][key]["version"])
        self.assertIn("1.14", self.snap["official"]["singbox"]["version"])
        self.assertIn("1.12", self.snap["official"]["singbox112"]["version"])

    def test_recorded_official_runs_used_the_current_rules(self):
        """快照里记着官方内核当时跑的那份配置的“规则段 + DNS 段”的摘要。它必须等于现在生成的配置的同一个摘要：
        改了任何一条规则或 DNS 设置而没有重新跑官方内核，这里失败。这样“模拟器的结果 = 官方内核的记录”比的才是同一套规则，
        不只是碰巧被抽到的那些主机。注释、版本号、图标不算在摘要里（它们不影响交给谁）。"""
        for client, key in (("mihomo-core", "mihomo"), ("singbox-1.14", "singbox"), ("singbox-1.12", "singbox112")):
            rec = self.snap["official"][key]
            rel = CLIENT_FILES[client]
            self.assertEqual(rec["config"], rel)
            self.assertEqual(rd.routing_digest(rel, text(client)), rec["routing_sha256"], rel + " 的规则或 DNS 改过" + HINT)
        # mihomo 的两份产物规则段、DNS 段相同时，才能共用一份官方记录
        m = self.snap["official"]["mihomo"]["routing_sha256"]
        self.assertEqual(rd.routing_digest(CLIENT_FILES["mihomo-profile"], text("mihomo-profile")), m,
                         "mihomo-profile 与 mihomo-core 的规则段或 DNS 段不同，不能共用一份官方内核记录")

    def test_qwen_is_in_the_real_domestic_sets(self):
        """这条用例存在的前提：上游的国内域名集合确实收了 qwen.ai（所以必须有显式规则）。
        哪天上游不收了，这里会失败，提醒可以去掉那句“上游收了它”的说明（规则本身留着无害）。"""
        rec = self.snap["hosts"]["chat.qwen.ai"]
        self.assertIn("cn", rec["mihomo"])
        self.assertIn("geosite-cn", rec["singbox"])

    def test_followed_upstream_behaviour_is_real_and_uncorrected(self):
        """“跟随上游的已知行为”（cases.yaml 的 upstream_followed）要名副其实：
        1. 写了差异的那一端，官方内核的记录确实是那个结果，而且确实和“按需求本该去的组”不同（没有差异就不该留在这一节）；
        2. 没写差异的端，官方内核的记录就是本该去的组。
        现在只有一条：MetaCubeX 的国内域名集合里有整段 .ms，SagerNet 的没有。2026-10-04 用户决定删掉 r8 加的
        更正规则（只写进 mihomo 的 DOMAIN-SUFFIX,ms → 国外默认）、跟随上游，所以下面还核对：
        3. 这个差异确实来自上游集合（快照里 example.ms 是 mihomo 的 cn 集合的成员，不是 sing-box 的）；
        4. 统一源里没有整段 .ms 的规则。
        上游改掉以后重新生成快照，这里会失败：把 upstream_followed 里的这一条和 docs/06 里对应的已知行为一起删掉。"""
        followed = CASES["upstream_followed"]
        self.assertTrue(followed)
        official = {fam: self.snap["official"][fam]["routes"] for fam in ("mihomo", "singbox")}
        for c in followed:
            self.assertTrue(c.get("per_client") and c.get("why"), c)
            for fam, routes in official.items():
                exp = c["per_client"].get(fam, c["expect"])
                self.assertIn(c["host"], routes, HINT)
                self.assertEqual(routes[c["host"]][1], exp, f"{fam} {c['host']}（{routes[c['host']][0]}）" + HINT)
            for fam, exp in c["per_client"].items():
                self.assertNotEqual(exp, c["expect"], f"{c['host']} 在 {fam} 上没有差异，不该放在 upstream_followed")
        rec = self.snap["hosts"]["example.ms"]
        self.assertIn("cn", rec["mihomo"], "MetaCubeX 的 cn 集合里的整段 .ms")
        self.assertNotIn("geosite-cn", rec["singbox"])
        self.assertIn("ms", self.snap["oddities"]["mihomo_cn_whole_tld"])
        self.assertFalse(self.snap["oddities"]["singbox_cn_has_ms"])
        whole_ms = [s.id for s in self.m.services for r in s.rules if r.kind == "suffix" and r.value == "ms"]
        self.assertEqual(whole_ms, [], "整段 .ms 的规则已按用户 2026-10-04 的决定删掉；要加回来先改 docs/06 和 upstream_followed")


class SingboxDns(unittest.TestCase):
    """sing-box 的 DNS 去向：按产品规则走代理组的域名不交给国内 DNS。"""

    def check_cases(self, make_fx):
        failures = []
        for client in ("singbox-1.14", "singbox-1.12"):
            fx = make_fx(client)
            for c in CASES["singbox_dns"]:
                got = emulate.singbox_dns(parsed(client), c["host"], c["type"], fx)
                if got != c["expect"]:
                    failures.append(f"[{client}] {c['host']} {c['type']}：期望 {c['expect']}，实际 {got}")
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_dns_cases_with_sample_sets(self):
        self.assertGreaterEqual(len(CASES["singbox_dns"]), 20)
        self.check_cases(lambda client: emulate.Fixtures(FIX, ads_on=True))

    def test_dns_cases_with_real_sets(self):
        self.check_cases(fx_for)

    def test_dns_cases_match_recorded_official_core(self):
        failures = []
        for key in ("singbox", "singbox112"):
            rec = snapshot()["official"][key]["dns"]
            failures += [f"[{key}] {c['host']} {c['type']}：期望 {c['expect']}，官方内核记录 {rec.get(c['host'] + ' ' + c['type'])}"
                         for c in CASES["singbox_dns"] if rec.get(f"{c['host']} {c['type']}") != c["expect"]]
        self.assertFalse(failures, "\n" + "\n".join(failures) + HINT)

    def test_dial_resolution_matches_recorded_official_cores(self):
        """审核 r9 的 F02：sing-box 拨号时，局域网里的名字交给系统 DNS，公网名字照旧交给国内 DNS。
        期望在 cases.yaml 的 singbox_dial（人工写的）；这里核对官方内核两个版本的拨号记录都符合，
        并且记录里“去掉修正”的那一遍确实不符合——说明这项核对看得见它要防的错误。"""
        cases = CASES["singbox_dial"]
        self.assertGreaterEqual(len(cases), 6)
        self.assertTrue(any(c["kind"] == "node" for c in cases) and any(c["kind"] == "direct" for c in cases))
        for key in ("singbox", "singbox112"):
            rec = snapshot()["official"][key]
            self.assertIn("dial", rec, f"快照里没有 {key} 的拨号记录" + HINT)
            wrong = [(rd.dial_key(c), c["expect"], rec["dial"].get(rd.dial_key(c))) for c in cases
                     if rec["dial"].get(rd.dial_key(c)) != c["expect"]]
            self.assertEqual(wrong, [], f"{key}：（用例, 期望, 官方内核记录）" + HINT)
            lan = [rd.dial_key(c) for c in cases if c["expect"] == "dns-local"]
            self.assertTrue(lan)
            for k in lan:
                self.assertEqual(rec["dial_without_fix"].get(k), "dns-cn",
                                 f"{key} {k}：去掉修正以后应该回到默认解析器（国内 DNS），记录是 {rec['dial_without_fix'].get(k)}")

    def test_proxied_hosts_never_go_to_domestic_dns(self):
        """对每个“期望走代理组”的主机（来自全部用例和排除项）：A 查询得到假地址，其他类型交给经代理的 DNS。
        样本和真实成员关系各查一遍。"""
        m, _ = model_and_plan()
        failures = []
        checked = 0
        for client in ("singbox-1.14", "singbox-1.12"):
            for label, fx in (("样本", emulate.Fixtures(FIX, ads_on=True)), ("真实集合", fx_for(client))):
                for p in rd.collect_probes(m):
                    if not p["host"] or p["expect"]["singbox"] in NOT_PROXIED:
                        continue
                    checked += 1
                    a = emulate.singbox_dns(parsed(client), p["host"], "A", fx)
                    other = emulate.singbox_dns(parsed(client), p["host"], "HTTPS", fx)
                    if (a, other) != ("dns-fakeip", "dns-foreign"):
                        failures.append(f"[{client}，{label}] {p['host']}（→ {p['expect']['singbox']}）：A → {a}，HTTPS → {other}")
        self.assertGreater(checked, 600)
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))

    def test_dns_layers_follow_most_specific_rule(self):
        """DNS 上的产品规则和路由用同一条“更具体优先”：逐条规则取代表主机，DNS 归类要等于路由归类。"""
        from generator.model import most_specific
        m, plan = model_and_plan()
        rules = [r for r in plan.exceptions + plan.product_for("singbox") if r.kind in ("domain", "suffix")]
        fx = emulate.Fixtures({"dns": {}, "geoip": {"cn": []}, "geosite": {"cn": [r.value for r in rules]}, "ad_list": []})
        failures = []
        for client in ("singbox-1.14", "singbox-1.12"):
            for r in rules:
                for h in ([r.value] if r.kind == "domain" else [r.value, "probe-x1." + r.value]):
                    target = most_specific(rules, h).target
                    got = emulate.singbox_dns(parsed(client), h, "A", fx)
                    exp = "dns-cn" if target == "国内直连" else "dns-fakeip"
                    if got != exp:
                        failures.append(f"[{client}] {h}（规则归 {target}）：A → {got}，应为 {exp}")
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))


if __name__ == "__main__":
    unittest.main()

"""真实上游数据下的路由与 DNS 去向（2026-10-03 GPT 审核 F01 之后加的）。

tests/test_routing.py 里的“国内域名集合”“广告集合”只是 tests/fixtures.yaml 的几条样本，看不出
“某个域名在真实的集合里”这类问题（qwen.ai 就是这样漏掉的）。这里换成 tests/data/real_sets.json：
核对用到的每个主机在真实集合里的成员关系，加上官方内核（mihomo、sing-box）对同一批主机的判断记录。
它由 tools/check_real_routes.py --write-snapshot 生成（需要官方内核和上游数据文件；数据文件的 SHA-256 记在快照里）。

三样东西互相核对，期望都是人工写的（tests/cases.yaml、统一源里排除项的 to）。cases.yaml 的 upstream_followed
一节记的是“跟随上游数据的已知行为”（上游数据是这样、决定不更正），real_only 一节记的是“只在真实数据下才看得到的行为”，
都只在这里核对，同样参加下面三项：
  1. 模拟器按真实成员关系算出的结果 = 人工期望（四个客户端的六份标准版产物，加 Loon / Quantumult X 的两份严格版）；
  2. 模拟器的结果 = 官方内核的记录（mihomo、sing-box；Loon / Quantumult X 没有可以在电脑上跑的官方内核）；
  3. 官方内核的记录 = 人工期望。
加了新的用例或排除项、或者改了规则让某个主机的去向变了，都要重新生成快照，否则这里会失败并提示。
解析结果仍是假定的（fixtures.yaml 的 dns；没列出的按境外 IP 算）：没有命中任何域名规则的主机，真实去向取决于当时解析到的 IP。

2026-10-06 起快照里另有三样东西，这里也核对：
  - “国外的连接，名字不要让国内 DNS 看到”的固定核对：走代理组的域名在连接过程中没有被任何 DNS 替身收到；没被域名规则接住的
    域名只有境外 DNS 的替身收到；境外替身只收不答时结果不变（内核没有转去问国内 / 系统 DNS）；
  - 国内 DNS 与路由的逐条扫描（r12 时叫“全集一致性”）：“名字交给国内 DNS、连接却走代理组”的代表主机，每一个都属于
    cases.yaml 里列出的已知类别；
  - Loon 严格版订阅的国内域名集合（blackmatrix7 ChinaMax_Domain）的成员关系。严格版引用的自有远程规则文件不在快照里，
    模拟器直接用这次生成的内容。
"""
import copy
import json
import os
import sys
import unittest

import yaml

from helpers import (CLIENT_FILES, LOON_CLIENTS, QX_CLIENTS, ROOT, STRICT_CLIENTS, emulate, family, is_strict, load_yaml,
                     model_and_plan, parsed, route, text)

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
    exp = probe["expect"][client if is_strict(client) else family(client)]
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
        # Loon / Quantumult X：标准版和严格版合起来订阅的上游规则文件，就是快照里记了成员关系的那几个；
        # 严格版引用的自有远程规则文件不算（内容就是这次的产物，模拟器直接读）
        base = self.m.strict["publish_base"]
        for fam, clients in (("loon", LOON_CLIENTS), ("quantumultx", QX_CLIENTS)):
            urls = {r["url"] for client in clients for r in parsed(client)["remote"] if not r["url"].startswith(base)}
            self.assertEqual(sorted(urls), sorted(self.snap["sizes"][fam]), fam + HINT)
            self.assertEqual(sorted(urls), sorted(rd.upstream_remote_lists(self.m)[fam]))
        own = {r["url"] for client in STRICT_CLIENTS for r in parsed(client)["remote"] if r["url"].startswith(base)}
        self.assertEqual(own, set(emulate.OWN_LISTS), "严格版引用的自有远程规则文件都要登记给模拟器")

    def test_loon_ad_list_has_its_domain_part(self):
        """blackmatrix7 把 Loon 版的 AdvertisingLite 拆成两个文件：只订阅 .list 的话只有关键词和 IP 段，
        三万多条域名都在 _Domain.list 里（2026-10-04 以前漏订了它）。"""
        ads = {fam: [x["url"] for x in self.m.adblock["remote_lists"][fam]] for fam in ("loon", "quantumultx")}
        sizes = self.snap["sizes"]["loon"]
        domains = sum(sizes[u]["domain"] + sizes[u]["suffix"] for u in ads["loon"])
        qx = sum(self.snap["sizes"]["quantumultx"][u]["domain"] + self.snap["sizes"]["quantumultx"][u]["suffix"]
                 for u in ads["quantumultx"])
        self.assertGreater(domains, 30000)
        self.assertEqual(domains, qx, "Loon 与 Quantumult X 订阅到的域名条数应该相同（同一份上游集合的两种格式）")

    def test_loon_strict_domestic_list_is_recorded(self):
        """Loon 严格版订阅的上游国内域名集合：只有域名和后缀两类（没有关键词、IP 段、别的规则类型），规模在十万条以上。"""
        urls = [x["url"] for x in self.m.strict["domestic_lists"]["loon"] if x.get("url")]
        self.assertEqual(len(urls), 1)
        info = self.snap["sizes"]["loon"][urls[0]]
        self.assertGreater(info["domain"] + info["suffix"], 100000)
        self.assertEqual((info["keyword"], info["ip"], info["ignored"]), (0, 0, {}),
                         "这份清单里出现了域名、后缀以外的规则：关键词会误伤，IP 规则会引出解析，要先看清楚再用")
        self.assertIn("ChinaMax_Domain.list", self.snap["sources"]["loon"])
        self.assertFalse([x for x in self.m.strict["domestic_lists"]["quantumultx"] if x.get("url")],
                         "Quantumult X 严格版现在只用自有清单；要订阅上游文件得先把它记进快照")


class RealRoutes(unittest.TestCase):
    def setUp(self):
        self.m, self.plan = model_and_plan()
        self.snap = snapshot()
        self.probes = rd.collect_probes(self.m)

    def test_probe_list_is_substantial(self):
        self.assertGreater(len(self.probes), 240)
        self.assertGreaterEqual(sum(1 for p in self.probes if p["src"].endswith("的排除项")), 40, "统一源里写了去向的排除项")

    def test_expectations_hold_with_real_sets(self):
        """全部用例与“写了去向的排除项”，在真实集合成员关系下，六份标准版产物和两份严格版都符合人工期望。"""
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
        不只是碰巧被抽到的那些主机。注释、版本号、图标不算在摘要里（它们不影响交给谁）。
        这个摘要管的是路由和 DNS 去向的记录（规则把目标交给哪个组、查询交给哪个 DNS 服务器）。拨号时名字交给谁解析的记录
        不归它管——那还取决于出站自己的设置，这两段里没有；拨号记录另有摘要，见下一项（2026-10-05 审核 r10 的建议）。"""
        for client, key in (("mihomo-core", "mihomo"), ("singbox-1.14", "singbox"), ("singbox-1.12", "singbox112")):
            rec = self.snap["official"][key]
            rel = CLIENT_FILES[client]
            self.assertEqual(rec["config"], rel)
            self.assertEqual(rd.routing_digest(rel, text(client)), rec["routing_sha256"], rel + " 的规则或 DNS 改过" + HINT)
        # mihomo 的两份产物规则段、DNS 段相同时，才能共用一份官方记录
        m = self.snap["official"]["mihomo"]["routing_sha256"]
        self.assertEqual(rd.routing_digest(CLIENT_FILES["mihomo-profile"], text("mihomo-profile")), m,
                         "mihomo-profile 与 mihomo-core 的规则段或 DNS 段不同，不能共用一份官方内核记录")

    def test_recorded_dial_runs_used_the_current_dial_config(self):
        """拨号记录（节点服务器的名字、域名形式的直连目标交给谁解析）对应的也必须是现在的配置。上一项的摘要只算规则段和
        DNS 段；sing-box 拨号时的解析还取决于出站自己的设置（节点和直连出站的 domain_resolver 等），光看上一项发现不了
        “出站改了、拨号记录还是旧的”。所以这里把拨号核对用的配置重新生成一遍（生成器带着同一批核对用的节点，和核对工具
        用的是同一个函数），它的拨号摘要必须等于快照里记的。mihomo 的节点由订阅提供、生成的配置里没有，摘要算的是核对时
        原样保留的那部分（规则、DNS、嗅探和几个开关）。"""
        m, plan = model_and_plan()
        nodes = sum(c["kind"] == "node" for c in CASES["singbox_dial"])
        for key, variant in (("singbox", "1.14"), ("singbox112", "1.12")):
            base, tags = rd.singbox_dial_base(m, plan, variant, CASES["singbox_dial"])
            self.assertEqual(len(tags), nodes, variant)
            self.assertEqual(rd.dial_digest("singbox", base), self.snap["official"][key].get("dial_sha256"),
                             f"sing-box {variant} 拨号核对用的配置变了" + HINT)
        core = rd.mihomo_dial_base(text("mihomo-core"))
        self.assertEqual(rd.dial_digest("mihomo", core), self.snap["official"]["mihomo"].get("dial_sha256"),
                         "mihomo 拨号核对用的配置变了" + HINT)
        self.assertEqual(rd.mihomo_dial_base(text("mihomo-profile")), core,
                         "mihomo-profile 与 mihomo-core 在拨号核对原样保留的部分不同，不能共用一份拨号记录")

    def test_dial_digest_sees_what_the_routing_digest_cannot(self):
        """审核 r10 举的例子：把 sing-box 直连出站的解析器改成境外 DNS，规则段与 DNS 段的摘要不变。拨号摘要必须变；
        节点上的 domain_resolver 被拿掉也必须变。反过来，策略组的成员、核对用节点的端口变了不应该变（改这些不必重跑官方内核）。
        mihomo：解析节点服务器的那条策略、直连出口跟随策略的开关变了必须变；策略组（成员、图标）和端口不在里面；
        生成的配置多出一个没有归类的顶层字段（比如 hosts）时直接报错，不悄悄略过。"""
        m, plan = model_and_plan()
        rel = CLIENT_FILES["singbox-1.14"]
        base, _ = rd.singbox_dial_base(m, plan, "1.14", CASES["singbox_dial"])
        dial0, routing0 = rd.dial_digest("singbox", base), rd.routing_digest(rel, json.dumps(base))
        self.assertEqual(routing0, rd.routing_digest(rel, text("singbox-1.14")), "带不带节点，规则段与 DNS 段相同")

        def edited(edit):
            conf = copy.deepcopy(base)
            edit(conf)
            return conf

        def direct(conf):
            return next(o for o in conf["outbounds"] if o["type"] == "direct")

        foreign = edited(lambda c: direct(c).__setitem__("domain_resolver", "dns-foreign"))
        self.assertEqual(rd.routing_digest(rel, json.dumps(foreign)), routing0, "规则段与 DNS 段的摘要看不到这个改动")
        self.assertNotEqual(rd.dial_digest("singbox", foreign), dial0)
        self.assertTrue(any("domain_resolver" in o for o in base["outbounds"]), "核对用的节点里要有带 domain_resolver 的")
        stripped = edited(lambda c: [o.pop("domain_resolver", None) for o in c["outbounds"]])
        self.assertEqual(rd.routing_digest(rel, json.dumps(stripped)), routing0)
        self.assertNotEqual(rd.dial_digest("singbox", stripped), dial0)
        regrouped = edited(lambda c: next(o for o in c["outbounds"] if o["type"] == "selector")["outbounds"].reverse())
        self.assertNotEqual(regrouped, base)
        self.assertEqual(rd.dial_digest("singbox", regrouped), dial0)
        other_port, _ = rd.singbox_dial_base(m, plan, "1.14", CASES["singbox_dial"], port=45678)
        self.assertNotEqual(other_port, base)
        self.assertEqual(rd.dial_digest("singbox", other_port), dial0)

        conf = yaml.safe_load(text("mihomo-core"))

        def mihomo_digest(edit):
            c = copy.deepcopy(conf)
            edit(c)
            return rd.dial_digest("mihomo", rd.mihomo_dial_base(yaml.safe_dump(c, allow_unicode=True, sort_keys=False)))

        m0 = mihomo_digest(lambda c: None)
        self.assertEqual(m0, rd.dial_digest("mihomo", rd.mihomo_dial_base(text("mihomo-core"))))
        self.assertNotEqual(mihomo_digest(lambda c: c["dns"].pop("proxy-server-nameserver-policy")), m0)
        self.assertNotEqual(mihomo_digest(lambda c: c["dns"]["proxy-server-nameserver-policy"].pop("*")), m0)
        self.assertNotEqual(mihomo_digest(lambda c: c["dns"].pop("direct-nameserver-follow-policy")), m0)
        self.assertNotEqual(mihomo_digest(lambda c: c["rules"].pop(0)), m0)
        self.assertEqual(mihomo_digest(lambda c: [g.pop("icon", None) for g in c["proxy-groups"]]), m0)
        self.assertEqual(mihomo_digest(lambda c: c["proxy-groups"][0]["proxies"].reverse()), m0)
        self.assertEqual(mihomo_digest(lambda c: c.__setitem__("mixed-port", 1)), m0)
        with self.assertRaises(ValueError):
            mihomo_digest(lambda c: c.__setitem__("hosts", {"gateway.lan": "192.0.2.1"}))

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
        样本和真实成员关系各查一遍。
        r12–r14 有一类已知的例外（2026-10-06 逐条扫描查出来的，待决事项 15）：“要真实地址的名单”里的名字，DNS 规则把它们
        交给 dns-cn，路由却不是直连。2026-10-07 用户选了方案二，四端都把这份名单固定直连，这一类没有了：期望走代理组的主机里
        不应再有名单里的名字（有的话说明名单和路由又不一致了，这里和 docs/06 一起看）。"""
        m, _ = model_and_plan()
        names = [(r.get("suffix"), r.get("domain")) for r in m.dns["real_ip"]]

        def in_real_ip(host):
            return any((s and emulate.suffix_match(host, s)) or host == d for s, d in names)

        failures, known = [], set()
        checked = 0
        for client in ("singbox-1.14", "singbox-1.12"):
            for label, fx in (("样本", emulate.Fixtures(FIX, ads_on=True)), ("真实集合", fx_for(client))):
                for p in rd.collect_probes(m):
                    if not p["host"] or p["expect"]["singbox"] in NOT_PROXIED:
                        continue
                    checked += 1
                    a = emulate.singbox_dns(parsed(client), p["host"], "A", fx)
                    other = emulate.singbox_dns(parsed(client), p["host"], "HTTPS", fx)
                    if in_real_ip(p["host"]):
                        known.add(p["host"])
                        if (a, other) != ("dns-cn", "dns-cn"):
                            failures.append(f"[{client}，{label}] {p['host']}（要真实地址的名单）：A → {a}，HTTPS → {other}，应为 dns-cn")
                    elif (a, other) != ("dns-fakeip", "dns-foreign"):
                        failures.append(f"[{client}，{label}] {p['host']}（→ {p['expect']['singbox']}）：A → {a}，HTTPS → {other}")
        self.assertGreater(checked, 600)
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))
        self.assertEqual(sorted(known), [],
                         "期望走代理组的主机里又出现了“要真实地址的名单”里的名字：对照 cases.yaml 的 dns_route_consistency 和 docs/06")

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


class MihomoDial(unittest.TestCase):
    """mihomo 里名字交给哪一类 DNS 解析（2026-10-05 审核 r10 的 R10-F01）：人工写的期望对照快照里官方内核的记录。
    mihomo 内核有三个互不相干的解析器——设备发来的 DNS 查询、直连出口拨号、节点连接自己的服务器——各有各的设置。"""

    WITHOUT = ("node_policy", "follow_policy", "lan_policy")

    def setUp(self):
        self.rec = snapshot()["official"]["mihomo"]
        self.dial = CASES["mihomo_dial"]
        self.dns = CASES["mihomo_dns"]
        self.dial_keys = [rd.dial_key(c) for c in self.dial]
        self.dns_keys = [f"{c['host']} {c['type']}" for c in self.dns]

    def test_dial_resolution_matches_recorded_official_core(self):
        """期望在 cases.yaml 的 mihomo_dial（人工写的）：局域网里的名字交给系统 DNS，公网名字照旧交给国内 DNS。"""
        self.assertGreaterEqual(len(self.dial), 6)
        self.assertTrue(any(c["kind"] == "node" for c in self.dial) and any(c["kind"] == "direct" for c in self.dial))
        self.assertIn("dial", self.rec, "快照里没有 mihomo 的拨号记录" + HINT)
        self.assertEqual(sorted(self.rec["dial"]), sorted(self.dial_keys), "快照里的拨号记录和现在的用例不是同一批" + HINT)
        wrong = [(k, c["expect"], self.rec["dial"][k]) for k, c in zip(self.dial_keys, self.dial) if self.rec["dial"][k] != c["expect"]]
        self.assertEqual(wrong, [], "（用例, 期望, 官方内核记录）" + HINT)

    def test_dns_cases_match_recorded_official_core(self):
        """期望在 cases.yaml 的 mihomo_dns（人工写的）：局域网后缀下的名字交给系统 DNS；普通域名给假地址、不向上游查询。
        标了 limit 的是已知限制的现状，同样要和记录一致。r12–r14 有一条（不带点的名字交给了国内的公共 DNS）；2026-10-07 用户
        定了待决事项第 14 项（方案二），不带点的名字和 private 集合交给系统 DNS，现在没有标 limit 的了。"""
        self.assertGreaterEqual(sum(c["expect"] == "system" for c in self.dns), 2)
        self.assertTrue(any(c["expect"] == "fake-ip" for c in self.dns), "要有一条对照：普通域名不向上游查询")
        self.assertIn("dns", self.rec, "快照里没有 mihomo 的 DNS 去向记录" + HINT)
        self.assertEqual(sorted(self.rec["dns"]), sorted(self.dns_keys), "快照里的 DNS 去向记录和现在的用例不是同一批" + HINT)
        wrong = [(k, c["expect"], self.rec["dns"][k]) for k, c in zip(self.dns_keys, self.dns) if self.rec["dns"][k] != c["expect"]]
        self.assertEqual(wrong, [], "（用例, 期望, 官方内核记录）" + HINT)
        limits = [c for c in self.dns if c.get("limit")]
        self.assertEqual([(c["host"], c["type"], c["expect"]) for c in limits], [], "又出现了已知限制：docs/03、docs/06 要写明")
        for k, want in (("printer A", "system"), ("tplinkwifi.net A", "system"), ("time.windows.com A", "domestic")):
            self.assertEqual(self.rec["dns"][k], want, k)
        # r13 时 qwen.ai 的 TXT 查询交给国内 DNS（待决事项 16）；r14 起产品域名那一层把它交给境外 DNS（R13-F01，用户选了改）
        self.assertEqual(self.rec["dns"]["qwen.ai TXT"], "foreign")
        self.assertFalse(set(self.dns_keys) & set(self.dial_keys))

    def test_each_setting_only_governs_its_own_path(self):
        """快照里另有三组自检的记录，各从 DNS 段里去掉一样东西再跑同一批用例：
          去掉 proxy-server-nameserver-policy        → 只有“节点服务器是局域网名字”的几条变回国内 DNS；
          去掉 direct-nameserver-follow-policy       → 只有“直连目标是局域网名字”的那条变回国内 DNS；
          nameserver-policy 里交给系统 DNS 的几条改成国内 DNS（局域网后缀、不带点的名字、private 集合；2026-10-07 以前只有
          局域网后缀那一条，自检是把它删掉）→ 设备查询局域网名字、直连局域网目标变回国内 DNS，节点的不变。
        这说明核对看得见它要防的错误，也说明三处各管各的：审核 r10 指出的正是“只写了第三处，以为节点也管到了”。"""
        lan = {kind: [k for k, c in zip(self.dial_keys, self.dial) if c["kind"] == kind and c["expect"] == "system"]
               for kind in ("node", "direct")}
        lan["query"] = [k for k, c in zip(self.dns_keys, self.dns) if c["expect"] == "system"]
        for kind, keys in lan.items():
            self.assertTrue(keys, f"用例里要有期望交给系统 DNS 的 {kind}")
        moved = {"node_policy": lan["node"], "follow_policy": lan["direct"], "lan_policy": lan["query"] + lan["direct"]}
        normal = {**{k: c["expect"] for k, c in zip(self.dial_keys, self.dial)},
                  **{k: c["expect"] for k, c in zip(self.dns_keys, self.dns)}}
        for name in self.WITHOUT:
            for part in ("dial", "dns"):
                self.assertIn(f"{part}_without_{name}", self.rec, f"快照里没有 {part}_without_{name}" + HINT)
            got = {**self.rec[f"dial_without_{name}"], **self.rec[f"dns_without_{name}"]}
            self.assertEqual(sorted(got), sorted(normal), name)
            for k, want in normal.items():
                self.assertEqual(got[k], "domestic" if k in moved[name] else want, f"去掉 {name} 后的 {k}")


class StrictWithRealSets(unittest.TestCase):
    """Loon / Quantumult X 严格版在真实数据下（上游的广告集合、Loon 多订阅的国内域名集合取成员快照；自有清单用这次生成的内容）。
    路由结果符合人工期望已经由 RealRoutes.test_expectations_hold_with_real_sets 核对；这里看“不在本机解析”。"""

    def setUp(self):
        self.m, _ = model_and_plan()
        self.probes = rd.collect_probes(self.m)

    def resolved_hosts(self, client):
        fx, out = fx_for(client), []
        for p in self.probes:
            if not p["host"]:
                continue
            trace = {}
            route(client, conn(p), fx, trace=trace)
            if trace.get("resolved"):
                out.append(p["host"])
        return sorted(set(out))

    def test_strict_configs_never_resolve_for_rule_matching(self):
        for client in STRICT_CLIENTS:
            self.assertEqual(self.resolved_hosts(client), [], f"{client}：这些域名仍要先在本机解析才能判断规则")

    def test_upstream_lists_have_no_ip_rule_that_would_make_loon_strict_resolve(self):
        """Loon 严格版的前提之一：它订阅的上游规则文件里，按 IP 判断的规则都带 no-resolve。
        本地规则由写盘前的结构检查管（tests/test_strict.py）；上游文件的内容本工程管不到，由 tools/check_real_routes.py
        在读真实文件时数出来、记进快照，这里核对记录的是 0。模拟器对 Loon 的远程规则就是按“不会为它解析”算的
        （emulate._loon_like_route 的 remote_ip_resolves），所以这一项不成立时，上面那一项“不在本机解析”的结论也不能用。
        Quantumult X 没有 no-resolve 这个参数：它的严格版靠域名兜底先接住域名，不靠这一条。"""
        urls = rd.upstream_remote_lists(self.m)["loon"]
        sizes = snapshot()["sizes"]["loon"]
        self.assertEqual(sorted(urls), sorted(sizes), "Loon 订阅的上游规则文件都要在快照里" + HINT)
        self.assertEqual(len(urls), 3, "标准版的两份广告集合，加严格版多订阅的国内域名集合")
        for url in urls:
            self.assertIn("ip_resolving", sizes[url], url + HINT)
            self.assertEqual(sizes[url]["ip_resolving"], 0,
                             f"{url} 里有不带 no-resolve 的 IP 规则（{sizes[url].get('ip_resolving_examples')}）："
                             "Loon 严格版里没被域名规则接住的域名会为它在本机解析")
        self.assertGreater(sum(sizes[u]["ip"] for u in urls), 100, "广告集合里本来就有一百多条 IP 段：这项检查不是空的")

    def test_standard_configs_do_resolve_unlisted_hosts(self):
        """对照：标准版里没被域名规则接住的域名都要先解析——严格版要解决的就是这件事，这里确认用例里确实有这样的主机。"""
        for client in ("loon", "quantumultx"):
            hosts = self.resolved_hosts(client)
            self.assertGreater(len(hosts), 20, client)
            self.assertIn("never-listed-site.org", hosts)

    def test_where_strict_and_standard_differ(self):
        """真实数据下，严格版和同一个 App 的标准版去向不同的主机，只有用例里写明的那些（per_client 里给严格版单独写了期望的）。"""
        for std, strict in (("loon", "loon-strict"), ("quantumultx", "quantumultx-strict")):
            a, b = fx_for(std), fx_for(strict)
            differ = sorted({p["host"] or p["ip"] for p in self.probes if route(std, conn(p), a) != route(strict, conn(p), b)})
            declared = sorted({p["host"] or p["ip"] for p in self.probes if p["expect"][strict] != p["expect"][std]})
            self.assertEqual(differ, declared, strict)
            self.assertIn("unknown-cn.example", differ)


class RealOnlyCases(unittest.TestCase):
    def test_real_only_cases_come_from_upstream_data(self):
        """cases.yaml 的 real_only 要名副其实。现在两条是同一件事：blackmatrix7 的 AdvertisingLite 收了“要真实地址的名单”里的
        主机，domain-list-community 的广告集合没有收。r12–r14 时标准版 Loon / Quantumult X 因此拦了它们（待决事项 18）；
        2026-10-07 起四端都把名单固定直连（待决事项 15 方案二），本地规则排在远程广告集合之前，各端都是直连（期望写的就是 DIRECT）。
        这里核对“真实的广告集合里确实有它们”——上游改掉以后重新生成快照，这里会失败：把那一条连同 docs/06 的说明一起删掉。"""
        m, _ = model_and_plan()
        snap = snapshot()
        names = [(r.get("suffix"), r.get("domain")) for r in m.dns["real_ip"]]
        self.assertTrue(CASES["real_only"])
        for c in CASES["real_only"]:
            host = c["host"]
            self.assertTrue(any((s and emulate.suffix_match(host, s)) or host == d for s, d in names), f"{host} 不在要真实地址的名单里")
            rec = snap["hosts"][host]
            for fam in ("loon", "quantumultx"):
                ads = [x["url"] for x in m.adblock["remote_lists"][fam]]
                self.assertTrue(any(u in rec[fam] for u in ads), f"{fam}：真实的广告集合里已经没有 {host} 了" + HINT)
            self.assertEqual(c["expect"], "DIRECT")
            self.assertNotIn("per_client", c, "四端都固定直连，不该再有哪一端不同")
            self.assertNotIn("category-ads-all", rec["mihomo"])
            self.assertNotIn("geosite-category-ads-all", rec["singbox"])
            self.assertTrue(c.get("why"))


class DnsLeakChecks(unittest.TestCase):
    """“国外的连接，名字不要让国内 DNS 看到”的三项固定核对（2026-10-06）。期望在 cases.yaml，人工写的；
    这里对照快照里官方内核（mihomo、sing-box 两个版本）的记录。记录和期望逐条相同已经由 MihomoDial、SingboxDns 里
    的测试核对过，这里补上：三类用例都在、境外 DNS 不应答那一遍确实跑了而且结果不变。"""

    FAMILIES = (("mihomo", "mihomo", "foreign", "domestic"), ("singbox", "singbox", "dns-foreign", "dns-cn"),
                ("singbox112", "singbox", "dns-foreign", "dns-cn"))

    def test_the_three_kinds_of_cases_exist_and_hold(self):
        for key, fam, foreign, domestic in self.FAMILIES:
            cases = CASES[f"{fam}_dial"]
            rec = snapshot()["official"][key]["dial"]
            proxied = [c for c in cases if c["kind"] == "proxied"]
            unlisted = [c for c in cases if c["kind"] == "unlisted"]
            self.assertGreaterEqual(len(proxied), 3, key)
            self.assertGreaterEqual(len(unlisted), 2, key)
            for c in proxied:
                self.assertEqual(c["expect"], "none")
                self.assertEqual(rec[rd.dial_key(c)], "none", f"{key} {c['host']}：走代理组的域名被拿去解析了" + HINT)
            for c in unlisted:
                self.assertEqual(c["expect"], foreign)
                self.assertEqual(rec[rd.dial_key(c)], foreign, f"{key} {c['host']}：没被接住的域名应该只问境外 DNS" + HINT)
            for c in proxied + unlisted:
                self.assertFalse(c["host"].endswith(".example") or c["host"] == "api.anthropic.com",
                                 "这两类名字不能用：上游的 private 集合收了 example 后缀；核对环境的 hosts 文件里有 api.anthropic.com")
        # 两个内核用的是同一批名字，归类一一对应
        pair = {"none": "none", "foreign": "dns-foreign", "domestic": "dns-cn", "system": "dns-local"}
        self.assertEqual([(c["kind"], rd.dial_name(c), pair[c["expect"]]) for c in CASES["mihomo_dial"]],
                         [(c["kind"], rd.dial_name(c), c["expect"]) for c in CASES["singbox_dial"]])

    def test_silent_foreign_dns_changes_nothing(self):
        """境外 DNS 的替身只收不答、每个连接保持十几秒：收到查询的替身和正常那一遍完全相同，
        而且确实有用例问到了境外 DNS（否则这一遍什么也没证明）。"""
        for key, fam, foreign, domestic in self.FAMILIES:
            rec = snapshot()["official"][key]
            cases = rd.silent_cases(CASES[f"{fam}_dial"])
            self.assertIn("dial_foreign_silent", rec, f"快照里没有 {key} 的“境外 DNS 不应答”记录" + HINT)
            silent = rec["dial_foreign_silent"]
            self.assertEqual(sorted(silent), sorted(rd.dial_key(c) for c in cases), key + HINT)
            for c in cases:
                k = rd.dial_key(c)
                self.assertEqual(silent[k], rec["dial"][k], f"{key} {k}：境外 DNS 不应答时结果变了")
                self.assertEqual(silent[k], c["expect"], f"{key} {k}")
            self.assertGreaterEqual(sum(v == foreign for v in silent.values()), 2, key)
            self.assertIn(domestic, silent.values(), f"{key}：要有一条直连公网域名的对照")
            self.assertNotIn(domestic, [silent[rd.dial_key(c)] for c in cases if c["kind"] in rd.SILENT_KINDS])
            # 设备发来的 DNS 查询那一半
            self.assertEqual(rec["dns_foreign_silent"], rec["dns"], f"{key}：境外 DNS 不应答时，查询交给谁变了")
            self.assertGreaterEqual(sum(v == foreign for v in rec["dns_foreign_silent"].values()), 2, key)

    def test_mihomo_device_queries_for_proxied_and_unlisted_names(self):
        """mihomo 上设备发来的查询：A 直接给假地址，HTTPS 回空应答，都不向上游查询；其他类型交给境外 DNS。"""
        rec = snapshot()["official"]["mihomo"]["dns"]
        by = {f"{c['host']} {c['type']}": c for c in CASES["mihomo_dns"]}
        self.assertEqual(rec["chatgpt.com A"], "fake-ip")
        self.assertEqual(rec["api.openai.com HTTPS"], "empty")
        self.assertEqual(rec["claude.ai TXT"], "foreign")
        self.assertEqual(rec["never-listed-query.net A"], "fake-ip")
        self.assertEqual(rec["never-listed-txt.net TXT"], "foreign")
        self.assertEqual(rec["www.qq.com TXT"], "domestic")
        for k in ("chatgpt.com A", "api.openai.com HTTPS", "claude.ai TXT", "never-listed-query.net A", "never-listed-txt.net TXT"):
            self.assertNotIn("limit", by[k])


class DnsRouteConsistency(unittest.TestCase):
    """国内 DNS 与路由的逐条扫描（2026-10-06；怎么扫的见 tools/dns_route_consistency.py；r12 时叫“全集一致性”）。
    快照的 consistency 里记着：名字会交给国内 DNS 的代表主机有多少、其中路由走代理组的是哪些。
    这里核对：集合里的条目确实都扫到了；走代理组的每一个主机都属于 cases.yaml 的 dns_route_consistency 里列出的已知类别，
    判断类别用的是统一源（不是快照自己的说法）；每个已知类别都确实还有主机。"""

    def setUp(self):
        self.m, self.plan = model_and_plan()
        self.snap = snapshot()
        self.assertIn("consistency", self.snap, "快照里没有逐条扫描的记录" + HINT)
        self.cons = self.snap["consistency"]
        self.real_ip = [(r.get("suffix"), r.get("domain")) for r in self.m.dns["real_ip"]]

    def in_real_ip(self, host):
        host = host[len("probe-x1."):] if host.startswith("probe-x1.") else host
        return any((s and emulate.suffix_match(host, s)) or host == d for s, d in self.real_ip)

    def kind_of(self, fam, item):
        from generator.model import most_specific
        host, group = item["host"], item["route"]
        if fam == "singbox":
            return "real_ip" if self.in_real_ip(host) else None
        if item["via"] == "geosite:private":
            return "private"
        rule = most_specific(self.plan.exceptions + self.plan.product_for("mihomo"), host)
        if rule is not None and rule.target == group and group not in NOT_PROXIED:
            return "product_cn"
        return None

    def test_sweep_covered_the_full_sets(self):
        sizes = self.snap["sizes"]
        mi = self.cons["mihomo"]["swept"]
        # 2026-10-07 起 private 集合交给系统 DNS（待决事项 14 方案二），不再是“名字会交给国内 DNS”的集合，不扫
        self.assertEqual(mi["sets"], {"cn": sizes["mihomo"]["cn"]})
        self.assertGreater(mi["from_sets"], sizes["mihomo"]["cn"], "后缀条目除了本身还要取一个子域")
        self.assertGreater(mi["from_rules"], 500)
        for key in ("singbox", "singbox112"):
            sb = self.cons[key]["swept"]
            self.assertEqual(sb["sets"], {"geosite-cn": sizes["singbox"]["geosite-cn"]}, key)
            self.assertGreater(sb["from_sets"], sizes["singbox"]["geosite-cn"], key)
            self.assertGreater(sb["from_rules"], 500, key)
        for key, rec in self.cons.items():
            self.assertEqual(rec["to_domestic"], rec["consistent"] + len(rec["default_direct"]) + len(rec["mismatch"]), key)
            self.assertGreater(rec["consistent"], 0.99 * rec["to_domestic"], key)
            checked = len({x["host"] for x in rec["mismatch"] + rec["default_direct"]})
            self.assertGreaterEqual(rec["official_checked"], checked + 100, f"{key}：交给官方内核核对的主机太少")

    def test_every_mismatch_belongs_to_a_known_kind(self):
        known = {fam: [x["kind"] for x in items] for fam, items in CASES["dns_route_consistency"].items()}
        self.assertEqual(sorted(known), ["mihomo", "singbox"])
        for key, fam in (("mihomo", "mihomo"), ("singbox", "singbox"), ("singbox112", "singbox")):
            rec = self.cons[key]
            seen, unknown = set(), []
            for item in rec["mismatch"]:
                kind = self.kind_of(fam, item)
                if kind is None or kind not in known[fam]:
                    unknown.append(f"{item['host']} → {item['route']}（来自 {item['via']}）")
                else:
                    seen.add(kind)
            self.assertEqual(unknown, [], f"{key}：这些主机的名字会交给国内 DNS、连接却走代理组，而且不属于任何已知类别" + HINT)
            self.assertEqual(sorted(seen), sorted(known[fam]), f"{key}：cases.yaml 里列的已知类别，和实际扫出来的不是同一批")
        for fam, items in CASES["dns_route_consistency"].items():
            for x in items:
                self.assertRegex(x["why"], r"待决事项 \d+", f"{fam} {x['kind']}：每一类都要指到 docs/06 的待决事项")

    def test_default_direct_groups_are_what_they_say(self):
        """归“默认直连、可以切换”的组的主机：那个组的首选确实是 DIRECT（Apple 那几个组，2026-10-07 起还有 Bilibili 港澳台）。默认状态下它们是一致的；
        用户把组切到代理以后，这些名字就变成“国内 DNS 解析、走代理”——docs/06 里写了。"""
        defaults = CASES["defaults"]
        for key, rec in self.cons.items():
            for item in rec["default_direct"]:
                self.assertEqual(defaults.get(item["route"]), "DIRECT", f"{key} {item['host']} → {item['route']}")

    def test_singbox_and_mihomo_both_have_the_product_layer(self):
        """两个内核的 DNS 上都有“走代理组的产品域名先判断”一层：sing-box 一直在 DNS 规则里；mihomo 是 r14 在 nameserver-policy 里加的
        （2026-10-07，GPT 审核 r13 的 R13-F01，待决事项 16 用户选了改）。同一天用户又定了第 15 项（名单固定直连）、第 14 项
        （mihomo 的 private 集合交给系统 DNS），sing-box 的“要真实地址的名单”、mihomo 的 private 集合两类也没有了：
        两端“名字交给国内 DNS、连接走代理组”的代表主机都应该是 0 个。
        另外，快照里记着两端的自检：把产品域名那一层拿掉再扫，走代理组的主机会多出一大批。"""
        sb = self.cons["singbox"]
        self.assertEqual(sb["mismatch"], [])
        self.assertEqual(self.cons["singbox112"]["mismatch"], [])
        self.assertGreater(sb["without_product_dns_rules"], len(sb["mismatch"]) + 20)
        mi = self.cons["mihomo"]["mismatch"]
        kinds = [self.kind_of("mihomo", x) for x in mi]
        self.assertEqual(kinds.count("product_cn"), 0, "mihomo 上又出现了“名字交给国内 DNS、规则交给代理组”的产品域名")
        self.assertEqual(mi, [])
        # mihomo 的自检：拿掉产品域名那一层再扫，多出来的就是这一层管到的主机，它们都交给官方内核查过 TXT（都由境外 DNS 收到）
        self.assertGreater(self.cons["mihomo"]["without_product_dns_rules"], len(mi) + 50)
        self.assertEqual(self.cons["mihomo"]["product_layer_checked"], self.cons["mihomo"]["without_product_dns_rules"] - len(mi))
        self.assertNotIn("qwen.ai", {x["host"] for x in mi})
        self.assertEqual(self.snap["official"]["mihomo"]["dns"]["qwen.ai TXT"], "foreign")


class ProbeReplyParsing(unittest.TestCase):
    """核对工具怎么认“内核自己回了什么”（tools/check_real_routes.py 的 dns_exchange、reply_kind）。不需要官方内核：
    本机起一个只回一次的假 DNS 服务器，回几种构造好的应答，看每种是不是都认对。
    2026-10-07 处理 GPT 对 r12 的审核时发现：以前只读应答里的 A 记录、按“没有 A 记录”判空应答，所以 AAAA 查询拿到了地址、
    HTTPS 查询拿到了记录，也会被记成 empty——审核方第 8 条说的“AAAA 全部为空应答”这类结论，这个工具其实看不出真假（变异 M100）。"""

    FAKE_NET = None

    @classmethod
    def setUpClass(cls):
        import ipaddress
        import check_real_routes as crr  # noqa: E402（tools/ 已在 sys.path 里）
        cls.crr = crr
        cls.FAKE_NET = ipaddress.ip_network("198.18.0.0/16")

    def ask(self, qtype, answers=(), rcode=0):
        """answers：[(记录类型, 记录内容的字节)]。返回 dns_exchange 的结果。"""
        import socket
        import struct
        import threading
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        srv.settimeout(5)

        def serve():
            data, addr = srv.recvfrom(4096)
            _, _, end = self.crr._parse_question(data)
            head = data[:2] + struct.pack("!HHHHH", 0x8180 | rcode, 1, len(answers), 0, 0)
            body = b"".join(b"\xc0\x0c" + struct.pack("!HHIH", t, 1, 60, len(rd_)) + rd_ for t, rd_ in answers)
            srv.sendto(head + data[12:end] + body, addr)

        th = threading.Thread(target=serve, daemon=True)
        th.start()
        try:
            return self.crr.dns_exchange(srv.getsockname()[1], "probe.example", qtype)
        finally:
            th.join(5)
            srv.close()

    def kind(self, reply):
        return self.crr.reply_kind(reply, self.FAKE_NET)

    def test_each_kind_of_reply_is_told_apart(self):
        import ipaddress
        import socket
        q = self.crr.QTYPE
        aaaa = self.ask(q["AAAA"], [(28, ipaddress.ip_address("2001:2::5").packed)])
        self.assertEqual(aaaa, (0, ["2001:2::5"], 1), "AAAA 记录要读出来：应答里有地址，不是空应答")
        self.assertEqual(self.kind(aaaa), "answer:2001:2::5", "AAAA 查询拿到了地址，不是空应答")
        https = self.ask(q["HTTPS"], [(65, b"\x00\x01\x00")])
        self.assertEqual(https, (0, [], 1), "HTTPS 记录不是地址，但要算进记录数：它不是空应答")
        self.assertEqual(self.kind(https), "records:1", "HTTPS 查询拿到了一条记录，不是空应答")
        self.assertEqual(self.kind(self.ask(q["AAAA"])), "empty")
        self.assertEqual(self.kind(self.ask(q["HTTPS"])), "empty")
        self.assertEqual(self.kind(self.ask(q["A"], [(1, socket.inet_aton("198.18.0.7"))])), "fake-ip")
        self.assertEqual(self.kind(self.ask(q["A"], [(1, socket.inet_aton("203.0.113.5"))])), "answer:203.0.113.5")
        self.assertEqual(self.kind(self.ask(q["A"], rcode=2)), "rcode-2")
        self.assertEqual(self.kind(None), "no-reply")

    def test_names_ending_in_a_pointer_after_labels_are_read(self):
        """GPT 审核 r13 的 R13-F04：记录的名字可以是“几个标签 + 一个压缩指针”（RFC 1035 第 4.1.4 节），例如 CNAME 之后的
        cdn.example.com 写成“cdn + 指向问题区 example.com 的指针”。以前只在名字的第一个字节看指针，这种合法的应答被读错、
        记成 rcode--1（变异 M101）。读不懂的应答现在记 unparsed，不再冒充应答码。"""
        import socket
        import struct
        import threading

        def serve(build):
            srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            srv.bind(("127.0.0.1", 0))
            srv.settimeout(5)

            def run():
                data, addr = srv.recvfrom(4096)
                srv.sendto(build(data), addr)
            th = threading.Thread(target=run, daemon=True)
            th.start()
            try:
                return self.crr.dns_exchange(srv.getsockname()[1], "www.example.com", self.crr.QTYPE["A"])
            finally:
                th.join(5)
                srv.close()

        def cname_then_a(data):
            _, _, end = self.crr._parse_question(data)
            head = data[:2] + struct.pack("!HHHHH", 0x8180, 1, 2, 0, 0)
            # 问题区的 www.example.com 从偏移 12 开始，example.com 在偏移 16
            cname = b"\xc0\x0c" + struct.pack("!HHIH", 5, 1, 60, 6) + b"\x03cdn\xc0\x10"
            a = b"\x03cdn\xc0\x10" + struct.pack("!HHIH", 1, 1, 60, 4) + socket.inet_aton("192.0.2.7")
            return head + data[12:end] + cname + a

        def cut_short(data):
            _, _, end = self.crr._parse_question(data)
            return data[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + data[12:end] + b"\xc0\x0c\x00\x01"

        got = serve(cname_then_a)
        self.assertEqual(got, (0, ["192.0.2.7"], 2), "CNAME + A 的正常应答要读出地址和记录数")
        self.assertEqual(self.kind(got), "answer:192.0.2.7")
        self.assertEqual(self.kind(serve(cut_short)), "unparsed", "读不懂的应答记 unparsed，不能冒充应答码")


class OutboundResolve(unittest.TestCase):
    """出站时的解析（2026-10-07，GPT 审核 r13 的 R13-F01；用例在 cases.yaml 的 outbound_resolve，怎么跑的见
    tools/check_real_routes.py 的 mihomo_outbound_probe、singbox_outbound_probe）。走代理的组换成真的出口（连本机空端口），
    看出口自己会不会为连接再解析目标、交给谁。mihomo 转发 UDP、经 WireGuard 时都会在本机解析；r13 时 qwen.ai 这类域名
    因此被交给了国内 DNS，r14 在 nameserver-policy 里加了产品域名那一层。这里核对快照里官方内核的记录和人工期望一致、
    自检确实看得出那一层；记录对应的是不是现在的配置，由上面 dial_sha256 那两项测试管（这项核对用的就是拨号核对那份配置）。"""

    @classmethod
    def setUpClass(cls):
        cls.cases = rd.outbound_cases()
        cls.official = snapshot()["official"]

    def test_cases_cover_the_point_of_the_check(self):
        hosts = {c["host"]: c for c in self.cases}
        self.assertTrue(any(c.get("product") for c in self.cases), "要有“国内域名集合收了、规则交给代理组”的主机")
        self.assertIn("qwen.ai", hosts)
        for c in self.cases:
            self.assertTrue(c.get("why"), c["host"])
        # 要有对照：国内直连的、默认直连组的（Apple）、产品域名那一层里交给国内 DNS 的（更具体的直连规则）
        for h in ("www.qq.com", "www.apple.com", "tlu.dl.delivery.mp.microsoft.com"):
            self.assertEqual(hosts[h]["expect"]["mihomo-wireguard-tcp"], "domestic", h)

    def test_recorded_official_runs_match_the_cases(self):
        for fam, scen_prefix in (("mihomo", "mihomo-"), ("singbox", "singbox-"), ("singbox112", "singbox-")):
            rec = self.official[fam].get("outbound")
            self.assertTrue(rec, f"快照里没有 {fam} 的出站解析记录" + HINT)
            scens = [s for s in rd.OUTBOUND_SCENARIOS if s.startswith(scen_prefix)]
            self.assertEqual(sorted(rec), scens, fam + HINT)
            wrong = [(fam, s, c["host"], c["expect"][s], rec[s].get(c["host"])) for s in scens for c in self.cases
                     if rec[s].get(c["host"]) != c["expect"][s]]
            self.assertEqual(wrong, [], "（记录, 场景, 主机, 期望, 官方内核记录）" + HINT)

    def test_mihomo_never_hands_a_proxied_name_to_the_domestic_dns(self):
        """r14 的目标：名字归走代理组的主机，三种出口下都没有被交给国内 DNS（time.windows.com 在 mihomo 上也没有）。"""
        rec = self.official["mihomo"]["outbound"]
        proxied = [c["host"] for c in self.cases if c["expect"]["mihomo-socks5-tcp"] in ("none", "foreign")]
        self.assertGreaterEqual(len(proxied), 4)
        for s, got in rec.items():
            for h in proxied:
                self.assertNotEqual(got[h], "domestic", f"{s} {h}")

    def test_self_check_sees_the_product_layer(self):
        """去掉 nameserver-policy 里产品域名那一层（r13 的样子）再跑 WireGuard：只有 product 一类变回国内 DNS。"""
        rec = self.official["mihomo"]
        without, now = rec["outbound_without_product_layer"], rec["outbound"]["mihomo-wireguard-tcp"]
        moved = sorted(h for h in now if without[h] != now[h])
        self.assertEqual(moved, sorted(c["host"] for c in self.cases if c.get("product")))
        self.assertTrue(all(without[h] == "domestic" for h in moved))


if __name__ == "__main__":
    unittest.main()

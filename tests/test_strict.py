"""Loon / Quantumult X 的严格版（2026-10-06）。

标准版里，没有命中任何域名规则的域名要先在本机解析（这两端填的是国内 DNS），再按 IP 决定走哪里——连接从代理出去，
域名却被国内 DNS 看到了。严格版各多生成一份配置：国内网站靠国内域名清单认出来、直连；其余域名不在本机解析，
直接交给“国外默认”；原本就是 IP 的连接照旧按 IP 规则判断。

这里检查的是生成出来的文本和按官方文档写的模拟器，不是这两个 App 的实测——两处关键写法在真机上是否如文档所说，
列在 docs/09 的验收步骤里：
  Loon：单独一行的 GEOIP,CN,策略,no-resolve（官方只在逻辑规则的例子里把 no-resolve 写在 GEOIP 上）；
  Quantumult X：远程规则之间按书写顺序、本地规则先于远程规则、域名类规则先于 IP 类规则（官方 sample.conf 没有完整写明）。
"""
import copy
import os
import re
import unittest

from helpers import (CLIENT_FILES, LOON_CLIENTS, QX_CLIENTS, ROOT, STRICT_CLIENTS, STRICT_OF, build, emulate, expected,
                     family, load_yaml, model_and_plan, outputs, parsed, route, text)

from generator import strict as strict_mod
from generator import verify
from generator.model import most_specific

CASES = load_yaml("cases.yaml")
FIX = load_yaml("fixtures.yaml")
EMPTY = {"dns": {}, "geoip": {"cn": []}, "geosite": {}, "ad_list": [], "cn_list": []}
REAL_IP_NAMES = ["localhost.ptlogin2.qq.com", "pool.ntp.org", "0.pool.ntp.org", "time.apple.com", "time.windows.com",
                 "cmpassport.com", "wap.cmpassport.com", "jegotrip.com.cn", "icitymobile.mobi", "id6.me"]


def sections(client):
    return parsed(client)["sections"]


def own_url(rel):
    return model_and_plan()[0].strict["publish_base"] + rel


def own_rules(rel):
    """自有远程规则文件里的规则行（去掉注释）。"""
    return [ln for ln in outputs()[rel].splitlines() if ln.strip() and not ln.startswith("#")]


class StrictOutputs(unittest.TestCase):
    def test_twelve_public_outputs(self):
        files = outputs()
        want = set(CLIENT_FILES.values()) | set(strict_mod.OWN_FILES) | {"manifest.json"}
        self.assertEqual(set(files), want)
        self.assertEqual(len(files), 12)

    def test_standard_configs_do_not_use_any_strict_part(self):
        """标准版不引用自有远程规则文件、不订阅国内域名集合；Loon 标准版的 GEOIP,CN 仍然会解析（没有 no-resolve）。"""
        base = model_and_plan()[0].strict["publish_base"]
        for client in ("loon", "quantumultx", "mihomo-profile", "mihomo-core", "singbox-1.14", "singbox-1.12"):
            self.assertNotIn(base, text(client), client)
            self.assertNotIn("ChinaMax", text(client), client)
            self.assertNotIn("严格版", text(client), client)
        self.assertIn(["GEOIP", "CN", "国内直连"], parsed("loon")["local"])
        for client in ("loon", "quantumultx"):
            self.assertFalse([r for r in parsed(client)["remote"] if r["policy"] == "国内直连"], client)

    def test_strict_differs_from_standard_only_where_intended(self):
        """严格版和同一个 App 的标准版相比：策略组、节点订阅、DNS、其余设置逐行相同；规则部分只多不少。"""
        for std, strict in STRICT_OF.items():
            a, b = sections(std), sections(strict)
            self.assertEqual(list(a), list(b), f"{strict} 的段落和标准版不一样")
            rule_sec = {"loon": ("Rule", "Remote Rule"), "quantumultx": ("filter_local", "filter_remote")}[std]
            for name in a:
                if name not in rule_sec:
                    self.assertEqual(a[name], b[name], f"{strict} 的 [{name}] 和标准版不一样")
            # 远程规则：标准版的几条原样在最前面，后面是严格版加的
            self.assertEqual(b[rule_sec[1]][:len(a[rule_sec[1]])], a[rule_sec[1]], strict)
            self.assertGreater(len(b[rule_sec[1]]), len(a[rule_sec[1]]), strict)
            # 本地规则：标准版的每一条都还在，顺序不变（Loon 的 IP 规则多了 no-resolve，比较时去掉它）
            norm = lambda ln: re.sub(r",\s*no-resolve$", "", ln)             # noqa: E731
            std_rules = [norm(x) for x in a[rule_sec[0]]]
            strict_rules = [norm(x) for x in b[rule_sec[0]]]
            it = iter(strict_rules)
            self.assertTrue(all(x in it for x in std_rules), f"{strict} 的本地规则少了标准版里的某一条，或者顺序变了")
            added = len(strict_rules) - len(std_rules)
            self.assertEqual(added, len(model_and_plan()[1].real_ip_direct), f"{strict} 多出来的本地规则应该只有“要真实地址的名单”那几条")

    def test_manifest_records_the_strict_outputs(self):
        import json
        m, plan = model_and_plan()
        man = json.loads(outputs()["manifest.json"])
        listed = man["outputs"] if isinstance(man.get("outputs"), dict) else {x["path"]: x for x in man["outputs"]}
        for rel in list(CLIENT_FILES.values()) + list(strict_mod.OWN_FILES):
            self.assertIn(rel, listed, "manifest.json 里没有登记 " + rel)
        self.assertEqual(man["rule_counts"]["strict_real_ip_direct"], len(plan.real_ip_direct))
        self.assertEqual(man["rule_counts"]["strict_cn_domains"],
                         {"loon": len(own_rules(strict_mod.LOON_CN_REL)), "quantumultx": len(own_rules(strict_mod.QX_CN_REL))},
                         "manifest 里记的是两份自有清单各自实际写出的条数")


class LoonStrict(unittest.TestCase):
    def setUp(self):
        self.conf = parsed("loon-strict")

    def test_every_ip_rule_carries_no_resolve(self):
        ip_rules = [p for p in self.conf["local"] if p[0] in ("IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN")]
        self.assertGreater(len(ip_rules), 20)
        for p in ip_rules:
            self.assertIn("no-resolve", p[3:], ",".join(p))
        self.assertIn(["GEOIP", "CN", "国内直连", "no-resolve"], self.conf["local"])
        self.assertEqual(self.conf["final"], "国外默认")
        # 对照：标准版的 GEOIP,CN 没有 no-resolve（它就是靠解析来认国内网站的）
        self.assertIn(["GEOIP", "CN", "国内直连"], parsed("loon")["local"])

    def test_remote_rules_order(self):
        """订阅规则按书写顺序匹配：广告集合 → blackmatrix7 的国内域名集合 → 自有清单（含整段 .cn）。"""
        m, _ = model_and_plan()
        remote = self.conf["remote"]
        ads = [x["url"] for x in m.adblock["remote_lists"]["loon"]]
        self.assertEqual([r["url"] for r in remote[:len(ads)]], ads)
        self.assertEqual([r["policy"] for r in remote[:len(ads)]], ["广告拦截"] * len(ads))
        rest = remote[len(ads):]
        self.assertEqual(len(rest), 2)
        self.assertRegex(rest[0]["url"], r"^https://raw\.githubusercontent\.com/blackmatrix7/ios_rule_script/master/rule/Loon/ChinaMax/ChinaMax_Domain\.list$")
        self.assertEqual(rest[1]["url"], own_url(strict_mod.LOON_CN_REL))
        self.assertEqual([r["policy"] for r in rest], ["国内直连", "国内直连"])
        self.assertTrue(all(r["enabled"] == "true" for r in remote))

    def test_real_ip_names_are_fixed_direct_before_product_rules(self):
        _, plan = model_and_plan()
        local = self.conf["local"]
        want = [["DOMAIN" if r.kind == "domain" else "DOMAIN-SUFFIX", r.value, "DIRECT"] for r in plan.real_ip_direct]
        self.assertEqual(len(want), 8)
        idx = [local.index(x) for x in want]
        self.assertEqual(idx, sorted(idx))
        first_product = next(i for i, p in enumerate(local) if p[2] not in ("DIRECT", "广告拦截", "REJECT") and p[0].startswith("DOMAIN"))
        self.assertLess(max(idx), first_product, "“要真实地址的名单”要排在产品规则之前（time.apple.com 不能被 apple.com 先接住）")


class QuantumultXStrict(unittest.TestCase):
    def setUp(self):
        self.conf = parsed("quantumultx-strict")

    def test_fallback_is_the_last_remote_resource(self):
        m, _ = model_and_plan()
        remote = self.conf["remote"]
        ads = [x["url"] for x in m.adblock["remote_lists"]["quantumultx"]]
        self.assertEqual([r["url"] for r in remote], ads + [own_url(strict_mod.QX_CN_REL), own_url(strict_mod.QX_FALLBACK_REL)])
        self.assertEqual([r["policy"] for r in remote], ["广告拦截"] * len(ads) + ["国内直连", "国外默认"])
        self.assertTrue(all(r["enabled"].strip() == "true" for r in remote))
        for line in sections("quantumultx-strict")["filter_remote"]:
            self.assertNotIn("inserted-resource", line)
            self.assertIn("opt-parser=false", line)

    def test_fallback_file_is_the_single_documented_rule(self):
        """官方 sample.conf 给的写法是 host-keyword, ., proxy；文件里只有这一条，真正的去向由配置里的 force-policy 决定。"""
        self.assertEqual(own_rules(strict_mod.QX_FALLBACK_REL), ["HOST-KEYWORD,.,proxy"])
        self.assertIn("skip the DNS query for all the non-matched hosts", outputs()[strict_mod.QX_FALLBACK_REL])

    def test_ip_rules_are_all_kept(self):
        """Quantumult X 没有 no-resolve，也不需要拿掉 IP 规则：域名兜底先于 IP 类规则接住全部域名，IP 规则只剩原本就是 IP 的连接。"""
        ip = lambda c: [p for p in parsed(c)["local"] if p[0] in ("ip-cidr", "ip6-cidr", "geoip")]      # noqa: E731
        self.assertEqual(ip("quantumultx-strict"), ip("quantumultx"))
        self.assertGreater(len(ip("quantumultx-strict")), 20)
        self.assertIn(["geoip", "cn", "国内直连"], self.conf["local"])
        self.assertEqual(self.conf["final"], "国外默认")

    def test_real_ip_names_are_fixed_direct(self):
        _, plan = model_and_plan()
        want = [["host" if r.kind == "domain" else "host-suffix", r.value, "direct"] for r in plan.real_ip_direct]
        for x in want:
            self.assertIn(x, self.conf["local"])


class StrictBehaviour(unittest.TestCase):
    """用模拟器看行为。样本数据：tests/fixtures.yaml；自有清单用的是这次生成的真实内容。"""

    def test_no_domain_is_resolved_locally_for_rule_matching(self):
        """全部用例里的域名，在两份严格版上都不需要“为了判断 IP 规则而在本机解析”；标准版上有一批需要（对照）。"""
        fx = emulate.Fixtures(FIX)
        hosts = sorted({c["host"] for c in CASES["cases"] if c.get("host")})
        self.assertGreater(len(hosts), 200)
        for client in STRICT_CLIENTS:
            resolved = []
            for h in hosts:
                trace = {}
                route(client, emulate.Conn(host=h), fx, trace=trace)
                if trace.get("resolved"):
                    resolved.append(h)
            self.assertEqual(resolved, [], client)
        for client in ("loon", "quantumultx"):
            resolved = []
            for h in hosts:
                trace = {}
                route(client, emulate.Conn(host=h), fx, trace=trace)
                if trace.get("resolved"):
                    resolved.append(h)
            self.assertGreater(len(resolved), 20, f"{client}：标准版里没被域名规则接住的域名应该要先解析（严格版要解决的就是这个）")
            self.assertIn("never-listed-site.org", resolved)

    def test_unlisted_domain_goes_to_foreign_default_even_if_it_resolves_to_china(self):
        fx = emulate.Fixtures(FIX)
        self.assertEqual(FIX["dns"]["unknown-cn.example"], "1.2.4.8")
        for std, strict in STRICT_OF.items():
            self.assertEqual(route(std, emulate.Conn(host="unknown-cn.example"), fx), "国内直连")
            self.assertEqual(route(strict, emulate.Conn(host="unknown-cn.example"), fx), "国外默认")
            # 原本就是 IP 的连接不受影响：国内 IP 仍然直连，局域网、服务专属 IP 也照旧
            for ip, want in (("1.2.4.8", "国内直连"), ("240e::1", "国内直连"), ("192.168.1.1", "DIRECT"),
                             ("149.154.167.51", "Telegram"), ("8.8.8.8", "国外默认")):
                self.assertEqual(route(strict, emulate.Conn(ip=ip), fx), want, f"{strict} {ip}")

    def test_real_ip_names_route_direct(self):
        fx = emulate.Fixtures(FIX)
        for client in STRICT_CLIENTS:
            for h in REAL_IP_NAMES:
                trace = {}
                self.assertEqual(route(client, emulate.Conn(host=h), fx, trace=trace), "DIRECT", f"{client} {h}")
                self.assertFalse(trace.get("resolved"))

    def test_domestic_lists_cover_the_supplementary_rules_other_clients_get(self):
        """mihomo / sing-box 另有一批只写给它们的国内补充规则（source/services/misc.yaml 的 cn_common）。
        严格版不写这些本地规则（会挡住远程广告集合），靠自有清单接住：每一条的域名本身和它的一个子域都要落到国内直连。
        这里不用任何样本集合，只有这次生成的自有清单。"""
        m, _ = model_and_plan()
        fx = emulate.Fixtures(EMPTY)
        rules = [r for s in m.services if s.id == "cn_common" for r in s.rules]
        self.assertGreater(len(rules), 60)
        for client in STRICT_CLIENTS:
            bad = []
            for r in rules:
                for h in ([r.value] if r.kind == "domain" else [r.value, "probe-x1." + r.value]):
                    got = route(client, emulate.Conn(host=h), fx)
                    if got != "国内直连":
                        bad.append(f"{h} → {got}")
            self.assertEqual(bad, [], client)

    def test_ads_still_win_over_the_domestic_lists(self):
        """广告集合排在国内域名清单之前：清单里的域名下的广告主机仍然被拦（样本里的 ad.12306.cn，整段 .cn 在自有清单里）。"""
        fx = emulate.Fixtures(FIX)
        for client in STRICT_CLIENTS:
            self.assertEqual(route(client, emulate.Conn(host="ad.12306.cn"), fx), "广告拦截", client)
            self.assertEqual(route(client, emulate.Conn(host="www.12306.cn"), fx), "国内直连", client)

    def test_local_product_rules_win_over_the_domestic_lists(self):
        """本地规则先于远程规则：上游的国内域名集合收了 qwen.ai（样本里也放了），仍由本地的显式规则交给国外默认。
        自有清单里干脆不写已被本地规则覆盖的条目，结果不依赖两类规则谁先谁后。"""
        fx = emulate.Fixtures(FIX)
        self.assertIn(["suffix", "qwen.ai"], FIX["cn_list"])
        for client in STRICT_CLIENTS:
            self.assertEqual(route(client, emulate.Conn(host="chat.qwen.ai"), fx), "国外默认", client)
        for rel in (strict_mod.LOON_CN_REL, strict_mod.QX_CN_REL):
            self.assertFalse([ln for ln in own_rules(rel) if ",qwen.ai" in ln or ",qwenlm.ai" in ln], rel)

    def test_loon_also_uses_the_larger_upstream_list(self):
        """Loon 严格版多订阅一份上游的大清单（blackmatrix7 ChinaMax_Domain）；Quantumult X 没有只含域名的上游成品，只有自有清单。
        只在大清单里的域名：Loon 严格版直连，Quantumult X 严格版走国外默认（已知差异，docs/06）。"""
        fx = emulate.Fixtures(FIX)
        host = "www.only-in-chinamax-sample.com"
        self.assertEqual(route("loon-strict", emulate.Conn(host=host), fx), "国内直连")
        self.assertEqual(route("quantumultx-strict", emulate.Conn(host=host), fx), "国外默认")

    def test_quantumultx_known_gaps_are_as_documented(self):
        """docs/06 写的两处限制，在模拟器里确实如此：
        1. 不带点的主机名不会被域名兜底（关键词是“.”）接住，仍要解析后按 IP 判断；
        2. 域名兜底是远程资源：它没有加载时（这里用“没启用”模拟），保护静默消失，行为退回标准版。"""
        fx = emulate.Fixtures({**EMPTY, "dns": {"printer": "1.2.4.8", "unknown-cn.example": "1.2.4.8"}, "geoip": {"cn": ["1.2.4.0/24"]}})
        trace = {}
        self.assertEqual(route("quantumultx-strict", emulate.Conn(host="printer"), fx, trace=trace), "国内直连")
        self.assertTrue(trace.get("resolved"))
        conf = copy.deepcopy(parsed("quantumultx-strict"))
        self.assertTrue(conf["remote"][-1]["url"].endswith(strict_mod.QX_FALLBACK_REL))
        conf["remote"][-1]["enabled"] = "false"
        trace = {}
        self.assertEqual(emulate.qx_route(conf, emulate.Conn(host="unknown-cn.example"), fx, trace=trace), "国内直连")
        self.assertTrue(trace.get("resolved"), "兜底没有加载时，没被接住的域名又回到“先在本机解析”")

    def test_strict_follows_standard_wherever_no_override_is_written(self):
        """用例里没有专门给严格版写期望的，严格版的结果和同一个 App 的标准版相同（样本数据）。
        也就是说：严格版改变去向的，只有 cases.yaml 里写明的那几类。"""
        fx = emulate.Fixtures(FIX)
        for std, strict in STRICT_OF.items():
            diff = []
            for c in CASES["cases"]:
                conn = emulate.Conn(host=c.get("host"), ip=c.get("ip"))
                a, b = route(std, conn, fx), route(strict, conn, fx)
                declared = strict in (c.get("per_client") or {})
                if (a != b) != (declared and expected(c, strict) != expected(c, std)):
                    diff.append(f"{c.get('host') or c.get('ip')}：标准版 {a}，严格版 {b}，用例里{'写了' if declared else '没写'}严格版的期望")
            self.assertEqual(diff, [], strict)


class OwnLists(unittest.TestCase):
    def test_data_file_header_matches_its_content(self):
        m, _ = model_and_plan()
        suffix, full = m.cn_domains
        with open(os.path.join(ROOT, *strict_mod.CN_DATA_REL.split("/")), encoding="utf-8") as f:
            head = [ln for ln in f.read().splitlines() if ln.startswith("#")]
        counts = re.search(r"剩下后缀 (\d+) 条、精确域名 (\d+) 条", "\n".join(head))
        self.assertEqual((int(counts.group(1)), int(counts.group(2))), (len(suffix), len(full)))
        self.assertGreater(len(suffix), 5000)
        self.assertTrue(any("MIT" in ln for ln in head))
        self.assertTrue(any(re.search(r"固定快照 [0-9a-f]{40}", ln) for ln in head))
        self.assertIn(m.evidence["dlc"]["snapshot"], "\n".join(head), "数据文件头里的快照提交要和 source/evidence.yaml 登记的一致")
        self.assertTrue(os.path.exists(os.path.join(ROOT, "source", "data", "LICENSE-domain-list-community.txt")))
        self.assertIn("cn", suffix, "整段 .cn 在自有清单里")

    def test_data_file_has_no_redundant_or_malformed_entries(self):
        from generator.util import valid_domain
        suffix, full = model_and_plan()[0].cn_domains
        self.assertEqual(len(set(suffix)), len(suffix))
        self.assertEqual(len(set(full)), len(full))
        sset = set(suffix)
        for d in suffix + full:
            self.assertTrue(valid_domain(d), d)
            self.assertEqual(d, d.lower())
        for s in suffix:
            parts = s.split(".")
            self.assertFalse(any(".".join(parts[i:]) in sset for i in range(1, len(parts))), f"{s} 已被清单里别的后缀覆盖")
        for d in full:
            parts = d.split(".")
            self.assertFalse(any(".".join(parts[i:]) in sset for i in range(len(parts))), f"{d} 已被清单里的后缀覆盖")

    def test_generated_lists_are_the_data_minus_locally_covered_entries(self):
        m, plan = model_and_plan()
        suffix, full = m.cn_domains
        for fam, rel, sfx_t, full_t, tail in (("loon", strict_mod.LOON_CN_REL, "DOMAIN-SUFFIX", "DOMAIN", ""),
                                              ("quantumultx", strict_mod.QX_CN_REL, "HOST-SUFFIX", "HOST", ",direct")):
            lines = own_rules(rel)
            kept_s, kept_f, dropped = strict_mod.cn_entries(m, plan, fam)
            self.assertEqual(lines, [f"{sfx_t},{x}{tail}" for x in kept_s] + [f"{full_t},{x}{tail}" for x in kept_f], rel)
            self.assertEqual(dropped, len(suffix) + len(full) - len(lines))
            self.assertGreater(dropped, 0)
            self.assertLess(dropped, 60, "被本地规则覆盖而去掉的应该只是少数")
            # 去掉的每一条，确实已经被这一端的本地规则接住（去向由本地规则决定）
            local = [r for r in plan.lan + plan.real_ip_direct + plan.exceptions + plan.ads_local + plan.product_for(fam)
                     if r.kind in ("domain", "suffix")]
            gone = (set(suffix) - set(kept_s)) | (set(full) - set(kept_f))
            for d in gone:
                self.assertIsNotNone(most_specific(local, d), f"{d} 被去掉了，但没有本地规则接住它")
            self.assertIn("qwen.ai", gone)
            self.assertIn(f"共 {len(lines)} 条", outputs()[rel])

    def test_list_headers_carry_source_and_license(self):
        for rel in (strict_mod.LOON_CN_REL, strict_mod.QX_CN_REL):
            head = [ln for ln in outputs()[rel].splitlines() if ln.startswith("#")]
            joined = "\n".join(head)
            self.assertIn("v2fly/domain-list-community", joined, rel)
            self.assertIn("MIT", joined, rel)
            self.assertIn("LICENSE-domain-list-community.txt", joined, rel)
            self.assertNotIn("统一源版本", joined, "清单文件里不写版本号：数据没变时文件就不变")


class StrictVerifier(unittest.TestCase):
    """写盘前的结构检查要拦得住严格版赖以成立的那几处被改坏。"""

    def own(self):
        m, _ = model_and_plan()
        return verify.own_files(m, outputs())

    def test_generated_outputs_pass(self):
        self.assertEqual(verify.check_outputs(outputs(), own=self.own()), [])

    def test_loon_breakages_are_caught(self):
        t = text("loon-strict")
        own = self.own()
        self.assertEqual(verify.check_loon(t, strict=True, own=own), [])
        broken = t.replace("GEOIP,CN,国内直连,no-resolve", "GEOIP,CN,国内直连")
        self.assertNotEqual(broken, t)
        self.assertTrue(any("no-resolve" in p for p in verify.check_loon(broken, strict=True, own=own)))
        cn_lines = [ln for ln in t.splitlines() if "policy=国内直连" in ln]
        self.assertEqual(len(cn_lines), 2)
        without = "\n".join(ln for ln in t.splitlines() if ln not in cn_lines)
        self.assertTrue(any("没有交给“国内直连”的国内域名清单" in p for p in verify.check_loon(without, strict=True, own=own)))
        ad_line = next(ln for ln in t.splitlines() if "policy=广告拦截" in ln)
        moved = without.replace(ad_line, cn_lines[0] + "\n" + cn_lines[1] + "\n" + ad_line)
        self.assertTrue(any("排在了广告集合前面" in p for p in verify.check_loon(moved, strict=True, own=own)))
        off = t.replace(cn_lines[1], cn_lines[1].replace("enabled=true", "enabled=false"))
        self.assertTrue(any("没有启用" in p for p in verify.check_loon(off, strict=True, own=own)))
        renamed = t.replace(strict_mod.LOON_CN_REL, "loon/rules/renamed.list")
        self.assertTrue(any("产物里没有这个文件" in p for p in verify.check_loon(renamed, strict=True, own=own)))
        # 标准版不受这些要求约束
        self.assertEqual(verify.check_loon(text("loon"), strict=False, own=own), [])
        self.assertTrue(verify.check_loon(text("loon"), strict=True, own=own), "把标准版当严格版检查，应该不合格")

    def test_quantumultx_breakages_are_caught(self):
        t = text("quantumultx-strict")
        own = self.own()
        self.assertEqual(verify.check_qx(t, strict=True, own=own), [])
        lines = t.splitlines()
        fb = next(ln for ln in lines if strict_mod.QX_FALLBACK_REL in ln)
        cn = next(ln for ln in lines if strict_mod.QX_CN_REL in ln)
        without = "\n".join(ln for ln in lines if ln != fb)
        self.assertTrue(any("最后一条不是域名兜底" in p for p in verify.check_qx(without, strict=True, own=own)))
        swapped = t.replace(cn, "@@").replace(fb, cn).replace("@@", fb)
        probs = verify.check_qx(swapped, strict=True, own=own)
        self.assertTrue(any("最后一条不是域名兜底" in p or "不是最后一条" in p for p in probs), probs)
        wrong = t.replace(fb, fb.replace("force-policy=国外默认", "force-policy=国内直连"))
        self.assertTrue(any("应该是“国外默认”" in p for p in verify.check_qx(wrong, strict=True, own=own)))
        inserted = t.replace(cn, cn + ", inserted-resource=true")
        self.assertTrue(any("inserted-resource" in p for p in verify.check_qx(inserted, strict=True, own=own)))
        self.assertEqual(verify.check_qx(text("quantumultx"), strict=False, own=own), [])
        self.assertTrue(verify.check_qx(text("quantumultx"), strict=True, own=own), "把标准版当严格版检查，应该不合格")

    def test_own_list_content_breakages_are_caught(self):
        files = dict(outputs())
        self.assertEqual(verify.check_own_lists(files), [])
        bad = dict(files)
        bad[strict_mod.QX_FALLBACK_REL] = files[strict_mod.QX_FALLBACK_REL].replace("HOST-KEYWORD,.,proxy", "HOST-KEYWORD,com,proxy")
        self.assertTrue(verify.check_own_lists(bad))
        bad = dict(files)
        bad[strict_mod.QX_FALLBACK_REL] = files[strict_mod.QX_FALLBACK_REL] + "HOST-SUFFIX,example.org,proxy\n"
        self.assertTrue(verify.check_own_lists(bad))
        bad = dict(files)
        bad[strict_mod.LOON_CN_REL] = files[strict_mod.LOON_CN_REL] + "DOMAIN-KEYWORD,baidu\n"
        self.assertTrue(any("不是“域名 / 后缀”规则" in p for p in verify.check_own_lists(bad)))
        bad = dict(files)
        bad[strict_mod.QX_CN_REL] = files[strict_mod.QX_CN_REL].replace(",direct\n", ",proxy\n", 1)
        self.assertTrue(any("策略名" in p for p in verify.check_own_lists(bad)))
        bad = dict(files)
        bad[strict_mod.LOON_CN_REL] = "\n".join(files[strict_mod.LOON_CN_REL].splitlines()[:50]) + "\n"
        self.assertTrue(any("不像一份完整的国内域名清单" in p for p in verify.check_own_lists(bad)))

    def test_build_refuses_to_write_a_broken_strict_config(self):
        """生成流程里，严格版的结构检查不合格时整个生成失败（不会留下一份“看起来是严格版、其实会解析”的文件）。"""
        m, plan = model_and_plan()
        files = build.render_public(m, plan)
        files["loon/loon-strict.conf"] = files["loon/loon-strict.conf"].replace("GEOIP,CN,国内直连,no-resolve", "GEOIP,CN,国内直连")
        self.assertTrue(verify.check_outputs(files, own=verify.own_files(m, files)))


class StrictFamilies(unittest.TestCase):
    def test_family_and_expectation_lookup(self):
        self.assertEqual([family(c) for c in LOON_CLIENTS + QX_CLIENTS], ["loon", "loon", "quantumultx", "quantumultx"])
        case = {"expect": "甲", "per_client": {"loon": "乙", "loon-strict": "丙"}}
        self.assertEqual(expected(case, "loon"), "乙")
        self.assertEqual(expected(case, "loon-strict"), "丙")
        self.assertEqual(expected(case, "quantumultx-strict"), "甲")
        self.assertEqual(expected({"expect": "甲", "per_client": {"quantumultx": "乙"}}, "quantumultx-strict"), "乙",
                         "没给严格版单独写期望时，跟同一个 App 的标准版")
        self.assertEqual(expected({"expect": "甲"}, "mihomo-core"), "甲")


if __name__ == "__main__":
    unittest.main()

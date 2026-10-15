"""Stash 的两份产物（2026-10-13，r16）：stash.yaml（标准版）、stash-strict.yaml（严格版）。

Stash 没有能在电脑上运行的内核。这里查的是生成出来的文本有没有按设计写、写法是不是都在下载的官方文档里，
和 mihomo 那份应该一样的地方是不是真的一样；按规则走到哪里由 test_routing.py / test_real_data.py 的模拟器查，
严格版“不在本机解析”由 test_strict.py 的行为测试查（它们都把 Stash 算进去了）。真机上的事在 docs/09。
设计和依据见 generator/emit_stash.py 的说明。
"""
import copy
import re
import unittest

import yaml

from helpers import STASH_CLIENTS, load_yaml, model_and_plan, outputs, parsed, text

from generator import emit_stash, verify

NODE_NAMES = load_yaml("node_names.yaml")


def conf(client):
    return copy.deepcopy(parsed(client))


class StashStructure(unittest.TestCase):
    def test_generated_outputs_pass_the_structure_check(self):
        for client in STASH_CLIENTS:
            self.assertEqual(verify.check_stash(text(client), strict=client == "stash-strict"), [], client)

    def test_standard_rules_are_the_mihomo_rules(self):
        """标准版的规则和 mihomo 的逐条相同（同一份产品规则、同样的 GEOSITE 和 GEOIP 写法；顺序也一样）。
        Stash 的规则按书写顺序匹配（文档“规则类型”），和 mihomo 一样，所以不需要像 Loon / Quantumult X 那样另排。"""
        self.assertEqual(conf("stash")["rules"], conf("mihomo-core")["rules"])

    def test_groups_are_the_mihomo_groups(self):
        """组名、类型、成员、筛选正则、图标和 mihomo 的相同；只差写法：Stash 用 include-all（文档的例子），没有 hidden（10-13 的文档快照没写；审核方说现行页面有，没有核实、没有用）、
        empty-fallback、组上的检测地址（Stash 按节点测，地址写在订阅和占位节点上）。
        筛选正则 r17 起只在开头多一段，排除 Stash 的内置策略名（见 StashBuiltinPolicies）。"""
        st = {g["name"]: g for g in conf("stash")["proxy-groups"]}
        mh = {g["name"]: g for g in conf("mihomo-core")["proxy-groups"]}
        self.assertEqual(list(st), list(mh))
        for name, g in st.items():
            h = mh[name]
            self.assertEqual(g["type"], h["type"], name)
            self.assertEqual(g.get("proxies"), h.get("proxies"), name)
            self.assertEqual(g.get("filter"), emit_stash.exclude_builtins(h["filter"]) if "filter" in h else None, name)
            self.assertEqual(g.get("icon"), h.get("icon"), name)
            self.assertEqual(bool(g.get("include-all")), "filter" in h, name)
            for key in ("hidden", "empty-fallback", "url", "include-all-providers", "use"):
                self.assertNotIn(key, g, f"{name}：{key} 这份配置不用（不在 10-13 的文档快照里，或者这里不该用）")
            if g["type"] in ("url-test", "fallback", "load-balance"):
                self.assertEqual((g["interval"], g["lazy"]), (h["interval"], h["lazy"]), name)
            if g["type"] == "load-balance":
                self.assertEqual(g["strategy"], "consistent-hashing")

    def test_strict_differs_from_standard_only_where_intended(self):
        """严格版和标准版：DNS、占位节点、订阅、策略组完全相同；多一个 rule-providers；规则只多一条 RULE-SET（排在
        GEOSITE,geolocation-!cn 后面），GEOIP,CN 多了 no-resolve。"""
        a, b = conf("stash"), conf("stash-strict")
        for key in ("mode", "log-level", "dns", "proxies", "proxy-providers", "proxy-groups"):
            self.assertEqual(a[key], b[key], key)
        self.assertNotIn("rule-providers", a)
        self.assertEqual(list(b["rule-providers"]), ["国内域名-ChinaMax"])
        ra, rb = a["rules"], b["rules"]
        extra = [r for r in rb if r.startswith("RULE-SET,")]
        self.assertEqual(extra, ["RULE-SET,国内域名-ChinaMax,国内直连"])
        self.assertEqual(rb.index(extra[0]), rb.index("GEOSITE,geolocation-!cn,国外默认") + 1)
        self.assertEqual([r for r in rb if r not in extra],
                         [r + ",no-resolve" if r == "GEOIP,CN,国内直连" else r for r in ra])
        self.assertEqual(rb[-1], "MATCH,国外默认")

    def test_strict_resolves_nothing_for_rule_matching(self):
        """严格版每一条按 IP 判断的规则都带 no-resolve；标准版只有最后的 GEOIP,CN 不带（它就是靠解析认国内网站的）。"""
        ip_types = ("IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN")
        for client, allowed in (("stash-strict", []), ("stash", ["GEOIP,CN,国内直连"])):
            resolving = [r for r in conf(client)["rules"] if r.split(",")[0] in ip_types and "no-resolve" not in r.split(",")[3:]]
            self.assertEqual(resolving, allowed, client)

    def test_rule_provider_is_the_documented_text_form(self):
        """国内域名清单：domain-text（文档“配置样例”的写法），地址是 source/strict.yaml 登记的上游文件，每天更新一次。"""
        m, _ = model_and_plan()
        rp = conf("stash-strict")["rule-providers"]["国内域名-ChinaMax"]
        self.assertEqual(rp, {"behavior": "domain-text", "url": m.strict["domestic_lists"]["stash"][0]["url"], "interval": 86400})
        self.assertTrue(rp["url"].endswith("/rule/Clash/ChinaMax/ChinaMax_Domain_For_Clash.txt"))


class StashDns(unittest.TestCase):
    def test_dns_block(self):
        """nameserver 是国内 DoH；局域网后缀交给系统 DNS（一个后缀一条、值是单个 system）；
        局域网后缀和“要真实地址的名单”拿真实地址；follow-rule 写明不开。DNS 段里没有境外 DNS。"""
        m, _ = model_and_plan()
        lan = m.project["lan"]["domain_suffix"]
        real_ip = [("+." + x["suffix"]) if "suffix" in x else x["domain"] for x in m.dns["real_ip"]]
        for client in STASH_CLIENTS:
            d = conf(client)["dns"]
            self.assertEqual(set(d), {"follow-rule", "nameserver", "nameserver-policy", "fake-ip-filter"}, client)
            self.assertIs(d["follow-rule"], False)
            self.assertEqual(d["nameserver"], m.dns["domestic_doh"])
            self.assertEqual(d["nameserver-policy"], {"+." + s: "system" for s in lan})
            self.assertEqual(d["fake-ip-filter"], list(dict.fromkeys(["+." + s for s in lan] + real_ip)))
            for foreign in m.dns["foreign_doh"]:
                self.assertNotIn(foreign, yaml.safe_dump(d, allow_unicode=True))

    def test_wildcard_keys_are_quoted_like_the_docs(self):
        """以 + 开头的域名写法在 DNS 段里加了单引号（文档的例子都加了）。"""
        dns_text = text("stash").split("\ndns:\n", 1)[1].split("\n\n", 1)[0]
        bare = [ln for ln in dns_text.splitlines() if re.match(r"^\s+\+", ln)]
        self.assertEqual(bare, [])
        self.assertIn("'+.lan': system", dns_text)

    def test_nothing_that_needs_stash_3_6_or_3_4(self):
        """不用文档标了 iOS 3.6 / macOS 4.3 才有的写法（proxy-server-nameserver、加密 DNS bootstrap、inline 规则集合、
        GEOIP,UNKNOWN），也不用 iOS 3.4.0 / macOS 4.2.0 才有的 nameserver-policy 写法（geosite: 键、一个键配多个服务器）。"""
        for client in STASH_CLIENTS:
            c = conf(client)
            t = text(client)
            for key in ("proxy-server-nameserver", "default-nameserver"):
                self.assertNotIn(key, c["dns"], client)
            self.assertFalse([k for k in c["dns"]["nameserver-policy"] if k.startswith("geosite:")], client)
            self.assertFalse([v for v in c["dns"]["nameserver-policy"].values() if not isinstance(v, str)], client)
            for rp in (c.get("rule-providers") or {}).values():
                self.assertNotEqual(rp.get("type"), "inline", client)
            self.assertNotIn("UNKNOWN", t, client)


class StashPlaceholders(unittest.TestCase):
    def test_one_placeholder_per_region_that_cannot_connect(self):
        m, _ = model_and_plan()
        proxies = conf("stash")["proxies"]
        want = [r["name"] + "·无可用节点" for r in m.regions] + [m.other_region["name"] + "·无可用节点"]
        self.assertEqual([p["name"] for p in proxies], want)
        for p in proxies:
            self.assertEqual((p["type"], p["server"], p["port"]), ("http", "127.0.0.1", 1), p["name"])
            self.assertEqual(p["benchmark-url"], m.hc["url_http"])

    def test_each_filter_group_picks_exactly_its_own_placeholder(self):
        """每个按节点筛选的组，筛选正则（Python 的正则）正好选中一个占位节点，是它自己地区的那个：
        这个地区一个节点都没有时，组里还有它，不会因为“没有代理”被 Stash 当作直连。"""
        m, _ = model_and_plan()
        ph = emit_stash.placeholders(m)
        paypal_region = m.special_entries["paypal_fixed"]["region"]
        for g in conf("stash")["proxy-groups"]:
            if "filter" not in g:
                continue
            hit = [n for n in ph.values() if re.search(g["filter"], n)]
            region = next((rid for rid, name in ph.items() if g["name"].startswith(name.replace("·无可用节点", ""))), None)
            if g["name"] == m.special_entries["paypal_fixed"]["name"]:
                region = paypal_region
            self.assertEqual(hit, [ph[region]], g["name"])

    def test_placeholders_are_in_the_hand_written_node_name_expectations(self):
        """占位节点的名字写进了 tests/node_names.yaml 的期望（只进自己地区的组）：
        这样 tools/check_icu.py 也用 ICU 跑一遍，test_regions.py 也拿各端的筛选核对（Stash 的正则引擎未知，见 docs/06）。"""
        m, _ = model_and_plan()
        for rid, name in emit_stash.placeholders(m).items():
            self.assertIn(name, NODE_NAMES["expect"][rid], rid)

    def test_pinned_paypal_node_keeps_its_placeholder(self):
        """local.yaml 指定了 PayPal 固定节点时，筛选是“名称完全相同”，另外允许美国的占位节点（不然那个节点被删掉以后组是空的）。"""
        m, plan = model_and_plan()
        m2 = copy.deepcopy(m)
        m2.special_entries["paypal_fixed"]["pinned_node_name"] = "🇺🇸 美国 PayPal, 专用 01"
        t = emit_stash.build(m2, plan)
        g = next(x for x in yaml.safe_load(t)["proxy-groups"] if x["name"] == m.special_entries["paypal_fixed"]["name"])
        rx = re.compile(g["filter"])
        self.assertTrue(rx.search("🇺🇸 美国 PayPal, 专用 01"))
        self.assertFalse(rx.search("🇺🇸 美国 PayPal, 专用 02"))
        self.assertTrue(rx.search("美国·无可用节点"))
        self.assertFalse(rx.search("香港·无可用节点"))
        self.assertEqual(verify.check_stash(t), [])


def all_node_names():
    """tests/node_names.yaml 里所有的节点名（各地区的期望、只进手动组的、已知的局限），去重保序。"""
    names = [n for lst in NODE_NAMES["expect"].values() for n in lst]
    names += [x["name"] for key in ("manual_only", "known_limits", "known_auto_limits") for x in NODE_NAMES[key]]
    return list(dict.fromkeys(names))


class StashBuiltinPolicies(unittest.TestCase):
    """GPT 审核 r16 的 R16-F01（2026-10-14）：文档“远程代理集”说远程代理集为空时以 DIRECT 替代；“其他地区”的筛选是
    “六个地区都不是的都收”，r16 会把 DIRECT 这个名字也收进组里。r17 起每条节点筛选的开头都排除内置策略的名字。
    这里只能查正则本身（Python 的正则）：App 替代之后组里实际有什么、会不会另外塞进 DIRECT，要在真机上看（docs/09）。"""

    NAMES = list(dict.fromkeys(x for n in emit_stash.BUILTIN_POLICIES for x in (n, n.lower(), n.title(), n.capitalize())))

    def test_no_filter_picks_a_builtin_policy(self):
        for client in STASH_CLIENTS:
            for g in conf(client)["proxy-groups"]:
                if "filter" in g:
                    rx = re.compile(g["filter"])
                    self.assertEqual([x for x in self.NAMES if rx.search(x)], [], f"{client}：{g['name']}")

    def test_without_the_prefix_other_regions_would_pick_direct(self):
        """前缀不是摆设：去掉它，“其他地区”那条会选中 DIRECT（r16 就是这样）；六个地区的本来就不会（名字里没有地区词）。"""
        m, _ = model_and_plan()
        rx = m.node_regexes()
        self.assertTrue(re.search(rx["other"], "DIRECT"))
        self.assertTrue(re.search(rx["other"], "reject-drop"))
        self.assertFalse(re.search(emit_stash.exclude_builtins(rx["other"]), "DIRECT"))
        for gid in [r["id"] for r in m.regions]:
            self.assertFalse(re.search(rx[gid], "DIRECT"), gid)

    def test_prefix_changes_nothing_for_node_names(self):
        """前缀只排除这几个名字本身：tests/node_names.yaml 里的每个节点名，加不加前缀，宽、严两套筛选的结果都一样；
        名字里只是含有 DIRECT 之类字样的节点照样按原来的规则选。"""
        m, _ = model_and_plan()
        names = all_node_names() + ["DIRECT 01", "🇭🇰 香港 Direct 02", "Reject 01", "REJECT-DROP-1", "directx", " DIRECT"]
        regexes = [("宽", k, v) for k, v in m.node_regexes().items()] + [("严", k, v) for k, v in m.node_regexes_strict().items()]
        for kind, gid, rx in regexes:
            plain, wrapped = re.compile(rx), re.compile(emit_stash.exclude_builtins(rx))
            for n in names:
                self.assertEqual(bool(wrapped.search(n)), bool(plain.search(n)), (kind, gid, n))

    def test_prefix_only_goes_after_the_documented_head(self):
        """前缀加在“(?i)^”后面；不是这样开头的正则直接报错，不去猜该加在哪里。"""
        self.assertEqual(emit_stash.exclude_builtins("(?i)^x"), "(?i)^(?!(?:DIRECT|REJECT|REJECT-DROP)$)x")
        with self.assertRaises(ValueError):
            emit_stash.exclude_builtins("^(?i)x")


class StashVerifyCatches(unittest.TestCase):
    """写盘前的结构检查（verify.check_stash）要能拦住这几种坏配置。"""

    def mutate(self, client, fn):
        c = conf(client)
        fn(c)
        return verify.check_stash(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), strict=client == "stash-strict")

    def test_missing_placeholder(self):
        probs = self.mutate("stash", lambda c: c["proxies"].pop(0))
        self.assertTrue(any("占位节点" in p and "香港" in p for p in probs), probs)

    def test_placeholder_that_could_connect(self):
        def fn(c):
            c["proxies"][0]["server"] = "1.1.1.1"
        self.assertTrue(any("连不上" in p for p in self.mutate("stash", fn)))

    def test_filter_without_include_all(self):
        def fn(c):
            g = next(x for x in c["proxy-groups"] if "filter" in x)
            del g["include-all"]
        self.assertTrue(any("include-all" in p for p in self.mutate("stash", fn)))

    def test_empty_group(self):
        def fn(c):
            c["proxy-groups"].append({"name": "空组", "type": "select"})
        self.assertTrue(any("没有成员" in p for p in self.mutate("stash", fn)))

    def test_strict_geoip_that_resolves(self):
        def fn(c):
            c["rules"] = [r.replace("GEOIP,CN,国内直连,no-resolve", "GEOIP,CN,国内直连") for r in c["rules"]]
        self.assertTrue(any("no-resolve" in p for p in self.mutate("stash-strict", fn)))

    def test_strict_list_before_geolocation(self):
        def fn(c):
            r = c["rules"]
            i, j = r.index("GEOSITE,geolocation-!cn,国外默认"), r.index("RULE-SET,国内域名-ChinaMax,国内直连")
            r[i], r[j] = r[j], r[i]
        self.assertTrue(any("排在" in p for p in self.mutate("stash-strict", fn)))

    def test_unknown_rule_set_and_unused_provider(self):
        def fn(c):
            c["rules"] = [r.replace("RULE-SET,国内域名-ChinaMax,", "RULE-SET,别的清单,") for r in c["rules"]]
        probs = self.mutate("stash-strict", fn)
        self.assertTrue(any("规则集合不存在" in p for p in probs), probs)
        self.assertTrue(any("没有被任何规则引用" in p for p in probs), probs)

    def test_filter_that_picks_a_builtin_policy(self):
        """把“其他地区”的筛选换回 r16 的写法（没有排除内置策略的前缀）：结构检查要报出来。"""
        m, _ = model_and_plan()

        def fn(c):
            g = next(x for x in c["proxy-groups"] if x["name"] == m.other_region["name"])
            g["filter"] = m.node_regexes()["other"]
        probs = self.mutate("stash", fn)
        self.assertTrue(any("内置策略" in p and "DIRECT" in p for p in probs), probs)

    def test_build_refuses_a_filter_that_picks_a_builtin_policy(self):
        """生成时也核对：筛选不加前缀（会选中 DIRECT）时，生成器直接报错，不写出配置。"""
        from unittest import mock
        m, plan = model_and_plan()
        with mock.patch.object(emit_stash, "exclude_builtins", side_effect=lambda rx: rx):
            with self.assertRaisesRegex(ValueError, "内置策略"):
                emit_stash.build(m, plan)

    def test_build_refuses_a_broken_stash_config(self):
        """生成时就核对占位节点：筛选正则选不中自己地区的占位节点时，生成器直接报错，不写出配置。"""
        from unittest import mock
        m, plan = model_and_plan()
        ph = emit_stash.placeholders(m)
        swapped = dict(ph, hk=ph["jp"], jp=ph["hk"])             # 香港、日本的占位节点对调：各自的筛选都选不中“自己的”那个
        with mock.patch.object(emit_stash, "placeholders", return_value=swapped):
            with self.assertRaises(ValueError):
                emit_stash.build(m, plan)


class StashRuleSetInTheEmulator(unittest.TestCase):
    def test_strict_list_catches_what_both_geosite_sets_miss(self):
        """样本数据下：只在国内域名清单（ChinaMax 的样本）里的主机，严格版靠 RULE-SET 直连；标准版不解析就认不出，按假定的
        解析结果（样本里没列，算境外）走国外默认。真实数据下的同一件事由 test_real_data.py 的快照核对（例如整段 .ms）。"""
        from helpers import emulate, route
        fx = emulate.Fixtures(load_yaml("fixtures.yaml"))
        self.assertEqual(route("stash-strict", emulate.Conn(host="www.only-in-chinamax-sample.com"), fx), "国内直连")
        self.assertEqual(route("stash", emulate.Conn(host="www.only-in-chinamax-sample.com"), fx), "国外默认")


class StashHeader(unittest.TestCase):
    def test_header_says_what_was_checked(self):
        for client in STASH_CLIENTS:
            head = text(client).split("\n\n", 1)[0]
            self.assertIn("iOS 3.4.0", head)
            self.assertIn("docs/09", head)
            self.assertIn("订阅", head)
        self.assertIn("严格版", text("stash-strict").split("\n\n", 1)[0])
        self.assertNotIn("严格版", text("stash"))
        self.assertIn("stash/stash.yaml", outputs())


if __name__ == "__main__":
    unittest.main()

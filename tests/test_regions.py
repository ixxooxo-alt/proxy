"""按节点名称分地区（2026-10-02）。

期望值有三个来源，都不是从生成结果反抄的：
  1. tests/node_names.yaml：人工按“名字表达的落地在哪”写的常见写法与边界写法；
  2. tests/data/cldr_tz_names.json：CLDR 的全部国家 / 地区名（英文、简体、繁体）和时区库的城市名，按国家代码判断归属；
  3. 词表自身：每个词单独出现时必须归它所在的地区。
被检查的有三样：拼出来的正则、逐步判断的实现、四个客户端产物里实际写出的筛选。
ICU（推断 Loon / Quantumult X 用的引擎）与 mihomo 官方内核上的对比分别在 tools/check_icu.py、tools/check_official.py。"""
import contextlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from helpers import ROOT, build, emulate, load_yaml, model_and_plan, parsed, text
from generator import emit_singbox, regions
from generator.model import SourceError, load

sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_node_names  # noqa: E402

SAMPLES = load_yaml("node_names.yaml")
SIX = ["hk", "jp", "kr", "tw", "sg", "us"]
NAME = {"hk": "香港", "jp": "日本", "kr": "韩国", "tw": "台湾", "sg": "新加坡", "us": "美国", "other": "其他地区"}
ISO = {"HK": "hk", "JP": "jp", "KR": "kr", "TW": "tw", "SG": "sg", "US": "us"}
# 美国海外属地：归美国还是其他地区都说得过去，不作为期望
TERRITORIES = {"UM", "VI", "AS", "GU", "PR", "MP"}
DECOR = ["{w} 01", "{w}01", "01 {w}", "[{w}] 01", "{w}-01", "{w}_01", "{w}|01", "{w}丨01", "【{w}】01",
         "Premium {w} 01", "{w} IPLC 01", "{w} 家宽 x0.5", "V2 {w}-A", "{w}（原生）", "{w}·02", "IEPL-{w}-03", "{w} #4"]


def expected():
    out = {}
    for k, names in SAMPLES["expect"].items():
        for n in names:
            out[n] = [] if k == "info" else [k]
    for e in SAMPLES["both"]:
        out[e["name"]] = sorted(e["groups"])
    return out


def reference():
    with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
        return json.load(f)


def spec():
    return model_and_plan()[0].region_spec


_compiled = {}


def by_regex(name, rxs=None):
    """这个名字匹配哪些组的正则（rxs 缺省为公开模型的那一套；每套只编译一次）。"""
    rxs = rxs if rxs is not None else model_and_plan()[0].node_regexes()
    key = id(rxs)
    if key not in _compiled:
        _compiled[key] = (rxs, {k: re.compile(v) for k, v in rxs.items()})      # 同时保留 rxs，避免 id 被复用
    return sorted(k for k, v in _compiled[key][1].items() if v.search(name))


def country_names():
    """[(节点名, 期望的组)]：每个国家 / 地区的中英文名、代码、国旗各种组合。"""
    out = []
    for c in reference()["regions"]:
        if c["code"] in TERRITORIES:
            continue
        want = ISO.get(c["code"], "other")
        fl = regions.flag(c["code"])
        for n in (f"{fl} {c['zh_hans']} 01", f"{c['zh_hans']} 01", f"{c['zh_hant']} 01", f"{c['en']} 01",
                  f"{c['code']}-01", f"{fl} {c['code']} 01"):
            out.append((n, want))
    return out


def word_names():
    """[(节点名, 词所在的地区)]：词表里的每个词、每面国旗，配上常见的前后缀写法。"""
    out = []
    s = spec()
    for w in s.regions + [s.other]:
        for word in w.words + w.latin + [regions.flag(c) for c in w.flags]:
            for variant in sorted({word, word.lower(), word.upper()}):
                out += [(d.format(w=variant), w.id) for d in DECOR]
    return out


class HandWrittenExpectations(unittest.TestCase):
    def test_sample_file_is_big_enough_and_unique(self):
        e = expected()
        self.assertGreaterEqual(len(e), 480)
        total = sum(len(v) for v in SAMPLES["expect"].values()) + len(SAMPLES["both"])
        self.assertEqual(total, len(e), "样本里有重复的名字")
        for k in SIX + ["other", "info"]:
            self.assertGreaterEqual(len(SAMPLES["expect"][k]), 20, k)

    def test_composed_regex(self):
        wrong = [(n, want, by_regex(n)) for n, want in expected().items() if by_regex(n) != want]
        self.assertEqual(wrong, [], "（节点名, 期望, 正则的结果）")

    def test_step_by_step_classifier(self):
        cl = regions.Classifier(spec())
        wrong = [(n, want, sorted(cl.classify(n).groups)) for n, want in expected().items()
                 if sorted(cl.classify(n).groups) != want]
        self.assertEqual(wrong, [], "（节点名, 期望, 逐步判断的结果）")

    def test_known_limits_are_recorded_as_they_are(self):
        """已知分不对的写法：结果要和记录的一致（规则改动让它们变了，就该更新记录和文档）。"""
        cl = regions.Classifier(spec())
        self.assertGreaterEqual(len(SAMPLES["known_limits"]), 5)
        for e in SAMPLES["known_limits"]:
            self.assertNotEqual(sorted(e["ideal"]), sorted(e["actual"]), e["name"])
            self.assertNotIn(e["name"], expected(), "已知分不对的名字不能同时放在期望里")
            self.assertEqual(by_regex(e["name"]), sorted(e["actual"]), e["name"])
            self.assertEqual(sorted(cl.classify(e["name"]).groups), sorted(e["actual"]), e["name"])

    def test_users_own_airport_style(self):
        """用户截图里的写法：台湾节点前面是 🇨🇳，带“家宽”字样。"""
        for n, want in (("🇨🇳 台湾 07 家宽", ["tw"]), ("🇨🇳 台湾 08 家宽", ["tw"]), ("🇸🇬 新加坡 12 家宽", ["sg"]),
                        ("🇺🇸 美国 10 家宽", ["us"]), ("🇺🇸 美国 04", ["us"]), ("🇯🇵 日本 04", ["jp"]),
                        ("🇯🇵 日本 02", ["jp"])):
            self.assertEqual(by_regex(n), want, n)


class GeneratedConfigs(unittest.TestCase):
    """四个客户端产物里写出的筛选，就是词表拼出来的那几条正则。"""

    def setUp(self):
        self.m, self.p = model_and_plan()
        self.rx = self.m.node_regexes()

    def test_loon(self):
        f = parsed("loon")["filters"]
        for gid, label in (("hk", "F-HK"), ("jp", "F-JP"), ("kr", "F-KR"), ("tw", "F-TW"), ("sg", "F-SG"),
                           ("us", "F-US"), ("other", "F-OTHER")):
            self.assertEqual(f[label], self.rx[gid], label)
        g = parsed("loon")["groups"]
        self.assertEqual(g["PayPal·美国固定"]["members"], ["F-US"], "没填固定节点时，PayPal 固定入口用美国那条筛选")
        self.assertEqual(len(f), 7, "同一条正则只定义一次")

    def test_quantumultx(self):
        pol = parsed("quantumultx")["policies"]
        for gid in SIX:
            for suffix in ("手动", "自动", "故障转移", "负载均衡"):
                self.assertEqual(pol[f"{NAME[gid]}·{suffix}"]["params"]["server-tag-regex"], self.rx[gid])
        self.assertEqual(pol["其他地区"]["params"]["server-tag-regex"], self.rx["other"])
        self.assertEqual(pol["PayPal·美国固定"]["params"]["server-tag-regex"], self.rx["us"])

    def test_mihomo(self):
        for client in ("mihomo-profile", "mihomo-core"):
            g = {x["name"]: x for x in parsed(client)["proxy-groups"]}
            for gid in SIX:
                for suffix in ("手动", "自动", "故障转移", "负载均衡"):
                    grp = g[f"{NAME[gid]}·{suffix}"]
                    self.assertEqual(grp["filter"], self.rx[gid])
                    self.assertNotIn("exclude-filter", grp, "排除条件已经在同一条正则里")
            self.assertEqual(g["其他地区"]["filter"], self.rx["other"])
            self.assertEqual(g["PayPal·美国固定"]["filter"], self.rx["us"])
            raw = text(client)
            for gid in SIX:      # 每条地区正则只写一次，其余用 YAML 别名
                self.assertEqual(raw.count(f"&flt-{gid} "), 1, gid)
                self.assertEqual(raw.count(f"*flt-{gid}\n"), 4 if gid == "us" else 3, gid)
            self.assertEqual(raw.count(self.rx["hk"]), 1)

    def test_singbox_groups_nodes_at_build_time(self):
        e = expected()
        nodes = [{"type": "socks", "tag": n, "server": "127.0.0.1", "server_port": 1080} for n in e]
        conf = json.loads(emit_singbox.build(self.m, self.p, "1.14", nodes))
        ob = {o["tag"]: o for o in conf["outbounds"]}
        for gid in SIX + ["other"]:
            group = NAME[gid] if gid == "other" else NAME[gid] + "·手动"
            want = [n for n, groups in e.items() if gid in groups]
            self.assertEqual(ob[group]["outbounds"], want, group)
        for n, groups in e.items():
            if not groups:
                self.assertFalse(any(n in o.get("outbounds", []) for o in ob.values()), f"信息节点 {n} 进了某个组")


class IndependentNames(unittest.TestCase):
    def test_reference_data_is_complete(self):
        ref = reference()
        self.assertEqual(len(ref["regions"]), 249)
        self.assertGreater(len(ref["tz_cities"]), 300)

    def test_country_names_and_flags(self):
        wrong = [(n, want, by_regex(n)) for n, want in country_names() if by_regex(n) != [want]]
        self.assertEqual(wrong, [], "六个地区的标准名称都要认出来，其他国家都不能被认成这六个地区")

    def test_cities_of_other_countries_are_never_claimed(self):
        wrong = []
        recognised = 0
        for z in reference()["tz_cities"]:
            cc = z["cc"][0]
            if cc in TERRITORIES:
                continue
            got = by_regex(z["city"] + " 01")
            if cc not in ISO:
                if got != ["other"]:
                    wrong.append((z["city"], cc, got))
            elif got == [ISO[cc]]:
                recognised += 1
            else:
                self.assertEqual(got, ["other"], f"{z['city']} 没认出来时只能进其他地区")
        self.assertEqual(wrong, [])
        # 时区库里美国的条目大多是小镇（Monticello、Vincennes……），机场不会用；主要城市要认得出
        self.assertGreaterEqual(recognised, 15)
        for city in ("Tokyo", "Seoul", "Taipei", "Singapore", "Hong Kong", "New York", "Los Angeles", "Chicago",
                     "Denver", "Phoenix", "Detroit", "Honolulu"):
            self.assertNotEqual(by_regex(city + " 01"), ["other"], city)


class Consistency(unittest.TestCase):
    def all_names(self):
        names = list(expected()) + [n for n, _ in country_names()]
        names += [z["city"] + " 01" for z in reference()["tz_cities"]] + [n for n, _ in word_names()]
        return list(dict.fromkeys(names))

    def test_every_word_lands_in_its_own_region(self):
        wrong = [(n, want, by_regex(n)) for n, want in word_names() if by_regex(n) != [want]]
        self.assertEqual(wrong[:20], [], f"共 {len(wrong)} 个")

    def test_regex_and_step_by_step_agree(self):
        """两种实现（拼出来的正则、逐步判断）在全部样本上结果相同。"""
        cl = regions.Classifier(spec())
        names = self.all_names()
        self.assertGreater(len(names), 20000)
        diff = [(n, by_regex(n), sorted(cl.classify(n).groups)) for n in names
                if by_regex(n) != sorted(cl.classify(n).groups)]
        self.assertEqual(diff[:20], [], f"共 {len(diff)} 个")

    def test_random_names_agree(self):
        """随机拼出来的名字（地区词、国旗、中转词、箭头、常见标签随机组合，种子固定）：两种实现结果相同，
        非信息节点不丢，“其他地区”不和六个地区同时出现。公开词表和带本地补充样例的词表各跑一遍。"""
        with open(os.path.join(ROOT, "source", "regions.yaml"), encoding="utf-8") as f:
            overlay_spec, errors = regions.parse(yaml.safe_load(f), OVERLAY["node_names"])
        self.assertEqual(errors, [])
        for label, sp, count, seed in (("公开词表", spec(), 30000, 20261002), ("带本地补充", overlay_spec, 10000, 7)):
            rnd = random.Random(seed)
            rx = {k: re.compile(v) for k, v in regions.compose(sp).items()}
            cl = regions.Classifier(sp)
            words = [x for w in sp.regions + [sp.other] for x in w.words + w.latin + [regions.flag(c) for c in w.flags]]
            flags = [regions.flag(c) for c in ("CN", "EU", "UN", "GB", "DE", "RU", "MO", "LV", "NU", "KP")]
            markers = sp.after + sp.before + sp.arrows + ["Via", "VIA", "Latvia", "Bolivia", "avia"]
            info = sp.info_words[:6] + sp.info_latin
            tags = ["01", "IPLC", "x0.5", "家宽", "|", "-", "_", " ", "  ", "[", "]", "(", ")", "【", "】", "·", "A", "a",
                    "Premium", "NF", "TR", "#", "/", ":", "：", ".", ",", "=", '"', "`", "流量", "群", "新", "港", "日", "美"]
            seps = ["", "", " ", " ", "-", "_", "|", " | ", "  "]
            bad = []
            for _ in range(count):
                parts = []
                for _ in range(rnd.randint(1, 6)):
                    r = rnd.random()
                    tok = rnd.choice(words if r < 0.40 else flags if r < 0.50 else markers if r < 0.72
                                     else info if r < 0.75 else tags)
                    r = rnd.random()
                    parts += [tok.lower() if r < 0.15 else tok.upper() if r < 0.25 else tok, rnd.choice(seps)]
                name = "".join(parts[:-1]).strip()
                if not name:
                    continue
                got = sorted(g for g, r_ in rx.items() if r_.search(name))
                v = cl.classify(name)
                if got != sorted(v.groups):
                    bad.append((name, got, sorted(v.groups)))
                elif not got and v.basis not in ("info", "assign"):
                    bad.append((name, got, "没有进任何组"))
                elif "other" in got and len(got) > 1:
                    bad.append((name, got, "其他地区和别的地区同时出现"))
            self.assertEqual(bad[:10], [], f"{label}：共 {len(bad)} 个")

    def test_no_node_is_lost_and_other_is_exclusive(self):
        """非信息节点至少进一个组；“其他地区”不和六个地区同时出现；这批样本里最多同时进两个地区。"""
        cl = regions.Classifier(spec())
        for n in self.all_names():
            got = by_regex(n)
            if cl.is_info(n):
                self.assertEqual(got, [], n)
                continue
            self.assertTrue(got, f"{n} 没有进任何组")
            if "other" in got:
                self.assertEqual(got, ["other"], n)
            self.assertLessEqual(len(got), 2, n)


class Portability(unittest.TestCase):
    """正则要原样写进 Loon / QX 的一行和 mihomo 的 filter，并且三个引擎都要支持。"""

    def test_no_character_with_special_meaning(self):
        for gid, rx in model_and_plan()[0].node_regexes().items():
            for bad in (",", '"', "`", "=", " ", "\n", "\t"):
                self.assertNotIn(bad, rx, f"{gid} 含 {bad!r}")
            self.assertTrue(rx.startswith("(?i)^") and rx.endswith(".*$"), gid)

    def test_only_constructs_every_engine_supports(self):
        for gid, rx in model_and_plan()[0].node_regexes().items():
            for bad in ("(?=", "(?<=", "(?>", "(?P", "\\b", "\\d", "\\w", "\\p", "\\u", "*+", "++", "?+", "{"):
                self.assertNotIn(bad, rx, f"{gid} 用了 {bad}")
            # 否定后顾必须定长：Python 的 re 遇到变长后顾会直接报错
            re.compile(rx)

    def test_size_is_bounded(self):
        for gid, rx in model_and_plan()[0].node_regexes().items():
            self.assertLess(len(rx.encode("utf-8")), 16000, f"{gid} 的正则过长，Quantumult X 每个模式组都要写一遍")

    def test_icu_engine_agrees(self):
        """系统里有 ICU 时，用它实际跑一遍（推断 Loon / QX 用的是苹果系统自带的正则，底层是 ICU）。放在子进程里：
        万一某个平台上的库不兼容，也只是这一项失败，不会带崩整个测试进程。"""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_icu.py"), "--public"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if r.returncode == 2:
            self.skipTest("这台机器上没有可用的 ICU 库：" + r.stdout.strip()[-200:])
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("完全一致", r.stdout)


class Rules(unittest.TestCase):
    """规则本身的几个要点，各用一两个最小的例子固定下来（更多例子在 node_names.yaml）。"""

    def check(self, cases):
        cl = regions.Classifier(spec())
        for n, want in cases:
            self.assertEqual(by_regex(n), want, n)
            self.assertEqual(sorted(cl.classify(n).groups), want, n)

    def test_flag_first_and_neutral_flags(self):
        self.check([("🇺🇸 香港 01", ["us"]), ("🇨🇳 香港 01", ["hk"]), ("🇪🇺 日本 01", ["jp"]), ("🇺🇳 美国 01", ["us"]),
                    ("🇬🇧 日本 01", ["other"]), ("🇺🇲 01", ["us"])])

    def test_adjacent_flags_are_read_in_pairs(self):
        # 🇨🇳🇺🇸 的中间两个字符拼起来是 🇳🇺（纽埃），不能被当成一面旗
        self.check([("🇨🇳🇺🇸 01", ["us"]), ("🇭🇰🇯🇵 01", ["jp"]), ("🇨🇳🇭🇰 01", ["hk"])])

    def test_yielding_region(self):
        self.check([("香港-日本 01", ["jp"]), ("日本 香港 01", ["jp"]), ("香港 英国 01", ["other"]), ("香港 01", ["hk"]),
                    ("🇭🇰🇺🇸 01", ["us"])])

    def test_transit_positions(self):
        self.check([("日本转美国 01", ["us"]), ("美国转香港 01", ["hk"]), ("香港 转发 01", ["hk"]),
                    ("美国 01 | 日本中转", ["us"]), ("日本中转 01", ["jp"]), ("日本→美国 01", ["us"]),
                    ("via 日本 美国 01", ["us"]), ("美国 01 解锁日本", ["us"]), ("美国 01 日本解锁", ["us"]),
                    ("经日本 美国 01", ["us"]), ("香港 01 解锁 🇺🇸🇯🇵", ["hk"])])

    def test_via_must_be_a_separate_word(self):
        # via 在名字开头、在名字中间都算；Latvia、Bolivia、Monrovia 这类词里的 via 不算
        self.check([("via 日本 美国 01", ["us"]), ("Via 日本 美国 01", ["us"]), ("IEPL via 日本 美国 01", ["us"]),
                    ("IEPL-via日本 美国 01", ["us"]), ("via 🇯🇵 美国 01", ["us"]),
                    ("Avia 日本 美国 01", ["jp", "us"]), ("Monrovia 🇺🇸 01", ["us"]), ("Bolivia US 01", ["us"]),
                    ("Latvia 🇱🇻 01", ["other"])])

    def test_other_country_wins_over_region_words(self):
        self.check([("日本 英国 01", ["other"]), ("South America 01", ["other"]), ("North Korea 01", ["other"]),
                    ("英国 01 | 日本中转", ["other"])])

    def test_latin_boundaries(self):
        self.check([("RUS 01", ["other"]), ("AUS 01", ["other"]), ("Plus 01", ["other"]), ("HKD 01", ["other"]),
                    ("US01", ["us"]), ("us-01", ["us"]), ("LosAngeles01", ["us"]), ("Los_Angeles", ["us"])])

    def test_info_words(self):
        self.check([("剩余流量：1G", []), ("香港 03 大流量", ["hk"]), ("开曼群岛 01", ["other"]), ("Preset 01", ["other"]),
                    ("Expires 2026-12-31", []), ("过滤掉 3 条线路", []), ("香港 BGP 线路 01", ["hk"])])

    def test_explanations_are_human_readable(self):
        cl = regions.Classifier(spec())
        v = cl.classify("美国 01 | 深港中转")
        self.assertEqual(v.groups, ["us"])
        self.assertIn("香港让位", "；".join(v.notes))
        v = cl.classify("Premium 01")
        self.assertEqual((v.groups, v.basis), (["other"], "none"))
        v = cl.classify("日本-美国 01")
        self.assertIn("说不清落地", "；".join(v.notes))


class TempSource:
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "source"), os.path.join(self.dir, "source"))

    def edit(self, rel, fn):
        p = os.path.join(self.dir, "source", rel)
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fn(data)
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def write_local(self, data):
        with open(os.path.join(self.dir, "source", "local.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def close(self):
        shutil.rmtree(self.dir)


class SourceValidation(unittest.TestCase):
    """词表写错时生成器要拒绝，而不是悄悄生成一条坏正则。"""

    def assertRejected(self, fn, needle):
        t = TempSource()
        try:
            t.edit("regions.yaml", fn)
            with self.assertRaises(SourceError) as cm:
                load(t.dir, include_local=False)
            self.assertIn(needle, str(cm.exception))
        finally:
            t.close()

    def region(self, d, rid):
        return next(r for r in d["regions"] if r["id"] == rid)

    def test_same_word_in_two_regions(self):
        self.assertRejected(lambda d: self.region(d, "us")["words"].append("日本"), "同时出现在")

    def test_ascii_word_must_go_to_latin(self):
        self.assertRejected(lambda d: self.region(d, "us")["words"].append("USA2"), "请放进 latin")

    def test_latin_word_charset(self):
        self.assertRejected(lambda d: self.region(d, "us")["latin"].append("美国"), "只能由英文字母")

    def test_pattern_with_forbidden_character(self):
        self.assertRejected(lambda d: self.region(d, "tw").update(patterns=["台(?=中)"]), "不允许的字符")
        self.assertRejected(lambda d: self.region(d, "tw").update(patterns=["台中,台南"]), "不允许的字符")
        self.assertRejected(lambda d: self.region(d, "tw").update(patterns=["台中("]), "不是合法正则")

    def test_unknown_field_and_yaml_boolean(self):
        self.assertRejected(lambda d: self.region(d, "us").update(wrods=["x"]), "未知字段")
        self.assertRejected(lambda d: self.region(d, "us")["flags"].append(False), "加引号")

    def test_flag_in_two_places(self):
        self.assertRejected(lambda d: self.region(d, "jp")["flags"].append("US"), "同时出现在")
        self.assertRejected(lambda d: d["rules"]["neutral_flags"].append("JP"), "neutral_flags")

    def test_only_one_yielding_region(self):
        self.assertRejected(lambda d: self.region(d, "jp").update(yields=True), "最多只能有一个让位")

    def test_missing_region_for_paypal(self):
        def fn(d):
            d["regions"] = [r for r in d["regions"] if r["id"] != "us"]
        t = TempSource()
        try:
            t.edit("regions.yaml", fn)
            with self.assertRaises(SourceError):
                load(t.dir, include_local=False)
        finally:
            t.close()


OVERLAY = load_yaml("local_overlay_sample.yaml")      # 虚构的本地补充 + 人工写的期望；ICU 与 mihomo 内核的检查也用它


class LocalNodeNames(unittest.TestCase):
    """某家机场特有的写法写在 local.yaml：只影响私密产物。"""
    LOCAL = {"node_names": OVERLAY["node_names"]}

    def setUp(self):
        self.t = TempSource()
        self.t.write_local(self.LOCAL)

    def tearDown(self):
        self.t.close()

    def test_extra_words_and_assignments(self):
        m = load(self.t.dir)
        rxs = m.node_regexes()
        cl = regions.Classifier(m.region_spec)
        self.assertGreaterEqual(len(OVERLAY["expect"]), 15)
        for e in OVERLAY["expect"]:
            n, want = e["name"], sorted(e["groups"])
            self.assertEqual(by_regex(n, rxs), want, n)
            self.assertEqual(sorted(cl.classify(n).groups), want, n)
        for rx in rxs.values():
            regions.check_composed(rx)          # 带逗号、引号、等号的节点名也能安全地写进一行

    def test_public_model_ignores_local(self):
        pub = load(self.t.dir, include_local=False).node_regexes()
        self.assertEqual(pub, model_and_plan()[0].node_regexes())
        self.assertEqual(by_regex("Premium 01", pub), ["other"])

    def test_private_outputs_only(self):
        """本地补充的词和指定的节点只在 dist/private/ 的配置里生效，公开配置不变。"""
        out = os.path.join(self.t.dir, "out")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(["--out", out], root=self.t.dir), 0)

        def loon_us(path):
            with open(path, encoding="utf-8") as f:
                return re.compile(emulate.parse_loon(f.read())["filters"]["F-US"])

        def qx_us(path):
            with open(path, encoding="utf-8") as f:
                return re.compile(emulate.parse_qx(f.read())["policies"]["美国·手动"]["params"]["server-tag-regex"])

        def mihomo_us(path):
            with open(path, encoding="utf-8") as f:
                g = {x["name"]: x for x in yaml.safe_load(f)["proxy-groups"]}
            return re.compile(g["美国·手动"]["filter"])

        for getter, pub, priv in ((loon_us, "loon/loon.conf", "private/loon.conf"),
                                  (qx_us, "quantumultx/quantumultx.conf", "private/quantumultx.conf"),
                                  (mihomo_us, "mihomo/mihomo-profile.yaml", "private/mihomo-profile.yaml"),
                                  (mihomo_us, "mihomo/mihomo-core.yaml", "private/mihomo-core.yaml")):
            public, private = getter(os.path.join(out, pub)), getter(os.path.join(out, priv))
            for n in ("STL 01", "圣路易 02", '怪名字, "带" 符号=`1`'):
                self.assertFalse(public.search(n), f"{pub} 不应受 local.yaml 影响：{n}")
                self.assertTrue(private.search(n), f"{priv} 应包含本地补充：{n}")
            self.assertFalse(private.search("日本 99"))
        with open(os.path.join(out, "loon", "loon.conf"), encoding="utf-8") as f:
            self.assertNotIn("Premium", f.read(), "指定的节点名不能出现在公开产物里")

    def test_bad_local_input_is_rejected(self):
        for bad, needle in (({"extra_words": {"xx": {"words": ["a啊"]}}}, "没有这个地区"),
                            ({"assign": [{"name": "A", "region": "mars"}]}, "region 只能是"),
                            ({"extra_words": {"us": {"words": ["日本"]}}}, "同时出现在"),
                            ({"assign": [{"name": "A", "region": "jp"}, {"name": "a", "region": "us"}]}, "指定了两次"),
                            ({"oops": 1}, "未知字段")):
            self.t.write_local({"node_names": bad})
            with self.assertRaises(SourceError) as cm:
                load(self.t.dir)
            self.assertIn(needle, str(cm.exception))


class CheckerTool(unittest.TestCase):
    def run_tool(self, *args, root=ROOT):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = check_node_names.main(list(args), root=root)
        return rc, buf.getvalue()

    def test_report_from_text_file(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "names.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(["🇨🇳 台湾 07 家宽", "美国 01 | 深港中转", "日本-美国 05", "Premium 01", "🇬🇧 英国 01",
                                   "剩余流量：100GB", "", "洛杉矶 02", "洛杉矶 02"]) + "\n")
            rc, out = self.run_tool(p, "--public")
            self.assertEqual(rc, 0)
            self.assertIn("节点 7 个", out, "空行和重复的名字不算")
            for needle in ("台湾 1", "美国 3", "没认出地区", "Premium 01", "说不清落地", "日本-美国 05 → 日本、美国",
                           "按中转 / 让位规则判断", "香港让位", "当成信息节点", "含“剩余”", "落地在其他国家"):
                self.assertIn(needle, out)
            rc, out = self.run_tool(p, "--public", "--all", "--out", os.path.join(d, "r.txt"))
            self.assertIn("🇨🇳 台湾 07 家宽 → 台湾", out)
            with open(os.path.join(d, "r.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), out)
        finally:
            shutil.rmtree(d)

    def test_clash_file_only_names_are_read(self):
        rc, out = self.run_tool("--clash", os.path.join(ROOT, "tests", "node_samples.yaml"), "--public", "--all")
        self.assertEqual(rc, 0)
        self.assertIn("香港 SS → 香港", out)
        for secret in ("example.net", "EXAMPLE", "00000000-0000", "password", "uuid"):
            self.assertNotIn(secret, out, "报告里只能有节点名称")

    def test_bad_input(self):
        rc, _ = self.run_tool(os.path.join(ROOT, "不存在.txt"))
        self.assertEqual(rc, 2)

    def test_build_writes_grouping_report_to_private(self):
        out = tempfile.mkdtemp()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = build.main(["--out", out, "--singbox-nodes", os.path.join(ROOT, "tests", "node_samples.yaml")])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "private", "节点分组报告.txt"), encoding="utf-8") as f:
                rep = f.read()
            self.assertIn("香港 SS → 香港", rep)
            self.assertIn("各组数量", rep)
            for secret in ("example.net", "EXAMPLE", "00000000-0000"):
                self.assertNotIn(secret, rep)
            self.assertFalse(os.path.exists(os.path.join(out, "节点分组报告.txt")), "报告只写进 private/")
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()

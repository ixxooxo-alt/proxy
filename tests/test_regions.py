"""按节点名称分地区（2026-10-02；2026-10-04 按 GPT 审核 F02–F05 改了提示行、解锁说明、国名与城市词的先后，
并把每个地区的筛选分成宽、严两条：说不清落地的节点只进手动组）。

期望值有三个来源，都不是从生成结果反抄的：
  1. tests/node_names.yaml：人工按“名字表达的落地在哪”写的常见写法与边界写法；
  2. tests/data/cldr_tz_names.json：CLDR 的全部国家 / 地区名（英文、简体、繁体）和时区库的城市名，按国家代码判断归属；
  3. 词表自身：每个词单独出现时必须归它所在的地区。
被检查的有三样：拼出来的两套正则（宽的给手动组，严的给自动 / 故障转移 / 负载均衡）、逐步判断的实现、
四个客户端产物里实际写出的筛选。
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
    """{节点名: 进哪些地区的手动组（宽）}。"""
    out = {}
    for k, names in SAMPLES["expect"].items():
        for n in names:
            out[n] = [] if k == "info" else [k]
    for e in SAMPLES["manual_only"]:
        out[e["name"]] = sorted(e["groups"])
    return out


def expected_auto():
    """{节点名: 进哪个地区的自动 / 故障转移 / 负载均衡（严）}。只指向一个地区的才进；其他地区没有这些模式。"""
    out = {}
    for k, names in SAMPLES["expect"].items():
        for n in names:
            out[n] = [] if k in ("info", "other") else [k]
    for e in SAMPLES["manual_only"]:
        out[e["name"]] = []
    return out


def reference():
    with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
        return json.load(f)


def spec():
    return model_and_plan()[0].region_spec


_compiled = {}


def by_regex(name, rxs=None):
    """这个名字匹配哪些组的正则（rxs 缺省为公开模型宽的那一套；每套只编译一次）。"""
    rxs = rxs if rxs is not None else model_and_plan()[0].node_regexes()
    key = id(rxs)
    if key not in _compiled:
        _compiled[key] = (rxs, {k: re.compile(v) for k, v in rxs.items()})      # 同时保留 rxs，避免 id 被复用
    return sorted(k for k, v in _compiled[key][1].items() if v.search(name))


def by_strict(name, rxs=None):
    """这个名字匹配哪些地区严的那条正则。"""
    return by_regex(name, rxs if rxs is not None else model_and_plan()[0].node_regexes_strict())


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
        self.assertGreaterEqual(len(e), 540)
        total = sum(len(v) for v in SAMPLES["expect"].values()) + len(SAMPLES["manual_only"])
        self.assertEqual(total, len(e), "样本里有重复的名字")
        for k in SIX + ["other", "info"]:
            self.assertGreaterEqual(len(SAMPLES["expect"][k]), 20, k)
        self.assertGreaterEqual(len(SAMPLES["manual_only"]), 12)

    def test_composed_regex(self):
        wrong = [(n, want, by_regex(n)) for n, want in expected().items() if by_regex(n) != want]
        self.assertEqual(wrong, [], "（节点名, 期望, 宽的那套正则的结果）")

    def test_composed_strict_regex(self):
        wrong = [(n, want, by_strict(n)) for n, want in expected_auto().items() if by_strict(n) != want]
        self.assertEqual(wrong, [], "（节点名, 期望, 严的那套正则的结果）")

    def test_step_by_step_classifier(self):
        cl = regions.Classifier(spec())
        auto = expected_auto()
        wrong = [(n, want, auto[n], sorted(cl.classify(n).groups), sorted(cl.classify(n).auto))
                 for n, want in expected().items()
                 if sorted(cl.classify(n).groups) != want or sorted(cl.classify(n).auto) != auto[n]]
        self.assertEqual(wrong, [], "（节点名, 期望（宽）, 期望（严）, 逐步判断的结果（宽）, （严））")

    def test_unclear_names_stay_out_of_automatic_groups(self):
        """说不清落地的名字（审核 F04）：进所列地区的手动组，不进任何自动 / 故障转移 / 负载均衡。"""
        cl = regions.Classifier(spec())
        for e in SAMPLES["manual_only"]:
            n = e["name"]
            self.assertEqual(by_regex(n), sorted(e["groups"]), n)
            self.assertEqual(by_strict(n), [], n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), v.auto), (sorted(e["groups"]), []), n)
            self.assertIn("说不清落地", "；".join(v.notes), n)

    def test_known_limits_are_recorded_as_they_are(self):
        """已知分不对的写法：结果要和记录的一致（规则改动让它们变了，就该更新记录和文档）。"""
        cl = regions.Classifier(spec())
        self.assertGreaterEqual(len(SAMPLES["known_limits"]), 5)
        for e in SAMPLES["known_limits"]:
            self.assertNotEqual(sorted(e["ideal"]), sorted(e["actual"]), e["name"])
            self.assertNotIn(e["name"], expected(), "已知分不对的名字不能同时放在期望里")
            self.assertEqual(by_regex(e["name"]), sorted(e["actual"]), e["name"])
            self.assertEqual(sorted(cl.classify(e["name"]).groups), sorted(e["actual"]), e["name"])

    def test_known_unrecognised_transit_wordings_are_recorded_as_they_are(self):
        """已知认不出的中转写法（2026-10-05 自查）：这些名字没说清落地，却会进自动类的组。如实记录现在的结果——
        规则改动让它们变了（不管变对还是变错），这里会失败，提醒更新记录和 docs/06。"""
        cl = regions.Classifier(spec())
        self.assertGreaterEqual(len(SAMPLES["known_auto_limits"]), 5)
        for e in SAMPLES["known_auto_limits"]:
            n = e["name"]
            self.assertTrue(e["auto"] and e["why"], f"{n}：这一节只记“进了自动类的组”的名字，并且要写原因")
            self.assertNotIn(n, expected(), "已知认不出的名字不能同时放在期望里")
            self.assertEqual((by_regex(n), by_strict(n)), (sorted(e["groups"]), sorted(e["auto"])), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (sorted(e["groups"]), sorted(e["auto"])), n)

    def test_users_own_airport_style(self):
        """用户截图里的写法：台湾节点前面是 🇨🇳，带“家宽”字样。"""
        for n, want in (("🇨🇳 台湾 07 家宽", ["tw"]), ("🇨🇳 台湾 08 家宽", ["tw"]), ("🇸🇬 新加坡 12 家宽", ["sg"]),
                        ("🇺🇸 美国 10 家宽", ["us"]), ("🇺🇸 美国 04", ["us"]), ("🇯🇵 日本 04", ["jp"]),
                        ("🇯🇵 日本 02", ["jp"])):
            self.assertEqual(by_regex(n), want, n)


class GeneratedConfigs(unittest.TestCase):
    """四个客户端产物里写出的筛选，就是词表拼出来的那几条正则：手动组用宽的，自动 / 故障转移 / 负载均衡用严的。"""
    AUTO_MODES = ("自动", "故障转移", "负载均衡")

    def setUp(self):
        self.m, self.p = model_and_plan()
        self.rx = self.m.node_regexes()
        self.strict = self.m.node_regexes_strict()

    def test_two_regex_sets(self):
        self.assertEqual(sorted(self.rx), sorted(SIX + ["other"]))
        self.assertEqual(sorted(self.strict), sorted(SIX), "其他地区只有手动，没有严的那条")
        for gid in SIX:
            self.assertNotEqual(self.rx[gid], self.strict[gid])

    def test_loon(self):
        f = parsed("loon")["filters"]
        for gid in SIX:
            self.assertEqual(f[f"F-{gid.upper()}"], self.rx[gid], gid)
            self.assertEqual(f[f"F-{gid.upper()}-AUTO"], self.strict[gid], gid)
        self.assertEqual(f["F-OTHER"], self.rx["other"])
        self.assertEqual(len(f), 13, "同一条正则只定义一次：六个地区各两条 + 其他地区")
        g = parsed("loon")["groups"]
        self.assertEqual(g["PayPal·美国固定"]["members"], ["F-US"], "没填固定节点时，PayPal 固定入口用美国宽的那条（人来选）")
        for gid in SIX:
            self.assertEqual(g[f"{NAME[gid]}·手动"]["members"], [f"F-{gid.upper()}"])
            for suffix in self.AUTO_MODES:
                self.assertEqual(g[f"{NAME[gid]}·{suffix}"]["members"], [f"F-{gid.upper()}-AUTO"], suffix)
            # 手动优先：手动 → 自动 → 同地区节点（嵌套被忽略时的退路，也只用严的那条）
            self.assertEqual(g[f"{NAME[gid]}·手动优先"]["members"],
                             [f"{NAME[gid]}·手动", f"{NAME[gid]}·自动", f"F-{gid.upper()}-AUTO"])
        self.assertEqual(g["其他地区"]["members"], ["F-OTHER"])

    def test_quantumultx(self):
        pol = parsed("quantumultx")["policies"]
        for gid in SIX:
            self.assertEqual(pol[f"{NAME[gid]}·手动"]["params"]["server-tag-regex"], self.rx[gid])
            for suffix in self.AUTO_MODES:
                self.assertEqual(pol[f"{NAME[gid]}·{suffix}"]["params"]["server-tag-regex"], self.strict[gid], suffix)
        self.assertEqual(pol["其他地区"]["params"]["server-tag-regex"], self.rx["other"])
        self.assertEqual(pol["PayPal·美国固定"]["params"]["server-tag-regex"], self.rx["us"])

    def test_mihomo(self):
        for client in ("mihomo-profile", "mihomo-core"):
            g = {x["name"]: x for x in parsed(client)["proxy-groups"]}
            for gid in SIX:
                self.assertEqual(g[f"{NAME[gid]}·手动"]["filter"], self.rx[gid])
                for suffix in self.AUTO_MODES:
                    grp = g[f"{NAME[gid]}·{suffix}"]
                    self.assertEqual(grp["filter"], self.strict[gid])
                    self.assertNotIn("exclude-filter", grp, "排除条件已经在同一条正则里")
            self.assertEqual(g["其他地区"]["filter"], self.rx["other"])
            self.assertEqual(g["PayPal·美国固定"]["filter"], self.rx["us"])
            raw = text(client)
            for gid in SIX:      # 严的那条三个组共用：写一次，另外两处用 YAML 别名
                self.assertEqual(raw.count(f"&flt-{gid}-auto "), 1, gid)
                self.assertEqual(raw.count(f"*flt-{gid}-auto\n"), 2, gid)
                self.assertEqual(raw.count(self.strict[gid]), 1)
                self.assertEqual(raw.count(self.rx[gid]), 1)
            # 宽的那条：美国的被 PayPal 固定入口和“美国·手动”共用，其余只用一次
            self.assertEqual((raw.count("&flt-us "), raw.count("*flt-us\n")), (1, 1))
            self.assertEqual(raw.count("&flt-hk "), 0)

    def test_singbox_groups_nodes_at_build_time(self):
        e, auto = expected(), expected_auto()
        nodes = [{"type": "socks", "tag": n, "server": "127.0.0.1", "server_port": 1080} for n in e]
        conf = json.loads(emit_singbox.build(self.m, self.p, "1.14", nodes))
        ob = {o["tag"]: o for o in conf["outbounds"]}
        for gid in SIX + ["other"]:
            group = NAME[gid] if gid == "other" else NAME[gid] + "·手动"
            want = [n for n, groups in e.items() if gid in groups]
            self.assertEqual(ob[group]["outbounds"], want, group)
        for gid in SIX:
            want = [n for n, groups in auto.items() if gid in groups]
            self.assertEqual(ob[NAME[gid] + "·自动"]["outbounds"], want, gid)
            self.assertEqual(ob[NAME[gid] + "·自动"]["type"], "urltest")
        self.assertEqual(ob["PayPal·美国固定"]["outbounds"], [n for n, groups in e.items() if "us" in groups])
        for n, groups in e.items():
            if not groups:
                self.assertFalse(any(n in o.get("outbounds", []) for o in ob.values()), f"提示行 {n} 进了某个组")
        for entry in SAMPLES["manual_only"]:
            n = entry["name"]
            self.assertFalse(any(n in o.get("outbounds", []) for o in ob.values() if o["type"] == "urltest"),
                             f"说不清落地的 {n} 进了自动测速组")


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
        """两种实现（拼出来的正则、逐步判断）在全部样本上结果相同：宽、严两套都比。"""
        cl = regions.Classifier(spec())
        names = self.all_names()
        self.assertGreater(len(names), 20000)
        diff = []
        for n in names:
            v = cl.classify(n)
            if by_regex(n) != sorted(v.groups) or by_strict(n) != sorted(v.auto):
                diff.append((n, by_regex(n), by_strict(n), sorted(v.groups), sorted(v.auto)))
        self.assertEqual(diff[:20], [], f"共 {len(diff)} 个")

    def test_strict_is_the_unambiguous_part_of_loose(self):
        """严的那条 = 宽的那条里“只指向这一个地区”的部分：进严的一定进同一个地区宽的；一个名字最多进一个地区严的；
        宽的进了不止一个地区时，严的一个都不进。"""
        for n in self.all_names():
            a, b = by_regex(n), by_strict(n)
            self.assertLessEqual(len(b), 1, n)
            self.assertTrue(set(b) <= set(a), n)
            if len(a) > 1:
                self.assertEqual(b, [], n)

    def test_random_names_agree(self):
        """随机拼出来的名字（地区词、国旗、中转词、解锁词、箭头、提示行的词、常见标签随机组合，种子固定）：
        两种实现在宽、严两套上结果都相同，不是提示行的节点不丢，“其他地区”不和六个地区同时出现，
        严的那条只收只指向一个地区的。公开词表和带本地补充样例的词表各跑一遍。"""
        with open(os.path.join(ROOT, "source", "regions.yaml"), encoding="utf-8") as f:
            overlay_spec, errors = regions.parse(yaml.safe_load(f), OVERLAY["node_names"])
        self.assertEqual(errors, [])
        for label, sp, count, seed in (("公开词表", spec(), 30000, 20261004), ("带本地补充", overlay_spec, 10000, 7)):
            rnd = random.Random(seed)
            loose, strict = regions.compose_all(sp)
            rx = {k: re.compile(v) for k, v in loose.items()}
            rx_strict = {k: re.compile(v) for k, v in strict.items()}
            cl = regions.Classifier(sp)
            words = [x for w in sp.regions + [sp.other] for x in w.words + w.latin + [regions.flag(c) for c in w.flags]]
            flags = [regions.flag(c) for c in ("CN", "EU", "UN", "GB", "DE", "RU", "MO", "LV", "NU", "KP")]
            markers = (sp.after + sp.before + sp.arrows + sp.unlock
                       + ["Via", "VIA", "Latvia", "Bolivia", "avia", "Unlock", "Unlocked", "sunlock", "流媒体解锁"])
            info = sp.info_words + sp.info_colon + sp.info_latin + sp.info_always[:2]
            tags = ["01", "IPLC", "x0.5", "家宽", "|", "-", "_", " ", "  ", "[", "]", "(", ")", "【", "】", "·", "A", "a",
                    "Premium", "NF", "TR", "#", "/", ":", "：", ".", ",", "=", '"', "`", "流量", "群", "新", "港", "日", "美",
                    "｜", "丨", "（", "）", "时报", "流媒体", "０１"]
            seps = ["", "", " ", " ", "-", "_", "|", " | ", "  "]
            bad = []
            for _ in range(count):
                parts = []
                for _ in range(rnd.randint(1, 6)):
                    r = rnd.random()
                    tok = rnd.choice(words if r < 0.38 else flags if r < 0.47 else markers if r < 0.70
                                     else info if r < 0.76 else tags)
                    r = rnd.random()
                    parts += [tok.lower() if r < 0.15 else tok.upper() if r < 0.25 else tok, rnd.choice(seps)]
                name = "".join(parts[:-1]).strip()
                if not name:
                    continue
                got = sorted(g for g, r_ in rx.items() if r_.search(name))
                auto = sorted(g for g, r_ in rx_strict.items() if r_.search(name))
                v = cl.classify(name)
                if got != sorted(v.groups) or auto != sorted(v.auto):
                    bad.append((name, got, auto, sorted(v.groups), sorted(v.auto)))
                elif not got and v.basis not in ("info", "assign"):
                    bad.append((name, got, "没有进任何组"))
                elif "other" in got and len(got) > 1:
                    bad.append((name, got, "其他地区和别的地区同时出现"))
                elif len(auto) > 1 or not set(auto) <= set(got) or (len(got) > 1 and auto):
                    bad.append((name, got, auto, "严的那条不是宽的那条里只指向一个地区的部分"))
            self.assertEqual(bad[:10], [], f"{label}：共 {len(bad)} 个")

    def test_no_node_is_lost_and_other_is_exclusive(self):
        """不是提示行的节点至少进一个组；“其他地区”不和六个地区同时出现；这批样本里最多同时进两个地区。"""
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

    @staticmethod
    def all_regexes():
        m = model_and_plan()[0]
        return ([("宽 " + k, v) for k, v in m.node_regexes().items()]
                + [("严 " + k, v) for k, v in m.node_regexes_strict().items()])

    def test_no_character_with_special_meaning(self):
        self.assertEqual(len(self.all_regexes()), 13)
        for gid, rx in self.all_regexes():
            for bad in (",", '"', "`", "=", " ", "\n", "\t"):
                self.assertNotIn(bad, rx, f"{gid} 含 {bad!r}")
            self.assertTrue(rx.startswith("(?i)^") and rx.endswith(".*$"), gid)

    def test_only_constructs_every_engine_supports(self):
        for gid, rx in self.all_regexes():
            for bad in ("(?=", "(?<=", "(?>", "(?P", "\\b", "\\d", "\\w", "\\p", "\\u", "*+", "++", "?+", "{"):
                self.assertNotIn(bad, rx, f"{gid} 用了 {bad}")
            # 否定后顾必须定长：Python 的 re 遇到变长后顾会直接报错
            re.compile(rx)

    def test_size_is_bounded(self):
        for gid, rx in self.all_regexes():
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
        self.assertIn("ICU：全部按时结束", r.stdout, "长名字那一项也要在 ICU 上跑过")

    def test_long_names_do_not_blow_up(self):
        """回溯失控：正则写得不好时，匹配时间会随名字长度成倍增长（客户端上表现为刷新节点时卡死）。
        写“跳过解锁说明”那一段时真的出过一次——两个分支能匹配同一个字符，三十来个字符的名字就要算上十亿步。
        这里拿几百个字符的怪名字（“解锁”、地区词、国旗、括号各自重复很多遍）去试 13 条正则：
        每次匹配都要很快结束，结果还要和逐步判断相同。放在子进程里并带超时：失控时是这一项失败，而不是测试卡死。"""
        cmd = [sys.executable, os.path.join(ROOT, "tools", "check_icu.py"), "--public", "--long-names-only"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        except subprocess.TimeoutExpired:
            self.fail("节点筛选正则在长名字上 5 分钟没有算完：有回溯失控的写法（检查 generator/regions.py 里带 * 的分组，"
                      "它的各个分支不能匹配同一个字符）")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("全部按时结束，分组与逐步判断完全一致", r.stdout)


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

    def test_yielding_only_to_country_level_words(self):
        """审核 F05：香港让位是机场常见的命名规则，但不该对宣传语里随便一个城市词都生效。
        名字里有“香港 / HK”这样国名一级的词、别的地区只有城市一级的词时，不让位：两边都进手动组，都不进自动类组。
        只有单个字的“港”或运营商、区名（深港、HKT、九龙）时照旧让位——“关西空港”里也有“港”字。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (("香港 01 纽约时报", ["hk", "us"], []), ("香港-东京 01", ["hk", "jp"], []),
                               ("HK-Tokyo 01", ["hk", "jp"], []), ("Hong Kong Seoul 01", ["hk", "kr"], []),
                               ("东京 香港 01", ["hk", "jp"], []),
                               ("香港-日本 01", ["jp"], ["jp"]), ("香港 东京 日本 01", ["jp"], ["jp"]),      # 有国名：让
                               ("香港 日本 纽约 01", ["jp", "us"], []),                                  # 让给日本；日本和美国说不清
                               ("深港专线 东京 01", ["jp"], ["jp"]), ("关西空港 大阪 01", ["jp"], ["jp"]),   # 只有“港”：让
                               ("HKT 东京 01", ["jp"], ["jp"]), ("九龙 东京 01", ["jp"], ["jp"]),
                               ("香港中转 东京 01", ["jp"], ["jp"]), ("香港 → 东京 01", ["jp"], ["jp"]),     # 香港不在落地位置
                               ("香港 东京中转 01", ["hk"], ["hk"]),                                     # 东京不在落地位置
                               ("香港 01 纽约时报解锁", ["hk"], ["hk"]),
                               ("🇭🇰 东京 01", ["hk"], ["hk"]), ("🇯🇵 香港 东京 01", ["jp"], ["jp"]),        # 有国旗按国旗
                               ("香港 伦敦 东京 01", ["other"], [])):                                    # 别国的城市词照旧
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)
        self.assertIn("香港不让位", "；".join(cl.classify("香港 01 纽约时报").notes))

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

    def test_info_line_needs_more_than_a_word(self):
        """审核 F02：名字里出现“官网”“网站”“Traffic”这类词，不再直接当成提示行。三种情况才算。"""
        # 1. 面板的固定写法：任何位置
        self.check([("剩余流量：10G | 香港", []), ("🇭🇰 套餐到期：2026-12-31", []), ("距离下次重置剩余：3 天", [])])
        # 2. “词 + 冒号”，而且这个词前面没有数字和竖线
        self.check([("官网：hk.example.com", []), ("官网 : hk.example.com", []), ("最新网址:us.example.com", []),
                    ("公告：香港节点维护中", []), ("Traffic: 1GB (US)", []), ("Expires: 2026 JP", []),
                    ("香港 01 | 官网：abc.com", ["hk"]), ("香港 01 官网：abc.com", ["hk"]), ("香港 | TG群：@abc", ["hk"]),
                    ("香港 ０１ 官网：abc.com", ["hk"])])
        # 3. 有这类词、而且整个名字里没有任何地区字样
        self.check([("官网 example.com", []), ("请更新订阅", []), ("Unlimited Traffic", []), ("套餐 VIP3", []),
                    ("日本 01 全网站解锁", ["jp"]), ("Japan 01 | Unlimited Traffic", ["jp"]), ("美国 01 ChatGPT官网可用", ["us"]),
                    ("V3套餐 香港 01", ["hk"]), ("英国 01 官网可用", ["other"]), ("🇬🇧 01 官网可用", ["other"]),
                    ("🇨🇳 官网可用", []), ("经日本 官网", ["jp"])])
        # “群”“流量”只在带冒号时才算
        self.check([("群：12345", []), ("流量:1G", []), ("大流量 01", ["other"]), ("群岛 01", ["other"])])

    def test_unlock_clause(self):
        """审核 F03：“解锁”后面的地名不算落地，中间隔着冒号、多个空格也一样；说明到下一个竖线或右括号为止。"""
        self.check([("日本01 | 解锁 美国", ["jp"]), ("日本01 | 解锁: 美国", ["jp"]), ("日本01 | 解锁：美国", ["jp"]),
                    ("日本01 | 解锁   美国", ["jp"]), ("日本01 | 解锁-美国", ["jp"]), ("日本01 | 解锁美国、韩国、台湾", ["jp"]),
                    ("日本01 | 解鎖 🇺🇸", ["jp"]), ("JP 01 unlock US", ["jp"]), ("JP 01 Unlocked: US/KR", ["jp"]),
                    ("JP 01 sunlock US", ["jp", "us"]),                  # sunlock 不是 unlock
                    ("【解锁美国】日本 01", ["jp"]), ("(解锁美国) 日本 01", ["jp"]), ("解锁美国 | 日本 01", ["jp"]),
                    ("日本 01 | 解锁美国(奈飞) 韩国", ["jp"]),             # 说明里又开了括号：管到名字结尾
                    ("解锁日本 01", ["jp"]), ("解锁日本 韩国", ["jp", "kr"])])
        # 同一段里后面跟着“解锁”的词也不算
        self.check([("香港 01 纽约时报解锁", ["hk"]), ("香港 01 美国解锁", ["hk"]), ("香港 01 美国 解锁", ["hk"]),
                    ("香港 01 美国Netflix解锁", ["hk"]), ("香港 01 美国/日本流媒体解锁", ["hk"]),
                    ("美国-日本解锁 01", ["us"]), ("美国_日本解锁 01", ["us"]), ("美国|日本解锁 01", ["us"])])
        cl = regions.Classifier(spec())
        self.assertEqual(cl.classify("解锁日本 韩国").auto, [], "两个地区都在说明里：说不清，只进手动")
        self.assertEqual(cl.classify("【解锁美国】日本 01").auto, ["jp"])

    def test_country_name_beats_foreign_city(self):
        """审核 F05：六个地区的国名和别国的城市词同时出现 → 按国名，但只进手动组；别国的国名仍然压过六个地区的词。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (("美国 奥克兰 01", ["us"], []), ("US Dublin 01", ["us"], []), ("US Oakland 01", ["us"], ["us"]),
                               ("韩国 伦敦 01", ["kr"], []), ("洛杉矶 奥克兰 01", ["other"], []),      # 城市对城市：别国的赢
                               ("美国 新西兰 奥克兰 01", ["other"], []), ("美国 英国 01", ["other"], []),
                               ("香港 奥克兰 01", ["other"], []),                                     # 让位地区的国名不算
                               ("美国 01 | 伦敦中转", ["us"], ["us"]), ("🇺🇸 奥克兰 01", ["us"], ["us"])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)

    def test_strict_and_loose(self):
        """审核 F04：每个地区两条筛选。说不清的只在宽的那条里。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (("日本 01", ["jp"], ["jp"]), ("日本-美国 01", ["jp", "us"], []), ("🇯🇵 Tokyo 01 🇺🇸", ["jp", "us"], []),
                               ("香港-美国 01", ["us"], ["us"]),                      # 香港让位不算说不清
                               ("美国 01 | 日本中转", ["us"], ["us"]),                # 中转位置上的不算对手
                               ("日本中转 01", ["jp"], []),                           # 只提到一个地区，但不在落地位置（审核 r9 F01）
                               ("香港中转 日本中转 01", ["hk", "jp"], []),            # 提到两个、都不在落地位置
                               ("香港 01 | 日本中转", ["hk"], ["hk"]), ("🇭🇰🇯🇵 01", ["jp"], ["jp"]),
                               ("英国 01", ["other"], []), ("Premium 01", ["other"], []), ("剩余流量：1G", [], [])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)

    def test_region_named_only_in_a_non_landing_position_is_manual_only(self):
        """审核 r9 的 F01：名字里唯一的地区词在“解锁”说明里，或者在中转 / 入口位置上——宽的那条仍然收（方便手选），
        严的那条不收：自动 / 故障转移 / 负载均衡不拿它当落地依据。旁边放着正常写法作对照。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (("IEPL 01 Unlock US", ["us"], []), ("Premium 01 | 解锁美国", ["us"], []), ("日本中转 01", ["jp"], []),
                               ("美国 01", ["us"], ["us"]), ("日本 01", ["jp"], ["jp"]),                      # 审核方给的对照
                               ("HK Relay 01", ["hk"], []), ("via Japan 01", ["jp"], []), ("经日本 01", ["jp"], []),
                               ("日本入口 01", ["jp"], []), ("日本→ 01", ["jp"], []),
                               ("解锁美国 01", ["us"], []), ("美国解锁 01", ["us"], []),
                               ("香港中转 01", ["hk"], []),                                                   # 让位地区也一样
                               ("中转 香港 01", ["hk"], ["hk"]), ("香港-01-中转", ["hk"], ["hk"]),              # “中转”没有接在地名后面
                               ("香港 01 | 中转", ["hk"], ["hk"]), ("香港 | 中转 | 01", ["hk"], ["hk"]),        # 竖线另起一段
                               ("🇺🇸 01 Unlock US", ["us"], ["us"]),                                          # 国旗在落地位置
                               ("香港 01 | 解锁美国", ["hk"], ["hk"]),                                         # 名字里另有落地
                               ("解锁日本 韩国", ["jp", "kr"], []),                                            # 两个都在说明里
                               # 国旗只在说明里：和文字写的“解锁美国”一样，只进手动组
                               # （2026-10-05 自查之前，不在落地位置的国旗不算“提到了这个地区”，这个名字掉进“其他地区”）
                               ("01 | 解锁 🇺🇸", ["us"], [])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)
        notes = "；".join(cl.classify("日本中转 01").notes)
        self.assertIn("不在落地位置", notes)
        self.assertIn("说不清落地", notes)
        self.assertIn("只进日本的手动组", notes)

    def test_joiner_between_region_and_transit_word_does_not_matter(self):
        """地名后面接着中转词时，中间隔的是空格、连字符、下划线，还是间隔号、句点、斜杠、破折号，结果都一样
        （2026-10-05：以前只认空格，“香港 中转 01”只进手动组，“香港-中转-01”却进自动类的组）。
        有落地的“甲 转 乙”同样不看连接符。"""
        cl = regions.Classifier(spec())
        for template, loose, auto in (("香港{}中转{}01", ["hk"], []), ("HK{}Relay{}01", ["hk"], []), ("台湾{}中继{}A", ["tw"], []),
                                      ("日本{}入口{}01", ["jp"], []), ("JP{}Transit{}02", ["jp"], []),
                                      ("日本{}中转{}美国{}01", ["us"], ["us"]), ("日本{}转{}美国{}01", ["us"], ["us"]),
                                      ("香港{}转{}日本{}01", ["jp"], ["jp"])):
            for joiner in (" ", "-", "_", " - ", "  ", "·", "・", ".", "/", "—", "–", " · ", "——"):
                n = template.replace("{}", joiner)
                self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
                v = cl.classify(n)
                self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)
        # 不隔任何东西的写法也一样（英文词之间必须有分隔，所以只看中文的）
        for n, loose, auto in (("香港中转01", ["hk"], []), ("日本中转美国01", ["us"], ["us"])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
        # 竖线和括号不是连接符：它们另起一段，地名仍在落地位置
        for n in ("香港|中转|01", "香港｜中转｜01", "香港 [中转] 01", "香港(中转)01", "香港（中转）01", "香港【中转】01"):
            self.assertEqual((by_regex(n), by_strict(n)), (["hk"], ["hk"]), n)

    def test_joiner_before_region_and_before_unlock_does_not_matter(self):
        """2026-10-05 自查：via / 经 和它后面的地名之间、地名和它后面的“解锁”之间，隔一个空格、连字符还是下划线，
        结果都一样。以前这两处只认空格：“via-HK-01”“日本-解锁-01”会进自动类的组，
        “香港 01 美国-解锁”更会让香港让位、进美国的自动组。"""
        cl = regions.Classifier(spec())
        cases = []
        for gap in ("", " ", "-", "_"):
            cases += [(f"经{gap}日本 01", ["jp"], []), (f"經{gap}香港 01", ["hk"], []),
                      (f"经{gap}日本 美国 01", ["us"], ["us"]), (f"IEPL 经{gap}🇯🇵 美国 01", ["us"], ["us"])]
        for gap in (" ", "-", "_"):                          # 英文的 via 和英文地名之间必须有分隔
            cases += [(f"via{gap}HK 01", ["hk"], []), (f"VIA{gap}Tokyo{gap}01", ["jp"], []), (f"IEPL{gap}via{gap}JP 01", ["jp"], []),
                      (f"via{gap}HK 日本 01", ["jp"], ["jp"]), (f"via{gap}🇯🇵 美国 01", ["us"], ["us"])]
        for gap in ("", " ", "-", "_", " - "):
            cases += [(f"日本{gap}解锁 01", ["jp"], []), (f"美国{gap}解鎖{gap}01", ["us"], []), (f"香港 01 美国{gap}解锁", ["hk"], ["hk"]),
                      (f"新加坡 01 纽约时报{gap}解锁", ["sg"], ["sg"])]
        for gap in (" ", "-", "_"):
            cases += [(f"JP{gap}Unlock 01", ["jp"], []), (f"HK 01 US{gap}unlock", ["hk"], ["hk"])]
        # 隔着两个以上的连接符、或者隔着别的词，就不算紧挨着了（via / 经 只管紧跟在后面的那个词）
        cases += [("via - HK 01", ["hk"], ["hk"]), ("经  日本 01", ["jp"], ["jp"]), ("Avia-日本 美国 01", ["jp", "us"], [])]
        for n, loose, auto in cases:
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)

    def test_flags_follow_the_same_position_rules_as_words(self):
        """2026-10-05 自查：国旗算不算落地，和文字用同一套条件。以前国旗只看“在不在解锁说明里、前面是不是 via、后面有没有箭头”，
        不看它后面接的是什么：“🇯🇵中转 01”进日本的自动组（文字写的“日本中转 01”不进），“IEPL 01 🇺🇸解锁”进美国的自动组
        （“IEPL 01 美国解锁”不进），“🇯🇵转🇭🇰 01”因为香港让位进了日本的自动组。一串连写的国旗按整串算。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (
                # 后面接着中转词（隔着连接符也算）
                ("🇯🇵中转 01", ["jp"], []), ("🇯🇵 中转 01", ["jp"], []), ("🇭🇰-Relay-01", ["hk"], []), ("🇸🇬·中继·01", ["sg"], []),
                ("🇺🇸 入口 01", ["us"], []), ("🇹🇼转 01", ["tw"], []),
                ("🇯🇵转🇭🇰 01", ["hk"], ["hk"]), ("🇺🇸转🇯🇵 01", ["jp"], ["jp"]), ("🇭🇰 中转 🇯🇵 01", ["jp"], ["jp"]),
                ("🇯🇵中转 美国 01", ["us"], ["us"]), ("🇬🇧中转 🇯🇵 01", ["jp"], ["jp"]),
                ("🇭🇰🇯🇵中转 01", ["hk", "jp"], []), ("🇨🇳🇯🇵 Relay 01", ["jp"], []),                    # 整串都不算
                # 同一段里后面跟着“解锁”
                ("IEPL 01 🇺🇸解锁", ["us"], []), ("IEPL 01 🇺🇸 Unlock", ["us"], []), ("IEPL 01 🇺🇸-解锁", ["us"], []),
                ("香港 01 | 🇺🇸解锁", ["hk"], ["hk"]), ("🇭🇰 香港 01 | 🇺🇸🇯🇵 解锁", ["hk"], ["hk"]),
                ("🇭🇰 01 🇺🇸Netflix解锁", ["hk"], ["hk"]),
                # 原来就有的三条：解锁说明里、via 后面、箭头前面
                ("01 | 解锁 🇺🇸", ["us"], []), ("via 🇯🇵 01", ["jp"], []), ("🇭🇰→ 01", ["hk"], []), ("🇭🇰→🇯🇵 01", ["jp"], ["jp"]),
                # 国旗后面不是中转词：照常按国旗
                ("🇯🇵 01", ["jp"], ["jp"]), ("🇯🇵 日本中转 01", ["jp"], ["jp"]), ("🇯🇵 IEPL 中转 01", ["jp"], ["jp"]),
                ("🇯🇵 01 中转", ["jp"], ["jp"]), ("🇯🇵 | 中转 | 01", ["jp"], ["jp"]), ("中转 🇯🇵 01", ["jp"], ["jp"]),
                ("🇺🇸 美国 01 解锁流媒体", ["us"], ["us"]), ("🇺🇸 01 | 解锁 Netflix", ["us"], ["us"]),
                # 其他国家的国旗同样处理
                ("🇬🇧中转 01", ["other"], []), ("🇬🇧 中转 日本 01", ["jp"], ["jp"]), ("🇬🇧 日本 01", ["other"], []),
                ("🇩🇪解锁 | 香港 01", ["hk"], ["hk"])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)
        notes = "；".join(cl.classify("🇯🇵中转 01").notes)
        self.assertIn("国旗 🇯🇵", notes)
        self.assertIn("只进日本的手动组", notes)

    def test_region_flag_outside_a_landing_position_still_counts_as_a_mention(self):
        """国旗不在落地位置、名字里又没有别的落地时，节点进这面国旗所属地区的手动组（和文字一样），不掉进“其他地区”，
        也不同时出现在两边。名字里另有落地时，这面国旗不起作用。"""
        cl = regions.Classifier(spec())
        for n, loose in (("🇯🇵中转 01", ["jp"]), ("🇯🇵中转 🇺🇸中转 01", ["jp", "us"]), ("🇯🇵中转 香港中转 01", ["hk", "jp"]),
                         ("🇯🇵中转 英国中转 01", ["jp"]), ("官网 🇯🇵中转", ["jp"]),
                         ("🇯🇵中转 伦敦 01", ["other"]), ("🇯🇵中转 英国 01", ["other"]), ("🇯🇵中转 🇬🇧 01", ["other"]),
                         ("🇯🇵中转 香港 01", ["hk"]), ("🇯🇵中转 🇭🇰 01", ["hk"]), ("🇨🇳中转 01", ["other"])):
            self.assertEqual(by_regex(n), loose, n)
            self.assertEqual(sorted(cl.classify(n).groups), loose, n)
        self.assertEqual(cl.classify("🇯🇵中转 01").basis, "flag")
        self.assertEqual(cl.classify("🇬🇧中转 01").basis, "none")

    def test_single_character_hk_word_is_not_counted_inside_a_longer_word(self):
        """2026-10-05 自查：单个字的“港”出现在“香港”、专线简称“港日 / 港韩 / 港美”里时不单独算一次。
        以前“经香港 01”里“香港”在“经”后面不算落地，“港”却因为前面是“香”照样算；“港日中转 01”里“港日”后面接着中转词
        不算落地，“港”却因为后面是“日”照样算——两个都进了香港的自动组，后一个还进不了日本的手动组。"""
        cl = regions.Classifier(spec())
        for n, loose, auto in (("经香港 01", ["hk"], []), ("via 香港 01", ["hk"], []), ("经香港 日本 01", ["jp"], ["jp"]),
                               ("港日中转 01", ["jp"], []), ("港韩 Relay 01", ["kr"], []), ("港韓-中转-01", ["kr"], []),
                               ("港美入口 01", ["us"], []), ("解锁港日 01", ["jp"], []), ("港日→ 01", ["jp"], []),
                               ("港日 01", ["jp"], ["jp"]), ("港美 IEPL 01", ["us"], ["us"]), ("香港 01", ["hk"], ["hk"]),
                               # “港”单独出现、或者在别的字后面，照旧
                               ("深港 IPLC 01", ["hk"], ["hk"]), ("港 01", ["hk"], ["hk"]), ("深港中转 01", ["hk"], []),
                               ("港转 01", ["hk"], []), ("深港专线 东京 01", ["jp"], ["jp"]), ("关西空港 大阪 01", ["jp"], ["jp"])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (loose, auto), n)
        # 词表里所有带“港”字的词，都要在“港”那条片段的排除条件里：加了新词（比如“港新”）而没有改片段，这里会失败
        s = spec()
        hk = s.region("hk")
        gang = [p for p in hk.patterns if "港" in p]
        self.assertEqual(len(gang), 1, "香港的词表里应当只有一条带条件的“港”")
        self.assertNotIn("港", hk.words, "单个字的“港”要写成带条件的片段，不能放回 words")
        longer = [w for r in s.regions + [s.other] for w in r.words if "港" in w]
        self.assertGreaterEqual(len(longer), 5)
        for w in longer:
            self.assertIsNone(re.search(gang[0], w),
                              f"词表里的“{w}”含“港”字：把它前后的字加进 source/regions.yaml 里“港”那条片段的排除条件")

    def test_words_nested_in_longer_words_are_all_reviewed(self):
        """一个词整个出现在另一个更长的词里时，短的那个会按它自己前后的字来判断“在不在落地位置”，可能和长的那个结论不同
        （上一项的“港”就是这样出的错）。这里把词表里所有这样的情形列出来，和逐个看过的清单比：词表改动产生了新的嵌套时会失败，
        提醒看一眼它会不会出同样的问题。清单里剩下的这几对，短词都是长词的后半截，长词都是“其他国家”的国名
        （North Korea、South America……）：
          - 长词在落地位置时，名字归其他地区，短词不起作用（“North Korea 01”）；
          - 长词后面接着中转词时，两个都不算落地，名字按“提到了韩国”进韩国的手动组，不进自动（“North Korea 中转 01”；
            本来该进其他地区，两边都是纯手动）；
          - 长词前面是 via / 经 时，短词前面隔着“North”，会被单独算成落地（“via North Korea 01”进韩国的自动组）。
            这是“via / 经 只管紧跟在后面的那个词”的一种，和“via South Korea 01”一起记在 docs/06。"""
        s = spec()
        cl = regions.Classifier(s)
        items = [(w.id, x, re.compile(re.escape(x), re.I)) for w in s.regions + [s.other] for x in w.words]
        items += [(w.id, x, cl._latin_rx(x)) for w in s.regions + [s.other] for x in w.latin]
        found = set()
        for ia, a, rx in items:
            for ib, b, _ in items:
                if (ia, a) != (ib, b) and any(m.end() - m.start() < len(b) for m in rx.finditer(b)):
                    found.add((f"{ia}:{a}", f"{ib}:{b}"))
        reviewed = {("kr:Korea", "other:North Korea"),
                    ("us:America", "other:North America"), ("us:America", "other:South America"),
                    ("us:America", "other:Latin America"), ("us:America", "other:Central America"),
                    ("other:Africa", "other:South Africa"), ("other:俄罗斯", "other:白俄罗斯"), ("other:柏林", "other:都柏林")}
        self.assertEqual(found, reviewed)
        for n, loose, auto in (("North Korea 01", ["other"], []), ("North Korea 中转 01", ["kr"], []),
                               ("via North Korea 01", ["kr"], ["kr"]), ("South America Relay 01", ["us"], [])):
            self.assertEqual((by_regex(n), by_strict(n)), (loose, auto), n)

    def test_every_region_word_and_flag_in_a_non_landing_position_is_manual_only(self):
        """审核 r9 的 F01 说的是一类名字，不是三个例子。这里把六个地区词表里的每个词、每面国旗，套进每一种“不在落地位置”的写法
        （后面接中转词 × 各种连接符、前面是 via / 经、后面有箭头、在解锁说明里、同一段里后面跟着解锁），逐个确认：
        严的那条不收，宽的那条收进这个地区，两种实现结果相同。"""
        s = spec()
        cl = regions.Classifier(s)
        templates = []
        for word in ("中转", "中繼", "转", "入口", "Relay", "transit"):
            templates += ["{w}" + j + word + " 01" for j in ("", " ", "-", "_", "·", ".", "/", "—", " - ")]
        for word in ("via", "VIA", "经", "經"):
            templates += [lead + word + gap + "{w} 01" for gap in (" ", "-", "_") for lead in ("", "IEPL ")]
        templates += ["经{w} 01", "IEPL 經{w} 01"]
        templates += ["{w}" + gap + arrow + " 01" for arrow in s.arrows for gap in ("", " ")]
        for word in ("解锁", "解鎖", "Unlock"):
            templates += [word + gap + "{w} 01" for gap in (" ", ": ", "：", "-")]
            templates += ["Premium 01 | " + word + " {w}", "Premium 01 [" + word + " {w}]"]
            templates += ["{w}" + gap + word + " 01" for gap in (" ", "-", "_")]
        templates += ["解锁{w} 01", "{w}解锁 01", "01 {w}解鎖"]
        self.assertGreaterEqual(len(templates), 100)
        bad, count = [], 0
        for r in s.regions:
            items = r.words + r.latin + [regions.flag(c) for c in r.flags] + (["港"] if r.id == "hk" else [])
            for w in items:
                for t in templates:
                    if w.isascii() and re.search(r"[A-Za-z]\{w\}|\{w\}[A-Za-z]", t):
                        continue                    # 英文词紧挨着英文字母就不是这个词了
                    n = t.format(w=w)
                    count += 1
                    got, auto = by_regex(n), by_strict(n)
                    v = cl.classify(n)
                    if auto or r.id not in got or got != sorted(v.groups) or auto != sorted(v.auto):
                        bad.append((n, got, auto, sorted(v.groups), sorted(v.auto)))
        self.assertGreater(count, 30000)
        self.assertEqual(bad[:20], [], f"共 {len(bad)} 个（节点名, 宽, 严, 逐步判断的宽, 严）")
        # via / 经 只管紧跟在后面的那个词：“经深港 01”里“港”前面隔着“深”，管不到（记在 node_names.yaml 的 known_auto_limits）
        self.assertEqual((by_regex("经深港 01"), by_strict("经深港 01")), (["hk"], ["hk"]))

    def test_explanations_are_human_readable(self):
        cl = regions.Classifier(spec())
        v = cl.classify("美国 01 | 深港中转")
        self.assertEqual(v.groups, ["us"])
        self.assertIn("香港让位", "；".join(v.notes))
        v = cl.classify("Premium 01")
        self.assertEqual((v.groups, v.basis), (["other"], "none"))
        v = cl.classify("日本-美国 01")
        self.assertIn("说不清落地", "；".join(v.notes))
        self.assertIn("只进", "；".join(v.notes))
        v = cl.classify("美国 奥克兰 01")
        self.assertIn("其他国家的城市词“奥克兰”", "；".join(v.notes))
        v = cl.classify("官网：hk.example.com")
        self.assertEqual((v.groups, v.basis), ([], "info"))
        self.assertIn("冒号", "；".join(v.notes))
        self.assertEqual(cl.classify("美国 01 ChatGPT官网可用").weak, "官网", "报告里要能列出“含提示词但按节点处理”的名字")


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
        rxs, strict = m.node_regexes(), m.node_regexes_strict()
        cl = regions.Classifier(m.region_spec)
        self.assertGreaterEqual(len(OVERLAY["expect"]), 15)
        for e in OVERLAY["expect"]:
            n, want = e["name"], sorted(e["groups"])
            auto = sorted(e.get("auto", [g for g in want if g != "other"]))      # 指定了地区的节点两条都进
            self.assertEqual(by_regex(n, rxs), want, n)
            self.assertEqual(by_strict(n, strict), auto, n)
            v = cl.classify(n)
            self.assertEqual((sorted(v.groups), sorted(v.auto)), (want, auto), n)
        for rx in list(rxs.values()) + list(strict.values()):
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
            self.assertNotIn("按节点处理", out, "这批名字里没有含提示词的真节点")
            for needle in ("台湾 1（1）", "美国 3（2）", "日本 1（0）", "没认出地区", "Premium 01", "说不清落地，只进手动组",
                           "日本-美国 05 → 日本、美国（只进手动组）",
                           "按中转 / 让位规则判断", "香港让位", "当成提示行", "面板的固定写法“剩余流量”", "落地在其他国家"):
                self.assertIn(needle, out)
            rc, out = self.run_tool(p, "--public", "--all", "--out", os.path.join(d, "r.txt"))
            self.assertIn("🇨🇳 台湾 07 家宽 → 台湾", out)
            with open(os.path.join(d, "r.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), out)
        finally:
            shutil.rmtree(d)

    def test_report_lists_kept_nodes_with_info_words(self):
        """名字里有提示行常用的词、但带地区字样的真节点：进组，并在报告里单独列出来（审核 F02）。"""
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "names.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(["日本 01 全网站解锁", "美国 01 ChatGPT官网可用", "官网 hk.example.com", "官网：hk.example.com",
                                   "美国 奥克兰 01"]) + "\n")
            rc, out = self.run_tool(p, "--public")
            self.assertEqual(rc, 0)
            for needle in ("日本 1（1）", "美国 2（1）", "香港 1（1）", "不进任何组 1",
                           "名字里有提示行常用的词，但带地区字样，按节点处理】3 个",
                           "日本 01 全网站解锁 → 日本（含“网站”）", "官网 hk.example.com → 香港（含“官网”）",
                           "官网：hk.example.com（“官网”后面紧跟冒号",
                           "美国 奥克兰 01 → 美国（只进手动组）"):
                self.assertIn(needle, out)
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

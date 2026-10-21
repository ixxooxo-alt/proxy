"""简易版（2026-10-21，docs/10-简易版框架.md）：每个地区一个组、里面直接是这个地区的节点，自己选，不自动换；
“国外默认”是七个地区再接全部节点；mihomo、sing-box 的境外 DNS 和规则下载另走内部的“境外DNS”组。
和完整版并存，文件名带 -simple，Loon / Quantumult X / Stash 也各有严格版。

这里查简易版自己的设计：
  1. 和对应的完整版只差在说好的地方（策略组、文件头的说明；mihomo、sing-box 另有境外 DNS 那几处），规则完全相同；
  2. 策略组的结构：期望按 docs/10 人工写在下面（GROUP_NAMES 等），不从生成结果反推；
  3. “全部节点”那条正则和“宽的七条取并集”完全等价，“境外DNS”的节点正好是六个地区严筛选的并集；
  4. 写盘前检查（generator/verify.py）拦得住简易版特有的几种坏写法，认不出的配置文件也不再悄悄跳过。
按规则走到哪里由 test_routing.py、test_real_data.py、test_strict.py 等照常查（helpers 把简易版算进了 CLIENT_FILES），
这里不重复。"""
import copy
import json
import random
import re
import unittest

import yaml

from helpers import (CLIENT_FILES, FULL_CLIENTS, FULL_OF, ROOT, SIMPLE_CLIENTS, SIMPLE_FILES, build, family, load_yaml,
                     model_and_plan, outputs, parsed, simple_spec, text)
from generator import emit_singbox, emit_stash, regions, verify
from generator.groups import NodeFilter
from generator.model import SourceError, _check_simple
from generator.nodes import convert
from test_regions import country_names, expected as sample_expected, reference, word_names

# ---- 按 docs/10 人工写的期望 ----
REGIONS = ["香港", "日本", "韩国", "台湾", "新加坡", "美国"]
OTHER = "其他地区"
FD = "国外默认"
FD_MEMBERS = ["日本", "香港", "韩国", "台湾", "新加坡", "美国", "其他地区"]      # 首次默认日本（和完整版一样）
DNS_GROUP = "境外DNS"
REGION_IDS = {"香港": "hk", "日本": "jp", "韩国": "kr", "台湾": "tw", "新加坡": "sg", "美国": "us", "其他地区": "other"}
LOON_FILTER = {"香港": "F-HK", "日本": "F-JP", "韩国": "F-KR", "台湾": "F-TW", "新加坡": "F-SG", "美国": "F-US", "其他地区": "F-OTHER"}
WITH_DNS_GROUP = ("mihomo", "singbox")         # 只有这两端的 DNS 经代理，才有“境外DNS”
SIMPLE_INTERVAL = 3600                          # 使用者 2026-10-21 定的“1 小时检查一次”
FULL_INTERVAL = 300
NODE_SAMPLES = load_yaml("node_samples.yaml")["proxies"]
OVERLAY = load_yaml("local_overlay_sample.yaml")


def group_names(client):
    """简易版应有的组：业务组（和完整版一样，sing-box 没有“广告拦截”）、PayPal·美国固定、六个地区、其他地区，
    mihomo、sing-box 再加“境外DNS”。"""
    m, _ = model_and_plan()
    names = [g.name for g in m.groups if not (family(client) == "singbox" and g.name == "广告拦截")]
    names += ["PayPal·美国固定"] + REGIONS + [OTHER]
    if family(client) in WITH_DNS_GROUP:
        names.append(DNS_GROUP)
    return names


def norm_groups(client):
    """{组名: {"kind": select / url-test …, "members": 写明的成员, "filter": 节点筛选（正则或 Loon 的筛选名；没有为 None）, "raw"}}"""
    c = parsed(client)
    fam = family(client)
    out = {}
    if fam in ("mihomo", "stash"):
        for g in c["proxy-groups"]:
            out[g["name"]] = {"kind": g["type"], "members": list(g.get("proxies") or []), "filter": g.get("filter"), "raw": g}
    elif fam == "singbox":
        groups = {o["tag"] for o in c["outbounds"] if o["type"] in ("selector", "urltest")}
        for o in c["outbounds"]:
            if o["type"] in ("selector", "urltest"):
                mem = list(o["outbounds"])
                out[o["tag"]] = {"kind": {"selector": "select", "urltest": "url-test"}[o["type"]],
                                 "members": [x for x in mem if x in groups or x == "DIRECT"],
                                 "filter": [x for x in mem if x not in groups and x != "DIRECT"] or None, "raw": o}
    elif fam == "loon":
        for name, g in c["groups"].items():
            flt = [x for x in g["members"] if x in c["filters"]]
            out[name] = {"kind": g["type"], "members": [x for x in g["members"] if x not in c["filters"]],
                         "filter": flt[0] if flt else None, "raw": g}
            if len(flt) > 1:
                raise AssertionError(f"{client} {name} 有不止一条筛选")
    else:
        for name, g in c["policies"].items():
            out[name] = {"kind": {"static": "select", "url-latency-benchmark": "url-test", "available": "fallback",
                                  "dest-hash": "load-balance"}[g["type"]],
                         "members": [{"direct": "DIRECT", "reject": "REJECT"}.get(x, x) for x in g["members"]],
                         "filter": g["params"].get("server-tag-regex"), "raw": g}
    return out


def strip_simple_header(t: str) -> str:
    """去掉简易版文件头多出的几行，并把“切回标准版 xxx-simple”换成完整版的文件名：剩下的应该和完整版逐字相同。"""
    lines = [ln for ln in t.splitlines() if not ln.startswith(("# 这是【简易版】", "# “国外默认”是七个地区", "# 境外 DNS 和规则数据的下载走"))]
    return "\n".join(lines).replace("-simple.", ".")


def ini_sections(t: str):
    """Loon / Quantumult X：[(段名, [行])]，段之前的文件头记作段名 ""。注释行、空行都保留。"""
    out = [("", [])]
    for ln in t.splitlines():
        m = re.match(r"^\[(.+)\]$", ln.strip())
        if m:
            out.append((m.group(1), []))
        else:
            out[-1][1].append(ln)
    return out


class Registered(unittest.TestCase):
    def test_every_full_output_has_a_simple_one(self):
        """十份完整版配置各有一份简易版，文件名在客户端名后面加 -simple；build.py 和测试登记的是同一批。"""
        simple_rel = sorted(rel for rel in build.PUBLIC_OUTPUTS if "-simple" in rel)
        self.assertEqual(simple_rel, sorted(SIMPLE_FILES.values()))
        self.assertEqual(len(SIMPLE_CLIENTS), 10)
        for client in SIMPLE_CLIENTS:
            self.assertIn(FULL_OF[client], FULL_CLIENTS)
            self.assertEqual(SIMPLE_FILES[client].replace("-simple", "", 1), CLIENT_FILES[FULL_OF[client]])
        manifest = json.loads(outputs()["manifest.json"])
        self.assertEqual(manifest["simple_version"], str(model_and_plan()[0].simple["version"]))
        self.assertTrue(set(SIMPLE_FILES.values()) <= set(manifest["outputs"]))

    def test_simple_header(self):
        """简易版的文件头写明是简易版和它的版本；完整版里没有“简易版”这几个字（完整版不改）。"""
        version = str(model_and_plan()[0].simple["version"])
        for client in SIMPLE_CLIENTS:
            if family(client) == "singbox":
                continue                       # JSON，没有注释
            self.assertIn(f"# 这是【简易版】（{version}）", text(client), client)
            self.assertNotIn("简易版", text(FULL_OF[client]), FULL_OF[client])


class SameAsFullOutsideGroups(unittest.TestCase):
    """简易版和对应的完整版：策略组以外完全相同，只差 docs/10 说好的几处。"""

    def test_loon_and_quantumultx(self):
        for client in SIMPLE_CLIENTS:
            fam = family(client)
            if fam not in ("loon", "quantumultx"):
                continue
            group_sections = {"loon": {"Remote Filter", "Proxy Group"}, "quantumultx": {"policy"}}[fam]
            a = ini_sections(strip_simple_header(text(client)))
            b = ini_sections(text(FULL_OF[client]))
            self.assertEqual([n for n, _ in a], [n for n, _ in b], client)
            for (name, la), (_, lb) in zip(a, b):
                if name not in group_sections:
                    self.assertEqual(la, lb, f"{client} 的 [{name or '文件头'}] 应该和完整版相同")

    def test_stash(self):
        """Stash：proxy-groups 以外的各项（DNS、占位节点、订阅、规则、规则集合）都相同；规则段连注释逐字相同。"""
        for client in SIMPLE_CLIENTS:
            if family(client) != "stash":
                continue
            a, b = parsed(client), parsed(FULL_OF[client])
            self.assertEqual(set(a), set(b), client)
            for key in a:
                if key != "proxy-groups":
                    self.assertEqual(a[key], b[key], f"{client} 的 {key} 应该和完整版相同")
            self.assertEqual(text(client).split("\nrules:\n", 1)[1], text(FULL_OF[client]).split("\nrules:\n", 1)[1], client)

    def test_mihomo(self):
        """mihomo：多出的只有——境外 DNS 地址后面的 #境外DNS；GEO 数据下载主机交给“境外DNS”的那一段规则；订阅上的检查间隔。"""
        for client in SIMPLE_CLIENTS:
            if family(client) != "mihomo":
                continue
            a, b = copy.deepcopy(parsed(client)), copy.deepcopy(parsed(FULL_OF[client]))
            self.assertEqual(set(a), set(b), client)
            dns_text = json.dumps(a["dns"], ensure_ascii=False)
            self.assertEqual(json.loads(dns_text.replace("#" + DNS_GROUP, "")), b["dns"], client)
            hosts = sorted({u.split("://", 1)[1].split("/", 1)[0] for u in a["geox-url"].values()})
            self.assertEqual(hosts, ["testingcf.jsdelivr.net"])
            extra = [f"DOMAIN,{h},{DNS_GROUP}" for h in hosts]
            self.assertEqual([r for r in a["rules"] if r not in extra], b["rules"], client)
            for name, pv in a["proxy-providers"].items():
                self.assertEqual(pv["health-check"]["interval"], SIMPLE_INTERVAL, client)
                pv["health-check"]["interval"] = FULL_INTERVAL
            self.assertEqual(a["proxy-providers"], b["proxy-providers"], client)
            for key in set(a) - {"dns", "rules", "proxy-providers", "proxy-groups"}:
                self.assertEqual(a[key], b[key], f"{client} 的 {key} 应该和完整版相同")

    def test_singbox(self):
        """sing-box：多出的只有境外 DNS（dns-foreign）和规则集下载走的出站；策略组以外的出站（直连、占位）相同。"""
        for client in SIMPLE_CLIENTS:
            if family(client) != "singbox":
                continue
            a, b = copy.deepcopy(parsed(client)), copy.deepcopy(parsed(FULL_OF[client]))
            for sv in a["dns"]["servers"]:
                if "detour" in sv:
                    self.assertEqual(sv["detour"], DNS_GROUP, client)
                    sv["detour"] = FD
            for hc in a.get("http_clients", []):
                self.assertEqual(hc["detour"], DNS_GROUP, client)
                hc["detour"] = FD
            for rs in a["route"]["rule_set"]:
                if "download_detour" in rs:
                    self.assertEqual(rs["download_detour"], DNS_GROUP, client)
                    rs["download_detour"] = FD
            keep = lambda c: [o for o in c["outbounds"] if o["type"] not in ("selector", "urltest")]
            self.assertEqual(keep(a), keep(b), client)
            a.pop("outbounds"), b.pop("outbounds")
            self.assertEqual(a, b, client)


class GroupStructure(unittest.TestCase):
    def test_group_names_and_kinds(self):
        """组名正好是 group_names()；没有完整版的模式组（X·手动优先、X·自动……）；除了“境外DNS”全是选择组。"""
        for client in SIMPLE_CLIENTS:
            gs = norm_groups(client)
            self.assertEqual(sorted(gs), sorted(group_names(client)), client)
            for name, g in gs.items():
                self.assertEqual(g["kind"], "url-test" if name == DNS_GROUP else "select", f"{client} {name}")
            self.assertFalse([n for n in gs if "·" in n and n != "PayPal·美国固定"], client)

    def test_business_groups_are_the_full_ones(self):
        """业务组（含国外默认的写明成员）、PayPal·美国固定、其他地区：成员和完整版的完全相同。"""
        m, _ = model_and_plan()
        for client in SIMPLE_CLIENTS:
            a, b = norm_groups(client), norm_groups(FULL_OF[client])
            for g in m.groups:
                if g.name in a:
                    self.assertEqual(a[g.name]["members"], b[g.name]["members"], f"{client} {g.name}")
            for name in ("PayPal·美国固定", OTHER):
                self.assertEqual((a[name]["members"], a[name]["filter"]), (b[name]["members"], b[name]["filter"]),
                                 f"{client} {name}")

    def test_region_groups_are_the_full_manual_groups(self):
        """六个地区：只按节点筛选的选择组，筛选和完整版的“X·手动”是同一条（宽的那条：按名字归到这个地区的全部节点）。"""
        for client in SIMPLE_CLIENTS:
            a, b = norm_groups(client), norm_groups(FULL_OF[client])
            for r in REGIONS:
                self.assertEqual(a[r]["members"], [], f"{client} {r} 不该嵌套别的组")
                self.assertIsNotNone(a[r]["filter"], f"{client} {r}")
                self.assertEqual(a[r]["filter"], b[f"{r}·手动"]["filter"], f"{client} {r}")
                if family(client) == "loon":
                    self.assertEqual(a[r]["filter"], LOON_FILTER[r])
                    self.assertEqual(parsed(client)["filters"][LOON_FILTER[r]], parsed(FULL_OF[client])["filters"][LOON_FILTER[r]])

    def test_foreign_default(self):
        """国外默认：写明的成员正好是七个地区、日本在第一个（首次默认日本），后面接全部节点那条筛选。"""
        m, _ = model_and_plan()
        any_rx = m.node_regex_any()
        for client in SIMPLE_CLIENTS:
            g = norm_groups(client)[FD]
            self.assertEqual(g["members"], FD_MEMBERS, client)
            fam = family(client)
            if fam == "loon":
                self.assertEqual(g["filter"], "F-ALL")
                self.assertEqual(parsed(client)["filters"]["F-ALL"], any_rx)
                self.assertEqual(g["raw"]["members"][-1], "F-ALL", "筛选排在七个地区后面")
            elif fam == "quantumultx":
                self.assertEqual(g["filter"], any_rx, client)
            elif fam == "mihomo":
                self.assertEqual(g["filter"], any_rx, client)
                self.assertTrue(g["raw"]["include-all-providers"])
            elif fam == "stash":
                self.assertEqual(g["filter"], emit_stash.exclude_builtins(emit_stash.exclude_placeholders(m, any_rx)), client)
                self.assertTrue(g["raw"]["include-all"])
            else:
                self.assertIsNone(g["filter"], "模板里没有节点：国外默认只有七个地区，不放占位")
                self.assertEqual(g["raw"]["default"], "日本")

    def test_foreign_dns_group(self):
        """境外DNS：只在 mihomo、sing-box；自动测速，节点 = 六个地区严筛选的并集（不含其他地区），检查间隔 1 小时；
        mihomo 上藏起来、写 max-failed-times，图标借用国外默认的；sing-box 的 idle_timeout 不小于检查间隔。"""
        m, _ = model_and_plan()
        strict = m.node_regexes_strict()
        for client in SIMPLE_CLIENTS:
            gs = norm_groups(client)
            if family(client) not in WITH_DNS_GROUP:
                self.assertNotIn(DNS_GROUP, gs, client)
                continue
            g = gs[DNS_GROUP]
            self.assertEqual(g["members"], [], client)
            if family(client) == "mihomo":
                raw = g["raw"]
                self.assertEqual(raw["filter"], "`".join(strict[REGION_IDS[r]] for r in REGIONS))
                self.assertEqual(raw["filter"].count("`"), 5)
                self.assertTrue(raw["hidden"])
                self.assertEqual(raw["interval"], SIMPLE_INTERVAL)
                self.assertEqual(raw["max-failed-times"], 3)
                self.assertEqual(raw["empty-fallback"], "REJECT")
                self.assertEqual(raw["icon"], m.icon_url(FD))
                # 完整版的自动组照旧 300 秒、不写 max-failed-times（完整版不改）
                full = norm_groups(FULL_OF[client])["日本·自动"]["raw"]
                self.assertEqual(full["interval"], FULL_INTERVAL)
                self.assertNotIn("max-failed-times", full)
            else:
                raw = g["raw"]
                self.assertEqual((raw["interval"], raw["idle_timeout"]), ("3600s", "3600s"), client)
                self.assertEqual(raw["outbounds"], [emit_singbox.PLACEHOLDER_TAG], "模板里没有节点")
                full = norm_groups(FULL_OF[client])["日本·自动"]["raw"]
                self.assertEqual((full["interval"], full["idle_timeout"]), ("300s", "30m"))

    def test_icons(self):
        """每个组都有图标（sing-box 没有图标字段），地址和完整版同名组的相同；“境外DNS”借用“国外默认”的图。"""
        m, _ = model_and_plan()
        for client in SIMPLE_CLIENTS:
            fam = family(client)
            if fam == "singbox":
                continue
            for name, g in norm_groups(client).items():
                raw = g["raw"]
                if fam in ("mihomo", "stash"):
                    icon = raw.get("icon")
                else:
                    line = [ln for ln in text(client).splitlines() if re.match(rf"^(?:static=)?{re.escape(name)} ?[=,]", ln)]
                    self.assertEqual(len(line), 1, f"{client} {name}")
                    icon = re.search(r"img-url ?= ?(\S+)$", line[0]).group(1)
                self.assertEqual(icon, m.icon_url(DNS_GROUP if name == DNS_GROUP else name), f"{client} {name}")
        self.assertEqual(m.icon_url(DNS_GROUP), m.icon_url(FD))


class SingboxWithNodes(unittest.TestCase):
    """sing-box 的节点是生成时按同一套正则分进组里的：拿样例节点生成一次，看每个组里是谁。期望按名字人工写。"""

    @classmethod
    def setUpClass(cls):
        cls.out, _, cls.renamed = convert(NODE_SAMPLES, emit_singbox.reserved_tags(model_and_plan()[0]))
        m, p = model_and_plan()
        cls.conf = {v: json.loads(emit_singbox.build(m, p, v, cls.out, cls.renamed, simple=True)) for v in ("1.14", "1.12")}

    def members(self, v, tag):
        ob = {o["tag"]: o for o in self.conf[v]["outbounds"]}
        return [self.renamed.get(t, t) for t in ob[tag]["outbounds"]]

    def test_nodes_in_groups(self):
        names = [p["name"] for p in NODE_SAMPLES]
        for v in ("1.14", "1.12"):
            self.assertEqual(self.members(v, "香港"), ["香港 SS", "香港 SS 无 UDP"])
            self.assertIn("日本", self.members(v, "日本"), "和组同名的节点改名以后仍按原名进日本组")
            fd = self.members(v, FD)
            self.assertEqual(fd[:7], FD_MEMBERS)
            converted = [self.renamed.get(o["tag"], o["tag"]) for o in self.out]
            self.assertTrue(set(converted) <= set(names))
            # 期望用逐步判断（generator/regions.py 的 Classifier，和拼出来的正则是两套实现）算：
            # 国外默认 = 进了任何一个组的节点（不是提示行）；境外DNS = 名字只指向一个地区的节点（严的那套）
            cl = regions.Classifier(model_and_plan()[0].region_spec)
            self.assertEqual(fd[7:], [n for n in converted if cl.classify(n).groups], "国外默认：七个地区后面是全部节点")
            dns = self.members(v, DNS_GROUP)
            self.assertTrue(dns)
            self.assertEqual(dns, [n for n in converted if cl.classify(n).auto], "境外DNS = 名字只指向一个地区的节点")
            self.assertNotIn("DIRECT", dns, "说不清地区的名字不进境外DNS")
            ob = {o["tag"]: o for o in self.conf[v]["outbounds"]}
            self.assertEqual(ob[FD]["default"], "日本")
            self.assertEqual(verify.check_singbox(json.dumps(self.conf[v], ensure_ascii=False)), [], v)
            self.assertEqual(verify.check_simple("singbox", json.dumps(self.conf[v], ensure_ascii=False), simple_spec()), [], v)

    def test_reserved_tags_cover_both_layouts(self):
        """完整版和简易版共用同一批转换好的节点：两版的组名都不能被节点占用（简易版多一个“境外DNS”）。"""
        reserved = emit_singbox.reserved_tags(model_and_plan()[0])
        self.assertTrue({DNS_GROUP, "日本", "日本·自动", "国外默认", "无可用节点", "DIRECT"} <= reserved)


class AllNodesRegex(unittest.TestCase):
    """“全部节点”（简易版的“国外默认”用）：一条正则，必须等于宽的七条取并集，也等于逐步判断里“进了某个组”的那些。"""

    @staticmethod
    def names():
        names = list(sample_expected()) + [n for n, _ in country_names()]
        names += [z["city"] + " 01" for z in reference()["tz_cities"]] + [n for n, _ in word_names()]
        return list(dict.fromkeys(names))

    def check(self, sp, names):
        loose, _ = regions.compose_all(sp)
        rx = {k: re.compile(v) for k, v in loose.items()}
        any_rx = re.compile(regions.compose_any(sp))
        cl = regions.Classifier(sp)
        bad = []
        for n in names:
            union = any(r.search(n) for r in rx.values())
            if bool(any_rx.search(n)) != union or union != bool(cl.classify(n).groups):
                bad.append((n, bool(any_rx.search(n)), union, cl.classify(n).groups))
        return bad

    def test_samples(self):
        names = self.names()
        self.assertGreater(len(names), 20000)
        bad = self.check(model_and_plan()[0].region_spec, names)
        self.assertEqual(bad[:10], [], f"共 {len(bad)} 个")

    def test_info_lines_and_placeholders(self):
        """提示行一个都不进；Stash 的占位节点名能被它选中（所以 Stash 那份另外排除了占位节点）。"""
        m = model_and_plan()[0]
        any_rx = re.compile(m.node_regex_any())
        info = load_yaml("node_names.yaml")["expect"]["info"]
        self.assertGreater(len(info), 20)
        self.assertEqual([n for n in info if any_rx.search(n)], [])
        holders = list(emit_stash.placeholders(m).values())
        self.assertTrue(all(any_rx.search(n) for n in holders))
        st = re.compile(emit_stash.filter_regex(m, NodeFilter(label="all", regex=m.node_regex_any())))
        self.assertEqual([n for n in holders + ["DIRECT", "direct", "REJECT", "Reject-Drop"] if st.search(n)], [])
        self.assertTrue(all(st.search(n) for n in FD_MEMBERS),
                        "Stash 文档没写 filter 管不管写明的成员；管的话七个地区的名字也要能通过")

    def test_random_names_and_local_overlay(self):
        """随机拼的名字（种子固定），公开词表和带本地补充样例的词表各跑一遍；本地补充里指定成 none 的名字不进。"""
        with open(f"{ROOT}/source/regions.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        overlay_spec, errors = regions.parse(data, OVERLAY["node_names"])
        self.assertEqual(errors, [])
        for label, sp, count, seed in (("公开词表", model_and_plan()[0].region_spec, 20000, 20261021),
                                       ("带本地补充", overlay_spec, 6000, 21)):
            rnd = random.Random(seed)
            words = [x for w in sp.regions + [sp.other] for x in w.words + w.latin + [regions.flag(c) for c in w.flags]]
            info = sp.info_words + sp.info_colon + sp.info_latin + sp.info_always[:2]
            extra = sp.after + sp.before + sp.arrows + sp.unlock + list(sp.assign)
            tags = ["01", "IPLC", "x0.5", "|", "-", " ", "[", "]", "【", "】", "·", "Premium", "#", "：", ":", "流量", "群", "０１"]
            flags = [regions.flag(c) for c in ("CN", "EU", "UN", "GB", "DE", "MO")]
            names = []
            for _ in range(count):
                parts = [rnd.choice(words if r < 0.4 else flags if r < 0.5 else info if r < 0.62 else extra if r < 0.75 else tags)
                         for r in (rnd.random() for _ in range(rnd.randint(1, 5)))]
                names.append(rnd.choice(["", " ", "-"]).join(parts).strip())
            names += list(sp.assign)
            bad = self.check(sp, [n for n in names if n])
            self.assertEqual(bad[:10], [], f"{label}：共 {len(bad)} 个")
        none = [n for n, rid in overlay_spec.assign.items() if rid == regions.NONE]
        self.assertTrue(none, "本地补充样例里要有指定成 none 的名字")
        any_rx = re.compile(regions.compose_any(overlay_spec))
        self.assertEqual([n for n in none if any_rx.search(n)], [])

    def test_portable_and_bounded(self):
        """和另外 13 条一样：没有会被当成分隔符的字符，只用三个引擎都支持的写法，不超过 16,000 字节（本项目自己定的上限）。"""
        rx = model_and_plan()[0].node_regex_any()
        for bad in (",", '"', "`", "=", " ", "\n", "\t", "(?=", "(?<=", "(?>", "(?P", "\\b", "\\d", "\\w", "{"):
            self.assertNotIn(bad, rx)
        self.assertTrue(rx.startswith("(?i)^") and rx.endswith(".*$"))
        self.assertLess(len(rx.encode("utf-8")), 16000)


class Verifier(unittest.TestCase):
    """写盘前检查（generator/verify.py）对简易版：现在的产物没有问题；几种坏写法都拦得住。"""

    def check(self, client, t):
        return verify.check_outputs({SIMPLE_FILES[client]: t}, spec=simple_spec())

    def test_generated_outputs_pass(self):
        files = outputs()
        self.assertEqual(verify.check_outputs(files, own=verify.own_files(model_and_plan()[0], files), spec=simple_spec()), [])

    def test_simple_files_are_not_skipped(self):
        """以前按完整文件名认 Loon / Quantumult X / Stash 的配置，新文件名会被悄悄跳过；现在按格式认，认不出的算错，
        有简易版而没给核对参数也算错。"""
        for client in SIMPLE_CLIENTS:
            self.assertTrue(verify.config_kind(SIMPLE_FILES[client].rsplit("/", 1)[-1]), client)
            probs = verify.check_outputs({SIMPLE_FILES[client]: text(client)})
            self.assertTrue(any("缺少参数" in p for p in probs), client)
        probs = verify.check_outputs({"loon/loon-lite.conf": text("loon"), "x/notes.txt": "x", "manifest.json": "{}"})
        self.assertEqual(len(probs), 1)
        self.assertIn("认不出", probs[0])
        broken = text("loon-simple").replace("FINAL,国外默认", "FINAL,不存在的组")
        self.assertTrue(any("目标不存在" in p for p in self.check("loon-simple", broken)))

    def test_layout_breakage_is_caught(self):
        cases = [
            # 地区组里塞进完整版的模式组 / 嵌套组
            ("loon-simple", lambda t: t.replace("日本 = select,F-JP", "日本 = select,日本·自动,F-JP\n日本·自动 = url-test,F-JP,url = http://x,interval = 300"),
             "模式组"),
            ("quantumultx-simple", lambda t: t.replace("static=日本, server-tag-regex=", "static=日本, 香港, server-tag-regex="), "只按节点筛选"),
            # 国外默认少了一个地区、筛选排到前面
            ("loon-simple", lambda t: t.replace("国外默认 = select,日本,香港,韩国,", "国外默认 = select,日本,香港,"), "七个地区"),
            ("loon-simple", lambda t: t.replace("国外默认 = select,日本,香港,韩国,台湾,新加坡,美国,其他地区,F-ALL",
                                                "国外默认 = select,F-ALL,日本,香港,韩国,台湾,新加坡,美国,其他地区"), "排在写明的成员后面"),
            ("stash-simple", lambda t: t.replace("proxies: [日本, 香港, 韩国, 台湾, 新加坡, 美国, 其他地区]",
                                                 "proxies: [日本, 香港, 台湾, 新加坡, 美国, 其他地区]"), "七个地区"),
            # 简易版里出现自动类的组
            ("quantumultx-simple", lambda t: t.replace("static=香港, server-tag-regex=", "url-latency-benchmark=香港, server-tag-regex="),
             "应该是选择组"),
            # mihomo：境外 DNS 没经内部组、组名拼错（mihomo 会把它当网卡名）、GEO 数据主机没交给它、内部组没藏、检查间隔不对
            ("mihomo-simple-profile", lambda t: t.replace("https://1.1.1.1/dns-query#境外DNS", "https://1.1.1.1/dns-query"), "#境外DNS"),
            ("mihomo-simple-profile", lambda t: t.replace("#境外DNS'", "#境外DN'"), "网卡名"),
            ("mihomo-simple-profile", lambda t: t.replace("- DOMAIN,testingcf.jsdelivr.net,境外DNS\n", ""), "GEO 数据"),
            ("mihomo-simple-profile", lambda t: t.replace("- DOMAIN,testingcf.jsdelivr.net,境外DNS\n",
                                                          "- DOMAIN-SUFFIX,jsdelivr.net,国外默认\n  - DOMAIN,testingcf.jsdelivr.net,境外DNS\n"),
             "先被"),
            ("mihomo-simple-profile", lambda t: t.replace("  hidden: true\n", "  hidden: false\n"), "藏起来"),
            ("mihomo-simple-profile", lambda t: t.replace("    interval: 3600\n", "    interval: 300\n", 1), "健康检查间隔"),
            # sing-box：境外 DNS / 规则集下载走国外默认、间隔超过 idle_timeout
            ("singbox-simple-1.14", lambda t: t.replace('"detour": "境外DNS"', '"detour": "国外默认"', 1), "应该经 境外DNS"),
            ("singbox-simple-1.12", lambda t: t.replace('"download_detour": "境外DNS"', '"download_detour": "国外默认"', 1), "应该经 境外DNS"),
            ("singbox-simple-1.14", lambda t: t.replace('"idle_timeout": "3600s"', '"idle_timeout": "30m"'), "idle_timeout"),
        ]
        for client, mutate, want in cases:
            t = mutate(text(client))
            self.assertNotEqual(t, text(client), f"{client}：替换没有生效（{want}）")
            probs = self.check(client, t)
            self.assertTrue(any(want in p for p in probs), f"{client} 应该报“{want}”，实际：{probs[:5]}")

    def test_duration_parser(self):
        self.assertEqual([verify._duration_s(x) for x in ("300s", "30m", "1h", "1h30m", "3600s", "1.5s", "250ms")],
                         [300, 1800, 3600, 5400, 3600, 1.5, 0.25])
        for bad in ("", "30", "5x", "1h 30m", "m"):
            self.assertIsNone(verify._duration_s(bad), bad)
        self.assertEqual([emit_singbox.idle_timeout(x) for x in (300, 1800, 1801, 3600)], ["30m", "30m", "1801s", "3600s"])


class SourceSettings(unittest.TestCase):
    """project.yaml 的 simple 一节写错时，生成直接报错。"""

    def test_bad_values_are_rejected(self):
        good = dict(model_and_plan()[0].simple)
        self.assertEqual(_check_simple(good), [])
        self.assertTrue(_check_simple(None))
        for key, value in (("version", "2026-10-21"), ("version", "v1"), ("health_check_interval_s", 30),
                           ("health_check_interval_s", "3600"), ("health_check_interval_s", True),
                           ("foreign_dns_group", ""), ("foreign_dns_group", "境外 DNS"), ("foreign_dns_group", "a#b"),
                           ("foreign_dns_group", "a&b"), ("foreign_dns_group", "a=b"), ("foreign_dns_group", "a,b"),
                           ("foreign_dns_group", 1)):
            self.assertTrue(_check_simple({**good, key: value}), (key, value))
        self.assertTrue(_check_simple({**good, "extra": 1}))
        missing = dict(good)
        missing.pop("version")
        self.assertTrue(_check_simple(missing))

    def test_internal_group_name_must_be_new(self):
        import shutil
        import tempfile
        from generator.model import load
        with tempfile.TemporaryDirectory() as d:
            for sub in ("source", "generator"):
                shutil.copytree(f"{ROOT}/{sub}", f"{d}/{sub}", ignore=shutil.ignore_patterns("local.yaml", "__pycache__"))
            path = f"{d}/source/project.yaml"
            with open(path, encoding="utf-8") as f:
                t = f.read()
            self.assertIn("foreign_dns_group: 境外DNS", t)
            with open(path, "w", encoding="utf-8") as f:
                f.write(t.replace("foreign_dns_group: 境外DNS", "foreign_dns_group: 日本"))
            with self.assertRaises(SourceError) as e:
                load(d, include_local=False)
            self.assertIn("重名", str(e.exception))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""上一版交付包与当前工程的对比：节点按名称分地区的结果，以及六个公开产物改了什么。

用法：python3 tools/compare_versions.py --old <上一版交付包解压后的工程目录> [--old-label r8] [--new-label r9] [--write] [--out 文件]
  --old    上一版的工程目录（里面有 source/、generator/、dist/）。上一版的筛选正则由它自己的生成器算出来：
           在那个目录里另起一个 Python 进程调用它的 generator.model.load()。
           所以 --old 指向的目录里的代码会被执行，只用你信任的旧版工程。
  --write  把结果写进 docs/evidence/与上一版的对比.md；不带时只打印。
  --out    和 --write 一起用：改写到别的文件（相对工程目录）。和更早的版本对比时用它，免得盖掉“与上一版”的那份，
           例如 --old <r7 的工程目录> --old-label r7 --out docs/evidence/与r7的对比.md。

对比的内容：
  1. 节点名称：tests/node_names.yaml（人工写期望的节点名）和 tests/data/cldr_tz_names.json（CLDR 的国家 / 地区名、时区库的
     城市名）在两版规则下各分到哪里。当前这一版每个地区有两条筛选（宽的给手动组，严的给自动 / 故障转移 / 负载均衡），
     上一版如果只有一条，就拿它同时和两种期望比。
  2. 社区写法：几份公开配置里的地区正则，原样用 ICU 执行（这台机器没有 ICU 时跳过这一节）。
  3. 公开产物：两版 dist/ 里的六个文件按“规则 / 策略组 / DNS / 其余设置”拆成一条一条来比，列出新增、删除、改动的条目，
     并确认两版都有的规则先后顺序没有变。节点筛选正则太长，对比时换成“宽 hk”“严 hk”“上一版 hk”这样的标记。
只读取文件，不联网。r6 → r7 那一次的对比（当时的规则写在 project.yaml 里，结构不同）保留在
docs/evidence/节点名称分组-r6与r7对比.md，不再重算。
"""
import argparse
import collections
import difflib
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from generator.model import load  # noqa: E402
from generator.regions import flag  # noqa: E402
from generator.util import safe_stdout  # noqa: E402
from check_icu import ICURegex, _load_icu, sample_expect_auto, sample_names  # noqa: E402

SIX = {"HK": "hk", "JP": "jp", "KR": "kr", "TW": "tw", "SG": "sg", "US": "us"}
SKIP = {"UM", "VI", "AS", "GU", "PR", "MP"}          # 美国海外属地：归美国还是其他地区都说得过去，不计
NAME = {"hk": "香港", "jp": "日本", "kr": "韩国", "tw": "台湾", "sg": "新加坡", "us": "美国", "other": "其他地区"}
OUT = os.path.join("docs", "evidence", "与上一版的对比.md")

# 公开配置里的地区正则，原样照录（Astra 审核包里的快照，或 2026-10-02 从各仓库读取；括号里是它所在的客户端）
COMMUNITY = {
    "墨鱼 ddgksf2013（Quantumult X）": {
        "hk": r"(?=.*(港|HK|(?i)Hong))^((?!(台|日|韩|新|美)).)*$", "tw": r"(?=.*(台|TW|(?i)Taiwan))^((?!(港|日|韩|新|美)).)*$",
        "jp": r"(?=.*(日|JP|(?i)Japan))^((?!(港|台|韩|新|美)).)*$", "sg": r"(?=.*(新|狮|獅|SG|(?i)Singapore))^((?!(港|台|日|韩|美)).)*$",
        "us": r"(?=.*(美|US|(?i)States|American))^((?!(港|台|日|韩|新)).)*$"},
    "Repcz（Loon）": {
        "hk": r"(?i)🇭🇰|香港|(\b(HK|Hong)\b)", "us": r"(?i)🇺🇸|美国|洛杉矶|圣何塞|(\b(US|United States)\b)",
        "sg": r"(?i)🇸🇬|新加坡|狮|(\b(SG|Singapore)\b)", "jp": r"(?i)🇯🇵|日本|东京|(\b(JP|Japan)\b)",
        "tw": r"(?i)🇨🇳|🇹🇼|台湾|(\b(TW|Tai|Taiwan)\b)"},
    "fmz200（Loon）": {
        "hk": r"(?i)(🇭🇰|港|HK)", "tw": r"(?i)(台|TW|Tai)", "us": r"(?i)(🇺🇸|美|US)", "jp": r"(?i)(🇯🇵|日本|JP|Japan)",
        "kr": r"(?i)(🇰🇷|KR|Korea|KOR|首尔|韩|韓)", "sg": r"(?i)(🇸🇬|新加坡|狮城|SG|Singapore)"},
    "Moli-X（Loon）": {
        "hk": r"(?i)(港|HK|Hong)", "tw": r"(?i)(台|TW|Tai|中国)",
        "jp": r"(?i)(日本|川日|东京|大阪|泉日|埼玉|沪日|深日|JP|Japan)",
        "us": r"(?i)(美|波特兰|达拉斯|俄勒冈|凤凰城|费利蒙|硅谷|拉斯维加斯|洛杉矶|圣何塞|圣克拉拉|西雅图|芝加哥|US|United States)",
        "sg": r"(?i)(新加坡|坡|狮城|SG|Singapore)"},
}

OUTPUTS = ("loon/loon.conf", "quantumultx/quantumultx.conf", "mihomo/mihomo-profile.yaml", "mihomo/mihomo-core.yaml",
           "sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json")
MAX_ITEMS = 40          # 每个分段最多列出这么多条，其余只报数量
MAX_LEN = 220


# ---------------------------------------------------------------------------
# 上一版的筛选正则
# ---------------------------------------------------------------------------

_OLD_CODE = r"""
import json, sys
sys.path.insert(0, ".")
from generator.model import load
m = load(".", include_local=False)
strict = m.node_regexes_strict() if hasattr(m, "node_regexes_strict") else None
sys.stdout.write(json.dumps({"loose": m.node_regexes(), "strict": strict,
                             "version": m.project["project"]["source_version"]}))
"""


def old_rules(old_dir: str):
    """返回 (宽 {组 id: 正则}, 严 {地区 id: 正则} 或 None, 旧统一源版本)。"""
    r = subprocess.run([sys.executable, "-c", _OLD_CODE], cwd=old_dir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    if r.returncode != 0:
        raise SystemExit("没能从上一版工程里算出筛选正则（它要有 generator.model.load 和 node_regexes；r6 及更早的版本结构不同，"
                         "那一次的对比保留在 docs/evidence/节点名称分组-r6与r7对比.md）：\n" + r.stderr[-600:])
    d = json.loads(r.stdout)
    return d["loose"], d["strict"], d["version"]


# ---------------------------------------------------------------------------
# 节点名称
# ---------------------------------------------------------------------------

def classify(rx: dict, n: str) -> list:
    return sorted(k for k, v in rx.items() if v.search(n))


def show(groups) -> str:
    return "、".join(NAME.get(g, g) for g in groups) or "不进任何组"


def kind(want, got, auto=False):
    """不符合期望时属于哪一类；auto：比的是自动类组（严的那条）。"""
    if got == want:
        return None
    if not want and got:
        return "不该进自动类组的进了（说不清落地的节点）" if auto else "提示行没排除"
    if not got:
        return "该进自动类组的没进（被当成说不清落地，或被当成提示行）" if auto else "真节点被当成提示行，哪个组都没进"
    if len(got) > len(want):
        return "多进了别的地区"
    if got == ["other"]:
        return "没认出来，掉进其他地区"
    if want == ["other"]:
        return "其他国家的节点被认成六个地区之一"
    if len(got) < len(want):
        return "少进了一个地区"
    return "分到了别的地区"


def independent_names():
    """[(名字, 期望的组, 类别)]，以及 CLDR 里的国家 / 地区个数。"""
    with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
        ref = json.load(f)
    out = []
    for c in ref["regions"]:
        if c["code"] in SKIP:
            continue
        want = SIX.get(c["code"], "other")
        fl = flag(c["code"])
        for n in (f'{fl} {c["zh_hans"]} 01', f'{c["zh_hans"]} 01', f'{c["zh_hant"]} 01', f'{c["en"]} 01',
                  f'{c["code"]}-01', f'{fl} {c["code"]} 01'):
            out.append((n, want, "国家"))
    for z in ref["tz_cities"]:
        cc = z["cc"][0]
        if cc not in SKIP:
            out.append((z["city"] + " 01", SIX.get(cc, "other"), "城市"))
    return out, len(ref["regions"])


def names_section(L, old, old_strict, new, new_strict, old_label, new_label):
    _, expect = sample_names()
    expect_auto = sample_expect_auto()
    indep, n_regions = independent_names()
    six = [k for k in new if k != "other"]
    # 上一版只有一条筛选时，自动类组用的就是它（“其他地区”没有自动类组）
    old_auto = old_strict if old_strict is not None else {k: v for k, v in old.items() if k in six}

    L += [f"## 一、节点名称：人工写期望的样本（{len(expect)} 个）", "",
          f"样本在 `tests/node_names.yaml`。期望有两种：进哪些地区的“手动”组（宽），进哪个地区的“自动 / 故障转移 / 负载均衡”（严；"
          "说不清落地的节点、其他地区的节点、提示行都不进）。"
          + ("" if old_strict is not None else f"{old_label} 每个地区只有一条筛选，手动组和自动类组用的是同一条，所以拿它同时和两种期望比。"), "",
          "| | 手动组：符合 | 不符合 | 自动类组：符合 | 不符合 |", "|---|---|---|---|---|"]
    detail = {}
    for label, loose_rx, strict_rx in ((old_label, old, old_auto), (new_label, new, new_strict)):
        bad_l, bad_s = collections.OrderedDict(), collections.OrderedDict()
        for n, want in expect.items():
            got = classify(loose_rx, n)
            k = kind(want, got)
            if k:
                bad_l.setdefault(k, []).append((n, want, got))
            want_a, got_a = expect_auto[n], classify(strict_rx, n)
            k = kind(want_a, got_a, auto=True)
            if k:
                bad_s.setdefault(k, []).append((n, want_a, got_a))
        detail[label] = (bad_l, bad_s)
        nl, ns = sum(len(v) for v in bad_l.values()), sum(len(v) for v in bad_s.values())
        L.append(f"| {label} | {len(expect) - nl} | {nl} | {len(expect) - ns} | {ns} |")
    def n_bad(label):
        return sum(len(v) for part in detail[label] for v in part.values())

    note = "说明：样本是照着要解决的问题写的（城市、繁体、运营商、中转、解锁说明、提示行、说不清落地的写法），不代表某家机场的真实比例"
    note += f"；{old_label} 在真实订阅上的错误率不会这么高。" if n_bad(old_label) else "。"
    if not n_bad(new_label):
        note += (f"{new_label} 全部符合，只能说明它" if n_bad(old_label) else "两版都全部符合，只能说明它们") + "和我写的期望一致；"
    note += "真实订阅里的写法要靠 `tools/check_node_names.py` 逐个看。"
    L += ["", note, ""]
    for label in (old_label, new_label):
        bad_l, bad_s = detail[label]
        for title, bad in (("手动组", bad_l), ("自动类组", bad_s)):
            if not bad:
                continue
            L += [f"### {label} 不符合期望的明细：{title}", ""]
            for k, v in bad.items():
                L += [f"**{k}（{len(v)}）**", ""]
                L += [f"- `{n}`：应为 {show(want)}，实际 {show(got)}" for n, want, got in v]
                L.append("")

    # 同一批名字上两版结果不同的
    all_names = list(dict.fromkeys(list(expect) + [n for n, _, _ in indep]))
    changed_manual, changed_auto = [], []
    for n in all_names:
        o, c = classify(old, n), classify(new, n)
        oa, ca = classify(old_auto, n), classify(new_strict, n)
        if o != c:
            changed_manual.append(f"- `{n}`：{show(o)} → {show(c)}" + (f"（自动类组：{show(oa)} → {show(ca)}）" if oa != ca else ""))
        elif oa != ca:
            changed_auto.append(f"- `{n}`：手动组不变（{show(c)}）；自动类组 {show(oa)} → {show(ca)}")
    L += [f"## 二、同一批名字上，两版结果不同的（共 {len(all_names)} 个名字：上面的样本 + 第三节的独立样本）", "",
          f"### 手动组的归属变了（{len(changed_manual)} 个）", ""]
    L += changed_manual or ["（没有）"]
    L += ["", f"### 手动组不变，只是自动 / 故障转移 / 负载均衡的成员变了（{len(changed_auto)} 个）", ""]
    L += changed_auto or ["（没有）"]
    L.append("")

    total = collections.Counter((cat, want != "other") for _, want, cat in indep)
    L += ["## 三、独立样本（不是我写的）", "",
          f"CLDR 的 {n_regions} 个国家 / 地区，每个生成 6 个名字：国旗 + 简体名、简体名、繁体名、英文名、两位代码、国旗 + 代码；"
          "美国的 6 个海外属地不计。城市取时区库 `zone1970.tab` 的城市名。表里是“分对的个数”（手动组）。", "",
          f"| | 六个地区的国名（{total[('国家', True)]}） | 其他国家的国名（{total[('国家', False)]}） "
          f"| 其他国家的城市（{total[('城市', False)]}） | 六个地区的城市（{total[('城市', True)]}） |", "|---|---|---|---|---|"]
    notes = []
    for label, rx in ((old_label, old), (new_label, new)):
        c = collections.Counter()
        miss = []
        for n, want, cat in indep:
            got = classify(rx, n)
            ok = got == [want]
            c[(cat, want != "other", ok)] += 1
            if not ok and not (cat == "城市" and want != "other"):
                miss.append(f"`{n}` → {show(got)}")
        L.append(f"| {label} | {c[('国家', True, True)]} | {c[('国家', False, True)]} | {c[('城市', False, True)]} "
                 f"| {c[('城市', True, True)]} |")
        if miss:
            notes.append(f"{label} 在国名和其他国家城市上分错的：{'；'.join(miss)}。")
    strict_ok = sum(1 for n, want, cat in indep if want != "other" and cat == "国家" and classify(new_strict, n) == [want])
    L += [""] + notes
    L += ["", f"六个地区的国名这 {total[('国家', True)]} 个名字，{new_label} 严的那条也全部收进各自的地区（{strict_ok} 个）。"
          if strict_ok == total[("国家", True)] else
          f"**注意**：六个地区的国名这 {total[('国家', True)]} 个名字里，{new_label} 严的那条只收了 {strict_ok} 个。",
          "“六个地区的城市”一栏里认不出的，都是时区库里的美国小镇（Monticello、Vincennes、Winamac、Tell City、Knox、Menominee、"
          "Beulah、Center、New Salem、Boise、Juneau、Sitka、Metlakatla、Yakutat、Nome、Adak 等），机场不会用它们命名节点，没有收进词表。", ""]
    return expect, indep


def community_section(L, expect, indep, old, new, old_label, new_label):
    lib, suf, where = _load_icu()
    if lib is None:
        L += ["## 四、社区常见写法", "", f"这台机器上没有 ICU，没有运行这一节（{where}）。", ""]
        return
    S = [(n, w) for n, w in expect.items() if w] + [(n, [w]) for n, w, _ in indep]
    seen = set()
    S = [(n, w) for n, w in S if not (n in seen or seen.add(n))]
    L += ["## 四、社区常见写法在同一批样本上的结果（参考）", "",
          f"正则原样取自公开配置（Astra 审核包里的快照，或 2026-10-02 从各仓库读取；照录在 `tools/compare_versions.py` 里），用 ICU {where} 执行。"
          "只统计它们各自定义了的地区，不含提示行；期望用的是“手动组”那一种（说不清落地的节点算两个地区都该收）。"
          "“漏认”偏高主要因为样本里城市写法多，对它们不完全公平；“误认”一栏更能说明问题：把不属于这个地区的节点收了进来。"
          "这些配置各有自己的设计取舍（正则短、好读、好改），这里只比较“按名字分地区”这一件事。", "",
          "| 写法 | 定义的地区 | 漏认 | 误认 | 误认举例 |", "|---|---|---|---|---|"]

    def run(rxs_icu):
        fn = fp = tot = 0
        ex = []
        for k, r in rxs_icu.items():
            for n, w in S:
                hit = r.search(n)
                if k in w:
                    tot += 1
                    fn += (not hit)
                elif hit:
                    fp += 1
                    if len(ex) < 4 and not any(n == e.split(" → ")[0].strip("`").replace("\\|", "|") for e in ex):
                        ex.append(f"`{n}` → {NAME[k]}".replace("|", "\\|"))
        return fn, tot, fp, ex

    for label, rxs in COMMUNITY.items():
        fn, tot, fp, ex = run({k: ICURegex(lib, suf, v) for k, v in rxs.items()})
        L.append(f"| {label} | {'、'.join(NAME[k] for k in rxs)} | {fn} / {tot} | {fp} | {'；'.join(ex)} |")
    new_fn = None
    for label, rx in ((f"本工程 {old_label}", old), (f"本工程 {new_label}（宽的那套）", new)):
        fn, tot, fp, ex = run({k: ICURegex(lib, suf, v.pattern) for k, v in rx.items() if k != "other"})
        L.append(f"| {label} | 六个地区 | {fn} / {tot} | {fp} | {'；'.join(ex) or '—'} |")
        new_fn = fn
    L += ["", f"{new_label}“漏认”的 {new_fn} 个都是上面说的时区库美国小镇。", ""]


# ---------------------------------------------------------------------------
# 公开产物：拆成一条一条来比
# ---------------------------------------------------------------------------

def _short(s: str) -> str:
    s = s.replace("|", "\\|")
    return s if len(s) <= MAX_LEN else s[:MAX_LEN] + f"…（共 {len(s)} 个字符）"


class Labels:
    """把节点筛选正则换成短标记。"""

    def __init__(self, sets):
        self.by_text = {}
        for prefix, rxs in sets:
            for k, v in (rxs or {}).items():
                self.by_text.setdefault(v, f"<筛选：{prefix}{k}>")

    def sub(self, text: str) -> str:
        return self.by_text.get(text, "<筛选：未知的正则>" if len(text) > 400 else text)


def _ini_units(text: str, rel: str, labels: Labels):
    """Loon / Quantumult X：{分段: [(键, 内容)]}。键相同的两条算“同一条的改动”；规则行没有键。"""
    out = collections.OrderedDict()
    cur = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
            continue
        if cur is None:
            continue
        key = None
        if rel.startswith("loon"):
            m = re.match(r'^(\S+) = NameRegex, FilterKey = "(.*)"$', line)
            if m:
                line = f'{m.group(1)} = NameRegex, FilterKey = "{labels.sub(m.group(2))}"'
            if cur not in ("Rule", "Remote Rule") and " = " in line:
                key = line.split(" = ", 1)[0]
        else:
            m = re.search(r"server-tag-regex=([^,]*)", line)
            if m:
                line = line.replace(m.group(1), labels.sub(m.group(1)))
            if cur == "policy":
                key = line.split(",", 1)[0]
            elif cur in ("general", "dns") and "=" in line and not line.startswith(("server", "doh-server")):
                key = line.split("=", 1)[0].strip()
        out[cur].append((key, line))
    return out


def _dump(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=False, separators=(", ", ": "))


def _mihomo_units(text: str, rel: str, labels: Labels):
    c = yaml.safe_load(text)
    out = collections.OrderedDict()
    rest = []
    for k, v in c.items():
        if k == "proxy-groups":
            groups = []
            for g in v:
                g = dict(g)
                if "filter" in g:
                    g["filter"] = labels.sub(g["filter"])
                groups.append((g["name"], _dump(g)))
            out["策略组（proxy-groups）"] = groups
        elif k == "rules":
            out["规则（rules）"] = [(None, r) for r in v]
        elif k == "dns":
            out["DNS（dns）"] = [(kk, f"{kk}: {_dump(vv)}") for kk, vv in v.items()]
        else:
            rest.append((k, f"{k}: {_dump(v)}"))
    out["其余设置"] = rest
    return out


def _inline_summary(rs: dict) -> dict:
    if rs.get("type") != "inline":
        return rs
    n = collections.Counter()
    for r in rs.get("rules", []):
        for k, v in r.items():
            n[k] += len(v) if isinstance(v, list) else 1
    return {"type": "inline", "tag": rs["tag"], "rules": "<" + "、".join(f"{k} {v} 条" for k, v in n.items()) + ">"}


def _singbox_units(text: str, rel: str, labels: Labels):
    c = json.loads(text)
    out = collections.OrderedDict()
    dns, route = c.get("dns", {}), c.get("route", {})
    out["DNS 服务器（dns.servers）"] = [(s.get("tag"), _dump(s)) for s in dns.get("servers", [])]
    out["DNS 规则（dns.rules）"] = [(None, _dump(r)) for r in dns.get("rules", [])]
    out["路由规则（route.rules）"] = [(None, _dump(r)) for r in route.get("rules", [])]
    out["规则集（route.rule_set）"] = [(r.get("tag"), _dump(_inline_summary(r))) for r in route.get("rule_set", [])]
    out["出站与策略组（outbounds）"] = [(o.get("tag"), _dump(o)) for o in c.get("outbounds", [])]
    rest = [(f"dns.{k}", f"dns.{k}: {_dump(v)}") for k, v in dns.items() if k not in ("servers", "rules")]
    rest += [(f"route.{k}", f"route.{k}: {_dump(v)}") for k, v in route.items() if k not in ("rules", "rule_set")]
    rest += [(k, f"{k}: {_dump(v)}") for k, v in c.items() if k not in ("dns", "route", "outbounds")]
    out["其余设置"] = rest
    return out


def units_of(text: str, rel: str, labels: Labels):
    if rel.endswith(".conf"):
        return _ini_units(text, rel, labels)
    if rel.endswith(".yaml"):
        return _mihomo_units(text, rel, labels)
    return _singbox_units(text, rel, labels)


def _token_diff(a: str, b: str) -> str:
    """同一条目改了什么：按逗号拆开后，列出去掉和加上的片段。"""
    # 两头的括号不算内容：JSON 列表里最后一项是“"x"]”，后面再加一项时它变成“"x"”，不能因此算成改动
    ta, tb = [x.strip().strip("[]{}").strip() for x in a.split(",")], [x.strip().strip("[]{}").strip() for x in b.split(",")]
    ca, cb = collections.Counter(ta), collections.Counter(tb)
    gone = [x for x in ta if ca[x] > cb[x]]
    come = [x for x in tb if cb[x] > ca[x]]
    def part(verb, items):
        return f"{verb} `{_short('，'.join(items))}`" if items else ""

    return "；".join(x for x in (part("去掉", gone), part("加上", come)) if x)


def diff_units(old_units, new_units):
    """返回 [(分段, 新增, 删除, 改动, 顺序是否不变)]，只含有差异的分段；以及没有差异的分段名。"""
    rows, same = [], []
    for sec in list(dict.fromkeys(list(old_units) + list(new_units))):
        a, b = old_units.get(sec, []), new_units.get(sec, [])
        ca, cb = collections.Counter(t for _, t in a), collections.Counter(t for _, t in b)
        removed = [(k, t) for k, t in a if ca[t] > cb[t]]
        added = [(k, t) for k, t in b if cb[t] > ca[t]]
        changed = []
        rk = {k: t for k, t in removed if k is not None}
        for k, t in list(added):
            if k is not None and k in rk:
                changed.append((k, rk[k], t))
                removed.remove((k, rk[k]))
                added.remove((k, t))
        for k, t in list(added):
            if k is not None:
                continue
            best = max(((difflib.SequenceMatcher(None, t0, t).ratio(), t0) for k0, t0 in removed if k0 is None),
                       default=(0, None))
            if best[0] >= 0.75:
                changed.append((_short(best[1][:60]) + "…", best[1], t))
                removed.remove((None, best[1]))
                added.remove((k, t))
        common_a = [t for _, t in a if cb[t] >= ca[t] and t in cb]
        common_b = [t for _, t in b if ca[t] >= cb[t] and t in ca]
        order_ok = common_a == common_b
        if removed or added or changed or not order_ok:
            rows.append((sec, [t for _, t in added], [t for _, t in removed], changed, order_ok))
        else:
            same.append(f"{sec}（{len(b)} 条）")
    return rows, same


_URL_RX = re.compile(r"https?://[^\s`，,\"']+")
_FILTER_LABEL_RX = re.compile(r"<筛选：(\S+) [a-z]+>")          # Labels 给筛选正则换上的标记：<筛选：宽 hk>、<筛选：上一版严 us>
_LOON_FILTER_RX = re.compile(r"(?<![A-Za-z0-9-])F-[A-Z]{2,5}(-AUTO)?(?![A-Za-z0-9-])")   # Loon 策略组引用的筛选名：F-HK、F-JP-AUTO
COLLAPSE_AT = 5          # 改法相同（只是各自的地址、各自的地区不同）的改动达到这么多条时合并成一条


def _generic(d: str) -> str:
    """把一条改动里“各自不同”的部分换成统一的说法：地址，筛选标记里的地区，Loon 筛选名里的地区。"""
    d = _FILTER_LABEL_RX.sub(r"<筛选：\1 各自的地区>", _URL_RX.sub("<各自的地址>", d))
    return _LOON_FILTER_RX.sub(lambda m: "F-<各自的地区>" + (m.group(1) or ""), d)


def collapse_changes(changed) -> list:
    """把“改法一模一样、只是各自的地址或各自的地区不同”的改动合并成一条——例如 81 个策略组都只是在行尾加了自己的
    图标地址，或者每个地区的自动组都把筛选从上一版的那条换成这一版严的那条：逐条列出来会把别的改动淹没。
    返回 [(条目的显示名, 改了什么)]，先后顺序按第一次出现。
    只有靠“把地址、地区看成一样”才相同的改动才合并；改法逐字相同的不动（那种本来就很少见，逐条列更清楚）。"""
    described = [(k, _token_diff(a, b)) for k, a, b in changed]
    buckets: dict = {}
    for k, d in described:
        buckets.setdefault(_generic(d), []).append((k, d))
    out = []
    for generic, items in buckets.items():
        if len(items) >= COLLAPSE_AT and generic != items[0][1]:
            names = "、".join(f"`{k}`" for k, _ in items[:3])
            out.append((f"{len(items)} 条（{names} 等，改法相同）", generic))
        else:
            out += [(f"`{k}`", d) for k, d in items]
    return out


def raw_line_diff(ta: str, tb: str):
    """逐行比较两个文本，返回 [("删除" | "新增", 行)]，只含有差别的行。"""
    a, b = ta.splitlines(), tb.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("delete", "replace"):
            out += [("删除", x) for x in a[i1:i2]]
        if tag in ("insert", "replace"):
            out += [("新增", x) for x in b[j1:j2]]
    return out


def output_diff_lines(ta: str, tb: str, rel: str, labels, seen: dict) -> list:
    """一个产物两版文本的对比，返回要写进报告的行。seen 记着“差异内容 → 第一个出现它的产物”，
    同一个客户端的两份产物差异一模一样时只列一次。"""
    if ta == tb:
        return ["逐字节相同。", ""]
    rows, same = diff_units(units_of(ta, rel, labels), units_of(tb, rel, labels))
    L = ["", "没有变化的分段：" + ("、".join(same) or "（无）") + "。"]
    if not rows:
        # 各分段逐条相同、文件却不同：差别在拆分时不计入的内容里。把有差别的行原样列出来，免得只留一句“没有变化”
        raw = raw_line_diff(ta, tb)
        L += ["", "各分段的条目完全相同；两个文件的差别只在拆分时不计入的内容里（注释、空行、排版）：", ""]
        L += [f"- {what}一行：`{_short(line.strip())}`" for what, line in raw[:MAX_ITEMS]]
        if len(raw) > MAX_ITEMS:
            L.append(f"- （还有 {len(raw) - MAX_ITEMS} 行，没有列出）")
        return L + [""]
    body = []
    for sec, added, removed, changed, order_ok in rows:
        body.append(f"**{sec}**：新增 {len(added)} 条，删除 {len(removed)} 条，改动 {len(changed)} 条；"
                    + ("两版都有的条目顺序不变。" if order_ok else "**两版都有的条目顺序变了。**"))
        body.append("")
        for title, items in (("新增", added), ("删除", removed)):
            for t in items[:MAX_ITEMS]:
                body.append(f"- {title}：`{_short(t)}`")
            if len(items) > MAX_ITEMS:
                body.append(f"- （{title}的还有 {len(items) - MAX_ITEMS} 条，没有列出）")
        shown = collapse_changes(changed)
        for label, what in shown[:MAX_ITEMS]:
            body.append(f"- 改动 {label}：{what}")
        if len(shown) > MAX_ITEMS:
            body.append(f"- （改动的还有 {len(shown) - MAX_ITEMS} 项，没有列出）")
        body.append("")
    key = "\n".join(body)
    if key in seen:           # 同一个客户端的两份产物（mihomo 的两种用法、sing-box 的两个版本）差异往往一模一样
        return L + ["", f"有差异的分段和 `{seen[key]}` 的一模一样（{'、'.join(r[0] for r in rows)}），不重复列出。", ""]
    seen[key] = rel
    return L + [""] + body


def outputs_section(L, old_dir, labels, old_label, new_label):
    L += [f"## 五、六个公开产物：{old_label} → {new_label} 改了什么", "",
          "每个产物按“分段”拆成一条一条来比（去掉注释）：Loon / Quantumult X 按 `[分段]` 逐行；mihomo 按策略组、规则、DNS、其余设置；"
          "sing-box 按 DNS 服务器、DNS 规则、路由规则、规则集、出站与策略组、其余设置。节点筛选正则换成了标记："
          f"`<筛选：上一版 hk>` / `<筛选：上一版严 hk>` 是 {old_label} 的（{old_label} 每个地区只有一条筛选时没有后一种），"
          f"`<筛选：宽 hk>` / `<筛选：严 hk>` 是 {new_label} 的两条。很多条目改法相同、只是各自的地区或各自的地址不同时，"
          "合并成一条，写成“各自的地区”“各自的地址”。“顺序”指两版都有的条目，先后是否相同。", ""]
    seen = {}
    for rel in OUTPUTS:
        a, b = os.path.join(old_dir, "dist", rel), os.path.join(ROOT, "dist", rel)
        L += [f"### `{rel}`", ""]
        if not (os.path.exists(a) and os.path.exists(b)):
            L += ["缺文件，没有比。", ""]
            continue
        with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
            ta, tb = fa.read(), fb.read()
        L.append(f"大小：{len(ta.encode('utf-8')):,} → {len(tb.encode('utf-8')):,} 字节。")
        L += output_diff_lines(ta, tb, rel, labels, seen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True)
    ap.add_argument("--old-label", default="上一版")
    ap.add_argument("--new-label", default="当前")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    safe_stdout()
    old_loose, old_strict, old_version = old_rules(a.old)
    m = load(ROOT, include_local=False)
    new_version = m.project["project"]["source_version"]
    new_loose, new_strict = m.node_regexes(), m.node_regexes_strict()
    old_label, new_label = f"{a.old_label}（统一源 {old_version}）", f"{a.new_label}（统一源 {new_version}）"

    def comp(d):
        return None if d is None else {k: re.compile(v) for k, v in d.items()}

    out_rel = a.out.replace(os.sep, "/")
    L = [f"# 版本对比：{a.old_label} → {a.new_label}", "",
         f"生成方式：`python3 tools/compare_versions.py --old <{a.old_label} 交付包解压后的工程目录> --old-label {a.old_label} "
         f"--new-label {a.new_label} --write" + ("" if a.out == OUT else f" --out {out_rel}")
         + f"`。{old_label} 的筛选正则由它自己的生成器算出来，{new_label} 的取自当前统一源；"
         "两者都用 Python 执行（当前这一版另有 ICU 与 mihomo 官方内核的对比，见 `icu-check.log`、`official-check.log`）。"
         "产物对比用的是两版各自 `dist/` 里的文件。", ""]
    expect, indep = names_section(L, comp(old_loose), comp(old_strict), comp(new_loose), comp(new_strict),
                                  a.old_label, a.new_label)
    community_section(L, expect, indep, comp(old_loose), comp(new_loose), a.old_label, a.new_label)
    labels = Labels([("上一版 ", old_loose), ("上一版严 ", old_strict), ("宽 ", new_loose), ("严 ", new_strict)])
    outputs_section(L, a.old, labels, a.old_label, a.new_label)

    text = "\n".join(L) + "\n"
    if a.write:
        out = os.path.join(ROOT, a.out)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {out_rel}（{len(text.splitlines())} 行）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

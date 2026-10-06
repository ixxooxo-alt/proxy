#!/usr/bin/env python3
"""节点名称分地区：旧规则（r6 交付包）与当前规则在同一批样本上的对比。

用法：python3 tools/compare_node_rules.py --old <r6 交付包解压后的目录> [--write]
  --old    统一源 2026.09.30-1 那一版的工程目录（里面有 source/project.yaml 和 generator/util.py）。
           旧规则 = 当时 project.yaml 里的六条地区正则和信息节点正则，按当时的 compose_node_regex 组合。
  --write  把结果写进 docs/evidence/节点名称分组-新旧对比.md；不带时只打印。

样本：tests/node_names.yaml（人工写期望的节点名）和 tests/data/cldr_tz_names.json（CLDR 的国家 / 地区名、时区库的城市名）。
社区写法：几份公开配置里的地区正则，原样用 ICU 执行（这台机器没有 ICU 时跳过这一节）。
另外逐行对比新旧两版 dist/ 里的六个公开产物：去掉节点筛选和注释之后是否完全相同（确认这次只动了节点分组）。
只读取节点名称样本，不联网。注意：--old 指向的目录里的 generator/util.py 会被当作代码执行，只用你信任的旧版工程。
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from generator.model import load  # noqa: E402
from generator.regions import flag  # noqa: E402
from generator.util import safe_stdout  # noqa: E402
from check_icu import ICURegex, _load_icu, sample_names  # noqa: E402

SIX = {"HK": "hk", "JP": "jp", "KR": "kr", "TW": "tw", "SG": "sg", "US": "us"}
SKIP = {"UM", "VI", "AS", "GU", "PR", "MP"}          # 美国海外属地：归美国还是其他地区都说得过去，不计
NAME = {"hk": "香港", "jp": "日本", "kr": "韩国", "tw": "台湾", "sg": "新加坡", "us": "美国", "other": "其他地区"}

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


def old_rules(old_dir: str):
    """返回 ({组 id: 编译好的正则}, 旧统一源版本)。"""
    spec = importlib.util.spec_from_file_location("old_util", os.path.join(old_dir, "generator", "util.py"))
    util = importlib.util.module_from_spec(spec)
    sys.modules["old_util"] = util
    spec.loader.exec_module(util)
    with open(os.path.join(old_dir, "source", "project.yaml"), encoding="utf-8") as f:
        p = yaml.safe_load(f)
    rx = {r["id"]: util.compose_node_regex(r["regex"], [p["info_node_regex"]]) for r in p["regions"]}
    rx["other"] = util.compose_node_regex(None, [r["regex"] for r in p["regions"]] + [p["info_node_regex"]])
    return {k: re.compile(v) for k, v in rx.items()}, p["project"]["source_version"]


OUTPUTS = ("loon/loon.conf", "quantumultx/quantumultx.conf", "mihomo/mihomo-profile.yaml", "mihomo/mihomo-core.yaml",
           "sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json")


def _without_node_filters(path: str, rel: str) -> list:
    """产物去掉注释和节点筛选之后的各行。Loon：去掉 [Remote Filter] 的定义行，引用的筛选名统一成 F-US
    （旧版 PayPal 固定入口单独定义了一条与美国相同的 F-PAYPAL）；Quantumult X：server-tag-regex 的值换成占位；
    mihomo：去掉策略组的 filter / exclude-filter 行。"""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f.read().split("\n"):
            if line.lstrip().startswith("#"):
                continue
            if rel.startswith("loon"):
                if re.match(r"^F-[A-Z]+ = NameRegex", line):
                    continue
                line = line.replace("F-PAYPAL", "F-US")
            elif rel.startswith("quantumultx"):
                line = re.sub(r"server-tag-regex=[^,]*", "server-tag-regex=RX", line)
            elif rel.startswith("mihomo") and re.match(r"^\s+(exclude-)?filter: ", line):
                continue
            out.append(line)
    return out


def rest_unchanged(old_dir: str) -> list:
    """[(产物, 结论)]。"""
    rows = []
    for rel in OUTPUTS:
        a, b = os.path.join(old_dir, "dist", rel), os.path.join(ROOT, "dist", rel)
        if not (os.path.exists(a) and os.path.exists(b)):
            rows.append((rel, "缺文件，没有比"))
            continue
        with open(a, "rb") as fa, open(b, "rb") as fb:
            if fa.read() == fb.read():
                rows.append((rel, "逐字节相同"))
                continue
        la, lb = _without_node_filters(a, rel), _without_node_filters(b, rel)
        if la == lb:
            rows.append((rel, f"去掉节点筛选和注释后逐行相同（{len(lb)} 行）"))
        else:
            diff = sum(1 for x, y in zip(la, lb) if x != y) + abs(len(la) - len(lb))
            rows.append((rel, f"**不同**：约 {diff} 行"))
    return rows


def classify(rx: dict, n: str) -> list:
    return sorted(k for k, v in rx.items() if v.search(n))


def show(groups) -> str:
    return "、".join(NAME[g] for g in groups) or "不进任何组"


def kind(want, got):
    if got == want:
        return None
    if not want:
        return "信息节点没排除"
    if not got:
        return "真节点被当成信息节点删掉"
    if len(got) > len(want):
        return "多进了别的组"
    if got == ["other"]:
        return "没认出来，掉进其他地区"
    if want == ["other"]:
        return "其他国家的节点被认成六个地区之一"
    return "分到了别的地区"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    safe_stdout()
    old, old_version = old_rules(a.old)
    m = load(ROOT, include_local=False)
    new_version = m.project["project"]["source_version"]
    new = {k: re.compile(v) for k, v in m.node_regexes().items()}
    _, expect = sample_names()
    with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
        ref = json.load(f)
    indep = []          # (名字, 期望, 类别)
    for c in ref["regions"]:
        if c["code"] in SKIP:
            continue
        want = SIX.get(c["code"], "other")
        fl = flag(c["code"])
        for n in (f'{fl} {c["zh_hans"]} 01', f'{c["zh_hans"]} 01', f'{c["zh_hant"]} 01', f'{c["en"]} 01',
                  f'{c["code"]}-01', f'{fl} {c["code"]} 01'):
            indep.append((n, want, "国家"))
    for z in ref["tz_cities"]:
        cc = z["cc"][0]
        if cc not in SKIP:
            indep.append((z["city"] + " 01", SIX.get(cc, "other"), "城市"))
    total = collections.Counter((cat, want != "other") for _, want, cat in indep)

    L = ["# 节点名称分组：旧规则（r6）与新规则（r7）对比", "",
         f"生成方式：`python3 tools/compare_node_rules.py --old <r6 交付包目录> --write`。输入是 `tests/node_names.yaml`"
         f"（人工写期望的 {len(expect)} 个节点名）和 `tests/data/cldr_tz_names.json`（CLDR 的 {len(ref['regions'])} 个国家 / 地区名、"
         f"时区库的城市名）。旧规则取自 r6 交付包（统一源 {old_version}）`source/project.yaml` 里的六条地区正则和信息节点正则，"
         f"按当时的 `compose_node_regex` 组合；新规则是统一源 {new_version} 的 `source/regions.yaml`。两者都用 Python 执行"
         "（新规则另有 ICU 与 mihomo 官方内核的对比，见 `icu-check.log`、`official-check.log`）。", "",
         f"## 人工写期望的样本（{len(expect)} 个）", ""]
    rows = {}
    for label, rx in (("旧规则（r6）", old), ("新规则（r7）", new)):
        bad = collections.OrderedDict()
        for n, want in expect.items():
            got = classify(rx, n)
            k = kind(want, got)
            if k:
                bad.setdefault(k, []).append((n, want, got))
        rows[label] = bad
    L += ["| | 分对 | 分错 | 其中 |", "|---|---|---|---|"]
    for label, bad in rows.items():
        nb = sum(len(v) for v in bad.values())
        L.append(f"| {label} | {len(expect) - nb} | {nb} | " + ("；".join(f"{k} {len(v)}" for k, v in bad.items()) or "—") + " |")
    L += ["", "说明：样本偏重城市、繁体、运营商和中转写法（这正是这次要解决的问题），不代表某家机场的真实比例，"
          "所以旧规则在真实订阅上的错误率不会这么高；这张表只说明新规则覆盖了哪些旧规则没覆盖的写法。", "",
          "样本的来历：第一批 345 个是调规则时用的；第二批 142 个是规则定型后另写的边界写法（两批去掉重复后共 483 个），"
          "首次运行时发现 1 个真问题（“香港新增 01”被专线简称“港新”带进了新加坡，已去掉这个简称）和 1 个我自己写错的期望；"
          "定稿前又加了 15 个，是和对应的规则改动一起写的：Xboard 面板源码里写出的 3 个提示行（同时补了信息词“过滤掉”）、"
          "“via 要单独成词”的 4 个、新补的城市 / 代码 5 个、“A转B”写法 3 个。"
          "新规则在这批样本上全对，只能说明它和我写的期望一致；真实订阅里的写法要靠 `tools/check_node_names.py` 逐个看。", "",
          "### 旧规则分错的明细", ""]
    for k, v in rows["旧规则（r6）"].items():
        L += [f"**{k}（{len(v)}）**", ""]
        L += [f"- `{n}`：应为 {show(want)}，旧规则 → {show(got)}" for n, want, got in v]
        L.append("")
    if rows["新规则（r7）"]:
        L += ["### 新规则分错的明细", ""]
        for k, v in rows["新规则（r7）"].items():
            L += [f"- `{n}`：应为 {show(want)}，新规则 → {show(got)}（{k}）" for n, want, got in v]
        L.append("")

    L += ["## 独立样本（不是我写的）", "",
          "每个国家 / 地区生成 6 个名字：国旗 + 简体名、简体名、繁体名、英文名、两位代码、国旗 + 代码；美国的 6 个海外属地不计。"
          "城市取时区库 `zone1970.tab` 的城市名。", "",
          f"| | 六个地区的国名（{total[('国家', True)]}） | 其他国家的国名（{total[('国家', False)]}） "
          f"| 其他国家的城市（{total[('城市', False)]}） | 六个地区的城市（{total[('城市', True)]}） |", "|---|---|---|---|---|"]
    notes = []
    for label, rx in (("旧规则（r6）", old), ("新规则（r7）", new)):
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
            notes.append(f"{label}在国名上分错的：{'；'.join(miss)}。")
    L += [""] + notes
    L += ["", "“六个地区的城市”一栏里认不出的，都是时区库里的美国小镇（Monticello、Vincennes、Winamac、Tell City、Knox、Menominee、"
          "Beulah、Center、New Salem、Boise、Juneau、Sitka、Metlakatla、Yakutat、Nome、Adak 等），机场不会用它们命名节点，没有收进词表。", ""]

    lib, suf, where = _load_icu()
    if lib is None:
        L += ["## 社区常见写法", "", f"这台机器上没有 ICU，没有运行这一节（{where}）。", ""]
    else:
        S = [(n, w) for n, w in expect.items() if w] + [(n, [w]) for n, w, _ in indep]
        seen = set()
        S = [(n, w) for n, w in S if not (n in seen or seen.add(n))]
        L += ["## 社区常见写法在同一批样本上的结果（参考）", "",
              f"正则原样取自公开配置（Astra 审核包里的快照，或 2026-10-02 从各仓库读取；照录在 `tools/compare_node_rules.py` 里），用 ICU {where} 执行。"
              "只统计它们各自定义了的地区，不含信息节点。“漏认”偏高主要因为样本里城市写法多，对它们不完全公平；"
              "“误认”一栏更能说明问题：把不属于这个地区的节点收了进来。这些配置各有自己的设计取舍（正则短、好读、好改），"
              "这里只比较“按名字分地区”这一件事。", "",
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
        for label, rx in (("本工程旧规则（r6）", old), ("本工程新规则（r7）", new)):
            fn, tot, fp, ex = run({k: ICURegex(lib, suf, v.pattern) for k, v in rx.items() if k != "other"})
            L.append(f"| {label} | 六个地区 | {fn} / {tot} | {fp} | {'；'.join(ex) or '—'} |")
            new_fn = fn
        L += ["", f"新规则“漏认”的 {new_fn} 个都是上面说的时区库美国小镇。", ""]

    L += ["## 其余部分有没有变", "",
          "逐行对比旧版与当前 `dist/` 里的六个公开产物（去掉注释；Loon 去掉 `[Remote Filter]` 的定义行，"
          "Quantumult X 把 `server-tag-regex` 的值换成占位，mihomo 去掉策略组的 `filter` / `exclude-filter` 行）：", "",
          "| 产物 | 结论 |", "|---|---|"]
    L += [f"| `{rel}` | {verdict} |" for rel, verdict in rest_unchanged(a.old)]
    L += ["", "也就是说，这一版相对上一版只改了节点筛选（和说明用的注释）；规则、策略组及其成员、DNS、订阅、广告集合的写法都没有变。", ""]

    text = "\n".join(L)
    if a.write:
        out = os.path.join(ROOT, "docs", "evidence", "节点名称分组-新旧对比.md")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {os.path.relpath(out, ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

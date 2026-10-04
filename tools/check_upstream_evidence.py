#!/usr/bin/env python3
"""按固定快照核对统一源里标为社区来源（dlc / bm7-snap）的规则，并生成核对记录。

用法：
  python3 tools/check_upstream_evidence.py --dlc /path/to/domain-list-community \\
      --bm7 /path/to/ios_rule_script [--write]

  --dlc  domain-list-community 的 git 检出目录（需要 data/ 目录）
  --bm7  blackmatrix7/ios_rule_script 的 git 检出目录（只需要 rule/Clash/<列表名>/ 这些子目录，可稀疏检出）
  --write 同时写入 docs/evidence/upstream-snapshot.json（核对记录）与 docs/evidence/上游规则对照.md（报告）

检查项（任何一项不通过，退出码为 1）：
  1. 两个检出目录的提交号必须与 source/evidence.yaml 里 dlc / bm7-snap 登记的 snapshot 一致。
  2. 每条 ev=dlc / bm7-snap 的规则，必须出现在所在服务 upstream 字段所列的上游列表里：
       same     有完全相同的条目（后缀对 domain: / DOMAIN-SUFFIX，精确对 full: / DOMAIN）
       covered  非汇总列表里有更宽的条目覆盖它（例如本项目写 music.apple.com，列表写 apple.com）
     被汇总列表（category-* / GlobalMedia 等）的上级域名覆盖、上游只有更窄的条目、或找不到，都不算。
  3. 自有广告 / 跟踪拦截条目里标为 dlc 的，必须在 category-ads-all 展开结果里有相同范围的条目。
  4. category-ads-all 里落在产品规则范围内的条目，必须由自有拦截条目或误杀例外处理
     （否则 mihomo / sing-box 会拦、Loon / Quantumult X 不拦，四端不一致）。
  5. category-ads-all 里不能有比产品规则更宽、会把整条产品规则拦掉的条目（除非有误杀例外）。
提示项（不影响退出码）：仍为维护者知识但上游已有的条目（可升级）、上游把同一域名归到另一个服务的列表（归属差异）。

上游只是证据来源之一：不按出现次数投票，也不直接求并集。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from generator.model import COMMUNITY_EV_SOURCE, build_plan, load  # noqa: E402
from generator.util import suffix_match  # noqa: E402

RECORD = os.path.join(ROOT, "docs", "evidence", "upstream-snapshot.json")
REPORT = os.path.join(ROOT, "docs", "evidence", "上游规则对照.md")

DLC_AGGREGATE_PREFIXES = ("category-", "geolocation-", "tld-")
DLC_AGGREGATE_NAMES = {"cn", "private", "google-registry-tld"}
BM7_AGGREGATES = {"GlobalMedia", "Global", "Proxy", "ProxyLite", "AsianMedia", "ChinaMax", "ChinaMaxNoIP",
                  "ChinaMaxNoMedia", "Developer", "USMedia", "UKMedia"}
RANK = {"same": 4, "covered": 3, "covered-aggregate": 2, "narrower": 1}


# ---------------------------------------------------------------------------
# 读取上游
# ---------------------------------------------------------------------------

def git_info(repo: str) -> dict:
    def g(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout.strip()
    return {"commit": g("rev-parse", "HEAD"), "date": g("log", "-1", "--format=%cI")}


def parse_dlc(data_dir: str):
    """返回 (own, includes)。own: 列表名 -> [(kind, value, attrs)]，kind 为 domain（含子域）/ full / keyword / regexp。
    “&列表名” 归属标记视同该列表直接定义。"""
    own = defaultdict(list)
    includes = defaultdict(list)
    for fn in sorted(os.listdir(data_dir)):
        name = fn.lower()
        with open(os.path.join(data_dir, fn), encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                toks = line.split()
                head = toks[0]
                if head.startswith("include:"):
                    must = [t[1:] for t in toks[1:] if t.startswith("@") and not t.startswith("@-")]
                    mustnot = [t[2:] for t in toks[1:] if t.startswith("@-")]
                    includes[name].append((head[8:].lower(), must, mustnot))
                    continue
                kind, value = "domain", head
                for pfx in ("domain:", "full:", "keyword:", "regexp:"):
                    if head.startswith(pfx):
                        kind, value = pfx[:-1], head[len(pfx):]
                        break
                attrs = tuple(t[1:] for t in toks[1:] if t.startswith("@"))
                rule = (kind, value.lower() if kind != "regexp" else value, attrs)
                own[name].append(rule)
                for aff in (t[1:].lower() for t in toks[1:] if t.startswith("&")):
                    own[aff].append(rule)
    return own, includes


def resolve(own, includes, name):
    """展开一个列表（含 include 与属性筛选）。"""
    def go(n, stack):
        if n in stack:
            return []
        out = list(own.get(n, []))
        for inc, must, mustnot in includes.get(n, []):
            for r in go(inc, stack + (n,)):
                attrs = set(r[2])
                if all(a in attrs for a in must) and not any(a in attrs for a in mustnot):
                    out.append(r)
        return out
    return go(name, ())


def parse_bm7(repo: str, names):
    own = {}
    missing = []
    for n in sorted(names):
        p = os.path.join(repo, "rule", "Clash", n, n + ".list")
        if not os.path.exists(p):
            missing.append(n)
            continue
        rules = []
        with open(p, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                t, v = parts[0], (parts[1].strip().lower() if len(parts) > 1 else "")
                kind = {"DOMAIN-SUFFIX": "domain", "DOMAIN": "full", "DOMAIN-KEYWORD": "keyword"}.get(t)
                if kind and v:
                    rules.append((kind, v, ()))
        own[n] = rules
    return own, missing


def dlc_is_aggregate(name: str) -> bool:
    return name.startswith(DLC_AGGREGATE_PREFIXES) or name in DLC_AGGREGATE_NAMES


# ---------------------------------------------------------------------------
# 比较
# ---------------------------------------------------------------------------

def relation(our_kind, our_value, kind, value):
    """上游条目 (kind, value) 相对本项目规则的关系：same / covered / narrower / None。"""
    if kind == "domain":
        if our_kind == "suffix":
            if value == our_value:
                return "same"
            if suffix_match(our_value, value):
                return "covered"
            if suffix_match(value, our_value):
                return "narrower"
        elif our_kind == "domain" and suffix_match(our_value, value):
            # 上游 domain:X 含子域；与本项目精确规则 X 同值时，说明上游明确列出了这个主机
            return "same" if value == our_value else "covered"
    elif kind == "full":
        if our_kind == "domain" and value == our_value:
            return "same"
        if our_kind == "suffix" and suffix_match(value, our_value):
            return "narrower"
    return None


def fmt_entry(src, lst, kind, value, attrs):
    if src == "dlc":
        p = {"domain": "", "full": "full:"}.get(kind, kind + ":")
        return f"{lst}:{p}{value}" + "".join(" @" + a for a in attrs)
    p = {"domain": "DOMAIN-SUFFIX,", "full": "DOMAIN,"}.get(kind, kind + ",")
    return f"{lst}:{p}{value}"


def evaluate(rule_kind, rule_value, lists, own, is_agg, src):
    best, hits = None, []
    for lst in lists:
        for kind, value, attrs in own.get(lst, []):
            if kind not in ("domain", "full"):
                continue
            rel = relation(rule_kind, rule_value, kind, value)
            if not rel:
                continue
            if rel == "covered" and is_agg(lst):
                rel = "covered-aggregate"
            hits.append((rel, fmt_entry(src, lst, kind, value, attrs)))
            if best is None or RANK[rel] > RANK[best]:
                best = rel
    hits.sort(key=lambda x: -RANK[x[0]])
    return {"status": best or "absent", "hits": [h for _, h in hits[:4]]}


def run(dlc_repo: str, bm7_repo: str):
    m = load(ROOT)
    plan = build_plan(m)
    failures, notes = [], []

    snaps = OrderedDict()
    for ev_id, repo, src in (("dlc", dlc_repo, "dlc"), ("bm7-snap", bm7_repo, "bm7")):
        info = git_info(repo)
        want = str(m.evidence[ev_id].get("snapshot", ""))
        snaps[src] = {"evidence_id": ev_id, "repo": m.evidence[ev_id].get("url", ""), **info}
        if info["commit"] != want:
            failures.append(f"{src} 检出目录的提交 {info['commit'] or '（读不到）'} 与 evidence.yaml 登记的 {want} 不一致")

    dlc_own, dlc_inc = parse_dlc(os.path.join(dlc_repo, "data"))
    services = [s for s in m.services if s.file != "local.yaml"]
    bm7_names = {n for s in services for n in s.upstream.get("bm7", [])}
    bm7_own, bm7_missing = parse_bm7(bm7_repo, bm7_names)
    for n in bm7_missing:
        failures.append(f"bm7 检出目录里没有 rule/Clash/{n}/{n}.list（稀疏检出时需要加上这个目录）")
    for s in services:
        for n in s.upstream.get("dlc", []):
            if n not in dlc_own and n not in dlc_inc:
                failures.append(f"服务 {s.id} 映射的 dlc 列表 {n} 在快照里不存在")

    # 列表 → 映射到它的服务（用于发现归属差异）
    list_owner = defaultdict(set)
    for s in services:
        for n in s.upstream.get("dlc", []):
            if not dlc_is_aggregate(n):
                list_owner[n].add(s.id)
    dlc_index = defaultdict(list)       # 值 -> [(列表, kind)]，只含非汇总列表
    for lst, rules in dlc_own.items():
        if dlc_is_aggregate(lst):
            continue
        for kind, value, attrs in rules:
            if kind in ("domain", "full"):
                dlc_index[value].append((lst, kind))

    records, upgrade, differ = [], [], []
    for s in services:
        for r in s.rules:
            if r.kind not in ("domain", "suffix"):
                continue
            rec = OrderedDict([("service", s.id), ("group", s.group), ("kind", r.kind), ("value", r.value), ("ev", r.ev)])
            ev_dlc = evaluate(r.kind, r.value, s.upstream.get("dlc", []), dlc_own, dlc_is_aggregate, "dlc")
            ev_bm7 = evaluate(r.kind, r.value, s.upstream.get("bm7", []), bm7_own, lambda n: n in BM7_AGGREGATES, "bm7")
            rec["dlc"], rec["bm7"] = ev_dlc, ev_bm7
            records.append(rec)
            src = COMMUNITY_EV_SOURCE.get(r.ev)
            ok = {"same", "covered"}
            if src and rec[src]["status"] not in ok:
                failures.append(f"[{s.id}] {r.kind},{r.value} 标为 {r.ev}，但在 upstream.{src} "
                                f"{s.upstream.get(src)} 里{'只有汇总列表覆盖' if rec[src]['status'] == 'covered-aggregate' else '找不到（' + rec[src]['status'] + '）'}")
            if r.ev == "maintainer" and (ev_dlc["status"] in ok or ev_bm7["status"] in ok):
                upgrade.append(f"[{s.id}] {r.kind},{r.value}：{(ev_dlc['hits'] + ev_bm7['hits'])[:2]}")
            # 归属差异：同一个值在上游非汇总列表里出现，而该列表映射到本项目的另一个服务
            want_kind = "domain" if r.kind == "suffix" else "full"
            for lst, kind in dlc_index.get(r.value, []):
                others = list_owner.get(lst, set()) - {s.id}
                if kind == want_kind and others and lst not in s.upstream.get("dlc", []):
                    differ.append(f"`{r.value}`：本项目归 {s.group}（{s.id}）；上游列表 `{lst}` 对应本项目的 {', '.join(sorted(others))}")

    # ---------- 广告 ----------
    ads_all = [x for x in resolve(dlc_own, dlc_inc, "category-ads-all")]
    ads_dom = sorted({(k, v, a) for k, v, a in ads_all if k in ("domain", "full")})
    ads_other = sum(1 for k, _, _ in ads_all if k not in ("domain", "full"))
    ads_set = {(k, v) for k, v, _ in ads_dom}

    ads_local_rec = []
    for r in plan.ads_local:
        want = ("domain" if r.kind == "suffix" else "full", r.value)
        present = want in ads_set
        ads_local_rec.append(OrderedDict([("kind", r.kind), ("value", r.value), ("ev", r.ev), ("in_category_ads_all", present)]))
        if r.ev == "dlc" and not present:
            alt = ("full" if want[0] == "domain" else "domain", r.value) in ads_set
            failures.append(f"自有拦截 {r.kind},{r.value} 标为 dlc，但 category-ads-all 里"
                            + ("范围不同（一个含子域、一个不含）" if alt else "没有这一条"))

    def covers_host(rule, kind, value):
        """规则 rule 是否把上游条目 (kind, value) 的拦截范围完全包住。"""
        if kind == "full":
            return (rule.kind == "suffix" and suffix_match(value, rule.value)) or (rule.kind == "domain" and value == rule.value)
        return rule.kind == "suffix" and suffix_match(value, rule.value)

    under, covering = [], []
    for kind, value, attrs in ads_dom:
        prods = [p for p in plan.product if (p.kind == "suffix" and suffix_match(value, p.value)) or
                 (p.kind == "domain" and value == p.value)]
        if prods:
            p = max(prods, key=lambda x: (x.kind == "domain", x.value.count(".")))
            by_local = [a for a in plan.ads_local if covers_host(a, kind, value)]
            by_exc = [e for e in plan.exceptions if covers_host(e, kind, value)]
            handled = "自有拦截" if by_local else ("误杀例外 → " + by_exc[0].target if by_exc else "")
            under.append(OrderedDict([("entry", fmt_entry("dlc", "", kind, value, attrs)[1:]), ("product_rule", f"{p.kind},{p.value}"),
                                      ("group", p.target), ("handled_by", handled or "未处理")]))
            if not handled:
                failures.append(f"category-ads-all 的 {kind}:{value} 落在产品规则 {p.kind},{p.value}（{p.target}）内，"
                                "但没有自有拦截条目或误杀例外：Loon / Quantumult X 不会拦截，与 mihomo / sing-box 不一致")
        if kind == "domain":
            for p in plan.product:          # 误杀例外本来就排在广告之前，不在此列
                if p.kind in ("suffix", "domain") and suffix_match(p.value, value):
                    exc = [e for e in plan.exceptions if covers_host(e, "full" if p.kind == "domain" else "domain", p.value)]
                    covering.append(OrderedDict([("entry", value), ("rule", f"{p.kind},{p.value}"), ("group", p.target),
                                                 ("exception", bool(exc))]))
                    if not exc:
                        failures.append(f"category-ads-all 的 {value} 比产品规则 {p.kind},{p.value}（{p.target}）更宽，"
                                        "mihomo / sing-box 会把整条规则拦掉")

    counts = defaultdict(int)
    for rec in records:
        src = COMMUNITY_EV_SOURCE.get(rec["ev"])
        key = (rec["ev"], rec[src]["status"] if src else max(rec["dlc"]["status"], rec["bm7"]["status"], key=lambda x: RANK.get(x, 0)))
        counts[key] += 1

    result = OrderedDict([
        ("generated_by", "tools/check_upstream_evidence.py"),
        ("snapshots", snaps),
        ("summary", OrderedDict([
            ("rules_checked", len(records)),
            ("community_rules", sum(1 for x in records if x["ev"] in COMMUNITY_EV_SOURCE)),
            ("failures", len(failures)),
            ("category_ads_all_domain_entries", len(ads_dom)),
            ("category_ads_all_keyword_regexp_entries", ads_other),
        ])),
        ("rules", records),
        ("ads_local", ads_local_rec),
        ("ads_under_products", under),
        ("ads_covering_rules", covering),
    ])
    return m, result, failures, upgrade, differ, counts


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

STATUS_ZH = {"same": "同值", "covered": "被上级域名覆盖", "covered-aggregate": "只被汇总列表覆盖",
             "narrower": "上游更窄", "absent": "未找到"}


def write_report(m, result, failures, upgrade, differ, counts, missing_by_service):
    L = ["# 上游规则对照（自动生成，请勿手改）", ""]
    L.append("由 `tools/check_upstream_evidence.py --write` 生成；逐条数据见同目录 `upstream-snapshot.json`。")
    L.append("上游规则集只是证据来源之一：不按出现次数投票，也不直接求并集；采纳原则见 `docs/08-外部审核记录.md`。")
    L.append("")
    L.append("## 快照")
    L.append("")
    L.append("| 来源 | 证据 id | 提交 | 提交时间 |")
    L.append("|---|---|---|---|")
    for src, s in result["snapshots"].items():
        L.append(f"| {s['repo']} | `{s['evidence_id']}` | `{s['commit']}` | {s['date']} |")
    L.append("")
    L.append("## 结论")
    L.append("")
    sm = result["summary"]
    L.append(f"- 核对域名规则 {sm['rules_checked']} 条，其中标为社区来源的 {sm['community_rules']} 条。")
    L.append(f"- 检查不通过：{len(failures)} 项。" + ("" if failures else "所有社区来源条目都在所在服务映射的上游列表里找到。"))
    for f in failures:
        L.append(f"  - {f}")
    L.append("")
    L.append("| 证据 | 核对结果 | 条数 |")
    L.append("|---|---|---|")
    for (ev, st), n in sorted(counts.items()):
        L.append(f"| `{ev}` | {STATUS_ZH.get(st, st)} | {n} |")
    L.append("")
    L.append("官方证据（`openai-net` 等）不需要上游佐证，表中结果只作参考。")
    L.append("")
    L.append("## 仍为维护者知识的条目")
    L.append("")
    L.append("在两个快照的映射列表里都找不到（或只被汇总列表覆盖），需要实测或另找依据：")
    L.append("")
    for rec in result["rules"]:
        if rec["ev"] == "maintainer":
            st = max(rec["dlc"]["status"], rec["bm7"]["status"], key=lambda x: RANK.get(x, 0))
            L.append(f"- `{rec['kind']},{rec['value']}` → {rec['group']}（dlc：{STATUS_ZH[rec['dlc']['status']]}；bm7：{STATUS_ZH[rec['bm7']['status']]}）")
    L.append("")
    L.append("可升级为社区证据的维护者条目：" + ("无。" if not upgrade else ""))
    for u in upgrade:
        L.append(f"- {u}")
    L.append("")
    L.append("## 归属与上游不同的条目")
    L.append("")
    if differ:
        L.append("同一个值在上游另一个服务的列表里（本项目的取舍理由写在对应服务的 notes / shared_excluded）：")
        L.append("")
        for d in sorted(set(differ)):
            L.append(f"- {d}")
    else:
        L.append("无。")
    L.append("")
    L.append("## 广告拦截")
    L.append("")
    L.append(f"快照中 category-ads-all 展开后有 {sm['category_ads_all_domain_entries']} 条域名条目"
             f"（另有 {sm['category_ads_all_keyword_regexp_entries']} 条关键词 / 正则条目，本项目的产品规则不涉及）。")
    L.append("")
    L.append("落在产品规则范围内的条目（mihomo / sing-box 先匹配广告集合会拦截；Loon / Quantumult X 本地产品规则优先于远程集合，"
             "所以必须用自有拦截条目前置，或者按官方依据放进误杀例外）：")
    L.append("")
    L.append("| 上游条目 | 所在产品规则 | 组 | 处理 |")
    L.append("|---|---|---|---|")
    for x in result["ads_under_products"]:
        L.append(f"| `{x['entry']}` | `{x['product_rule']}` | {x['group']} | {x['handled_by']} |")
    L.append("")
    cov = result["ads_covering_rules"]
    L.append(f"比产品规则更宽、会把整条规则拦掉的上游条目：{len(cov)} 条。")
    for x in cov:
        L.append(f"- `{x['entry']}` 覆盖 `{x['rule']}`（{x['group']}）" + ("，已有误杀例外" if x["exception"] else ""))
    L.append("")
    L.append("## 映射列表中未收录的上游条目")
    L.append("")
    L.append("以下只列数量（汇总列表不统计）。未覆盖的主要是防御性注册域名、公司官网 / 招聘站、CNAME 目标、共享设施，"
             "以及对地区不敏感的静态资源；它们落入国外默认或国内兜底规则。值得说明的取舍写在各服务的 shared_excluded。")
    L.append("")
    L.append("| 上游列表 | 映射到的服务 | 域名条目 | 本项目未覆盖 |")
    L.append("|---|---|---|---|")
    for lst, sids, total, n in missing_by_service:
        L.append(f"| `{lst}` | {', '.join(sids)} | {total} | {n} |")
    L.append("")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def missing_counts(m, dlc_repo, bm7_repo):
    """按上游列表统计：列表里的域名条目有多少不被本项目任何规则覆盖（汇总列表不统计）。"""
    dlc_own, _ = parse_dlc(os.path.join(dlc_repo, "data"))
    names = {n for s in m.services for n in s.upstream.get("bm7", [])}
    bm7_own, _ = parse_bm7(bm7_repo, names)
    rules = [r for s in m.services for r in s.rules if r.kind in ("domain", "suffix")]
    rules += [r for r in build_plan(m).ads_local]
    mapped = OrderedDict()
    for s in m.services:
        if s.file == "local.yaml":
            continue
        for src in ("dlc", "bm7"):
            for lst in s.upstream.get(src, []):
                if (src == "dlc" and dlc_is_aggregate(lst)) or (src == "bm7" and lst in BM7_AGGREGATES):
                    continue
                mapped.setdefault((src, lst), []).append(s.id)
    out = []
    for (src, lst), sids in mapped.items():
        own = dlc_own if src == "dlc" else bm7_own
        entries = [(k, v) for k, v, _ in own.get(lst, []) if k in ("domain", "full") and "." in v]
        n = sum(1 for k, v in entries
                if not any((r.kind == "suffix" and suffix_match(v, r.value)) or (r.kind == "domain" and v == r.value) for r in rules))
        out.append((f"{src}:{lst}", sids, len(entries), n))
    return out


def dump_record(result) -> str:
    """每条记录占一行，便于比较不同快照之间的差异。"""
    out = ["{"]
    keys = list(result)
    for i, k in enumerate(keys):
        v = result[k]
        tail = "," if i < len(keys) - 1 else ""
        if isinstance(v, list):
            out.append(f" {json.dumps(k)}: [")
            for j, item in enumerate(v):
                out.append("  " + json.dumps(item, ensure_ascii=False) + ("," if j < len(v) - 1 else ""))
            out.append(" ]" + tail)
        else:
            out.append(f" {json.dumps(k)}: " + json.dumps(v, ensure_ascii=False) + tail)
    out.append("}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dlc", required=True)
    ap.add_argument("--bm7", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    m, result, failures, upgrade, differ, counts = run(a.dlc, a.bm7)
    for src, s in result["snapshots"].items():
        print(f"{src} 快照：{s['commit']}（{s['date']}）")
    sm = result["summary"]
    print(f"核对域名规则 {sm['rules_checked']} 条，社区来源 {sm['community_rules']} 条；"
          f"产品规则下的上游广告条目 {len(result['ads_under_products'])} 条；更宽的广告条目 {len(result['ads_covering_rules'])} 条")
    print("按证据与结果：" + "，".join(f"{ev}/{st} {n}" for (ev, st), n in sorted(counts.items())))
    for u in upgrade:
        print("可升级：" + u)
    for d in sorted(set(differ)):
        print("归属差异：" + d)
    if a.write:
        os.makedirs(os.path.dirname(RECORD), exist_ok=True)
        with open(RECORD, "w", encoding="utf-8") as f:
            f.write(dump_record(result))
        write_report(m, result, failures, upgrade, differ, counts, missing_counts(m, a.dlc, a.bm7))
        print(f"已写入 {os.path.relpath(RECORD, ROOT)} 与 {os.path.relpath(REPORT, ROOT)}")
    if failures:
        print(f"检查不通过（{len(failures)} 项）：")
        for f in failures:
            print("  - " + f)
        return 1
    print("检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

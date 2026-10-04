"""生成逐条收录 / 排除依据文档（docs/04-规则清单与证据.md）。"""
from __future__ import annotations

import json
import os
from collections import OrderedDict

from .model import COMMUNITY_EV_SOURCE, Model, Plan

KIND_ZH = {"domain": "精确域名", "suffix": "域名后缀", "keyword": "关键词", "ip4": "IPv4 段", "ip6": "IPv6 段"}
EV_ZH = {"official": "官方（已查阅）", "official-unfetched": "官方（未能重新抓取，需复核）",
         "community": "社区规则集", "maintainer": "维护者知识（需实测）"}
STATUS_ZH = {"same": "同值", "covered": "上级域名覆盖", "covered-aggregate": "仅汇总列表覆盖",
             "narrower": "上游更窄", "absent": "未找到"}


def _load_record(root: str) -> dict:
    """读取上游快照核对记录（没有时返回空，文档里相应一栏显示“—”）。"""
    path = os.path.join(root, "docs", "evidence", "upstream-snapshot.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {(r["service"], r["kind"], r["value"]): r for r in data.get("rules", [])}


def _upstream_cell(rec, ev) -> str:
    if not rec:
        return "—"
    src = COMMUNITY_EV_SOURCE.get(ev)
    order = [src] if src else ["dlc", "bm7"]
    for s in order:
        x = rec.get(s) or {}
        st = x.get("status", "absent")
        if st != "absent" or src:
            hit = f"：`{x['hits'][0]}`" if x.get("hits") else ""
            return f"{s} {STATUS_ZH.get(st, st)}{hit}"
    return "未找到"


def write_audit(m: Model, plan: Plan, path: str) -> None:
    L = []
    L.append("# 规则清单与证据（自动生成，请勿手改）")
    L.append("")
    L.append(f"统一源版本：{m.project['project']['source_version']}　文档查阅日期：{m.project['project']['docs_checked']}")
    L.append("")
    L.append("每条规则记录：匹配条件、匹配类型、证据来源、性质（专属 / 共享）、说明。"
             "“排除”一栏记录官方放行清单里出现、但不归该服务的主机及理由——官方放行清单不等于产品归属表。")
    L.append("")

    # 证据统计
    counts = OrderedDict((k, 0) for k in m.evidence)
    for s in m.services:
        for r in s.rules:
            counts[r.ev] += 1
    L.append("## 证据强度统计")
    L.append("")
    L.append("| 证据 | 类型 | 规则数 |")
    L.append("|---|---|---|")
    for k, v in counts.items():
        if v:
            L.append(f"| `{k}` | {EV_ZH[m.evidence[k]['kind']]} | {v} |")
    L.append("")
    L.append("社区来源（`dlc`、`bm7-snap`）已按固定快照逐条核对：规则值必须出现在所在服务登记的上游列表里。"
             "“上游核对”一栏来自 `docs/evidence/upstream-snapshot.json`（`tools/check_upstream_evidence.py` 生成）。")
    L.append("")

    L.append("## 证据登记")
    L.append("")
    for k, e in m.evidence.items():
        url = e.get("url", "")
        checked = f"，查阅 {e['checked']}" if e.get("checked") else ""
        snap = f"，快照 `{e['snapshot']}`（{e.get('snapshot_date', '')}）" if e.get("snapshot") else ""
        L.append(f"- `{k}`（{EV_ZH[e['kind']]}{checked}{snap}）{url}  \n  {e.get('note', '')}")
    L.append("")
    record = _load_record(m.root)

    by_group = OrderedDict()
    for s in m.services:
        by_group.setdefault(s.group, []).append(s)
    L.append("## 按策略组")
    for g, services in by_group.items():
        L.append("")
        L.append(f"### {g}")
        for s in services:
            L.append("")
            L.append(f"**{s.title}**（`{s.id}`，{s.file}）")
            if s.upstream:
                L.append("")
                L.append("上游列表：" + "；".join(f"{k} " + "、".join(f"`{x}`" for x in v) for k, v in s.upstream.items()))
            if s.notes:
                L.append("")
                L.append("> " + s.notes.strip().replace("\n", " "))
            L.append("")
            L.append("| 条件 | 类型 | 证据 | 上游核对 | 性质 | 说明 |")
            L.append("|---|---|---|---|---|---|")
            for r in s.rules:
                nature = "共享" if "shared" in r.note or r.value in ("googleapis.com", "gstatic.com", "googleusercontent.com") else "专属"
                up = _upstream_cell(record.get((s.id, r.kind, r.value)), r.ev) if r.kind in ("domain", "suffix") else "—"
                L.append(f"| `{r.value}` | {KIND_ZH[r.kind]} | `{r.ev}` | {up} | {nature} | {r.note} |")
            if s.shared_excluded:
                L.append("")
                L.append("排除（不归本服务）：")
                for x in s.shared_excluded:
                    L.append(f"- `{x['host']}`（证据 `{x.get('ev', '')}`）：{x.get('why', '')}")
    L.append("")
    L.append("## 广告拦截")
    L.append("")
    L.append("远程集合（按客户端格式分别引用，内容以上游为准）：")
    for client, items in m.adblock["remote_lists"].items():
        for x in items:
            where = x.get("url") or f"{x.get('kind')}:{x.get('value')}"
            L.append(f"- {client}：{where} —— {x.get('source', '')}")
    L.append("")
    L.append("自有拦截条目：")
    for r in plan.ads_local:
        L.append(f"- `{r.value}`（{KIND_ZH[r.kind]}，证据 `{r.ev}`）{r.note}")
    L.append("")
    L.append("误杀例外（排在广告拦截之前，按业务目标放行）：")
    for r in plan.exceptions:
        L.append(f"- `{r.value}`（{KIND_ZH[r.kind]}）→ **{r.target}**，证据 `{r.ev}`；{r.note}")
    L.append("")
    L.append("HTTPDNS：暂无经过验证的条目，未启用。复写 / 脚本 / MITM：未内置。")
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

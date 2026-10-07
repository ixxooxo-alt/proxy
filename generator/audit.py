"""生成逐条收录 / 排除依据文档（docs/04-规则清单与证据.md）。"""
from __future__ import annotations

import json
import os
from collections import OrderedDict

from . import strict as strict_mod
from .model import COMMUNITY_EV_SOURCE, Model, Plan

KIND_ZH = {"domain": "精确域名", "suffix": "域名后缀", "keyword": "关键词", "ip4": "IPv4 段", "ip6": "IPv6 段"}
EV_ZH = {"official": "官方（已查阅）", "official-unfetched": "官方（未能重新抓取，需复核）",
         "community": "社区规则集", "maintainer": "维护者知识（需实测）",
         "requirement": "需求指定（照搬给定基线，未找到其他依据）",
         "imported": "从另一版导入（未找到依据）"}
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
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_audit(m, plan))


def render_audit(m: Model, plan: Plan) -> str:
    L = []
    L.append("# 规则清单与证据（自动生成，请勿手改）")
    L.append("")
    L.append(f"统一源版本：{m.project['project']['source_version']}　基线文档查阅日期：{m.project['project']['docs_checked']}"
             "（之后新增或复查的来源，逐条查阅日期见“证据来源”一节）")
    L.append("")
    L.append("每条规则记录：匹配条件、匹配类型、证据来源、性质（专属 / 共享）、说明。"
             "“排除”一栏记录官方放行清单里出现、但不归该服务的主机及理由——官方放行清单不等于产品归属表。"
             "排除项里写了“去向”的，是经过核对的断言（用上游数据的成员快照和官方内核检查四个客户端都把它交给这个组）；"
             "没写去向的只表示没有收，落到哪里取决于上游集合与解析结果。")
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
                nature = "共享" if r.nature == "shared" else "专属"
                up = _upstream_cell(record.get((s.id, r.kind, r.value)), r.ev) if r.kind in ("domain", "suffix") else "—"
                L.append(f"| `{r.value}` | {KIND_ZH[r.kind]} | `{r.ev}` | {up} | {nature} | {r.note} |")
            if s.shared_excluded:
                L.append("")
                L.append("排除（不归本服务）：")
                for x in s.shared_excluded:
                    to = ""
                    if x.get("to"):
                        to = f" **去向：{x['to']}**（核对用的主机：" + "、".join(f"`{h}`" for h in x["probe"]) + "）"
                    L.append(f"- `{x['host']}`（证据 `{x.get('ev', '')}`）：{x.get('why', '')}{to}")
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
    L += _strict_section(m, plan)
    return "\n".join(L)


def _strict_section(m: Model, plan: Plan) -> list:
    """严格版（Loon / Quantumult X 各多生成的一份配置）用到的清单：来源、条数、和本地规则的关系。"""
    st = m.strict
    suffix, full = m.cn_domains
    L = ["## 严格版（Loon / Quantumult X）用到的清单", ""]
    L.append("严格版只在这两端各多生成一份配置（`loon-strict.conf`、`quantumultx-strict.conf`），标准版不用下面这些。"
             "做法与限制见 `docs/03`“严格版”一节和 `docs/06`。")
    L.append("")
    L.append("**国内域名清单**（远程规则，排在广告集合之后，交给“国内直连”）：")
    for client in ("loon", "quantumultx"):
        for x in st["domestic_lists"][client]:
            if x.get("url"):
                L.append(f"- {client}：{x['url']}（证据 `{x.get('ev', '')}`）—— {x.get('source', '')}")
            else:
                kept_s, kept_f, dropped = strict_mod.cn_entries(m, plan, client)
                L.append(f"- {client}：`dist/{x['own']}`（自有清单，随本项目生成和发布，配置里引用的地址是 {strict_mod.own_url(m, x['own'])}）——"
                         f"后缀 {len(kept_s)} 条、精确域名 {len(kept_f)} 条；数据文件里另有 {dropped} 条已被这一端的本地规则覆盖，没有写进去")
    L.append("")
    L.append(f"自有清单的数据在 `{strict_mod.CN_DATA_REL}`（后缀 {len(suffix)} 条、精确域名 {len(full)} 条），"
             "由 `tools/update_cn_list.py` 从固定快照生成，文件头照录如下：")
    L.append("")
    for line in m.cn_data_header:
        L.append("> " + line.lstrip("# ").strip())
    L.append("")
    gone = {}
    for client in ("loon", "quantumultx"):
        kept_s, kept_f, _ = strict_mod.cn_entries(m, plan, client)
        for d in sorted((set(suffix) - set(kept_s)) | (set(full) - set(kept_f))):
            gone.setdefault(d, []).append(client)
    local = {c: [r for r in plan.lan + plan.real_ip_direct + plan.exceptions + plan.ads_local + plan.product_for(c)
                 if r.kind in ("domain", "suffix")] for c in ("loon", "quantumultx")}
    from .model import most_specific
    L.append("已被本地规则覆盖、没有写进自有清单的条目（本地规则优先于远程规则，它们的去向由本地规则决定）：")
    L.append("")
    L.append("| 条目 | 本地规则把它交给 |")
    L.append("|---|---|")
    for d, clients in gone.items():
        target = most_specific(local[clients[0]], d)
        only = "" if len(clients) == 2 else f"（只在 {clients[0]} 上）"
        L.append(f"| `{d}` | {target.target if target else '？'}{only} |")
    L.append("")
    fb = st["qx_fallback"]
    L.append(f"**域名兜底**（只有 Quantumult X 严格版）：`dist/{fb['own']}`，只有一条规则 `HOST-KEYWORD,{strict_mod.FALLBACK_KEYWORD},{strict_mod.QX_INLINE_PROXY}`，"
             "在配置里排在全部远程规则的最后，由 `force-policy` 交给“国外默认”。写法出自官方 sample.conf。")
    L.append("")
    L.append("**要真实地址的名单固定直连**（四个客户端的标准版和严格版都有，2026-10-07 起；以前只有两端的严格版。"
             "名单在 `source/project.yaml` 的 `dns.real_ip`，其中局域网后缀和系统联网检测本来就固定直连，下面是其余的）：")
    L.append("")
    for r in plan.real_ip_direct:
        L.append(f"- `{r.value}`（{KIND_ZH[r.kind]}）")
    L.append("")
    return L

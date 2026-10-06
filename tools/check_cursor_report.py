#!/usr/bin/env python3
"""对照 Cursor 云端的逐条对照明细（docs/evidence/cursor-对照明细.csv，2026-09-29），核对两件事：

1. Cursor 版的每一条规则，在本工程里进哪个组（迁入是否到位、没迁的差在哪里）；
2. 报告判为“不该收”的本工程条目，现在的处理（删除 / 保留及理由）。

只读统一源，不需要上游数据，不改任何规则。
用法：python3 tools/check_cursor_report.py [--csv PATH] [--write]
  --write  把结果写进 docs/evidence/cursor-迁入核对.md
退出码：Cursor 版条目里有“进了别的组 / 没有专门规则”且没有写明处理的，返回 1。
"""
import argparse
import csv
import os
import sys
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from generator.model import build_plan, load  # noqa: E402

CSV = os.path.join(ROOT, "docs", "evidence", "cursor-对照明细.csv")
OUT = os.path.join(ROOT, "docs", "evidence", "cursor-迁入核对.md")

# Cursor 版的分流名 → 本工程的组（名字相同的不用写）
ALIAS = {"共享基础设施": "国外默认", "局域网/保留地址": "DIRECT", "系统联网检测": "DIRECT",
         "Cursor": "Grok"}      # 2026-09-30 用户决定 Cursor 与 Grok 合并为 Grok 组

SHARED_ROOT = ("共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。"
               "Cursor 版把它显式绑到国外默认")
NARROW_GAI = "本工程按精确主机写（归 Google AI），子域会走 Google；目前没有已知子域，对现有主机结果相同"
GOOGLE_SHARED = ("设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），"
                 "Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组")

# Cursor 版条目在本工程里去向不同（或没有专门规则）时的处理说明
DIFF_NOTES = {
    "cursorvm.com": "Cursor 官方文档写明是 Grok Bot 托管计算机，本工程归远程控制（报告也建议这样挪）",
    "x.ai": "2026-09-30 用户决定 Grok / xAI 与 Cursor 合并为 Grok 组，不再归其他 AI",
    "grok.com": "2026-09-30 用户决定 Grok / xAI 与 Cursor 合并为 Grok 组，不再归其他 AI",
    "aistudio.google.com": NARROW_GAI,
    "gemini.google.com": NARROW_GAI,
    "ggpht.com": GOOGLE_SHARED, "googleapis.com": GOOGLE_SHARED,
    "googleusercontent.com": GOOGLE_SHARED, "gstatic.com": GOOGLE_SHARED,
    "copilot.ai": "归属未证实（报告也标“不确定”），不是 Microsoft 的域名；未收录，落入国外默认",
    "youtubeeducation.com": "未收录，落入国外默认（YouTube 组默认也是国外默认）",
    "www.youtubeeducation.com": "未收录，落入国外默认（YouTube 组默认也是国外默认）",
    "instagr.am": "Instagram 短链接，未收录，落入国外默认",
    "redditinc.com": "公司官网，按采纳原则不收，落入国外默认",
    "github.io": "GitHub Pages 托管第三方站点，按共享托管根域不收（见 github 服务的 shared_excluded），落入国外默认",
    **{v: SHARED_ROOT for v in ("akamai.net", "akamaihd.net", "akamaized.net", "amazonaws.com", "azure.com", "azure.net",
                                 "azureedge.net", "cloudfront.net", "edgesuite.net", "msecnd.net", "windows.net",
                                 "windowsazure.com")},
    "siri": "按 2026-09-29 补充需求，关键词换成 siri.apple.com、siri.com、applesiri.cn 三条后缀",
}

DESIGN = ("设计差异：本工程在 mihomo / sing-box 引用远程集合（category-ads-all 广告拦截，cn / geolocation-!cn / GEOIP,CN 兜底），"
          "Loon / QX 用 AdvertisingLite 广告集合与 GEOIP,CN 兜底；未命中专门规则的流量才走到这些集合。理由见 docs/03、docs/06")
BILI = "保留：需求要求港澳台内容走 Bilibili 港澳台，这些接口主机大陆与港澳台共用、按域名拆不开；代价与切换方法见 docs/06 第 5 项"
MS_FIRST = "保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面"
# 报告判为“不该收”的本工程条目
REJECT_NOTES = {
    "sora.com": "已删除（采纳）：Sora 已停服，导出页 sora.chatgpt.com 由 chatgpt.com 覆盖",
    "cursor.com": ("保留后缀：cursor.com 的子域都属于 Cursor（官网、控制台、登录跳转、文档），归 Cursor 组不会误收第三方；"
                   "证据由官方改标为 dlc（官方网络文档只列了 downloads.cursor.com）"),
    "aistudio.google.com": "保留：报告的理由是 Cursor 版已有同名后缀，对本工程不适用",
    "gemini.google.com": "保留：报告的理由是 Cursor 版已有同名后缀，对本工程不适用",
    "daily-cloudcode-pa.googleapis.com": "保留：上游 dlc 归入 Gemini Code Assist；官方清单未列，已在规则说明里注明",
    "ppl-ai-file-upload.s3.amazonaws.com": "保留：只收 Perplexity 专属的这一个存储桶主机，不收云根域（与报告认可的 Cursor 专属 S3 主机同一原则）",
    "pplx-res.cloudinary.com": "保留：只收 Perplexity 专属的这一个资源主机，不收云根域（与报告认可的 Cursor 专属 S3 主机同一原则）",
    "byteoversea.com": "已移出 TikTok（采纳），byteglb.com 一并移出",
    "byteoversea.net": "已移出 TikTok（采纳）",
    "api.bilibili.com": BILI, "app.bilibili.com": BILI, "bangumi.bilibili.com": BILI,
    "periscope.tv": "保留：域名仍属 X，归 X 组没有副作用（上游 dlc twitter 列表仍收录）",
    "pscp.tv": "保留：域名仍属 X，归 X 组没有副作用（上游 dlc twitter 列表仍收录）",
    "apple-dns.net": "保留在 Apple 组（2026-09-29 补充需求明确要求）；Apple AI 的 20 条都写在它之前",
    "ggpht.com": GOOGLE_SHARED, "googleapis.com": GOOGLE_SHARED,
    "googleusercontent.com": GOOGLE_SHARED, "gstatic.com": GOOGLE_SHARED,
    "recaptcha.net": "保留后缀：这是 Google 为访问不了 google.com 的地区准备的 reCAPTCHA 域名，子域都属于 Google；证据标维护者知识",
    "azure.com": "已移出 Microsoft（采纳），并加入共享云禁收名单",
    "bing.com": MS_FIRST, "bing.net": MS_FIRST, "live.com": MS_FIRST, "gfx.ms": MS_FIRST, "sfx.ms": MS_FIRST,
    "collector.github.com": "保留为误杀例外：mihomo / sing-box 用的 category-ads-all 会拦它，GitHub 官方 Copilot 放行清单要求放行",
    "category-ads-all": DESIGN, "cn": DESIGN, "geolocation-!cn": DESIGN, "CN": DESIGN,
}


def ip_target(plan, value):
    for r in list(plan.lan) + list(plan.service_ip):
        if r.kind in ("ip4", "ip6") and r.value == value:
            return r.target
    return None


def own_rule(m, plan, kind, value):
    """本工程里同类同值的规则（服务规则、自有拦截、误杀例外），返回 (位置, 目标)；没有返回 None。"""
    want = {"完整域名": "domain", "域名后缀": "suffix"}.get(kind)
    for s in m.services:
        for r in s.rules:
            if r.kind == want and r.value == value:
                return f"{s.id}", r.target
    for stage, rules in (("自有拦截", plan.ads_local), ("误杀例外", plan.exceptions)):
        for r in rules:
            if r.kind == want and r.value == value:
                return stage, r.target
    return None


def analyze(rows, m, plan):
    cursor_rows, reject_rows = [], []
    for r in rows:
        kind, value, group = r["规则类型"], r["规则值"], r["分流"]
        if r["本仓库有"] == "是":
            want = ALIAS.get(group, group)
            if kind in ("IPv4 段", "IPv6 段"):
                t = ip_target(plan, value)
                cat, got = ("同组" if t == want else "不同组"), t or "（无）"
            elif kind == "关键词":
                cat, got = "已替换", "Apple AI（三条后缀）"
            else:
                hosts = [value] if kind == "完整域名" else [value, "cursor-probe." + value]
                tm = [plan.intended_target(h, "mihomo") for h in hosts]
                tl = [plan.intended_target(h, "loon") for h in hosts]
                if all(t == want for t in tm + tl):
                    cat = "同组"
                elif all(t == want for t in tm) and all(t is None for t in tl):
                    cat = "同组（只写进 mihomo / sing-box）"
                elif all(t is None for t in tm):
                    cat = "无专门规则"
                else:
                    cat = "不同组"
                got = " / ".join(OrderedDict.fromkeys(str(t) if t else "兜底" for t in tm))
            cursor_rows.append(OrderedDict(group=group, kind=kind, value=value, judge=r["判断"], cat=cat, got=got,
                                           note=DIFF_NOTES.get(value, "")))
        if r["另一版有"] == "是" and r["判断"] == "不该收":
            now = own_rule(m, plan, kind, value)
            state = f"仍在（{now[0]} → {now[1]}）" if now else ("设计差异" if kind in ("域名集合", "地理 IP") else "已不在")
            reject_rows.append(OrderedDict(group=group, kind=kind, value=value, state=state,
                                           note=REJECT_NOTES.get(value, ""), why=r["理由"]))
    return cursor_rows, reject_rows


def render(cursor_rows, reject_rows, m):
    L = ["# Cursor 版迁入核对（自动生成，请勿手改）", "",
         "由 `tools/check_cursor_report.py --write` 生成。输入是 Cursor 云端的逐条对照明细 `docs/evidence/cursor-对照明细.csv`"
         "（报告里“本仓库”= Cursor 版，“另一版”= 本工程），按当前统一源 "
         f"`{m.project['project']['source_version']}` 计算每条规则的去向。",
         "“去向”按 mihomo 计算；后缀规则同时测根域和一个子域。Loon / Quantumult X 与 mihomo 不同的只有“只写进 mihomo / sing-box”那一类。", "",
         "## 一、Cursor 版的规则在本工程里进哪个组", ""]
    c = Counter(x["cat"] for x in cursor_rows)
    L.append(f"Cursor 版共 {len(cursor_rows)} 条：" + "，".join(f"{k} {v}" for k, v in c.most_common()) + "。")
    L.append("")
    L.append("| 分流 | 同组 | 同组（只写进 mihomo / sing-box） | 已替换 | 不同组 | 无专门规则 |")
    L.append("|---|---|---|---|---|---|")
    by = OrderedDict()
    for x in cursor_rows:
        by.setdefault(x["group"], Counter())[x["cat"]] += 1
    for g, cc in by.items():
        L.append(f"| {g} | {cc['同组'] or ''} | {cc['同组（只写进 mihomo / sing-box）'] or ''} | {cc['已替换'] or ''} | "
                 f"{cc['不同组'] or ''} | {cc['无专门规则'] or ''} |")
    L.append("")
    L.append("去向不同、没有专门规则或被替换的条目，逐条写明处理：")
    L.append("")
    L.append("| 分流 | 类型 | 值 | 报告判断 | 本工程去向 | 处理 |")
    L.append("|---|---|---|---|---|---|")
    for x in cursor_rows:
        if x["cat"] not in ("同组", "同组（只写进 mihomo / sing-box）"):
            L.append(f"| {x['group']} | {x['kind']} | `{x['value']}` | {x['judge']} | {x['got']} | {x['note'] or '**未说明**'} |")
    L.append("")
    L.append("“同组（只写进 mihomo / sing-box）”是国内常用网站：Loon / QX 不写这些规则，由 `GEOIP,CN` 兜底直连，原因见 `docs/06`。")
    L.append("")
    L += ["## 二、报告判为“不该收”的本工程条目", ""]
    L.append(f"共 {len(reject_rows)} 条。")
    L.append("")
    L.append("| 分流 | 类型 | 值 | 现在 | 处理 | 报告理由 |")
    L.append("|---|---|---|---|---|---|")
    for x in reject_rows:
        why = x["why"].replace("|", "／")
        L.append(f"| {x['group']} | {x['kind']} | `{x['value']}` | {x['state']} | {x['note'] or '**未说明**'} | {why} |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=CSV)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    with open(a.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    m = load(ROOT, include_local=False)
    plan = build_plan(m)
    cursor_rows, reject_rows = analyze(rows, m, plan)
    text = render(cursor_rows, reject_rows, m)
    missing = [x for x in cursor_rows if x["cat"] not in ("同组", "同组（只写进 mihomo / sing-box）") and not x["note"]]
    missing += [x for x in reject_rows if not x["note"]]
    c = Counter(x["cat"] for x in cursor_rows)
    print(f"Cursor 版 {len(cursor_rows)} 条：" + "，".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"报告判为不该收的本工程条目 {len(reject_rows)} 条：" + "，".join(
        f"{k} {v}" for k, v in Counter(x["state"].split("（")[0] for x in reject_rows).most_common()))
    for x in missing:
        print(f"没有写明处理：{x['group']} {x['kind']} {x['value']}")
    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入 {os.path.relpath(OUT, ROOT)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""分析 mihomo 系客户端（Clash Verge Rev / Clash Meta for Android / mihomo 内核）的连接记录，
对照统一源判断每个连接是否进了应该进的组，并找出可能漏掉的域名。

用法：
  python3 tools/check_connections.py [--service 服务id或组名] [--out 报告.md] 记录文件 [记录文件 ...]

记录文件可以是以下任意一种，可以混用：
  1. 控制接口 /logs 的输出：每行一个 JSON，{"type":"info","payload":"[TCP] ... match ... using 组[节点]"}
       curl -sN -H "Authorization: Bearer <密钥>" "http://127.0.0.1:<端口>/logs?level=info" > netflix.jsonl
     每个新连接一行，能收全；即使配置里 log-level 是 warning 也能收到（mihomo v1.19.31 源码 log/log.go）。
  2. 从 Clash Verge Rev“日志”页面复制出来的文本：每行含 “--> 主机:端口 match 规则(内容) using 组[节点]”。
  3. 控制接口 /connections 的输出：只包含保存那一刻仍在活动的连接，但带进程名。
       curl -s -H "Authorization: Bearer <密钥>" "http://127.0.0.1:<端口>/connections" > netflix-connections.json

判断方法：用统一源（source/）算出每个主机按本项目规则应进的组，与记录里实际命中的组比较。
  - 日志里的 “组[节点]” 是 mihomo 的链路写法：前面是规则指向的组，方括号里是最终节点
    （mihomo 源码 constant/adapters.go 的 Chain.String()）；/connections 的 chains 数组里，最后一项是组、第一项是节点。
  - 与统一源不一致：客户端用的配置和统一源不是同一版，或者规则顺序有问题。退出码 1。
  - 落入国外兜底（GeoSite geolocation-!cn / Match）：本项目没有专门规则的主机。测某个服务时出现的这类主机，
    就是可能漏掉的域名，需要人工判断（第三方统计、验证码、公共 CDN 走国外默认属于正常）。
报告只包含主机名、命中的规则、组、节点名和进程名，不含来源地址、控制接口密钥或订阅信息。
Loon、Quantumult X、sing-box 的记录格式不同，本工具不支持，请截图人工核对。
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from generator.model import build_plan, load  # noqa: E402

LOG_RE = re.compile(r"\[(TCP|UDP)\] (\S+) --> (\S+) (?:match (.+?) using (.+)|doesn't match any rule using (.+)|using (.+))$")

CATEGORY_ZH = OrderedDict([
    ("mismatch", "与统一源不一致"),
    ("ads_over_product", "上游广告集合拦截了产品规则里的主机"),
    ("unexpected_rule", "命中了统一源里没有的规则"),
    ("fallback_foreign", "落入国外兜底（可能漏掉的域名）"),
    ("fallback_cn", "落入国内兜底"),
    ("ads_upstream", "上游广告集合拦截"),
    ("ok", "符合统一源"),
])


@dataclass
class Record:
    host: str
    rule: str          # mihomo 规则类型名，例如 DomainSuffix、GeoSite、Match
    payload: str       # 规则内容，例如 google.com、cn
    group: str         # 规则指向的组
    node: str          # 最终节点（或 DIRECT / REJECT）
    process: str = ""
    source: str = ""   # 来自哪个文件


def _host_of(dst: str) -> str:
    if dst.startswith("["):                       # [IPv6]:端口
        return dst[1:dst.index("]")].lower()
    return (dst.rsplit(":", 1)[0] if dst.count(":") == 1 else dst).lower()


def _split_rule(text: str):
    m = re.match(r"^([A-Za-z0-9-]+)(?:\((.*)\))?$", text.strip())
    return (m.group(1), m.group(2) or "") if m else (text.strip(), "")


def _split_chain(text: str):
    """"Google[日本 01]" -> ("Google", "日本 01")；"DIRECT" -> ("DIRECT", "DIRECT")。
    组名不含方括号，节点名可能含，所以按第一个 “[” 切分。"""
    text = text.strip()
    if text.endswith("]") and "[" in text:
        i = text.index("[")
        return text[:i], text[i + 1:-1]
    return text, text


def parse_log_line(line: str, source: str = "") -> Optional[Record]:
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            line = str(obj.get("payload") or obj.get("message") or "")
    m = LOG_RE.search(line)
    if not m:
        return None
    _net, _src, dst, rule, chain_matched, chain_none, chain_special = m.groups()
    if rule:
        rtype, payload = _split_rule(rule)
        chain = chain_matched
    elif chain_none:
        rtype, payload, chain = "(未匹配规则)", "", chain_none
    else:
        rtype, payload, chain = "(特殊出站)", "", chain_special
    group, node = _split_chain(chain)
    return Record(_host_of(dst), rtype, payload, group, node, source=source)


def parse_connections(obj: dict, source: str = "") -> List[Record]:
    out = []
    for c in obj.get("connections") or []:
        md = c.get("metadata") or {}
        host = (md.get("host") or md.get("sniffHost") or md.get("destinationIP") or "").lower()
        chains = c.get("chains") or []
        out.append(Record(host, c.get("rule", ""), c.get("rulePayload", ""),
                          chains[-1] if chains else "", chains[0] if chains else "",
                          md.get("process", ""), source))
    return out


def read_records(paths: Iterable[str]) -> List[Record]:
    records: List[Record] = []
    for p in paths:
        name = os.path.basename(p)
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        try:
            whole = json.loads(text)
        except ValueError:
            whole = None
        if isinstance(whole, dict) and "connections" in whole:
            records += parse_connections(whole, name)
            continue
        for line in text.splitlines():
            r = parse_log_line(line, name)
            if r and r.host:
                records.append(r)
    return records


class Expectation:
    """按统一源算出主机应进的组；本项目没有专门规则时返回 None（交给 GeoSite / GeoIP / MATCH 兜底）。"""

    def __init__(self, plan):
        self.plan = plan
        self.ip_rules = [r for r in plan.lan if r.kind in ("ip4", "ip6")] + list(plan.service_ip)

    def target(self, host: str) -> Optional[str]:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return self.plan.intended_target(host)
        for r in self.ip_rules:
            net = ipaddress.ip_network(r.value)
            if ip.version == net.version and ip in net:
                return r.target
        return None


def classify(rec: Record, expected: Optional[str]) -> str:
    ads_remote = rec.rule == "GeoSite" and rec.payload == "category-ads-all"
    if expected is not None:
        if rec.group == expected:
            return "ok"
        return "ads_over_product" if ads_remote else "mismatch"
    if ads_remote:
        return "ads_upstream"
    if rec.group == "国内直连" and rec.rule in ("GeoSite", "GeoIP"):
        return "fallback_cn"
    if rec.group == "国外默认" and (rec.rule == "Match" or (rec.rule == "GeoSite" and rec.payload.startswith("geolocation"))):
        return "fallback_foreign"
    return "unexpected_rule"


def resolve_service(m, key: Optional[str]):
    """--service 可以是服务 id（如 netflix）或组名（如 Netflix）。返回 (说明, 组名集合)。"""
    if not key:
        return None, set()
    for s in m.services:
        if s.id == key:
            return f"服务 `{s.id}`（{s.title}）→ 组 {s.group}", {s.group}
    if key in m.group_names or key in ("DIRECT", "国内直连"):
        return f"组 {key}", {key}
    raise SystemExit(f"找不到服务或组：{key}（服务 id 见 docs/04-规则清单与证据.md）")


def analyze(records: List[Record], m, plan, service: Optional[str] = None):
    exp = Expectation(plan)
    label, groups = resolve_service(m, service)
    rows = OrderedDict()                      # (host, rule, payload, group) -> 统计
    for r in records:
        e = exp.target(r.host)
        key = (r.host, r.rule, r.payload, r.group)
        if key not in rows:
            rows[key] = {"host": r.host, "rule": r.rule, "payload": r.payload, "group": r.group,
                         "expected": e, "category": classify(r, e), "count": 0,
                         "nodes": set(), "processes": set(), "files": set()}
        x = rows[key]
        x["count"] += 1
        if r.node and r.node != r.group:
            x["nodes"].add(r.node)
        if r.process:
            x["processes"].add(r.process)
        if r.source:
            x["files"].add(r.source)
    by_cat = defaultdict(list)
    for x in rows.values():
        by_cat[x["category"]].append(x)
    for v in by_cat.values():
        v.sort(key=lambda x: (-x["count"], x["host"]))
    return {"label": label, "groups": groups, "records": len(records),
            "hosts": len({r.host for r in records}), "by_cat": by_cat}


def _rule_text(x):
    return f"{x['rule']}({x['payload']})" if x["payload"] else x["rule"]


def _join(values, limit=3):
    v = sorted(values)
    return "、".join(v[:limit]) + ("…" if len(v) > limit else "")


def render(result, m, files) -> str:
    L = ["# 连接记录分析", ""]
    L.append(f"- 记录文件：{', '.join(os.path.basename(f) for f in files)}；共 {result['records']} 条记录，{result['hosts']} 个不同主机")
    L.append(f"- 对照的统一源版本：{m.project['project']['source_version']}")
    if result["label"]:
        L.append(f"- 本次测试的对象：{result['label']}")
    L.append("")
    L.append("## 结论")
    L.append("")
    cats = result["by_cat"]
    for k, zh in CATEGORY_ZH.items():
        L.append(f"- {zh}：{len(cats.get(k, []))} 个主机")
    L.append("")
    if cats.get("mismatch") or cats.get("unexpected_rule"):
        L.append("**有与统一源不一致的连接。** 先确认客户端正在用的是这一版生成的配置（`dist/manifest.json` 的版本），"
                 "如果版本一致，把这份报告发回来排查。")
        L.append("")

    def table(key, title, note, with_expected=False):
        items = cats.get(key, [])
        if not items:
            return
        L.append(f"## {title}")
        L.append("")
        if note:
            L.append(note)
            L.append("")
        head = "| 主机 | " + ("应进的组 | " if with_expected else "") + "命中的规则 | 实际的组 | 次数 | 节点 | 进程 |"
        L.append(head)
        L.append("|" + "---|" * (head.count("|") - 1))
        for x in items:
            L.append(f"| `{x['host']}` | " + (f"{x['expected']} | " if with_expected else "")
                     + f"{_rule_text(x)} | {x['group']} | {x['count']} | {_join(x['nodes'])} | {_join(x['processes'])} |")
        L.append("")

    table("mismatch", "与统一源不一致", "按统一源应进的组和实际命中的组不同。", True)
    table("ads_over_product", "上游广告集合拦截了产品规则里的主机",
          "统一源把这些主机归给了业务组，但客户端先用上游广告集合拦掉了（上游新加的条目？）。确认是否误杀，"
          "需要的话加进 `source/adblock.yaml` 的误杀例外或自有拦截。", True)
    table("unexpected_rule", "命中了统一源里没有的规则", "通常说明客户端用的不是这一版配置。")
    note = ("本项目没有专门规则、最后走国外默认的主机。"
            + ("测试这个服务时出现的这类主机，就是可能漏掉的域名，" if result["label"] else "")
            + "请逐个判断：属于该服务自己的（接口、播放、CDN）应补进 `source/services/*.yaml`；"
              "第三方统计、验证码、公共 CDN 走国外默认属于正常。")
    table("fallback_foreign", "落入国外兜底", note)
    table("fallback_cn", "落入国内兜底", "解析到国内或在国内域名集合里，直连。一般正常；如果其中有境外服务的主机，说明归属需要调整。")

    ok = cats.get("ok", []) + cats.get("ads_upstream", [])
    if ok:
        L.append("## 符合预期的连接（按组汇总）")
        L.append("")
        per_group = defaultdict(list)
        for x in ok:
            per_group[x["group"]].append(x)
        target = result["groups"]
        L.append("| 组 | 主机数 | 例子 |")
        L.append("|---|---|---|")
        for g in sorted(per_group, key=lambda g: (g not in target, -len(per_group[g]), g)):
            xs = per_group[g]
            mark = "（本次测试对象）" if g in target else ""
            L.append(f"| {g}{mark} | {len(xs)} | {_join({x['host'] for x in xs}, 4)} |")
        L.append("")
        if target and not any(g in target for g in per_group):
            L.append(f"**注意：没有任何连接进入 {'、'.join(sorted(target))}。** 可能是测试时没有产生新连接（先关掉浏览器或 App 再测），"
                     "也可能是这个服务的域名都没被收录。")
            L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--service", help="本次测试的服务 id（如 netflix）或组名（如 Netflix）")
    ap.add_argument("--out", help="报告写到这个文件（默认打印到屏幕）")
    a = ap.parse_args(argv)
    m = load(ROOT)
    plan = build_plan(m)
    records = read_records(a.files)
    if not records:
        print("没有从记录文件里解析出任何连接。请确认是 /logs、/connections 的输出，或从“日志”页面复制的文本。", file=sys.stderr)
        return 2
    result = analyze(records, m, plan, a.service)
    report = render(result, m, a.files)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"报告已写入 {a.out}")
    else:
        print(report)
    bad = len(result["by_cat"].get("mismatch", [])) + len(result["by_cat"].get("unexpected_rule", []))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

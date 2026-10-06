"""写盘前的结构检查（审核 F09）：生成的配置里，每个组成员、规则目标都要能找到，组之间不能循环引用，
sing-box 的出站标签不能重名。以前这些只在单独运行测试时检查，正常生成不会拦住坏配置。

这里的解析只看结构（名字和引用），不模拟匹配；匹配行为由 tests/ 里独立写的模拟器检查。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Set

import yaml

BUILTIN = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}


def _sections(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(line)
    return out


def _cycles(graph: Dict[str, List[str]]) -> List[str]:
    """返回第一条环（组名链），没有环返回空列表。"""
    state: Dict[str, int] = {}

    def visit(n, stack):
        state[n] = 1
        for mem in graph.get(n, []):
            if mem not in graph:
                continue
            if state.get(mem) == 1:
                return stack + [n, mem]
            if state.get(mem) is None:
                found = visit(mem, stack + [n])
                if found:
                    return found
        state[n] = 2
        return []

    for n in graph:
        if state.get(n) is None:
            found = visit(n, [])
            if found:
                return found
    return []


def check_mihomo(text: str) -> List[str]:
    c = yaml.safe_load(text)
    problems = []
    groups = {g["name"]: list(g.get("proxies") or []) for g in c.get("proxy-groups", [])}
    if len(groups) != len(c.get("proxy-groups", [])):
        problems.append("策略组重名")
    providers = set((c.get("proxy-providers") or {}).keys())
    proxies = {p["name"] for p in (c.get("proxies") or [])}
    known = set(groups) | proxies | BUILTIN
    for g in c.get("proxy-groups", []):
        for mem in g.get("proxies") or []:
            if mem not in known:
                problems.append(f"组 {g['name']} 引用了不存在的 {mem}")
        for u in g.get("use") or []:
            if u not in providers:
                problems.append(f"组 {g['name']} 引用了不存在的订阅 {u}")
        if g["name"] in (g.get("proxies") or []):
            problems.append(f"组 {g['name']} 引用了自己")
    for r in c.get("rules", []):
        parts = [x.strip() for x in r.split(",")]
        target = parts[1] if parts[0] == "MATCH" else (parts[2] if len(parts) > 2 else None)
        if target is None or target not in known:
            problems.append(f"规则 {r} 的目标不存在")
    loop = _cycles(groups)
    if loop:
        problems.append("组循环引用：" + " → ".join(loop))
    # DNS 段里 mihomo 自己会拒绝加载的两种写法（v1.19.31 config/config.go 的 parseDNS）：这里先拦住，不用等到拿官方内核去试。
    # 都和 proxy-server-nameserver（解析节点服务器地址的 DNS）有关：respect-rules 和节点专用的解析策略都要求它不为空
    dns = c.get("dns") or {}
    if not dns.get("proxy-server-nameserver"):
        if dns.get("respect-rules"):
            problems.append("dns.respect-rules 打开时 dns.proxy-server-nameserver 不能为空（mihomo 会拒绝加载）")
        if dns.get("proxy-server-nameserver-policy"):
            problems.append("写了 dns.proxy-server-nameserver-policy 时 dns.proxy-server-nameserver 不能为空（mihomo 会拒绝加载）")
    for key in ("nameserver-policy", "proxy-server-nameserver-policy"):
        for pattern, servers in (dns.get(key) or {}).items():
            if not servers:
                problems.append(f"dns.{key} 的 {pattern} 没有写 DNS 服务器")
    return problems


def check_singbox(text: str) -> List[str]:
    c = json.loads(text)
    problems = []
    tags = [o["tag"] for o in c.get("outbounds", [])] + [e["tag"] for e in c.get("endpoints", [])]
    dup = sorted({t for t in tags if tags.count(t) > 1})
    if dup:
        problems.append(f"出站标签重名：{dup}")
    known = set(tags)
    graph = {}
    for o in c.get("outbounds", []):
        if o.get("type") in ("selector", "urltest"):
            graph[o["tag"]] = list(o.get("outbounds") or [])
            for mem in o.get("outbounds") or []:
                if mem not in known:
                    problems.append(f"组 {o['tag']} 引用了不存在的 {mem}")
            if o["tag"] in (o.get("outbounds") or []):
                problems.append(f"组 {o['tag']} 引用了自己")
            if "default" in o and o["default"] not in (o.get("outbounds") or []):
                problems.append(f"组 {o['tag']} 的默认值 {o['default']} 不在成员里")
    route = c.get("route", {})
    for r in route.get("rules", []):
        if "outbound" in r and r["outbound"] not in known:
            problems.append(f"路由规则指向不存在的出站 {r['outbound']}")
    if route.get("final") and route["final"] not in known:
        problems.append(f"route.final 指向不存在的出站 {route['final']}")
    for rs in route.get("rule_set", []):
        if rs.get("download_detour") and rs["download_detour"] not in known:
            problems.append(f"规则集 {rs.get('tag')} 的下载出站不存在")
    for s in c.get("dns", {}).get("servers", []):
        if s.get("detour") and s["detour"] not in known:
            problems.append(f"DNS 服务器 {s.get('tag')} 的出站不存在")
    # 规则集与 DNS 服务器的引用（sing-box check 不一定在检查阶段报出来，这里先拦住）
    set_tags = [rs.get("tag") for rs in route.get("rule_set", [])]
    dup = sorted({t for t in set_tags if set_tags.count(t) > 1})
    if dup:
        problems.append(f"规则集标签重名：{dup}")
    dns = c.get("dns", {})
    servers = {s.get("tag") for s in dns.get("servers", [])}
    for where, rules in (("路由规则", route.get("rules", [])), ("DNS 规则", dns.get("rules", []))):
        for r in rules:
            for tag in ([r["rule_set"]] if isinstance(r.get("rule_set"), str) else r.get("rule_set") or []):
                if tag not in set_tags:
                    problems.append(f"{where}引用了不存在的规则集 {tag}")
    for r in dns.get("rules", []):
        if "server" in r and r["server"] not in servers:
            problems.append(f"DNS 规则指向不存在的服务器 {r['server']}")
    if dns.get("final") and dns["final"] not in servers:
        problems.append(f"dns.final 指向不存在的服务器 {dns['final']}")
    # 拨号解析用到的 DNS 服务器：路由规则的 resolve 动作、出站自己的 domain_resolver、route.default_domain_resolver
    for r in route.get("rules", []):
        if r.get("action") == "resolve" and r.get("server") and r["server"] not in servers:
            problems.append(f"路由规则的 resolve 动作指向不存在的 DNS 服务器 {r['server']}")
    for o in c.get("outbounds", []):
        dr = o.get("domain_resolver")
        tag = dr.get("server") if isinstance(dr, dict) else dr
        if tag and tag not in servers:
            problems.append(f"出站 {o.get('tag')} 的 domain_resolver 指向不存在的 DNS 服务器 {tag}")
    ddr = route.get("default_domain_resolver")
    tag = ddr.get("server") if isinstance(ddr, dict) else ddr
    if tag and tag not in servers:
        problems.append(f"route.default_domain_resolver 指向不存在的 DNS 服务器 {tag}")
    loop = _cycles(graph)
    if loop:
        problems.append("组循环引用：" + " → ".join(loop))
    return problems


def check_loon(text: str) -> List[str]:
    s = _sections(text)
    problems = []
    filters = {line.split("=", 1)[0].strip() for line in s.get("Remote Filter", [])}
    graph: Dict[str, List[str]] = {}
    for line in s.get("Proxy Group", []):
        name, rest = [x.strip() for x in line.split("=", 1)]
        items = [x.strip() for x in rest.split(",")]
        if name in graph:
            problems.append(f"策略组重名 {name}")
        graph[name] = [x for x in items[1:] if "=" not in x]
    known = set(graph) | filters | {"DIRECT", "REJECT"}
    for name, mem in graph.items():
        for x in mem:
            if x not in known:
                problems.append(f"组 {name} 引用了不存在的 {x}")
            if x == name:
                problems.append(f"组 {name} 引用了自己")
    for line in s.get("Rule", []):
        parts = [x.strip() for x in line.split(",")]
        target = parts[1] if parts[0] == "FINAL" else (parts[2] if len(parts) > 2 else None)
        if target not in known:
            problems.append(f"规则 {line} 的目标不存在")
    for line in s.get("Remote Rule", []):
        m = re.search(r"policy\s*=\s*([^,]+)", line)
        if not m or m.group(1).strip() not in known:
            problems.append(f"远程规则 {line} 的策略不存在")
    loop = _cycles(graph)
    if loop:
        problems.append("组循环引用：" + " → ".join(loop))
    return problems


def check_qx(text: str) -> List[str]:
    s = _sections(text)
    problems = []
    graph: Dict[str, List[str]] = {}
    for line in s.get("policy", []):
        kind, rest = line.split("=", 1)
        items = [x.strip() for x in rest.split(",")]
        name = items[0]
        if name in graph:
            problems.append(f"策略重名 {name}")
        graph[name] = [x for x in items[1:] if "=" not in x]
    known = set(graph) | {"direct", "reject", "proxy", "DIRECT", "REJECT"}
    for name, mem in graph.items():
        for x in mem:
            if x not in known:
                problems.append(f"策略 {name} 引用了不存在的 {x}")
            if x == name:
                problems.append(f"策略 {name} 引用了自己")
    for line in s.get("filter_local", []):
        parts = [x.strip() for x in line.split(",")]
        target = parts[1] if parts[0] == "final" else (parts[2] if len(parts) > 2 else None)
        if target not in known:
            problems.append(f"规则 {line} 的目标不存在")
    for line in s.get("filter_remote", []):
        m = re.search(r"force-policy\s*=\s*([^,]+)", line)
        if not m or m.group(1).strip() not in known:
            problems.append(f"远程规则 {line} 的策略不存在")
    loop = _cycles(graph)
    if loop:
        problems.append("策略循环引用：" + " → ".join(loop))
    return problems


def check_outputs(files: Dict[str, str]) -> List[str]:
    """files：{相对路径: 内容}。按文件名判断格式，返回“文件：问题”列表。"""
    out: List[str] = []
    for rel, text in sorted(files.items()):
        base = rel.rsplit("/", 1)[-1]
        if base.startswith("mihomo") and base.endswith(".yaml"):
            probs = check_mihomo(text)
        elif base.startswith("sing-box") and base.endswith(".json"):
            probs = check_singbox(text)
        elif base == "loon.conf":
            probs = check_loon(text)
        elif base == "quantumultx.conf":
            probs = check_qx(text)
        else:
            continue
        out += [f"{rel}：{p}" for p in probs]
    return out

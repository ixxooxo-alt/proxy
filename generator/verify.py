"""写盘前的结构检查（审核 F09）：生成的配置里，每个组成员、规则目标都要能找到，组之间不能循环引用，
sing-box 的出站标签不能重名。以前这些只在单独运行测试时检查，正常生成不会拦住坏配置。

这里的解析只看结构（名字和引用），不模拟匹配；匹配行为由 tests/ 里独立写的模拟器检查。

严格版（loon-strict.conf、quantumultx-strict.conf，2026-10-06）另查几条它赖以成立的结构：
  Loon：[Rule] 里每一条按 IP 判断的规则都带 no-resolve（漏一条，没命中域名规则的域名就又要在本机解析）；
  Quantumult X：[filter_remote] 的最后一条是域名兜底、交给“国外默认”，而且没有用 inserted-resource；
  两端：广告集合在前、国内域名清单在后，清单交给“国内直连”；引用的自有远程规则文件确实在这次生成的产物里；
  自有文件本身：国内清单只有域名和后缀两类规则，兜底文件只有那一条关键词规则。
Stash（stash.yaml、stash-strict.yaml，2026-10-13）另查的几条见 check_stash。
简易版（文件名带 -simple，2026-10-21）另查策略组的结构，见 check_simple；按文件名认格式（check_outputs），
认不出的配置文件算错，不再悄悄跳过（以前按完整文件名认，新文件名会被跳过，handoff/notes/simple_generator 的演示）。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Set, Tuple

import yaml

from . import strict as strict_mod

BUILTIN = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
LOON_IP_RULES = {"IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN"}


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
    # DNS 服务器地址后面的 #名字（简易版的境外 DNS 用它指定经哪个组去问）：名字必须是已有的组或节点，或者 RULES。
    # 不是的话 mihomo 不报错，而是把它当成网卡名（v1.19.31 tunnel/dns_dialer.go 的 DialContext），DNS 就悄悄断了
    for where, server in _mihomo_dns_servers(c.get("dns") or {}):
        frag = server.split("#", 1)[1] if "#" in server else ""
        for part in frag.split("&") if frag else []:
            if "=" not in part and part not in known | {"RULES"}:
                problems.append(f"dns.{where} 的 {server} 指定经 {part} 去问，但没有这个组或节点（mihomo 会把它当成网卡名）")
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


def _mihomo_dns_servers(dns: dict) -> List[Tuple[str, str]]:
    """mihomo 的 dns 段里写的全部服务器地址：[(在哪一项, 地址)]。"""
    out: List[Tuple[str, str]] = []
    for key in ("default-nameserver", "nameserver", "fallback", "proxy-server-nameserver", "direct-nameserver"):
        for x in dns.get(key) or []:
            out.append((key, str(x)))
    for key in ("nameserver-policy", "proxy-server-nameserver-policy"):
        for pattern, servers in (dns.get(key) or {}).items():
            for x in ([servers] if isinstance(servers, str) else servers or []):
                out.append((f"{key}.{pattern}", str(x)))
    return out


STASH_IP_RULES = {"IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN"}


def check_stash(text: str, strict: bool = False) -> List[str]:
    """Stash（2026-10-13）：引用都找得到、组不循环；另查两条这份配置赖以成立的结构——
      每个按节点筛选的组（include-all + filter），筛选正则正好选中一个占位节点（名字以“·无可用节点”结尾的那几个）：
        Stash 的文档说没有代理的组会被当作直连，占位节点保证组永远不空（这里用 Python 的正则判断；Stash 的引擎未知）；
        筛选也不能选中内置策略的名字（DIRECT、REJECT、REJECT-DROP，大小写的几种写法都试）：文档说远程代理集为空时以 DIRECT 替代
        （2026-10-14，GPT 审核 r16 的 R16-F01：以前“其他地区”的筛选会收它，这里没有查）；
      严格版：每一条按 IP 判断的规则都带 no-resolve，国内域名清单（RULE-SET → 国内直连）排在广告集合、GEOSITE,geolocation-!cn 之后，
        最后一条是 MATCH,国外默认。"""
    from .emit_stash import BUILTIN_POLICIES, PLACEHOLDER_PORT, PLACEHOLDER_SERVER, PLACEHOLDER_SUFFIX
    c = yaml.safe_load(text)
    problems = []
    groups = {g["name"]: list(g.get("proxies") or []) for g in c.get("proxy-groups", [])}
    if len(groups) != len(c.get("proxy-groups", [])):
        problems.append("策略组重名")
    proxies = [p for p in (c.get("proxies") or [])]
    names = [p["name"] for p in proxies]
    if len(names) != len(set(names)):
        problems.append("代理（占位节点）重名")
    holders = [p for p in proxies if str(p.get("name", "")).endswith(PLACEHOLDER_SUFFIX)]
    for p in holders:
        if (p.get("server"), p.get("port"), p.get("type")) != (PLACEHOLDER_SERVER, PLACEHOLDER_PORT, "http"):
            problems.append(f"占位节点 {p['name']} 应该是连 {PLACEHOLDER_SERVER}:{PLACEHOLDER_PORT} 的 http 代理（连不上）")
    if len(holders) != len(proxies):
        problems.append("proxies 里只应该有占位节点（真节点从订阅来）")
    providers = set((c.get("proxy-providers") or {}).keys())
    rule_providers = c.get("rule-providers") or {}
    known = set(groups) | set(names) | BUILTIN
    for g in c.get("proxy-groups", []):
        for mem in g.get("proxies") or []:
            if mem not in known:
                problems.append(f"组 {g['name']} 引用了不存在的 {mem}")
        for u in g.get("use") or []:
            if u not in providers:
                problems.append(f"组 {g['name']} 引用了不存在的订阅 {u}")
        if g["name"] in (g.get("proxies") or []):
            problems.append(f"组 {g['name']} 引用了自己")
        if "filter" in g:
            if not g.get("include-all"):
                problems.append(f"组 {g['name']} 有 filter 却没有 include-all（本项目只按文档的 include-all + filter 写法核对过）")
            try:
                rx = re.compile(g["filter"])
            except re.error as e:
                problems.append(f"组 {g['name']} 的筛选正则 Python 也读不懂：{e}")
                continue
            hit = [p["name"] for p in holders if rx.search(p["name"])]
            if g.get("proxies"):
                # 写明了成员的组（简易版的“国外默认”：七个地区再接全部节点）不会是空组，筛选不该再选连不上的占位节点
                if hit:
                    problems.append(f"组 {g['name']} 有写明的成员，筛选却选中了占位节点 {hit}（会让人点到连不上的节点）")
            elif len(hit) != 1:
                problems.append(f"组 {g['name']} 的筛选应该正好选中一个占位节点，实际 {hit}：选不中就可能变成空组（Stash 当作直连）")
            builtin = [x for name in BUILTIN_POLICIES for x in (name, name.lower(), name.title()) if rx.search(x)]
            if builtin:
                problems.append(f"组 {g['name']} 的筛选会选中内置策略 {builtin}：订阅为空时 Stash 用 DIRECT 替代，会被它收进组里")
        elif not g.get("proxies"):
            problems.append(f"组 {g['name']} 没有成员（Stash 当作直连）")
    rules = c.get("rules", [])
    for r in rules:
        parts = [x.strip() for x in r.split(",")]
        target = parts[1] if parts[0] == "MATCH" else (parts[2] if len(parts) > 2 else None)
        if target is None or target not in known:
            problems.append(f"规则 {r} 的目标不存在")
        if parts[0] == "RULE-SET" and parts[1] not in rule_providers:
            problems.append(f"规则 {r} 引用的规则集合不存在")
    for name, rp in rule_providers.items():
        if not any(r.split(",")[:2] == ["RULE-SET", name] for r in rules):
            problems.append(f"规则集合 {name} 没有被任何规则引用")
    loop = _cycles(groups)
    if loop:
        problems.append("组循环引用：" + " → ".join(loop))
    dns = c.get("dns") or {}
    if not dns.get("nameserver"):
        problems.append("dns.nameserver 不能为空")
    for pattern, servers in (dns.get("nameserver-policy") or {}).items():
        if not servers:
            problems.append(f"dns.nameserver-policy 的 {pattern} 没有写 DNS 服务器")
    if strict:
        for r in rules:
            parts = [x.strip() for x in r.split(",")]
            if parts[0].upper() in STASH_IP_RULES and "no-resolve" not in parts[3:]:
                problems.append(f"严格版里按 IP 判断的规则 {r} 没有 no-resolve：没命中域名规则的域名又要在本机解析")
        kinds = [[x.strip() for x in r.split(",")] for r in rules]
        cn = [i for i, k in enumerate(kinds) if k[0] == "RULE-SET" and k[2] == "国内直连"]
        ads = [i for i, k in enumerate(kinds) if k[0] in ("GEOSITE", "RULE-SET") and k[2] == "广告拦截"]
        foreign = [i for i, k in enumerate(kinds) if k[:2] == ["GEOSITE", "geolocation-!cn"]]
        if not cn:
            problems.append("严格版里没有交给“国内直连”的国内域名清单（RULE-SET）")
        elif (ads and min(cn) < max(ads)) or (foreign and min(cn) < max(foreign)):
            problems.append("严格版的国内域名清单应该排在广告集合和 GEOSITE,geolocation-!cn 之后")
        if not kinds or kinds[-1] != ["MATCH", "国外默认"]:
            problems.append("严格版最后一条应该是 MATCH,国外默认")
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
    for o in c.get("outbounds", []):
        if o.get("type") == "urltest":
            # sing-box 要求检查间隔不超过 idle_timeout（v1.14.1 protocol/group/urltest.go 的 NewURLTestGroup）：
            # 超过时 sing-box check 照样通过，内核启动才失败（handoff/notes/simple_singbox/typecheck）
            iv, idle = _duration_s(o.get("interval") or "3m"), _duration_s(o.get("idle_timeout") or "30m")
            if iv is None or idle is None:
                problems.append(f"组 {o['tag']} 的 interval / idle_timeout 写法不认识：{o.get('interval')!r} / {o.get('idle_timeout')!r}")
            elif iv > idle:
                problems.append(f"组 {o['tag']} 的检查间隔 {o.get('interval')} 超过了 idle_timeout {o.get('idle_timeout')}（内核会启动失败）")
    for hc in c.get("http_clients", []):
        if hc.get("detour") and hc["detour"] not in known:
            problems.append(f"http_clients 的 {hc.get('tag')} 指向不存在的出站 {hc['detour']}")
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


_DURATION = re.compile(r"(\d+(?:\.\d+)?)(h|ms|m|s)")


def _duration_s(text: str) -> Optional[float]:
    """Go 的时长写法（300s、30m、1h30m）换成秒；不认识的返回 None。"""
    t = str(text).strip()
    parts = _DURATION.findall(t)
    if not t or "".join(n + u for n, u in parts) != t:
        return None
    return sum(float(n) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[u] for n, u in parts)


def own_files(model, files: Dict[str, str]) -> dict:
    """这次生成的自有远程规则文件：{"base": 发布前缀, "files": {地址: (相对路径, 内容)}}。
    私密产物里的严格版引用的也是这几个公开文件，所以检查私密产物时传同一份。"""
    base = model.strict["publish_base"]
    return {"base": base, "files": {base + rel: (rel, files[rel]) for rel in strict_mod.OWN_FILES if rel in files}}


def _remote_entries(lines: List[str], policy_key: str) -> List[dict]:
    out = []
    for line in lines:
        parts = [x.strip() for x in line.split(",")]
        kv = dict(x.split("=", 1) for x in parts[1:] if "=" in x)
        out.append({"url": parts[0], "policy": (kv.get(policy_key) or "").strip(), "enabled": kv.get("enabled", "true").strip(),
                    "raw": line, "flags": {k.strip() for k in kv}})
    return out


def _check_own_refs(entries: List[dict], own: Optional[dict]) -> List[str]:
    if not own:
        return []
    return [f"远程规则 {e['url']} 在自有文件的发布位置下，但这次生成的产物里没有这个文件"
            for e in entries if e["url"].startswith(own["base"]) and e["url"] not in own["files"]]


def _check_domestic_after_ads(entries: List[dict], what: str) -> List[str]:
    problems = []
    ads = [i for i, e in enumerate(entries) if e["policy"] == "广告拦截"]
    cn = [i for i, e in enumerate(entries) if e["policy"] == "国内直连"]
    if not cn:
        problems.append(f"严格版的{what}里没有交给“国内直连”的国内域名清单（国内网站会全部走代理）")
    elif ads and min(cn) < max(ads):
        problems.append(f"严格版的{what}里国内域名清单排在了广告集合前面（清单里的域名下的广告主机拦不到了）")
    for e in entries:
        if e["enabled"] != "true":
            problems.append(f"严格版的远程规则 {e['url']} 没有启用")
    return problems


def check_loon(text: str, strict: bool = False, own: Optional[dict] = None) -> List[str]:
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
    remote = _remote_entries(s.get("Remote Rule", []), "policy")
    problems += _check_own_refs(remote, own)
    if strict:
        for line in s.get("Rule", []):
            parts = [x.strip() for x in line.split(",")]
            if parts[0].upper() in LOON_IP_RULES and "no-resolve" not in parts[3:]:
                problems.append(f"严格版里按 IP 判断的规则 {line} 没有 no-resolve：没命中域名规则的域名又要在本机解析")
        problems += _check_domestic_after_ads(remote, " [Remote Rule] ")
    return problems


def check_qx(text: str, strict: bool = False, own: Optional[dict] = None) -> List[str]:
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
    remote = _remote_entries(s.get("filter_remote", []), "force-policy")
    problems += _check_own_refs(remote, own)
    if strict:
        last = remote[-1] if remote else None
        is_fallback = bool(last) and last["url"].endswith("/" + strict_mod.QX_FALLBACK_REL)
        if not is_fallback:
            problems.append("严格版 [filter_remote] 的最后一条不是域名兜底：没被前面规则接住的域名又要在本机解析")
        elif last["policy"] != "国外默认":
            problems.append(f"严格版的域名兜底交给了 {last['policy']}，应该是“国外默认”")
        if any(e["url"].endswith("/" + strict_mod.QX_FALLBACK_REL) for e in remote[:-1]):
            problems.append("严格版的域名兜底不是最后一条：排在它后面的远程规则不会再有域名命中")
        if any("inserted-resource" in e["flags"] for e in remote):
            problems.append("严格版的远程规则用了 inserted-resource：它会改变远程规则与本地规则的先后，本项目没有按这种写法核对过")
        problems += _check_domestic_after_ads(remote[:-1] if is_fallback else remote, " [filter_remote] ")
    return problems


def check_own_lists(files: Dict[str, str]) -> List[str]:
    """自有远程规则文件的内容：国内清单只能有域名、后缀两类规则；域名兜底只能有那一条关键词规则。"""
    out: List[str] = []

    def rules_of(rel):
        return [[x.strip() for x in ln.split(",")] for ln in files[rel].splitlines() if ln.strip() and not ln.startswith("#")]

    for rel, allowed, fields in ((strict_mod.LOON_CN_REL, {"DOMAIN", "DOMAIN-SUFFIX"}, 2),
                                 (strict_mod.QX_CN_REL, {"HOST", "HOST-SUFFIX"}, 3),
                                 (strict_mod.QX_MAX_REL, {"HOST", "HOST-SUFFIX"}, 3)):
        if rel not in files:
            continue
        rules = rules_of(rel)
        bad = [r for r in rules if r[0] not in allowed or len(r) != fields or not r[1]]
        if bad:
            out.append(f"{rel}：有 {len(bad)} 行不是“域名 / 后缀”规则，例如 {','.join(bad[0])}")
        if len(rules) < 1000:
            out.append(f"{rel}：只有 {len(rules)} 条，不像一份完整的国内域名清单")
        if fields == 3 and any(r[2] != strict_mod.QX_INLINE_DIRECT for r in rules if len(r) == 3):
            out.append(f"{rel}：行内的策略名应全部是 {strict_mod.QX_INLINE_DIRECT}")
    rel = strict_mod.QX_FALLBACK_REL
    if rel in files and rules_of(rel) != [["HOST-KEYWORD", strict_mod.FALLBACK_KEYWORD, strict_mod.QX_INLINE_PROXY]]:
        out.append(f"{rel}：应该只有一条 HOST-KEYWORD,{strict_mod.FALLBACK_KEYWORD},{strict_mod.QX_INLINE_PROXY}")
    return [f"{x}" for x in out]


# 配置文件的文件名（2026-10-21 起按格式认，以前按完整文件名认）：客户端、是不是简易版、是不是严格版
CONFIG_NAME = re.compile(r"^(?:(?P<mihomo>mihomo)(?P<ms>-simple)?-(?:profile|core)\.yaml"
                         r"|(?P<singbox>sing-box)(?P<ss>-simple)?-1\.1[24]\.json"
                         r"|(?P<loon>loon)(?P<ls>-simple)?(?P<lt>-strict)?\.conf"
                         r"|(?P<qx>quantumultx)(?P<qs>-simple)?(?P<qt>-strict)?\.conf"
                         r"|(?P<stash>stash)(?P<ts>-simple)?(?P<tt>-strict)?\.yaml)$")
CONFIG_SUFFIXES = (".conf", ".yaml", ".json")


def config_kind(base: str) -> Optional[Tuple[str, bool, bool]]:
    """文件名 → (客户端, 简易版?, 严格版?)；不是配置文件名返回 None。"""
    m = CONFIG_NAME.match(base)
    if not m:
        return None
    fam = next(k for k in ("mihomo", "singbox", "loon", "qx", "stash") if m.group(k))
    simple = bool(m.group({"mihomo": "ms", "singbox": "ss", "loon": "ls", "qx": "qs", "stash": "ts"}[fam]))
    strict = bool({"loon": m.group("lt"), "qx": m.group("qt"), "stash": m.group("tt")}.get(fam))
    return fam, simple, strict


def simple_spec(model) -> dict:
    """简易版的结构核对要用的名字（verify 只看文本，名字从模型取）。"""
    return {
        "regions": [r["name"] for r in model.regions],
        "other": model.other_region["name"],
        "foreign_default": next(g.name for g in model.groups if g.special == "foreign_default"),
        "mode_names": [f"{r['name']}·{x['suffix']}" for r in model.regions for x in model.project["region_modes"]],
        "dns_group": model.simple["foreign_dns_group"],
        "interval_s": model.simple["health_check_interval_s"],
    }


def _simple_common(groups: Dict[str, dict], spec: dict, with_dns: bool) -> List[str]:
    """五端共用的那几条。groups：{组名: {"kind": 类型, "members": [写明的成员], "nodes": 有没有节点筛选}}，
    类型统一成 select / url-test 等（Quantumult X 的 static 记作 select），节点筛选只记有没有。"""
    problems = []
    for name in spec["mode_names"]:
        if name in groups:
            problems.append(f"简易版里不该有完整版的模式组 {name}")
    regions = spec["regions"] + [spec["other"]]
    for name in regions:
        g = groups.get(name)
        if g is None:
            problems.append(f"简易版缺少地区组 {name}")
        elif g["kind"] != "select" or g["members"] or not g["nodes"]:
            problems.append(f"简易版的地区组 {name} 应该是只按节点筛选的选择组（里面直接是节点、不嵌套别的组）")
    fd = groups.get(spec["foreign_default"])
    if fd is None:
        problems.append(f"简易版缺少 {spec['foreign_default']}")
    elif fd["kind"] != "select" or sorted(fd["members"]) != sorted(regions) or not fd["nodes"]:
        problems.append(f"简易版的 {spec['foreign_default']} 应该是选择组：写明的成员正好是七个地区，后面再接全部节点")
    elif fd["members"][0] not in regions:
        problems.append(f"简易版的 {spec['foreign_default']} 第一项应该是一个地区")
    dg = groups.get(spec["dns_group"])
    if with_dns:
        if dg is None:
            problems.append(f"简易版缺少内部组 {spec['dns_group']}（境外 DNS 和规则下载走它）")
        elif dg["kind"] != "url-test" or dg["members"] or not dg["nodes"]:
            problems.append(f"简易版的 {spec['dns_group']} 应该是只按节点筛选的自动测速组")
    elif dg is not None:
        problems.append(f"这个客户端的简易版不该有 {spec['dns_group']}（它的 DNS 不经代理）")
    for name, g in groups.items():
        if g["kind"] != "select" and name != spec["dns_group"]:
            problems.append(f"简易版的 {name} 应该是选择组（简易版不自动换节点），实际是 {g['kind']}")
    return problems


def check_simple(fam: str, text: str, spec: Optional[dict]) -> List[str]:
    """简易版（2026-10-21，docs/10）的策略组结构：没有完整版的模式组；六个地区和“其他地区”是只按节点筛选的选择组；
    “国外默认”是选择组，写明的成员正好是七个地区、后面再接全部节点；只有 mihomo、sing-box 有内部的自动测速组
    （境外 DNS 和规则下载走它），其余都是选择组。mihomo 另查：内部组藏起来，境外 DNS 地址都经它去问，GEO 数据的下载
    交给它而且前面没有别的规则先接住，订阅上的检查间隔是简易版的间隔；sing-box 另查：境外 DNS 和规则集下载都走它。"""
    if spec is None:
        return ["简易版的结构核对缺少参数（verify.simple_spec(模型)），没法核对"]
    groups: Dict[str, dict] = {}
    problems: List[str] = []
    dns_group = spec["dns_group"]
    if fam == "loon":
        s = _sections(text)
        filters = {line.split("=", 1)[0].strip() for line in s.get("Remote Filter", [])}
        for line in s.get("Proxy Group", []):
            name, rest = [x.strip() for x in line.split("=", 1)]
            items = [x.strip() for x in rest.split(",")]
            mem = [x for x in items[1:] if "=" not in x]
            flt = [x for x in mem if x in filters]
            if flt and mem[-len(flt):] != flt:
                problems.append(f"组 {name} 的节点筛选应该排在写明的成员后面")
            groups[name] = {"kind": items[0], "members": [x for x in mem if x not in filters], "nodes": bool(flt)}
        return problems + _simple_common(groups, spec, with_dns=False)
    if fam == "qx":
        kinds = {"static": "select", "available": "fallback", "url-latency-benchmark": "url-test", "dest-hash": "load-balance",
                 "round-robin": "round-robin"}
        for line in _sections(text).get("policy", []):
            kind, rest = line.split("=", 1)
            items = [x.strip() for x in rest.split(",")]
            regex_at = [i for i, x in enumerate(items) if x.startswith("server-tag-regex=")]
            mem = [x for x in items[1:] if "=" not in x]
            if regex_at and any("=" not in x for x in items[regex_at[0]:]):
                problems.append(f"策略 {items[0]} 的 server-tag-regex 应该排在写明的成员后面")
            groups[items[0]] = {"kind": kinds.get(kind.strip(), kind.strip()), "members": mem, "nodes": bool(regex_at)}
        return problems + _simple_common(groups, spec, with_dns=False)
    if fam == "stash":
        for g in yaml.safe_load(text).get("proxy-groups", []):
            groups[g["name"]] = {"kind": g["type"], "members": list(g.get("proxies") or []),
                                 "nodes": bool(g.get("include-all") and g.get("filter"))}
            # R20-F01：Stash 默认每 600 秒给组里的代理测一次延迟（select 组也测）；纯手选用不着，每个组都要写负数关掉
            iv = g.get("interval")
            if not isinstance(iv, int) or isinstance(iv, bool) or iv >= 0:
                problems.append(f"组 {g['name']} 应该写 interval: -1（不写时 Stash 默认每 600 秒测一次延迟），实际 {iv!r}")
        return problems + _simple_common(groups, spec, with_dns=False)
    if fam == "mihomo":
        c = yaml.safe_load(text)
        for g in c.get("proxy-groups", []):
            groups[g["name"]] = {"kind": g["type"], "members": list(g.get("proxies") or []),
                                 "nodes": bool(g.get("include-all-providers") and g.get("filter"))}
            if g.get("filter") and g.get("empty-fallback") != "REJECT" and not g.get("proxies"):
                problems.append(f"组 {g['name']} 只按节点筛选，筛选为空时应该拒绝（empty-fallback: REJECT），不能悄悄直连")
        dg = next((g for g in c.get("proxy-groups", []) if g["name"] == dns_group), None)
        if dg is not None:
            if not dg.get("hidden"):
                problems.append(f"{dns_group} 是内部组，应该藏起来（hidden: true）")
            if dg.get("interval") != spec["interval_s"]:
                problems.append(f"{dns_group} 的检查间隔应该是 {spec['interval_s']} 秒，实际 {dg.get('interval')}")
        dns = c.get("dns") or {}
        foreign = [str(x) for x in dns.get("nameserver") or []]
        if not foreign or any(not x.endswith("#" + dns_group) for x in foreign):
            problems.append(f"dns.nameserver 的每个地址都应该写成“地址#{dns_group}”（经内部组去问，不跟着国外默认）：{foreign}")
        bare = {x.split("#", 1)[0] for x in foreign}
        for where, server in _mihomo_dns_servers(dns):
            if server.split("#", 1)[0] in bare and not server.endswith("#" + dns_group):
                problems.append(f"dns.{where} 用了境外 DNS {server}，没有写成经 {dns_group} 去问")
        rules = [[x.strip() for x in r.split(",")] for r in c.get("rules", [])]
        for url in (c.get("geox-url") or {}).values():
            host = str(url).split("://", 1)[-1].split("/", 1)[0]
            at = [i for i, r in enumerate(rules) if r[:3] == ["DOMAIN", host, dns_group]]
            if not at:
                problems.append(f"GEO 数据的下载主机 {host} 没有交给 {dns_group}（会跟着国外默认里手选的节点）")
                continue
            for r in rules[:at[0]]:
                if len(r) > 2 and ((r[0] == "DOMAIN" and r[1] == host) or
                                   (r[0] == "DOMAIN-SUFFIX" and (host == r[1] or host.endswith("." + r[1])))):
                    problems.append(f"GEO 数据的下载主机 {host} 先被 {','.join(r)} 接住了，交给 {dns_group} 的那条不起作用")
        for name, pv in (c.get("proxy-providers") or {}).items():
            hc = pv.get("health-check") or {}
            if hc.get("enable") and hc.get("interval") != spec["interval_s"]:
                problems.append(f"订阅 {name} 的健康检查间隔应该是简易版的 {spec['interval_s']} 秒（mihomo 按订阅上的间隔检查）")
        return problems + _simple_common(groups, spec, with_dns=True)
    if fam == "singbox":
        c = json.loads(text)
        tags = {o["tag"] for o in c.get("outbounds", []) if o.get("type") in ("selector", "urltest")}
        for o in c.get("outbounds", []):
            if o.get("type") not in ("selector", "urltest"):
                continue
            members = list(o.get("outbounds") or [])
            explicit = [x for x in members if x in tags or x == "DIRECT"]
            nodes = [x for x in members if x not in explicit]
            if explicit and nodes and members[:len(explicit)] != explicit:
                problems.append(f"组 {o['tag']} 的节点应该排在写明的成员后面")
            if explicit and o.get("type") == "selector" and o.get("default") != members[0]:
                problems.append(f"组 {o['tag']} 首次导入时应该选中第一项 {members[0]}")
            groups[o["tag"]] = {"kind": {"selector": "select", "urltest": "url-test"}[o["type"]], "members": explicit,
                                "nodes": bool(nodes)}
            if o["tag"] == dns_group and _duration_s(o.get("interval") or "") != spec["interval_s"]:
                problems.append(f"{dns_group} 的检查间隔应该是 {spec['interval_s']} 秒，实际 {o.get('interval')}")
        # 国外默认没有节点时只剩七个地区，也算对（模板里本来就没有节点）
        fd = groups.get(spec["foreign_default"])
        if fd is not None and not fd["nodes"]:
            fd["nodes"] = True
        for sv in c.get("dns", {}).get("servers", []):
            if sv.get("detour") and sv["detour"] != dns_group:
                problems.append(f"DNS 服务器 {sv.get('tag')} 经 {sv['detour']} 去问，简易版应该经 {dns_group}")
        if not any(sv.get("detour") == dns_group for sv in c.get("dns", {}).get("servers", [])):
            problems.append(f"简易版里没有经 {dns_group} 去问的 DNS 服务器")
        for hc in c.get("http_clients", []):
            if hc.get("detour") != dns_group:
                problems.append(f"http_clients 的 {hc.get('tag')} 经 {hc.get('detour')} 下载，简易版应该经 {dns_group}")
        for rs in c.get("route", {}).get("rule_set", []):
            if rs.get("type") == "remote" and rs.get("download_detour") not in (None, dns_group):
                problems.append(f"规则集 {rs.get('tag')} 经 {rs['download_detour']} 下载，简易版应该经 {dns_group}")
        return problems + _simple_common(groups, spec, with_dns=True)
    raise ValueError(fam)


def check_outputs(files: Dict[str, str], own: Optional[dict] = None, spec: Optional[dict] = None) -> List[str]:
    """files：{相对路径: 内容}。按文件名判断格式（CONFIG_NAME），返回“文件：问题”列表。
    own：这次生成的自有远程规则文件（own_files 的返回值）；给了才检查配置里对它们的引用。
    spec：简易版的结构核对要用的名字（simple_spec 的返回值）；有简易版的文件而没给它时算错，不跳过。
    后缀是 .conf / .yaml / .json 而文件名认不出的算错（manifest.json 除外），不再悄悄跳过。"""
    out: List[str] = []
    for rel, text in sorted(files.items()):
        base = rel.rsplit("/", 1)[-1]
        kind = config_kind(base)
        if kind is None:
            if base.endswith(CONFIG_SUFFIXES) and base != "manifest.json":
                out.append(f"{rel}：认不出这是哪个客户端的配置（文件名不在 verify.CONFIG_NAME 里），没有核对")
            continue
        fam, simple, strict = kind
        if fam == "mihomo":
            probs = check_mihomo(text)
        elif fam == "singbox":
            probs = check_singbox(text)
        elif fam == "loon":
            probs = check_loon(text, strict=strict, own=own)
        elif fam == "qx":
            probs = check_qx(text, strict=strict, own=own)
        else:
            probs = check_stash(text, strict=strict)
        if simple:
            probs += check_simple(fam, text, spec)
        out += [f"{rel}：{p}" for p in probs]
    out += check_own_lists(files)
    return out

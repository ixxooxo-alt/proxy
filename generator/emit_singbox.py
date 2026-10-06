"""sing-box 产物（SFA / Android）。
语法依据：sing-box v1.14.1 文档与源码（docs/configuration/**、option/*.go）。
- 1.14 版：http_clients + route.default_http_client 下载远程规则集（download_detour 在 1.14 已弃用）
- 1.12 兼容版：rule_set.download_detour（1.12–1.13 可用；1.14 仍可用但会有弃用警告）
sing-box 只有 selector / urltest 两种组，没有 fallback / load-balance，也没有订阅（节点必须内联）。"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .groups import GroupSpec, NodeFilter, build_groups
from .model import Model, Plan
from .util import Rule, dump_json

MODES = ["auto", "manual"]          # 第一个为地区入口默认值（手动优先·自动兜底无法原生实现）
PLACEHOLDER_TAG = "无可用节点"       # block 类型：筛选为空时明确拒绝，不静默直连
DIRECT_TAG = "DIRECT"
RULESET_BASE_SITE = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/"
RULESET_BASE_IP = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/"


def _compile(nf: NodeFilter):
    """sing-box 没有按名称筛选节点的字段：生成时在本机用同一条正则把节点分进各组。"""
    if nf.pinned is not None:
        return lambda name: name == nf.pinned
    rx = re.compile(nf.regex)
    return lambda name: bool(rx.search(name))


def _selectable_members(members: List[str]) -> List[str]:
    out = []
    for x in members:
        if x == "REJECT":
            continue      # sing-box 1.13+ 移除了旧的特殊出站用法，拒绝改用规则动作 reject
        out.append(DIRECT_TAG if x == "DIRECT" else x)
    return out


def _rule_obj(rules: List[Rule], outbound: Optional[str]) -> dict:
    obj: Dict[str, list] = {}
    for r in rules:
        key = {"domain": "domain", "suffix": "domain_suffix", "keyword": "domain_keyword",
               "ip4": "ip_cidr", "ip6": "ip_cidr"}[r.kind]
        obj.setdefault(key, []).append(r.value)
    if outbound is None:
        obj["action"] = "reject"
    else:
        obj["outbound"] = outbound
    return obj


def _chunk(rules: List[Rule], target_map) -> List[dict]:
    """把连续、同目标、同类（域名类 / IP 类）的规则合并成一个规则对象，保持先后顺序。"""
    out = []
    run: List[Rule] = []

    def fam(r):
        return "ip" if r.kind in ("ip4", "ip6") else "domain"

    for r in rules:
        if run and (run[-1].target != r.target or fam(run[-1]) != fam(r)):
            out.append(_rule_obj(run, target_map(run[0].target)))
            run = []
        run.append(r)
    if run:
        out.append(_rule_obj(run, target_map(run[0].target)))
    return out


def reserved_tags(m: Model) -> set:
    """配置里节点以外的全部出站标签。订阅节点不能用这些名字，否则 sing-box 报重名（审核 F02）。"""
    return {g.name for g in build_groups(m, MODES) if g.name != "广告拦截"} | {DIRECT_TAG, PLACEHOLDER_TAG}


def build(m: Model, plan: Plan, variant: str, nodes: Optional[List[dict]] = None,
          renamed: Optional[dict] = None) -> str:
    """variant: '1.14' | '1.12'；nodes: 已转换好的 sing-box 出站（None 表示模板，不含节点）；
    renamed: 转换器因重名改过的节点 {新标签: 订阅里的原名}，地区筛选与固定节点仍按原名匹配。"""
    p = m.project
    hc = m.hc
    dns = m.dns
    groups = build_groups(m, MODES)
    nodes = nodes or []
    renamed = renamed or {}
    node_tags = [n["tag"] for n in nodes]

    outbounds: List[dict] = []
    need_placeholder = False

    def pick(nf: NodeFilter) -> List[str]:
        nonlocal need_placeholder
        ok = _compile(nf)
        sel = [t for t in node_tags if ok(renamed.get(t, t))]
        if not sel:
            need_placeholder = True
            return [PLACEHOLDER_TAG]
        return sel

    for g in groups:
        if g.name == "广告拦截":
            continue          # 以规则动作 reject 实现，不作为可切换组
        if g.nodes is not None:
            members = pick(g.nodes)
        else:
            members = _selectable_members(g.members)
        if g.kind == "select":
            ob = {"type": "selector", "tag": g.name, "outbounds": members}
            if g.nodes is None and members:
                ob["default"] = members[0]
            if g.role == "paypal_fixed" and g.nodes.pinned:
                hit = [t for t in members if renamed.get(t, t) == g.nodes.pinned]
                if hit:
                    ob["default"] = hit[0]
            outbounds.append(ob)
        elif g.kind in ("url-test", "fallback"):
            # fallback 仅出现在“已验证的 Netflix 解锁入口”：sing-box 无 fallback，用同一批已验证节点间的 urltest 近似
            outbounds.append({"type": "urltest", "tag": g.name, "outbounds": members,
                              "url": hc["url_https"], "interval": f"{hc['interval_s']}s",
                              "tolerance": hc["tolerance_ms"], "idle_timeout": "30m",
                              "interrupt_exist_connections": False})
        else:
            raise ValueError(f"sing-box 不支持的组类型 {g.kind}（{g.name}）")

    outbounds.append({"type": "direct", "tag": DIRECT_TAG})
    if need_placeholder:
        outbounds.append({"type": "block", "tag": PLACEHOLDER_TAG})
    outbounds.extend(nodes)
    tags = [o["tag"] for o in outbounds]
    dup = sorted({t for t in tags if tags.count(t) > 1})
    if dup:
        raise ValueError(f"sing-box 出站标签重名：{dup}（节点名与策略组同名时应先由转换器改名）")

    def target_map(t: str) -> Optional[str]:
        if t in ("广告拦截", "REJECT"):
            return None
        return DIRECT_TAG if t == "DIRECT" else t

    # ---------- 路由规则 ----------
    rules: List[dict] = [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
    ]
    rules += _chunk(plan.lan, target_map)
    rules += _chunk(plan.exceptions, target_map)
    rules += _chunk(plan.ads_local, target_map)
    for x in m.adblock["remote_lists"]["singbox"]:
        rules.append({"rule_set": x["tag"], "action": "reject"})
    rules += _chunk(plan.product_for("singbox"), target_map)
    rules.append({"rule_set": "geosite-cn", "outbound": "国内直连"})
    rules.append({"rule_set": "geosite-geolocation-!cn", "outbound": "国外默认"})
    rules += _chunk(plan.service_ip_for("singbox"), target_map)   # 仅 IP 直连的连接（尚未解析，相当于 no-resolve）
    rules.append({"action": "resolve", "server": "dns-foreign"})   # 未分类域名经代理 DNS 解析后判断是否国内 IP
    rules.append({"rule_set": "geoip-cn", "outbound": "国内直连"})

    rule_sets = []
    remote_tags = [(x["tag"], x["url"]) for x in m.adblock["remote_lists"]["singbox"]]
    remote_tags += [("geosite-cn", RULESET_BASE_SITE + "geosite-cn.srs"),
                    ("geosite-geolocation-!cn", RULESET_BASE_SITE + "geosite-geolocation-!cn.srs"),
                    ("geoip-cn", RULESET_BASE_IP + "geoip-cn.srs")]
    for tag, url in remote_tags:
        rs = {"type": "remote", "tag": tag, "format": "binary", "url": url, "update_interval": "1d"}
        if variant == "1.12":
            rs["download_detour"] = "国外默认"
        rule_sets.append(rs)

    route = {
        "rules": rules,
        "rule_set": rule_sets,
        "final": "国外默认",
        "auto_detect_interface": True,
        "default_domain_resolver": "dns-cn",
    }
    if variant == "1.14":
        route["default_http_client"] = "经代理下载"

    # ---------- DNS ----------
    def host_of(u: str) -> str:
        return u.split("://", 1)[1].split("/", 1)[0]

    lan_sfx = set(p["lan"]["domain_suffix"])
    real_sfx = [x["suffix"] for x in dns["real_ip"] if "suffix" in x and x["suffix"] not in lan_sfx]
    real_dom = [x["domain"] for x in dns["real_ip"] if "domain" in x]
    # 不返回 AAAA 时不配置 IPv6 假地址段：v1.14.1 源码中 AAAA 在 strategy=ipv4_only 下于进入任何 DNS 传输（含 fakeip）之前
    # 就返回空结果（dns/client.go beginExchange），这里直接不给 inet6_range，让意图不依赖求值顺序。
    fakeip_server = {"type": "fakeip", "tag": "dns-fakeip", "inet4_range": dns["fakeip_v4_cidr"]}
    if dns["ipv6_answers"]:
        fakeip_server["inet6_range"] = dns["fakeip_v6"]
    dns_obj = {
        "servers": [
            {"type": "https", "tag": "dns-cn", "server": host_of(dns["domestic_doh"][0])},
            {"type": "https", "tag": "dns-foreign", "server": host_of(dns["foreign_doh"][0]), "detour": "国外默认"},
            fakeip_server,
            {"type": "local", "tag": "dns-local"},
        ],
        "rules": [
            {"domain_suffix": list(p["lan"]["domain_suffix"]), "server": "dns-local"},
            {"domain_suffix": real_sfx, "domain": real_dom, "server": "dns-cn"},
            {"rule_set": "geosite-cn", "server": "dns-cn"},
            {"query_type": ["A", "AAAA"], "server": "dns-fakeip"},
        ],
        "final": "dns-foreign",
        "strategy": "prefer_ipv4" if dns["ipv6_answers"] else "ipv4_only",
    }

    conf = {
        "log": {"level": "warn", "timestamp": True},
        "dns": dns_obj,
    }
    if variant == "1.14":
        conf["http_clients"] = [{"tag": "经代理下载", "detour": "国外默认"}]
    conf["inbounds"] = [{
        "type": "tun", "tag": "tun-in",
        "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
        "auto_route": True, "strict_route": True, "stack": "mixed",
    }]
    conf["outbounds"] = outbounds
    conf["route"] = route
    conf["experimental"] = {"cache_file": {"enabled": True, "store_fakeip": True}}
    return dump_json(conf)

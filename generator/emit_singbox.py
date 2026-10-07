"""sing-box 产物（SFA / Android）。
语法依据：sing-box v1.14.1 文档与源码（docs/configuration/**、option/*.go）。
- 1.14 版：http_clients + route.default_http_client 下载远程规则集（download_detour 在 1.14 已弃用）
- 1.12 兼容版：rule_set.download_detour（1.12–1.13 可用；1.14 仍可用但会有弃用警告）
sing-box 只有 selector / urltest 两种组，没有 fallback / load-balance，也没有订阅（节点必须内联）。"""
from __future__ import annotations

import ipaddress
import re
from typing import Dict, List, Optional, Tuple

from .groups import GroupSpec, NodeFilter, build_groups
from .model import DOMAIN_KINDS, Model, Plan
from .util import Rule, covers, dump_json

MODES = ["auto", "manual"]          # 第一个为地区入口默认值（手动优先·自动兜底无法原生实现）
PLACEHOLDER_TAG = "无可用节点"       # block 类型：筛选为空时明确拒绝，不静默直连
DIRECT_TAG = "DIRECT"
RULESET_BASE_SITE = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/"
RULESET_BASE_IP = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/"
DOMESTIC_GROUP = "国内直连"
PROXIED_SET_TAG = "product-proxied"   # 内联规则集：产品规则里不归“国内直连”的域名（DNS 规则引用两次，所以只写一份）
LOCAL_DNS_TAG = "dns-local"           # 系统 DNS：局域网里的名字只有它认识


def is_lan_name(host: str, lan_suffixes: List[str]) -> bool:
    """这个主机名是不是“只有局域网里的 DNS 认识的名字”：不带点的主机名（router、nas），
    或者以局域网后缀结尾的域名（gateway.lan、proxy.home.arpa）。IP 地址不算。"""
    h = host.strip().rstrip(".").lower()
    if not h:
        return False
    try:
        ipaddress.ip_address(h.strip("[]"))
        return False
    except ValueError:
        pass
    if "." not in h:
        return True
    return any(h == x or h.endswith("." + x) for x in (s.lower().lstrip(".") for s in lan_suffixes))


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


def dns_layers(plan: Plan) -> List[Tuple[List[Rule], List[Rule]]]:
    """把产品规则（含误杀例外）按 DNS 上的去向分层，返回 [(走代理组的, 归国内直连的), …]，先判断的在前。

    为什么需要：DNS 规则里“国内域名集合 → 国内 DNS”排在假地址之前。上游的国内域名集合会收一些本项目交给代理组的域名
    （qwen.ai、apple.com.cn、music.apple.com、recaptcha.net、google.cn、B 站的接口主机……）。不处理的话，
    这些域名先被国内 DNS 解析成真实地址，连接再按域名规则交给代理组——代理拿到的是国内解析出来的地址，
    国内 DNS 也看得到这些查询（2026-10-03 审核 F01 的 DNS 部分）。

    做法：DNS 上先按产品规则判断，和路由用同一条“更具体的规则优先”：
      - 归代理组的域名（默认直连的 Apple / Apple Music/TV 组也算：给假地址之后，直连时由直连出站用国内 DNS 解析，
        用户把组切到某个地区时由代理解析）→ 不进国内 DNS；
      - 被更具体的“国内直连”规则划出去的部分（例如 microsoft.com 下的 delivery.mp.microsoft.com）→ 仍用国内 DNS。
    分层依据“覆盖链上换了几次去向”：规则 r 被更宽的规则 b 覆盖、且两者去向不同，r 就比 b 深一层，必须先判断。
    同一层里两类规则不会同时命中同一个主机，所以层内先后无所谓。最外层（第 0 层）归国内直连的规则不用写：
    它们本来就由后面的国内域名集合或假地址规则处理，和以前一样。"""
    rules = [r for r in plan.exceptions + plan.product_for("singbox") if r.kind in DOMAIN_KINDS]
    cls = {id(r): (r.target == DOMESTIC_GROUP) for r in rules}
    depth: Dict[int, int] = {}

    def depth_of(r: Rule, stack=()) -> int:
        if id(r) in depth:
            return depth[id(r)]
        if id(r) in stack:                      # 两条规则互相覆盖只可能是同值，模型校验已拒绝重复规则
            raise ValueError(f"规则覆盖关系成环：{r.kind},{r.value}")
        d = 0
        for b in rules:
            if b is not r and covers(b.kind, b.value, r.kind, r.value) and not covers(r.kind, r.value, b.kind, b.value):
                d = max(d, depth_of(b, stack + (id(r),)) + (1 if cls[id(b)] != cls[id(r)] else 0))
        depth[id(r)] = d
        return d

    top = max((depth_of(r) for r in rules), default=0)
    layers = []
    for d in range(top, -1, -1):
        layers.append(([r for r in rules if depth[id(r)] == d and not cls[id(r)]],
                       [r for r in rules if depth[id(r)] == d and cls[id(r)]]))
    return layers


def _match_fields(rules: List[Rule]) -> dict:
    """一组域名规则 → sing-box 规则里的匹配字段（去重，保持先后）。"""
    obj: Dict[str, list] = {}
    for r in rules:
        key = {"domain": "domain", "suffix": "domain_suffix", "keyword": "domain_keyword"}[r.kind]
        if r.value not in obj.setdefault(key, []):
            obj[key].append(r.value)
    return obj


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
        elif g.kind == "url-test":
            outbounds.append({"type": "urltest", "tag": g.name, "outbounds": members,
                              "url": hc["url_https"], "interval": f"{hc['interval_s']}s",
                              "tolerance": hc["tolerance_ms"], "idle_timeout": "30m",
                              "interrupt_exist_connections": False})
        else:
            raise ValueError(f"sing-box 不支持的组类型 {g.kind}（{g.name}）")

    outbounds.append({"type": "direct", "tag": DIRECT_TAG})
    if need_placeholder:
        outbounds.append({"type": "block", "tag": PLACEHOLDER_TAG})
    # 节点的服务器地址是局域网里的名字（自己搭在家里 / 公司内网的代理）时，指定用系统 DNS 解析它。
    # 不指定的话，拨号用的是 route.default_domain_resolver（国内 DoH）：sing-box 拨号时解析服务器地址这条路
    # 不经过 dns.rules（v1.14.1 common/dialer/dialer.go 把这个解析器直接填进查询选项，dns/router.go 的 Lookup
    # 在指定了解析器时不匹配规则），所以上面“局域网后缀 → dns-local”的 DNS 规则管不到它：内部名字会被拿去问公共 DNS，
    # 查不到，节点不可用（2026-10-04 审核 r9 的 F02）。公网域名的节点不动，仍由国内 DNS 解析。
    lan_names = list(p["lan"]["domain_suffix"])
    for n in nodes:
        server = n.get("server")
        if isinstance(server, str) and "domain_resolver" not in n and is_lan_name(server, lan_names):
            n = {**n, "domain_resolver": LOCAL_DNS_TAG}
        outbounds.append(n)
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
        # 目标是“域名形式的局域网名字”时（TUN 下一般不会：应用先经 DNS 拿到地址再连；经代理协议入站、或者嗅探后改写目标时才会），
        # 先用系统 DNS 把它解析成地址，再交给下面的直连规则。不这样做的话，直连出站自己拨号时用的是默认解析器（国内 DoH），
        # 解析不了内部名字（审核 r9 的 F02 的另一半）。目标本来就是 IP 时这条规则什么都不做。
        {"domain_suffix": list(p["lan"]["domain_suffix"]), "action": "resolve", "server": LOCAL_DNS_TAG},
    ]
    rules += _chunk(plan.lan, target_map)
    rules += _chunk(plan.real_ip_direct, target_map)    # 要真实地址的名单：DNS 规则交给 dns-cn，连接也固定直连（待决事项第 15 项）
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

    layers = dns_layers(plan)
    rule_sets = [{"type": "inline", "tag": PROXIED_SET_TAG, "rules": [_match_fields(layers[-1][0])]}]
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
    # 产品规则先于国内域名集合判断（见 dns_layers 的说明）。走代理组的域名：A / AAAA 给假地址，其他类型的查询
    # （HTTPS / SVCB 等）交给经代理的 dns-foreign——都不进国内 DNS。深层（更具体）的小列表直接写在规则里，
    # 最外层的大列表写成内联规则集 product-proxied，两条规则共用一份。
    product_dns: List[dict] = []
    for i, (proxied, domestic) in enumerate(layers):
        outer = i == len(layers) - 1
        if proxied:
            match = {"rule_set": PROXIED_SET_TAG} if outer else _match_fields(proxied)
            product_dns.append({**match, "query_type": ["A", "AAAA"], "server": "dns-fakeip"})
            product_dns.append({**match, "server": "dns-foreign"})
        if domestic and not outer:
            product_dns.append({**_match_fields(domestic), "server": "dns-cn"})
    dns_obj = {
        "servers": [
            {"type": "https", "tag": "dns-cn", "server": host_of(dns["domestic_doh"][0])},
            {"type": "https", "tag": "dns-foreign", "server": host_of(dns["foreign_doh"][0]), "detour": "国外默认"},
            fakeip_server,
            {"type": "local", "tag": LOCAL_DNS_TAG},
        ],
        "rules": [
            {"domain_suffix": list(p["lan"]["domain_suffix"]), "server": LOCAL_DNS_TAG},
            {"domain_suffix": real_sfx, "domain": real_dom, "server": "dns-cn"},
            *product_dns,
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

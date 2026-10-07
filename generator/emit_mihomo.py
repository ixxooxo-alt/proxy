"""mihomo（Clash Meta）产物：内核通用版 + 客户端托管版（Clash Verge Rev / CMFA）。
语法依据：mihomo v1.19.31 源码（config/config.go、adapter/outboundgroup/*）与 https://wiki.metacubex.one/config/"""
from __future__ import annotations

from typing import Dict, List, Tuple

import yaml

from .groups import GroupSpec, build_groups, shared_filter_labels
from .model import Model, Plan
from .util import Rule, check_regex_line_safe, covers

MODES = ["manual_first", "manual", "auto", "failover", "balance"]
PROVIDER_NAME = "订阅1"
SUB_PLACEHOLDER = "https://REPLACE-ME.invalid/请替换为你的订阅链接"
DOTLESS_NAME = "*"       # mihomo 的域名通配符：单独一个 * 只匹配不带点的主机名（homeproxy、nas）


def node_server_dns_policy(lan_suffixes: List[str]) -> dict:
    """proxy-server-nameserver-policy 的内容：节点自己的服务器地址是局域网里的名字时，交给系统 DNS 解析。

    节点的服务器地址（订阅里每个节点的 server）由 proxy-server-nameserver 解析。这个解析器有自己的一套策略，
    不看 nameserver-policy；direct-nameserver-follow-policy 也只管直连出口（v1.19.31 dns/resolver.go：
    ProxyResolver 的 main 取自 ProxyServer，policy 取自 ProxyServerPolicy）。所以只在 nameserver-policy 里写
    “局域网后缀 → system”是不够的：服务器地址是 gateway.lan、proxy.home.arpa 的节点（自己搭在家里 / 公司内网的代理）
    会被拿去问国内的公共 DNS，查不到，节点不可用，内部的名字还发给了外面（2026-10-05 审核 r10 的 R10-F01）。
    两类名字，与 sing-box 那边的 is_lan_name 判断相同：
      - 以局域网后缀结尾的（+.lan 这种写法同时匹配 lan 本身和它下面的任意多级）；
      - 不带点的主机名（单独一个 *）。
    公网域名的节点不受影响，仍由 proxy-server-nameserver（国内 DNS）解析。"""
    return {
        ",".join("+." + s for s in lan_suffixes): ["system"],
        DOTLESS_NAME: ["system"],
    }


def direct_default_groups(m: Model) -> set:
    """默认直连的组（国内直连、Apple 那几个组）：组的首选是 DIRECT。"""
    return {g.name for g in m.groups if g.default == "DIRECT"} | {"DIRECT"}


def product_dns_policy(m: Model, plan: Plan) -> List[Tuple[str, bool]]:
    """nameserver-policy 里“走代理组的产品域名”这一层。返回 [(域名写法, True = 交给境外 DNS / False = 交给国内 DNS)]，
    按产品规则的先后。

    为什么要有（2026-10-07，GPT 审核 r13 的 R13-F01；待决事项第 16 项，用户选了“改”）：以前 nameserver-policy 只有
    “局域网后缀 → system”“geosite:cn,private → 国内 DNS”两条，上游国内域名集合收了、规则又交给代理组的域名（qwen.ai、
    google.cn、bilibili.tv、一批微软下载主机……）由国内 DNS 解析。以为只有设备发来的 TXT 这类查询会受影响，其实不止：
    mihomo v1.19.31 转发 UDP 时，几乎所有代理协议都先用默认解析器在本机解析目标域名（adapter/outbound/base.go 的
    ResolveUDP），WireGuard 这类出站连 TCP 也是（wireguard.go 的 DialContext）——这些域名就被交给了国内 DNS。
    官方内核实测见 handoff/notes/r13_review_probes.*。

    做法和 sing-box 的 dns_layers 一样按覆盖关系分层，只是“归哪一类”看的是规则交给的组默认直连不直连：
      - 默认走代理的组（国外默认、Google、Microsoft……）→ 境外 DNS；
      - 默认直连的组（国内直连、Apple、Apple Music/TV、Apple Push）里，被更宽的“走代理”规则覆盖的那些 → 国内 DNS
        （例如 microsoft.com 下的 delivery.mp.microsoft.com）；最外层的默认直连规则不写，和以前一样由后面的
        geosite:cn,private 或默认的 nameserver 管。
    默认直连的组不能算进“境外 DNS”：mihomo 的直连连接也按 nameserver-policy 解析（direct-nameserver-follow-policy），
    算进去的话 Apple 默认直连时会拿境外 DNS 的结果、可能变慢。sing-box 那边把它们算作走代理的一类，是因为它的直连出站
    另由 route.default_domain_resolver（国内 DNS）解析，和这里不同。
    写成一条一条的域名：mihomo 把相邻的普通域名写法合成一棵域名树，树里越具体的越优先、不看先后
    （v1.19.31 dns/resolver.go 的 makePolicy、component/trie/domain.go 的 search），和路由规则“更具体的优先”一致；
    geosite: 的条目各自单独、按书写顺序，所以这一层要写在 geosite:cn,private 之前。
    关键词规则写不进域名树；现在的产品规则里没有，有了就报错，要另想办法。"""
    direct = direct_default_groups(m)
    rules = [r for r in plan.exceptions + plan.product_for("mihomo") if r.kind in ("domain", "suffix", "keyword")]
    keyword = [f"{r.value} → {r.target}" for r in rules if r.kind == "keyword"]
    if keyword:
        raise ValueError("mihomo 的 nameserver-policy 写不了关键词规则，产品规则里出现了：" + "、".join(keyword))
    is_direct = {id(r): r.target in direct for r in rules}
    depth: Dict[int, int] = {}

    def depth_of(r: Rule, stack=()) -> int:
        if id(r) in depth:
            return depth[id(r)]
        if id(r) in stack:
            raise ValueError(f"规则覆盖关系成环：{r.kind},{r.value}")
        d = 0
        for b in rules:
            if b is not r and covers(b.kind, b.value, r.kind, r.value) and not covers(r.kind, r.value, b.kind, b.value):
                d = max(d, depth_of(b, stack + (id(r),)) + (1 if is_direct[id(b)] != is_direct[id(r)] else 0))
        depth[id(r)] = d
        return d

    out: List[Tuple[str, bool]] = []
    seen = set()
    for r in rules:
        if is_direct[id(r)] and depth_of(r) == 0:
            continue
        pattern = ("+." + r.value) if r.kind == "suffix" else r.value
        if pattern in seen:
            continue
        seen.add(pattern)
        out.append((pattern, not is_direct[id(r)]))
    return out


class _Dumper(yaml.SafeDumper):
    """映射用块格式、纯标量列表用行内格式：既好读又紧凑。"""


def _repr_list(dumper, data):
    flow = all(not isinstance(x, (list, dict)) for x in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _repr_list)


def _y(obj, dumper=None) -> str:
    return yaml.dump(obj, Dumper=dumper or _Dumper, allow_unicode=True, sort_keys=False, width=1000, default_flow_style=False)


class _DnsDumper(_Dumper):
    """dns 段：同一份服务器列表出现多次时，第一次写成锚点（&dns-foreign / &dns-domestic），之后用别名引用——
    nameserver-policy 里几百条产品域名不必每条都把两个地址抄一遍。只有同一个 Python 列表对象才会这样写。"""
    ANCHORS: Dict[Tuple[str, ...], str] = {}

    def generate_anchor(self, node):
        if isinstance(node, yaml.SequenceNode):
            name = self.ANCHORS.get(tuple(x.value for x in node.value))
            if name:
                return name
        return super().generate_anchor(node)


def _scalar(s: str) -> str:
    out = yaml.safe_dump(s, allow_unicode=True, width=10000).strip()
    if out.endswith("\n..."):
        out = out[:-4].strip()
    if out.endswith("..."):
        out = out[:-3].strip()
    return out


def rule_line(r: Rule) -> str:
    t = r.target
    if r.kind == "domain":
        return f"DOMAIN,{r.value},{t}"
    if r.kind == "suffix":
        return f"DOMAIN-SUFFIX,{r.value},{t}"
    if r.kind == "keyword":
        return f"DOMAIN-KEYWORD,{r.value},{t}"
    if r.kind == "ip4":
        return f"IP-CIDR,{r.value},{t},no-resolve"
    if r.kind == "ip6":
        return f"IP-CIDR6,{r.value},{t},no-resolve"
    raise ValueError(r.kind)


FILTER_MARK = "NODEFILTERPLACEHOLDER"      # 先占位，写出 YAML 后再换成正则或锚点引用（见 _filter_lines）


def _group_dict(m: Model, g: GroupSpec) -> dict:
    hc = m.hc
    d = {"name": g.name, "type": g.kind}
    if g.members:
        d["proxies"] = list(g.members)
    if g.nodes is not None:
        d["include-all-providers"] = True
        d["filter"] = FILTER_MARK
        d["empty-fallback"] = "REJECT"          # 筛选为空时明确拒绝，不静默 DIRECT（默认 COMPATIBLE 等同直连）
    if g.kind in ("url-test", "fallback", "load-balance"):
        d["url"] = hc["url_https"]
        d["expected-status"] = str(hc["expected_status"])
        d["interval"] = hc["interval_s"]
        d["timeout"] = hc["timeout_ms"]
        d["lazy"] = bool(hc["lazy"])
    if g.kind == "url-test":
        d["tolerance"] = hc["tolerance_ms"]
    if g.kind == "fallback":
        d["max-failed-times"] = hc["max_failed_times"]
    if g.kind == "load-balance":
        d["strategy"] = "consistent-hashing"
    if g.hidden:
        d["hidden"] = True
    icon = m.icon_url(g.name)
    if icon:
        d["icon"] = icon                          # 图标只影响显示（Clash Verge Rev 等界面读取），不影响分流
    return d


class _Filters:
    """节点筛选正则。同一条正则（每个地区的自动 / 故障转移 / 负载均衡三个组、PayPal 固定入口用的美国正则）只写一次：
    第一次出现时定义 YAML 锚点（&flt-hk），之后用别名（*flt-hk）引用。锚点 / 别名是 YAML 标准写法，
    mihomo（go-yaml）和 Clash Verge Rev 读取时会展开；这样每条约 10 KB 的正则不用重复几十遍。"""

    def __init__(self, groups: List[GroupSpec], region_ids: List[str]):
        count: dict = {}
        for g in groups:
            if g.nodes is not None:
                rx = g.nodes.final_regex()
                check_regex_line_safe(rx)          # 含反引号时 mihomo 会把它拆成多条正则
                count[rx] = count.get(rx, 0) + 1
        labels = shared_filter_labels(groups, region_ids)
        self.name = {rx: "flt-" + labels[rx] for rx, n in count.items() if n > 1}
        self.defined: set = set()

    def line(self, nf) -> str:
        rx = nf.final_regex()
        anchor = self.name.get(rx)
        if anchor is None:
            return "filter: " + _scalar(rx)
        if anchor in self.defined:
            return f"filter: *{anchor}"
        self.defined.add(anchor)
        return f"filter: &{anchor} " + _scalar(rx)


def build_rules_text(m: Model, plan: Plan) -> List[str]:
    lines: List[str] = []

    def section(title: str):
        lines.append(f"  # ==== {title} ====")

    def emit(rules: List[Rule], by_service=True):
        last = None
        for r in rules:
            if by_service and r.service != last:
                lines.append(f"  # -- {r.service} --")
                last = r.service
            lines.append("  - " + _scalar(rule_line(r)))

    section("2 局域网、内网与系统联网检测（固定直连）")
    emit(plan.lan)
    section("3a 广告误杀例外：按没有广告规则时的业务目标放行")
    emit(plan.exceptions, by_service=False)
    section("3b 自有广告 / 跟踪拦截")
    emit(plan.ads_local, by_service=False)
    section("3c 广告集合（远程数据）")
    for x in m.adblock["remote_lists"]["mihomo"]:
        lines.append("  - " + _scalar(f"GEOSITE,{x['value']},广告拦截"))
    section("4-5 产品专属、共享依赖与厂商规则（更具体的规则在前，由生成器排序）")
    emit(plan.product_for("mihomo"))
    section("6 国内外域名分类")
    lines.append("  - " + _scalar("GEOSITE,cn,国内直连"))
    lines.append("  - " + _scalar("GEOSITE,geolocation-!cn,国外默认"))
    section("7 服务专属 IP（不触发 DNS 解析）")
    emit(plan.service_ip_for("mihomo"))
    section("8 国内 IP 兜底")
    lines.append("  - " + _scalar("GEOIP,CN,国内直连"))
    section("9 其余目标")
    lines.append("  - " + _scalar("MATCH,国外默认"))
    return lines


def build(m: Model, plan: Plan, flavor: str, sub_urls: List[str] | None = None) -> str:
    """flavor: core（内核直接运行）| profile（Clash Verge Rev / CMFA 托管端口、TUN、控制面）"""
    p = m.project
    dns = m.dns
    hc = m.hc
    groups = build_groups(m, MODES)

    head = {}
    if flavor == "core":
        head.update({
            "mixed-port": p["control"]["mixed_port"],
            "allow-lan": p["control"]["allow_lan"],
            "bind-address": "127.0.0.1",
            "external-controller": p["control"]["external_controller"],
        })
    head.update({
        "mode": "rule",
        "log-level": "warning",
        "ipv6": True,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "strict",
        "profile": {"store-selected": True, "store-fake-ip": True},
        "geodata-mode": False,
        "geo-auto-update": True,
        "geo-update-interval": 24,
        "geox-url": {
            "geoip": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
            "geosite": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
            "mmdb": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb",
            "asn": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/GeoLite2-ASN.mmdb",
        },
    })
    if flavor == "core":
        head["tun"] = {
            "enable": False,
            "stack": "mixed",
            "auto-route": True,
            "auto-detect-interface": True,
            "dns-hijack": ["any:53", "tcp://any:53"],
            "strict-route": True,
        }

    real_ip = []
    for x in dns["real_ip"]:
        real_ip.append(("+." + x["suffix"]) if "suffix" in x else x["domain"])
    foreign = list(dns["foreign_doh"])          # nameserver 和产品域名那一层共用这一个列表：写出来是 &dns-foreign / *dns-foreign
    domestic_layer = list(dns["domestic_doh"])  # 被更宽的代理规则覆盖的直连规则共用：&dns-domestic / *dns-domestic
    _DnsDumper.ANCHORS = {tuple(foreign): "dns-foreign", tuple(domestic_layer): "dns-domestic"}
    policy = {",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"]}
    for pattern, to_foreign in product_dns_policy(m, plan):
        policy[pattern] = foreign if to_foreign else domestic_layer
    policy["geosite:cn,private"] = list(dns["domestic_doh"])
    dns_block = {
        "dns": {
            "enable": True,
            "ipv6": bool(dns["ipv6_answers"]),
            "enhanced-mode": "fake-ip",
            "fake-ip-range": dns["fakeip_v4"],
            "fake-ip-filter-mode": "blacklist",
            "fake-ip-filter": ["geosite:private"] + real_ip,
            "respect-rules": True,
            "default-nameserver": list(dns["domestic_plain"]),
            # 不能清空：respect-rules 依赖它（清空后 mihomo 拒绝加载），公网域名的节点也由它解析
            "proxy-server-nameserver": list(dns["domestic_doh"]),
            "proxy-server-nameserver-policy": node_server_dns_policy(p["lan"]["domain_suffix"]),
            "direct-nameserver": list(dns["domestic_doh"]),
            "nameserver": foreign,
            # 局域网后缀交给系统 DNS（路由器 / 公司内网 DNS 才认识这些名字）；接着是走代理组的产品域名那一层
            # （product_dns_policy）；geosite:cn,private 放在最后：geosite 条目按书写顺序匹配，相邻的普通域名写法合成一棵
            # 域名树、越具体的越优先。direct-nameserver-follow-policy 让 DIRECT 连接的解析也走这份策略，
            # 否则 DIRECT 出站会直接用 direct-nameserver（公共 DoH）。与 sing-box / Loon / QX 的做法一致。
            # 这些管的是“访问的目标”；节点自己的服务器地址另由上面的 proxy-server-nameserver-policy 管。
            "nameserver-policy": policy,
            "direct-nameserver-follow-policy": True,
        }
    }
    sniffer = {
        "sniffer": {
            "enable": True,
            "force-dns-mapping": True,
            "parse-pure-ip": True,
            "override-destination": False,
            "sniff": {
                "HTTP": {"ports": [80, "8080-8880"], "override-destination": True},
                "TLS": {"ports": [443, 8443]},
                "QUIC": {"ports": [443, 8443]},
            },
            "skip-domain": ["+.push.apple.com", "Mijia Cloud"],
        }
    }
    urls = sub_urls or [SUB_PLACEHOLDER]
    providers = {}
    for i, u in enumerate(urls, 1):
        providers[f"订阅{i}"] = {
            "type": "http",
            "url": u,
            "path": f"./proxy_providers/sub{i}.yaml",
            "interval": 86400,
            "proxy": "DIRECT",
            "health-check": {
                "enable": True,
                "url": hc["url_https"],
                "expected-status": str(hc["expected_status"]),
                # 与组的检查间隔一致：订阅（provider）上的间隔优先于组上的间隔（mihomo healthcheck.go 的注册逻辑）
                "interval": hc["interval_s"],
                "timeout": hc["timeout_ms"],
                "lazy": True,
            },
        }

    out: List[str] = []
    out.append("# 由统一源生成，请勿手工修改；改动请在 source/ 中进行后重新生成。")
    out.append(f"# 统一源版本 {p['project']['source_version']}；目标：{p['targets']['mihomo']['core']}")
    out.append("# 产物类型：" + ("mihomo 内核直接运行（含端口、控制面、TUN 开关）" if flavor == "core"
                           else "客户端托管版（Clash Verge Rev Windows/macOS、Clash Meta for Android：端口、TUN、控制面由客户端设置）"))
    if not sub_urls:
        out.append("# ⚠ 使用前必须把 proxy-providers 里的 url 换成你的订阅链接（当前是占位符，不可直接使用）。")
    out.append("")
    out.append(_y(head).rstrip())
    out.append("")
    out.append(_y(dns_block, _DnsDumper).rstrip())
    out.append("")
    out.append(_y(sniffer).rstrip())
    out.append("")
    out.append(_y({"proxy-providers": providers}).rstrip())
    out.append("")
    out.append("# 节点筛选（filter）：按节点名称分地区的正则，由 source/regions.yaml 的词表拼出，不手写。")
    out.append("# 每个地区两条：“手动”组用宽的（按名字归到这个地区的全部节点，含名字说不清落地的）；")
    out.append("# “自动 / 故障转移 / 负载均衡”用严的（flt-xx-auto：只收名字只指向这个地区的节点）。")
    out.append("# 同一条正则只写一次：第一次出现时用 &flt-xx 定义，之后用 *flt-xx 引用（YAML 的锚点 / 别名）。")
    out.append("# 名称只是初筛，不证明实际出口；想看每个节点进了哪个组、为什么，运行 tools/check_node_names.py。")
    out.append("proxy-groups:")
    filters = _Filters(groups, [r["id"] for r in m.regions] + [m.other_region["id"]])
    for g in groups:
        d = _group_dict(m, g)
        if g.comment:
            out.append(f"  # {g.name}：{g.comment}")
        block = _y([d]).rstrip().splitlines()
        if g.nodes is not None:
            i = block.index(f"  filter: {FILTER_MARK}")
            block[i] = "  " + filters.line(g.nodes)
        out.extend("  " + ln for ln in block)
    out.append("")
    out.append("rules:")
    out.extend(build_rules_text(m, plan))
    out.append("")
    return "\n".join(out)

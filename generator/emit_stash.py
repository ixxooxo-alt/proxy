"""Stash 产物（iPhone / iPad / Mac 共用）：标准版 stash.yaml、严格版 stash-strict.yaml（2026-10-13 加的，r16）。

语法依据：Stash 官方文档 stash.wiki。这台机器打不开 stash.wiki，用的是用户请另一个模型 2026-10-13 下载的 44 项内容
（42 个页面、站点的 llms.txt、从“配置样例”页摘出的 YAML；放在仓库以外，每个文件的 SHA-256 与包里的清单一致。
我这里没法和原网页比对；GPT 审核 r16 时和当时的官网逐字节比过，44 项都一致），见 docs/02“Stash”一节。Stash 没有能在电脑上运行的
内核，和 Loon、Quantumult X 一样只能按文档写，真机交给用户验（docs/09）。下面每一处写法后面的“文档：”指那份下载的页面。

和 mihomo 的配置（emit_mihomo.py）共用规则顺序和组的结构。不同的地方：

1. DNS。Stash 一直用假地址（文档“IPv6 兼容性”“编写高效的配置文件”两页），没有 mihomo 的 respect-rules、direct-nameserver；
   proxy-server-nameserver 文档标了 iOS 3.6 / macOS 4.3 才有（下载时最新的是 iOS 3.4.0、macOS 4.2.0），不用。
   这里 nameserver 填国内 DoH——文档“编写高效的配置文件”给中国用户的建议是用国内 DNS；局域网后缀交给 system。
   走代理的连接一般不用本机的 nameserver：TCP 通常把域名交给节点（文档“IPv6 兼容性”：“通常会尽可能地”向代理服务器转发域名——
   文档自己留了余地）；UDP 由 Stash 经代理去查再按地址转发（文档“协议类型”：UDP 只以 IP 形式转发，转发前通过代理发起 DNS 查询，
   默认问 1.0.0.1；订阅里的节点可以用 udp-nameserver 改成别的）。
   本机的 nameserver 只在这几种时候用到：直连的连接；要真实地址的名单（fake-ip-filter）；没被任何域名规则接住、要按 IP 判断的
   域名（标准版最后的 GEOIP,CN）。最后一种和 Loon、Quantumult X 的标准版一样，国内 DNS 看得到这类域名，所以 Stash 也多出一份
   严格版（见下）。
   没有采用 dns.follow-rule（让 DNS 查询按规则走，像 mihomo 那样把没分类的域名经代理交给境外 DNS）。理由都是没有验证过的成本，
   不是“做不到”（GPT 审核 r16 的 R16-F03 之后收窄的说法）：文档说“绝大部分场景下不需要开启”，DNS 经代理“可能”影响 CDN 的
   就近优化、进网络引擎会让延迟略升——没有测过，也不等于一开国内网站就变慢（geosite:cn 仍可以交给国内 DNS、直连去问）；
   “连代理服务器要先解析、解析又要经代理”的循环，文档给的三个条件满足一个即可，这份配置的 DNS 服务器本来就写成 IP；
   订阅、GEOSITE 数据第一次下载时还没有节点，境外 DNS 只能直连去问；Stash 没有 direct-nameserver 那样的分工。
   nameserver-policy 的 geosite: 键、一个键配多个服务器，在目标版本（iOS 3.4.0 / macOS 4.2.0）都已经支持，只是更早的版本不支持。
   这些都没法在这里验证，所以没有做（docs/03）。
2. 节点筛选为空。文档“策略组”：不包含任何代理的策略组会被当作 DIRECT；“远程代理集”：远程代理集为空时会以 DIRECT 替代。
   Stash 没有 mihomo 的 empty-fallback。这里给每个地区放一个连不上的占位节点（PLACEHOLDER_SERVER 的 1 号端口，没有程序在听，
   连接马上被拒绝），名字只会被这个地区的筛选正则选中（生成时用 Python 的正则核对，verify.check_stash 再查一遍）：
   这个地区一个节点都没有时，组里只剩它，连接失败而不是直连。文档“远程代理集”还说“远程代理集为空时候，会以 DIRECT 替代”
   （什么情况算为空——订阅第一次就没下载下来、订阅里一个节点都没有——文档没细说，这是推断）：每条节点筛选的开头都排除
   DIRECT、REJECT、REJECT-DROP 这几个名字（exclude_builtins；GPT 审核 r16 的 R16-F01——“其他地区”那条“六个地区都不是的都收”的
   筛选，以前会把 DIRECT 这个名字也收进组里），生成时和 verify.check_stash 都核对。
   替代进来的 DIRECT 在 App 里叫不叫这个名字、App 会不会在筛选之后另外把它塞进组里、自动测速等组会不会选到它，文档没写，
   要在真机上看（docs/09）。
3. 组。select / url-test / fallback / load-balance 都有（文档“策略组”）；节点用 include-all + filter 选（文档的例子就是这样写的）。
   筛选正则和其他三端是同一条（只在开头多排除内置策略的名字，见上一条），Stash 用什么正则引擎文档没写——见 docs/02、docs/06
   （如果是不支持否定前瞻的引擎，筛选会出错）。
   2026-10-13 下载的文档没有写 hidden，这里没有用，子组（某地区·自动 等）会显示在界面上。GPT 审核 r17（2026-10-15）说
   现行的“策略组”页面有“隐藏策略组”一节（hidden: true）；stash.wiki 在这台机器上连不上，没有核对，目标版本认不认也不知道，
   所以没有改（docs/06）。健康检查的网址写在订阅（proxy-providers 的 benchmark-url，
   文档“发布说明”2.6.5）和占位节点上——Stash 按节点测延迟；组上只写 interval、lazy（文档“策略组”的定时延迟测试）。
4. 国内外域名分类、广告集合用 Stash 自带的 GEOSITE（文档“规则类型”：domain-list-community，不随 App 分发，首次用到时从
   github.com 下载）。

严格版（strict=True）与标准版只差两处：
  1. GEOIP,CN 加 no-resolve（文档“规则类型”：可添加 no-resolve 以避免触发 DNS 解析）。这样全部按 IP 判断的规则都带 no-resolve，
     没命中域名规则的连接不为判断规则在本机解析域名，落到最后的 MATCH（国外默认）；
  2. 在 GEOSITE,geolocation-!cn 之后订阅 blackmatrix7 的 ChinaMax 域名清单（source/strict.yaml 的 domestic_lists.stash），
     交给“国内直连”——只接住两个 GEOSITE 集合都没收的域名。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .emit_mihomo import FILTER_MARK, _Dumper, _scalar, _y, rule_line
from .groups import ALL_LABEL, AUTO_SUFFIX, GroupSpec, NodeFilter, build_groups, shared_filter_labels, simple_header
from .model import Model, Plan
from .regions import lit
from .util import Rule, check_regex_line_safe

MODES = ["manual_first", "manual", "auto", "failover", "balance"]
SUB_PLACEHOLDER = "https://REPLACE-ME.invalid/请替换为你的订阅链接"
PLACEHOLDER_SUFFIX = "·无可用节点"
PLACEHOLDER_SERVER = "127.0.0.1"      # 本机；1 号端口没有程序在听，连接马上被拒绝
PLACEHOLDER_PORT = 1
DOMAIN_TEXT = "domain-text"           # 文档“配置样例”的写法（“推荐使用 text 格式”）；“规则集合”一页另有 behavior: domain + format: text
# Stash 的内置策略（文档“规则类型”：REJECT、REJECT-DROP 两个内置代理；DIRECT 是直连）。节点筛选一律不选这几个名字（不分大小写）：
# 文档“远程代理集”说远程代理集为空时以 DIRECT 替代——“其他地区”的筛选是“六个地区都不是的都收”，以前会把这个名字也收进来
# （GPT 审核 r16 的 R16-F01）。只在节点筛选上排除；业务组里写明的 DIRECT 照旧可以手动选。
BUILTIN_POLICIES = ("DIRECT", "REJECT", "REJECT-DROP")


class _QuotedWildcards(_Dumper):
    """dns 段：以 + 或 * 开头的域名写法加单引号，和文档的例子（'+.internal.crop.com'、'*.example.com'）一样。
    不加引号也是合法的 YAML（mihomo 那份就没加），这里只是不让 Stash 的解析器去猜。"""


def _repr_str(dumper, data):
    style = "'" if data.startswith(("+", "*")) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_QuotedWildcards.add_representer(str, _repr_str)


def placeholder_name(region_name: str) -> str:
    return region_name + PLACEHOLDER_SUFFIX


def placeholders(m: Model) -> Dict[str, str]:
    """{地区 id: 占位节点名}：六个地区加“其他地区”。"""
    regions = [(r["id"], r["name"]) for r in m.regions] + [(m.other_region["id"], m.other_region["name"])]
    return {rid: placeholder_name(name) for rid, name in regions}


def _region_of(m: Model, nf: NodeFilter) -> str:
    """筛选属于哪个地区：hk / hk-auto → hk；paypal → PayPal 固定入口的地区（美国）；other → other。"""
    if nf.label == "paypal":
        return m.special_entries["paypal_fixed"]["region"]
    return nf.label[:-len(AUTO_SUFFIX)] if nf.label.endswith(AUTO_SUFFIX) else nf.label


def exclude_builtins(rx: str) -> str:
    """在地区筛选正则的开头（“(?i)^”之后）加一个否定前瞻：整个名字是内置策略（BUILTIN_POLICIES，不分大小写）时不选。
    其余部分和其他三端的那一条逐字相同。"""
    head = "(?i)^"
    if not rx.startswith(head):
        raise ValueError(f"Stash：地区筛选正则应该以 {head} 开头：{rx[:40]}")
    return head + "(?!(?:" + "|".join(BUILTIN_POLICIES) + ")$)" + rx[len(head):]


def exclude_placeholders(m: Model, rx: str) -> str:
    """在筛选正则的开头（“(?i)^”和不选内置策略那一段之后）再加一个否定前瞻：整个名字是七个占位节点之一时不选。
    简易版的“国外默认”（全部节点）用：那个组里有写明的七个地区，不会是空组，用不着占位节点，也不该让人点到连不上的占位节点。"""
    head = "(?i)^"
    if not rx.startswith(head):
        raise ValueError(f"Stash：节点筛选正则应该以 {head} 开头：{rx[:40]}")
    return head + "(?!(?:" + "|".join(lit(n) for n in placeholders(m).values()) + ")$)" + rx[len(head):]


def filter_regex(m: Model, nf: NodeFilter) -> str:
    """写进 Stash 的筛选正则。地区的那几条 = 其他三端的同一条，开头另加“不选内置策略”（exclude_builtins；占位节点的名字
    本来就会被它选中）；固定节点（local.yaml 的 PayPal 固定节点）的“名称完全相同”那一条，另外允许这个地区的占位节点，
    不然那个节点被删掉以后组是空的（这一条只认两个写死的名字，不会选中内置策略，生成时照样核对）。
    简易版“国外默认”的全部节点（label all）：同一条全部节点正则，开头不选内置策略，也不选占位节点（exclude_placeholders）。"""
    if nf.pinned:
        ph = placeholders(m)[_region_of(m, nf)]
        return "^(?:" + lit(nf.pinned) + "|" + lit(ph) + ")$"
    if nf.label == ALL_LABEL:
        return exclude_builtins(exclude_placeholders(m, nf.final_regex()))
    return exclude_builtins(nf.final_regex())


def check_placeholders(m: Model, groups: List[GroupSpec]) -> None:
    """每个只按节点筛选的组，筛选正则要正好选中一个占位节点，而且是它自己地区的那个；同时有写明成员的组（简易版的“国外默认”）
    一个占位节点都不能选。也不能选中内置策略的名字（大小写的几种写法都试；GPT 审核 r16 的 R16-F01）。
    用 Python 的正则判断；Stash 的引擎未知。"""
    ph = placeholders(m)
    for g in groups:
        if g.nodes is None:
            continue
        rx = re.compile(filter_regex(m, g.nodes))
        hit = [name for name in ph.values() if rx.search(name)]
        if g.members:
            if hit:
                raise ValueError(f"Stash：组 {g.name} 有写明的成员，筛选不应该选中占位节点，实际选中 {hit}")
        else:
            want = ph[_region_of(m, g.nodes)]
            if hit != [want]:
                raise ValueError(f"Stash：组 {g.name} 的筛选应该只选中占位节点 {want}，实际选中 {hit}")
        builtin = [x for name in BUILTIN_POLICIES for x in (name, name.lower(), name.title()) if rx.search(x)]
        if builtin:
            raise ValueError(f"Stash：组 {g.name} 的筛选会选中内置策略 {builtin}（空订阅被替换成 DIRECT 时会被它收进组里）")


class _Filters:
    """同一条正则只写一次：第一次出现时用 &flt-xx 定义（YAML 锚点），之后用 *flt-xx 引用。和 mihomo 那份一样。"""

    def __init__(self, m: Model, groups: List[GroupSpec], region_ids: List[str]):
        count: dict = {}
        labels = shared_filter_labels(groups, region_ids)
        self.label = {}
        for g in groups:
            if g.nodes is not None:
                rx = filter_regex(m, g.nodes)
                check_regex_line_safe(rx)
                count[rx] = count.get(rx, 0) + 1
                self.label[rx] = labels.get(g.nodes.final_regex(), g.nodes.label)
        self.name = {rx: "flt-" + self.label[rx] for rx, n in count.items() if n > 1}
        self.defined: set = set()

    def line(self, rx: str) -> str:
        anchor = self.name.get(rx)
        if anchor is None:
            return "filter: " + _scalar(rx)
        if anchor in self.defined:
            return f"filter: *{anchor}"
        self.defined.add(anchor)
        return f"filter: &{anchor} " + _scalar(rx)


# 简易版的组都写 interval: -1（R20-F01，2026-10-23）。文档“策略组”的“定时执行延迟测试”：Stash 默认每 600 秒为组里的代理
# 测一次延迟（包括 select 组，组里有组时递归测），interval 设为负数就不定时测。简易版是纯手选、没有自动选节点的组，
# 定时测速只用来刷新显示的延迟，所以关掉（要看延迟就在 App 里手动测）。完整版不写，照旧是文档说的默认 600 秒。
SIMPLE_GROUP_INTERVAL = -1


def _group_dict(m: Model, g: GroupSpec, simple: bool = False) -> dict:
    hc = m.hc
    d = {"name": g.name, "type": g.kind}
    if g.members:
        d["proxies"] = list(g.members)
    if g.nodes is not None:
        d["include-all"] = True              # 文档“策略组”：引用所有的代理和远程代理集（含上面的占位节点），再按 filter 筛
        d["filter"] = FILTER_MARK
    if simple:
        if g.kind != "select":
            raise ValueError(f"Stash 简易版只该有选择组：{g.name} 是 {g.kind}")
        d["interval"] = SIMPLE_GROUP_INTERVAL
    if g.kind in ("url-test", "fallback", "load-balance"):
        d["interval"] = hc["interval_s"]
        d["lazy"] = bool(hc["lazy"])
    if g.kind == "load-balance":
        d["strategy"] = "consistent-hashing"  # 文档“策略组”：一般建议 consistent-hashing，避免频繁换 IP
    icon = m.icon_url(g.name)
    if icon:
        d["icon"] = icon                      # 文档“策略组图标”：只影响显示
    return d


def build_rules_text(m: Model, plan: Plan, strict: bool) -> List[str]:
    lines: List[str] = []

    def section(title: str):
        lines.append(f"  # ==== {title} ====")

    def add(line: str):
        lines.append("  - " + _scalar(line))

    def emit(rules: List[Rule], by_service=True):
        last = None
        for r in rules:
            if by_service and r.service != last:
                lines.append(f"  # -- {r.service} --")
                last = r.service
            add(rule_line(r))

    section("2 局域网、内网与系统联网检测（固定直连）")
    emit(plan.lan)
    section("2b 要真实地址的名单（dns 段 fake-ip-filter 里的那些）：先在本机由国内 DNS 解析，所以固定直连")
    emit(plan.real_ip_direct, by_service=False)
    section("3a 广告误杀例外：按没有广告规则时的业务目标放行")
    emit(plan.exceptions, by_service=False)
    section("3b 自有广告 / 跟踪拦截")
    emit(plan.ads_local, by_service=False)
    section("3c 广告集合（Stash 自带的 GEOSITE，首次用到时从 github.com 下载）")
    for x in m.adblock["remote_lists"]["stash"]:
        add(f"GEOSITE,{x['value']},广告拦截")
    section("4-5 产品专属、共享依赖与厂商规则（更具体的规则在前，由生成器排序）")
    emit(plan.product_for("stash"))
    section("6 国内外域名分类" + ("；严格版另用国内域名清单接住两个集合都没收的国内网站" if strict else ""))
    add("GEOSITE,cn,国内直连")
    add("GEOSITE,geolocation-!cn,国外默认")
    if strict:
        for x in m.strict["domestic_lists"]["stash"]:
            add(f"RULE-SET,{x['tag']},国内直连")
    section("7 服务专属 IP（不触发 DNS 解析）")
    emit(plan.service_ip_for("stash"))
    if strict:
        section("8 国内 IP：只对原本就是 IP 的连接生效（no-resolve），不为域名做本机解析")
        add("GEOIP,CN,国内直连,no-resolve")
        section("9 其余目标：包括没被任何域名规则接住的域名（不为判断规则在本机解析；按文档，TCP 一般把域名交给节点）")
    else:
        section("8 国内 IP 兜底（没被域名规则接住的域名在这里由本机的国内 DNS 解析）")
        add("GEOIP,CN,国内直连")
        section("9 其余目标")
    add("MATCH,国外默认")
    return lines


def build(m: Model, plan: Plan, sub_urls: Optional[List[str]] = None, strict: bool = False, simple: bool = False) -> str:
    """simple：简易版（docs/10，2026-10-21）。和完整版只差 proxy-groups（没有自动类的组）和几行说明。"""
    p = m.project
    dns = m.dns
    hc = m.hc
    groups = build_groups(m, MODES, "simple" if simple else "full")
    check_placeholders(m, groups)

    lan = p["lan"]["domain_suffix"]
    real_ip = [("+." + x["suffix"]) if "suffix" in x else x["domain"] for x in dns["real_ip"]]
    fake_ip_filter = list(dict.fromkeys(["+." + s for s in lan] + real_ip))
    dns_block = {"dns": {
        # 文档“内置 DNS 服务”：默认情况下 Stash 发出的 DNS 查询都直接出站；follow-rule 写明不开（不开也是默认值），原因见文件开头
        "follow-rule": False,
        "nameserver": list(dns["domestic_doh"]),
        # 局域网后缀交给系统 DNS（路由器 / 公司内网 DNS 才认识这些名字）。一个后缀一条、值写单个 system：
        # 文档的例子里有 '+.internal.crop.com': system；值写成列表、键写 geosite: 是 iOS 3.4.0 / macOS 4.2.0 加的（发布说明；目标版本支持，这里用不上）
        "nameserver-policy": {"+." + s: "system" for s in lan},
        # 这些名字拿真实地址（文档“配置样例”：列表里的域名不会被解析为 fake ip）：局域网后缀、要真实地址的名单
        "fake-ip-filter": fake_ip_filter,
    }}

    urls = sub_urls or [SUB_PLACEHOLDER]
    providers = {}
    for i, u in enumerate(urls, 1):
        providers[f"订阅{i}"] = {
            "url": u,
            "interval": 86400,
            # 文档“发布说明”2.6.5：Proxy-Providers 里可以设 benchmark-url 与 benchmark-timeout（单位：秒）；
            # 文档“延迟测试”建议只用 HTTP，所以用不带 TLS 的那个检测地址
            "benchmark-url": hc["url_http"],
            "benchmark-timeout": hc["timeout_ms"] // 1000,
        }
    dummy = [{"name": name, "type": "http", "server": PLACEHOLDER_SERVER, "port": PLACEHOLDER_PORT,
              "benchmark-url": hc["url_http"], "benchmark-timeout": hc["timeout_ms"] // 1000}
             for name in placeholders(m).values()]

    out: List[str] = []
    out.append("# 由统一源生成，请勿手工修改；改动请在 source/ 中进行后重新生成。")
    out.append(f"# 统一源版本 {p['project']['source_version']}；目标：{p['targets']['stash']['core']}")
    out.append("# 适用：iPhone / iPad / Mac 共用同一份配置。Stash 没有能在电脑上运行的内核，这份配置只按官方文档核对过，导入后请按 docs/09 验收。")
    if simple:
        out += simple_header(m, "stash-strict.yaml" if strict else "stash.yaml")
    if strict:
        out.append("# 这是【严格版】：没有命中任何域名规则的连接，不为判断规则在本机解析域名，直接交给“国外默认”；国内网站靠 GEOSITE,cn 和 rule-providers 里的国内域名清单认出来。")
        out.append("# 清单里没有的国内网站会走代理（可能变慢，个别网站可能限制境外访问；没有实测）；遇到了可以在 App 里切回标准版 "
                   + ("stash-simple.yaml" if simple else "stash.yaml") + "。")
    if not sub_urls:
        out.append("# ⚠ 使用前必须把 proxy-providers 里的 url 换成你的订阅链接（当前是占位符，不可直接使用）。订阅要选 Clash / Stash 格式。")
    out.append("# 证书：本配置不含任何 MITM 证书或密码。")
    out.append("")
    out.append(_y({"mode": "rule", "log-level": "warning"}).rstrip())
    out.append("")
    out.append(_y(dns_block, _QuotedWildcards).rstrip())
    out.append("")
    out.append("# 占位节点：每个地区一个，连本机一个没有程序在听的端口，连接马上失败。")
    out.append("# Stash 的文档说一个代理都没有的策略组会被当作直连（DIRECT）；放上占位节点，某个地区一个节点都没有时，")
    out.append("# 这个地区的组里只剩它，连接失败而不是直连。它的名字只会被这个地区的筛选正则选中。有真节点时不要选它。")
    out.append("# 文档还说远程代理集为空时以 DIRECT 替代：下面每条节点筛选的开头都排除了 DIRECT、REJECT、REJECT-DROP 这几个名字。")
    if simple:
        out.append("# 简易版：地区组里直接是节点，Stash 怎么给组里的节点排序、第一次导入时默认选哪个，文档没写——如果默认选中的是占位节点，")
        out.append("# 走这个地区的连接会失败（不会直连）：导入后先在用到的地区组里点一个真节点（docs/09）。“国外默认”里没有占位节点。")
        out.append("# 简易版的组都写 interval: -1：不定时测延迟（文档：Stash 默认每 600 秒测一次，负数关闭）。纯手选用不着定时测，")
        out.append("# 想看延迟就在 App 里手动测速。")
    out.append(_y({"proxies": dummy}).rstrip())
    out.append("")
    out.append(_y({"proxy-providers": providers}).rstrip())
    out.append("")
    out.append("# 节点筛选（filter）：按节点名称分地区的正则，由 source/regions.yaml 的词表拼出，不手写，和另外三个客户端是同一条，")
    out.append("# 只在开头多一段 (?!(?:DIRECT|REJECT|REJECT-DROP)$)：整个名字是内置策略的不选。")
    if simple:
        out.append("# 每个地区一条（按名字归到这个地区的全部节点，含名字说不清落地的）。“国外默认”另用一条全部节点（去掉提示行），")
        out.append("# 开头再多一段：七个占位节点不选。“国外默认”把写明的七个地区（proxies）和 include-all + filter 写在同一个组里：")
        out.append("# 文档没写两者一起用时谁排在前面、filter 管不管写明的成员，要在设备上看（docs/09）。")
    else:
        out.append("# 每个地区两条：“手动”组用宽的（按名字归到这个地区的全部节点，含名字说不清落地的）；")
        out.append("# “自动 / 故障转移 / 负载均衡”用严的（flt-xx-auto：只收名字只指向这个地区的节点）。")
    out.append("# 同一条正则只写一次：第一次出现时用 &flt-xx 定义，之后用 *flt-xx 引用（YAML 的锚点 / 别名）。")
    out.append("# 正则里用了否定前瞻等写法；Stash 用什么正则引擎官方文档没写，导入后请先看各地区的组里有没有节点（docs/09）。")
    out.append("# 名称只是初筛，不证明实际出口；想看每个节点进了哪个组、为什么，运行 tools/check_node_names.py。")
    out.append("proxy-groups:")
    filters = _Filters(m, groups, [r["id"] for r in m.regions] + [m.other_region["id"]])
    for g in groups:
        d = _group_dict(m, g, simple)
        if g.comment:
            out.append(f"  # {g.name}：{g.comment}")
        block = _y([d]).rstrip().splitlines()
        if g.nodes is not None:
            i = block.index(f"  filter: {FILTER_MARK}")
            block[i] = "  " + filters.line(filter_regex(m, g.nodes))
        out.extend("  " + ln for ln in block)
    if strict:
        out.append("")
        out.append("# 严格版的国内域名清单（直接订阅上游，内容跟着上游更新）。文档“配置样例”的写法：behavior: domain-text。")
        rp = {}
        for x in m.strict["domestic_lists"]["stash"]:
            rp[x["tag"]] = {"behavior": DOMAIN_TEXT, "url": x["url"], "interval": 86400}
        out.append(_y({"rule-providers": rp}).rstrip())
    out.append("")
    out.append("rules:")
    out.extend(build_rules_text(m, plan, strict))
    out.append("")
    return "\n".join(out)

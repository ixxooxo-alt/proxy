"""Quantumult X 产物（iPhone / iPad / Mac 共用）。
语法依据：官方 sample.conf（https://github.com/crossutility/Quantumult-X/blob/master/sample.conf）。
策略：static（手选）/ available（第一个可用）/ url-latency-benchmark（测速）/ dest-hash（按目标散列，作负载均衡）。
节点筛选：server-tag-regex。sample.conf 的注释写它“only work for static, available and round-robin type of polices”，
同一文件的示例又把它写在 dest-hash 和 url-latency-benchmark 上（2026-10-02 读取）；所以“X·自动”“X·负载均衡”
是否按正则取节点，要在设备上确认（docs/06）。地区正则由 source/regions.yaml 的词表拼出，见 generator/regions.py。
分流优先级：本地 filter_local > 远程 filter_remote（不使用 inserted-resource）；域名类先于 IP 类。

严格版（build 的 strict=True，另存为 quantumultx-strict.conf；设定在 source/strict.yaml，说明见 generator/strict.py）与标准版的差别：
  1. [filter_remote] 在广告集合之后多两项：国内域名清单（交给“国内直连”）、域名兜底（一条 HOST-KEYWORD,. ，交给“国外默认”，排在最后）。
     兜底的写法出自官方 sample.conf：“You can add below host-keyword rule to skip the DNS query for all the non-matched hosts.
     Pure IP requests won't be matched by the host related rules.” 官方把它写在 filter_local 里；这里放在远程规则的最后，
     因为官方仓库的问题单 #251（用户报告）说它放在本地时全部远程规则不再触发——广告集合和国内清单都是远程的。
     代价：这个远程文件没有加载成功时，兜底不存在，行为回到标准版（验收步骤见 docs/09）。
  2. 本地规则与标准版相同（按 IP 判断的规则全部保留，原本就是 IP 的连接照旧按它们走），只多一段：
     要真实地址的名单（dns_exclusion_list）里标准版没有固定直连规则的名字，补上固定直连。"""
from __future__ import annotations

from typing import List

from . import strict as strict_mod
from .groups import NodeFilter, build_groups
from .model import Model, Plan
from .util import Rule, check_regex_line_safe

MODES = ["manual_first", "manual", "auto", "failover", "balance"]
SUB_PLACEHOLDER = "https://REPLACE-ME.invalid/请替换为你的订阅链接"
KIND_MAP = {"select": "static", "url-test": "url-latency-benchmark", "fallback": "available", "load-balance": "dest-hash"}


def _pol(name: str) -> str:
    return {"DIRECT": "direct", "REJECT": "reject"}.get(name, name)


def rule_line(r: Rule) -> str:
    t = _pol(r.target)
    return {
        "domain": f"host, {r.value}, {t}",
        "suffix": f"host-suffix, {r.value}, {t}",
        "keyword": f"host-keyword, {r.value}, {t}",
        "ip4": f"ip-cidr, {r.value}, {t}",
        "ip6": f"ip6-cidr, {r.value}, {t}",
    }[r.kind]


def _regex(nf: NodeFilter) -> str:
    rx = nf.final_regex()
    check_regex_line_safe(rx)
    return rx


def build(m: Model, plan: Plan, sub_urls: List[str] | None = None, strict: bool = False) -> str:
    p = m.project
    hc = m.hc
    dns = m.dns
    groups = build_groups(m, MODES)
    L: List[str] = []
    L.append("# 由统一源生成，请勿手工修改；改动请在 source/ 中进行后重新生成。")
    L.append(f"# 统一源版本 {p['project']['source_version']}；目标：{p['targets']['quantumultx']['core']}")
    L.append("# 适用：iPhone / iPad / Mac 共用同一份配置（平台验收分别记录）")
    if strict:
        L.append("# 这是【严格版】：没有命中任何域名规则的域名不在本机解析，直接交给“国外默认”；国内网站靠 [filter_remote] 里的国内域名清单认出来。")
        L.append("# 清单里没有的国内网站会走代理（能打开，会慢）；遇到了可以在 App 里切回标准版 quantumultx.conf。")
        L.append("# 这一份依赖 [filter_remote] 最后那条“域名兜底”加载成功，Quantumult X 的规则先后也没有完整的官方说明：导入后请按 docs/09 的严格版一节验收。")
        L.append(f"# 国内域名清单和域名兜底都在 {m.strict['publish_base']} 下：文件还没有发布、改了名、或者仓库改成私有时加载会失败——"
                 "国内清单失败，国内网站改走代理；域名兜底失败，回到标准版的行为（没命中的域名又在本机解析），App 不会有任何提示。")
    if not sub_urls:
        L.append("# ⚠ 使用前必须把 [server_remote] 的订阅链接换成你自己的（当前是占位符，不可直接使用）。")
    L.append("# 证书：本配置不含任何 MITM 证书或密码。")
    L.append("")

    excl = ["*.cmpassport.com", "*.jegotrip.com.cn", "*.icitymobile.mobi", "id6.me"]
    for x in dns["real_ip"]:
        v = ("*." + x["suffix"]) if "suffix" in x else x["domain"]
        if v not in excl:
            excl.append(v)
    L += [
        "[general]",
        f"server_check_url={hc['url_http']}",
        f"server_check_timeout={min(hc['timeout_ms'], 5000)}",
        "network_check_url=http://connectivitycheck.platform.hicloud.com/generate_204",
        "dns_exclusion_list=" + ", ".join(excl),
        "excluded_routes=192.168.0.0/16, 172.16.0.0/12, 100.64.0.0/10, 10.0.0.0/8",
        "fallback_udp_policy=reject",
        "",
        "[dns]",
    ]
    if not dns["ipv6_answers"]:
        L.append("no-ipv6")
    for s in dns["domestic_plain"]:
        L.append(f"server={s}")
    L.append("doh-server=" + ", ".join(dns["domestic_doh"]))
    for sfx in m.project["lan"]["domain_suffix"]:          # 与其他三端同一份局域网后缀
        L.append(f"server=/*.{sfx}/system")

    L += ["", "[policy]",
          "# server-tag-regex：按节点名称分地区的正则，由 source/regions.yaml 的词表拼出，不手写。",
          "# 每个地区两条：“手动”用宽的（按名字归到这个地区的全部节点，含名字说不清落地的）；",
          "# “自动 / 故障转移 / 负载均衡”用严的（只收名字只指向这个地区的节点）。",
          "# 名称只是初筛，不证明实际出口；想看每个节点进了哪个组、为什么，在电脑上运行 tools/check_node_names.py。",
          "# 每行末尾的 img-url 是策略组图标的地址（图片在图标仓库里，只影响显示，不影响分流；见 source/icons.yaml）。"]
    for g in groups:
        kind = KIND_MAP[g.kind]
        if g.nodes is not None:
            body = f"server-tag-regex={_regex(g.nodes)}"
        else:
            body = ", ".join(_pol(x) for x in g.members)
        line = f"{kind}={g.name}, {body}"
        if kind == "url-latency-benchmark":
            line += f", check-interval={hc['interval_s']}, alive-checking=false, tolerance={hc['tolerance_ms']}"
        icon = m.icon_url(g.name)
        if icon:
            line += f", img-url={icon}"           # 图标只影响显示；地址已做百分号编码，不含逗号和空格
        L.append(line)

    L += ["", "[server_remote]"]
    for i, u in enumerate(sub_urls or [SUB_PLACEHOLDER], 1):
        L.append(f"{u}, tag=订阅{i}, update-interval=86400, opt-parser=true, enabled=true")

    L += ["", "[filter_remote]",
          "# 3c 广告集合。远程分流优先级低于本地分流，位于产品根域下的广告主机需要本地前置拦截（见 filter_local 3b）"]
    for x in m.adblock["remote_lists"]["quantumultx"]:
        L.append(f"{x['url']}, tag={x['tag']}, force-policy=广告拦截, update-interval=86400, opt-parser=false, enabled=true")
    if strict:
        L.append("# 6 国内域名清单（严格版）：排在广告集合之后；本地的产品规则仍然优先于它")
        for x in m.strict["domestic_lists"]["quantumultx"]:
            url = x["url"] if "url" in x else strict_mod.own_url(m, x["own"])
            L.append(f"{url}, tag={x['tag']}, force-policy=国内直连, update-interval=86400, opt-parser=false, enabled=true")
        fb = m.strict["qx_fallback"]
        L.append("# 9 域名兜底（严格版）：必须是最后一条。前面都没接住的域名交给“国外默认”，不再为了判断 IP 规则而在本机解析")
        L.append(f"{strict_mod.own_url(m, fb['own'])}, tag={fb['tag']}, force-policy=国外默认, update-interval=86400, "
                 "opt-parser=false, enabled=true")

    L += ["", "[rewrite_remote]", "", "[server_local]", "", "[filter_local]"]

    def emit(rules: List[Rule], by_service=True):
        last = None
        for r in rules:
            if by_service and r.service != last:
                L.append(f"# -- {r.service} --")
                last = r.service
            L.append(rule_line(r))

    L.append("# ==== 2 局域网、内网与系统联网检测（固定直连） ====")
    emit(plan.lan)
    L.append("# ==== 2b 要真实地址的名单（[general] 的 dns_exclusion_list）：这些名字先在本机由国内 DNS 解析、再选出口，所以固定直连 ====")
    emit(plan.real_ip_direct, by_service=False)
    L.append("# ==== 3a 广告误杀例外：按业务目标放行 ====")
    emit(plan.exceptions, by_service=False)
    L.append("# ==== 3b 自有广告 / 跟踪拦截 ====")
    emit(plan.ads_local, by_service=False)
    L.append("# ==== 4-5 产品专属、共享依赖与厂商规则（更具体的规则在前） ====")
    emit(plan.product_for("quantumultx"))
    if strict:
        L.append("# ==== 6 国内外域名分类：国内域名清单与域名兜底都在 [filter_remote] 里；域名类规则全部先于下面的 IP 类规则判断 ====")
        L.append("# ==== 7 服务专属 IP：只有原本就是 IP 的连接会走到这里（域名已经被上面的规则或域名兜底接住） ====")
    else:
        L.append("# ==== 6 国内外域名分类：未引入第三方大集合，由自有规则与 GEOIP 兜底覆盖 ====")
        L.append("# ==== 7 服务专属 IP ====")
    emit(plan.service_ip_for("quantumultx"))
    if strict:
        L.append("# ==== 8 国内 IP：同上，只对原本就是 IP 的连接生效 ====")
    else:
        L.append("# ==== 8 国内 IP 兜底 ====")
    L.append("geoip, cn, 国内直连")
    L.append("# ==== 9 其余目标 ====")
    L.append("final, 国外默认")

    L += ["", "[rewrite_local]", "", "[task_local]", "", "[http_backend]", "", "[mitm]", ""]
    return "\n".join(L)

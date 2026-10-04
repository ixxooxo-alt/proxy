"""Quantumult X 产物（iPhone / iPad / Mac 共用）。
语法依据：官方 sample.conf（https://github.com/crossutility/Quantumult-X/blob/master/sample.conf）。
策略：static（手选）/ available（第一个可用）/ url-latency-benchmark（测速）/ dest-hash（按目标散列，作负载均衡）。
分流优先级：本地 filter_local > 远程 filter_remote（不使用 inserted-resource）；域名类先于 IP 类。"""
from __future__ import annotations

from typing import List

from .groups import NodeFilter, build_groups
from .model import Model, Plan
from .util import Rule, check_regex_line_safe, compose_node_regex

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
    if nf.pinned:
        rx = nf.exact_regex()
    elif nf.raw:
        rx = nf.include
    else:
        rx = compose_node_regex(nf.include, nf.exclude)
    check_regex_line_safe(rx)
    return rx


def build(m: Model, plan: Plan, sub_urls: List[str] | None = None) -> str:
    p = m.project
    hc = m.hc
    dns = m.dns
    groups = build_groups(m, MODES)
    L: List[str] = []
    L.append("# 由统一源生成，请勿手工修改；改动请在 source/ 中进行后重新生成。")
    L.append(f"# 统一源版本 {p['project']['source_version']}；目标：{p['targets']['quantumultx']['core']}")
    L.append("# 适用：iPhone / iPad / Mac 共用同一份配置（平台验收分别记录）")
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
    for sfx in ("lan", "local", "localdomain", "home.arpa"):
        L.append(f"server=/*.{sfx}/system")

    L += ["", "[policy]"]
    for g in groups:
        kind = KIND_MAP[g.kind]
        if g.nodes is not None:
            body = f"server-tag-regex={_regex(g.nodes)}"
        else:
            body = ", ".join(_pol(x) for x in g.members)
        line = f"{kind}={g.name}, {body}"
        if kind == "url-latency-benchmark":
            line += f", check-interval={hc['interval_s']}, alive-checking=false, tolerance={hc['tolerance_ms']}"
        L.append(line)

    L += ["", "[server_remote]"]
    for i, u in enumerate(sub_urls or [SUB_PLACEHOLDER], 1):
        L.append(f"{u}, tag=订阅{i}, update-interval=86400, opt-parser=true, enabled=true")

    L += ["", "[filter_remote]",
          "# 3c 广告集合。远程分流优先级低于本地分流，位于产品根域下的广告主机需要本地前置拦截（见 filter_local 3b）"]
    for x in m.adblock["remote_lists"]["quantumultx"]:
        L.append(f"{x['url']}, tag={x['tag']}, force-policy=广告拦截, update-interval=86400, opt-parser=false, enabled=true")

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
    L.append("# ==== 3a 广告误杀例外：按业务目标放行 ====")
    emit(plan.exceptions, by_service=False)
    L.append("# ==== 3b 自有广告 / 跟踪拦截 ====")
    emit(plan.ads_local, by_service=False)
    L.append("# ==== 4-5 产品专属、共享依赖与厂商规则（更具体的规则在前） ====")
    emit(plan.product)
    L.append("# ==== 6 国内外域名分类：未引入第三方大集合，由自有规则与 GEOIP 兜底覆盖 ====")
    L.append("# ==== 7 服务专属 IP ====")
    emit(plan.service_ip)
    L.append("# ==== 8 国内 IP 兜底 ====")
    L.append("geoip, cn, 国内直连")
    L.append("# ==== 9 其余目标 ====")
    L.append("final, 国外默认")

    L += ["", "[rewrite_local]", "", "[task_local]", "", "[http_backend]", "", "[mitm]", ""]
    return "\n".join(L)

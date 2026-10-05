"""Loon 产物（iPhone / iPad / Mac 共用）。
语法依据：https://nsloon.app/docs/（规则优先级：本地 > 插件 > 订阅；域名规则先于 IP 规则，Loon 3.0.3+）
策略组：select / url-test / fallback / load-balance，支持嵌套；节点筛选用 [Remote Filter] NameRegex
（官方“节点筛选”页 https://nsloon.app/docs/Node/nodefilter 的常用正则里有否定前瞻 ^(?!.*A)，没有说明用的是什么正则引擎；
地区正则由 source/regions.yaml 的词表拼出，见 generator/regions.py）。"""
from __future__ import annotations

from typing import List

from .groups import GroupSpec, NodeFilter, build_groups, shared_filter_labels
from .model import Model, Plan
from .util import Rule, check_regex_line_safe

MODES = ["manual_first", "manual", "auto", "failover", "balance"]
SUB_PLACEHOLDER = "https://REPLACE-ME.invalid/请替换为你的订阅链接"


def rule_line(r: Rule) -> str:
    t = r.target
    return {
        "domain": f"DOMAIN,{r.value},{t}",
        "suffix": f"DOMAIN-SUFFIX,{r.value},{t}",
        "keyword": f"DOMAIN-KEYWORD,{r.value},{t}",
        "ip4": f"IP-CIDR,{r.value},{t},no-resolve",
        "ip6": f"IP-CIDR6,{r.value},{t},no-resolve",
    }[r.kind]


def _filter_regex(nf: NodeFilter) -> str:
    rx = nf.final_regex()
    check_regex_line_safe(rx)
    return rx


def build(m: Model, plan: Plan, sub_urls: List[str] | None = None) -> str:
    p = m.project
    hc = m.hc
    dns = m.dns
    groups = build_groups(m, MODES)
    labels = shared_filter_labels(groups, [r["id"] for r in m.regions] + [m.other_region["id"]])

    def _filter_name(nf: NodeFilter) -> str:
        return "F-" + labels[nf.final_regex()].upper()

    L: List[str] = []
    L.append("# 由统一源生成，请勿手工修改；改动请在 source/ 中进行后重新生成。")
    L.append(f"# 统一源版本 {p['project']['source_version']}；目标：{p['targets']['loon']['core']}")
    L.append("# 适用：iPhone / iPad / Mac 共用同一份配置（平台验收分别记录）")
    if not sub_urls:
        L.append("# ⚠ 使用前必须把 [Remote Proxy] 的订阅链接换成你自己的（当前是占位符，不可直接使用）。")
    L.append("# 证书：本配置不含任何 MITM 证书或密码，如需复写 / 脚本请在设备上自行生成并信任证书。")
    L.append("")

    lan4 = ",".join(p["lan"]["ipv4"][1:])       # 去掉 0.0.0.0/8
    real_ip = []
    for x in dns["real_ip"]:
        real_ip.append(("*." + x["suffix"]) if "suffix" in x else x["domain"])
    L += [
        "[General]",
        "ip-mode = " + ("dual" if dns["ipv6_answers"] else "ipv4-only"),
        "dns-server = " + ",".join(dns["domestic_plain"]),
        "doh-server = " + ",".join(dns["domestic_doh"]),
        "sni-sniffing = true",
        "disable-stun = false",
        "dns-reject-mode = LoopbackIP",
        "domain-reject-mode = DNS",
        "udp-fallback-mode = REJECT",
        "allow-wifi-access = false",
        "interface-mode = auto",
        f"test-timeout = {hc['timeout_ms'] // 1000}",
        "disconnect-on-policy-change = false",
        f"switch-node-after-failure-times = {hc['max_failed_times']}",
        f"proxy-test-url = {hc['url_http']}",
        "internet-test-url = http://connectivitycheck.platform.hicloud.com/generate_204",
        "skip-proxy = 192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,100.64.0.0/10,127.0.0.0/8,localhost,*.local,*.lan,captive.apple.com",
        f"bypass-tun = {lan4},192.0.0.0/24,192.0.2.0/24,192.88.99.0/24,198.51.100.0/24,203.0.113.0/24",
        "real-ip = " + ",".join(real_ip),
        "hijack-dns = 8.8.8.8:53,8.8.4.4:53,1.1.1.1:53,1.0.0.1:53",
        "",
        "[Host]",
    ]
    for sfx in m.project["lan"]["domain_suffix"]:          # 与其他三端同一份局域网后缀
        L.append(f"*.{sfx} = server:system")
    L += ["", "[Proxy]", "", "[Remote Proxy]"]
    for i, u in enumerate(sub_urls or [SUB_PLACEHOLDER], 1):
        L.append(f"订阅{i} = {u}, udp=true, fast-open=false, vmess-aead=true, enabled=true")

    # 节点筛选：正则由 source/regions.yaml 的词表拼出（generator/regions.py）；同一条正则只定义一次
    L += ["", "[Remote Filter]",
          "# 按节点名称分地区。名称只是初筛，不证明实际出口；想看每个节点进了哪个组、为什么，",
          "# 在电脑上运行 tools/check_node_names.py。",
          "# 每个地区两条：F-XX 是按名字归到这个地区的全部节点（手动组用，含名字说不清落地的）；",
          "# F-XX-AUTO 只收名字只指向这个地区的节点（自动 / 故障转移 / 负载均衡用）。"]
    seen = set()
    for g in groups:
        for nf in (g.nodes, g.backup_nodes):
            if nf is None:
                continue
            name = _filter_name(nf)
            if name in seen:
                continue
            seen.add(name)
            L.append(f'{name} = NameRegex, FilterKey = "{_filter_regex(nf)}"')

    L += ["", "[Proxy Group]",
          "# 每行末尾的 img-url 是策略组图标的地址（图片在图标仓库里，只影响显示，不影响分流；见 source/icons.yaml）。",
          "# 注意：Loon 官方示例配置注释写明 url-test / fallback“只支持单个节点和远端节点，其他会被忽略”，",
          "# 而现行文档说策略组“支持嵌套”。为避免“手动优先”组在前一种情况下变成空组，它在两个成员组之后",
          "# 还附带同地区节点：若嵌套生效，按 手动 → 自动 → 同地区节点 的顺序；若嵌套被忽略，退化为同地区顺序故障转移，",
          "# 仍不跨国、不直连。实际是哪一种，需要在设备上查看该组的成员列表确认。"]
    for g in groups:
        if g.comment:
            L.append(f"# {g.name}：{g.comment}")
        if g.nodes is not None:
            members = [_filter_name(g.nodes)]
        else:
            members = list(g.members)
            if g.backup_nodes is not None:
                members.append(_filter_name(g.backup_nodes))
        head = f"{g.name} = {g.kind}," + ",".join(members)
        if g.kind == "url-test":
            head += f",url = {hc['url_http']},interval = {hc['interval_s']},tolerance = {hc['tolerance_ms']}"
        elif g.kind == "fallback":
            head += f",url = {hc['url_http']},interval = {hc['interval_s']},max-timeout = {hc['timeout_ms']}"
        elif g.kind == "load-balance":
            head += f",url = {hc['url_http']},interval = {hc['interval_s']},max-timeout = {hc['timeout_ms']},algorithm = pcc"
        icon = m.icon_url(g.name)
        if icon:
            head += f",img-url = {icon}"          # 图标只影响显示；地址已做百分号编码，不含逗号和空格
        L.append(head)

    L += ["", "[Rule]"]

    def emit(rules: List[Rule], by_service=True):
        last = None
        for r in rules:
            if by_service and r.service != last:
                L.append(f"# -- {r.service} --")
                last = r.service
            L.append(rule_line(r))

    L.append("# ==== 2 局域网、内网与系统联网检测（固定直连） ====")
    emit(plan.lan)
    L.append("# ==== 3a 广告误杀例外：按业务目标放行（本地规则优先于订阅的广告集合） ====")
    emit(plan.exceptions, by_service=False)
    L.append("# ==== 3b 自有广告 / 跟踪拦截（位于产品根域下，必须在本地产品规则之前） ====")
    emit(plan.ads_local, by_service=False)
    L.append("# ==== 4-5 产品专属、共享依赖与厂商规则（更具体的规则在前） ====")
    emit(plan.product_for("loon"))
    L.append("# ==== 6 国内外域名分类：未引入第三方大集合（其中含宽泛关键词规则），由上面的自有规则与下面的 GEOIP 兜底覆盖 ====")
    L.append("# ==== 7 服务专属 IP（不触发 DNS 解析） ====")
    emit(plan.service_ip_for("loon"))
    L.append("# ==== 8 国内 IP 兜底 ====")
    L.append("GEOIP,CN,国内直连")
    L.append("# ==== 9 其余目标 ====")
    L.append("FINAL,国外默认")

    L += ["", "[Remote Rule]",
          "# 3c 广告集合：Loon 中订阅规则优先级低于本地规则（官方文档），因此位于上面产品根域下的广告主机不会被它拦截"]
    for x in m.adblock["remote_lists"]["loon"]:
        L.append(f"{x['url']}, policy=广告拦截, tag={x['tag']}, enabled=true")

    L += ["", "[Rewrite]", "", "[Script]", "",
          "[Plugin]",
          "# 未内置第三方插件。可自行添加（例如可莉的去广告插件）；插件规则优先级介于本地规则与订阅规则之间。",
          "", "[Mitm]", "hostname = ", "skip-server-cert-verify = false", ""]
    return "\n".join(L)

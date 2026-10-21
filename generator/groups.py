"""策略组图：与客户端无关的描述，由各端按自身能力映射。

两种布局（2026-10-21 起）：
  full（完整版，原来的那一套）：地区入口选模式（手动优先 / 手动 / 自动 / 故障转移 / 负载均衡），模式组在下一层；
  simple（简易版，docs/10）：每个地区一个选择组，里面直接是这个地区的全部节点（宽筛选），没有模式组；
    “国外默认”是七个地区再接全部节点；mihomo、sing-box 另有一个内部的自动测速组（project.yaml 的 simple.foreign_dns_group），
    只给境外 DNS 和规则数据的下载用。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .model import Model
from .regions import lit

ALL_MODES = ["manual_first", "manual", "auto", "failover", "balance"]


AUTO_SUFFIX = "-auto"                # 严的那条筛选的标签后缀：hk-auto（Loon 里叫 F-HK-AUTO，mihomo 的锚点叫 flt-hk-auto）


@dataclass
class NodeFilter:
    label: str                       # 例如 hk / hk-auto / other / paypal / all / dns
    regex: Optional[str]             # 完整的名称筛选正则（地区正则已含提示行排除等全部条件）；固定节点、any_of 时为 None
    pinned: Optional[str] = None     # 固定节点的完整名称
    # 几条正则任一条匹配就算（简易版的“境外DNS”：六个地区的严筛选）。合成一条太长（每条十几 KB），所以分开写：
    # mihomo 用反引号把它们连起来（v1.19.31 groupbase.go 按反引号拆成多条、取并集），sing-box 在生成时逐条判断。
    # 只有这两端会用到它；Loon、Quantumult X、Stash 没有这个组
    any_of: Tuple[str, ...] = ()

    def exact_regex(self) -> Optional[str]:
        """固定节点：整个名称完全相同才算（逗号、引号、空格等写成 \\xHH，任何名称都能放进 Loon / QX 的一行）。"""
        if not self.pinned:
            return None
        return "^" + lit(self.pinned) + "$"

    def final_regex(self) -> str:
        """写进各客户端的那条正则。"""
        if self.any_of:
            raise ValueError(f"节点筛选 {self.label} 由 {len(self.any_of)} 条正则合成，没有单独的一条（只有 mihomo、sing-box 写得出来）")
        return self.exact_regex() if self.pinned else self.regex


@dataclass
class GroupSpec:
    name: str
    kind: str                        # select | url-test | fallback | load-balance
    members: List[str] = field(default_factory=list)   # 组 / DIRECT / REJECT
    nodes: Optional[NodeFilter] = None                 # 从节点中筛选（与 members 二选一）
    hidden: bool = False
    role: str = ""                   # business | foreign_default | region_entry | region_mode | other_region | paypal_fixed
    comment: str = ""
    mode: str = ""                   # 地区子组的模式 id
    backup_nodes: Optional[NodeFilter] = None   # 仅 Loon 使用：排在成员组之后的同地区节点（见 emit_loon）
    # 简易版（2026-10-21）：“国外默认”既有成员组（七个地区）又有节点筛选（全部节点），members 和 nodes 同时有值，
    # 节点排在成员组后面。完整版里两者仍是二选一。
    interval_s: Optional[int] = None            # 健康检查间隔；None 用 project.yaml 的 health_check.interval_s
    max_failed_times: Optional[int] = None      # mihomo：写了就输出 max-failed-times（完整版只有 fallback 写）


def shared_filter_labels(groups: List["GroupSpec"], region_ids: List[str]) -> dict:
    """{正则: 标签}：多个组用同一条筛选正则时（每个地区的几个模式组、PayPal 固定入口用的美国正则），
    给这条正则一个共用的标签，Loon 的 [Remote Filter] 和 mihomo 的 YAML 锚点都只写一次。
    标签优先用地区 id（us），所以 PayPal 固定入口没填固定节点时直接引用美国那条。"""
    labels: dict = {}
    for g in groups:
        for nf in (g.nodes, g.backup_nodes):
            if nf is not None and not nf.any_of:
                labels.setdefault(nf.final_regex(), []).append(nf.label)
    return {rx: next((x for x in ls if x in region_ids), ls[0]) for rx, ls in labels.items()}


def region_mode_name(region_name: str, suffix: str) -> str:
    return f"{region_name}·{suffix}"


LAYOUTS = ("full", "simple")
ALL_LABEL = "all"                    # 简易版“国外默认”的全部节点筛选（Loon 里叫 F-ALL）
FOREIGN_DNS_LABEL = "dns"


def build_groups(m: Model, modes: List[str], layout: str = "full", foreign_dns: bool = False) -> List[GroupSpec]:
    """modes：该客户端支持的地区模式（顺序即入口组成员顺序，第一个为默认；简易版不用）。
    layout：full（完整版）| simple（简易版）。foreign_dns：简易版里要不要那个内部的自动测速组（只有 mihomo、sing-box 要）。"""
    if layout not in LAYOUTS:
        raise ValueError(f"不认识的布局 {layout!r}")
    if layout == "simple":
        return _build_simple(m, foreign_dns)
    if foreign_dns:
        raise ValueError("完整版没有“境外DNS”那个内部组")
    p = m.project
    enabled = p.get("enabled_region_modes") or ALL_MODES
    modes = [x for x in modes if x in enabled]
    if "manual_first" in modes and not {"manual", "auto"} <= set(modes):
        raise ValueError("手动优先·自动兜底依赖“手动”和“自动”两个模式")
    # 由 source/regions.yaml 的词表拼出。每个地区两条（2026-10-04，审核 F04）：
    #   宽的：按名字归到这个地区的全部节点，包括说不清落地的 → 手动组、PayPal 的美国固定入口（都是人来选）
    #   严的：名字只指向这一个地区的节点 → 自动测速、故障转移、负载均衡（客户端自己选，不能把说不清的节点选进去）
    node_rx = m.node_regexes()
    node_rx_strict = m.node_regexes_strict()
    mode_suffix = {x["id"]: x["suffix"] for x in p["region_modes"]}
    out: List[GroupSpec] = []

    paypal = m.special_entries["paypal_fixed"]

    # 业务组（含国外默认）按 groups.yaml 顺序
    for g in m.groups:
        role = "foreign_default" if g.special == "foreign_default" else "business"
        out.append(GroupSpec(name=g.name, kind="select", members=g.members, role=role, comment=g.note))

    # 专用入口
    out.append(GroupSpec(
        name=paypal["name"], kind="select", role="paypal_fixed",
        nodes=NodeFilter(label="paypal", regex=None if paypal.get("pinned_node_name") else node_rx[paypal["region"]],
                         pinned=paypal.get("pinned_node_name") or None),
        comment=("固定节点：" + paypal["pinned_node_name"]) if paypal.get("pinned_node_name") else
                "尚未指定固定节点：在美国节点中手动选一个；被选节点删除后会回到本组第一个美国节点（见已知限制）"))

    # 地区入口
    for r in m.regions:
        out.append(GroupSpec(
            name=r["name"], kind="select", role="region_entry",
            members=[region_mode_name(r["name"], mode_suffix[x]) for x in modes],
            comment="地区入口：选择本地区的工作模式，不跨国"))
    other = m.other_region
    out.append(GroupSpec(
        name=other["name"], kind="select", role="other_region",
        nodes=NodeFilter(label=other["id"], regex=node_rx[other["id"]]),
        comment="纯手动；不提供跨国自动模式。名称里认不出六个地区的节点、落地在其他国家的节点都在这里"))

    # 地区子组
    for r in m.regions:
        nf = NodeFilter(label=r["id"], regex=node_rx[r["id"]])
        nf_auto = NodeFilter(label=r["id"] + AUTO_SUFFIX, regex=node_rx_strict[r["id"]])
        for x in modes:
            name = region_mode_name(r["name"], mode_suffix[x])
            if x == "manual":
                out.append(GroupSpec(name=name, kind="select", nodes=nf, role="region_mode", mode=x,
                                     comment="纯手动：在本地区节点中选择（含名字说不清落地的节点）"))
            elif x == "auto":
                out.append(GroupSpec(name=name, kind="url-test", nodes=nf_auto, role="region_mode", mode=x, hidden=True,
                                     comment="自动测速：同地区延迟最低（不代表带宽 / 解锁 / IP 信誉）；只用名字只指向本地区的节点"))
            elif x == "failover":
                out.append(GroupSpec(name=name, kind="fallback", nodes=nf_auto, role="region_mode", mode=x, hidden=True,
                                     comment="顺序故障转移：按订阅顺序取第一个可用节点；只用名字只指向本地区的节点"))
            elif x == "balance":
                out.append(GroupSpec(name=name, kind="load-balance", nodes=nf_auto, role="region_mode", mode=x, hidden=True,
                                     comment="负载均衡：同一目标尽量固定同一节点；只用名字只指向本地区的节点"))
            elif x == "manual_first":
                out.append(GroupSpec(
                    name=name, kind="fallback", role="region_mode", mode=x, hidden=True,
                    members=[region_mode_name(r["name"], mode_suffix["manual"]),
                             region_mode_name(r["name"], mode_suffix["auto"])],
                    backup_nodes=nf_auto,
                    comment="手动优先·自动兜底：手选节点健康检查失败时用同地区自动测速，恢复后切回"))
    return out


def _build_simple(m: Model, foreign_dns: bool) -> List[GroupSpec]:
    """简易版（使用者 2026-10-21 定的，docs/10）：
      业务组：和完整版一样（组名、成员、默认都相同；说明有 note_simple 的用它）；
      国外默认：成员是七个地区（和完整版一样，首次默认日本），后面接全部节点（不含提示行）；
      PayPal·美国固定、其他地区：和完整版一样；
      六个地区：选择组，里面直接是这个地区的全部节点（宽筛选，和完整版的“X·手动”是同一条），没有模式组，不自动换；
      foreign_dns 时最后加一个内部的自动测速组：六个地区的严筛选取并集（不收“其他地区”：那里可能有回国节点），
        检查间隔用 simple.health_check_interval_s，mihomo 上藏起来，只给境外 DNS 和规则数据的下载用。"""
    sp = m.simple
    node_rx = m.node_regexes()
    node_rx_strict = m.node_regexes_strict()
    paypal = m.special_entries["paypal_fixed"]
    out: List[GroupSpec] = []
    for g in m.groups:
        role = "foreign_default" if g.special == "foreign_default" else "business"
        spec = GroupSpec(name=g.name, kind="select", members=g.members, role=role, comment=g.note_simple or g.note)
        if role == "foreign_default":
            spec.nodes = NodeFilter(label=ALL_LABEL, regex=m.node_regex_any())
        out.append(spec)
    out.append(GroupSpec(
        name=paypal["name"], kind="select", role="paypal_fixed",
        nodes=NodeFilter(label="paypal", regex=None if paypal.get("pinned_node_name") else node_rx[paypal["region"]],
                         pinned=paypal.get("pinned_node_name") or None),
        comment=("固定节点：" + paypal["pinned_node_name"]) if paypal.get("pinned_node_name") else
                "尚未指定固定节点：在美国节点中手动选一个；被选节点删除后会回到本组第一个美国节点（见已知限制）"))
    for r in m.regions:
        out.append(GroupSpec(
            name=r["name"], kind="select", role="region_simple",
            nodes=NodeFilter(label=r["id"], regex=node_rx[r["id"]]),
            comment="手选：本地区的全部节点（含名字说不清落地的）；选中的节点挂了不会自动换，要换回这里点别的"))
    other = m.other_region
    out.append(GroupSpec(
        name=other["name"], kind="select", role="other_region",
        nodes=NodeFilter(label=other["id"], regex=node_rx[other["id"]]),
        comment="纯手动；不提供跨国自动模式。名称里认不出六个地区的节点、落地在其他国家的节点都在这里"))
    if foreign_dns:
        out.append(GroupSpec(
            name=sp["foreign_dns_group"], kind="url-test", role="foreign_dns", hidden=True,
            nodes=NodeFilter(label=FOREIGN_DNS_LABEL, regex=None,
                             any_of=tuple(node_rx_strict[r["id"]] for r in m.regions)),
            interval_s=sp["health_check_interval_s"], max_failed_times=m.hc["max_failed_times"],
            comment="内部用：只给境外 DNS 和规则数据的下载用，不管网页和 App 的连接走哪里。在六个地区里名字只指向一个地区的节点"
                    "（不含其他地区）中自动测速"))
    return out


def interval_text(seconds: int) -> str:
    """检查间隔写成人话：3600 → 1 小时，300 → 5 分钟。"""
    if seconds % 3600 == 0:
        return f"{seconds // 3600} 小时"
    if seconds % 60 == 0:
        return f"{seconds // 60} 分钟"
    return f"{seconds} 秒"


def simple_header(m: Model, full_file: str, foreign_dns: bool = False) -> List[str]:
    """简易版文件头的说明（Loon、Quantumult X、mihomo、Stash 的简易版都写；sing-box 是 JSON，没有注释）。
    full_file：对应的完整版文件名（标准版对标准版、严格版对严格版）。"""
    sp = m.simple
    out = [f"# 这是【简易版】（{sp['version']}）：每个地区一个组，里面直接是这个地区的全部节点，点哪个用哪个；"
           "选中的节点挂了不会自动换，要换就回组里点别的。",
           "# “国外默认”是七个地区，后面接全部节点（首次默认日本）。"]
    if foreign_dns:
        out[-1] += f"分流规则与完整版 {full_file} 相同，只多一条（见下）；策略组不同（说明见 docs/10）。"
        out.append(f"# 境外 DNS 和规则数据的下载走内部的“{sp['foreign_dns_group']}”组：六个地区里名字只指向一个地区的节点自动测速、"
                   f"{interval_text(sp['health_check_interval_s'])}检查一次，不跟着“国外默认”里手选的节点。")
    else:
        out[-1] += f"分流规则和 DNS 与完整版 {full_file} 相同，只是策略组不同（说明见 docs/10）。"
    return out

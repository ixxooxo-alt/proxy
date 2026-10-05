"""策略组图：与客户端无关的描述，由各端按自身能力映射。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .model import Model
from .regions import lit

ALL_MODES = ["manual_first", "manual", "auto", "failover", "balance"]


AUTO_SUFFIX = "-auto"                # 严的那条筛选的标签后缀：hk-auto（Loon 里叫 F-HK-AUTO，mihomo 的锚点叫 flt-hk-auto）


@dataclass
class NodeFilter:
    label: str                       # 例如 hk / hk-auto / other / paypal / netflix
    regex: Optional[str]             # 完整的名称筛选正则（地区正则已含提示行排除等全部条件）；固定节点时为 None
    pinned: Optional[str] = None     # 固定节点的完整名称

    def exact_regex(self) -> Optional[str]:
        """固定节点：整个名称完全相同才算（逗号、引号、空格等写成 \\xHH，任何名称都能放进 Loon / QX 的一行）。"""
        if not self.pinned:
            return None
        return "^" + lit(self.pinned) + "$"

    def final_regex(self) -> str:
        """写进各客户端的那条正则。"""
        return self.exact_regex() if self.pinned else self.regex


@dataclass
class GroupSpec:
    name: str
    kind: str                        # select | url-test | fallback | load-balance
    members: List[str] = field(default_factory=list)   # 组 / DIRECT / REJECT
    nodes: Optional[NodeFilter] = None                 # 从节点中筛选（与 members 二选一）
    hidden: bool = False
    role: str = ""                   # business | foreign_default | region_entry | region_mode | other_region | paypal_fixed | netflix_entry
    comment: str = ""
    mode: str = ""                   # 地区子组的模式 id
    backup_nodes: Optional[NodeFilter] = None   # 仅 Loon 使用：排在成员组之后的同地区节点（见 emit_loon）


def shared_filter_labels(groups: List["GroupSpec"], region_ids: List[str]) -> dict:
    """{正则: 标签}：多个组用同一条筛选正则时（每个地区的几个模式组、PayPal 固定入口用的美国正则），
    给这条正则一个共用的标签，Loon 的 [Remote Filter] 和 mihomo 的 YAML 锚点都只写一次。
    标签优先用地区 id（us），所以 PayPal 固定入口没填固定节点时直接引用美国那条。"""
    labels: dict = {}
    for g in groups:
        for nf in (g.nodes, g.backup_nodes):
            if nf is not None:
                labels.setdefault(nf.final_regex(), []).append(nf.label)
    return {rx: next((x for x in ls if x in region_ids), ls[0]) for rx, ls in labels.items()}


def region_mode_name(region_name: str, suffix: str) -> str:
    return f"{region_name}·{suffix}"


def build_groups(m: Model, modes: List[str]) -> List[GroupSpec]:
    """modes：该客户端支持的地区模式（顺序即入口组成员顺序，第一个为默认）。"""
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
    netflix = m.special_entries["netflix_entry"]

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

    if netflix.get("verified_node_regex"):
        out.append(GroupSpec(
            name=netflix["name"], kind="fallback", role="netflix_entry",
            nodes=NodeFilter(label="netflix", regex=netflix["verified_node_regex"]),      # 用户给出的正则，原样使用
            comment=f"已验证解锁节点（{netflix.get('verified_region', '')}，验证于 {netflix.get('verified_at', '未填写')}）之间故障转移"))
    else:
        out.append(GroupSpec(
            name=netflix["name"], kind="select", role="netflix_entry",
            members=["国外默认", "日本", "香港", "台湾", "新加坡", "美国", "韩国", "其他地区"],
            comment="尚无解锁验证记录：暂按地区选择，默认国外默认；普通测速通过不代表解锁"))

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

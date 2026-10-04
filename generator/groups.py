"""策略组图：与客户端无关的描述，由各端按自身能力映射。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .model import Model

ALL_MODES = ["manual_first", "manual", "auto", "failover", "balance"]


@dataclass
class NodeFilter:
    label: str                       # 例如 hk / other / paypal
    include: Optional[str]           # 地区正则（含 (?i)），None 表示“不限”
    exclude: List[str]               # 需要排除的正则列表（信息节点、其他地区等）
    pinned: Optional[str] = None     # 固定节点的完整名称
    raw: bool = False                # include 是用户给出的完整正则，原样使用（不再组合排除项）

    def exact_regex(self) -> Optional[str]:
        if not self.pinned:
            return None
        return "^" + re.escape(self.pinned) + "$"


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


def region_mode_name(region_name: str, suffix: str) -> str:
    return f"{region_name}·{suffix}"


def build_groups(m: Model, modes: List[str]) -> List[GroupSpec]:
    """modes：该客户端支持的地区模式（顺序即入口组成员顺序，第一个为默认）。"""
    p = m.project
    enabled = p.get("enabled_region_modes") or ALL_MODES
    modes = [x for x in modes if x in enabled]
    if "manual_first" in modes and not {"manual", "auto"} <= set(modes):
        raise ValueError("手动优先·自动兜底依赖“手动”和“自动”两个模式")
    info = p["info_node_regex"]
    mode_suffix = {x["id"]: x["suffix"] for x in p["region_modes"]}
    out: List[GroupSpec] = []

    paypal = m.special_entries["paypal_fixed"]
    netflix = m.special_entries["netflix_entry"]

    # 业务组（含国外默认）按 groups.yaml 顺序
    for g in m.groups:
        role = "foreign_default" if g.special == "foreign_default" else "business"
        out.append(GroupSpec(name=g.name, kind="select", members=g.members, role=role, comment=g.note))

    # 专用入口
    region_by_id = {r["id"]: r for r in m.regions}
    us = region_by_id[paypal["region"]]
    out.append(GroupSpec(
        name=paypal["name"], kind="select", role="paypal_fixed",
        nodes=NodeFilter(label="paypal", include=None if paypal.get("pinned_node_name") else us["regex"],
                         exclude=[info], pinned=paypal.get("pinned_node_name") or None),
        comment=("固定节点：" + paypal["pinned_node_name"]) if paypal.get("pinned_node_name") else
                "尚未指定固定节点：在美国节点中手动选一个；被选节点删除后会回到本组第一个美国节点（见已知限制）"))

    if netflix.get("verified_node_regex"):
        out.append(GroupSpec(
            name=netflix["name"], kind="fallback", role="netflix_entry",
            nodes=NodeFilter(label="netflix", include=netflix["verified_node_regex"], exclude=[], raw=True),
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
    other = p["other_region"]
    out.append(GroupSpec(
        name=other["name"], kind="select", role="other_region",
        nodes=NodeFilter(label="other", include=None, exclude=[x["regex"] for x in m.regions] + [info]),
        comment="纯手动；不提供跨国自动模式"))

    # 地区子组
    for r in m.regions:
        nf = NodeFilter(label=r["id"], include=r["regex"], exclude=[info])
        for x in modes:
            name = region_mode_name(r["name"], mode_suffix[x])
            if x == "manual":
                out.append(GroupSpec(name=name, kind="select", nodes=nf, role="region_mode", mode=x,
                                     comment="纯手动：在本地区节点中选择"))
            elif x == "auto":
                out.append(GroupSpec(name=name, kind="url-test", nodes=nf, role="region_mode", mode=x, hidden=True,
                                     comment="自动测速：同地区延迟最低（不代表带宽 / 解锁 / IP 信誉）"))
            elif x == "failover":
                out.append(GroupSpec(name=name, kind="fallback", nodes=nf, role="region_mode", mode=x, hidden=True,
                                     comment="顺序故障转移：按订阅顺序取第一个可用节点"))
            elif x == "balance":
                out.append(GroupSpec(name=name, kind="load-balance", nodes=nf, role="region_mode", mode=x, hidden=True,
                                     comment="负载均衡：同一目标尽量固定同一节点"))
            elif x == "manual_first":
                out.append(GroupSpec(
                    name=name, kind="fallback", role="region_mode", mode=x, hidden=True,
                    members=[region_mode_name(r["name"], mode_suffix["manual"]),
                             region_mode_name(r["name"], mode_suffix["auto"])],
                    backup_nodes=nf,
                    comment="手动优先·自动兜底：手选节点健康检查失败时用同地区自动测速，恢复后切回"))
    return out

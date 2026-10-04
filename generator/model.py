"""加载统一源、校验，并生成与客户端无关的“规则计划”。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

from .util import (BANNED_SHARED_SUFFIXES, GOOGLE_SHARED_ROOTS, Rule, cidr_covers, covers,
                   rule_matches_host, valid_cidr, valid_domain, check_regex_line_safe)

SERVICE_FILES = ["ai.yaml", "streaming.yaml", "social.yaml", "misc.yaml", "bigtech.yaml"]
STANDARD_OPTIONS = ["国外默认", "香港", "日本", "韩国", "台湾", "新加坡", "美国", "其他地区", "DIRECT"]
BUILTIN = {"DIRECT", "REJECT"}
RULE_KINDS = ("domain", "suffix", "keyword", "ip4", "ip6")
DOMAIN_KINDS = ("domain", "suffix", "keyword")


class SourceError(Exception):
    pass


@dataclass
class Group:
    name: str
    category: str
    default: str
    options: List[str]
    residual: bool = False
    note: str = ""
    special: str = ""

    @property
    def members(self) -> List[str]:
        out = [self.default]
        for o in self.options:
            if o not in out:
                out.append(o)
        return out


@dataclass
class Service:
    id: str
    group: str
    title: str
    rules: List[Rule]
    shared_excluded: list
    notes: str
    file: str
    upstream: Dict[str, List[str]] = field(default_factory=dict)   # 固定快照里对应的上游列表


# 社区证据 id → service.upstream 里的键（该证据必须能在这些列表中找到）
COMMUNITY_EV_SOURCE = {"dlc": "dlc", "bm7-snap": "bm7"}


@dataclass
class Model:
    root: str
    project: dict
    groups: List[Group]
    special_entries: dict
    evidence: dict
    services: List[Service]
    adblock: dict

    # 便捷访问
    @property
    def group_names(self) -> List[str]:
        return [g.name for g in self.groups]

    def group(self, name: str) -> Group:
        for g in self.groups:
            if g.name == name:
                return g
        raise KeyError(name)

    @property
    def regions(self) -> List[dict]:
        return self.project["regions"]

    @property
    def region_names(self) -> List[str]:
        return [r["name"] for r in self.regions] + [self.project["other_region"]["name"]]

    @property
    def hc(self) -> dict:
        return self.project["health_check"]

    @property
    def dns(self) -> dict:
        return self.project["dns"]


def _load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _rule_from_entry(entry: dict, target: str, stage: str, service: str, order: int) -> Rule:
    kinds = [k for k in RULE_KINDS if k in entry]
    if len(kinds) != 1:
        raise SourceError(f"[{service}] 规则必须且只能有一个匹配类型 {RULE_KINDS}: {entry}")
    kind = kinds[0]
    value = str(entry[kind]).strip()
    if kind in DOMAIN_KINDS:
        value = value.lower()
    return Rule(kind=kind, value=value, target=target, stage=stage, service=service,
                ev=str(entry.get("ev", "")), note=str(entry.get("note", "")), order=order)


def load(root: str) -> Model:
    src = os.path.join(root, "source")
    project = _load_yaml(os.path.join(src, "project.yaml"))
    g = _load_yaml(os.path.join(src, "groups.yaml"))
    evidence = _load_yaml(os.path.join(src, "evidence.yaml"))["evidence"]
    adblock = _load_yaml(os.path.join(src, "adblock.yaml"))

    groups: List[Group] = []
    for e in g["groups"]:
        opts = e.get("options", [])
        if opts == "standard":
            opts = list(STANDARD_OPTIONS)
        groups.append(Group(name=e["name"], category=e["category"], default=e["default"],
                            options=list(opts), residual=bool(e.get("residual", False)),
                            note=str(e.get("note", "")), special=str(e.get("special", ""))))

    services: List[Service] = []
    order = 0
    for fn in SERVICE_FILES:
        data = _load_yaml(os.path.join(src, "services", fn)) or {}
        for s in data.get("services", []):
            rules = []
            for entry in s.get("rules", []):
                order += 1
                stage = "lan" if s["group"] == "DIRECT" else ("service_ip" if ("ip4" in entry or "ip6" in entry) else "product")
                rules.append(_rule_from_entry(entry, s["group"], stage, s["id"], order))
            services.append(Service(id=s["id"], group=s["group"], title=str(s.get("title", s["id"])),
                                    rules=rules, shared_excluded=s.get("shared_excluded", []) or [],
                                    notes=str(s.get("notes", "") or ""), file=fn,
                                    upstream=s.get("upstream") or {}))

    # 用户本地覆盖（可选）：与生成默认值分离，更新统一源时不会被覆盖
    special = g["special_entries"]
    local_path = os.path.join(src, "local.yaml")
    if os.path.exists(local_path):
        local = _load_yaml(local_path) or {}
        for key, over in (local.get("special_entries") or {}).items():
            special[key] = {**special[key], **over}
        for s in local.get("extra_services") or []:
            rules = []
            for entry in s.get("rules", []):
                order += 1
                stage = "lan" if s["group"] == "DIRECT" else ("service_ip" if ("ip4" in entry or "ip6" in entry) else "product")
                rules.append(_rule_from_entry(entry, s["group"], stage, s["id"], order))
            services.append(Service(id=s["id"], group=s["group"], title=str(s.get("title", s["id"])) + "（本地）",
                                    rules=rules, shared_excluded=[], notes=str(s.get("notes", "") or ""),
                                    file="local.yaml", upstream=s.get("upstream") or {}))
        evidence = {**evidence, **(local.get("evidence") or {})}

    model = Model(root=root, project=project, groups=groups, special_entries=special,
                  evidence=evidence, services=services, adblock=adblock)
    validate(model)
    return model


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate(m: Model) -> None:
    errors: List[str] = []
    names = set(m.group_names)
    region_names = set(m.region_names)
    special_names = {m.special_entries["paypal_fixed"]["name"], m.special_entries["netflix_entry"]["name"]}
    referable = names | region_names | special_names | BUILTIN

    # 组成员只能引用地区入口、国外默认、专用入口、DIRECT/REJECT
    allowed_members = region_names | special_names | BUILTIN | {"国外默认"}
    for grp in m.groups:
        for mem in grp.members:
            if mem not in allowed_members:
                errors.append(f"组 {grp.name} 的成员 {mem} 不是地区入口 / 国外默认 / 专用入口 / DIRECT / REJECT")
        if grp.name == "PayPal" and "国外默认" in grp.members:
            errors.append("PayPal 不得跟随国外默认")
    if len(names) != len(m.groups):
        errors.append("存在重名策略组")

    # 地区正则
    for r in m.regions:
        try:
            check_regex_line_safe(r["regex"])
        except ValueError as e:
            errors.append(str(e))
    check_regex_line_safe(m.project["info_node_regex"])

    # 服务与规则
    seen: Dict[Tuple[str, str], Rule] = {}
    ids = [s.id for s in m.services]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"服务 id 重复：{dup}")
    for s in m.services:
        if s.group not in referable:
            errors.append(f"服务 {s.id} 指向不存在的组 {s.group}")
        if not isinstance(s.upstream, dict) or not set(s.upstream) <= set(COMMUNITY_EV_SOURCE.values()) or \
                not all(isinstance(v, list) and v and all(isinstance(x, str) and x for x in v) for v in s.upstream.values()):
            errors.append(f"服务 {s.id} 的 upstream 写法不对：只能有 dlc / bm7 两个键，值是非空的列表名列表")
        for r in s.rules:
            if r.ev not in m.evidence:
                errors.append(f"[{s.id}] {r.kind},{r.value} 引用了未登记的证据 {r.ev!r}")
            src = COMMUNITY_EV_SOURCE.get(r.ev)
            if src and not (isinstance(s.upstream, dict) and s.upstream.get(src)):
                errors.append(f"[{s.id}] {r.kind},{r.value} 的证据是 {r.ev}，但服务没有登记 upstream.{src} 列表")
            if r.kind in ("domain", "suffix") and not valid_domain(r.value):
                errors.append(f"[{s.id}] 非法域名 {r.value}")
            if r.kind == "ip4" and not valid_cidr(r.value, 4):
                errors.append(f"[{s.id}] 非法 IPv4 CIDR {r.value}")
            if r.kind == "ip6" and not valid_cidr(r.value, 6):
                errors.append(f"[{s.id}] 非法 IPv6 CIDR {r.value}")
            if r.kind == "keyword":
                errors.append(f"[{s.id}] 关键词规则 {r.value} 需要单独论证范围（本版本不允许）")
            if r.kind == "suffix" and r.value in BANNED_SHARED_SUFFIXES:
                errors.append(f"[{s.id}] 禁止整体收录共享云 / CDN 根域 {r.value}")
            if r.kind == "suffix" and r.value in GOOGLE_SHARED_ROOTS and s.group != "Google":
                errors.append(f"[{s.id}] Google 共享根域 {r.value} 只能归 Google 通用组")
            if r.key in seen:
                prev = seen[r.key]
                errors.append(f"规则重复 {r.kind},{r.value}：{prev.service}({prev.target}) 与 {s.id}({r.target})")
            else:
                seen[r.key] = r

    # 剩余集合（其他 AI / 其他流媒体 / 日本影音）不得抢走独立服务的流量
    residual = {g.name for g in m.groups if g.residual}
    all_rules = [r for s in m.services for r in s.rules if r.kind in DOMAIN_KINDS]
    for r in all_rules:
        if r.target not in residual:
            continue
        for o in all_rules:
            if o.target == r.target or o.target in residual:
                continue
            if covers(o.kind, o.value, r.kind, r.value) and m_group_is_independent(m, o.target):
                errors.append(f"剩余集合 {r.target} 的 {r.kind},{r.value} 落在独立服务 {o.target} 的 {o.kind},{o.value} 范围内")

    # 例外
    for e in m.adblock.get("exceptions", []):
        kind = "suffix" if "suffix" in e else "domain"
        if not valid_domain(e[kind]):
            errors.append(f"例外 {e} 域名非法")
        if e.get("ev") not in m.evidence:
            errors.append(f"例外 {e} 证据未登记")
        if e.get("target") == "DIRECT" and not e.get("allow_direct"):
            errors.append(f"例外 {e[kind]} 统一放行到 DIRECT 需要显式说明（allow_direct）")
    for sec in ("local_ads", "local_tracking"):
        for e in m.adblock.get(sec, []):
            if e.get("ev") not in m.evidence:
                errors.append(f"{sec} {e} 证据未登记")

    if errors:
        raise SourceError("统一源校验失败：\n  - " + "\n  - ".join(errors))


def m_group_is_independent(m: Model, name: str) -> bool:
    try:
        g = m.group(name)
    except KeyError:
        return False
    return not g.residual and g.category not in ("基础",)


# ---------------------------------------------------------------------------
# 规则计划
# ---------------------------------------------------------------------------

def specificity(r: Rule) -> Tuple[int, int]:
    """越具体越大：精确域名 > 后缀（层级越多越具体）> 关键词。"""
    if r.kind == "domain":
        return (3, r.value.count(".") + 1)
    if r.kind == "suffix":
        return (2, r.value.count(".") + 1)
    return (1, len(r.value))


def most_specific(rules: List[Rule], host: str) -> Optional[Rule]:
    hits = [r for r in rules if rule_matches_host(r.kind, r.value, host)]
    if not hits:
        return None
    return max(hits, key=lambda r: (specificity(r), -r.order))


def order_rules(rules: List[Rule]) -> List[Rule]:
    """贪心拓扑排序：若 a 的匹配范围被 b 覆盖且目标不同，则 a 必须排在 b 前面。
    在满足约束的前提下尽量保持源文件顺序，让同一服务的规则尽量连在一起。"""
    domain_rules = [r for r in rules if r.kind in DOMAIN_KINDS]
    ip_rules = [r for r in rules if r.kind in ("ip4", "ip6")]
    out: List[Rule] = []
    for group_rules, cover in ((domain_rules, "domain"), (ip_rules, "ip")):
        pending = sorted(group_rules, key=lambda r: (r.kind == "keyword", r.order))
        preds = {id(r): set() for r in pending}
        for a in pending:
            for b in pending:
                if a is b or a.target == b.target:
                    continue
                if cover == "domain":
                    if covers(b.kind, b.value, a.kind, a.value) and not covers(a.kind, a.value, b.kind, b.value):
                        preds[id(b)].add(id(a))
                else:
                    if (a.kind == b.kind) and cidr_covers(b.value, a.value) and a.value != b.value:
                        preds[id(b)].add(id(a))
        done = set()
        while pending:
            for i, r in enumerate(pending):
                if preds[id(r)] <= done:
                    out.append(r)
                    done.add(id(r))
                    pending.pop(i)
                    break
            else:  # pragma: no cover - 数据自相矛盾时才会发生
                raise SourceError("规则覆盖关系存在环，无法排序：" + ", ".join(f"{r.kind},{r.value}" for r in pending))
    return out


@dataclass
class Plan:
    lan: List[Rule]            # 第 2 阶段：局域网 + 系统联网检测（固定 DIRECT）
    exceptions: List[Rule]     # 第 3 阶段：误杀例外（按业务目标放行）
    ads_local: List[Rule]      # 第 3 阶段：自有广告 / 跟踪拦截
    product: List[Rule]        # 第 4–5 阶段：产品专属 + 共享依赖 / 厂商规则（已排序）
    service_ip: List[Rule]     # 第 7 阶段：服务专属 IP（no-resolve，已排序）

    def intended_target(self, host: str) -> Optional[str]:
        """按语义阶段求一个主机名的预期目标（不含远程集合；远程集合在测试里用样本模拟）。"""
        for stage in (self.lan, self.exceptions, self.ads_local):
            for r in stage:
                if rule_matches_host(r.kind, r.value, host):
                    return r.target
        r = most_specific(self.product, host)
        return r.target if r else None


def build_plan(m: Model) -> Plan:
    lan: List[Rule] = []
    order = 0
    for sfx in m.project["lan"]["domain_suffix"]:
        order += 1
        lan.append(Rule("suffix", sfx, "DIRECT", "lan", "lan", "maintainer", "局域网", order))
    for c in m.project["lan"]["ipv4"]:
        order += 1
        lan.append(Rule("ip4", c, "DIRECT", "lan", "lan", "maintainer", "局域网 / 保留地址", order))
    for c in m.project["lan"]["ipv6"]:
        order += 1
        lan.append(Rule("ip6", c, "DIRECT", "lan", "lan", "maintainer", "局域网 / 保留地址", order))
    for s in m.services:
        if s.group == "DIRECT":
            lan.extend(s.rules)

    product_all = [r for s in m.services if s.group != "DIRECT" for r in s.rules if r.stage == "product"]
    service_ip = [r for s in m.services if s.group != "DIRECT" for r in s.rules if r.stage == "service_ip"]
    product = order_rules(product_all)
    service_ip = order_rules(service_ip)

    # 广告拦截自有条目
    ads_local: List[Rule] = []
    for sec, label in (("local_ads", "广告"), ("local_tracking", "跟踪统计")):
        for e in m.adblock.get(sec, []):
            order += 1
            kind = "suffix" if "suffix" in e else "domain"
            ads_local.append(Rule(kind, e[kind].lower(), "广告拦截", "ads_local", sec, e.get("ev", ""),
                                  f"{label}：{e.get('note', '')}", order))

    # 例外：推导业务目标
    exceptions: List[Rule] = []
    errors = []
    for e in m.adblock.get("exceptions", []):
        order += 1
        kind = "suffix" if "suffix" in e else "domain"
        value = e[kind].lower()
        derived = most_specific(product, value)
        target = e.get("target")
        if derived and target and derived.target != target:
            errors.append(f"例外 {value} 写明目标 {target}，但产品规则归属是 {derived.target}")
        if not target:
            if not derived:
                errors.append(f"例外 {value} 不属于任何产品规则，必须写明 target")
                continue
            target = derived.target
        if kind == "suffix":
            for p in product:
                if covers("suffix", value, p.kind, p.value) and p.value != value and p.target != target:
                    errors.append(f"后缀例外 {value} 会遮挡更具体的产品规则 {p.kind},{p.value}→{p.target}")
        # 例外不得与自有拦截条目冲突
        for a in ads_local:
            if covers(kind, value, a.kind, a.value) or covers(a.kind, a.value, kind, value):
                errors.append(f"例外 {value} 与自有拦截条目 {a.value} 冲突")
        exceptions.append(Rule(kind, value, target, "exception", "exceptions", e.get("ev", ""),
                               f"误杀例外：{e.get('why', '')}", order))
    if errors:
        raise SourceError("规则计划失败：\n  - " + "\n  - ".join(errors))

    # 自有拦截条目若位于产品根域下，确认确实存在需要前置的产品规则（仅记录，不报错）
    return Plan(lan=lan, exceptions=exceptions, ads_local=ads_local, product=product, service_ip=service_ip)

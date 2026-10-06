"""加载统一源、校验，并生成与客户端无关的“规则计划”。"""
from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

from . import regions as region_rules
from . import strict as strict_mod
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
    clients: Tuple[str, ...] = ()                                   # 只生成到这些客户端；空 = 全部


# 社区证据 id → service.upstream 里的来源（该证据必须能在这些列表中找到）
COMMUNITY_EV_SOURCE = {"dlc": "dlc", "bm7-snap": "bm7"}
# upstream 允许的键：dlc（列表自身的条目）、dlc_resolved（展开 include 之后的整个集合，例如 geosite:cn）、bm7
UPSTREAM_KEYS = ("dlc", "dlc_resolved", "bm7")
# 客户端族：服务的 clients 字段只能写这些；不写表示全部生成
ALL_CLIENTS = ("mihomo", "singbox", "loon", "quantumultx")


def upstream_lists(s: "Service", src: str) -> List[str]:
    """某个来源下登记的全部列表名（dlc 含 dlc_resolved）。"""
    up = s.upstream if isinstance(s.upstream, dict) else {}
    names = list(up.get(src, []) or [])
    if src == "dlc":
        names += list(up.get("dlc_resolved", []) or [])
    return names


@dataclass
class Model:
    root: str
    project: dict
    groups: List[Group]
    special_entries: dict
    evidence: dict
    services: List[Service]
    adblock: dict
    region_spec: Optional[region_rules.Spec] = None      # 节点名称分地区的词表（source/regions.yaml + 本地补充）
    icons: dict = field(default_factory=dict)            # 策略组图标的登记（source/icons.yaml 的 icons 一节；没有这个文件时为空）
    icons_strict: bool = True                            # 公开模型：启用图标后每个策略组都必须有图；带本地覆盖的私密模型不强求
    strict: dict = field(default_factory=dict)           # 严格版的设定（source/strict.yaml 的 strict 一节）
    cn_domains: Tuple[List[str], List[str]] = field(default_factory=lambda: ([], []))   # 国内域名清单：(后缀, 精确域名)
    cn_data_header: List[str] = field(default_factory=list)    # 清单数据文件头部讲来源与授权的几行
    _node_rx: Optional[Tuple[Dict[str, str], Dict[str, str]]] = field(default=None, repr=False, compare=False)

    # 便捷访问
    @property
    def group_names(self) -> List[str]:
        return [g.name for g in self.groups]

    def group(self, name: str) -> Group:
        for g in self.groups:
            if g.name == name:
                return g
        raise KeyError(name)

    def icon_url(self, group_name: str) -> Optional[str]:
        """这个策略组的图标地址；没有启用图标时返回 None。
        地址 = base_url + 文件名按 UTF-8 逐字节百分号编码 + ext：编码后只剩字母、数字和 % - . _ ~，
        可以原样写进 Loon / Quantumult X 用逗号分隔参数的一行里。
        启用了图标而这个组在 available 里找不到图：公开模型直接报错（宁可生成失败，也不要悄悄少一个图标）；
        带本地覆盖的私密模型（本地改过组名等）就不给这个组写图标。"""
        ic = self.icons or {}
        if not ic.get("enabled"):
            return None
        file_name = self.icon_file(group_name)
        if file_name not in set(ic.get("available") or []) | set(ic.get("pending") or []):
            if self.icons_strict:
                raise SourceError(f"策略组 {group_name} 没有图标：source/icons.yaml 的 available 里没有“{file_name}”。"
                                  "先把图放进图标仓库并登记到 available（文件名和组名不同时写进 renamed），或者把 icons.enabled 改成 false")
            return None
        return ic["base_url"] + urllib.parse.quote(file_name + ic.get("ext", ".png"), safe="")

    def icon_file(self, group_name: str) -> str:
        """这个策略组用图标仓库里的哪张图（文件名，不带扩展名）：改名表里有就用它，否则和组名相同。"""
        ic = self.icons or {}
        return (ic.get("renamed") or {}).get(group_name) or group_name

    @property
    def regions(self) -> List[dict]:
        """六个明确地区：[{id, name}]（顺序即 regions.yaml 里的顺序）。"""
        return [{"id": r.id, "name": r.name} for r in self.region_spec.regions]

    @property
    def other_region(self) -> dict:
        return {"id": self.region_spec.other.id, "name": self.region_spec.other.name}

    @property
    def region_names(self) -> List[str]:
        return [r["name"] for r in self.regions] + [self.other_region["name"]]

    def _node_rx_all(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        if self._node_rx is None:                # 每个模型只拼一次
            self._node_rx = region_rules.compose_all(self.region_spec)
        return self._node_rx

    def node_regexes(self) -> Dict[str, str]:
        """宽的那套：{地区 id（含其他地区）: 节点名称筛选正则}。手动组、PayPal 的美国固定入口用。"""
        return self._node_rx_all()[0]

    def node_regexes_strict(self) -> Dict[str, str]:
        """严的那套：{地区 id: 正则}，只收“名字只指向这一个地区”的节点。自动 / 故障转移 / 负载均衡用。"""
        return self._node_rx_all()[1]

    @property
    def hc(self) -> dict:
        return self.project["health_check"]

    @property
    def dns(self) -> dict:
        return self.project["dns"]


class _StrictLoader(yaml.SafeLoader):
    """同一层出现重复键时报错：PyYAML 默认让后一个覆盖前一个，拼写或复制错误会被悄悄吞掉（审核 F09）。"""


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise SourceError(f"YAML 重复键 {key!r}（第 {key_node.start_mark.line + 1} 行）")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.load(f, Loader=_StrictLoader)
        except SourceError as e:
            raise SourceError(f"{os.path.basename(path)}：{e}")


# 各类条目允许的键：拼错的键（例如 sufix、tartget）以前会被默默忽略（审核 F09）
SERVICE_KEYS = {"id", "group", "title", "upstream", "rules", "shared_excluded", "notes", "clients"}
RULE_EXTRA_KEYS = {"ev", "note", "nature"}
GROUP_KEYS = {"name", "category", "default", "options", "residual", "note", "special"}
# shared_excluded：只说明“不归本服务”的主机。写了 to 的，表示“它会去这个组”，是一条要核对的断言：
# probe 列出具体主机，测试（tests/test_real_data.py，用上游数据的成员快照）和 tools/check_real_routes.py（官方内核）
# 会检查四个客户端是否真的把它们交给 to。不写 to 的只是“没有收”，不保证去向（2026-10-03 审核 F01 之后加的区分）。
EXCLUDED_KEYS = {"host", "ev", "why", "to", "probe"}
AD_KEYS = {"suffix", "domain", "ev", "note"}
EXCEPTION_KEYS = {"suffix", "domain", "target", "ev", "why", "allow_direct"}
ADBLOCK_KEYS = {"remote_lists", "local_ads", "local_tracking", "httpdns", "exceptions", "rewrite_mitm"}
LOCAL_KEYS = {"special_entries", "extra_services", "evidence", "node_names"}
ICON_KEYS = {"enabled", "base_url", "ext", "renamed", "pending", "checked_commit", "checked", "available"}
STRICT_KEYS = {"publish_base", "domestic_lists", "qx_fallback"}
STRICT_LIST_KEYS = {"url", "own", "tag", "ev", "source"}
# 严格版只给这两端生成；各端能引用的自有清单文件
STRICT_CLIENTS = ("loon", "quantumultx")
STRICT_OWN_CN = {"loon": strict_mod.LOON_CN_REL, "quantumultx": strict_mod.QX_CN_REL}
# 图标地址要原样写进 Loon / Quantumult X 的一行：不能有逗号、空格、引号、反引号这些会被当成分隔符的字符
_ICON_BASE_RX = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~%/-]*/$")
_ICON_EXT_RX = re.compile(r"^\.[A-Za-z0-9]{2,5}$")


def _check_icons(ic: dict) -> List[str]:
    """source/icons.yaml 的 icons 一节自身的格式（每个组有没有图，在生成各端产物时由 Model.icon_url 检查）。"""
    errors: List[str] = []
    if not isinstance(ic.get("enabled", False), bool):
        errors.append("icons.yaml：enabled 只能写 true / false")
    if not ic.get("enabled"):
        return errors
    base, ext = ic.get("base_url"), ic.get("ext", ".png")
    if not isinstance(base, str) or not _ICON_BASE_RX.match(base):
        errors.append(f"icons.yaml：base_url 必须是 https:// 开头、以 / 结尾，且不含逗号、空格、引号的地址：{base!r}")
    if not isinstance(ext, str) or not _ICON_EXT_RX.match(ext):
        errors.append(f"icons.yaml：ext 应是 .png 这样的扩展名：{ext!r}")
    avail = ic.get("available")
    if not isinstance(avail, list) or not avail or not all(isinstance(x, str) and x.strip() == x and x for x in avail):
        errors.append("icons.yaml：available 应是图标文件名（不带扩展名）的列表，不能为空")
        avail = []
    dup = sorted({x for x in avail if avail.count(x) > 1})
    if dup:
        errors.append(f"icons.yaml：available 里有重复的名字 {dup}")
    renamed = ic.get("renamed") or {}
    if not isinstance(renamed, dict):
        errors.append("icons.yaml：renamed 应是“策略组名: 文件名”的键值表")
        renamed = {}
    for group, file_name in renamed.items():
        if file_name not in avail:
            errors.append(f"icons.yaml：renamed 把 {group} 指向“{file_name}”，available 里没有它")
    pending = ic.get("pending") or []
    if not isinstance(pending, list) or not all(isinstance(x, str) and x.strip() == x and x for x in pending):
        errors.append("icons.yaml：pending 应是图标文件名（不带扩展名）的列表")
        pending = []
    for x in pending:
        if x in avail:
            errors.append(f"icons.yaml：{x} 已经在 available 里了，不该再留在 pending 里")
        if "/" in x or "\\" in x:
            errors.append(f"icons.yaml：pending 里的名字不能含斜杠：{x!r}")
    if len(set(pending)) != len(pending):
        errors.append("icons.yaml：pending 里有重复的名字")
    for x in avail:
        if "/" in x or "\\" in x:
            errors.append(f"icons.yaml：available 里的名字不能含斜杠：{x!r}（文件名里的斜杠写全角“／”，再在 renamed 里对应）")
    return errors


def _check_strict(st: dict, evidence: dict) -> List[str]:
    """source/strict.yaml 的 strict 一节。地址和标签要原样写进 Loon / Quantumult X 用逗号分隔参数的一行。"""
    errors: List[str] = []
    base = st.get("publish_base")
    if not isinstance(base, str) or not _ICON_BASE_RX.match(base):
        errors.append(f"strict.yaml：publish_base 必须是 https:// 开头、以 / 结尾，且不含逗号、空格、引号的地址：{base!r}")
    lists = st.get("domestic_lists")
    if not isinstance(lists, dict) or set(lists) != set(STRICT_CLIENTS):
        errors.append(f"strict.yaml：domestic_lists 要给 {' / '.join(STRICT_CLIENTS)} 各写一份")
        lists = {}
    entries = [(c, e) for c in STRICT_CLIENTS for e in (lists.get(c) or [])]
    fb = st.get("qx_fallback")
    if not isinstance(fb, dict) or fb.get("own") != strict_mod.QX_FALLBACK_REL:
        errors.append(f"strict.yaml：qx_fallback.own 只能是 {strict_mod.QX_FALLBACK_REL}")
    else:
        entries.append(("quantumultx 的域名兜底", fb))
    for client in STRICT_CLIENTS:
        if not lists.get(client) and lists:
            errors.append(f"strict.yaml：{client} 的国内域名清单不能为空（严格版要靠它认出国内网站）")
    for where, e in entries:
        errors += _unknown(f"strict.yaml {where} {e}", e, STRICT_LIST_KEYS)
        if not isinstance(e, dict):
            continue
        if ("url" in e) == ("own" in e):
            errors.append(f"strict.yaml {where} {e}：url（订阅上游文件）和 own（自有清单）必须且只能写一个")
        tag = e.get("tag")
        if not isinstance(tag, str) or not tag or any(ch in tag for ch in ", \"'`=\n"):
            errors.append(f"strict.yaml {where} {e}：tag 不能为空，也不能含逗号、空格、引号、等号")
        if "url" in e:
            url = e["url"]
            if not isinstance(url, str) or not re.match(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~%/-]+$", url):
                errors.append(f"strict.yaml {where}：url 必须是 https:// 地址，且不含逗号、空格、引号：{url!r}")
            if e.get("ev") not in evidence:
                errors.append(f"strict.yaml {where} {url}：证据 {e.get('ev')!r} 未登记")
        elif "own" in e and where in STRICT_OWN_CN and e["own"] != STRICT_OWN_CN[where]:
            errors.append(f"strict.yaml {where}：own 只能是 {STRICT_OWN_CN[where]}")
    tags = [(c, e.get("tag")) for c, e in entries if isinstance(e, dict)]
    for client in STRICT_CLIENTS:
        mine = [t for c, t in tags if c.startswith(client)]
        if len(mine) != len(set(mine)):
            errors.append(f"strict.yaml：{client} 的远程规则标签有重复")
    return errors


def _check_cn_domains(cn: Tuple[List[str], List[str]]) -> List[str]:
    """source/data/cn-domains.txt：由 tools/update_cn_list.py 生成，这里只查写法（内容与上游快照是否一致由那个工具核对）。"""
    suffix, full = cn
    errors: List[str] = []
    if len(suffix) < 1000:
        errors.append(f"{strict_mod.CN_DATA_REL}：后缀只有 {len(suffix)} 条，不像一份完整的国内域名清单")
    bad = [d for d in list(suffix) + list(full) if not valid_domain(d)]
    if bad:
        errors.append(f"{strict_mod.CN_DATA_REL}：有 {len(bad)} 条不是合法域名，例如 {bad[:5]}")
    every = list(suffix) + list(full)
    if len(set(suffix)) != len(suffix) or len(set(full)) != len(full):
        errors.append(f"{strict_mod.CN_DATA_REL}：有重复的条目")
    sset = set(suffix)

    def covered(name: str, itself: bool) -> bool:
        parts = name.split(".")
        return any(".".join(parts[i:]) in sset for i in range(0 if itself else 1, len(parts)))

    redundant = [d for d in suffix if covered(d, False)] + [d for d in full if covered(d, True)]
    if redundant:
        errors.append(f"{strict_mod.CN_DATA_REL}：有 {len(redundant)} 条已被别的后缀覆盖（应由生成工具去掉），例如 {redundant[:5]}")
    if "cn" not in sset:
        errors.append(f"{strict_mod.CN_DATA_REL}：没有整段 cn——严格版要靠它把没有单独列出的 .cn 域名交给国内直连")
    del every
    return errors


def _unknown(where: str, entry, allowed: set) -> List[str]:
    if not isinstance(entry, dict):
        return [f"{where}：应为键值表，实际是 {type(entry).__name__}"]
    extra = sorted(set(entry) - allowed)
    return [f"{where}：未知字段 {extra}"] if extra else []


def _rule_from_entry(entry: dict, target: str, stage: str, service: str, order: int) -> Rule:
    kinds = [k for k in RULE_KINDS if k in entry]
    if len(kinds) != 1:
        raise SourceError(f"[{service}] 规则必须且只能有一个匹配类型 {RULE_KINDS}: {entry}")
    kind = kinds[0]
    value = str(entry[kind]).strip()
    if kind in DOMAIN_KINDS:
        value = value.lower()
    nature = str(entry.get("nature", "") or "")
    if nature not in ("", "shared"):
        raise SourceError(f"[{service}] nature 只能写 shared：{entry}")
    return Rule(kind=kind, value=value, target=target, stage=stage, service=service,
                ev=str(entry.get("ev", "")), note=str(entry.get("note", "")), order=order, nature=nature)


def load(root: str, include_local: bool = True) -> Model:
    """include_local=False：不读 source/local.yaml，得到可以公开的模型（审核 F11：个人覆盖只进私密产物）。"""
    src = os.path.join(root, "source")
    project = _load_yaml(os.path.join(src, "project.yaml"))
    g = _load_yaml(os.path.join(src, "groups.yaml"))
    evidence = _load_yaml(os.path.join(src, "evidence.yaml"))["evidence"]
    adblock = _load_yaml(os.path.join(src, "adblock.yaml"))
    regions_data = _load_yaml(os.path.join(src, "regions.yaml"))
    local_node_names = None
    schema_errors: List[str] = []
    schema_errors += _unknown("adblock.yaml", adblock, ADBLOCK_KEYS)
    for sec in ("local_ads", "local_tracking"):
        for e in adblock.get(sec, []) or []:
            schema_errors += _unknown(f"adblock.yaml {sec} {e}", e, AD_KEYS)
    for e in adblock.get("exceptions", []) or []:
        schema_errors += _unknown(f"adblock.yaml exceptions {e}", e, EXCEPTION_KEYS)
    for e in g["groups"]:
        schema_errors += _unknown(f"groups.yaml {e.get('name', e)}", e, GROUP_KEYS)

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
            schema_errors += _unknown(f"{fn} 服务 {s.get('id', s)}", s, SERVICE_KEYS)
            for x in s.get("shared_excluded", []) or []:
                schema_errors += _unknown(f"{fn} {s.get('id')} shared_excluded {x}", x, EXCLUDED_KEYS)
            for entry in s.get("rules", []) or []:
                schema_errors += _unknown(f"{fn} {s.get('id')} 规则 {entry}", entry, set(RULE_KINDS) | RULE_EXTRA_KEYS)
            rules = []
            for entry in s.get("rules", []):
                order += 1
                stage = "lan" if s["group"] == "DIRECT" else ("service_ip" if ("ip4" in entry or "ip6" in entry) else "product")
                rules.append(_rule_from_entry(entry, s["group"], stage, s["id"], order))
            services.append(Service(id=s["id"], group=s["group"], title=str(s.get("title", s["id"])),
                                    rules=rules, shared_excluded=s.get("shared_excluded", []) or [],
                                    notes=str(s.get("notes", "") or ""), file=fn,
                                    upstream=s.get("upstream") or {}, clients=tuple(s.get("clients") or ())))

    # 用户本地覆盖（可选）：与生成默认值分离，更新统一源时不会被覆盖
    special = g["special_entries"]
    local_path = os.path.join(src, "local.yaml")
    if include_local and os.path.exists(local_path):
        local = _load_yaml(local_path) or {}
        schema_errors += _unknown("local.yaml", local, LOCAL_KEYS)
        for s in local.get("extra_services") or []:
            schema_errors += _unknown(f"local.yaml 服务 {s.get('id', s)}", s, SERVICE_KEYS)
            for entry in s.get("rules", []) or []:
                schema_errors += _unknown(f"local.yaml {s.get('id')} 规则 {entry}", entry, set(RULE_KINDS) | RULE_EXTRA_KEYS)
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
                                    file="local.yaml", upstream=s.get("upstream") or {},
                                    clients=tuple(s.get("clients") or ())))
        evidence = {**evidence, **(local.get("evidence") or {})}
        local_node_names = local.get("node_names")

    # 节点名称分地区的词表：公开模型只用 regions.yaml；本地补充词、指定节点只进私密模型
    region_spec, region_errors = region_rules.parse(regions_data, local_node_names)
    schema_errors += region_errors
    # 策略组图标（可选文件：没有 icons.yaml 就是不带图标）
    icons: dict = {}
    icons_path = os.path.join(src, "icons.yaml")
    if os.path.exists(icons_path):
        icons_data = _load_yaml(icons_path) or {}
        schema_errors += _unknown("icons.yaml", icons_data, {"icons"})
        icons = icons_data.get("icons") if isinstance(icons_data, dict) else None
        if not isinstance(icons, dict):
            schema_errors.append("icons.yaml：缺少 icons 一节")
            icons = {}
        else:
            schema_errors += _unknown("icons.yaml icons", icons, ICON_KEYS)
            schema_errors += _check_icons(icons)
    # 严格版（Loon / Quantumult X 各多生成一份）的设定与国内域名清单
    strict_data = _load_yaml(os.path.join(src, "strict.yaml")) or {}
    schema_errors += _unknown("strict.yaml", strict_data, {"strict"})
    strict_conf = strict_data.get("strict") if isinstance(strict_data, dict) else None
    if not isinstance(strict_conf, dict):
        schema_errors.append("strict.yaml：缺少 strict 一节")
        strict_conf = {}
    else:
        schema_errors += _unknown("strict.yaml strict", strict_conf, STRICT_KEYS)
        schema_errors += _check_strict(strict_conf, evidence)
    cn_domains, cn_header = ([], []), []
    try:
        cn_domains = strict_mod.load_cn_domains(root)
        cn_header = strict_mod.data_header(root)
        schema_errors += _check_cn_domains(cn_domains)
    except OSError as e:
        schema_errors.append(f"读不到国内域名清单 {strict_mod.CN_DATA_REL}（{e}）：用 tools/update_cn_list.py 生成")
    if schema_errors:
        raise SourceError("统一源校验失败：\n  - " + "\n  - ".join(schema_errors))
    has_local = include_local and os.path.exists(local_path)
    model = Model(root=root, project=project, groups=groups, special_entries=special,
                  evidence=evidence, services=services, adblock=adblock, region_spec=region_spec,
                  icons=icons, icons_strict=not has_local, strict=strict_conf,
                  cn_domains=cn_domains, cn_data_header=cn_header)
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
        if grp.name in grp.members:
            errors.append(f"组 {grp.name} 引用了自己（会形成循环）")
    if len(names) != len(m.groups):
        errors.append("存在重名策略组")

    # 专用入口：PayPal 固定入口所在地区必须存在；用户给的已验证节点正则要能写进 Loon / QX 的一行里
    region_ids = {r["id"] for r in m.regions}
    if m.special_entries["paypal_fixed"].get("region") not in region_ids:
        errors.append(f"PayPal 固定入口的 region {m.special_entries['paypal_fixed'].get('region')!r} 不是已有地区")
    rx = m.special_entries["netflix_entry"].get("verified_node_regex")
    if rx:
        try:
            check_regex_line_safe(rx)
            re.compile(rx)
        except (ValueError, re.error) as e:
            errors.append(f"Netflix 已验证节点正则无效：{e}")

    # 服务与规则
    seen: Dict[Tuple[str, str], Rule] = {}
    ids = [s.id for s in m.services]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"服务 id 重复：{dup}")
    for s in m.services:
        if s.group not in referable:
            errors.append(f"服务 {s.id} 指向不存在的组 {s.group}")
        if not isinstance(s.upstream, dict) or not set(s.upstream) <= set(UPSTREAM_KEYS) or \
                not all(isinstance(v, list) and v and all(isinstance(x, str) and x for x in v) for v in s.upstream.values()):
            errors.append(f"服务 {s.id} 的 upstream 写法不对：只能有 {' / '.join(UPSTREAM_KEYS)} 这几个键，值是非空的列表名列表")
        bad_clients = [c for c in s.clients if c not in ALL_CLIENTS]
        if bad_clients:
            errors.append(f"服务 {s.id} 的 clients 只能写 {' / '.join(ALL_CLIENTS)}：{bad_clients}")
        for x in s.shared_excluded:
            to, probe = x.get("to"), x.get("probe")
            if to is None and probe is None:
                continue
            where = f"服务 {s.id} 的 shared_excluded {x.get('host')!r}"
            if to is None or not probe:
                errors.append(f"{where}：to（去向）和 probe（用来核对的具体主机）要一起写")
                continue
            if to not in names | {"DIRECT"}:
                errors.append(f"{where}：to 写的 {to!r} 不是已有的策略组")
            if not isinstance(probe, list) or not all(isinstance(h, str) and valid_domain(h) for h in probe):
                errors.append(f"{where}：probe 要写成具体主机名的列表（不能带通配符）")
        for r in s.rules:
            if r.ev not in m.evidence:
                errors.append(f"[{s.id}] {r.kind},{r.value} 引用了未登记的证据 {r.ev!r}")
            src = COMMUNITY_EV_SOURCE.get(r.ev)
            if src and not upstream_lists(s, src):
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
        if not valid_domain(str(e.get(kind, ""))):
            errors.append(f"例外 {e} 域名非法")
        if e.get("target") is not None and e["target"] not in names | {"DIRECT"}:
            errors.append(f"例外 {e[kind]} 的目标 {e['target']} 不是已有的业务组")
        if e.get("ev") not in m.evidence:
            errors.append(f"例外 {e} 证据未登记")
        if e.get("target") == "DIRECT" and not e.get("allow_direct"):
            errors.append(f"例外 {e[kind]} 统一放行到 DIRECT 需要显式说明（allow_direct）")
    for sec in ("local_ads", "local_tracking"):
        for e in m.adblock.get(sec, []):
            if e.get("ev") not in m.evidence:
                errors.append(f"{sec} {e} 证据未登记")
            kinds = [k for k in ("suffix", "domain") if k in e]
            if len(kinds) != 1 or not valid_domain(str(e[kinds[0]]).lower()):
                errors.append(f"{sec} {e} 必须且只能有一个合法的 suffix / domain")

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
    service_clients: Dict[str, Tuple[str, ...]] = field(default_factory=dict)   # 只生成到部分客户端的服务
    # 严格版（Loon / Quantumult X）多出的一段：要真实地址的名单里，标准版没有固定直连规则的那些名字。
    # 这些名字必须先在本机解析（解析发生在选出口之前），所以严格版把它们固定成直连，不让“国内 DNS 解析 + 代理出口”出现
    real_ip_direct: List[Rule] = field(default_factory=list)

    def emitted_to(self, rule: Rule, family: str) -> bool:
        clients = self.service_clients.get(rule.service) or ALL_CLIENTS
        return family in clients

    def product_for(self, family: str) -> List[Rule]:
        """某个客户端族实际写出的产品规则（顺序不变）。"""
        return [r for r in self.product if self.emitted_to(r, family)]

    def service_ip_for(self, family: str) -> List[Rule]:
        return [r for r in self.service_ip if self.emitted_to(r, family)]

    def intended_target(self, host: str, family: Optional[str] = None) -> Optional[str]:
        """按语义阶段求一个主机名的预期目标（不含远程集合；远程集合在测试里用样本模拟）。
        family 给出时只看该客户端族实际写出的产品规则（例如国内常用网站只写进 mihomo / sing-box）。"""
        for stage in (self.lan, self.exceptions, self.ads_local):
            for r in stage:
                if rule_matches_host(r.kind, r.value, host):
                    return r.target
        r = most_specific(self.product_for(family) if family else self.product, host)
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

    lan_keys = {r.key for r in lan}
    real_ip_direct: List[Rule] = []
    for i, x in enumerate(m.project["dns"]["real_ip"], 1):
        kind = "suffix" if "suffix" in x else "domain"
        value = str(x[kind]).lower()
        if (kind, value) not in lan_keys:
            real_ip_direct.append(Rule(kind, value, "DIRECT", "lan", "real_ip", "maintainer",
                                       "要真实地址的名单：解析在选出口之前，严格版固定直连", i))

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
                errors.append(f"例外 {value} 与自有拦截条目 {a.value} 冲突（要放行它，先从 adblock.yaml 的 local_ads / local_tracking 删掉 {a.value}，再加例外）")
        exceptions.append(Rule(kind, value, target, "exception", "exceptions", e.get("ev", ""),
                               f"误杀例外：{e.get('why', '')}", order))
    if errors:
        raise SourceError("规则计划失败：\n  - " + "\n  - ".join(errors))

    # 自有拦截条目若位于产品根域下，确认确实存在需要前置的产品规则（仅记录，不报错）
    return Plan(lan=lan, exceptions=exceptions, ads_local=ads_local, product=product, service_ip=service_ip,
                service_clients={s.id: s.clients for s in m.services if s.clients}, real_ip_direct=real_ip_direct)

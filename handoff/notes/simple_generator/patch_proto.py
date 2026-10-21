"""在 scratch 里的工程副本（proto/）上套一份“简易版”的最小改法原型。只改副本，不碰仓库。
每处改动都用“原文必须正好出现一次”的替换，顺便数出要改几处。
用法：python3 -B patch_proto.py <proto 目录>
"""
import os
import sys

P = sys.argv[1]
count = {}


def sub(rel, old, new, n=1):
    path = os.path.join(P, rel)
    with open(path, encoding="utf-8") as f:
        s = f.read()
    got = s.count(old)
    assert got == n, f"{rel}: 期望出现 {n} 次，实际 {got}：{old[:80]!r}"
    s = s.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    count[rel] = count.get(rel, 0) + 1


# ---------------- regions.py：全部节点（去掉提示行）的筛选 ----------------
sub("generator/regions.py", '''def compose_all(spec: Spec) -> Tuple[Dict[str, str], Dict[str, str]]:''', '''def compose_any(spec: Spec) -> str:
    """全部节点（简易版“国外默认”用）：不是提示行的都收；local.yaml 指定 none 的不收、指定了组的照收。
    应当等于宽的那套各条的并集（由测试核对）。"""
    c = _Composer(spec)
    s = spec
    body = c.info_common()
    weak = c.weak()
    if weak is not None:
        sign = _alt([c.txt(s.ids + [s.other.id]), c.any_flag()])
        body += "(?:" + _pos(sign) + "|" + _neg(weak) + ")"
    core = body + ".*$"
    names = sorted(s.assign)
    if not names:
        return "(?i)^" + core
    excl = "(?!(?:" + "|".join(lit(n) for n in names) + ")$)"
    keep = [n for n in names if s.assign[n] != NONE]
    if keep:
        return "(?i)^(?:(?:" + "|".join(lit(n) for n in keep) + ")$|" + excl + core + ")"
    return "(?i)^" + excl + core


def compose_all(spec: Spec) -> Tuple[Dict[str, str], Dict[str, str]]:''')
sub("generator/regions.py", '''        for rx in list(loose.values()) + list(strict.values()):
            check_composed(rx)''', '''        for rx in list(loose.values()) + list(strict.values()) + [compose_any(spec)]:
            check_composed(rx)''')

# ---------------- model.py ----------------
sub("generator/model.py", '''    _node_rx: Optional[Tuple[Dict[str, str], Dict[str, str]]] = field(default=None, repr=False, compare=False)
''', '''    _node_rx: Optional[Tuple[Dict[str, str], Dict[str, str]]] = field(default=None, repr=False, compare=False)
    _node_rx_any: Optional[str] = field(default=None, repr=False, compare=False)
''')
sub("generator/model.py", '''    @property
    def hc(self) -> dict:''', '''    def node_regex_any(self) -> str:
        """全部节点（去掉提示行）：简易版“国外默认”用。"""
        if self._node_rx_any is None:
            self._node_rx_any = region_rules.compose_any(self.region_spec)
        return self._node_rx_any

    @property
    def hc(self) -> dict:''')

# ---------------- groups.py：layout 参数，简易版另起一个函数，完整版那条路一个字不动 ----------------
sub("generator/groups.py", '''ALL_MODES = ["manual_first", "manual", "auto", "failover", "balance"]
''', '''ALL_MODES = ["manual_first", "manual", "auto", "failover", "balance"]
LAYOUTS = ("full", "simple")
ANY_LABEL = "all"                    # 简易版“国外默认”的全部节点筛选（Loon 里叫 F-ALL）
''')
sub("generator/groups.py", '''def build_groups(m: Model, modes: List[str]) -> List[GroupSpec]:
    """modes：该客户端支持的地区模式（顺序即入口组成员顺序，第一个为默认）。"""
    p = m.project''', '''def build_groups(m: Model, modes: List[str], layout: str = "full") -> List[GroupSpec]:
    """modes：该客户端支持的地区模式（顺序即入口组成员顺序，第一个为默认）。layout：full（完整版）| simple（简易版）。"""
    if layout not in LAYOUTS:
        raise ValueError(f"layout 只能是 {LAYOUTS}：{layout!r}")
    if layout == "simple":
        return _build_simple(m)
    p = m.project''')
sub("generator/groups.py", '''                    comment="手动优先·自动兜底：手选节点健康检查失败时用同地区自动测速，恢复后切回"))
    return out''', '''                    comment="手动优先·自动兜底：手选节点健康检查失败时用同地区自动测速，恢复后切回"))
    return out


def _build_simple(m: Model) -> List[GroupSpec]:
    """简易版（方案 ③）：每个地区一个给人用的组 = [X·自动] + 宽筛选的节点，默认 X·自动；X·自动 = 严筛选的自动测速；
    国外默认 = 七个地区 + 全部节点（去掉提示行）。业务组、PayPal·美国固定、其他地区和完整版相同。"""
    p = m.project
    wide_rx, strict_rx = m.node_regexes(), m.node_regexes_strict()
    suffix = {x["id"]: x["suffix"] for x in p["region_modes"]}
    if "auto" not in suffix:
        raise ValueError("简易版要用 region_modes 里 auto 的后缀（X·自动）")
    out: List[GroupSpec] = []
    for g in m.groups:
        if g.special == "foreign_default":
            out.append(GroupSpec(name=g.name, kind="select", members=g.members, role="foreign_default", comment=g.note,
                                 nodes=NodeFilter(label=ANY_LABEL, regex=m.node_regex_any())))
        else:
            out.append(GroupSpec(name=g.name, kind="select", members=g.members, role="business", comment=g.note))
    paypal = m.special_entries["paypal_fixed"]
    out.append(GroupSpec(
        name=paypal["name"], kind="select", role="paypal_fixed",
        nodes=NodeFilter(label="paypal", regex=None if paypal.get("pinned_node_name") else wide_rx[paypal["region"]],
                         pinned=paypal.get("pinned_node_name") or None),
        comment=("固定节点：" + paypal["pinned_node_name"]) if paypal.get("pinned_node_name") else
                "尚未指定固定节点：在美国节点中手动选一个；被选节点删除后会回到本组第一个美国节点（见已知限制）"))
    for r in m.regions:
        out.append(GroupSpec(
            name=r["name"], kind="select", role="region_entry",
            members=[region_mode_name(r["name"], suffix["auto"])],
            nodes=NodeFilter(label=r["id"], regex=wide_rx[r["id"]]),
            comment="地区组：默认“自动”（同地区自动测速）；也可以直接点一个节点固定用它（挂了不会自动换）"))
    other = m.other_region
    out.append(GroupSpec(
        name=other["name"], kind="select", role="other_region",
        nodes=NodeFilter(label=other["id"], regex=wide_rx[other["id"]]),
        comment="纯手动；不提供跨国自动模式。名称里认不出六个地区的节点、落地在其他国家的节点都在这里"))
    for r in m.regions:
        out.append(GroupSpec(
            name=region_mode_name(r["name"], suffix["auto"]), kind="url-test", role="region_mode", mode="auto", hidden=True,
            nodes=NodeFilter(label=r["id"] + AUTO_SUFFIX, regex=strict_rx[r["id"]]),
            comment="自动测速：同地区延迟最低（不代表带宽 / 解锁 / IP 信誉）；只用名字只指向本地区的节点"))
    return out''')

# ---------------- Loon：成员组在前、筛选名在后 ----------------
sub("generator/emit_loon.py", "def build(m: Model, plan: Plan, sub_urls: List[str] | None = None, strict: bool = False) -> str:",
    "def build(m: Model, plan: Plan, sub_urls: List[str] | None = None, strict: bool = False, layout: str = \"full\") -> str:")
sub("generator/emit_loon.py", "    groups = build_groups(m, MODES)\n", "    groups = build_groups(m, MODES, layout)\n")
sub("generator/emit_loon.py", '''        if g.nodes is not None:
            members = [_filter_name(g.nodes)]
        else:
            members = list(g.members)
            if g.backup_nodes is not None:
                members.append(_filter_name(g.backup_nodes))''', '''        members = list(g.members)                 # 简易版：先写明的成员组，再接筛选（完整版的节点组没有成员组，结果不变）
        if g.nodes is not None:
            members.append(_filter_name(g.nodes))
        if g.backup_nodes is not None:
            members.append(_filter_name(g.backup_nodes))''')

# ---------------- Quantumult X ----------------
sub("generator/emit_qx.py", "def build(m: Model, plan: Plan, sub_urls: List[str] | None = None, strict: bool = False) -> str:",
    "def build(m: Model, plan: Plan, sub_urls: List[str] | None = None, strict: bool = False, layout: str = \"full\") -> str:")
sub("generator/emit_qx.py", "    groups = build_groups(m, MODES)\n", "    groups = build_groups(m, MODES, layout)\n")
sub("generator/emit_qx.py", '''        if g.nodes is not None:
            body = f"server-tag-regex={_regex(g.nodes)}"
        else:
            body = ", ".join(_pol(x) for x in g.members)''', '''        parts = [_pol(x) for x in g.members]       # 简易版：写明的成员在前，正则在后（混写没有官方示例，见 docs/06）
        if g.nodes is not None:
            parts.append(f"server-tag-regex={_regex(g.nodes)}")
        body = ", ".join(parts)''')

# ---------------- mihomo：_group_dict 本来就能同时写 proxies 和 include-all-providers + filter ----------------
sub("generator/emit_mihomo.py", "def build(m: Model, plan: Plan, flavor: str, sub_urls: List[str] | None = None) -> str:",
    "def build(m: Model, plan: Plan, flavor: str, sub_urls: List[str] | None = None, layout: str = \"full\") -> str:")
sub("generator/emit_mihomo.py", "    groups = build_groups(m, MODES)\n", "    groups = build_groups(m, MODES, layout)\n")

# ---------------- Stash ----------------
sub("generator/emit_stash.py", "from .groups import AUTO_SUFFIX, GroupSpec, NodeFilter, build_groups, shared_filter_labels",
    "from .groups import ANY_LABEL, AUTO_SUFFIX, GroupSpec, NodeFilter, build_groups, shared_filter_labels")
sub("generator/emit_stash.py", '''    if nf.pinned:
        ph = placeholders(m)[_region_of(m, nf)]
        return "^(?:" + lit(nf.pinned) + "|" + lit(ph) + ")$"
    return exclude_builtins(nf.final_regex())''', '''    if nf.pinned:
        ph = placeholders(m)[_region_of(m, nf)]
        return "^(?:" + lit(nf.pinned) + "|" + lit(ph) + ")$"
    if nf.label == ANY_LABEL:                  # 简易版“国外默认”的全部节点：另外不选本项目的占位节点
        rx = exclude_builtins(nf.final_regex())
        head = "(?i)^"
        return head + "(?!(?:" + "|".join(lit(x) for x in placeholders(m).values()) + ")$)" + rx[len(head):]
    return exclude_builtins(nf.final_regex())''')
sub("generator/emit_stash.py", '''        rx = re.compile(filter_regex(m, g.nodes))
        hit = [name for name in ph.values() if rx.search(name)]
        want = ph[_region_of(m, g.nodes)]
        if hit != [want]:''', '''        rx = re.compile(filter_regex(m, g.nodes))
        hit = [name for name in ph.values() if rx.search(name)]
        want = None if g.nodes.label == ANY_LABEL else ph[_region_of(m, g.nodes)]
        if hit != ([want] if want else []):''')
sub("generator/emit_stash.py", "def build(m: Model, plan: Plan, sub_urls: Optional[List[str]] = None, strict: bool = False) -> str:",
    "def build(m: Model, plan: Plan, sub_urls: Optional[List[str]] = None, strict: bool = False, layout: str = \"full\") -> str:")
sub("generator/emit_stash.py", "    groups = build_groups(m, MODES)\n", "    groups = build_groups(m, MODES, layout)\n")

# ---------------- sing-box：成员组 + 本机筛出的节点；有成员组时筛选为空也不放占位 ----------------
sub("generator/emit_singbox.py", '''def build(m: Model, plan: Plan, variant: str, nodes: Optional[List[dict]] = None,
          renamed: Optional[dict] = None) -> str:''', '''def build(m: Model, plan: Plan, variant: str, nodes: Optional[List[dict]] = None,
          renamed: Optional[dict] = None, layout: str = "full") -> str:''')
sub("generator/emit_singbox.py", "    groups = build_groups(m, MODES)\n    nodes = nodes or []", "    groups = build_groups(m, MODES, layout)\n    nodes = nodes or []")
sub("generator/emit_singbox.py", '''    def pick(nf: NodeFilter) -> List[str]:
        nonlocal need_placeholder
        ok = _compile(nf)
        sel = [t for t in node_tags if ok(renamed.get(t, t))]
        if not sel:''', '''    def pick(nf: NodeFilter, allow_empty: bool = False) -> List[str]:
        nonlocal need_placeholder
        ok = _compile(nf)
        sel = [t for t in node_tags if ok(renamed.get(t, t))]
        if not sel and not allow_empty:''')
sub("generator/emit_singbox.py", '''        if g.nodes is not None:
            members = pick(g.nodes)
        else:
            members = _selectable_members(g.members)
        if g.kind == "select":
            ob = {"type": "selector", "tag": g.name, "outbounds": members}
            if g.nodes is None and members:
                ob["default"] = members[0]''', '''        members = _selectable_members(g.members)
        if g.nodes is not None:
            members += pick(g.nodes, allow_empty=bool(members))     # 简易版：写明的成员组在前，节点在后
        if g.kind == "select":
            ob = {"type": "selector", "tag": g.name, "outbounds": members}
            if g.members and members:
                ob["default"] = members[0]''')

# ---------------- verify：按前缀分派（以前按完整文件名，新文件会被悄悄跳过）；Stash 带成员组的筛选组 ----------------
sub("generator/verify.py", '''        elif base in ("loon.conf", "loon-strict.conf"):
            probs = check_loon(text, strict=base == "loon-strict.conf", own=own)
        elif base in ("quantumultx.conf", "quantumultx-strict.conf"):
            probs = check_qx(text, strict=base == "quantumultx-strict.conf", own=own)
        elif base in ("stash.yaml", "stash-strict.yaml"):
            probs = check_stash(text, strict=base == "stash-strict.yaml")''', '''        elif base.startswith("loon") and base.endswith(".conf"):
            probs = check_loon(text, strict=base.endswith("-strict.conf"), own=own)
        elif base.startswith("quantumultx") and base.endswith(".conf"):
            probs = check_qx(text, strict=base.endswith("-strict.conf"), own=own)
        elif base.startswith("stash") and base.endswith(".yaml"):
            probs = check_stash(text, strict=base.endswith("-strict.yaml"))''')
sub("generator/verify.py", '''            hit = [p["name"] for p in holders if rx.search(p["name"])]
            if len(hit) != 1:''', '''            hit = [p["name"] for p in holders if rx.search(p["name"])]
            if g.get("proxies") and len(hit) > 1:
                problems.append(f"组 {g['name']} 的筛选选中了不止一个占位节点 {hit}")
            elif not g.get("proxies") and len(hit) != 1:''')

# ---------------- build.py ----------------
sub("build.py", '''    strict.LOON_CN_REL: strict.loon_cn_list,''', '''    # 简易版（原型）：和完整版并存；规则、DNS 与完整版逐字相同，只有策略组不同。严格版引用的自有远程规则文件共用上面那几个
    "mihomo/mihomo-simple-profile.yaml": lambda m, p: emit_mihomo.build(m, p, "profile", layout="simple"),
    "mihomo/mihomo-simple-core.yaml": lambda m, p: emit_mihomo.build(m, p, "core", layout="simple"),
    "sing-box/sing-box-simple-1.14.json": lambda m, p: emit_singbox.build(m, p, "1.14", layout="simple"),
    "sing-box/sing-box-simple-1.12.json": lambda m, p: emit_singbox.build(m, p, "1.12", layout="simple"),
    "loon/loon-simple.conf": lambda m, p: emit_loon.build(m, p, layout="simple"),
    "loon/loon-simple-strict.conf": lambda m, p: emit_loon.build(m, p, strict=True, layout="simple"),
    "quantumultx/quantumultx-simple.conf": lambda m, p: emit_qx.build(m, p, layout="simple"),
    "quantumultx/quantumultx-simple-strict.conf": lambda m, p: emit_qx.build(m, p, strict=True, layout="simple"),
    "stash/stash-simple.yaml": lambda m, p: emit_stash.build(m, p, layout="simple"),
    "stash/stash-simple-strict.yaml": lambda m, p: emit_stash.build(m, p, strict=True, layout="simple"),
    strict.LOON_CN_REL: strict.loon_cn_list,''')

print("改动处数：", count, "合计", sum(count.values()))

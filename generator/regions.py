"""节点名称分地区。

从 source/regions.yaml 的词表拼出各客户端通用的筛选正则（compose），并提供同一套规则的逐步判断实现
（Classifier）：检查工具用它解释“为什么进这个组”，测试用它和拼出来的正则逐个节点交叉核对。

规则（名称只是初筛，不证明实际出口）：
  0. 本地指定（local.yaml 的 node_names.assign）优先；信息节点不进任何组。
  1. 有“有效”的国旗 → 按国旗：其他国家的旗 → 其他地区；让位地区的旗遇到别的地区旗时让位。
  2. 没有 → 看文字：其他国家的有效词 → 其他地区；地区的有效词 → 该地区；
     词都在中转位置、且没有别的地区的有效词 → 仍归该地区；让位地区遇到别的地区的有效词时让位。
  3. 都没有 → 其他地区。
“有效” = 后面没有箭头，前面不是 via / 经 / 解锁 这类词（via 要单独成词）；文字还要求不紧跟中转词。

正则只用 ICU、regexp2、Python 三个引擎都支持的写法：(?i)、分组、交替、字符类、否定前瞻、定长否定后顾、\\s、\\xHH。
  - mihomo 用 regexp2（源码可查）；sing-box 的分组在生成时由 Python 完成；
  - Loon / Quantumult X 用什么引擎没有官方说明。推断是苹果系统自带的 NSRegularExpression（底层是 ICU），
    所以用 ICU 实际跑过一遍（tools/check_icu.py）；这仍然不等于在 App 里验证过。
不使用肯定前瞻（写成双重否定），也不出现英文逗号、双引号、反引号、等号和空格——
它们在 Loon / QX 的行语法或 mihomo 的 filter 里有特殊含义。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 不能原样出现在筛选正则里的字符 → 十六进制转义（ICU、regexp2、Python 都支持 \xHH）
_HEX = {",": r"\x2C", '"': r"\x22", "`": r"\x60", "=": r"\x3D", " ": r"\x20"}
FORBIDDEN_IN_REGEX = (",", '"', "`", "=", " ", "\n", "\r")
RI_FIRST, RI_LAST = 0x1F1E6, 0x1F1FF            # 区域指示符 🇦–🇿，两个一组构成国旗
_RI = "[" + chr(RI_FIRST) + "-" + chr(RI_LAST) + "]"
_LATIN_WORD = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 .'-]*[A-Za-z0-9])?$")
_ASCII_LETTERS = re.compile(r"^[A-Za-z]+$")
_FLAG_CODE = re.compile(r"^[A-Z]{2}$")
NONE = "none"                                   # node_names.assign 里表示“不进任何组”

REGION_KEYS = {"id", "name", "yields", "flags", "words", "latin", "patterns"}
OTHER_KEYS = {"words", "latin", "patterns"}
RULES_KEYS = {"info", "transit_after", "transit_before", "arrows", "neutral_flags"}
TOP_KEYS = {"rules", "regions", "other_region", "other_countries"}
LOCAL_KEYS = {"extra_words", "assign"}
LOCAL_WORD_KEYS = {"words", "latin"}


def flag(code: str) -> str:
    return "".join(chr(RI_FIRST + ord(c) - ord("A")) for c in code)


def lit(s: str) -> str:
    """把一段文字写成正则里的字面量。"""
    return "".join(_HEX.get(ch) or re.escape(ch) for ch in s)


@dataclass
class Words:
    id: str
    name: str
    yields: bool = False
    flags: List[str] = field(default_factory=list)       # ISO 两位字母
    words: List[str] = field(default_factory=list)
    latin: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)


@dataclass
class Spec:
    regions: List[Words]
    other: Words                                           # 其他国家的词表；id / name 是“其他地区”
    info_words: List[str]
    info_latin: List[str]
    after: List[str]
    before: List[str]
    arrows: List[str]
    neutral_flags: List[str]
    assign: Dict[str, str] = field(default_factory=dict)   # 节点完整名称 → 地区 id / 其他地区 id / none

    @property
    def ids(self) -> List[str]:
        return [r.id for r in self.regions]

    def region(self, rid: str) -> Words:
        for r in self.regions:
            if r.id == rid:
                return r
        raise KeyError(rid)

    def name_of(self, gid: str) -> str:
        return self.other.name if gid == self.other.id else self.region(gid).name


# ---------------------------------------------------------------------------
# 读取与校验
# ---------------------------------------------------------------------------

def _str_list(where: str, v, errors: List[str]) -> List[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        errors.append(f"{where}：应为列表")
        return []
    out = []
    for x in v:
        if not isinstance(x, str) or not x:
            errors.append(f"{where}：{x!r} 不是非空字符串（NO、ON、YES 这类词在 YAML 里要加引号）")
            continue
        out.append(x)
    return out


def _check_words(where: str, words: List[str], latin: List[str], patterns: List[str], errors: List[str]) -> None:
    for w in words:
        if any(c in w for c in ("\n", "\r", "\t")):
            errors.append(f"{where} words：{w!r} 含换行或制表符")
        if w.isascii() and re.fullmatch(r"[A-Za-z0-9 ]+", w):
            errors.append(f"{where} words：{w!r} 是纯英文 / 数字，请放进 latin（那里会检查前后不紧挨英文字母）")
    for w in latin:
        if not _LATIN_WORD.match(w) or len(w) < 2 or "  " in w:
            errors.append(f"{where} latin：{w!r} 只能由英文字母、数字、空格、点、撇号、连字符组成，首尾是字母或数字，至少 2 个字符")
    for p in patterns:
        for bad in FORBIDDEN_IN_REGEX:
            if bad in p:
                errors.append(f"{where} patterns：{p!r} 含不允许的字符 {bad!r}")
        if "(?=" in p or "(?<=" in p:
            errors.append(f"{where} patterns：{p!r} 用了肯定前瞻 / 后顾（含等号），请改用否定形式")
        try:
            re.compile(p)
        except re.error as e:
            errors.append(f"{where} patterns：{p!r} 不是合法正则（{e}）")
    for label, items in (("words", words), ("latin", [x.lower() for x in latin])):
        dup = sorted({x for x in items if items.count(x) > 1})
        if dup:
            errors.append(f"{where} {label}：重复 {dup}")


def parse(data: dict, local: Optional[dict] = None) -> Tuple[Optional[Spec], List[str]]:
    """data：regions.yaml 的内容；local：local.yaml 里的 node_names（可为空）。返回 (词表, 错误列表)。"""
    errors: List[str] = []

    def unknown(where, entry, allowed):
        if not isinstance(entry, dict):
            errors.append(f"{where}：应为键值表")
            return True
        extra = sorted(set(entry) - allowed)
        if extra:
            errors.append(f"{where}：未知字段 {extra}")
        return False

    if unknown("regions.yaml", data, TOP_KEYS):
        return None, errors
    rules = data.get("rules") or {}
    unknown("regions.yaml rules", rules, RULES_KEYS)
    info = rules.get("info") or {}
    unknown("regions.yaml rules.info", info, {"words", "latin"})

    def words_of(where: str, e: dict, rid: str, name: str, yields: bool = False) -> Words:
        w = Words(id=rid, name=name, yields=yields,
                  flags=_str_list(f"{where} flags", e.get("flags"), errors),
                  words=_str_list(f"{where} words", e.get("words"), errors),
                  latin=_str_list(f"{where} latin", e.get("latin"), errors),
                  patterns=_str_list(f"{where} patterns", e.get("patterns"), errors))
        for c in w.flags:
            if not _FLAG_CODE.match(c):
                errors.append(f"{where} flags：{c!r} 不是两位大写字母")
        _check_words(where, w.words, w.latin, w.patterns, errors)
        return w

    regions: List[Words] = []
    for e in data.get("regions") or []:
        if unknown(f"regions.yaml 地区 {e.get('id', e) if isinstance(e, dict) else e}", e, REGION_KEYS):
            continue
        rid, name = e.get("id"), e.get("name")
        if not isinstance(rid, str) or not re.fullmatch(r"[a-z][a-z0-9]*", rid or ""):
            errors.append(f"regions.yaml：地区 id {rid!r} 只能是小写字母和数字")
            continue
        if not isinstance(name, str) or not name:
            errors.append(f"regions.yaml 地区 {rid}：缺少 name")
            continue
        r = words_of(f"regions.yaml 地区 {rid}", e, rid, name, bool(e.get("yields", False)))
        if not (r.flags or r.words or r.latin or r.patterns):
            errors.append(f"regions.yaml 地区 {rid}：词表是空的")
        regions.append(r)
    if not regions:
        errors.append("regions.yaml：没有任何地区")
    o = data.get("other_region") or {}
    unknown("regions.yaml other_region", o, {"id", "name"})
    oid, oname = o.get("id") or "other", o.get("name") or "其他地区"
    oc = data.get("other_countries") or {}
    unknown("regions.yaml other_countries", oc, OTHER_KEYS)
    other = words_of("regions.yaml other_countries", oc if isinstance(oc, dict) else {}, oid, oname)

    spec = Spec(regions=regions, other=other,
                info_words=_str_list("regions.yaml rules.info.words", info.get("words") if isinstance(info, dict) else None, errors),
                info_latin=_str_list("regions.yaml rules.info.latin", info.get("latin") if isinstance(info, dict) else None, errors),
                after=_str_list("regions.yaml rules.transit_after", rules.get("transit_after"), errors),
                before=_str_list("regions.yaml rules.transit_before", rules.get("transit_before"), errors),
                arrows=_str_list("regions.yaml rules.arrows", rules.get("arrows"), errors),
                neutral_flags=_str_list("regions.yaml rules.neutral_flags", rules.get("neutral_flags"), errors))
    _check_words("regions.yaml rules.info", spec.info_words, spec.info_latin, [], errors)
    for c in spec.neutral_flags:
        if not _FLAG_CODE.match(c):
            errors.append(f"regions.yaml rules.neutral_flags：{c!r} 不是两位大写字母")
    for label, items in (("transit_after", spec.after), ("transit_before", spec.before), ("arrows", spec.arrows)):
        for x in items:
            if any(c in x for c in ("\n", "\r", "\t")) or x != x.strip():
                errors.append(f"regions.yaml rules.{label}：{x!r} 含空白字符")

    # 本地补充（只进私密产物）
    if local:
        if not unknown("local.yaml node_names", local, LOCAL_KEYS):
            extra = local.get("extra_words") or {}
            if not isinstance(extra, dict):
                errors.append("local.yaml node_names.extra_words：应为 {地区 id: {words: [...], latin: [...]}}")
                extra = {}
            by_id = {r.id: r for r in regions}
            by_id[oid] = other
            for rid, add in extra.items():
                where = f"local.yaml node_names.extra_words.{rid}"
                if rid not in by_id:
                    errors.append(f"{where}：没有这个地区（可用：{', '.join(by_id)}）")
                    continue
                if unknown(where, add, LOCAL_WORD_KEYS):
                    continue
                by_id[rid].words += _str_list(f"{where} words", add.get("words"), errors)
                by_id[rid].latin += _str_list(f"{where} latin", add.get("latin"), errors)
                _check_words(where, by_id[rid].words, by_id[rid].latin, [], errors)
            for e in local.get("assign") or []:
                where = f"local.yaml node_names.assign {e}"
                if unknown(where, e, {"name", "region"}):
                    continue
                n, rid = e.get("name"), e.get("region")
                if not isinstance(n, str) or not n.strip() or "\n" in n:
                    errors.append(f"{where}：name 要写节点的完整名称")
                    continue
                if rid not in list(by_id) + [NONE]:
                    errors.append(f"{where}：region 只能是 {', '.join(by_id)} 或 {NONE}（不进任何组）")
                    continue
                if n.casefold() in {k.casefold() for k in spec.assign}:
                    errors.append(f"{where}：同一个节点指定了两次（不分大小写）")
                    continue
                spec.assign[n] = rid

    # 跨地区检查
    ids = [r.id for r in regions]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"regions.yaml：地区 id 重复 {dup}")
    if oid in ids or oid == NONE or NONE in ids:
        errors.append(f"regions.yaml：{oid!r} / {NONE!r} 是保留的 id")
    names = [r.name for r in regions] + [oname]
    for dup in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"regions.yaml：地区名称重复 {dup}")
    if sum(1 for r in regions if r.yields) > 1:
        errors.append("regions.yaml：最多只能有一个让位（yields）地区")
    owner: Dict[Tuple[str, str], str] = {}
    for r in regions + [other]:
        label = r.id if r is not other else "other_countries"
        for kind, items in (("flag", r.flags), ("word", r.words), ("latin", [x.lower() for x in r.latin])):
            for x in set(items):
                if (kind, x) in owner:
                    errors.append(f"词表（含 local.yaml 的补充）：{x!r} 同时出现在 {owner[(kind, x)]} 和 {label}")
                owner[(kind, x)] = label
    for c in spec.neutral_flags:
        if ("flag", c) in owner:
            errors.append(f"regions.yaml：国旗 {c} 既在 neutral_flags 里，又在 {owner[('flag', c)]} 里")
    if errors:
        return None, errors
    try:
        for rx in compose(spec).values():
            check_composed(rx)
    except (re.error, ValueError) as e:
        return None, [f"节点筛选正则无法生成：{e}"]
    return spec, []


def check_composed(rx: str) -> None:
    for bad in FORBIDDEN_IN_REGEX:
        if bad in rx:
            raise ValueError(f"生成的节点筛选正则含不允许的字符 {bad!r}")
    re.compile(rx)


# ---------------------------------------------------------------------------
# 拼正则
# ---------------------------------------------------------------------------

class _Sep:
    def __repr__(self):
        return "SEP"


_SEP = _Sep()


def _units(word: str, latin: bool) -> list:
    if not latin:
        return list(word)
    return [_SEP if ch == " " else ch.lower() for ch in word]


def _unit_rx(u) -> str:
    return r"[\s_-]?" if u is _SEP else lit(u)


def _trie(words: List[str], latin: bool) -> str:
    """把一组词压成前缀树形式，减少引擎逐个尝试整词的次数。"""
    root: dict = {}
    for w in words:
        node = root
        for u in _units(w, latin):
            node = node.setdefault(u, {})
        node[""] = True

    def key(k):
        return (1, "") if k is _SEP else (0, k)

    def emit(node: dict) -> str:
        end = "" in node
        kids = sorted(((k, v) for k, v in node.items() if k != ""), key=lambda kv: key(kv[0]))
        if not kids:
            return ""
        singles = [k for k, v in kids if k is not _SEP and set(v) == {""}]
        branches = []
        if len(singles) > 1:
            branches.append("[" + "".join(_cls(s) for s in singles) + "]")
        elif singles:
            branches.append(lit(singles[0]))
        for k, v in kids:
            if k is not _SEP and set(v) == {""}:
                continue
            branches.append(_unit_rx(k) + emit(v))
        if len(branches) == 1 and not end:
            return branches[0]
        body = "(?:" + "|".join(branches) + ")"
        return body + "?" if end else body

    return emit(root)


def _cls(ch: str) -> str:
    """字符类内部的字面量。"""
    return _HEX.get(ch) or re.escape(ch)


def _guard(words: List[str], latin: bool) -> str:
    """“下一个字符在这些词的首字符集合里”的快速判断（写成双重否定前瞻，不出现等号）。
    放在最前面，绝大多数位置一步就能排除，不用逐个词去试。"""
    first = sorted({_units(w, latin)[0] for w in words})
    return "(?!(?![" + "".join(_cls(c) for c in first) + "]))"


def _guarded(words: List[str], latin: bool) -> str:
    words = sorted(set(words))
    return _guard(words, latin) + _trie(words, latin)


_LEADING_LOOKBEHINDS = re.compile(r"^(?:\(\?<![^()]*\))*")


def _pattern_guard(p: str) -> str:
    """patterns 里的正则片段：能看出第一个字符的范围时，也加上同样的快速判断。"""
    rest = p[_LEADING_LOOKBEHINDS.match(p).end():]
    if rest.startswith("[") and not rest.startswith("[^"):
        end = rest.find("]", 2)
        if end != -1 and "\\" not in rest[:end]:
            return "(?!(?!" + rest[:end + 1] + "))"
    elif rest and (rest[0].isalnum() or ord(rest[0]) > 0x7F) and not (len(rest) > 1 and rest[1] in "?*{"):
        return "(?!(?![" + _cls(rest[0].lower()) + "]))"
    return ""


def _alt(parts: List[str]) -> Optional[str]:
    parts = [p for p in parts if p]
    return "(?:" + "|".join(parts) + ")" if parts else None


def _pos(x: Optional[str]) -> str:
    """名字里某处出现 x。x 为空时条件不可能成立。"""
    return "(?!)" if x is None else "(?!(?!.*" + x + "))"


def _neg(x: Optional[str]) -> str:
    """名字里任何位置都不出现 x。x 为空时条件恒成立。"""
    return "" if x is None else "(?!.*" + x + ")"


class _Composer:
    def __init__(self, spec: Spec):
        self.s = spec
        self.by_id = {r.id: r for r in spec.regions}
        self.by_id[spec.other.id] = spec.other
        self.arrow = "(?!.*(?:" + "|".join(lit(a) for a in spec.arrows) + "))" if spec.arrows else ""
        self.after = r"(?!\s*(?:" + "|".join(lit(a) for a in spec.after) + "))" if spec.after else ""
        # 否定后顾要定长：同样长度的词并成一组（Python 不支持变长后顾）
        by_len: Dict[int, List[str]] = {}
        latin_before: List[str] = []
        for b in spec.before:
            if _ASCII_LETTERS.match(b):
                latin_before.append(lit(b))
            else:
                by_len.setdefault(len(b), []).append(lit(b))
        self.before = "".join(f"(?<!(?:{'|'.join(v)}))(?<!(?:{'|'.join(v)})\\s)" for _, v in sorted(by_len.items()))
        # 英文词（via）要单独成词：前面是非英文字母，或者它就在名字开头。Latvia、Bolivia 里的 via 不算
        for b in latin_before:
            self.before += "".join(f"(?<!{head}{b})(?<!{head}{b}\\s)" for head in ("[^A-Za-z]", "^"))

    def _parts(self, ids: List[str], before: str = "") -> List[str]:
        """这些地区的词，按“中文等原样词 / 英文词 / 正则片段”三类各成一个分支。
        before（前面不能是 via、解锁 这类词）放在快速判断之后：否定后顾比较贵，先排除掉不可能的位置。"""
        words, latin, pats = [], [], []
        for i in ids:
            r = self.by_id[i]
            words += r.words
            latin += r.latin
            pats += r.patterns
        parts = []
        if words:
            words = sorted(set(words))
            parts.append(_guard(words, False) + before + _trie(words, False))
        if latin:
            latin = sorted(set(latin))
            parts.append(_guard(latin, True) + r"(?<![A-Za-z])" + before + _trie(latin, True) + r"(?![A-Za-z])")
        parts += [_pattern_guard(p) + before + f"(?:{p})" for p in pats]
        return parts

    def txt(self, ids: List[str]) -> Optional[str]:
        """名字里出现这些地区的任意一个词。"""
        return _alt(self._parts(ids))

    def eff(self, ids: List[str]) -> Optional[str]:
        """这些地区的“有效”词：前面不是 via / 解锁 这类词，后面不紧跟中转词，再往后也没有箭头。"""
        t = _alt(self._parts(ids, self.before))
        return None if t is None else t + self.after + self.arrow

    def _align(self) -> str:
        """从一串国旗的开头成对跳过，只在对齐的位置上认国旗：🇨🇳🇺🇸 连写时不能把中间的 🇳🇺 当成一面旗。
        这串国旗前面是 via / 解锁 这类词时（“解锁 🇺🇸🇯🇵”），整串都不算。"""
        return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})(?:{_RI}{_RI})*"

    def eflag(self, ids: List[str]) -> Optional[str]:
        """属于这些地区的“有效”国旗（后面没有箭头，所在的一串国旗前面不是 via / 解锁 这类词）。"""
        flags = sorted({flag(c) for i in ids for c in self.by_id[i].flags})
        if not flags:
            return None
        return self._align() + _guarded(flags, latin=False) + self.arrow

    def eflag_other(self) -> str:
        """其他国家的有效国旗：不属于任何地区、也不在 neutral_flags 里的任意一面旗。"""
        known = sorted({flag(c) for r in self.s.regions for c in r.flags} | {flag(c) for c in self.s.neutral_flags})
        skip = "(?!" + _trie(known, latin=False) + ")" if known else ""
        return self._align() + skip + _RI + _RI + self.arrow

    def info(self) -> str:
        parts = []
        if self.s.info_words:
            parts.append(_guarded(self.s.info_words, latin=False))
        if self.s.info_latin:
            parts.append(r"(?<![A-Za-z])" + _guarded(self.s.info_latin, latin=True))
        return _neg(_alt(parts))

    def wrap(self, gid: str, body: str) -> str:
        core = body + ".*$"
        names = sorted(self.s.assign)
        if not names:
            return "(?i)^" + core
        excl = "(?!(?:" + "|".join(lit(n) for n in names) + ")$)"
        mine = [n for n in names if self.s.assign[n] == gid]
        if mine:
            return "(?i)^(?:(?:" + "|".join(lit(n) for n in mine) + ")$|" + excl + core + ")"
        return "(?i)^" + excl + core

    def compose(self) -> Dict[str, str]:
        s = self.s
        ids = s.ids
        oid = s.other.id
        out: Dict[str, str] = {}
        no_other_flag = _neg(self.eflag_other())
        no_region_flag = _neg(self.eflag(ids))
        for r in s.regions:
            others = [i for i in ids if i != r.id]
            if r.yields:
                by_flag = _pos(self.eflag([r.id])) + _neg(self.eflag(others))
                by_text = _pos(self.txt([r.id])) + _neg(self.eff(others + [oid]))
            else:
                by_flag = _pos(self.eflag([r.id]))
                by_text = (_neg(self.eff([oid])) + "(?:" + _pos(self.eff([r.id])) + "|"
                           + _pos(self.txt([r.id])) + _neg(self.eff(others)) + ")")
            out[r.id] = self.wrap(r.id, self.info() + no_other_flag + "(?:" + by_flag + "|" + no_region_flag + by_text + ")")
        other = ("(?:" + _pos(self.eflag_other()) + "|" + no_region_flag
                 + "(?:" + _pos(self.eff([oid])) + "|" + _neg(self.txt(ids)) + "))")
        out[oid] = self.wrap(oid, self.info() + other)
        return out


def compose(spec: Spec) -> Dict[str, str]:
    """{地区 id: 筛选正则}，含“其他地区”。每个非信息节点至少匹配其中一条（被指定为 none 的除外）。"""
    return _Composer(spec).compose()


# ---------------------------------------------------------------------------
# 同一套规则的逐步判断（不经过上面拼出来的正则）
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    groups: List[str]                 # 地区 id（可能两个）、其他地区 id，或空（信息节点 / 指定不进组）
    basis: str                        # assign | info | flag | text | none
    hits: Dict[str, List[str]]        # 地区 id / 其他地区 id → 名字里找到的词或国旗
    notes: List[str]                  # 给人看的说明


def _is_ri(ch: str) -> bool:
    return RI_FIRST <= ord(ch) <= RI_LAST


class Classifier:
    def __init__(self, spec: Spec):
        self.s = spec
        self._all = spec.regions + [spec.other]
        self._flag_owner = {flag(c): w.id for w in spec.regions for c in w.flags}
        self._neutral = {flag(c) for c in spec.neutral_flags}
        self._rx = {w.id: ([re.compile(re.escape(x), re.I) for x in w.words]
                           + [self._latin_rx(x) for x in w.latin]
                           + [re.compile(p, re.I) for p in w.patterns]) for w in self._all}
        self._after = re.compile(r"\s*(?:" + "|".join(re.escape(a) for a in spec.after) + ")", re.I) if spec.after else None
        self._before = (re.compile("(?:" + "|".join((r"(?<![A-Za-z])" if _ASCII_LETTERS.match(b) else "") + re.escape(b)
                                                    for b in spec.before) + r")\s?$", re.I)
                        if spec.before else None)
        self._info = ([re.compile(re.escape(x), re.I) for x in spec.info_words]
                      + [re.compile(r"(?<![A-Za-z])" + self._latin_body(x), re.I) for x in spec.info_latin])
        self._assign = [(re.compile(re.escape(k), re.I), v) for k, v in spec.assign.items()]

    @staticmethod
    def _latin_body(word: str) -> str:
        return r"[\s_-]?".join(re.escape(p) for p in word.split(" "))

    def _latin_rx(self, word: str):
        return re.compile(r"(?<![A-Za-z])" + self._latin_body(word) + r"(?![A-Za-z])", re.I)

    # --- 找词 ---
    def _spans(self, w: Words, name: str) -> List[Tuple[int, int]]:
        spans = []
        for rx in self._rx[w.id]:
            pos = 0
            while True:                     # 逐个位置找，包含互相重叠的出现
                m = rx.search(name, pos)
                if not m:
                    break
                spans.append(m.span())
                pos = m.start() + 1
        return sorted(set(spans))

    def _has_arrow_after(self, name: str, end: int) -> bool:
        return any(a in name[end:] for a in self.s.arrows)

    def _effective(self, name: str, start: int, end: int) -> bool:
        if self._before is not None and self._before.search(name[:start]):
            return False
        if self._after is not None and self._after.match(name[end:]):
            return False
        return not self._has_arrow_after(name, end)

    def _flags(self, name: str) -> List[Tuple[str, bool]]:
        """按对齐的两两一组切出国旗，返回 [(国旗, 是否有效)]。
        有效 = 后面没有箭头，且所在的一串国旗前面不是 via / 解锁 这类词。"""
        out, i, n = [], 0, len(name)
        while i < n:
            if _is_ri(name[i]):
                j = i
                while j < n and _is_ri(name[j]):
                    j += 1
                led = self._before is not None and bool(self._before.search(name[:i]))
                for k in range(i, j - 1, 2):
                    out.append((name[k:k + 2], not led and not self._has_arrow_after(name, k + 2)))
                i = j
            else:
                i += 1
        return out

    def is_info(self, name: str) -> Optional[str]:
        for rx in self._info:
            m = rx.search(name)
            if m:
                return m.group(0)
        return None

    def classify(self, name: str) -> Verdict:
        s = self.s
        oid = s.other.id
        for rx, rid in self._assign:
            if rx.fullmatch(name):
                return Verdict([] if rid == NONE else [rid], "assign", {}, ["local.yaml 指定"])
        w = self.is_info(name)
        if w:
            return Verdict([], "info", {}, [f"信息节点，含“{w}”"])

        # 先把名字里的国旗和词都找出来
        eff_flags: Dict[str, List[str]] = {}
        seen_flags: Dict[str, List[str]] = {}
        for f, effective in self._flags(name):
            if f in self._neutral:
                continue
            owner = self._flag_owner.get(f, oid)        # 不属于任何地区的国旗都算其他国家
            seen_flags.setdefault(owner, []).append(f)
            if effective:
                eff_flags.setdefault(owner, []).append(f)
        txt: Dict[str, List[str]] = {}
        eff: Dict[str, List[str]] = {}
        for w_ in self._all:
            for a, b in self._spans(w_, name):
                txt.setdefault(w_.id, []).append(name[a:b])
                if self._effective(name, a, b):
                    eff.setdefault(w_.id, []).append(name[a:b])
        region_words = "、".join(f"{r.name}（{txt[r.id][0]}）" for r in s.regions if r.id in txt)

        # 1. 国旗
        if oid in eff_flags:
            notes = [f"带其他国家的国旗 {''.join(eff_flags[oid])}"]
            if region_words:
                notes.append(f"名字里的 {region_words} 不算落地")
            return Verdict([oid], "flag", {**txt, **eff_flags}, notes)
        region_flags = [r.id for r in s.regions if r.id in eff_flags]
        if region_flags:
            groups, notes = [], []
            for r in s.regions:
                if r.id not in eff_flags:
                    continue
                if r.yields and len(region_flags) > 1:
                    notes.append(f"{r.name}让位：名字里还有别的地区的国旗")
                    continue
                groups.append(r.id)
            if len(groups) > 1:
                notes.append("同时有 " + "、".join(s.name_of(g) for g in groups) + " 的国旗，说不清落地，两个组都进")
            ignored = "、".join(f"{r.name}（{txt[r.id][0]}）" for r in s.regions if r.id in txt and r.id not in groups)
            if ignored:
                notes.append(f"按国旗算；名字里的 {ignored} 不算落地")
            return Verdict(groups, "flag", {**txt, **eff_flags}, notes)

        # 2. 文字
        if oid in eff:
            notes = [f"带其他国家的词“{eff[oid][0]}”"]
            if region_words:
                notes.append(f"名字里的 {region_words} 不算落地")
            return Verdict([oid], "text", txt, notes)
        groups, notes = [], []
        for r in s.regions:
            if r.id not in txt:
                continue
            others_eff = [x.id for x in s.regions if x.id != r.id and x.id in eff]
            if r.yields:
                if others_eff:
                    notes.append(f"{r.name}让位给 " + "、".join(s.name_of(x) for x in others_eff))
                    continue
                groups.append(r.id)
                if r.id not in eff:
                    notes.append(f"“{txt[r.id][0]}”在中转位置，但名字里没有别的地区，仍归{r.name}")
            elif r.id in eff:
                groups.append(r.id)
            elif not others_eff:
                groups.append(r.id)
                notes.append(f"“{txt[r.id][0]}”在中转位置，但名字里没有别的地区，仍归{r.name}")
            else:
                notes.append(f"{r.name}的词在中转位置，按落地归 " + "、".join(s.name_of(x) for x in others_eff))
        if len(groups) > 1:
            notes.append("同时有 " + "、".join(s.name_of(g) for g in groups) + " 的词，说不清落地，两个组都进")
        if groups:
            return Verdict(groups, "text", txt, notes)

        # 3. 都没有
        notes.append("名字里没有认识的地区词" if not seen_flags
                     else "名字里的国旗不在落地位置（在箭头前面，或跟在“解锁”这类词后面），也没有认识的地区词")
        return Verdict([oid], "none", txt, notes)


# ---------------------------------------------------------------------------
# 报告：一批节点名各进了哪个组、为什么
# ---------------------------------------------------------------------------

def render_report(spec: Spec, names: List[str], show_all: bool = False) -> Tuple[List[str], Dict[str, int]]:
    """返回 (报告的各行, 统计)。只用到节点名称。统计的键：地区 id、其他地区 id、none（不进任何组），
    以及 unrecognized / ambiguous / relay / info / assigned / inconsistent。"""
    cl = Classifier(spec)
    rx = {k: re.compile(v) for k, v in compose(spec).items()}
    order = spec.ids + [spec.other.id]
    count = {k: 0 for k in order + [NONE]}
    buckets: Dict[str, List[str]] = {k: [] for k in ("unrecognized", "ambiguous", "relay", "info", "assigned",
                                                     "foreign", "inconsistent")}
    rows = []
    for n in names:
        v = cl.classify(n)
        by_rx = [k for k in order if rx[k].search(n)]
        if sorted(by_rx) != sorted(v.groups):
            buckets["inconsistent"].append(f"{n}：正则 {by_rx}，逐步判断 {v.groups}")
        for g in v.groups:
            count[g] += 1
        if not v.groups:
            count[NONE] += 1
        where = "、".join(spec.name_of(g) for g in v.groups) or "不进任何组"
        note = "；".join(v.notes)
        rows.append(f"{n} → {where}" + (f"（{note}）" if note else ""))
        line = f"{n} → {where}" + (f"（{note}）" if note else "")
        if v.basis == "assign":
            buckets["assigned"].append(f"{n} → {where}")
        elif v.basis == "info":
            buckets["info"].append(f"{n}（{note.split('，', 1)[-1]}）")
        elif v.basis == "none":
            buckets["unrecognized"].append(n)
        elif len(v.groups) > 1:
            buckets["ambiguous"].append(line)
        elif v.groups == [spec.other.id] and len(v.notes) < 2:
            buckets["foreign"].append(line)
        elif v.notes:
            buckets["relay"].append(line)           # 含“其他国家 + 地区词”的中转写法

    L = [f"节点 {len(names)} 个。各组数量：" + "、".join(f"{spec.name_of(k)} {count[k]}" for k in order)
         + f"、不进任何组 {count[NONE]}。", "名称只是初筛：这里判断的是“名字写的是哪里”，不证明节点实际从哪里出去。"]

    def section(title: str, items: List[str], hint: str = ""):
        if not items:
            return
        L.append("")
        L.append(f"【{title}】{len(items)} 个" + (f"——{hint}" if hint else ""))
        L.extend("  " + x for x in items)

    section("内部不一致（请把这几行发给维护者）", buckets["inconsistent"])
    section(f"没认出地区，放进“{spec.other.name}”", buckets["unrecognized"],
            "如果其实是六个地区之一，把名字里的写法补进 source/local.yaml 的 node_names.extra_words，或用 assign 直接指定")
    section("说不清落地，同时进了两个地区", buckets["ambiguous"], "可以在 local.yaml 的 node_names.assign 里指定")
    section("按中转 / 让位规则判断", buckets["relay"], "请看一眼归属对不对")
    section("当成信息节点，不进任何组", buckets["info"], "如果里面有真节点，请告诉维护者是哪个词误伤了")
    section("local.yaml 指定", buckets["assigned"])
    if show_all:
        section(f"落地在其他国家，放进“{spec.other.name}”", buckets["foreign"])
        L.append("")
        L.append("【全部节点】")
        L.extend("  " + r for r in rows)
    elif buckets["foreign"]:
        L.append("")
        L.append(f"【落地在其他国家，放进“{spec.other.name}”】{len(buckets['foreign'])} 个（加 --all 查看）")
    stats = dict(count)
    stats.update({k: len(v) for k, v in buckets.items()})
    return L, stats

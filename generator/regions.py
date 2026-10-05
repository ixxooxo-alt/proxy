"""节点名称分地区。

从 source/regions.yaml 的词表拼出各客户端通用的筛选正则（compose / compose_strict），并提供同一套规则的逐步判断实现
（Classifier）：检查工具用它解释“为什么进这个组”，测试用它和拼出来的正则逐个节点交叉核对。

规则（名称只是初筛，不证明实际出口）：
  0. 本地指定（local.yaml 的 node_names.assign）优先；提示行不进任何组。
  1. 有“有效”的国旗 → 按国旗：其他国家的旗 → 其他地区；让位地区的旗遇到别的地区旗时让位。
  2. 没有 → 看文字里“有效”的词：
       其他国家的国名 → 其他地区；只有其他国家的城市词时，若同时有六个地区之一的国名，按国名算（但算“说不清”）；
       地区的有效词 → 该地区；一个有效的词都没有、但提到了地区（文字或国旗）→ 仍归提到的地区，但只进它的手动组；
       让位地区遇到别的地区有效的“国名一级”的词时让位；别的地区只有城市一级的词时，让位地区自己也只有
       城市一级的词（或单个字的简称）就照样让，有国名一级的词就不让——两边都算，但算“说不清”。
  3. 都没有 → 其他地区。
“有效” = 不在落地以外的位置上。国旗和文字用同一套条件（2026-10-05 交付前自查之前，后两条只管文字）：
  - 不在“解锁”这类说明里（它后面到下一个竖线或右括号为止的词和国旗都不算）；
  - 后面没有箭头；
  - 前面不是 via / 经 这类词（via 要单独成词；中间可以隔一个空格、连字符或下划线：“via HK”“via-HK”“经_日本”）；
  - 后面不接着中转词（中间只隔连接符也算接着：“日本中转”“日本 中转”“日本-中转”“HK_Relay”“香港·中转”是一回事。
    连接符 = 空白、连字符、下划线、间隔号、句点、斜杠、破折号；竖线和括号另起一段，不算）；
  - 同一段里后面没有跟着“解锁”（“美国解锁”“纽约时报解锁”“美国-解锁”“🇺🇸解锁”）。
连写的一串国旗按整串算：“🇭🇰🇯🇵中转”两面都不算。
国旗不在落地位置时和文字一样算“提到了这个地区”：名字里没有别的落地，就进它的手动组（“🇯🇵中转 01”“01 | 解锁 🇺🇸”）。
词表里的词出现在另一个更长的词里时，按更长的那个算：单个字的“港”在“香港”“港日 / 港韩 / 港美”里不单独算一次
（写成带条件的片段，见 source/regions.yaml）。

每个地区有两条筛选（2026-10-04，审核 F04）：
  宽的（compose）       按上面的顺序算出来的全部节点。给“手动”组用。
  严的（compose_strict） 只收“有这个地区有效的国旗或有效的词，而且名字只指向这一个地区”的节点。
                        给“自动 / 故障转移 / 负载均衡”用。
说不清落地的节点（两个地区都像落地、国名和别国城市词同时出现、提到的地区词和国旗都不在落地位置……）只在宽的那条里。
最后一种是 2026-10-04 审核 r9 的 F01：以前“名字里只提到一个地区”就能进严的那条，哪怕那个词在解锁说明或中转位置里。

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
_ASCII_LETTER = re.compile(r"[A-Za-z]")
_FLAG_CODE = re.compile(r"^[A-Z]{2}$")
NONE = "none"                                   # node_names.assign 里表示“不进任何组”

# 提示行的“词 + 冒号”：这个词前面不能有数字和竖线（“香港 01 | 官网：abc.com”是带广告语的真节点）
_LABEL_PREFIX = "[^0-9０-９|｜丨]*"
_COLON = r"\s*[:：]"
# “同一段”：中间没有空白、竖线、下划线、连字符（“纽约时报解锁”里的“纽约”和“解锁”在同一段）
_TOKEN = r"[^\s|｜丨_-]*"
# “解锁”说明管到哪里：到它后面第一个竖线或右括号为止（“【解锁美国】日本 01”里日本仍是落地）；
# 如果先遇到的是左括号（“解锁：美国(Netflix)/日本(Abema)”），就一直管到名字结尾
_PIPES = "|｜丨"
_OPEN = r"(（\[【"
_CLOSE = r")）\]】"
_CLAUSE_REST = "[^" + _PIPES + _OPEN + _CLOSE + "]*[" + _PIPES + _CLOSE + "]"
# 地名和中转词之间可以隔着的字符：空白、连字符、下划线，以及同样只起连接作用的间隔号、句点、斜杠、破折号。
# “香港-中转-01”“HK_Relay_01”“香港·中转·01”和“香港 中转 01”是同一种写法
# （2026-10-05：以前只认空白，同一个名字换个连接符结果就不一样）。竖线和括号不算：它们另起一段说明，
# “香港 01 | 中转”“香港 01 [中转]”里的“中转”是单独的线路标记，地名仍在落地位置。
# 斜杠写成 \x2F：它在各客户端的配置行里有没有别的含义没有逐个核对过，转义之后三个引擎读到的都是同一个字符。
_JOIN = r"[\s_·・.\x2F—–-]*"
# 只容许隔一个字符的两处（via / 经 和它后面的地名或国旗之间；“解锁”和它前面那一段之间）只认最常见的三种。
# 前一处是定长的否定后顾，每多认一种写法，每条正则里十来处都要变长；后一处“同一段”本身已经能越过别的符号。
_GAP = r"[\s_-]"

REGION_KEYS = {"id", "name", "yields", "flags", "country", "words", "latin", "patterns"}
OTHER_KEYS = {"words", "latin", "patterns", "cities"}
RULES_KEYS = {"info", "transit_after", "transit_before", "unlock", "arrows", "neutral_flags"}
INFO_KEYS = {"always", "words", "colon_words", "latin"}
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
    """一个地区（或“其他国家”）的词表。words / latin / patterns 是全部的词；core_* 是其中“国名一级”的那部分：
    地区的 country（国名、代码、专线简称），其他国家的国名（城市之外的）。"""
    id: str
    name: str
    yields: bool = False
    flags: List[str] = field(default_factory=list)       # ISO 两位字母
    words: List[str] = field(default_factory=list)
    latin: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    core_words: List[str] = field(default_factory=list)
    core_latin: List[str] = field(default_factory=list)

    def vocab(self, tier: str) -> Tuple[List[str], List[str], List[str]]:
        """tier：all 全部；core 国名一级；rest 其余（地区的城市 / 运营商 / 机场，其他国家的城市）。"""
        if tier == "all":
            return self.words, self.latin, self.patterns
        if tier == "core":
            return self.core_words, self.core_latin, []
        cw, cl = set(self.core_words), {x.lower() for x in self.core_latin}
        return ([w for w in self.words if w not in cw], [w for w in self.latin if w.lower() not in cl], self.patterns)


@dataclass
class Spec:
    regions: List[Words]
    other: Words                                           # 其他国家的词表；id / name 是“其他地区”
    info_always: List[str]
    info_words: List[str]
    info_colon: List[str]
    info_latin: List[str]
    after: List[str]
    before: List[str]
    unlock: List[str]
    arrows: List[str]
    neutral_flags: List[str]
    assign: Dict[str, str] = field(default_factory=dict)   # 节点完整名称 → 地区 id / 其他地区 id / none

    @property
    def ids(self) -> List[str]:
        return [r.id for r in self.regions]

    @property
    def steady_ids(self) -> List[str]:
        """不让位的地区。"""
        return [r.id for r in self.regions if not r.yields]

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
    if unknown("regions.yaml rules.info", info, INFO_KEYS):
        info = {}

    def words_of(where: str, e: dict, rid: str, name: str, yields: bool, sub_key: str, sub_is_core: bool) -> Words:
        """sub_key：地区的 country（国名一级）或其他国家的 cities（城市）；它里面的词也并入全部词表。"""
        sub = e.get(sub_key) or {}
        if unknown(f"{where} {sub_key}", sub, {"words", "latin"}):
            sub = {}
        top_w = _str_list(f"{where} words", e.get("words"), errors)
        top_l = _str_list(f"{where} latin", e.get("latin"), errors)
        sub_w = _str_list(f"{where} {sub_key}.words", sub.get("words"), errors)
        sub_l = _str_list(f"{where} {sub_key}.latin", sub.get("latin"), errors)
        w = Words(id=rid, name=name, yields=yields,
                  flags=_str_list(f"{where} flags", e.get("flags"), errors),
                  words=sub_w + top_w if sub_is_core else top_w + sub_w,
                  latin=sub_l + top_l if sub_is_core else top_l + sub_l,
                  patterns=_str_list(f"{where} patterns", e.get("patterns"), errors),
                  core_words=sub_w if sub_is_core else top_w,
                  core_latin=sub_l if sub_is_core else top_l)
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
        r = words_of(f"regions.yaml 地区 {rid}", e, rid, name, bool(e.get("yields", False)), "country", True)
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
    other = words_of("regions.yaml other_countries", oc if isinstance(oc, dict) else {}, oid, oname, False, "cities", False)

    def rule_list(key: str, src: dict = rules, label: str = "") -> List[str]:
        return _str_list(f"regions.yaml rules.{label or key}", src.get(key) if isinstance(src, dict) else None, errors)

    spec = Spec(regions=regions, other=other,
                info_always=rule_list("always", info, "info.always"), info_words=rule_list("words", info, "info.words"),
                info_colon=rule_list("colon_words", info, "info.colon_words"), info_latin=rule_list("latin", info, "info.latin"),
                after=rule_list("transit_after"), before=rule_list("transit_before"), unlock=rule_list("unlock"),
                arrows=rule_list("arrows"), neutral_flags=rule_list("neutral_flags"))
    _check_words("regions.yaml rules.info", spec.info_words + spec.info_colon, spec.info_latin, [], errors)
    for w in spec.info_always:
        if w.isascii():
            errors.append(f"regions.yaml rules.info.always：{w!r} 是纯英文；固定写法只收面板里的中文句子")
    for c in spec.neutral_flags:
        if not _FLAG_CODE.match(c):
            errors.append(f"regions.yaml rules.neutral_flags：{c!r} 不是两位大写字母")
    for label, items in (("transit_after", spec.after), ("transit_before", spec.before), ("unlock", spec.unlock),
                         ("arrows", spec.arrows), ("info.always", spec.info_always)):
        for x in items:
            if any(c in x for c in ("\n", "\r", "\t")) or x != x.strip():
                errors.append(f"regions.yaml rules.{label}：{x!r} 含空白字符")

    # 本地补充（只进私密产物）。补给地区的词算城市一级；补给“其他国家”的词算国名一级（它压得过地区的词）
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
                more_w = _str_list(f"{where} words", add.get("words"), errors)
                more_l = _str_list(f"{where} latin", add.get("latin"), errors)
                by_id[rid].words += more_w
                by_id[rid].latin += more_l
                if rid == oid:
                    by_id[rid].core_words += more_w
                    by_id[rid].core_latin += more_l
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
        loose, strict = compose_all(spec)
        for rx in list(loose.values()) + list(strict.values()):
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


def _pattern_first(p: str) -> Optional[str]:
    """patterns 里的正则片段：能看出第一个字符的范围时，返回这个范围（字符类内部的写法）；看不出来返回 None。"""
    rest = p[_LEADING_LOOKBEHINDS.match(p).end():]
    if rest.startswith("[") and not rest.startswith("[^"):
        end = rest.find("]", 2)
        if end != -1 and "\\" not in rest[:end]:
            return rest[1:end]
    elif rest and (rest[0].isalnum() or ord(rest[0]) > 0x7F) and not (len(rest) > 1 and rest[1] in "?*{"):
        return _cls(rest[0].lower())
    return None


def _alt(parts: List[str]) -> Optional[str]:
    parts = [p for p in parts if p]
    return "(?:" + "|".join(parts) + ")" if parts else None


def _pos(x: Optional[str]) -> str:
    """名字里某处出现 x。x 为空时条件不可能成立。"""
    return "(?!)" if x is None else "(?!(?!.*" + x + "))"


def _neg(x: Optional[str]) -> str:
    """名字里任何位置都不出现 x。x 为空时条件恒成立。"""
    return "" if x is None else "(?!.*" + x + ")"


def _marker_parts(spec: Spec) -> List[str]:
    """“解锁”这类词的正则片段。英文词要求前面不紧挨英文字母；其余的压成前缀树（解[锁鎖]）。"""
    plain = sorted({m for m in spec.unlock if not _ASCII_LETTERS.match(m)})
    return ([_trie(plain, False)] if plain else []) + [r"(?<![A-Za-z])" + lit(m) for m in spec.unlock if _ASCII_LETTERS.match(m)]


def _choice(items: List[str]) -> str:
    """几个字面量任选其一：都是单个字符时写成字符类，否则写成交替。items 是已经转义好的片段。"""
    if all(len(x) == 1 for x in items):
        return "[" + "".join(items) + "]"
    return "(?:" + "|".join(items) + ")"


class _Composer:
    def __init__(self, spec: Spec):
        self.s = spec
        self.by_id = {r.id: r for r in spec.regions}
        self.by_id[spec.other.id] = spec.other
        self.marker = _alt(_marker_parts(spec))
        # “有效”的词和国旗不能落在“解锁”说明里：从名字开头往后走，遇到“解锁”时只能把整段说明
        # （到下一个竖线或右括号）一起跳过；跳不过去（后面没有竖线和右括号，或先遇到左括号）就到此为止。
        # 两个分支互不重叠：这个位置不是“解锁”→ 走过一个字符；是“解锁”→ 连同整段说明一起跳过。
        # 每个位置只有一种走法——如果两个分支能匹配同一个字符，匹配失败时的回溯次数会按名字长度成倍增长
        # （写这段时真的出过一次，tests/test_regions.py 里有专门的检查）
        self.pre = ("(?:(?!" + self.marker + ").|" + self.marker + _CLAUSE_REST + ")*") if self.marker else ".*"
        # 箭头：单个字符的并成一个字符类，比逐个尝试快
        single = [a for a in spec.arrows if len(a) == 1]
        multi = [lit(a) for a in spec.arrows if len(a) > 1]
        arrows = (["[" + "".join(_cls(a) for a in single) + "]"] if single else []) + multi
        self.arrow = "(?!.*" + _alt(arrows) + ")" if arrows else ""
        transit = _JOIN + _trie(sorted(set(spec.after)), False) if spec.after else None
        self.after = "(?!" + transit + ")" if transit else ""
        # 国旗按“一串”算：这一串后面接着中转词时整串都不算（“🇯🇵中转 01”“🇭🇰🇯🇵 中转 01”）
        self.run_after = "(?!" + _RI + "*" + transit + ")" if transit else ""
        if self.marker:                         # 同一段里后面跟着“解锁”：纽约时报解锁、美国 解锁、美国-解锁
            same = "(?!" + _TOKEN + _GAP + "*" + self.marker + ")"
            self.after += same
            self.run_after += same              # 国旗也是这一段里的字符：🇺🇸解锁、🇺🇸 解锁
        # 否定后顾要定长：同样长度的词并成一组（Python 不支持变长后顾）
        by_len: Dict[int, List[str]] = {}
        latin_before: List[str] = []
        for b in spec.before:
            if _ASCII_LETTERS.match(b):
                latin_before.append(lit(b))
            else:
                by_len.setdefault(len(b), []).append(lit(b))
        # 这类词和后面的地名之间可以隔一个空格、连字符或下划线（“via HK”“via-HK”“经_日本”）
        self.before = "".join(f"(?<!{_choice(v)})(?<!{_choice(v)}{_GAP})" for _, v in sorted(by_len.items()))
        # 英文词（via）要单独成词：前面是非英文字母，或者它就在名字开头。Latvia、Bolivia 里的 via 不算
        for b in latin_before:
            self.before += "".join(f"(?<!{head}{b})(?<!{head}{b}{_GAP})" for head in ("[^A-Za-z]", "^"))

    # --- 两种“存在 / 不存在”：任何位置（_pos / _neg），或只看不在“解锁”说明里的位置（pos_e / neg_e）---
    def pos_e(self, x: Optional[str]) -> str:
        return "(?!)" if x is None else "(?!(?!" + self.pre + x + "))"

    def neg_e(self, *xs: Optional[str]) -> str:
        """这些片段一个都不出现（几个片段共用一次从头往后的扫描，正则短一些）。"""
        xs = [x for x in xs if x is not None]
        if not xs:
            return ""
        return "(?!" + self.pre + (xs[0] if len(xs) == 1 else "(?:" + "|".join(xs) + ")") + ")"

    def _vocab(self, ids: List[str], tier: str, before: str = "") -> Optional[str]:
        """这些地区的词：中文等原样词、英文词、正则片段三类并成一个交替，前面共用一个“首字符”快速判断。
        三类共用一份快速判断和一份 before（前面不能是 via、经 这类词），比各写一份短——每条正则里这样的片段有七八处。

        先后顺序只为了快，不改变结果。引擎对交替是一个分支一个分支试的，所以：
          - 最前面是“下一个字符在这些词的首字符里”，绝大多数位置一步排除；
          - before 是好几个否定后顾，比较贵：英文单词中间的字母（前一个字符也是字母）不可能是英文词的开头，先用一步排除掉；
          - 原样词那一支的前缀树在英文字母上要把每个首字符都试一遍，前面加一个“不是英文字母”挡掉。
        后两条只在“原样词和正则片段都不以英文字母开头”时才成立（local.yaml 可以补“NTT东京”这样的词），否则不加。"""
        words, latin, pats = [], [], []
        for i in ids:
            w, l, p = self.by_id[i].vocab(tier)
            words += w
            latin += l
            pats += p
        branches, first = [], set()
        pat_first = [_pattern_first(p) for p in pats]
        # 原样词、正则片段会不会以英文字母开头（不分大小写，所以大小写都算）
        ascii_start = (any(_ASCII_LETTER.match(w) for w in words)
                       or any(f is None or _ASCII_LETTER.search(f) for f in pat_first))
        cheap = bool(latin) and not ascii_start
        if words:
            words = sorted(set(words))
            branches.append((r"(?![A-Za-z])" if cheap else "") + _trie(words, False))
            first |= {_cls(_units(w, False)[0]) for w in words}
        if latin:
            latin = sorted(set(latin))
            branches.append(r"(?<![A-Za-z])" + _trie(latin, True) + r"(?![A-Za-z])")
            first |= {_cls(_units(w, True)[0]) for w in latin}
        for p, f in zip(pats, pat_first):
            branches.append(f"(?:{p})")
            first = None if (f is None or first is None) else first | {f}
        if not branches:
            return None
        guard = "(?!(?![" + "".join(sorted(first)) + "]))" if first else ""
        if before and cheap:
            guard += r"(?:(?![A-Za-z])|(?<![A-Za-z]))"
        return guard + before + (branches[0] if len(branches) == 1 else "(?:" + "|".join(branches) + ")")

    def txt(self, ids: List[str], tier: str = "all") -> Optional[str]:
        """名字里出现这些地区的任意一个词（不管在什么位置）。"""
        return self._vocab(ids, tier)

    def eff(self, ids: List[str], tier: str = "all") -> Optional[str]:
        """这些地区的“有效”词：前面不是 via / 经 这类词，后面不接着中转词（隔着空格、连字符这类连接符也算接着）、
        同一段里后面没有“解锁”，再往后也没有箭头。“不在解锁之后”由调用处的 pos_e / neg_e 保证。"""
        t = self._vocab(ids, tier, self.before)
        return None if t is None else t + self.after + self.arrow

    def _align(self) -> str:
        """从一串国旗的开头成对跳过，只在对齐的位置上认国旗：🇨🇳🇺🇸 连写时不能把中间的 🇳🇺 当成一面旗。
        这串国旗前面是 via / 经 这类词、后面接着中转词或同一段里跟着“解锁”时，整串都不算——和文字用的是同一套条件
        （2026-10-05 交付前自查：以前国旗不看后面，“🇯🇵中转 01”“IEPL 01 🇺🇸解锁”会进自动类的组，换成文字写就不会）。"""
        return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})" + self.run_after + f"(?:{_RI}{_RI})*"

    def eflag(self, ids: List[str]) -> Optional[str]:
        """属于这些地区的“有效”国旗（条件见 _align；另外它后面不能有箭头）。"""
        flags = sorted({flag(c) for i in ids for c in self.by_id[i].flags})
        if not flags:
            return None
        return self._align() + _guarded(flags, latin=False) + self.arrow

    def aflag(self, ids: List[str]) -> Optional[str]:
        """名字里出现这些地区的国旗（同样按成对对齐来认），不管它在什么位置、算不算有效。"""
        flags = sorted({flag(c) for i in ids for c in self.by_id[i].flags})
        if not flags:
            return None
        return f"(?!(?!{_RI}))(?<!{_RI})(?:{_RI}{_RI})*" + _guarded(flags, latin=False)

    def eflag_other(self) -> str:
        """其他国家的有效国旗：不属于任何地区、也不在 neutral_flags 里的任意一面旗。"""
        known = sorted({flag(c) for r in self.s.regions for c in r.flags} | {flag(c) for c in self.s.neutral_flags})
        skip = "(?!" + _trie(known, latin=False) + ")" if known else ""
        return self._align() + skip + _RI + _RI + self.arrow

    def any_flag(self) -> str:
        """名字里任何一面算数的国旗（neutral_flags 之外的），不管它在什么位置。"""
        neutral = sorted(flag(c) for c in self.s.neutral_flags)
        skip = "(?!" + _trie(neutral, latin=False) + ")" if neutral else ""
        return f"(?!(?!{_RI}))(?<!{_RI})(?:{_RI}{_RI})*" + skip + _RI + _RI

    # --- 提示行 ---
    def info_common(self) -> str:
        """每条正则开头都有的排除：面板的固定写法（任何位置）；“词 + 冒号”且这个词前面没有数字和竖线。"""
        s = self.s
        out = _neg(_guarded(s.info_always, latin=False)) if s.info_always else ""
        labels = []
        if s.info_words or s.info_colon:
            labels.append(_guarded(s.info_words + s.info_colon, latin=False))
        if s.info_latin:
            labels.append(_guard(s.info_latin, True) + r"(?<![A-Za-z])" + _trie(sorted(set(s.info_latin)), True) + "[A-Za-z]*")
        if labels:
            out += "(?!" + _LABEL_PREFIX + _alt(labels) + _COLON + ")"
        return out

    def weak(self) -> Optional[str]:
        """提示行常用的词（colon_words 要带冒号）。只有名字里没有任何地区的词和国旗时才据此判为提示行。"""
        s = self.s
        parts = []
        if s.info_words:
            parts.append(_guarded(s.info_words, latin=False))
        if s.info_colon:
            parts.append(_guarded(s.info_colon, latin=False) + _COLON)
        if s.info_latin:
            parts.append(r"(?<![A-Za-z])" + _guarded(s.info_latin, latin=True))
        return _alt(parts)

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

    def compose(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        s = self.s
        ids, steady, oid = s.ids, s.steady_ids, s.other.id
        pos, neg, pos_e, neg_e = _pos, _neg, self.pos_e, self.neg_e
        info = self.info_common()
        no_other_flag = neg_e(self.eflag_other())
        region_flag = self.eflag(ids)
        no_region_flag = neg_e(region_flag)
        other_name = self.eff([oid], "core")            # 其他国家的国名
        other_city = self.eff([oid], "rest")            # 其他国家的城市
        region_name = self.eff(steady, "core")          # 不让位的地区的国名
        # 文字上“落地在其他国家”：有其他国家的国名；或只有城市词、又没有六个地区的国名可以压过它
        other_text = "(?:" + pos_e(other_name) + "|" + pos_e(other_city) + neg_e(region_name) + ")"
        # 按文字判断的前提：没有地区的有效国旗，文字上也不是落地在其他国家。
        # 宽：国名压得过别国的城市词。严：名字里只要有其他国家的有效词就不收
        by_text_loose = neg_e(region_flag, other_name) + "(?:" + neg_e(other_city) + "|" + pos_e(region_name) + ")"
        by_text_strict = neg_e(region_flag, self.eff([oid]))

        # 各条件的先后只影响速度，不影响结果（全是在名字开头做的判断）。把最容易失败的放最前面：
        # 一个节点要拿去和十几条正则各比一次，其中大多数和它无关——“名字里根本没有这个地区的国旗和词”一步就能排除，
        # 不用先把其他国家的词表扫一遍。提示行、其他国家国旗这两项通用的排除放在最后。
        loose: Dict[str, str] = {}
        strict: Dict[str, str] = {}
        tail = no_other_flag + info
        yielders = [r.id for r in s.regions if r.yields]
        for r in s.regions:
            others = [i for i in ids if i != r.id]
            rivals = [i for i in steady if i != r.id]            # 会和它抢的：别的不让位的地区
            mine = pos(self.txt([r.id]))                         # 文字里提到了它（任何位置）
            # 提到了它：文字或国旗，任何位置。国旗不在落地位置（“🇯🇵中转 01”“01 | 解锁 🇺🇸”）时和文字一样对待：
            # 谁都没有有效的词和国旗，就进提到的那个地区的手动组，而不是掉进“其他地区”
            seen = pos(_alt([self.txt([r.id]), self.aflag([r.id])]))
            raw = pos(_alt([lit(flag(c)) for c in r.flags])) if r.flags else "(?!)"
            only = pos_e(self.eff([r.id])) + neg_e(self.eff(rivals))     # 它有有效的词，对手都没有
            if r.yields:
                flag_l = flag_s = raw + pos_e(self.eflag([r.id])) + neg_e(self.eflag(rivals))
                # 让位：对手没有有效的词时提到了它就算；对手有有效的国名一级的词 → 让；
                # 对手只有城市一级的词（“香港 01 纽约时报”）→ 它自己有国名一级的词的话不让，两边都进手动组
                text_l = (seen + by_text_loose + "(?:" + neg_e(self.eff(rivals)) + "|"
                          + pos_e(self.eff([r.id], "core")) + neg_e(self.eff(rivals, "core")) + ")")
            else:
                flag_l = raw + pos_e(self.eflag([r.id]))
                flag_s = flag_l + neg_e(self.eflag(rivals))
                # 它有有效的词；或者谁都没有有效的词（这时提到了它就算）
                text_l = seen + by_text_loose + "(?:" + pos_e(self.eff([r.id])) + "|" + neg_e(self.eff(others)) + ")"
                # 严：让位地区有国名一级的有效词时，它也要有国名一级的词才算“只指向它”
                if yielders:
                    only += "(?:" + neg_e(self.eff(yielders, "core")) + "|" + pos_e(self.eff([r.id], "core")) + ")"
            # 严：它是唯一有有效词的地区（让位地区不算对手）。名字里只提到它一个地区、但那个词不在落地位置
            # （“日本中转 01”“Premium 01 | 解锁美国”）的不收：宽的那条仍把它放进这个地区的手动组，自动类的组不拿
            # “解锁说明 / 中转位置里的地名”当落地依据（2026-10-04 审核 r9 的 F01；以前这里多一个“或者名字里只提到它一个地区”）。
            # mine 被 only 蕴含，留着只为让无关的名字尽早失败。
            text_s = mine + by_text_strict + only
            loose[r.id] = self.wrap(r.id, "(?:" + flag_l + "|" + text_l + ")" + tail)
            strict[r.id] = self.wrap(r.id, "(?:" + flag_s + "|" + text_s + ")" + tail)

        # 其他地区：其他国家的国旗；或没有地区国旗时，文字上落地在其他国家；或六个地区的词和国旗一个都没有
        # （这时如果名字里有提示行常用的词、又完全没有别的地区字样，就是提示行，不收）
        weak = self.weak()
        nothing = neg(_alt([self.txt(ids), self.aflag(ids)]))
        if weak is not None:
            nothing += "(?:" + pos(self.txt([oid])) + "|" + pos(self.any_flag()) + "|" + neg(weak) + ")"
        other = "(?:" + pos_e(self.eflag_other()) + "|" + no_region_flag + "(?:" + other_text + "|" + nothing + "))"
        loose[oid] = self.wrap(oid, info + other)
        return loose, strict


def compose_all(spec: Spec) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(宽的 {地区 id（含其他地区）: 正则}, 严的 {地区 id: 正则})。"""
    return _Composer(spec).compose()


def compose(spec: Spec) -> Dict[str, str]:
    """宽的那套：{地区 id: 筛选正则}，含“其他地区”。每个不是提示行的节点至少匹配其中一条（被指定为 none 的除外）。"""
    return compose_all(spec)[0]


def compose_strict(spec: Spec) -> Dict[str, str]:
    """严的那套：{地区 id: 筛选正则}，只有六个地区。每个节点最多匹配其中一条。"""
    return compose_all(spec)[1]


# ---------------------------------------------------------------------------
# 同一套规则的逐步判断（不经过上面拼出来的正则）
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    groups: List[str]                 # 宽：地区 id（可能不止一个）、其他地区 id，或空（提示行 / 指定不进组）
    auto: List[str]                   # 严：进哪个地区的自动 / 故障转移 / 负载均衡（最多一个；其他地区没有这些模式）
    basis: str                        # assign | info | flag | text | none
    hits: Dict[str, List[str]]        # 地区 id / 其他地区 id → 名字里找到的词或国旗
    notes: List[str]                  # 给人看的说明
    weak: Optional[str] = None        # 名字里有提示行常用的词，但仍按节点处理时，这个词是什么


def _is_ri(ch: str) -> bool:
    return RI_FIRST <= ord(ch) <= RI_LAST


class Classifier:
    def __init__(self, spec: Spec):
        self.s = spec
        self._all = spec.regions + [spec.other]
        self._flag_owner = {flag(c): w.id for w in spec.regions for c in w.flags}
        self._neutral = {flag(c) for c in spec.neutral_flags}
        # 每个词记下它是不是“国名一级”
        self._rx = {}
        for w in self._all:
            core_w, core_l = set(w.core_words), {x.lower() for x in w.core_latin}
            self._rx[w.id] = ([(re.compile(re.escape(x), re.I), x in core_w) for x in w.words]
                              + [(self._latin_rx(x), x.lower() in core_l) for x in w.latin]
                              + [(re.compile(p, re.I), False) for p in w.patterns])
        marker = "|".join((r"(?<![A-Za-z])" if _ASCII_LETTERS.match(m) else "") + re.escape(m) for m in spec.unlock)
        self._marker = re.compile(marker, re.I) if marker else None
        self._clause = re.compile("(?:" + marker + ")" + _CLAUSE_REST, re.I) if marker else None
        self._same_token = re.compile(_TOKEN + _GAP + "*(?:" + marker + ")", re.I) if marker else None
        self._after = re.compile(_JOIN + "(?:" + "|".join(re.escape(a) for a in spec.after) + ")", re.I) if spec.after else None
        self._before = (re.compile("(?:" + "|".join((r"(?<![A-Za-z])" if _ASCII_LETTERS.match(b) else "") + re.escape(b)
                                                    for b in spec.before) + ")" + _GAP + "?$", re.I)
                        if spec.before else None)
        self._always = [re.compile(re.escape(x), re.I) for x in spec.info_always]
        labels = [re.escape(x) for x in spec.info_words + spec.info_colon]
        labels += [r"(?<![A-Za-z])" + self._latin_body(x) + "[A-Za-z]*" for x in spec.info_latin]
        self._label = re.compile(_LABEL_PREFIX + "(" + "|".join(labels) + ")" + _COLON, re.I) if labels else None
        self._weak = ([re.compile(re.escape(x), re.I) for x in spec.info_words]
                      + [re.compile(re.escape(x) + _COLON, re.I) for x in spec.info_colon]
                      + [re.compile(r"(?<![A-Za-z])" + self._latin_body(x), re.I) for x in spec.info_latin])
        self._assign = [(re.compile(re.escape(k), re.I), v) for k, v in spec.assign.items()]

    @staticmethod
    def _latin_body(word: str) -> str:
        return r"[\s_-]?".join(re.escape(p) for p in word.split(" "))

    def _latin_rx(self, word: str):
        return re.compile(r"(?<![A-Za-z])" + self._latin_body(word) + r"(?![A-Za-z])", re.I)

    # --- 找词 ---
    def _spans(self, w: Words, name: str) -> List[Tuple[int, int, bool]]:
        """[(起, 止, 是不是国名一级)]，含互相重叠的出现。"""
        spans = set()
        for rx, core in self._rx[w.id]:
            pos = 0
            while True:
                m = rx.search(name, pos)
                if not m:
                    break
                spans.add((m.start(), m.end(), core))
                pos = m.start() + 1
        return sorted(spans)

    def _has_arrow_after(self, name: str, end: int) -> bool:
        return any(a in name[end:] for a in self.s.arrows)

    def _open_positions(self, name: str) -> Optional[set]:
        """不在“解锁”说明里的位置。从头往后走：遇到“解锁”时，能把整段说明（到下一个竖线或右括号）跳过就跳过，
        跳不过去就到此为止——后面的词和国旗都不算落地。没有配置“解锁”这类词时返回 None（所有位置都算）。"""
        if self._marker is None:
            return None
        ok, i, n = set(), 0, len(name)
        while True:
            ok.add(i)
            if i >= n:
                break
            if self._marker.match(name, i):
                m = self._clause.match(name, i)
                if not m:
                    break
                i = m.end()
            else:
                i += 1
        return ok

    def _effective(self, name: str, start: int, end: int, clause: Optional[set]) -> bool:
        if clause is not None and start not in clause:
            return False
        if self._before is not None and self._before.search(name[:start]):
            return False
        if self._after is not None and self._after.match(name, end):
            return False
        if self._same_token is not None and self._same_token.match(name, end):
            return False
        return not self._has_arrow_after(name, end)

    def _flags(self, name: str, clause: Optional[set]) -> List[Tuple[str, bool]]:
        """按对齐的两两一组切出国旗，返回 [(国旗, 是否有效)]。
        有效的条件和文字一样：不在“解锁”说明里，后面没有箭头；所在的一串国旗前面不是 via / 经 这类词，
        后面不接着中转词，同一段里后面也没有“解锁”（这三条按整串算）。"""
        out, i, n = [], 0, len(name)
        while i < n:
            if _is_ri(name[i]):
                j = i
                while j < n and _is_ri(name[j]):
                    j += 1
                dead = ((clause is not None and i not in clause)
                        or (self._before is not None and bool(self._before.search(name[:i])))
                        or (self._after is not None and bool(self._after.match(name, j)))
                        or (self._same_token is not None and bool(self._same_token.match(name, i))))
                for k in range(i, j - 1, 2):
                    out.append((name[k:k + 2], not dead and not self._has_arrow_after(name, k + 2)))
                i = j
            else:
                i += 1
        return out

    def weak_word(self, name: str) -> Optional[str]:
        for rx in self._weak:
            m = rx.search(name)
            if m:
                return m.group(0)
        return None

    def has_region_sign(self, name: str) -> bool:
        """名字里有没有任何地区的词或算数的国旗（不管在什么位置）。"""
        if any(f not in self._neutral for f, _ in self._flags(name, None)):
            return True
        return any(self._spans(w, name) for w in self._all)

    def info_reason(self, name: str) -> Optional[str]:
        """是提示行的话返回原因，否则返回 None。"""
        for rx in self._always:
            m = rx.search(name)
            if m:
                return f"含面板的固定写法“{m.group(0)}”"
        if self._label is not None:
            m = self._label.match(name)
            if m:
                return f"“{m.group(1)}”后面紧跟冒号，前面没有数字和竖线"
        w = self.weak_word(name)
        if w and not self.has_region_sign(name):
            return f"含“{w}”，名字里没有任何地区字样"
        return None

    def is_info(self, name: str) -> Optional[str]:
        return self.info_reason(name)

    def classify(self, name: str) -> Verdict:
        s = self.s
        oid = s.other.id
        for rx, rid in self._assign:
            if rx.fullmatch(name):
                g = [] if rid == NONE else [rid]
                return Verdict(g, [x for x in g if x != oid], "assign", {}, ["local.yaml 指定"])
        why = self.info_reason(name)
        if why:
            return Verdict([], [], "info", {}, ["提示行：" + why])
        weak = self.weak_word(name)
        clause = self._open_positions(name)

        # 先把名字里的国旗和词都找出来
        eff_flags: Dict[str, List[str]] = {}
        seen_flags: Dict[str, List[str]] = {}
        for f, effective in self._flags(name, clause):
            if f in self._neutral:
                continue
            owner = self._flag_owner.get(f, oid)        # 不属于任何地区的国旗都算其他国家
            seen_flags.setdefault(owner, []).append(f)
            if effective:
                eff_flags.setdefault(owner, []).append(f)
        txt: Dict[str, List[str]] = {}
        eff: Dict[str, List[str]] = {}
        eff_core: Dict[str, List[str]] = {}
        eff_rest: Dict[str, List[str]] = {}
        for w_ in self._all:
            for a, b, core in self._spans(w_, name):
                txt.setdefault(w_.id, []).append(name[a:b])
                if self._effective(name, a, b, clause):
                    eff.setdefault(w_.id, []).append(name[a:b])
                    (eff_core if core else eff_rest).setdefault(w_.id, []).append(name[a:b])
        region_words = "、".join(f"{r.name}（{txt[r.id][0]}）" for r in s.regions if r.id in txt)

        def done(groups, auto, basis, hits, notes):
            return Verdict(groups, auto, basis, hits, notes, weak)

        # 1. 国旗
        if oid in eff_flags:
            notes = [f"带其他国家的国旗 {''.join(eff_flags[oid])}"]
            if region_words:
                notes.append(f"名字里的 {region_words} 不算落地")
            return done([oid], [], "flag", {**txt, **eff_flags}, notes)
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
                notes.append("同时有 " + "、".join(s.name_of(g) for g in groups) + " 的国旗，说不清落地：只进这几个地区的手动组")
            ignored = "、".join(f"{r.name}（{txt[r.id][0]}）" for r in s.regions if r.id in txt and r.id not in groups)
            if ignored:
                notes.append(f"按国旗算；名字里的 {ignored} 不算落地")
            return done(groups, groups if len(groups) == 1 else [], "flag", {**txt, **eff_flags}, notes)

        # 2. 文字
        steady = [r for r in s.regions if not r.yields]
        other_name, other_city = oid in eff_core, oid in eff_rest
        region_name = [r for r in steady if r.id in eff_core]
        if other_name or (other_city and not region_name):
            notes = [f"带其他国家的词“{eff[oid][0]}”"]
            if region_words:
                notes.append(f"名字里的 {region_words} 不算落地")
            return done([oid], [], "text", txt, notes)
        clash = other_city and bool(region_name)
        winners = [r for r in steady if r.id in eff]
        yielder = next((r for r in s.regions if r.yields), None)
        groups, notes, unplaced = [], [], False
        if winners:
            groups = [r.id for r in winners]
            if yielder is not None and yielder.id in eff_core and not any(r.id in eff_core for r in winners):
                # 让位只对国名一级的词无条件生效；这里让位地区有国名一级的词，别的地区只有城市一级的词，说不清哪个是落地
                groups = [r.id for r in s.regions if r.id in groups or r.id == yielder.id]
                notes.append(f"{yielder.name}不让位：有“{eff_core[yielder.id][0]}”，而"
                             + "、".join(f"{r.name}只有城市一级的词“{eff[r.id][0]}”" for r in winners))
            elif yielder is not None and yielder.id in txt:
                notes.append(f"{yielder.name}让位给 " + "、".join(r.name for r in winners))
            passed = [r for r in steady if r.id in txt and r.id not in eff]
            if passed:
                notes.append("、".join(r.name for r in passed) + "的词不在落地位置（中转、解锁说明等），按落地归 "
                             + "、".join(r.name for r in winners))
        elif yielder is not None and yielder.id in eff:
            groups = [yielder.id]
            passed = [r for r in steady if r.id in txt]
            if passed:
                notes.append("、".join(r.name for r in passed) + f"的词不在落地位置（中转、解锁说明等），按落地归 {yielder.name}")
        else:
            # 谁都没有落在落地位置的词和国旗：提到了哪个地区（文字或国旗）就进哪个地区的手动组（方便手选），
            # 但不进任何自动类的组
            groups = [r.id for r in s.regions if r.id in txt or r.id in seen_flags]
            unplaced = bool(groups)
            for g in groups:
                what = f"“{txt[g][0]}”" if g in txt else f"国旗 {seen_flags[g][0]} "
                notes.append(f"{what}不在落地位置（中转、解锁说明等），名字里也没有别的落地，说不清落地：只进{s.name_of(g)}的手动组")
        auto = list(groups) if len(groups) == 1 and not clash and not unplaced else []
        if len(groups) > 1:
            what = "词" if all(g in txt for g in groups) else "词或国旗"
            notes.append("同时有 " + "、".join(s.name_of(g) for g in groups) + f" 的{what}，说不清落地：只进这几个地区的手动组")
        elif groups and clash:
            notes.append(f"有国名“{eff_core[groups[0]][0]}”，也有其他国家的城市词“{eff_rest[oid][0]}”，"
                         f"说不清落地：只进{s.name_of(groups[0])}的手动组")
        if groups:
            by_flag_only = unplaced and not any(g in txt for g in groups)
            return done(groups, auto, "flag" if by_flag_only else "text",
                        {**{k: v for k, v in seen_flags.items() if k in groups}, **txt}, notes)

        # 3. 都没有（到这里还有国旗的话，只能是其他国家的、又不在落地位置的国旗）
        notes.append("名字里没有认识的地区词" if not seen_flags
                     else "名字里只有其他国家的国旗，而且不在落地位置（在箭头前面、“解锁”说明里、中转词前面，或跟在 via 这类词后面），"
                          "也没有认识的地区词")
        return done([oid], [], "none", txt, notes)


# ---------------------------------------------------------------------------
# 报告：一批节点名各进了哪个组、为什么
# ---------------------------------------------------------------------------

def render_report(spec: Spec, names: List[str], show_all: bool = False) -> Tuple[List[str], Dict[str, int]]:
    """返回 (报告的各行, 统计)。只用到节点名称。统计的键：地区 id、其他地区 id、none（不进任何组），
    以及 unrecognized / ambiguous / relay / info / kept / assigned / inconsistent。"""
    cl = Classifier(spec)
    loose, strict = compose_all(spec)
    rx = {k: re.compile(v) for k, v in loose.items()}
    rx_strict = {k: re.compile(v) for k, v in strict.items()}
    order = spec.ids + [spec.other.id]
    count = {k: 0 for k in order + [NONE]}
    auto_count = {k: 0 for k in spec.ids}
    buckets: Dict[str, List[str]] = {k: [] for k in ("unrecognized", "ambiguous", "relay", "info", "kept", "assigned",
                                                     "foreign", "inconsistent")}
    rows = []
    for n in names:
        v = cl.classify(n)
        by_rx = [k for k in order if rx[k].search(n)]
        by_strict = [k for k in spec.ids if rx_strict[k].search(n)]
        if sorted(by_rx) != sorted(v.groups) or sorted(by_strict) != sorted(v.auto):
            buckets["inconsistent"].append(f"{n}：正则 {by_rx} / {by_strict}，逐步判断 {v.groups} / {v.auto}")
        for g in v.groups:
            count[g] += 1
        for g in v.auto:
            auto_count[g] += 1
        if not v.groups:
            count[NONE] += 1
        manual_only = bool(v.groups) and v.groups != [spec.other.id] and not v.auto
        where = "、".join(spec.name_of(g) for g in v.groups) or "不进任何组"
        if manual_only:
            where += "（只进手动组）"
        note = "；".join(v.notes)
        line = f"{n} → {where}" + (f"（{note}）" if note else "")
        rows.append(line)
        if v.basis == "assign":
            buckets["assigned"].append(f"{n} → {where}")
        elif v.basis == "info":
            buckets["info"].append(f"{n}（{note.split('：', 1)[-1]}）")
        elif v.basis == "none":
            buckets["unrecognized"].append(n)
        elif manual_only:
            buckets["ambiguous"].append(line)
        elif v.groups == [spec.other.id] and len(v.notes) < 2:
            buckets["foreign"].append(line)
        elif v.notes:
            buckets["relay"].append(line)           # 含“其他国家 + 地区词”的中转写法
        if v.weak and v.basis not in ("assign", "info"):
            buckets["kept"].append(f"{n} → {where}（含“{v.weak}”）")

    L = [f"节点 {len(names)} 个。各组数量（括号里是其中进自动 / 故障转移 / 负载均衡的）："
         + "、".join(f"{spec.name_of(k)} {count[k]}" + (f"（{auto_count[k]}）" if k in auto_count else "") for k in order)
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
    section("说不清落地，只进手动组", buckets["ambiguous"],
            "不会被自动 / 故障转移 / 负载均衡用到；确定落地的话，在 local.yaml 的 node_names.assign 里指定")
    section("按中转 / 让位规则判断", buckets["relay"], "请看一眼归属对不对")
    section("当成提示行，不进任何组", buckets["info"], "如果里面有真节点，请告诉维护者是哪种写法误伤了")
    section("名字里有提示行常用的词，但带地区字样，按节点处理", buckets["kept"],
            "如果其实是机场的提示行，用 assign 把它指定为 none")
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
    stats["auto"] = dict(auto_count)
    return L, stats

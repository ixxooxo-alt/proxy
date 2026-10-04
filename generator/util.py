"""通用工具：域名 / CIDR 校验、规则覆盖关系、正则组合、稳定输出。"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

# 共享云 / 公共 CDN / 第三方托管根域：禁止作为后缀整体收录到任何业务组
BANNED_SHARED_SUFFIXES = {
    "amazonaws.com", "cloudfront.net", "akamaized.net", "akamaihd.net", "akamai.net",
    "edgekey.net", "edgesuite.net", "fastly.net", "fastlylb.net", "cloudflare.net",
    "azureedge.net", "azurewebsites.net", "windows.net", "trafficmanager.net",
    "appspot.com", "firebaseapp.com", "web.app", "herokuapp.com", "vercel.app",
    "netlify.app", "github.io", "workers.dev", "pages.dev", "cdn77.org", "b-cdn.net",
    "jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
}
# 这些 Google 共享根域只允许归 “Google” 通用组，不允许归任何 AI 组
GOOGLE_SHARED_ROOTS = {"googleapis.com", "googleusercontent.com", "gstatic.com"}


def valid_domain(d: str) -> bool:
    if not d or d != d.lower() or d.startswith(".") or d.endswith("."):
        return False
    labels = d.split(".")
    return all(LABEL_RE.match(l) for l in labels)


def valid_cidr(c: str, version: int) -> bool:
    try:
        net = ipaddress.ip_network(c, strict=True)
    except ValueError:
        return False
    return net.version == version


@dataclass(frozen=True)
class Rule:
    """统一规则。kind: domain | suffix | keyword | ip4 | ip6"""
    kind: str
    value: str
    target: str               # 策略组名 / DIRECT / REJECT
    stage: str                # lan | exception | ads_local | product | service_ip
    service: str = ""
    ev: str = ""
    note: str = ""
    order: int = 0            # 源文件中的顺序，用于稳定排序

    @property
    def key(self):
        return (self.kind, self.value)


def suffix_match(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def rule_matches_host(kind: str, value: str, host: str) -> bool:
    if kind == "domain":
        return host == value
    if kind == "suffix":
        return suffix_match(host, value)
    if kind == "keyword":
        return value in host
    return False


def covers(broad_kind: str, broad: str, narrow_kind: str, narrow: str) -> bool:
    """broad 规则的匹配集合是否包含 narrow 规则的匹配集合（域名类）。"""
    if broad_kind == "suffix":
        if narrow_kind in ("domain", "suffix"):
            return suffix_match(narrow, broad)
        return False
    if broad_kind == "domain":
        return narrow_kind == "domain" and narrow == broad
    if broad_kind == "keyword":
        if narrow_kind in ("domain", "suffix"):
            return broad in narrow
        if narrow_kind == "keyword":
            return broad in narrow
    return False


def cidr_covers(broad: str, narrow: str) -> bool:
    b = ipaddress.ip_network(broad)
    n = ipaddress.ip_network(narrow)
    return b.version == n.version and n.subnet_of(b)


def strip_flag_group(regex: str) -> str:
    """'(?i)(A|B)' -> 'A|B'，用于组合。"""
    r = regex
    if r.startswith("(?i)"):
        r = r[4:]
    if r.startswith("(") and r.endswith(")"):
        # 确认最外层括号成对
        depth = 0
        for i, ch in enumerate(r):
            if ch == "(" and (i == 0 or r[i - 1] != "\\"):
                depth += 1
            elif ch == ")" and (i == 0 or r[i - 1] != "\\"):
                depth -= 1
                if depth == 0 and i != len(r) - 1:
                    return r
        return r[1:-1]
    return r


def compose_node_regex(include: Optional[str], exclude: Iterable[str]) -> str:
    """组合成单个正则：包含 include 且不包含任何 exclude。供 Loon / QX / sing-box 使用。
    只使用 (?i)、分组、交替、前瞻与定长后顾，Python re / .NET regexp2 / ICU 都支持。"""
    excl = "|".join(strip_flag_group(e) for e in exclude)
    parts = ["(?i)^"]
    if excl:
        parts.append(f"(?!.*(?:{excl}))")
    if include:
        parts.append(f".*(?:{strip_flag_group(include)}).*$")
    else:
        parts.append(".*$")
    return "".join(parts)


def check_regex_line_safe(regex: str) -> None:
    for bad in (",", '"', "\n"):
        if bad in regex:
            raise ValueError(f"节点正则不能包含 {bad!r}（Loon / QX 行语法限制）: {regex}")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

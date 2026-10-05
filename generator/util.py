"""通用工具：域名 / CIDR 校验、规则覆盖关系、稳定输出。"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field

LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

# 共享云 / 公共 CDN / 第三方托管根域：禁止作为后缀整体收录到任何业务组
BANNED_SHARED_SUFFIXES = {
    "amazonaws.com", "cloudfront.net", "akamaized.net", "akamaihd.net", "akamai.net",
    "edgekey.net", "edgesuite.net", "fastly.net", "fastlylb.net", "cloudflare.net",
    "azureedge.net", "azurewebsites.net", "windows.net", "trafficmanager.net", "azure.com",
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
    nature: str = ""          # "shared"：共享依赖（例如 Google 的共享接口根域）；空 = 产品专属

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


def check_regex_line_safe(regex: str) -> None:
    """节点筛选正则要原样写进 Loon / Quantumult X 的一行、mihomo 的 filter 里：
    不能有英文逗号（QX、Loon 用它分隔参数）、双引号（Loon 用它包住正则）、换行、反引号（mihomo 用它分隔多条正则）。"""
    for bad in (",", '"', "\n", "`"):
        if bad in regex:
            raise ValueError(f"节点正则不能包含 {bad!r}（Loon / QX 行语法、mihomo filter 的限制）: {regex[:80]}")


def safe_stdout() -> None:
    """节点名里常有国旗等表情符号。Windows 上把输出重定向到文件或管道时，默认编码（GBK）写不了它们：
    重定向时改用 UTF-8；直接显示在终端时，写不了的字符用 ? 代替，不让工具因此中断。"""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

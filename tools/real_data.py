"""上游数据文件的读取与成员判断，以及“要核对哪些主机、各端应该交给谁”的清单。只读，不联网。

tools/check_real_routes.py（用官方内核和这些文件实际跑）与 tests/test_real_data.py（用记录下来的成员快照离线跑）共用。

为什么要有这一层（2026-10-03 审核 F01）：以前路由测试里的“国内域名集合”“广告集合”只是 tests/fixtures.yaml 里的几条样本，
所以“qwen.ai 在真实的国内域名集合里”这种事测试看不到。现在把核对用到的每个主机在真实集合里的成员关系记成一份快照
（tests/data/real_sets.json，带数据文件的 SHA-256），测试用它重跑一遍全部用例。
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(ROOT, "tests", "data", "real_sets.json")
FAMILIES = ("mihomo", "singbox", "loon", "quantumultx")
# 各端配置里引用的集合（改了配置引用的集合，这里和快照都要跟着改；测试会检查两边一致）
MIHOMO_SETS = ("category-ads-all", "cn", "geolocation-!cn")
SINGBOX_SETS = ("geosite-category-ads-all", "geosite-cn", "geosite-geolocation-!cn")
SINGBOX_IP_SETS = ("geoip-cn",)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 域名集合
# ---------------------------------------------------------------------------

class DomainSet:
    """full（精确）/ suffix（域名本身和全部子域）/ subonly（只含子域，sing-box 里以“.”开头的后缀）/ keyword / regex。"""

    def __init__(self):
        self.full: set = set()
        self.suffix: set = set()
        self.subonly: set = set()
        self.keyword: List[str] = []
        self.regex: List[Tuple[str, "re.Pattern"]] = []

    def __len__(self):
        return len(self.full) + len(self.suffix) + len(self.subonly) + len(self.keyword) + len(self.regex)

    def add_regex(self, pattern: str) -> None:
        try:
            self.regex.append((pattern, re.compile(pattern)))
        except re.error:                    # Go 的正则里有 Python 不认识的写法时跳过，并在快照里记一笔
            self.regex.append((pattern, None))

    def why(self, host: str) -> Optional[str]:
        """命中的那一条（给人看），没命中返回 None。"""
        host = host.lower().rstrip(".")
        if host in self.full:
            return "full:" + host
        parts = host.split(".")
        for i in range(len(parts)):
            s = ".".join(parts[i:])
            if s in self.suffix:
                return "suffix:" + s
            if i > 0 and s in self.subonly:
                return "suffix:." + s
        for k in self.keyword:
            if k in host:
                return "keyword:" + k
        for pattern, rx in self.regex:
            if rx is not None and rx.search(host):
                return "regex:" + pattern
        return None


# ---- V2Ray 的 geosite.dat / geoip.dat（protobuf）：mihomo 用的 MetaCubeX 数据 ----

def _varint(b: bytes, i: int) -> Tuple[int, int]:
    x = s = 0
    while True:
        c = b[i]
        i += 1
        x |= (c & 0x7F) << s
        if c < 0x80:
            return x, i
        s += 7


def _fields(b: bytes):
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            ln, i = _varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif wt == 1:
            v = b[i:i + 8]
            i += 8
        elif wt == 5:
            v = b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"不认识的 protobuf 线类型 {wt}")
        yield f, wt, v


def read_geosite_dat(path: str, wanted=None) -> Dict[str, DomainSet]:
    """GeoSiteList{repeated GeoSite entry=1}；GeoSite{country_code=1; repeated Domain domain=2}；
    Domain{type=1（0 关键词、1 正则、2 域名含子域、3 精确）; value=2}。"""
    with open(path, "rb") as f:
        data = f.read()
    out: Dict[str, DomainSet] = {}
    for f1, _, v in _fields(data):
        if f1 != 1:
            continue
        code, doms = None, []
        for f2, _, v2 in _fields(v):
            if f2 == 1:
                code = v2.decode().lower()
                if wanted is not None and code not in wanted:
                    break
            elif f2 == 2:
                doms.append(v2)
        if code is None or (wanted is not None and code not in wanted):
            continue
        ds = DomainSet()
        for raw in doms:
            t, val = 0, ""
            for f3, _, v3 in _fields(raw):
                if f3 == 1:
                    t = v3
                elif f3 == 2:
                    val = v3.decode()
            if t == 3:
                ds.full.add(val.lower())
            elif t == 2:
                ds.suffix.add(val.lower())
            elif t == 0:
                ds.keyword.append(val.lower())
            else:
                ds.add_regex(val)
        out[code] = ds
    return out


def read_geoip_dat(path: str, code: str) -> List["ipaddress._BaseNetwork"]:
    """GeoIPList{repeated GeoIP entry=1}；GeoIP{country_code=1; repeated CIDR cidr=2}；CIDR{bytes ip=1; uint32 prefix=2}。"""
    with open(path, "rb") as f:
        data = f.read()
    nets = []
    for f1, _, v in _fields(data):
        if f1 != 1:
            continue
        name, cidrs = None, []
        for f2, _, v2 in _fields(v):
            if f2 == 1:
                name = v2.decode().lower()
                if name != code.lower():
                    break
            elif f2 == 2:
                cidrs.append(v2)
        if name != code.lower():
            continue
        for raw in cidrs:
            ip, prefix = b"", 0
            for f3, _, v3 in _fields(raw):
                if f3 == 1:
                    ip = v3
                elif f3 == 2:
                    prefix = v3
            nets.append(ipaddress.ip_network((ipaddress.ip_address(ip), prefix), strict=False))
    return nets


# ---- sing-box 的 .srs：用 sing-box 自己的 rule-set decompile 转成 JSON 再读 ----

def decompile_srs(singbox: str, path: str) -> dict:
    out = path + ".decompiled.json"
    r = subprocess.run([singbox, "rule-set", "decompile", path, "-o", out], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"sing-box rule-set decompile {path} 失败：{(r.stdout + r.stderr).strip()[-300:]}")
    try:
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    finally:
        os.remove(out)


def srs_domain_set(data: dict) -> DomainSet:
    ds = DomainSet()
    for rule in data.get("rules", []):
        for x in _as_list(rule.get("domain")):
            ds.full.add(x.lower())
        for x in _as_list(rule.get("domain_suffix")):
            x = x.lower()
            (ds.subonly if x.startswith(".") else ds.suffix).add(x.lstrip("."))
        for x in _as_list(rule.get("domain_keyword")):
            ds.keyword.append(x.lower())
        for x in _as_list(rule.get("domain_regex")):
            ds.add_regex(x)
    return ds


def srs_networks(data: dict) -> list:
    return [ipaddress.ip_network(x, strict=False) for rule in data.get("rules", []) for x in _as_list(rule.get("ip_cidr"))]


def _as_list(v) -> list:
    return [] if v is None else (v if isinstance(v, list) else [v])


# ---- blackmatrix7 的规则列表（Loon / Quantumult X 的远程广告集合）----

class RuleList:
    """一份远程规则文件：域名、后缀、关键词、IP 段。"""

    def __init__(self):
        self.domains = DomainSet()
        self.nets: list = []
        self.ignored: Dict[str, int] = {}

    def host_hits(self, host: str) -> List[str]:
        w = self.domains.why(host)
        return [w] if w else []

    def ip_hits(self, ip: str) -> List[str]:
        a = ipaddress.ip_address(ip)
        return ["ip:" + str(n) for n in self.nets if a.version == n.version and a in n][:1]


def read_rule_list(path: str) -> RuleList:
    """认三种写法：Loon / Clash 的“类型,值”、Quantumult X 的“类型,值,策略”、域名集合（每行一个域名，“.”开头表示含子域）。"""
    rl = RuleList()
    kinds = {"DOMAIN": "full", "HOST": "full", "DOMAIN-SUFFIX": "suffix", "HOST-SUFFIX": "suffix",
             "DOMAIN-KEYWORD": "keyword", "HOST-KEYWORD": "keyword",
             "IP-CIDR": "ip", "IP-CIDR6": "ip", "IP6-CIDR": "ip"}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            if "," not in line:                                  # 域名集合
                if line.startswith("."):
                    rl.domains.suffix.add(line[1:].lower())
                else:
                    rl.domains.full.add(line.lower())
                continue
            parts = [x.strip() for x in line.split(",")]
            kind = kinds.get(parts[0].upper())
            if kind is None:
                rl.ignored[parts[0].upper()] = rl.ignored.get(parts[0].upper(), 0) + 1
            elif kind == "ip":
                rl.nets.append(ipaddress.ip_network(parts[1], strict=False))
            elif kind == "keyword":
                rl.domains.keyword.append(parts[1].lower())
            else:
                getattr(rl.domains, kind).add(parts[1].lower())
    return rl


BM7_RAW_PREFIX = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/"


def bm7_local_path(bm7_dir: str, url: str) -> str:
    """配置里订阅的是 master 分支的在线文件；核对时用固定快照检出目录里的同名文件。"""
    if not url.startswith(BM7_RAW_PREFIX):
        raise ValueError(f"不认识的远程规则地址：{url}")
    return os.path.join(bm7_dir, *url[len(BM7_RAW_PREFIX):].split("/"))


# ---------------------------------------------------------------------------
# 要核对的主机与期望
# ---------------------------------------------------------------------------

def _load(rel: str):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_probes(model) -> List[dict]:
    """[{host | ip, expect: {族: 期望的组}, src}]。
    来源：tests/cases.yaml 的全部路由用例（标了 synthetic 的除外：它们只在样本数据下有意义）、
    同一个文件里“跟随上游数据的已知行为”（upstream_followed，只在真实数据下有意义），
    以及统一源里写了去向（to）的排除项。期望都是人工写的。"""
    out = []
    cases = _load("tests/cases.yaml")
    for c in cases["cases"]:
        if c.get("synthetic"):
            continue
        exp = {f: c.get("per_client", {}).get(f, c["expect"]) for f in FAMILIES}
        out.append({"host": c.get("host"), "ip": c.get("ip"), "expect": exp, "src": "cases.yaml", "why": c.get("why", "")})
    for c in cases.get("upstream_followed") or []:
        exp = {f: c.get("per_client", {}).get(f, c["expect"]) for f in FAMILIES}
        out.append({"host": c["host"], "ip": None, "expect": exp, "src": "cases.yaml 的 upstream_followed（跟随上游的已知行为）",
                    "why": c.get("why", ""), "followed": True, "base": c["expect"]})
    for s in model.services:
        for x in s.shared_excluded:
            if x.get("to"):
                for h in x["probe"]:
                    out.append({"host": h, "ip": None, "expect": {f: x["to"] for f in FAMILIES},
                                "src": f"{s.file} {s.id} 的排除项", "why": x.get("why", "")})
    return out


def dns_cases() -> List[dict]:
    return _load("tests/cases.yaml")["singbox_dns"]


def dial_cases() -> List[dict]:
    """sing-box 拨号时的解析用例（节点服务器的名字、域名形式的直连目标各交给哪个 DNS 服务器）。"""
    return _load("tests/cases.yaml")["singbox_dial"]


def dial_key(case: dict) -> str:
    """快照里记录一条拨号用例的键。"""
    return f"node {case['server']}" if case["kind"] == "node" else f"direct {case['host']}"


def all_hosts(model) -> List[str]:
    """快照里要有成员记录的全部主机名（按字母排序）。"""
    hosts = {p["host"] for p in collect_probes(model) if p["host"]}
    cases = _load("tests/cases.yaml")
    hosts |= {c["host"] for c in cases["cases"] if c.get("host")}
    hosts |= {c["host"] for c in cases["singbox_dns"]}
    hosts |= set(cases.get("exception_consistency", []))
    return sorted(hosts)


def all_ips(model) -> List[str]:
    cases = _load("tests/cases.yaml")
    ips = {c["ip"] for c in cases["cases"] if c.get("ip")}
    ips |= set(_load("tests/fixtures.yaml")["dns"].values())      # 测试里假定的解析结果
    return sorted(ips)


def routing_digest(output_rel: str, text: str) -> str:
    """一份产物里“决定连接和查询交给谁”的部分的 SHA-256：mihomo 取 rules 与 dns 两段；sing-box 取 route 与 dns 两段。
    注释、版本号、策略组的成员与图标这些不影响判断的内容不算在内——改了它们不必重新跑官方内核，改了规则或 DNS 才要。"""
    if output_rel.startswith("mihomo/"):
        c = yaml.safe_load(text)
        part = {"rules": c.get("rules"), "dns": c.get("dns")}
    else:
        c = json.loads(text)
        part = {"route": c.get("route"), "dns": c.get("dns")}
    return hashlib.sha256(json.dumps(part, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_snapshot() -> dict:
    with open(SNAPSHOT, encoding="utf-8") as f:
        return json.load(f)

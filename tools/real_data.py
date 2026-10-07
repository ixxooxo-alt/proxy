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
# Loon / Quantumult X 另有严格版（2026-10-06）。它和标准版订阅的上游数据算在同一类里（成员快照按类记录），
# 但期望可以不同：用例的 per_client 里可以单独写 loon-strict / quantumultx-strict，没写时跟同一类的标准版。
STRICT_KEYS = {"loon-strict": "loon", "quantumultx-strict": "quantumultx"}
EXPECT_KEYS = FAMILIES + tuple(STRICT_KEYS)
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


# ---- blackmatrix7 的规则列表（Loon / Quantumult X 的远程广告集合；Loon 严格版订阅的国内域名集合）----

class RuleList:
    """一份远程规则文件：域名、后缀、关键词、IP 段。"""

    def __init__(self):
        self.domains = DomainSet()
        self.nets: list = []
        self.ignored: Dict[str, int] = {}
        # 按 IP 判断、又不带 no-resolve 的行（原文）。Loon 遇到域名连接时会为这样的规则先在本机解析——严格版的前提是
        # 它订阅的上游文件里没有这样的行（只对 Loon 的写法有意义：Quantumult X 没有 no-resolve 这个参数）
        self.ip_resolving: List[str] = []

    def host_hits(self, host: str) -> List[str]:
        w = self.domains.why(host)
        return [w] if w else []

    def ip_hits(self, ip: str) -> List[str]:
        a = ipaddress.ip_address(ip)
        return ["ip:" + str(n) for n in self.nets if a.version == n.version and a in n][:1]


# 按目标 IP 判断的规则类型（Loon / Clash 的写法）。GEOIP、IP-ASN 这里不读成员，但带不带 no-resolve 照样要数
IP_RULE_TYPES = {"IP-CIDR", "IP-CIDR6", "IP6-CIDR", "GEOIP", "IP-ASN"}


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
            if parts[0].upper() in IP_RULE_TYPES and not any(x.lower() == "no-resolve" for x in parts[2:]):
                rl.ip_resolving.append(line)
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


def expect_of(case: dict, key: str) -> str:
    """一条用例在某一类客户端（或某一份严格版）上的期望：per_client[键] → per_client[同一类的标准版] → expect。"""
    pc = case.get("per_client") or {}
    if key in pc:
        return pc[key]
    return pc.get(STRICT_KEYS.get(key, key), case["expect"])


def upstream_remote_lists(model) -> Dict[str, List[str]]:
    """Loon / Quantumult X 的配置（标准版和严格版合起来）订阅的上游规则文件地址。本项目自己生成的远程规则文件不在内：
    它们的内容就是这次的产物，模拟器直接读（tests/emulate.py 的 register_own_lists）。"""
    out = {}
    for family in ("loon", "quantumultx"):
        urls = [x["url"] for x in model.adblock["remote_lists"][family]]
        urls += [x["url"] for x in model.strict["domestic_lists"][family] if x.get("url")]
        out[family] = urls
    return out


def collect_probes(model) -> List[dict]:
    """[{host | ip, expect: {键: 期望的组}, src}]。expect 的键是四类客户端加两份严格版（EXPECT_KEYS）。
    来源：tests/cases.yaml 的全部路由用例（标了 synthetic 的除外：它们只在样本数据下有意义）、
    同一个文件里“跟随上游数据的已知行为”（upstream_followed）和“只在真实数据下才看得到的行为”（real_only），
    以及统一源里写了去向（to）的排除项。期望都是人工写的。"""
    out = []
    cases = _load("tests/cases.yaml")
    for c in cases["cases"]:
        if c.get("synthetic"):
            continue
        exp = {k: expect_of(c, k) for k in EXPECT_KEYS}
        out.append({"host": c.get("host"), "ip": c.get("ip"), "expect": exp, "src": "cases.yaml", "why": c.get("why", "")})
    for c in cases.get("upstream_followed") or []:
        exp = {k: expect_of(c, k) for k in EXPECT_KEYS}
        out.append({"host": c["host"], "ip": None, "expect": exp, "src": "cases.yaml 的 upstream_followed（跟随上游的已知行为）",
                    "why": c.get("why", ""), "followed": True, "base": c["expect"]})
    for c in cases.get("real_only") or []:
        exp = {k: expect_of(c, k) for k in EXPECT_KEYS}
        out.append({"host": c["host"], "ip": None, "expect": exp, "src": "cases.yaml 的 real_only（只在真实数据下看得到的行为）",
                    "why": c.get("why", ""), "real_only": True})
    for s in model.services:
        for x in s.shared_excluded:
            if x.get("to"):
                for h in x["probe"]:
                    out.append({"host": h, "ip": None, "expect": {k: x["to"] for k in EXPECT_KEYS},
                                "src": f"{s.file} {s.id} 的排除项", "why": x.get("why", "")})
    return out


def dns_cases(family: str = "singbox") -> List[dict]:
    """DNS 查询去向的用例：sing-box 的在 singbox_dns，mihomo 的在 mihomo_dns。"""
    return _load("tests/cases.yaml")[f"{family}_dns"]


# 出站时的解析（2026-10-07，GPT 审核 r13 的 R13-F01）：哪个内核 - 测试出口的类型 - 流量
OUTBOUND_SCENARIOS = ("mihomo-socks5-tcp", "mihomo-socks5-udp", "mihomo-wireguard-tcp", "singbox-socks-udp", "singbox-wireguard-tcp")


def outbound_cases() -> List[dict]:
    """连接交给代理出口以后、名字交给谁解析的用例（tests/cases.yaml 的 outbound_resolve）。每条都要写全部场景的期望。"""
    cases = _load("tests/cases.yaml")["outbound_resolve"]
    for c in cases:
        if sorted(c["expect"]) != sorted(OUTBOUND_SCENARIOS):
            raise ValueError(f"outbound_resolve 里 {c['host']} 的期望没有写全场景：{sorted(c['expect'])}")
        if not set(c.get("limit", [])) <= set(OUTBOUND_SCENARIOS):
            raise ValueError(f"outbound_resolve 里 {c['host']} 的 limit 要写场景名：{c['limit']}")
    hosts = [c["host"] for c in cases]
    if len(set(hosts)) != len(hosts):
        raise ValueError("outbound_resolve 里有重复的主机：核对时是按名字认查询的")
    return cases


def dial_cases(family: str = "singbox") -> List[dict]:
    """连接时名字交给哪个 DNS 的用例：sing-box 的在 singbox_dial，mihomo 的在 mihomo_dial。
    kind: node（节点服务器的名字）、direct（域名形式的直连目标）是拨号时的解析；
    kind: proxied（有规则、走代理组的域名）、unlisted（没有被任何域名规则接住的域名）是 2026-10-06 加的，
    看的是规则判断阶段这个名字有没有被拿去解析、问的是谁。"""
    return _load("tests/cases.yaml")[f"{family}_dial"]


DIAL_KINDS = ("node", "direct", "proxied", "unlisted")
# “境外 DNS 不应答”那一遍重跑的用例：这两类加上公网直连的对照
SILENT_KINDS = ("proxied", "unlisted")


def dial_name(case: dict) -> str:
    """这条用例看的是哪个名字。"""
    return case["server"] if case["kind"] == "node" else case["host"]


def dial_key(case: dict) -> str:
    """快照里记录一条拨号用例的键。"""
    if case["kind"] not in DIAL_KINDS:
        raise ValueError(f"不认识的拨号用例类型 {case['kind']}")
    return f"{case['kind']} {dial_name(case)}"


def silent_cases(cases: List[dict]) -> List[dict]:
    """“境外 DNS 只收不答”那一遍用到的用例：走代理的、没被接住的，加上“直连公网域名”作对照（它应该照旧只问国内 DNS）。"""
    control = [c for c in cases if c["kind"] == "direct" and c["expect"] in ("domestic", "dns-cn")]
    return [c for c in cases if c["kind"] in SILENT_KINDS] + control


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


# ---------------------------------------------------------------------------
# 拨号核对用的配置：节点服务器的名字、域名形式的直连目标，拨号时交给哪个 DNS
# ---------------------------------------------------------------------------

DIAL_NODE_NAME = "拨号核对节点"
# 拨号核对怎么用生成的 mihomo 配置：这几个顶层字段原样保留……
MIHOMO_DIAL_KEPT = ("mode", "ipv6", "unified-delay", "tcp-concurrent", "geodata-mode", "dns", "sniffer", "rules")
# ……这几个由核对工具自己另写或者去掉（只开本机的一个端口、不开 TUN 和控制面、不下载订阅和数据文件、策略组换成固定出口）
MIHOMO_DIAL_REPLACED = ("mixed-port", "allow-lan", "bind-address", "external-controller", "log-level", "find-process-mode",
                        "profile", "geo-auto-update", "geo-update-interval", "geox-url", "tun", "proxy-providers", "proxy-groups")
# sing-box：日志、入站、缓存文件由核对工具另写或者去掉；http_clients 只管远程规则集怎么下载（核对时规则集换成本地文件）
SINGBOX_DIAL_REPLACED = ("log", "inbounds", "experimental", "http_clients")
SINGBOX_DIAL_KEPT = ("dns", "route", "outbounds")
SINGBOX_GROUP_TYPES = ("selector", "urltest")


def dial_proxies(cases: List[dict], port: int) -> List[dict]:
    """拨号核对用的节点（Clash 的写法）：每个 kind: node 的用例一个 SOCKS 节点，服务器地址取自用例，端口由调用方给
    （核对时是本机一个没人监听的端口）。"""
    return [{"name": f"{DIAL_NODE_NAME} {i + 1}", "type": "socks5", "server": c["server"], "port": port}
            for i, c in enumerate(c for c in cases if c["kind"] == "node")]


def _only_known_keys(conf: dict, kept, replaced, what: str) -> None:
    unknown = sorted(set(conf) - set(kept) - set(replaced))
    if unknown:
        raise ValueError(f"{what}多了顶层字段 {unknown}：拨号核对不知道该原样保留它还是另写。"
                         "先在 tools/real_data.py 里把它归到“原样保留”或“核对工具另写”的名单里")


def mihomo_dial_base(text: str) -> dict:
    """拨号核对从生成的 mihomo 配置里原样拿来用的那部分：规则、DNS、嗅探和几个开关（MIHOMO_DIAL_KEPT）。
    生成的配置里出现了两份名单之外的顶层字段时报错——新加的字段可能影响拨号（比如 hosts），要先决定核对时怎么对待它。"""
    conf = yaml.safe_load(text)
    _only_known_keys(conf, MIHOMO_DIAL_KEPT, MIHOMO_DIAL_REPLACED, "生成的 mihomo 配置")
    return {k: conf[k] for k in MIHOMO_DIAL_KEPT if k in conf}


def singbox_dial_base(model, plan, variant: str, cases: List[dict], port: int = 1) -> Tuple[dict, Dict[str, str]]:
    """拨号核对用的 sing-box 配置：生成器带着核对用的节点（dial_proxies）生成的那一份，还没有换上本机替身。
    返回 (配置, {节点的服务器地址: 出站标签})。公开模板里没有节点，节点上的 domain_resolver 只有这样生成才看得到。"""
    from generator import emit_singbox, nodes as nodeconv      # 用到时才引入：读数据文件的那些函数不需要生成器
    proxies = dial_proxies(cases, port)
    conv, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(model))
    if len(conv) != len(proxies):
        raise RuntimeError("拨号核对用的节点没能全部转换：" + "；".join(report))
    conf = json.loads(emit_singbox.build(model, plan, variant, nodes=conv, renamed=renamed))
    _only_known_keys(conf, SINGBOX_DIAL_KEPT, SINGBOX_DIAL_REPLACED, f"生成的 sing-box {variant} 配置")
    wanted = {p["server"] for p in proxies}
    tag_of = {o["server"]: o["tag"] for o in conf["outbounds"] if o.get("server") in wanted}
    return conf, tag_of


def dial_digest(family: str, base: dict) -> str:
    """拨号核对那份配置里“会影响拨号时名字交给谁解析”的部分的 SHA-256（2026-10-05 审核 r10 的建议）。

    routing_digest 只算规则段和 DNS 段，用来确认“规则把目标交给哪个组”的记录没有过期是够的；拨号时的解析还取决于
    出站自己的设置（sing-box 的 domain_resolver、detour 等），那些不在规则段和 DNS 段里。所以拨号记录另记这一个摘要：
      mihomo   mihomo_dial_base 返回的全部内容（规则、DNS、嗅探和几个开关）；
      sing-box dns、route 两段，加上策略组以外的全部出站（直连出站、核对用的节点，连同各自的 domain_resolver）。
               节点的端口每次核对都不一样，不算在内。
    策略组的成员与图标、注释、版本号不在里面：改了它们不必重新跑官方内核。"""
    if family == "mihomo":
        part = base
    else:
        outbounds = []
        for o in base["outbounds"]:
            if o.get("type") in SINGBOX_GROUP_TYPES:
                continue
            o = dict(o)
            o.pop("server_port", None)
            outbounds.append(o)
        part = {"dns": base["dns"], "route": base["route"], "outbounds": outbounds}
    return hashlib.sha256(json.dumps(part, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def routing_digest(output_rel: str, text: str) -> str:
    """一份产物里“决定连接和查询交给谁”的部分的 SHA-256：mihomo 取 rules 与 dns 两段；sing-box 取 route 与 dns 两段。
    注释、版本号、策略组的成员与图标这些不影响判断的内容不算在内——改了它们不必重新跑官方内核，改了规则或 DNS 才要。
    它管的是“规则把目标交给哪个组、DNS 查询交给哪个服务器”的记录；拨号时名字交给谁解析的记录另有 dial_digest
    （出站自己的设置不在规则段和 DNS 段里，这个摘要看不到）。"""
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

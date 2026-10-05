"""按各客户端文档描述的匹配语义，模拟“生成出来的配置文本”会把一个连接交给哪个策略。
这里解析的是 dist/ 里的真实产物，而不是生成器的内部数据，用来发现“生成器写错语法 / 顺序”的问题。
远程集合（广告、国内域名、GeoIP）有两种来源：
  - Fixtures：tests/fixtures.yaml 里的几条样本，用来检查先后顺序这类语义；
  - SnapshotFixtures：tests/data/real_sets.json 记录的真实上游数据成员关系（由 tools/check_real_routes.py 生成），
    用来检查“在真实数据下最后交给谁”（2026-10-03 审核 F01：只用样本看不出 qwen.ai 在真实的国内域名集合里）。
解析结果（某个域名解析到哪个 IP）两种来源下都是 fixtures.yaml 里假定的。

这是自制模拟器，不能替代官方解析器与真机验证；mihomo / sing-box 另用官方内核实际跑一遍（tools/check_real_routes.py）。"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import yaml


@dataclass
class Conn:
    host: Optional[str] = None
    ip: Optional[str] = None


def suffix_match(host: str, sfx: str) -> bool:
    return host == sfx or host.endswith("." + sfx)


def in_cidrs(ip: str, cidrs: List[str]) -> bool:
    a = ipaddress.ip_address(ip)
    return any(a in ipaddress.ip_network(c) for c in cidrs)


class Fixtures:
    def __init__(self, data: dict, ads_on: bool = True, exception_values=()):
        """ads_on=False 模拟“关闭广告规则”：去掉广告拦截条目、远程广告集合以及只为对抗它们而存在的误杀例外。"""
        self.ads_on = ads_on
        self.exception_values = set(exception_values) if not ads_on else set()
        self.dns: Dict[str, str] = data["dns"]
        self.geoip = {k.lower(): v for k, v in data["geoip"].items()}
        self.geosite = dict(data["geosite"])
        if not ads_on:
            self.geosite["category-ads-all"] = []
        self.ads = data["ad_list"] if ads_on else []

    def resolve(self, host: str) -> Optional[str]:
        return self.dns.get(host)

    def site(self, name: str, host: str) -> bool:
        return any(suffix_match(host, s) for s in self.geosite.get(name, []))

    def geoip_match(self, code: str, ip: str) -> bool:
        return in_cidrs(ip, self.geoip.get(code.lower(), []))

    # Loon / Quantumult X 订阅的远程规则文件（url 是配置里写的地址）。样本里不分文件：每个远程广告集合都用同一份样本
    def remote_host_hit(self, url: str, host: str) -> bool:
        return any((t == "domain" and host == v) or (t == "suffix" and suffix_match(host, v)) or (t == "keyword" and v in host)
                   for t, v in self.ads)

    def remote_ip_hit(self, url: str, ip: str) -> bool:
        return False


class SnapshotFixtures(Fixtures):
    """真实上游数据的成员快照。family：mihomo / singbox / loon / quantumultx（同名集合在各端的数据不一样，
    例如 mihomo 用 MetaCubeX 的 geosite.dat，sing-box 用 SagerNet 的 .srs）。
    快照里没有某个主机的记录时直接报错，不当成“不在集合里”。"""

    def __init__(self, snap: dict, family: str, dns: Dict[str, str]):
        self.ads_on = True
        self.exception_values = set()
        self.snap, self.family = snap, family
        self.dns = dict(dns)

    def _rec(self, kind: str, key: str) -> dict:
        try:
            return self.snap[kind][key][self.family]
        except KeyError:
            raise KeyError(f"成员快照里没有 {key} 的记录：加了新的用例或排除项之后，要重新运行 "
                           "tools/check_real_routes.py --write-snapshot（需要官方内核和上游数据文件）") from None

    def site(self, name: str, host: str) -> bool:
        if self.family not in ("mihomo", "singbox"):
            raise AssertionError(f"{self.family} 的配置不应该引用域名集合 {name}")
        return (name if self.family == "mihomo" else "geosite-" + name) in self._rec("hosts", host)

    def geoip_match(self, code: str, ip: str) -> bool:
        if code.lower() != "cn":
            raise AssertionError(f"快照只记录了国内 IP 段，配置引用了 {code}")
        # Loon / Quantumult X 用 App 自带的 GeoIP 库，拿不到；这里假定与 mihomo 的数据一致
        fam = self.family if self.family in ("mihomo", "singbox") else "mihomo"
        try:
            return bool(self.snap["ips"][ip][fam]["cn"])
        except KeyError:
            raise KeyError(f"成员快照里没有 IP {ip} 的记录：重新运行 tools/check_real_routes.py --write-snapshot") from None

    def remote_host_hit(self, url: str, host: str) -> bool:
        return url in self._rec("hosts", host)

    def remote_ip_hit(self, url: str, ip: str) -> bool:
        return url in self._rec("ips", ip)


# ---------------------------------------------------------------------------
# mihomo：严格按书写顺序；IP 类规则在域名连接上会触发解析，除非带 no-resolve
# ---------------------------------------------------------------------------

def parse_mihomo(text: str) -> dict:
    return yaml.safe_load(text)


def mihomo_route(conf: dict, c: Conn, fx: Fixtures) -> str:
    rules = conf["rules"]
    if not fx.ads_on:
        rules = _mihomo_drop_adblock(rules, fx.exception_values)
    ip = c.ip
    for line in rules:
        parts = [x.strip() for x in line.split(",")]
        t = parts[0]
        if t == "MATCH":
            return parts[1]
        payload, target, opts = parts[1], parts[2], parts[3:]
        if t in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "GEOSITE"):
            if not c.host:
                continue
            h = c.host
            ok = ((t == "DOMAIN" and h == payload) or (t == "DOMAIN-SUFFIX" and suffix_match(h, payload))
                  or (t == "DOMAIN-KEYWORD" and payload in h) or (t == "GEOSITE" and fx.site(payload, h)))
            if ok:
                return target
        elif t in ("IP-CIDR", "IP-CIDR6", "GEOIP"):
            cur = ip
            if cur is None and c.host:
                if "no-resolve" in opts:
                    continue
                cur = fx.resolve(c.host)
            if cur is None:
                continue
            if t == "GEOIP":
                if fx.geoip_match(payload, cur):
                    return target
            elif in_cidrs(cur, [payload]):
                return target
        else:
            raise ValueError(f"模拟器不认识的 mihomo 规则类型 {t}")
    raise AssertionError("mihomo 规则没有 MATCH 兜底")


def _mihomo_drop_adblock(rules: List[str], exception_values) -> List[str]:
    """模拟“关闭广告规则”：去掉广告拦截条目与误杀例外（例外只为对抗广告规则而存在）。
    误杀例外只出现在广告拦截条目之前；之后与例外同值的行是产品规则，必须保留。"""
    first_ad = next((i for i, line in enumerate(rules) if [x.strip() for x in line.split(",")][2:3] == ["广告拦截"]),
                    len(rules))
    out = []
    for i, line in enumerate(rules):
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 3 and (parts[2] == "广告拦截" or (i < first_ad and parts[1] in exception_values)):
            continue
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# sing-box：按顺序；域名类在同一条规则内为“或”；ip_cidr 只匹配已知 IP（IP 直连或 resolve 之后）
# ---------------------------------------------------------------------------

def parse_singbox(text: str) -> dict:
    return json.loads(text)


def singbox_route(conf: dict, c: Conn, fx: Fixtures) -> str:
    resolved = c.ip
    drop_adblock = not fx.ads_on
    rules = conf["route"]["rules"]
    first_ad = next((i for i, r in enumerate(rules) if r.get("action") == "reject"), len(rules))
    for i, r in enumerate(rules):
        # 误杀例外只出现在广告拦截（reject）之前；之后与例外同值的是产品规则，关闭广告时保留
        if drop_adblock and fx.exception_values and i < first_ad and any(k in r for k in ("domain", "domain_suffix")):
            r = dict(r)
            for k in ("domain", "domain_suffix"):
                if k in r:
                    r[k] = [v for v in r[k] if v not in fx.exception_values]
                    if not r[k]:
                        del r[k]
            if not any(k in r for k in ("domain", "domain_suffix", "domain_keyword", "ip_cidr", "rule_set")):
                continue
        action = r.get("action", "route")
        if action in ("sniff",) or r.get("protocol") == "dns":
            continue
        if drop_adblock and action == "reject":
            continue
        conditional = any(k in r for k in ("domain", "domain_suffix", "domain_keyword", "ip_cidr", "rule_set"))
        matched = False
        if any(k in r for k in ("domain", "domain_suffix", "domain_keyword")) and c.host:
            h = c.host
            matched = (h in r.get("domain", []) or any(suffix_match(h, s) for s in r.get("domain_suffix", []))
                       or any(k in h for k in r.get("domain_keyword", [])))
        if "ip_cidr" in r and resolved:
            matched = matched or in_cidrs(resolved, r["ip_cidr"])
        if "rule_set" in r:
            matched = matched or any(_singbox_rule_set(conf, tag, c.host, resolved, fx) for tag in _as_list(r["rule_set"]))
        if action == "resolve":
            # 不带条件的 resolve 对所有连接生效；带条件的（局域网后缀 → 系统 DNS）只对命中的连接生效。
            # 目标本来就是 IP 时什么都不做
            if (matched or not conditional) and c.ip is None and c.host:
                resolved = fx.resolve(c.host)
            continue
        if matched:
            return "REJECT" if action == "reject" else r["outbound"]
    return conf["route"]["final"]


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def _singbox_rule_set(conf: dict, tag: str, host: Optional[str], ip: Optional[str], fx: Fixtures) -> bool:
    """规则集：内联的按它自己写的域名判断；远程的（geosite-* / geoip-*）问数据来源。"""
    rs = next((x for x in conf["route"]["rule_set"] if x["tag"] == tag), None)
    if rs is None:
        raise AssertionError(f"规则引用了没有定义的规则集 {tag}")
    if rs["type"] == "inline":
        for rule in rs["rules"]:
            extra = set(rule) - {"domain", "domain_suffix", "domain_keyword"}
            if extra:
                raise ValueError(f"模拟器不认识内联规则集里的字段 {sorted(extra)}")
            if host and (host in rule.get("domain", []) or any(suffix_match(host, x) for x in rule.get("domain_suffix", []))
                         or any(k in host for k in rule.get("domain_keyword", []))):
                return True
        return False
    if tag.startswith("geoip-"):
        return bool(ip) and fx.geoip_match(tag[len("geoip-"):], ip)
    if tag.startswith("geosite-"):
        return bool(host) and fx.site(tag[len("geosite-"):], host)
    raise ValueError(f"模拟器不认识的规则集 {tag}")


SINGBOX_DNS_RULE_KEYS = {"domain", "domain_suffix", "domain_keyword", "rule_set", "query_type", "server"}


def singbox_dns(conf: dict, host: str, qtype: str, fx: Fixtures) -> str:
    """sing-box 的 DNS 规则：按书写顺序，第一条命中的规则决定这次查询交给哪个 DNS 服务器；都不命中用 final。
    一条规则里域名类条件（含规则集）之间是“或”，与 query_type 之间是“且”（官方文档的默认规则匹配逻辑）。
    返回服务器标签（dns-cn / dns-foreign / dns-fakeip / dns-local）。"""
    for r in conf["dns"]["rules"]:
        extra = set(r) - SINGBOX_DNS_RULE_KEYS
        if extra:
            raise ValueError(f"模拟器不认识 DNS 规则里的字段 {sorted(extra)}")
        if "query_type" in r and qtype not in r["query_type"]:
            continue
        if any(k in r for k in ("domain", "domain_suffix", "domain_keyword", "rule_set")):
            ok = (host in r.get("domain", []) or any(suffix_match(host, x) for x in r.get("domain_suffix", []))
                  or any(k in host for k in r.get("domain_keyword", []))
                  or any(_singbox_rule_set(conf, tag, host, None, fx) for tag in _as_list(r.get("rule_set", []))))
            if not ok:
                continue
        return r["server"]
    return conf["dns"]["final"]


# ---------------------------------------------------------------------------
# Loon / Quantumult X：本地 > 远程；域名类规则全部先于 IP 类规则
# ---------------------------------------------------------------------------

def _sections(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
            continue
        if cur is not None:
            out[cur].append(line)
    return out


def parse_loon(text: str) -> dict:
    s = _sections(text)
    local, final = [], None
    for line in s.get("Rule", []):
        parts = [x.strip() for x in line.split(",")]
        if parts[0] == "FINAL":
            final = parts[1]
        else:
            local.append(parts)
    remote = []
    for line in s.get("Remote Rule", []):
        parts = [x.strip() for x in line.split(",")]
        kv = dict(x.split("=", 1) for x in parts[1:])
        remote.append({"url": parts[0], "policy": kv["policy"].strip(), "enabled": kv.get("enabled", "true").strip()})
    groups = {}
    for line in s.get("Proxy Group", []):
        name, rest = [x.strip() for x in line.split("=", 1)]
        items = [x.strip() for x in rest.split(",")]
        groups[name] = {"type": items[0], "members": [x for x in items[1:] if "=" not in x]}
    filters = {}
    for line in s.get("Remote Filter", []):
        name, rest = [x.strip() for x in line.split("=", 1)]
        m = re.search(r'FilterKey\s*=\s*"(.*)"\s*$', rest)
        filters[name] = m.group(1)
    return {"local": local, "final": final, "remote": remote, "groups": groups, "filters": filters, "sections": s}


LOON_DOMAIN = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}
LOON_IP = {"IP-CIDR", "IP-CIDR6", "GEOIP"}


def _loon_like_route(local, remote, final, c: Conn, fx: Fixtures, dom_types, ip_types, norm, remote_ip_resolves=False):
    """先域名类、后 IP 类；同一类里本地规则先于订阅的远程规则（Loon 官方：本地 > 插件 > 订阅；域名规则先于 IP 规则）。
    remote_ip_resolves：远程规则里的 IP 段遇到域名连接时会不会先解析再比（Loon 的带 no-resolve，不会；Quantumult X 会）。"""
    drop_adblock = not fx.ads_on
    def dom_ok(t, v, h):
        t = norm(t)
        return (t == "DOMAIN" and h == v) or (t == "DOMAIN-SUFFIX" and suffix_match(h, v)) or (t == "DOMAIN-KEYWORD" and v in h)

    if drop_adblock:
        first_ad = next((i for i, p in enumerate(local) if p[2] == "广告拦截"), len(local))
        local = [p for i, p in enumerate(local)
                 if p[2] != "广告拦截" and not (i < first_ad and p[1] in fx.exception_values)]
        remote = [r for r in remote if r["policy"] != "广告拦截"]
    if c.host:
        for p in local:
            if norm(p[0]) in dom_types and dom_ok(p[0], p[1].lower(), c.host):
                return p[2]
        for r in remote:
            if fx.remote_host_hit(r["url"], c.host):
                return r["policy"]
    ip = c.ip
    for p in local:
        t = norm(p[0])
        if t not in ip_types:
            continue
        cur = ip
        if cur is None and c.host:
            if "no-resolve" in p[3:]:
                continue
            cur = fx.resolve(c.host)
        if cur is None:
            continue
        if t == "GEOIP":
            if fx.geoip_match(p[1], cur):
                return p[2]
        elif in_cidrs(cur, [p[1]]):
            return p[2]
    cur = ip
    if cur is None and c.host and remote_ip_resolves:
        cur = fx.resolve(c.host)
    if cur is not None:
        for r in remote:
            if fx.remote_ip_hit(r["url"], cur):
                return r["policy"]
    return final


def loon_route(conf: dict, c: Conn, fx: Fixtures) -> str:
    return _loon_like_route(conf["local"], conf["remote"], conf["final"], c, fx, LOON_DOMAIN, LOON_IP,
                            lambda t: t)


QX_NORM = {"host": "DOMAIN", "host-suffix": "DOMAIN-SUFFIX", "host-keyword": "DOMAIN-KEYWORD",
           "ip-cidr": "IP-CIDR", "ip6-cidr": "IP-CIDR6", "geoip": "GEOIP"}


def parse_qx(text: str) -> dict:
    s = _sections(text)
    local, final = [], None
    for line in s.get("filter_local", []):
        parts = [x.strip() for x in line.split(",")]
        if parts[0] == "final":
            final = parts[1]
        else:
            local.append(parts)
    remote = []
    for line in s.get("filter_remote", []):
        parts = [x.strip() for x in line.split(",")]
        kv = dict(x.split("=", 1) for x in parts[1:])
        remote.append({"url": parts[0], "policy": kv["force-policy"].strip(), "enabled": kv.get("enabled", "true")})
    policies = {}
    for line in s.get("policy", []):
        kind, rest = line.split("=", 1)
        items = [x.strip() for x in rest.split(",")]
        policies[items[0]] = {"type": kind.strip(), "members": [x for x in items[1:] if "=" not in x],
                              "params": dict(x.split("=", 1) for x in items[1:] if "=" in x)}
    return {"local": local, "final": final, "remote": remote, "policies": policies, "sections": s}


def qx_route(conf: dict, c: Conn, fx: Fixtures) -> str:
    def norm(t):
        return QX_NORM.get(t, t)
    out = _loon_like_route(conf["local"], conf["remote"], conf["final"], c, fx, LOON_DOMAIN, LOON_IP, norm,
                           remote_ip_resolves=True)
    return {"direct": "DIRECT", "reject": "REJECT"}.get(out, out)

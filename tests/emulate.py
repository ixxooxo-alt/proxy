"""按各客户端文档描述的匹配语义，模拟“生成出来的配置文本”会把一个连接交给哪个策略。
这里解析的是 dist/ 里的真实产物，而不是生成器的内部数据，用来发现“生成器写错语法 / 顺序”的问题。
远程集合（广告、国内域名、GeoIP）内容未知，用 fixtures.yaml 里的样本代替。

这是自制模拟器，不能替代官方解析器与真机验证。"""
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
        if action == "resolve":
            if c.ip is None and c.host:
                resolved = fx.resolve(c.host)
            continue
        if drop_adblock and action == "reject":
            continue
        matched = False
        if any(k in r for k in ("domain", "domain_suffix", "domain_keyword")) and c.host:
            h = c.host
            matched = (h in r.get("domain", []) or any(suffix_match(h, s) for s in r.get("domain_suffix", []))
                       or any(k in h for k in r.get("domain_keyword", [])))
        if "ip_cidr" in r and resolved:
            matched = matched or in_cidrs(resolved, r["ip_cidr"])
        if "rule_set" in r:
            tag = r["rule_set"]
            if tag.startswith("geoip-"):
                matched = bool(resolved) and fx.geoip_match(tag[len("geoip-"):], resolved)
            elif tag.startswith("geosite-") and c.host:
                name = tag[len("geosite-"):]
                matched = fx.site(name, c.host)
        if matched:
            return "REJECT" if action == "reject" else r["outbound"]
    return conf["route"]["final"]


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


def _loon_like_route(local, remote, final, c: Conn, fx: Fixtures, dom_types, ip_types, norm):
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
            for t, v in fx.ads:
                if t in ("domain", "suffix") and dom_ok({"domain": "DOMAIN", "suffix": "DOMAIN-SUFFIX"}[t], v, c.host):
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
    out = _loon_like_route(conf["local"], conf["remote"], conf["final"], c, fx, LOON_DOMAIN, LOON_IP, norm)
    return {"direct": "DIRECT", "reject": "REJECT"}.get(out, out)

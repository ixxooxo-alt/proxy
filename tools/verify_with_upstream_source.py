#!/usr/bin/env python3
"""用上游源码核对生成产物的字段名（可选工具）。

没有官方二进制时的补充手段：从 mihomo / sing-box 源码的结构体标签里提取“内核认识的字段”，
检查产物中用到的每个键都存在，并核对若干枚举值。它能发现拼错或放错位置的字段，
但不能替代 `mihomo -t` / `sing-box check` 的完整解析，更不能替代真机运行。

用法：
  python3 tools/verify_with_upstream_source.py --mihomo-src ../mihomo --singbox-src ../sing-box
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_structs(paths, tagname):
    structs, aliases = {}, {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        for m in re.finditer(r"\btype\s+(\w+)\s+struct\s*\{(.*?)\n\}", text, re.S):
            name, body = m.group(1), m.group(2)
            fields, embeds = set(), []
            for line in body.splitlines():
                s = line.strip()
                if not s or s.startswith("//"):
                    continue
                tm = re.search(tagname + r':"([^"]*)"', s)
                if tm:
                    tag = tm.group(1).split(",")[0]
                    if tag and tag != "-":
                        fields.add(tag)
                    elif tag == "" and re.match(r"^\*?[\w\.]+\s+`", s):
                        embeds.append(s.split()[0].lstrip("*").split(".")[-1])   # 带空标签的内联嵌入
                    continue
                em = re.match(r"^\*?([\w\.]+)$", s)
                if em:
                    embeds.append(em.group(1).split(".")[-1])
            structs[name] = (fields, embeds)
        for m in re.finditer(r"^type\s+(\w+)\s+(_?\w+)\s*$", text, re.M):
            aliases[m.group(1)] = m.group(2)
        for m in re.finditer(r"^\s+(\w+)\s+(_\w+)\s*$", text, re.M):     # type ( A _A ) 分组写法
            aliases.setdefault(m.group(1), m.group(2))
    return structs, aliases


def fields(structs, aliases, name, seen=None):
    seen = seen or set()
    if name in seen:
        return set()
    seen.add(name)
    name = aliases.get(name, name)
    if name not in structs:
        return set()
    own, embeds = structs[name]
    out = set(own)
    for e in embeds:
        out |= fields(structs, aliases, e, seen)
    return out


class Checker:
    def __init__(self):
        self.errors, self.checked = [], 0

    def keys(self, where, obj, allowed):
        for k in obj:
            self.checked += 1
            if k not in allowed:
                self.errors.append(f"{where}: 未知字段 {k!r}")

    def value(self, where, v, allowed):
        self.checked += 1
        if v not in allowed:
            self.errors.append(f"{where}: 值 {v!r} 不在 {sorted(allowed)}")


def check_mihomo(src: str, c: Checker):
    cfg, _ = parse_structs([os.path.join(src, "config", "config.go")], "yaml")
    grp, ga = parse_structs(glob.glob(os.path.join(src, "adapter", "outboundgroup", "*.go")), "group")
    prov, pa = parse_structs([os.path.join(src, "adapter", "provider", "parser.go")], "provider")
    top = fields(cfg, {}, "RawConfig")
    rules_src = open(os.path.join(src, "rules", "parser.go"), encoding="utf-8").read()
    for fn in ("mihomo/mihomo-profile.yaml", "mihomo/mihomo-core.yaml"):
        conf = yaml.safe_load(open(os.path.join(ROOT, "dist", fn), encoding="utf-8"))
        c.keys(fn, conf, top)
        c.keys(fn + " dns", conf["dns"], fields(cfg, {}, "RawDNS"))
        c.keys(fn + " sniffer", conf["sniffer"], fields(cfg, {}, "RawSniffer"))
        for proto, sc in conf["sniffer"]["sniff"].items():
            c.keys(fn + f" sniffer.sniff.{proto}", sc, fields(cfg, {}, "RawSniffingConfig"))
        c.keys(fn + " profile", conf["profile"], fields(cfg, {}, "RawProfile"))
        c.keys(fn + " geox-url", conf["geox-url"], fields(cfg, {}, "RawGeoXUrl"))
        if "tun" in conf:
            c.keys(fn + " tun", conf["tun"], fields(cfg, {}, "RawTun"))
        for name, p in conf["proxy-providers"].items():
            c.keys(fn + f" provider {name}", p, fields(prov, pa, "proxyProviderSchema"))
            c.keys(fn + f" provider {name}.health-check", p["health-check"], fields(prov, pa, "healthCheckSchema"))
        common = fields(grp, ga, "GroupCommonOption")
        extra = {"url-test": "URLTestOption", "select": "SelectorOption", "fallback": "FallbackOption",
                 "load-balance": "LoadBalanceOption"}
        for g in conf["proxy-groups"]:
            c.value(fn + f" group {g['name']}.type", g["type"], set(extra))
            c.keys(fn + f" group {g['name']}", g, common | fields(grp, ga, extra[g["type"]]))
            if g["type"] == "load-balance":
                c.value(fn + " strategy", g["strategy"], {"round-robin", "consistent-hashing", "sticky-sessions"})
        for r in conf["rules"]:
            t = r.split(",")[0]
            c.checked += 1
            if f'"{t}"' not in rules_src:
                c.errors.append(f"{fn}: 规则类型 {t} 未在 rules/parser.go 中找到")
        # empty-fallback 默认值与 COMPATIBLE 行为来自源码，已在报告中说明


def check_singbox(src: str, c: Checker):
    st, al = parse_structs(glob.glob(os.path.join(src, "option", "*.go")), "json")
    F = lambda n: fields(st, al, n)  # noqa: E731
    for fn in ("sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json"):
        conf = json.load(open(os.path.join(ROOT, "dist", fn), encoding="utf-8"))
        c.keys(fn, conf, F("_Options") | F("Options"))
        c.keys(fn + " log", conf["log"], F("LogOptions"))
        c.keys(fn + " dns", conf["dns"], F("RawDNSOptions") | F("DNSClientOptions") | {"servers", "rules", "final", "fakeip"})
        server_types = {"https": "RemoteHTTPSDNSServerOptions", "fakeip": "FakeIPDNSServerOptions",
                        "local": "LocalDNSServerOptions"}
        for s in conf["dns"]["servers"]:
            c.value(fn + " dns.server.type", s["type"], set(server_types))
            c.keys(fn + f" dns.server {s['tag']}", s, {"type", "tag"} | F(server_types[s["type"]]))
        dns_rule_keys = F("RawDefaultDNSRule") | F("DNSRouteActionOptions") | {"action", "type"}
        for r in conf["dns"]["rules"]:
            c.keys(fn + " dns.rule", r, dns_rule_keys)
        c.value(fn + " dns.strategy", conf["dns"]["strategy"], {"prefer_ipv4", "prefer_ipv6", "ipv4_only", "ipv6_only"})
        for ib in conf["inbounds"]:
            c.keys(fn + " inbound tun", ib, {"type", "tag"} | F("TunInboundOptions"))
        ob_types = {"selector": "SelectorOutboundOptions", "urltest": "URLTestOutboundOptions",
                    "direct": "DirectOutboundOptions", "block": "StubOptions"}
        for o in conf["outbounds"]:
            if o["type"] in ob_types:
                c.keys(fn + f" outbound {o['tag']}", o, {"type", "tag"} | F(ob_types[o["type"]]))
        route = conf["route"]
        c.keys(fn + " route", route, F("RouteOptions"))
        rule_keys = F("RawDefaultRule") | {"type", "action"}
        action_keys = {"route": F("RouteActionOptions"), "reject": F("RejectActionOptions") | F("_RejectActionOptions"),
                       "resolve": F("RouteActionResolve"), "sniff": F("RouteActionSniff"), "hijack-dns": set()}
        for r in route["rules"]:
            act = r.get("action", "route")
            c.value(fn + " route.rule.action", act, set(action_keys))
            c.keys(fn + " route.rule", r, rule_keys | action_keys[act])
        rs_keys = F("_RuleSet") | F("RemoteRuleSet")
        for rs in route["rule_set"]:
            c.keys(fn + f" rule_set {rs['tag']}", rs, rs_keys)
        for h in conf.get("http_clients", []):
            c.keys(fn + " http_client", h, F("_HTTPClientOptions"))
        c.keys(fn + " experimental", conf["experimental"], F("ExperimentalOptions"))
        c.keys(fn + " cache_file", conf["experimental"]["cache_file"], F("CacheFileOptions"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo-src")
    ap.add_argument("--singbox-src")
    a = ap.parse_args()
    c = Checker()
    if a.mihomo_src:
        check_mihomo(a.mihomo_src, c)
    if a.singbox_src:
        check_singbox(a.singbox_src, c)
    print(f"检查了 {c.checked} 个字段 / 取值")
    if c.errors:
        print("发现问题：\n  " + "\n  ".join(c.errors))
        return 1
    print("全部字段都能在上游源码的结构体标签中找到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

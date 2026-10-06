"""国内 DNS 与路由的逐条扫描（2026-10-06 加；GPT 评审 r12 方案时提的要求）。由 tools/check_real_routes.py 调用。
r12 时叫“全集一致性”。2026-10-07 按 GPT 对 r12 的审核改名：它扫的是集合里每个条目的代表主机，不是“全部合法域名”的证明，
扫出来的个数也只是这份快照、这种取代表主机的办法下的计数，不是互联网上实际受影响的主机数。

要回答的问题：有没有哪个域名，名字会被交给国内 DNS，连接却走代理组？
（国内的解析方看到了一个最后从境外出口出去的域名——“DNS 泄露”说的就是这件事。）

以前的核对只看 tests/cases.yaml 里那几百个主机。这里把“名字会被交给国内 DNS”的集合整个拿出来，
逐条取代表主机（条目本身；后缀条目再取它的一个子域），看路由把它交给谁。再反过来，把配置里每一条域名规则的值
（和它的一个子域）也查一遍——“规则比集合条目更具体”的那种重叠，只有这样才看得到。
  sing-box：名字交给国内 DNS = DNS 规则把它的查询交给 dns-cn（要真实地址的名单、比代理规则更具体的直连规则、
            geosite-cn 里没有被“走代理组的产品域名”先接住的部分）。
  mihomo：  名字交给国内 DNS = nameserver-policy 里指向国内 DNS 的那一条（geosite:cn,private）管到它。
            设备发来的 A 查询直接给假地址、AAAA / HTTPS 回空应答（交付的原始配置），都不向上游查询；真正会去问这条策略的是
            fake-ip-filter 里的名字、其他类型的查询，以及规则判断时的解析——所以 mihomo 上的不一致比 sing-box 上的轻。
判断用的是自制模拟器加读进来的真实集合（不是成员快照里那几百条记录），所以可以查任意主机。
模拟器会不会算错：不一致的每个主机，加上按固定间隔抽出来的一批主机，由调用方另外交给官方内核实际跑一遍。
解析结果仍是假定的（tests/fixtures.yaml 的 dns；没列出的主机按境外 IP 算）：只有“没被任何域名规则接住、靠解析到的
IP 决定去向”的主机受它影响，这类主机在记录里标了 by_ip。
局限：代表主机只有“条目本身和它的一个子域”。一条规则只管某个更深的子域、而这个子域既不是集合条目也不是规则的值时，
这里看不到；正则、关键词条目取不出代表主机，只计数。手动切换策略组、客户端改写配置（例如 Clash Verge Rev 的 DNS 覆写）、
真实的解析结果，都不在这项扫描的范围里。
"""
from __future__ import annotations

import ipaddress
import os
import sys
from typing import Dict, Iterable, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import emulate  # noqa: E402

SUB = "probe-x1."                     # 后缀条目的代表子域（和 tests/test_routing.py 里用的是同一个前缀）
NOT_PROXIED = ("国内直连", "DIRECT", "REJECT", "广告拦截")


class LiveFixtures(emulate.Fixtures):
    """成员关系直接问读进来的真实集合，所以可以问任意主机（SnapshotFixtures 只有快照里记了的那些）。
    sets：{集合名: real_data.DomainSet}，名字是这一端配置里的写法（mihomo：cn；sing-box：geosite-cn）。"""

    def __init__(self, family: str, sets: dict, cn_nets: list, dns: Dict[str, str], default_ip: str):
        self.ads_on = True
        self.exception_values = set()
        self.family, self.sets, self.cn_nets = family, sets, cn_nets
        self.dns, self.default_ip = dict(dns), default_ip
        self.resolved: set = set()                   # 被拿去解析过的主机（路由结果取决于假定的解析结果）
        self._cn: Dict[str, bool] = {}

    def resolve(self, host: str) -> Optional[str]:
        self.resolved.add(host)
        return self.dns.get(host, self.default_ip)

    def site(self, name: str, host: str) -> bool:
        key = name if self.family == "mihomo" else "geosite-" + name
        if key not in self.sets:
            raise AssertionError(f"{self.family} 的配置引用了没有读进来的域名集合 {name}")
        return bool(self.sets[key].why(host))

    def geoip_match(self, code: str, ip: str) -> bool:
        if code.lower() != "cn":
            raise AssertionError(f"只读了国内 IP 段，配置引用了 {code}")
        if ip not in self._cn:
            addr = ipaddress.ip_address(ip)
            self._cn[ip] = any(addr.version == n.version and addr in n for n in self.cn_nets)
        return self._cn[ip]


def representatives(ds) -> Iterable[str]:
    """一个域名集合的代表主机：精确条目本身；后缀条目本身和它的一个子域；只含子域的后缀取一个子域。"""
    for d in sorted(ds.full):
        yield d
    for s in sorted(ds.suffix):
        yield s
        yield SUB + s
    for s in sorted(ds.subonly):
        yield SUB + s


def _with_sub(values: Iterable, suffix: bool) -> List[str]:
    out = []
    for v in values:
        out.append(v)
        if suffix:
            out.append(SUB + v)
    return out


# ---------------------------------------------------------------------------
# mihomo
# ---------------------------------------------------------------------------

class FastMihomo:
    """mihomo 规则的快速判断：只处理“在第一条会触发解析的 IP 规则之前，被域名类规则接住”的情况，其余返回 None，
    由调用方退回 tests/emulate.py 的逐条模拟。十几万个主机逐条模拟近千条规则太慢；两种算法的结果由调用方抽样互相核对。"""

    def __init__(self, rules: List[str], fx):
        self.fx = fx
        self.exact: Dict[str, tuple] = {}
        self.suffix: Dict[str, tuple] = {}
        self.keywords: List[tuple] = []
        self.geosites: List[tuple] = []
        self.first_resolving = len(rules)
        for i, line in enumerate(rules):
            parts = [x.strip() for x in line.split(",")]
            t = parts[0]
            if t == "MATCH":
                break
            payload, target, opts = parts[1], parts[2], parts[3:]
            if t == "DOMAIN":
                self.exact.setdefault(payload, (i, target))
            elif t == "DOMAIN-SUFFIX":
                self.suffix.setdefault(payload, (i, target))
            elif t == "DOMAIN-KEYWORD":
                self.keywords.append((i, payload, target))
            elif t == "GEOSITE":
                self.geosites.append((i, payload, target))
            elif t in ("IP-CIDR", "IP-CIDR6", "GEOIP"):
                if "no-resolve" not in opts:
                    self.first_resolving = min(self.first_resolving, i)
            else:
                raise ValueError(f"不认识的 mihomo 规则类型 {t}")

    def route(self, host: str) -> Optional[str]:
        best = self.exact.get(host)
        parts = host.split(".")
        for k in range(len(parts)):
            hit = self.suffix.get(".".join(parts[k:]))
            if hit and (best is None or hit[0] < best[0]):
                best = hit
        for i, kw, target in self.keywords:
            if kw in host and (best is None or i < best[0]):
                best = (i, target)
        for i, name, target in self.geosites:                # 按书写顺序
            if best is not None and i > best[0]:
                break
            if self.fx.site(name, host):
                best = (i, target)
                break
        if best is not None and best[0] < self.first_resolving:
            return best[1]
        return None


def mihomo_policy(conf: dict, host: str, sets: dict) -> Optional[List[str]]:
    """nameserver-policy 里第一条管到这个主机的策略的服务器列表（没有返回 None，表示用默认的 nameserver）。
    认三种键：geosite:甲,乙；用逗号分开的域名写法（+.后缀 = 域名和全部子域，*.后缀 = 子域，其余 = 精确）。"""
    for key, servers in conf["dns"].get("nameserver-policy", {}).items():
        servers = [servers] if isinstance(servers, str) else list(servers)
        if key.startswith("geosite:"):
            names = key[len("geosite:"):].split(",")
            for n in names:
                if n not in sets:
                    raise AssertionError(f"nameserver-policy 引用了没有读进来的域名集合 {n}")
            if any(sets[n].why(host) for n in names):
                return servers
            continue
        if ":" in key:
            raise ValueError(f"不认识的 nameserver-policy 写法 {key}")
        for pat in key.split(","):
            pat = pat.strip()
            if pat.startswith("+."):
                ok = emulate.suffix_match(host, pat[2:])
            elif pat.startswith("*."):
                ok = host.endswith(pat[1:]) and host != pat[2:]
            elif "*" in pat:
                raise ValueError(f"不认识的 nameserver-policy 域名写法 {pat}")
            else:
                ok = host == pat
            if ok:
                return servers
    return None


def mihomo_policy_sets(conf: dict, domestic: Iterable[str]) -> List[str]:
    """nameserver-policy 里指向国内 DNS 的 geosite 集合名。"""
    domestic = set(domestic)
    out = []
    for key, servers in conf["dns"].get("nameserver-policy", {}).items():
        servers = [servers] if isinstance(servers, str) else list(servers)
        if key.startswith("geosite:") and set(servers) <= domestic:
            out += key[len("geosite:"):].split(",")
    return out


def _group_defaults_mihomo(conf: dict) -> Dict[str, str]:
    return {g["name"]: (g.get("proxies") or [None])[0] for g in conf.get("proxy-groups", [])}


def sweep_mihomo(conf: dict, sets: dict, fx: LiveFixtures, domestic_servers: Iterable[str]) -> dict:
    """返回 {swept, hosts, to_domestic, consistent, default_direct, mismatch}。sets 要含规则和策略引用到的全部集合。"""
    domestic = set(domestic_servers)
    names = mihomo_policy_sets(conf, domestic)
    if not names:
        raise AssertionError("nameserver-policy 里没有指向国内 DNS 的 geosite 条目：配置的结构变了，这项核对要跟着改")
    fast = FastMihomo(conf["rules"], fx)
    defaults = _group_defaults_mihomo(conf)
    hosts: Dict[str, str] = {}                      # 主机 → 它是从哪里来的
    skipped = {"regex": 0, "keyword": 0}
    for n in names:
        ds = sets[n]
        skipped["regex"] += len(ds.regex)
        skipped["keyword"] += len(ds.keyword)
        for h in representatives(ds):
            hosts.setdefault(h, f"geosite:{n}")
    set_hosts = len(hosts)
    for line in conf["rules"]:
        parts = [x.strip() for x in line.split(",")]
        if parts[0] in ("DOMAIN", "DOMAIN-SUFFIX"):
            for h in _with_sub([parts[1]], parts[0] == "DOMAIN-SUFFIX"):
                hosts.setdefault(h, "规则的值")
    for pat in conf["dns"].get("fake-ip-filter", []):
        if not pat.startswith("geosite:"):
            for h in _with_sub([pat[2:] if pat.startswith("+.") else pat], pat.startswith("+.")):
                hosts.setdefault(h, "fake-ip-filter")
    rec = _empty_record(len(hosts), set_hosts, skipped, {n: len(sets[n]) for n in names})
    slow = 0
    for h in sorted(hosts):
        servers = mihomo_policy(conf, h, sets)
        if servers is None or not set(servers) <= domestic:
            continue
        rec["to_domestic"] += 1
        before = len(fx.resolved)
        group = fast.route(h)
        if group is None:
            slow += 1
            group = emulate.mihomo_route(conf, emulate.Conn(host=h), fx)
        _classify(rec, h, group, defaults, by_ip=len(fx.resolved) > before, via=hosts[h])
    rec["slow_path"] = slow
    return rec


# ---------------------------------------------------------------------------
# sing-box
# ---------------------------------------------------------------------------

def _group_defaults_singbox(conf: dict) -> Dict[str, str]:
    out = {}
    for o in conf["outbounds"]:
        if o["type"] == "selector":
            out[o["tag"]] = o.get("default") or (o["outbounds"] or [None])[0]
    return out


def sweep_singbox(conf: dict, sets: dict, fx: LiveFixtures, domestic_tag: str = "dns-cn") -> dict:
    defaults = _group_defaults_singbox(conf)
    hosts: Dict[str, str] = {}
    skipped = {"regex": 0, "keyword": 0}
    dns_sets = []
    for r in conf["dns"]["rules"]:
        if r.get("server") != domestic_tag:
            continue
        for tag in emulate._as_list(r.get("rule_set", [])):
            if tag not in dns_sets:
                dns_sets.append(tag)
        for h in _with_sub(r.get("domain", []), False) + _with_sub(r.get("domain_suffix", []), True):
            hosts.setdefault(h, "DNS 规则里写明交给国内 DNS 的名单")
    if not dns_sets:
        raise AssertionError("DNS 规则里没有“规则集 → dns-cn”：配置的结构变了，这项核对要跟着改")
    for tag in dns_sets:
        ds = sets[tag]
        skipped["regex"] += len(ds.regex)
        skipped["keyword"] += len(ds.keyword)
        for h in representatives(ds):
            hosts.setdefault(h, tag)
    set_hosts = len(hosts)
    for r in conf["route"]["rules"]:
        for h in _with_sub(r.get("domain", []), False) + _with_sub(r.get("domain_suffix", []), True):
            hosts.setdefault(h, "规则的值")
    rec = _empty_record(len(hosts), set_hosts, skipped, {t: len(sets[t]) for t in dns_sets})
    for h in sorted(hosts):
        a = emulate.singbox_dns(conf, h, "A", fx)
        other = emulate.singbox_dns(conf, h, "HTTPS", fx)
        if domestic_tag not in (a, other):
            continue
        rec["to_domestic"] += 1
        before = len(fx.resolved)
        group = emulate.singbox_route(conf, emulate.Conn(host=h), fx)
        _classify(rec, h, group, defaults, by_ip=len(fx.resolved) > before, via=hosts[h])
    return rec


# ---------------------------------------------------------------------------

def _empty_record(n_hosts: int, set_hosts: int, skipped: dict, set_sizes: dict) -> dict:
    return {"swept": {"hosts": n_hosts, "from_sets": set_hosts, "from_rules": n_hosts - set_hosts,
                      "sets": set_sizes, "skipped": skipped},
            "to_domestic": 0, "consistent": 0, "default_direct": [], "mismatch": [],
            "_routes": {}}                    # 名字交给国内 DNS 的每个主机 → 路由结果（只给调用方抽样用，不进快照）


def _classify(rec: dict, host: str, group: str, defaults: Dict[str, str], by_ip: bool, via: str) -> None:
    rec["_routes"][host] = group
    if group in NOT_PROXIED:
        rec["consistent"] += 1
    elif defaults.get(group) == "DIRECT":
        rec["default_direct"].append({"host": host, "route": group, "via": via})
    else:
        item = {"host": host, "route": group, "via": via}
        if by_ip:
            item["by_ip"] = True
        rec["mismatch"].append(item)


def sample(hosts: List[str], n: int) -> List[str]:
    """按固定间隔取大约 n 个（同一份输入每次取到的都一样）。"""
    hosts = sorted(hosts)
    if len(hosts) <= n:
        return hosts
    step = len(hosts) / n
    return [hosts[int(i * step)] for i in range(n)]

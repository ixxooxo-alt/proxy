#!/usr/bin/env python3
"""一次性核对（2026-10-07，r14；不参与生成和测试，结果记在 docs/08 第 9 轮“我自己查出来的”第 2 条）。

r14 把核对工具查 mihomo nameserver-policy 的办法从“按书写顺序取第一条命中”改成 mihomo 的域名树（相邻的普通域名写法
合成一棵树，越具体越优先、不看先后；tools/dns_route_consistency.py 的 DomainTrie）。这里看两件事：
  1. 这一版交付的配置上，两种办法的结果有没有不同——也就是 r13 的旧办法放到 r14 的配置上会不会算错；
  2. 把策略里普通域名写法的先后倒过来（mihomo 不看先后，结果不该变），两种办法各自变不变。
主机取每条写法本身、它的一个子域（probe-x1.）和两级子域（a.b.）；geosite: 的条目不读上游集合，一律当作没命中
（这里只比较写明的域名那一部分）。

用法（仓库根目录）：python3 handoff/notes/r14_policy_order.py > handoff/notes/r14_policy_order.out
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dns_route_consistency as drc  # noqa: E402


class NotInAnySet:
    def why(self, host):
        return None


def first_match(policy: dict, host: str):
    """r13 的旧办法（tools/dns_route_consistency.py 的 mihomo_policy，提交 bf42e8b）：按书写顺序，第一条管到的。"""
    for key, servers in policy.items():
        if key.startswith("geosite:"):
            continue
        for pat in key.split(","):
            pat = pat.strip()
            if pat.startswith("+."):
                ok = host == pat[2:] or host.endswith(pat[1:])
            elif pat.startswith("*."):
                ok = host.endswith(pat[1:]) and host != pat[2:]
            elif "*" in pat:
                raise ValueError(pat)
            else:
                ok = host == pat
            if ok:
                return servers
    return None


def compare(policy: dict, hosts):
    conf = {"dns": {"nameserver-policy": policy}}
    sets = {"cn": NotInAnySet(), "private": NotInAnySet()}
    out = []
    for h in hosts:
        t, f = drc.mihomo_policy(conf, h, sets), first_match(policy, h)
        if t != f:
            out.append((h, t, f))
    return out


def label(servers, foreign, domestic):
    if servers is None:
        return "默认（nameserver）"
    return {tuple(foreign): "境外", tuple(domestic): "国内", ("system",): "system"}.get(tuple(servers), str(servers))


def main():
    path = os.path.join(ROOT, "dist", "mihomo", "mihomo-core.yaml")
    conf = yaml.safe_load(open(path, encoding="utf-8"))
    head = next(l for l in open(path, encoding="utf-8") if "统一源版本" in l).strip().lstrip("# ")
    policy = conf["dns"]["nameserver-policy"]
    foreign, domestic = conf["dns"]["nameserver"], policy["geosite:cn,private"]
    plain = [k for k in policy if not k.startswith("geosite:")]
    pats = [p.strip() for k in plain for p in k.split(",")]
    hosts = set()
    for p in pats:
        b = p[2:] if p.startswith(("+.", "*.")) else p
        hosts.update({b, "probe-x1." + b, "a.b." + b})
    hosts = sorted(hosts)
    print(f"配置：dist/mihomo/mihomo-core.yaml（{head.split('；')[0]}）")
    print(f"nameserver-policy：{len(policy)} 个键，普通域名写法 {len(pats)} 条；比较的主机 {len(hosts)} 个")

    diff = compare(policy, hosts)
    print(f"\n1. 交付的书写顺序：域名树和“第一条命中”结果不同的主机 {len(diff)} 个")
    for h, t, f in diff[:10]:
        print(f"    {h}：域名树 {label(t, foreign, domestic)}，第一条命中 {label(f, foreign, domestic)}")

    rev = {k: policy[k] for k in reversed(plain)}
    rev.update({k: v for k, v in policy.items() if k.startswith("geosite:")})
    conf_now, conf_rev = {"dns": {"nameserver-policy": policy}}, {"dns": {"nameserver-policy": rev}}
    sets = {"cn": NotInAnySet(), "private": NotInAnySet()}
    trie_moved = [h for h in hosts if drc.mihomo_policy(conf_now, h, sets) != drc.mihomo_policy(conf_rev, h, sets)]
    first_moved = [h for h in hosts if first_match(policy, h) != first_match(rev, h)]
    print(f"\n2. 把普通域名写法的先后倒过来：域名树的结果变了的 {len(trie_moved)} 个；“第一条命中”的结果变了的 {len(first_moved)} 个")
    for h in first_moved[:10]:
        print(f"    {h}：倒过来以前 {label(first_match(policy, h), foreign, domestic)}，倒过来以后 {label(first_match(rev, h), foreign, domestic)}")
    print("\n说明：mihomo 不看这些写法的先后（v1.19.31 dns/resolver.go 的 makePolicy、component/trie/domain.go；读源码得到）。")


if __name__ == "__main__":
    main()

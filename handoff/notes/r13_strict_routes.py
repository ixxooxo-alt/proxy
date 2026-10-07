#!/usr/bin/env python3
"""一次性核对（2026-10-07，处理 GPT 对 r13 的审核 R13-F03 时做的；不参与生成和测试，结果记在 docs/08 第 9 轮）。

r13 写进 docs/03、docs/06 第 19 项的“105,446 条（94.8%）只在 Loon 严格版直连、Quantumult X 严格版走代理”，
来自 handoff/notes/qx_strict_coverage.py：它只扣掉了自有国内清单和 Quantumult X 本地域名规则接得住的条目，
没有扣两端都排在国内清单之前的远程广告集合——所以那个数是“这两样都没接住的条目数”，不是两端实际分流不同的条目数。

这里按两份严格版的完整顺序，把 Loon 严格版订阅的上游国内域名集合（blackmatrix7 ChinaMax_Domain.list，按登记的快照）
里的每一条各走一遍（域名规则部分；两份严格版的 IP 规则都不为域名解析，到不了）：
  Loon 严格版：本地域名规则（按书写顺序） → 远程规则按书写顺序：两个广告集合 → ChinaMax → 自有清单 → FINAL
  Quantumult X 严格版：本地域名规则 → 远程规则按书写顺序：广告集合 → 自有清单 → 域名兜底（HOST-KEYWORD,.）
每一条的代表主机就是条目本身（“.x.com”这种后缀条目取 x.com），和 r13 那个脚本相同；另外给后缀条目各取一个子域
（probe-x1.x.com）再算一遍，看结论是否一样。规则顺序的依据和模拟器（tests/emulate.py）相同，是按官方文档的推断，不是 App 实测。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r13_strict_routes.py > handoff/notes/r13_strict_routes.out
"""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import emulate  # noqa: E402
import real_data as rd  # noqa: E402


def parents(h):
    parts = h.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


class Ordered:
    """按书写顺序取第一条命中的域名规则：精确、后缀查表，关键词逐个看；返回 (序号, 策略) 或 None。"""

    def __init__(self, rules):
        self.exact, self.suffix, self.keyword = {}, {}, []
        for i, (t, v, policy) in enumerate(rules):
            if t == "DOMAIN":
                self.exact.setdefault(v, (i, policy))
            elif t == "DOMAIN-SUFFIX":
                self.suffix.setdefault(v, (i, policy))
            elif t == "DOMAIN-KEYWORD":
                self.keyword.append((i, v, policy))

    def first(self, h):
        hits = [self.exact[h]] if h in self.exact else []
        hits += [self.suffix[p] for p in parents(h) if p in self.suffix]
        hits += [(i, policy) for i, v, policy in self.keyword if v in h]
        return min(hits) if hits else None


def local_rules(conf, norm):
    out = []
    for p in conf["local"]:
        t = norm(p[0])
        if t in emulate.LOON_DOMAIN:
            out.append((t, p[1].lower(), p[2]))
    return out


def remote_chain(conf, bm7_dir):
    """远程规则按书写顺序 → [(说明, 查找函数, 策略)]。"""
    chain = []
    for r in conf["remote"]:
        if str(r.get("enabled", "true")).strip() != "true":
            continue
        own = emulate._own_list(r["url"])
        if own is not None:
            od = Ordered([(t, v, r["policy"]) for t, v in own])
            chain.append((r["url"].rsplit("/", 1)[-1], (lambda od: lambda h: od.first(h) is not None)(od), r["policy"]))
        else:
            rl = rd.read_rule_list(rd.bm7_local_path(bm7_dir, r["url"]))
            chain.append((r["url"].rsplit("/", 1)[-1], (lambda rl: lambda h: bool(rl.host_hits(h)))(rl), r["policy"]))
    return chain


def route(h, local, chain, final):
    hit = local.first(h)
    if hit:
        return hit[1], "本地规则"
    for name, look, policy in chain:
        if look(h):
            return policy, name
    return final, "FINAL"


def main():
    bm7 = os.environ["BM7_SRC"]
    base = "https://raw.githubusercontent.com/ixxooxo-alt/proxy/main/dist/"
    files = {}
    for rel in ("loon/rules/cn-domains.list", "quantumultx/rules/cn-domains.list", "quantumultx/rules/domain-fallback.list"):
        with open(os.path.join(ROOT, "dist", rel), encoding="utf-8") as f:
            files[base + rel] = f.read()
    emulate.register_own_lists(base, files)
    loon = emulate.parse_loon(open(os.path.join(ROOT, "dist/loon/loon-strict.conf"), encoding="utf-8").read())
    qx = emulate.parse_qx(open(os.path.join(ROOT, "dist/quantumultx/quantumultx-strict.conf"), encoding="utf-8").read())
    loon_local = Ordered(local_rules(loon, lambda t: t))
    qx_local = Ordered(local_rules(qx, lambda t: emulate.QX_NORM.get(t, t)))
    loon_chain, qx_chain = remote_chain(loon, bm7), remote_chain(qx, bm7)
    qx_final = {"direct": "DIRECT", "reject": "REJECT"}.get(qx["final"], qx["final"])
    cm_url = next(r["url"] for r in loon["remote"] if "ChinaMax" in r["url"])
    cm = rd.read_rule_list(rd.bm7_local_path(bm7, cm_url))
    entries = [(d, True) for d in sorted(cm.domains.suffix)] + [(d, False) for d in sorted(cm.domains.full)]
    print(f"Loon 严格版订阅的上游国内域名集合：{cm_url.rsplit('/', 1)[-1]}（blackmatrix7 快照 {os.environ.get('BM7_ORIGIN', bm7)}）")
    print(f"条目 {len(entries)} 条（后缀 {len(cm.domains.suffix)}，精确 {len(cm.domains.full)}，关键词 {len(cm.domains.keyword)}）")
    print("Loon 严格版远程规则顺序：" + " → ".join(n for n, _, _ in loon_chain) + f" → FINAL {loon['final']}")
    print("Quantumult X 严格版远程规则顺序：" + " → ".join(n for n, _, _ in qx_chain) + f" → final {qx_final}")
    for label, sub in (("代表主机 = 条目本身", False), ("后缀条目改用一个子域（probe-x1.条目）", True)):
        pairs = collections.Counter()
        why = collections.Counter()
        examples = collections.defaultdict(list)
        for d, is_suffix in entries:
            h = f"probe-x1.{d}" if (sub and is_suffix) else d
            lr, lw = route(h, loon_local, loon_chain, loon["final"])
            qr, qw = route(h, qx_local, qx_chain, qx_final)
            pairs[(lr, qr)] += 1
            why[(lw, qw)] += 1
            if len(examples[(lr, qr)]) < 6:
                examples[(lr, qr)].append(h)
        print(f"\n{label}：两端各自交给哪个组（Loon 严格版 / Quantumult X 严格版）")
        for (lr, qr), n in pairs.most_common():
            print(f"  {lr} / {qr}：{n} 条（{100 * n / len(entries):.2f}%）　例：{'、'.join(examples[(lr, qr)][:4])}")
        print("  按命中的那一层分（Loon / Quantumult X）：")
        for (lw, qw), n in why.most_common(8):
            print(f"    {lw} / {qw}：{n} 条")
    print("\n说明：只看域名规则；规则顺序按 tests/emulate.py（依据官方文档的推断）。“国外默认”是策略组，默认走代理。")


if __name__ == "__main__":
    main()

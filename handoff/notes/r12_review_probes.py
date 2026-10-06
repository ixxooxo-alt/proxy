#!/usr/bin/env python3
"""一次性核对（2026-10-07，处理 GPT 对 r12 的审核时做的；不参与生成和测试，结果记在 docs/08 第 8 轮）。

用官方 mihomo v1.19.31 和这份工程生成的配置：
  A. 复现审核报告第二节第 7 条：6 个节点服务器名字分别交给哪一类 DNS 解析；
  B. 复现第二节第 8 条：快照里归为 product_cn 的主机（逐条扫描——r12 时叫“全集一致性”——查出来的第三类，待决事项 16），
     A / AAAA / HTTPS 查询各一次，内核怎么回、有没有替身收到；再加 qwen.ai 的 TXT；
  C. 审核报告第三节第 4 点说的 Clash Verge Rev 开虚拟网卡时的情形：v2.5.7 enhance/tun.rs 第 34–48 行在 fake-ip 模式下
     把 dns.ipv6 设成顶层的 ipv6（App 的 IPv6 开关，模板默认开），并在没有 fake-ip-range6 时补上 2001:2::0/64。
     用托管版配置（mihomo-profile.yaml）照这两处改，同一批主机的 AAAA / HTTPS 查询再各一次，另加几个对照名字。
     mihomo 只有在本机有公网 IPv6 地址时才保留 fake-ip-range6（config/config.go 的 parseIPV6、config/utils.go 的
     verifyIP6），所以分两遍：带内核认的环境变量 SKIP_SYSTEM_IPV6_CHECK=1（当作有 IPv6 的机器）、不带（这台机器的实际情况）。
做法与 tools/check_real_routes.py 的 mihomo_dial_probe 相同：系统 / 国内 / 境外三类 DNS 各换成一个本机替身，
看“这个名字被哪一类替身收到过”，内核没有向上游查询时看它自己回了什么。不联网。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r12_review_probes.py > handoff/notes/r12_review_probes.out

r12_review_probes.before-fix.out 是同一个脚本在修 tools/check_real_routes.py 之前跑的输出（当时那里只读 A 记录、
没有 A 记录就算“空应答”）：C 两遍都报 AAAA 空应答 142 个，假的 IPv6 地址被看漏了——这就是那个缺陷。只截了脚本的标准输出。
"""
import ipaddress
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import build as builder  # noqa: E402
import check_real_routes as crr  # noqa: E402
from generator.model import build_plan, load, most_specific  # noqa: E402

NOT_PROXIED = {"国内直连", "DIRECT", "广告拦截"}          # 与 tests/test_real_data.py 相同
CVR_RANGE6 = "2001:2::0/64"                               # Clash Verge Rev v2.5.7 补的那一段


def main():
    binary, geodata = os.environ["MIHOMO_BIN"], os.environ["GEODATA_DIR"]
    model = load(ROOT, include_local=False)
    plan = build_plan(model)
    files = builder.render_public(model, plan)
    core, profile = files["mihomo/mihomo-core.yaml"], files["mihomo/mihomo-profile.yaml"]
    print(f"统一源 {model.project['project']['source_version']}；mihomo：{os.path.basename(binary)}；"
          f"geodata：{os.environ.get('GEODATA_ORIGIN', geodata)}")
    print()

    # ---- A. 节点服务器名字 ----
    names = [("auditnode", "system"), ("auditnode.lan", "system"), ("auditnode.local", "system"),
             ("auditnode.home.arpa", "system"), ("auditnode.lan.example.com", "domestic"), ("auditnode.public.net", "domestic")]
    cases = [{"kind": "node", "server": n, "expect": e} for n, e in names]
    dial, _ = crr.mihomo_dial_probe(binary, geodata, model, core, cases)
    print("A. 节点的服务器地址交给哪一类 DNS（审核报告第二节第 7 条；期望是按审核方写的结果抄的）")
    bad = 0
    for n, e in names:
        got = dial[f"node {n}"]
        bad += got != e
        print(f"  {n:28} 期望 {e:9} 实际 {got}{'' if got == e else '  ← 不同'}")
    print(f"  {len(names) - bad}/{len(names)} 与审核方的结果相同")
    print()

    # ---- B. product_cn 的主机，交付的原始配置 ----
    snap = json.load(open(os.path.join(ROOT, "tests/data/real_sets.json"), encoding="utf-8"))
    mismatch = snap["consistency"]["mihomo"]["mismatch"]
    product_cn = []
    for item in mismatch:
        if item["via"] == "geosite:private":
            continue
        rule = most_specific(plan.exceptions + plan.product_for("mihomo"), item["host"])
        if rule is not None and rule.target == item["route"] and item["route"] not in NOT_PROXIED:
            product_cn.append(item["host"])
    product_cn = sorted(set(product_cn))
    print(f"B. 快照里 mihomo 的不一致共 {len(mismatch)} 个，按 tests/test_real_data.py 的归类，product_cn {len(product_cn)} 个。"
          "交付的原始配置（mihomo-core.yaml；它和 mihomo-profile.yaml 的 dns 段相同），每个主机 A / AAAA / HTTPS 各查一次：")
    for qtype in ("A", "AAAA", "HTTPS"):
        _, got = crr.mihomo_dial_probe(binary, geodata, model, core, [], [{"host": h, "type": qtype} for h in product_cn])
        tally = {}
        for h in product_cn:
            tally.setdefault(got[(h, qtype)], []).append(h)
        print(f"  {qtype:5}：" + "；".join(f"{k} {len(v)} 个" for k, v in sorted(tally.items())))
    _, got = crr.mihomo_dial_probe(binary, geodata, model, core, [], [{"host": "qwen.ai", "type": "TXT"}])
    print(f"  qwen.ai 的 TXT：{got[('qwen.ai', 'TXT')]}（收到查询的替身）")
    print()

    # ---- C. Clash Verge Rev 开虚拟网卡、App 的 IPv6 开关开着 ----
    conf = yaml.safe_load(profile)
    assert conf.get("ipv6") is True and conf["dns"]["ipv6"] is False and "fake-ip-range6" not in conf["dns"]
    conf["dns"]["ipv6"] = True                    # tun.rs 第 36 行：dns.ipv6 = 顶层 ipv6（App 的开关；这里按默认的开）
    conf["dns"]["fake-ip-range6"] = CVR_RANGE6    # tun.rs 第 46–48 行
    cvr = yaml.safe_dump(conf, allow_unicode=True, sort_keys=False, width=100000)
    crr.MIHOMO_DNS_OTHER = crr.MIHOMO_DNS_OTHER + ("fake-ip-range6",)   # 这个字段里没有 DNS 服务器，不用换替身
    fake6 = ipaddress.ip_network(CVR_RANGE6, strict=False)
    controls = [("printer.lan", "AAAA"), ("time.apple.com", "AAAA"), ("www.qq.com", "AAAA"), ("chatgpt.com", "AAAA")]

    def label(where):
        if where.startswith("answer:"):
            ips = [ipaddress.ip_address(x) for x in where[len("answer:"):].split(",")]
            if all(ip.version == 6 and ip in fake6 for ip in ips):
                return f"假 IPv6 地址（{CVR_RANGE6} 里的）"
        return where

    for skip in ("1", None):
        if skip:
            os.environ["SKIP_SYSTEM_IPV6_CHECK"] = skip
            title = "带 SKIP_SYSTEM_IPV6_CHECK=1（当作这台机器有公网 IPv6 地址）"
        else:
            os.environ.pop("SKIP_SYSTEM_IPV6_CHECK", None)
            title = "不带（这台机器的实际情况：没有公网 IPv6 地址时内核丢掉 fake-ip-range6）"
        print(f"C. 托管版配置照 Clash Verge Rev v2.5.7 开虚拟网卡时的改法改两处（dns.ipv6: true、fake-ip-range6: {CVR_RANGE6}），{title}：")
        for qtype in ("AAAA", "HTTPS"):
            _, got = crr.mihomo_dial_probe(binary, geodata, model, cvr, [], [{"host": h, "type": qtype} for h in product_cn])
            tally = {}
            for h in product_cn:
                tally.setdefault(label(got[(h, qtype)]), []).append(h)
            print(f"  product_cn {len(product_cn)} 个，{qtype:5}：" + "；".join(f"{k} {len(v)} 个" for k, v in sorted(tally.items())))
        _, got = crr.mihomo_dial_probe(binary, geodata, model, cvr, [], [{"host": h, "type": t} for h, t in controls])
        print("  对照：" + "；".join(f"{h} {t} → {label(got[(h, t)])}" for h, t in controls))
        print()
    print("结果的含义：system / domestic / foreign = 收到这个名字的查询的是哪一类替身；fake-ip = 内核直接给了假的 IPv4 地址；"
          "empty = 内核直接回了没有记录的正常应答；都没有向上游查询。")


if __name__ == "__main__":
    main()

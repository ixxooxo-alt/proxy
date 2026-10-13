#!/usr/bin/env python3
"""一次性核对（2026-10-13，处理 GPT 对 r14 的审核时做的；不参与生成和测试，结果记在 docs/08 第 10 轮）。

审核报告 R14-F01 说：待决事项第 21 项把“现在这份配置做不到”说成了“mihomo 做不到”。mihomo 的直连出口解析目标时用
direct-nameserver 那个解析器（关掉 direct-nameserver-follow-policy 时不看 nameserver-policy），走代理的 UDP、WireGuard
出口用默认解析器（看 nameserver-policy）——两条路本来就是分开的。只要 direct-nameserver 指向一台既认得局域网名字、又把
国内网站交给国内 DNS 的路由器 DNS，再把 Apple、Bilibili 港澳台这几个组的名字放进“交给境外 DNS”那一层，就能做到：组选
直连时由路由器解析，切到国外时由境外 DNS 解析。

这里用官方内核把两份配置各跑一遍，看系统 / 国内 / 境外三类 DNS 替身各收到了谁的查询（做法同 tools/check_real_routes.py 的
mihomo_outbound_probe：规则原样，三类 DNS 换成本机替身，测试节点连本机一个没人监听的端口）：

  现在的配置（r14）：默认直连的组保持直连；再把 Apple、Apple Music/TV、Apple Push、Bilibili 港澳台切到测试节点
                    （第 21 项说的“切到国外”）。
  审核方的做法：     direct-nameserver 改成 [system]、direct-nameserver-follow-policy 改成 false，nameserver-policy 里把
                    www.apple.com.cn、api.bilibili.com 交给境外 DNS（审核方的复现脚本也只加了这两个名字）；同样试“保持直连”
                    和“切到测试节点”两种。这里的 system 替身代表“认得局域网名字、把国内网站交给国内 DNS 的路由器”——
                    它只是本机的一个替身，不能说明哪台真实路由器做得到。
  出口和流量：       WireGuard 走 TCP、SOCKS5 走 UDP（两种都会在本机解析目标）。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r14_review_probes.py > handoff/notes/r14_review_probes.out
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import check_real_routes as crr  # noqa: E402
from generator.model import load  # noqa: E402

HOSTS = ["www.apple.com.cn", "api.bilibili.com", "www.qq.com", "router.lan", "qwen.ai"]
SWITCHABLE = ["Apple", "Apple Music/TV", "Apple Push", "Bilibili 港澳台"]


def variant(text: str, model, router_dns: bool, switched: bool) -> str:
    conf = yaml.safe_load(text)
    if router_dns:
        d = conf["dns"]
        d["direct-nameserver-follow-policy"] = False
        d["direct-nameserver"] = ["system"]
        pol = {}
        for k, v in d["nameserver-policy"].items():
            if k == "geosite:private":           # 普通域名写法要和前面那一串连在一起，才在同一棵域名树里
                for h in HOSTS[:2]:
                    pol[h] = list(model.dns["foreign_doh"])
            pol[k] = v
        d["nameserver-policy"] = pol
    if switched:
        for g in conf["proxy-groups"]:
            if g["name"] in SWITCHABLE:
                g["proxies"] = ["国外默认"]          # 第一项不是 DIRECT，探针就把它换成测试节点
    return yaml.safe_dump(conf, allow_unicode=True, sort_keys=False, width=100000)


SOURCE_VERSION = yaml.safe_load(open(os.path.join(ROOT, "dist", "manifest.json"), encoding="utf-8"))["source_version"]


def main() -> int:
    binary, geodata = os.environ["MIHOMO_BIN"], os.environ["GEODATA_DIR"]
    model = load(ROOT, include_local=False)
    text = open(os.path.join(ROOT, "dist", "mihomo", "mihomo-core.yaml"), encoding="utf-8").read()
    ver = os.popen(f"{binary} -v").read().strip().splitlines()[0]
    print(f"mihomo：{ver}；配置：dist/mihomo/mihomo-core.yaml（统一源 {SOURCE_VERSION}）")
    print("结果：收到这个名字查询的 DNS 替身（system = 代表路由器的替身，domestic = 国内，foreign = 境外；none = 三类都没有收到）")
    for title, router_dns in (("现在的配置（r14）", False), ("审核方的做法（direct-nameserver: [system]，follow-policy: false）", True)):
        print()
        print(f"== {title}")
        for switched in (False, True):
            for outbound, transport in (("wireguard", "tcp"), ("socks5", "udp")):
                res = crr.mihomo_outbound_probe(binary, geodata, model, variant(text, model, router_dns, switched),
                                                HOSTS, outbound, transport)
                state = "Apple / Bilibili 港澳台切到测试节点" if switched else "默认直连的组保持直连"
                print(f"  {state:<26}{outbound} {transport.upper()}：" + "，".join(f"{h} → {res[h]}" for h in HOSTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

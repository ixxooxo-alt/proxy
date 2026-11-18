"""r22 的一次性核对（2026-11-18，不属于 tools/run_checks.sh）：带本地补充和节点生成的私密产物，相对 r21b 只变了这一版有意改的地方吗？

做法和 handoff/notes/r21_private_vs_r20.py 相同：把两个工程的 build.py、generator/、source/ 各复制到临时目录，配上同一份虚构的
source/local.yaml（tests/local_overlay_sample.yaml 里的节点名补充，再加一个固定节点和一条额外服务）、同一个虚构的订阅地址、同一批虚构节点
（这一版的 tests/node_samples.yaml——比 r21b 多了全项目复核 F01–F03 的四个样例——再加一个叫“境外DNS”的 Shadowsocks 节点），
各跑一次 build.py --singbox-nodes，比 dist/private/ 里的每一份文件。
允许的差别（别的差别都算不符，退出码非 0）：
  1. 每一份配置只多出 GitHub Copilot 那 7 个主机（全项目复核 F04）：Loon、Quantumult X、mihomo、Stash 去掉 # 开头的注释行以后逐行比，
     只多不少，多出来的每一行都含这 7 个主机之一、7 个都出现；sing-box 把新配置里这 7 个主机从所有列表里拿掉以后，其余部分和旧的一致（2 除外）。
  2. sing-box 的节点（F01–F03）：“新加坡 Trojan 写了 tls false”有了 TLS（enabled、server_name）；两个 packet 写法的节点 packet_encoding
     由 packet 变成 packetaddr；“美国 HTTPS 布尔写成字符串”不再转换，出站和各组成员里都没有它。同时核对旧配置里确实是错的样子
     （Trojan 没有 TLS、packet 原样、那个 HTTPS 节点带着 insecure: true）——证明两边吃的是同一批输入，r21b 确实有这几个问题。
  3. sing-box-节点转换报告.txt：只有第一行的计数变了，另外多一行跳过（布尔写法）、多一行提示（Trojan 写了 tls: false）。
  4. 私密产物里的 manifest.json 整份不比（版本、摘要，以及这一版新加的 not_refreshed）。其余文件逐字节相同。
不联网，不读、不写仓库里的 source/local.yaml。
用法：python3 -B r22_private_vs_r21b.py <r21b 工程目录> <当前工程目录> <临时输出目录>（相对路径也可以，先转成绝对路径）"""
import json
import os
import shutil
import subprocess
import sys
from collections import Counter

import yaml

old, new, out = (os.path.abspath(x) for x in sys.argv[1:4])
# GitHub 官方 Copilot 放行清单列出的 7 个（docs/04 的 ghcopilot-net）；这里照抄一份，不从规则源读，免得两边一起错
HOSTS = ["production-copilot-host.webpubsub.azure.com", "production-copilot-host-centralus.webpubsub.azure.com",
         "production-copilot-host-centralus-02.webpubsub.azure.com", "production-copilot-host-eastasia.webpubsub.azure.com",
         "production-copilot-host-austriaeast.webpubsub.azure.com", "production-copilot-host-westus.webpubsub.azure.com",
         "production-copilot-host-westus3.webpubsub.azure.com"]
TROJAN, PACKET, DROPPED = "新加坡 Trojan 写了 tls false", ("美国 VMess packet", "日本 VLESS packet"), "美国 HTTPS 布尔写成字符串"

nodes = yaml.safe_load(open(os.path.join(new, "tests", "node_samples.yaml"), encoding="utf-8"))
names_in_samples = {p["name"] for p in nodes["proxies"]}
assert {TROJAN, DROPPED, *PACKET} <= names_in_samples, "样例节点里应当有全项目复核加的那四个"
nodes["proxies"].append({"name": "境外DNS", "type": "ss", "server": "dns-node.example.net", "port": 443,
                         "cipher": "aes-128-gcm", "password": "not-a-real-password", "udp": True})
raw = yaml.safe_load(open(os.path.join(new, "tests", "local_overlay_sample.yaml"), encoding="utf-8"))
overlay = yaml.safe_dump({"node_names": raw["node_names"],
                          "special_entries": {"paypal_fixed": {"pinned_node_name": "美国 Trojan WS ed"}},
                          "extra_services": [{"id": "corp", "group": "DIRECT", "title": "公司内网（虚构）",
                                              "rules": [{"suffix": "corp.example.com", "ev": "corp-note"}]}],
                          "evidence": {"corp-note": {"kind": "maintainer", "note": "虚构的内网域名"}}},
                         allow_unicode=True, sort_keys=False)
env = {**os.environ, "SUB_URLS": "https://sub.example.invalid/fake-subscription"}
res = {}
for label, root in (("r21b", old), ("当前", new)):
    d = os.path.join(out, label)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for x in ("source", "generator"):
        shutil.copytree(os.path.join(root, x), os.path.join(d, x), ignore=shutil.ignore_patterns("__pycache__", "local.yaml"))
    shutil.copy(os.path.join(root, "build.py"), d)
    with open(os.path.join(d, "source", "local.yaml"), "w", encoding="utf-8") as f:
        f.write(overlay)
    nf = os.path.join(d, "nodes.yaml")
    with open(nf, "w", encoding="utf-8") as f:
        yaml.safe_dump(nodes, f, allow_unicode=True, sort_keys=False)
    p = subprocess.run([sys.executable, "-B", "build.py", "--out", os.path.join(d, "dist"), "--singbox-nodes", nf],
                       cwd=d, env=env, capture_output=True, text=True)
    print(f"{label}：build.py 退出码 {p.returncode}")
    if p.returncode != 0:
        print(p.stdout[-1000:], p.stderr[-1000:])
        sys.exit(1)
    res[label] = os.path.join(d, "dist", "private")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_hosts(x):
    if isinstance(x, dict):
        return {k: strip_hosts(v) for k, v in x.items()}
    if isinstance(x, list):
        return [strip_hosts(v) for v in x if not (isinstance(v, str) and v in HOSTS)]
    return x


def count_hosts(x):
    if isinstance(x, dict):
        return sum(count_hosts(v) for v in x.values())
    if isinstance(x, list):
        return sum(count_hosts(v) for v in x)
    return 1 if isinstance(x, str) and x in HOSTS else 0


def old_with_intended_node_changes(conf, problems, n):
    """把旧的 sing-box 配置照这一版有意的节点改动改一遍；顺便确认旧的确实是错的样子。"""
    seen = set()
    obs = []
    for o in conf["outbounds"]:
        tag = o.get("tag")
        if tag == DROPPED:
            seen.add(tag)
            if not (isinstance(o.get("tls"), dict) and o["tls"].get("insecure") is True):
                problems.append(f"{n}：旧配置里 {DROPPED} 没有 insecure: true，和预期的错误不一样")
            continue
        o = dict(o)
        if tag == TROJAN:
            seen.add(tag)
            if o.get("tls"):
                problems.append(f"{n}：旧配置里 {TROJAN} 已经有 TLS，和预期的错误不一样")
            o["tls"] = {"enabled": True, "server_name": "sg2.example.net"}
        if tag in PACKET:
            seen.add(tag)
            if o.get("packet_encoding") != "packet":
                problems.append(f"{n}：旧配置里 {tag} 的 packet_encoding 是 {o.get('packet_encoding')!r}，不是预期的 packet")
            o["packet_encoding"] = "packetaddr"
        if isinstance(o.get("outbounds"), list):
            o["outbounds"] = [t for t in o["outbounds"] if t != DROPPED]
        obs.append(o)
    if seen != {TROJAN, DROPPED, *PACKET}:
        problems.append(f"{n}：旧配置里没找到 {sorted({TROJAN, DROPPED, *PACKET} - seen)}")
    conf["outbounds"] = obs
    return conf


names = sorted(set(os.listdir(res["r21b"])) | set(os.listdir(res["当前"])))
print("私密产物：" + "、".join(names))
bad = []
for n in names:
    a, b = os.path.join(res["r21b"], n), os.path.join(res["当前"], n)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"{n}：只在一边有")
        continue
    same_bytes = open(a, "rb").read() == open(b, "rb").read()
    if n == "manifest.json":
        print(f"\n{n}：整份不比（{'逐字节相同' if same_bytes else '不同'}）")
        continue
    problems = []
    if n.endswith((".conf", ".yaml")):
        lines = {k: Counter(x for x in read(p).split("\n") if not x.lstrip().startswith("#")) for k, p in (("a", a), ("b", b))}
        removed, added = lines["a"] - lines["b"], lines["b"] - lines["a"]
        if removed:
            problems.append(f"{n}：少了 {sum(removed.values())} 行，例如 {next(iter(removed))!r}")
        stray = [x for x in added if not any(h in x for h in HOSTS)]
        if stray:
            problems.append(f"{n}：多出来的行里有和那 7 个主机无关的，例如 {stray[0]!r}")
        missing = [h for h in HOSTS if not any(h in x for x in added)]
        if missing:
            problems.append(f"{n}：没有多出 {missing}")
        what = f"去掉注释以后多了 {sum(added.values())} 行（都含那 7 个主机）、少了 {sum(removed.values())} 行"
    elif n.startswith("sing-box-") and n.endswith(".json"):
        ca, cb = json.load(open(a, encoding="utf-8")), json.load(open(b, encoding="utf-8"))
        hosts_new, hosts_old = count_hosts(cb), count_hosts(ca)
        if hosts_old:
            problems.append(f"{n}：旧配置里已经有那 7 个主机（{hosts_old} 处）")
        if strip_hosts(cb) != old_with_intended_node_changes(ca, problems, n):
            problems.append(f"{n}：去掉那 7 个主机、照预期改了节点以后，仍和旧的不同")
        tags = [o["tag"] for o in cb["outbounds"]]
        if DROPPED in tags or any(DROPPED in (o.get("outbounds") or []) for o in cb["outbounds"]):
            problems.append(f"{n}：新配置里还有 {DROPPED}")
        what = f"那 7 个主机出现 {hosts_new} 次；节点照预期改了 {len({TROJAN, *PACKET})} 个、去掉 1 个"
    elif n == "sing-box-节点转换报告.txt":
        la, lb = Counter(read(a).split("\n")), Counter(read(b).split("\n"))
        removed, added = sorted((la - lb).elements()), sorted((lb - la).elements())
        want_added = [x for x in added if x.startswith(f"跳过 {DROPPED}（http）：skip-cert-verify 应该是 true / false")
                      or x.startswith(f"提示 {TROJAN}（trojan）：订阅里写了 tls: false，但 Trojan 只能走 TLS")]
        first_old, first_new = read(a).split("\n")[0], read(b).split("\n")[0]
        if removed != [first_old] or sorted(added) != sorted([first_new] + want_added) or len(want_added) != 2:
            problems.append(f"{n}：少了 {removed}，多了 {added}")
        what = f"第一行 {first_old!r} → {first_new!r}；多了跳过一行、提示一行"
    else:
        if not same_bytes:
            problems.append(f"{n}：应当逐字节相同")
        what = "逐字节相同" if same_bytes else "不同"
    print(f"\n{n}：{what}")
    for x in problems:
        print("    " + x)
    bad += problems
print()
if bad:
    print(f"不符 {len(bad)} 处（见上）")
    sys.exit(1)
print(f"全部符合：{len(names)} 份私密产物里，除了 manifest.json，只有这一版有意改的地方不同")

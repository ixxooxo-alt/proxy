"""R20-F02 的复现和同一类自查（2026-10-23，一次性核对，不属于 tools/run_checks.sh）：
加了简易版以后，完整版的私密产物（带订阅、本地补充、节点生成的那些）还和 r19 一样吗？

做法：把几个工程的 build.py、generator/、source/ 各复制到临时目录，配上同一份 source/local.yaml（tests/local_overlay_sample.yaml
里的节点名补充，再加一个固定节点和一条额外服务）、同一个虚构的订阅地址、同一批虚构节点（tests/node_samples.yaml 再加一个
叫“境外DNS”的 Shadowsocks 节点，服务器和密码都是虚构的），各跑一次 build.py --singbox-nodes，逐字节比 dist/private/ 里的
完整版文件。工程依次是：r19（基线）、简易版送审稿 4d3349d（审核时的代码）、当前工程。不联网，不读、不写仓库里的 source/local.yaml。
用法：python3 -B r20_full_private_same.py <r19 工程目录> <送审稿工程目录> <当前工程目录> <临时输出目录>"""
import filecmp
import os
import shutil
import subprocess
import sys

import yaml

old, draft, new, out = sys.argv[1:5]
nodes = yaml.safe_load(open(os.path.join(new, "tests", "node_samples.yaml"), encoding="utf-8"))
nodes["proxies"].append({"name": "境外DNS", "type": "ss", "server": "dns-node.example.net", "port": 443,
                         "cipher": "aes-128-gcm", "password": "not-a-real-password", "udp": True})
raw = yaml.safe_load(open(os.path.join(new, "tests", "local_overlay_sample.yaml"), encoding="utf-8"))
# 样例里的 expect 是给测试用的期望，不是 local.yaml 的字段；另外加一个固定节点和一项额外服务，让私密产物里的覆盖都用上
overlay = yaml.safe_dump({"node_names": raw["node_names"],
                          "special_entries": {"paypal_fixed": {"pinned_node_name": "美国 Trojan WS ed"}},
                          "extra_services": [{"id": "corp", "group": "DIRECT", "title": "公司内网（虚构）",
                                              "rules": [{"suffix": "corp.example.com", "ev": "corp-note"}]}],
                          "evidence": {"corp-note": {"kind": "maintainer", "note": "虚构的内网域名"}}},
                         allow_unicode=True, sort_keys=False)
env = {**os.environ, "SUB_URLS": "https://sub.example.invalid/fake-subscription"}
res = {}
for label, root in (("r19", old), ("送审稿", draft), ("当前", new)):
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

full = ["loon.conf", "loon-strict.conf", "quantumultx.conf", "quantumultx-strict.conf", "mihomo-profile.yaml",
        "mihomo-core.yaml", "stash.yaml", "stash-strict.yaml", "sing-box-1.14.json", "sing-box-1.12.json",
        "节点分组报告.txt", "sing-box-节点转换报告.txt"]
print("r19 的私密产物：" + "、".join(sorted(os.listdir(res["r19"]))))
for label in ("送审稿", "当前"):
    print(f"\n{label}和 r19 比（完整版的私密产物）：")
    diff = []
    for f in full:
        a, b = os.path.join(res["r19"], f), os.path.join(res[label], f)
        same = filecmp.cmp(a, b, shallow=False)
        print(f"  {'相同' if same else '不同'}  {f}（{os.path.getsize(a):,} → {os.path.getsize(b):,} 字节）")
        if not same:
            diff.append(f)
    print(f"  {len(full) - len(diff)} 个相同、{len(diff)} 个不同")
    import json
    tags = [o["tag"] for o in json.load(open(os.path.join(res[label], "sing-box-1.14.json"), encoding="utf-8"))["outbounds"]
            if o.get("server") == "dns-node.example.net"]
    print(f"  完整版 sing-box 里那个虚构节点的标签：{tags}")
tags = [o["tag"] for o in json.load(open(os.path.join(res["r19"], "sing-box-1.14.json"), encoding="utf-8"))["outbounds"]
        if o.get("server") == "dns-node.example.net"]
print(f"\nr19 完整版 sing-box 里那个虚构节点的标签：{tags}")
rep = open(os.path.join(res["当前"], "sing-box-节点转换报告.txt"), encoding="utf-8").read()
old_rep = open(os.path.join(res["r19"], "sing-box-节点转换报告.txt"), encoding="utf-8").read()
print("\n当前的节点转换报告比 r19 多出来的部分：" if rep.startswith(old_rep) else "\n当前的节点转换报告和 r19 的开头不同！")
print(rep[len(old_rep):] if rep.startswith(old_rep) else rep)

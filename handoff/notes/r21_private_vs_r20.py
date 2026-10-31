"""r21 的一次性核对（2026-10-31，不属于 tools/run_checks.sh）：带本地补充和节点生成的私密产物，相对 r20 只变了使用者定的三个间隔吗？

做法和 handoff/notes/r20_full_private_same.py 相同：把两个工程的 build.py、generator/、source/ 各复制到临时目录，配上同一份 source/local.yaml
（tests/local_overlay_sample.yaml 里的节点名补充，再加一个固定节点和一条额外服务）、同一个虚构的订阅地址、同一批虚构节点（tests/node_samples.yaml
再加一个叫“境外DNS”的 Shadowsocks 节点，服务器和密码都是虚构的），各跑一次 build.py --singbox-nodes，比 dist/private/ 里的每一份文件。
比法（GPT 审核 r20 时建议的“按解析结果比、断言允许的差别”）：YAML / JSON 解析以后逐字段比（注释不算）；Loon、Quantumult X 去掉 # 开头的注释行再比；
报告类的文本逐字节比。允许的差别只有：Stash 完整版的选择组加了 interval -1、Stash 简易版的组 interval -1 → 3600、sing-box 简易版的“境外DNS”
interval / idle_timeout 3600s / 3600s → 600s / 30m，以及私密产物里的 manifest.json（版本和摘要）。别的差别都算不符，退出码非 0。
不联网，不读、不写仓库里的 source/local.yaml。
用法：python3 -B r21_private_vs_r20.py <r20 工程目录> <当前工程目录> <临时输出目录>"""
import json
import os
import shutil
import subprocess
import sys

import yaml

old, new, out = sys.argv[1:4]
nodes = yaml.safe_load(open(os.path.join(new, "tests", "node_samples.yaml"), encoding="utf-8"))
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
for label, root in (("r20", old), ("当前", new)):
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


def diff_paths(a, b, path=""):
    """两份解析结果不同的位置，写成 “proxy-groups[组名].interval” 这样的路径。列表里是带 name / tag 的字典时按它对齐。"""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}.{k}（{'新增' if k not in a else '去掉'}）")
            else:
                out += diff_paths(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        key = next((k for k in ("name", "tag") if all(isinstance(x, dict) and k in x for x in a + b)), None)
        if key and [x[key] for x in a] == [x[key] for x in b]:
            return [p for x, y in zip(a, b) for p in diff_paths(x, y, f"{path}[{x[key]}]")]
        return [] if a == b else [path]
    return [] if a == b else [path]


def uncommented(path):
    with open(path, encoding="utf-8") as f:
        return [line for line in f.read().split("\n") if not line.lstrip().startswith("#")]


names = sorted(set(os.listdir(res["r20"])) | set(os.listdir(res["当前"])))
print("私密产物：" + "、".join(names))
bad = []
for n in names:
    a, b = os.path.join(res["r20"], n), os.path.join(res["当前"], n)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"{n}：只在一边有")
        continue
    if n.endswith((".yaml", ".json")):
        load = (lambda p: yaml.safe_load(open(p, encoding="utf-8"))) if n.endswith(".yaml") else \
               (lambda p: json.load(open(p, encoding="utf-8")))
        paths = diff_paths(load(a), load(b))
    elif n.endswith(".conf"):
        paths = [] if uncommented(a) == uncommented(b) else ["（去掉注释以后的正文）"]
    else:
        paths = [] if open(a, "rb").read() == open(b, "rb").read() else ["（全文）"]
    same_bytes = open(a, "rb").read() == open(b, "rb").read()
    print(f"\n{n}：{'逐字节相同' if same_bytes else ('只有注释不同' if not paths else f'{len(paths)} 处不同')}")
    for x in paths[:6]:
        print(f"    {x}")
    if len(paths) > 6:
        print(f"    ……共 {len(paths)} 处")
    # 允许的差别
    if n == "manifest.json":
        continue
    if n in ("stash.yaml", "stash-strict.yaml"):
        c = yaml.safe_load(open(b, encoding="utf-8"))
        sel = {g["name"] for g in c["proxy-groups"] if g["type"] == "select"}
        want = sorted(f".proxy-groups[{x}].interval（新增）" for x in sel)
        if sorted(paths) != want or {g.get("interval") for g in c["proxy-groups"] if g["type"] == "select"} != {-1}:
            bad.append(f"{n}：不只是选择组加了 interval -1")
        continue
    if n in ("stash-simple.yaml", "stash-simple-strict.yaml"):
        c = yaml.safe_load(open(b, encoding="utf-8"))
        want = sorted(f".proxy-groups[{g['name']}].interval" for g in c["proxy-groups"])
        if sorted(paths) != want or {g.get("interval") for g in c["proxy-groups"]} != {3600}:
            bad.append(f"{n}：不只是组的 interval 改成 3600")
        continue
    if n.startswith("sing-box-simple-"):
        c = json.load(open(b, encoding="utf-8"))
        dg = next(o for o in c["outbounds"] if o["tag"] == "境外DNS")
        if sorted(paths) != [".outbounds[境外DNS].idle_timeout", ".outbounds[境外DNS].interval"] or \
                (dg["interval"], dg["idle_timeout"]) != ("600s", "30m"):
            bad.append(f"{n}：不只是“境外DNS”的间隔改成 600s / 30m")
        continue
    if paths:
        bad.append(f"{n}：{len(paths)} 处不同，不在允许的差别里")
print()
if bad:
    print("不符：")
    for x in bad:
        print("  " + x)
    sys.exit(1)
print(f"全部符合：{len(names)} 份私密产物里，除了 manifest.json，只有允许的那几个间隔不同")

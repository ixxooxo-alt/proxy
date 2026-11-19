"""r22 第二份送审稿的一次性核对（2026-11-19，不属于 tools/run_checks.sh）：带本地补充和节点生成的私密产物，相对第一份送审稿（f60ee42）
只变了这一轮有意改的地方吗？做法和 handoff/notes/r22_private_vs_r21b.py 相同（两个工程各复制 build.py、generator/、source/，配同一份
虚构的 local.yaml、同一个虚构订阅地址、同一批虚构节点——这一版的 tests/node_samples.yaml 加一个叫“境外DNS”的节点——各跑一次
build.py --singbox-nodes，比 dist/private/ 里的每一份文件）。允许的差别（别的差别都算不符，退出码非 0）：
  1. 节点按名称分地区的筛选正则（GPT 审核 r22 送审稿 R22-F15：“港德 / 港英 / 港法 / 港欧 / 港歐”前面不能是“香”）——只有含正则写法的那几处；
  2. 文字报告里的版本号（统一源 2026.11.18-1 → 2026.11.19-1、生成器 1.13.0 → 1.14.0）；
  3. sing-box 的节点（R22-F09）：样例里四个 cipher 是 auto 又开了 TLS 的 VMess 节点写成 aes-128-gcm。同时核对第一份送审稿里确实是 auto；
  4. sing-box-节点转换报告.txt：只多了这四个节点的提示；
  5. 私密 manifest.json 不逐项比，另外核对它本身（outputs、摘要、版本、not_refreshed 是空的）。其余文件逐字节相同；
  6. 使用者 2026-11-19 选的：Claude 组多了 http-intake.logs.us5.datadoghq.com——各端多一条规则，mihomo 的 nameserver-policy、
     sing-box 的路由和 DNS 规则各多这一个名字（只认带这个名字的新增，别的新增照样算不符）。
这一轮别的改动（订阅读法、整数、SS2022、QUIC 上的指纹、按端的固定直连……）在这批样例和这份 local.yaml 上不该产生差别。
不联网，不读、不写仓库里的 source/local.yaml。
用法：python3 -B r22b_private_vs_r22draft.py <第一份送审稿的工程目录> <当前工程目录> <临时输出目录>"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

import yaml

old, new, out = (os.path.abspath(x) for x in sys.argv[1:4])
VMESS_AUTO_TLS = ["美国 VMess HTTPUpgrade", "韩国 VMess gRPC", "美国 VMess packet", "台湾 VMess 指纹 none"]
VERSIONS = [("2026.11.18-1", "2026.11.19-1"), ("1.13.0", "1.14.0")]
DATADOG = "http-intake.logs.us5.datadoghq.com"   # 第 6 条

nodes = yaml.safe_load(open(os.path.join(new, "tests", "node_samples.yaml"), encoding="utf-8"))
by = {p["name"]: p for p in nodes["proxies"]}
assert all(by[n]["type"] == "vmess" and by[n].get("cipher") == "auto" and by[n].get("tls") is True for n in VMESS_AUTO_TLS)
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
for label, root in (("第一份送审稿", old), ("当前", new)):
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
    res[label] = os.path.join(d, "dist")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def bump(x: str) -> str:
    for a, b in VERSIONS:
        x = x.replace(a, b)
    return x


def walk(a, b, path=""):
    """两份解析结果的差别：(路径, 类别, 旧, 新)。字符串列表按多重集合比；带 name / tag 的字典列表按它对齐。"""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a:
                yield f"{path}.{k}", "新增键", None, b[k]
            elif k not in b:
                yield f"{path}.{k}", "去掉键", a[k], None
            else:
                yield from walk(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if all(isinstance(x, str) for x in a + b):
            ca, cb = Counter(a), Counter(b)
            for x in (cb - ca).elements():
                yield path, "新增项", None, x
            for x in (ca - cb).elements():
                yield path, "去掉项", x, None
            return
        key = next((k for k in ("name", "tag") if all(isinstance(x, dict) and k in x for x in a + b)), None)
        if key:
            ia, ib = {x[key]: x for x in a}, {x[key]: x for x in b}
            for k in [x[key] for x in b if x[key] not in ia]:
                yield f"{path}[{k}]", "新增项", None, ib[k]
            for k in [x[key] for x in a if x[key] not in ib]:
                yield f"{path}[{k}]", "去掉项", ia[k], None
            for k in [x[key] for x in a if x[key] in ib]:
                yield from walk(ia[k], ib[k], f"{path}[{k}]")
        elif len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                yield from walk(x, y, f"{path}[{i}]")
        else:
            yield path, "长度不同", len(a), len(b)
    elif a != b:
        yield path, "改了", a, b


def is_regex_change(kind, a, b):
    return kind == "改了" and isinstance(a, str) and isinstance(b, str) and "(?" in a and "(?" in b


def is_datadog_added(path, kind, a, b):
    """第 6 条：新加的规则行、域名列表里新加的这个名字、mihomo nameserver-policy 里新加的这个键、
    sing-box 的 Claude 路由规则里新加的 domain（以前只有 domain_suffix，所以是整个键新加，值只有这一个名字）。"""
    return ((kind == "新增项" and isinstance(b, str) and DATADOG in b.replace(" ", "").split(",") + [b])
            or (kind == "新增键" and (path.endswith("." + DATADOG) or b == [DATADOG])))


def singbox_expected(conf_old, conf_new, problems, n):
    """旧配置里四个 VMess 节点的 security 改成 aes-128-gcm 以后，应当和新配置完全相同；同时确认旧的确实是 auto。"""
    obs = []
    for o in conf_old["outbounds"]:
        o = dict(o)
        if o.get("tag") in VMESS_AUTO_TLS:
            if o.get("security") != "auto":
                problems.append(f"{n}：第一份送审稿里 {o['tag']} 的 security 是 {o.get('security')!r}，不是预期的 auto")
            o["security"] = "aes-128-gcm"
        obs.append(o)
    diffs = [d for d in walk(dict(conf_old, outbounds=obs), conf_new) if not is_datadog_added(*d)]
    for path, kind, a, b in diffs[:6]:
        problems.append(f"{n}：照预期改了 VMess 以后仍不同：{path} {kind} {json.dumps(a, ensure_ascii=False)[:80]} → "
                        f"{json.dumps(b, ensure_ascii=False)[:80]}")
    return len(diffs)


def check_private_manifest(d, problems):
    man = json.load(open(os.path.join(d, "private", "manifest.json"), encoding="utf-8"))
    pub = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    files = sorted(f for f in os.listdir(os.path.join(d, "private")) if f not in ("manifest.json", "请勿分享.txt"))
    if sorted(man["outputs"]) != files:
        problems.append(f"私密 manifest 的 outputs 和目录里的文件不一致：{sorted(set(files) ^ set(man['outputs']))}")
    for f in files:
        sha = hashlib.sha256(open(os.path.join(d, "private", f), "rb").read()).hexdigest()
        if man["outputs"].get(f) != sha:
            problems.append(f"私密 manifest 里 {f} 的摘要和文件不符")
    for k in ("generator_version", "source_version", "simple_version", "source_sha256"):
        if man.get(k) != pub.get(k):
            problems.append(f"私密 manifest 的 {k} 和公开 manifest 不同")
    if man.get("not_refreshed") != {}:
        problems.append(f"新目录里私密 manifest 的 not_refreshed 应当是空的：{man.get('not_refreshed')}")
    return len(files)


A, B = res["第一份送审稿"], res["当前"]
names = sorted(set(os.listdir(os.path.join(A, "private"))) | set(os.listdir(os.path.join(B, "private"))))
print("私密产物：" + "、".join(names))
bad = []
for n in names:
    a, b = os.path.join(A, "private", n), os.path.join(B, "private", n)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"{n}：只在一边有")
        continue
    problems, kinds = [], Counter()
    if n == "manifest.json":
        count = check_private_manifest(B, problems)
        what = f"不逐项比；本身核对：outputs 列了 {count} 个文件，摘要都相符，版本和公开 manifest 相同，not_refreshed 是空的"
    elif n.endswith(".yaml"):
        for path, kind, x, y in walk(yaml.safe_load(read(a)), yaml.safe_load(read(b))):
            if is_regex_change(kind, x, y):
                kinds["地区筛选正则"] += 1
            elif is_datadog_added(path, kind, x, y):
                kinds["Claude 组新加的 Datadog 遥测主机"] += 1
            else:
                problems.append(f"{n}：{path} {kind} {json.dumps(x, ensure_ascii=False)[:80]} → {json.dumps(y, ensure_ascii=False)[:80]}")
        what = "；".join(f"{k} {v} 处" for k, v in kinds.items()) or "解析以后相同"
    elif n.endswith(".conf"):
        la = Counter(x for x in read(a).split("\n") if not x.lstrip().startswith("#"))
        lb = Counter(x for x in read(b).split("\n") if not x.lstrip().startswith("#"))
        for x in (lb - la).elements():
            if DATADOG in x.replace(" ", "").split(","):
                kinds["Claude 组新加的 Datadog 遥测主机"] += 1
                continue
            kinds["地区筛选正则" if "(?" in x else "?"] += 1
            if "(?" not in x:
                problems.append(f"{n}：多了一行 {x[:100]!r}")
        for x in (la - lb).elements():
            kinds["地区筛选正则（旧）" if "(?" in x else "?"] += 1
            if "(?" not in x:
                problems.append(f"{n}：少了一行 {x[:100]!r}")
        what = "去掉注释以后：" + ("；".join(f"{k} {v} 行" for k, v in kinds.items()) or "相同")
    elif n.startswith("sing-box-") and n.endswith(".json"):
        left = singbox_expected(json.load(open(a, encoding="utf-8")), json.load(open(b, encoding="utf-8")), problems, n)
        added = sum(1 for d in walk(json.load(open(a, encoding="utf-8")), json.load(open(b, encoding="utf-8"))) if is_datadog_added(*d))
        what = (f"四个 VMess 节点照预期写成 aes-128-gcm、Claude 组新加的 Datadog 遥测主机（{added} 处）以外"
                f"{'相同' if not left else f'还有 {left} 处不同'}")
    elif n == "sing-box-节点转换报告.txt":
        ra, rb = bump(read(a)).split("\n"), read(b).split("\n")
        gone, came = sorted((Counter(ra) - Counter(rb)).elements()), sorted((Counter(rb) - Counter(ra)).elements())
        want = [x for x in came if re.match(r"提示 (.+)（vmess）：cipher 是 auto 又开了 TLS", x)
                and re.match(r"提示 (.+)（vmess）", x).group(1) in VMESS_AUTO_TLS]
        if gone or came != want or len(want) != len(VMESS_AUTO_TLS):
            problems.append(f"{n}：少了 {gone}，多了 {came}")
        what = f"只多了 {len(want)} 个 VMess 节点的提示（auto 加 TLS 写明 aes-128-gcm）"
    else:
        x, y = read(a), read(b)
        same = bump(x) == y
        if not same:
            problems.append(f"{n}：除了版本号应当相同")
        what = "逐字节相同" if x == y else "除了版本号相同" if same else "不同"
    print(f"\n{n}：{what}")
    for x in problems[:8]:
        print("    " + x)
    if len(problems) > 8:
        print(f"    ……共 {len(problems)} 处")
    bad += problems
print()
if bad:
    print(f"不符 {len(bad)} 处（见上）")
    sys.exit(1)
print(f"全部符合：{len(names)} 份私密产物里，只有这一轮有意改的地方不同；私密 manifest 本身核对过")

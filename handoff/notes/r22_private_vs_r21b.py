"""r22 的一次性核对（2026-11-18，不属于 tools/run_checks.sh）：带本地补充和节点生成的私密产物，相对 r21b 只变了这一版有意改的地方吗？

做法和 handoff/notes/r21_private_vs_r20.py 相同：把两个工程的 build.py、generator/、source/ 各复制到临时目录，配上同一份虚构的
source/local.yaml（tests/local_overlay_sample.yaml 里的节点名补充，再加一个固定节点和一条额外服务）、同一个虚构的订阅地址、同一批虚构节点
（这一版的 tests/node_samples.yaml——比 r21b 多了三份全项目复核加的七个样例——再加一个叫“境外DNS”的 Shadowsocks 节点），
各跑一次 build.py --singbox-nodes，比 dist/private/ 里的每一份文件。YAML、JSON 解析以后逐项比（注释不算），Loon、Quantumult X 去掉
# 开头的注释行逐行比，报告类的文本逐行比。允许的差别（别的差别都算不符，退出码非 0）：
  1. 新收的规则：Copilot 的 7 个主机（第 21 轮 F04）、Claude 的 10 个域名（使用者 2026-11-18 的清单）、Max 的 discomax.com 和一张图片 CDN
     主机（第 22 轮 C4）、Cursor 的 spacexsi.com 和三个存储主机（第 23 轮 F02）——只多不少；
  2. 节点按名称分地区的筛选正则（第 22 轮 C5：“港台 / 港新 / 港坡 / 港德……”，和“臺中”）——只有含正则写法的那几行；
  3. Loon：ip-mode = ipv4-only → v4-only、dns-reject-mode = LoopbackIP → LOOPBACKIP、去掉 switch-node-after-failure-times（第 22 轮 C1、C7）；
  4. mihomo：要真实地址的名单里的系统联网检测域名交给国内 DNS（第 23 轮 F01）；sing-box：dns.reverse_mapping（第 23 轮 F04）；
  5. sing-box 的节点（第 21 轮 F01–F03、第 22 轮 C2 和 F03 的同一类）：Trojan 有了 TLS；两个 packet 写法的节点改成 packetaddr；
     指纹写 none 的不再写 uTLS；short-id 留空的 Reality 写成空、不是 "None"；“美国 HTTPS 布尔写成字符串”不再转换；
     “新加坡 HY2 单端口跳跃”以前被跳过（换端口间隔是区间，读不了），现在转换。同时核对旧配置里确实是错的样子；
  6. sing-box-节点转换报告.txt：只差第一行的计数、上面这几个节点的提示和跳过；
  7. 私密 manifest.json 不逐项比，另外核对它本身：outputs 正好是这一次生成的文件（manifest.json、请勿分享.txt 除外）、每个摘要和文件相符、
     版本和统一源摘要和公开 manifest 相同、not_refreshed 是空的（新目录）——第 20 轮记下的建议 ②。其余文件逐字节相同。
不联网，不读、不写仓库里的 source/local.yaml。
用法：python3 -B r22_private_vs_r21b.py <r21b 工程目录> <当前工程目录> <临时输出目录>（相对路径也可以，先转成绝对路径）"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter

import yaml

old, new, out = (os.path.abspath(x) for x in sys.argv[1:4])
# 这一版新收的规则（照抄一份，不从规则源读，免得两边一起错）
NEW_HOSTS = ["production-copilot-host.webpubsub.azure.com", "production-copilot-host-centralus.webpubsub.azure.com",
             "production-copilot-host-centralus-02.webpubsub.azure.com", "production-copilot-host-eastasia.webpubsub.azure.com",
             "production-copilot-host-austriaeast.webpubsub.azure.com", "production-copilot-host-westus.webpubsub.azure.com",
             "production-copilot-host-westus3.webpubsub.azure.com",
             "ant.dev", "anthropic.team", "antspace.dev", "chatbotclaude.com", "claude.dev", "claude.new", "claude.site",
             "claudeacademy.com", "claudepages.dev", "claudestudio.com",
             "discomax.com", "hbomax-images.warnermediacdn.com",
             "spacexsi.com", "agent-stores.s3.us-east-1.amazonaws.com", "agent-stores.s3.amazonaws.com", "cursor.blob.core.windows.net"]
CONNECTIVITY = ["+.msftconnecttest.com", "+.msftncsi.com", "captive.apple.com"]
LOON_OLD = ["ip-mode = ipv4-only", "dns-reject-mode = LoopbackIP", "switch-node-after-failure-times = 3"]
LOON_NEW = ["ip-mode = v4-only", "dns-reject-mode = LOOPBACKIP"]
TROJAN, PACKET, FP_NONE, REALITY, DROPPED, ADDED = ("新加坡 Trojan 写了 tls false", ("美国 VMess packet", "日本 VLESS packet"),
                                                   "台湾 VMess 指纹 none", "日本 VLESS Reality 无 short-id",
                                                   "美国 HTTPS 布尔写成字符串", "新加坡 HY2 单端口跳跃")

nodes = yaml.safe_load(open(os.path.join(new, "tests", "node_samples.yaml"), encoding="utf-8"))
assert {TROJAN, FP_NONE, REALITY, DROPPED, ADDED, *PACKET} <= {p["name"] for p in nodes["proxies"]}, "样例节点里应当有三份复核加的那几个"
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
    res[label] = os.path.join(d, "dist")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def has_new_host(x) -> bool:
    s = json.dumps(x, ensure_ascii=False)
    return any(h in s for h in NEW_HOSTS)


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


def why_ok(n, path, kind, a, b):
    """这一处差别属于哪一类有意的改动；不属于就返回 None。"""
    x = b if b is not None else a
    if kind in ("新增项", "新增键") and has_new_host(x if kind == "新增项" else {path: x}):
        return "新收的规则"
    if kind == "改了" and isinstance(a, str) and isinstance(b, str) and "(?" in a and "(?" in b:
        return "地区筛选正则"
    if kind == "新增键" and n.startswith("mihomo") and any(path.endswith("." + c) for c in CONNECTIVITY):
        return "联网检测域名交给国内 DNS"
    if kind == "新增键" and n.startswith("sing-box") and path == ".dns.reverse_mapping" and b is True:
        return "reverse_mapping"
    return None


def singbox_expected(conf_old, conf_new, problems, n):
    """旧配置照这一版有意的节点改动改一遍、新配置去掉新收的规则和新转换的节点，再比。顺便确认旧的确实是错的样子。"""
    def strip(x):
        if isinstance(x, dict):
            # 新规则单独开出来的列表（例如只放了新主机的 domain）去掉以后是空的，整个键都不算
            return {k: strip(v) for k, v in x.items()
                    if not (isinstance(v, list) and v and all(isinstance(e, str) and e in NEW_HOSTS for e in v))}
        if isinstance(x, list):
            return [strip(v) for v in x if not (isinstance(v, str) and v in NEW_HOSTS)]
        return x

    def without(conf, tag):
        conf["outbounds"] = [dict(o, outbounds=[t for t in o["outbounds"] if t != tag]) if isinstance(o.get("outbounds"), list) else o
                             for o in conf["outbounds"] if o.get("tag") != tag]

    new_conf = strip(conf_new)
    new_conf["dns"].pop("reverse_mapping", None)
    if ADDED not in [o["tag"] for o in conf_new["outbounds"]]:
        problems.append(f"{n}：新配置里没有 {ADDED}")
    without(new_conf, ADDED)
    seen = set()
    obs = []
    for o in conf_old["outbounds"]:
        tag, o = o.get("tag"), dict(o)
        if tag == ADDED:
            problems.append(f"{n}：旧配置里有 {ADDED}（预期 r21b 读不了它的 hop-interval 区间、跳过了）")
        if tag == DROPPED:
            seen.add(tag)
            if not (isinstance(o.get("tls"), dict) and o["tls"].get("insecure") is True):
                problems.append(f"{n}：旧配置里 {DROPPED} 没有 insecure: true，和预期的错误不一样")
            continue
        if tag == TROJAN:
            seen.add(tag)
            if o.get("tls"):
                problems.append(f"{n}：旧配置里 {TROJAN} 已经有 TLS")
            o["tls"] = {"enabled": True, "server_name": "sg2.example.net"}
        if tag in PACKET:
            seen.add(tag)
            if o.get("packet_encoding") != "packet":
                problems.append(f"{n}：旧配置里 {tag} 的 packet_encoding 是 {o.get('packet_encoding')!r}")
            o["packet_encoding"] = "packetaddr"
        if tag == FP_NONE:
            seen.add(tag)
            tls = dict(o.get("tls") or {})
            if tls.get("utls") != {"enabled": True, "fingerprint": "none"}:
                problems.append(f"{n}：旧配置里 {FP_NONE} 的 uTLS 是 {tls.get('utls')!r}，不是预期的指纹 none")
            tls.pop("utls", None)
            o["tls"] = tls
        if tag == REALITY:
            seen.add(tag)
            tls = json.loads(json.dumps(o.get("tls") or {}))
            if tls.get("reality", {}).get("short_id") != "None":
                problems.append(f"{n}：旧配置里 {REALITY} 的 short_id 是 {tls.get('reality', {}).get('short_id')!r}，不是预期的 \"None\"")
            tls.setdefault("reality", {})["short_id"] = ""
            o["tls"] = tls
        if isinstance(o.get("outbounds"), list):
            o["outbounds"] = [t for t in o["outbounds"] if t != DROPPED]
        obs.append(o)
    if seen != {TROJAN, DROPPED, FP_NONE, REALITY, *PACKET}:
        problems.append(f"{n}：旧配置里没找到 {sorted({TROJAN, DROPPED, FP_NONE, REALITY, *PACKET} - seen)}")
    conf_old = dict(conf_old, outbounds=obs)
    diffs = list(walk(conf_old, new_conf))
    for path, kind, a, b in diffs[:6]:
        problems.append(f"{n}：去掉新规则、照预期改了节点以后仍不同：{path} {kind} {json.dumps(a, ensure_ascii=False)[:80]} → "
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


names = sorted(set(os.listdir(os.path.join(res["r21b"], "private"))) | set(os.listdir(os.path.join(res["当前"], "private"))))
print("私密产物：" + "、".join(names))
bad = []
for n in names:
    a, b = os.path.join(res["r21b"], "private", n), os.path.join(res["当前"], "private", n)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"{n}：只在一边有")
        continue
    problems, kinds = [], Counter()
    if n == "manifest.json":
        count = check_private_manifest(res["当前"], problems)
        what = f"不逐项比；本身核对：outputs 列了 {count} 个文件，摘要都相符，版本和公开 manifest 相同，not_refreshed 是空的"
    elif n.endswith(".yaml"):
        for path, kind, x, y in walk(yaml.safe_load(read(a)), yaml.safe_load(read(b))):
            ok = why_ok(n, path, kind, x, y)
            if ok:
                kinds[ok] += 1
            else:
                problems.append(f"{n}：{path} {kind} {json.dumps(x, ensure_ascii=False)[:80]} → {json.dumps(y, ensure_ascii=False)[:80]}")
        what = "；".join(f"{k} {v} 处" for k, v in kinds.items()) or "解析以后相同"
    elif n.endswith(".conf"):
        la = Counter(x for x in read(a).split("\n") if not x.lstrip().startswith("#"))
        lb = Counter(x for x in read(b).split("\n") if not x.lstrip().startswith("#"))
        for x in (lb - la).elements():
            k = "新收的规则" if has_new_host(x) else "地区筛选正则" if "(?" in x else "Loon 的 General" if x in LOON_NEW else None
            kinds[k or "?"] += 1
            if not k:
                problems.append(f"{n}：多了一行 {x[:100]!r}")
        for x in (la - lb).elements():
            k = "地区筛选正则（旧）" if "(?" in x else "Loon 的 General（旧）" if x in LOON_OLD else None
            kinds[k or "?"] += 1
            if not k:
                problems.append(f"{n}：少了一行 {x[:100]!r}")
        what = "去掉注释以后：" + "；".join(f"{k} {v} 行" for k, v in kinds.items())
    elif n.startswith("sing-box-") and n.endswith(".json"):
        left = singbox_expected(json.load(open(a, encoding="utf-8")), json.load(open(b, encoding="utf-8")), problems, n)
        what = f"去掉新收的规则和 reverse_mapping、照预期改了节点以后{'相同' if not left else f'还有 {left} 处不同'}"
    elif n == "sing-box-节点转换报告.txt":
        ra, rb = read(a).split("\n"), read(b).split("\n")
        gone, came = sorted((Counter(ra) - Counter(rb)).elements()), sorted((Counter(rb) - Counter(ra)).elements())
        first = int(ra[0] != rb[0])           # 第一行的计数可能碰巧相同（这一批两边都是跳过 3 个）
        want_gone = [x for x in gone if x == ra[0] or x.startswith(f"跳过 {ADDED}（hysteria2）：字段缺失或格式错误")]
        want_came = [x for x in came if x == rb[0] or x.startswith((f"提示 {TROJAN}（trojan）：订阅里写了 tls: false",
                                                                      f"提示 {ADDED}（hysteria2）：hop-interval 是区间",
                                                                      f"跳过 {DROPPED}（http）：skip-cert-verify 应该是 true / false"))]
        if gone != want_gone or came != want_came or len(want_gone) != 1 + first or len(want_came) != 3 + first:
            problems.append(f"{n}：少了 {gone}，多了 {came}")
        what = (f"第一行{'相同' if not first else f' {ra[0]!r} → {rb[0]!r}'}；少了 HY2 的跳过一行，"
                "多了 Trojan、HY2 的提示和 HTTPS 的跳过三行")
    else:
        same = open(a, "rb").read() == open(b, "rb").read()
        if not same:
            problems.append(f"{n}：应当逐字节相同")
        what = "逐字节相同" if same else "不同"
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
print(f"全部符合：{len(names)} 份私密产物里，只有这一版有意改的地方不同；私密 manifest 本身核对过")

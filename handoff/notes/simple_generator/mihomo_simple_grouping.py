"""用官方 mihomo（v1.19.31）实际分一次组，看原型简易版里“写明的成员组 + include-all-providers + filter”的组：
成员顺序、filter 会不会作用到写明的组名上、全部节点那条有没有排掉提示行。照 tools/check_official.py 的 mihomo_grouping 改的：
订阅换成本地文件里的假节点（127.0.0.1:1，不联网，关掉订阅的健康检查），控制接口只听 127.0.0.1 的临时端口，读完就停。
用法：python3 -B 本文件 <proto 目录> <mihomo 可执行文件> <放 GeoIP 等文件的目录>
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

P, MIHOMO, GEO = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, P)
sys.path.insert(0, os.path.join(P, "tools"))
sys.dont_write_bytecode = True
import yaml  # noqa: E402

from check_icu import sample_names  # noqa: E402
from generator.model import load  # noqa: E402

m = load(P, include_local=False)
names, expect = sample_names()
names = list(dict.fromkeys(names))
with open(os.path.join(P, "out", "mihomo", "mihomo-simple-profile.yaml"), encoding="utf-8") as f:
    profile = f.read()

home = tempfile.mkdtemp(prefix="mh-simple-", dir=os.path.dirname(os.path.abspath(__file__)))
for fn in os.listdir(GEO):
    shutil.copy(os.path.join(GEO, fn), os.path.join(home, fn))
with open(os.path.join(home, "fake-nodes.yaml"), "w", encoding="utf-8") as f:
    yaml.safe_dump({"proxies": [{"name": n, "type": "ss", "server": "127.0.0.1", "port": 1, "cipher": "aes-128-gcm",
                                 "password": "x"} for n in names]}, f, allow_unicode=True, sort_keys=False, width=100000)
provider = ("proxy-providers:\n  假节点:\n    type: file\n    path: ./fake-nodes.yaml\n"
            "    health-check:\n      enable: false\n      url: " + m.hc["url_https"] + "\n\n")
text, n1 = re.subn(r"(?ms)^proxy-providers:\n.*?(?=^proxy-groups:)", lambda _m: provider, profile)
assert n1 == 1
text = text.replace("geo-auto-update: true", "geo-auto-update: false")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
text = f"external-controller: 127.0.0.1:{port}\n" + text
path = os.path.join(home, "grouping.yaml")
with open(path, "w", encoding="utf-8") as f:
    f.write(text)
proc = subprocess.Popen([MIHOMO, "-d", home, "-f", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
got = None
try:
    for _ in range(120):
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/providers/proxies", timeout=3) as r:
                loaded = len(((json.load(r).get("providers") or {}).get("假节点") or {}).get("proxies") or [])
            if loaded < len(names):
                continue
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/proxies", timeout=10) as r:
                got = json.load(r)["proxies"]
                break
        except OSError:
            continue
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(home, ignore_errors=True)
if got is None:
    sys.exit("mihomo 没有起来")

wide, strict, anyrx = m.node_regexes(), m.node_regexes_strict(), re.compile(m.node_regex_any())
problems = []
for r in m.regions:
    allm = got[r["name"]]["all"]
    want = [r["name"] + "·自动"] + [n for n in names if re.search(wide[r["id"]], n)]
    if allm != want:
        problems.append(f"{r['name']}：mihomo {allm[:3]}…（{len(allm)}），期望 {want[:3]}…（{len(want)}）")
    auto = got[r["name"] + "·自动"]["all"]
    if auto != [n for n in names if re.search(strict[r["id"]], n)]:
        problems.append(f"{r['name']}·自动 和严筛选不一致")
    if got[r["name"]].get("now") != r["name"] + "·自动":
        problems.append(f"{r['name']} 当前选中的是 {got[r['name']].get('now')}")
fd = got["国外默认"]["all"]
want_fd = ["日本", "香港", "韩国", "台湾", "新加坡", "美国", "其他地区"] + [n for n in names if anyrx.search(n)]
if fd != want_fd:
    problems.append(f"国外默认：mihomo {len(fd)} 个，期望 {len(want_fd)} 个；多 {sorted(set(fd) - set(want_fd))[:5]} 少 {sorted(set(want_fd) - set(fd))[:5]}")
info = [n for n, g in expect.items() if not g]
leaked = [n for n in info if n in fd]
print(f"假节点 {len(names)} 个（其中提示行 {len(info)} 个）")
print(f"日本：第一项 {got['日本']['all'][0]}，共 {len(got['日本']['all'])} 项；当前选中 {got['日本'].get('now')}；hidden 的 日本·自动 仍在成员里：{'日本·自动' in got['日本']['all']}")
print(f"国外默认：前七项 {fd[:7]}，共 {len(fd)} 项；当前选中 {got['国外默认'].get('now')}；进了国外默认的提示行 {leaked}")
print("不一致：", problems or "没有（六个地区组、六个自动组、国外默认的成员和顺序都和 Python 按同一条正则算的相同）")

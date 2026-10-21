#!/usr/bin/env python3
"""E1：方案 ③ 的写法在 mihomo v1.19.31 上的实际结构（成员顺序、filter 管不管 proxies 里写的组名、默认选中、
exclude-filter / 反引号多条筛选 / include-all 的副作用、hidden、store-selected）。
用法：python3 -I e1_structure.py <运行目录> <base_port>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

OUT, BASE = sys.argv[1], int(sys.argv[2])
os.makedirs(OUT, exist_ok=True)
MIX, API = BASE + 7, BASE + 8
F = mh.filters()
INFO = mh.info_common()
PH = r"(?!.*·无可用节点$)"                      # 占位节点：名字以“·无可用节点”结尾

# 订阅里的节点（第二列是实验台的节点编号；延迟决定自动测速的先后）
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("日本-美国 03", 3, 30), ("剩余流量：10GB", 4, 0),
         ("香港 01", 5, 20), ("美国 01", 6, 40), ("德国 01", 7, 50), ("官网 example.com", 8, 0),
         ("请更新订阅", 9, 0), ("香港 01 | 官网：abc.com", 10, 25), ("香港·无可用节点", 11, 0)]
lab_nodes = [{"id": f"n{i}", "delay_ms": d} for _, i, d in NODES]
HC = {"url": "http://www.gstatic.com/generate_204", "expected-status": "204"}


def strip(rx):
    assert rx.startswith("(?i)^") and rx.endswith(".*$"), rx[:20]
    return rx[len("(?i)^"):-len(".*$")]


ALL_A = "(?i)^" + PH + INFO + ".*$"                                    # 只用“现有 filter 末尾那段”
LOOSE = [F["wide"][r] for r in mh.REGIONS] + [F["other"]]
ALL_B = "(?i)^" + PH + "(?:" + "|".join(strip(rx) for rx in LOOSE) + ").*$"   # 七条宽筛选的并集
ALL_C = "`".join(LOOSE)                                                # 反引号多条（生成器禁止反引号，这里只为对照）


def region(r):
    return [
        {"name": r, "type": "select", "proxies": [f"{r}·自动"], "include-all-providers": True,
         "filter": F["wide"][r], "empty-fallback": "REJECT"},
        {"name": f"{r}·自动", "type": "url-test", "include-all-providers": True, "filter": F["strict"][r],
         "empty-fallback": "REJECT", **HC, "interval": 300, "timeout": 5000, "lazy": True, "tolerance": 50,
         "hidden": True},
    ]


groups = [{"name": "国外默认", "type": "select", "proxies": mh.REGIONS[1:2] + mh.REGIONS[:1] + mh.REGIONS[2:] + ["其他地区", "全部节点"]},
          {"name": "OpenAI", "type": "select", "proxies": ["日本", "国外默认", "香港", "韩国", "台湾", "新加坡", "美国", "其他地区", "DIRECT"]}]
for r in mh.REGIONS:
    groups += region(r)
groups += [
    {"name": "其他地区", "type": "select", "include-all-providers": True, "filter": F["other"], "empty-fallback": "REJECT"},
    {"name": "全部节点", "type": "select", "include-all-providers": True, "filter": ALL_A, "empty-fallback": "REJECT"},
    # ---- 对照组（不是方案的一部分）----
    {"name": "T-全部节点-并集", "type": "select", "include-all-providers": True, "filter": ALL_B, "empty-fallback": "REJECT"},
    {"name": "T-全部节点-反引号", "type": "select", "include-all-providers": True, "filter": ALL_C,
     "exclude-filter": "·无可用节点$", "empty-fallback": "REJECT"},
    {"name": "T-日本-include-all", "type": "select", "proxies": ["日本·自动"], "include-all": True,
     "filter": F["wide"]["日本"], "empty-fallback": "REJECT"},
    {"name": "T-日本-exclude含间隔号", "type": "select", "proxies": ["日本·自动"], "include-all-providers": True,
     "filter": F["wide"]["日本"], "exclude-filter": "·", "empty-fallback": "REJECT"},
    {"name": "T-日本-反引号", "type": "select", "proxies": ["日本·自动"], "include-all-providers": True,
     "filter": "Tokyo`日本", "empty-fallback": "REJECT"},
    {"name": "T-日本-不写filter", "type": "select", "proxies": ["日本·自动"], "include-all-providers": True,
     "empty-fallback": "REJECT"},
]
国外默认 = groups[0]
国外默认["proxies"] = ["日本", "香港", "韩国", "台湾", "新加坡", "美国", "其他地区", "全部节点"]

conf = {
    "mixed-port": MIX, "allow-lan": False, "bind-address": "127.0.0.1", "external-controller": f"127.0.0.1:{API}",
    "mode": "rule", "log-level": "debug", "ipv6": False, "unified-delay": True, "find-process-mode": "off",
    "profile": {"store-selected": True, "store-fake-ip": False},
    # Stash 那份的占位节点写法（最外层 proxies，http 连本机 1 号端口）；mihomo 的现有配置里没有占位节点
    "proxies": [{"name": "日本·无可用节点", "type": "http", "server": "127.0.0.1", "port": 1}],
    "proxy-providers": {"订阅1": {"type": "file", "path": "./sub1.yaml",
                                 "health-check": {"enable": True, **HC, "interval": 300, "timeout": 5000, "lazy": True}}},
    "proxy-groups": groups,
    "rules": ["MATCH,国外默认"],
}


def write_sub(names):
    mh.write_yaml(os.path.join(OUT, "sub1.yaml"),
                  {"proxies": [mh.socks_node(n, BASE, i) for n, i, _ in NODES if n in names]})


cfg = os.path.join(OUT, "config.yaml")
mh.write_yaml(cfg, conf)
write_sub([n for n, _, _ in NODES])
rc, out = mh.check(OUT, cfg)
print("== mihomo -t：退出码", rc, "|", out.splitlines()[-1][:200])
lab = mh.Lab(BASE, lab_nodes, OUT)
report = {"check": [rc, out.splitlines()[-1][:300]]}
SHOW = ["国外默认", "OpenAI", "日本", "日本·自动", "香港", "香港·自动", "美国", "美国·自动", "韩国", "韩国·自动", "其他地区",
        "全部节点", "T-全部节点-并集", "T-全部节点-反引号", "T-日本-include-all", "T-日本-exclude含间隔号",
        "T-日本-反引号", "T-日本-不写filter"]


def dump(m, tag):
    snap = {}
    for g in SHOW:
        d = m.group(g)
        snap[g] = {"type": d["type"], "now": d.get("now"), "hidden": d.get("hidden"), "all": d.get("all")}
        print(f"  [{tag}] {g}: type={d['type']} hidden={d.get('hidden')} now={d.get('now')!r}")
        print(f"        all={d.get('all')}")
    return snap


try:
    m = mh.Mihomo(OUT, cfg, API)
    time.sleep(3)                                # 等启动时的那一次健康检查
    report["start"] = dump(m, "启动")
    glob = m.group("GLOBAL")
    report["GLOBAL_all"] = glob["all"]
    print("  GLOBAL all =", glob["all"])
    # 选择：hidden 的组能不能被选；不是成员的能不能被选
    report["put"] = {
        "日本<-日本·自动": m.select("日本", "日本·自动"),
        "日本<-香港 01(不是成员)": m.select("日本", "香港 01"),
        "日本<-日本 01": m.select("日本", "日本 01"),
        "国外默认<-全部节点": m.select("国外默认", "全部节点"),
        "全部节点<-美国 01": m.select("全部节点", "美国 01"),
    }
    print("  PUT 结果：", json.dumps(report["put"], ensure_ascii=False))
    report["after_put"] = {g: m.group(g)["now"] for g in ["国外默认", "日本", "全部节点", "OpenAI"]}
    print("  选择以后 now：", report["after_put"])
    # 一次真实请求：OpenAI 默认日本 -> 日本 已手选“日本 01”
    report["req_openai_like"] = mh.http_via_proxy(MIX, "jp.example", BASE)
    m.stop()
    # store-selected：重启以后还在不在
    m = mh.Mihomo(OUT, cfg, API)
    time.sleep(2)
    report["after_restart"] = {g: m.group(g)["now"] for g in ["国外默认", "日本", "全部节点"]}
    print("  重启以后 now：", report["after_restart"])
    m.stop()
    # 订阅里“日本 01”没了（改名 / 下线）再启动：日本回到第一个成员？全部节点里选的“美国 01”也删掉看看
    write_sub([n for n, _, _ in NODES if n not in ("日本 01", "美国 01")])
    m = mh.Mihomo(OUT, cfg, API)
    time.sleep(2)
    report["after_node_gone"] = {g: m.group(g)["now"] for g in ["国外默认", "日本", "全部节点"]}
    report["after_node_gone_all_日本"] = m.group("日本")["all"]
    print("  删掉“日本 01”“美国 01”再启动：", report["after_node_gone"], report["after_node_gone_all_日本"])
    m.stop()
finally:
    lab.stop()
json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)

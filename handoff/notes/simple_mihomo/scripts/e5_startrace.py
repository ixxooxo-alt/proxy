#!/usr/bin/env python3
"""E5：启动时的检查顺序。mihomo 把订阅（proxy-providers）和各组自带的“兼容 provider”同时初始化（executor.go loadProvider 并发）。
带健康检查、成员里有“用订阅的组”的组（完整版的“X·手动优先”= fallback[X·手动, X·自动]），启动那一次检查可能赶在订阅读进来之前，
这时成员组里一个节点都没有（返回 REJECT），被记成不可用；url-test 组把这次结果缓存 10 秒。
这里用仓库的完整版配置（只换订阅、DNS 替身、健康检查地址）和方案 ③ 各启动 N 次，看启动后 0~12 秒“日本·自动”的 now
和“日本·手动优先”对两个成员的记录。用法：python3 -I e5_startrace.py <运行目录> <base_port> <次数>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402
import simple  # noqa: E402

OUT, BASE, N = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
os.makedirs(OUT, exist_ok=True)
MIX, API, DDNS, SDNS = BASE + 7, BASE + 8, BASE + 3, BASE + 4
HURL = "http://www.gstatic.com/generate_204"
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("香港 01", 3, 20), ("美国 01", 4, 40)]


def build(variant):
    conf = mh.dist("core")
    dns = conf["dns"]
    F = ["tcp://1.1.1.1:53", "tcp://8.8.8.8:53"]
    D = [f"tcp://127.0.0.1:{DDNS}"]
    S = [f"tcp://127.0.0.1:{SDNS}"]

    def stand(v):
        return F if v[0].startswith("https://1.1.1.1") else (D if v[0].startswith("https://223") else S)
    dns["nameserver"], dns["direct-nameserver"], dns["proxy-server-nameserver"] = F, D, D
    dns["default-nameserver"] = [f"127.0.0.1:{DDNS}"]
    for key in ("nameserver-policy", "proxy-server-nameserver-policy"):
        dns[key] = {k: stand(v) for k, v in dns[key].items()}
    conf.update({"mixed-port": MIX, "allow-lan": False, "bind-address": "127.0.0.1",
                 "external-controller": f"127.0.0.1:{API}", "log-level": "debug", "find-process-mode": "off",
                 "geo-auto-update": False, "profile": {"store-selected": False, "store-fake-ip": False}})
    conf["tun"]["enable"] = False
    conf["proxy-providers"] = {"订阅1": {"type": "file", "path": "./sub1.yaml",
                                        "health-check": {"enable": True, "url": HURL, "expected-status": "204",
                                                         "interval": 300, "timeout": 5000, "lazy": True}}}
    if variant == "simple":
        conf["proxy-groups"] = simple.simple_groups(conf, simple.all_nodes_filter_compact())
    for g in conf["proxy-groups"]:
        if "url" in g:
            g["url"] = HURL
    return conf


res = {}
for variant in ("full", "simple"):
    res[variant] = []
    for k in range(N):
        home = os.path.join(OUT, f"{variant}-{k}")
        os.makedirs(home, exist_ok=True)
        mh.copy_geodata(home)
        mh.write_yaml(os.path.join(home, "sub1.yaml"), {"proxies": [mh.socks_node(n, BASE, i) for n, i, _ in NODES]})
        cfg = os.path.join(home, "config.yaml")
        mh.write_yaml(cfg, build(variant))
        lab = mh.Lab(BASE, [{"id": f"n{i}", "delay_ms": d} for _, i, d in NODES], home)
        mi = mh.Mihomo(home, cfg, API)
        t0 = time.time()
        samples = []
        try:
            while time.time() - t0 < 12:
                row = {"t": round(time.time() - t0, 1), "日本·自动": mi.group("日本·自动")["now"]}
                if variant == "full":
                    hist = {}
                    for mem in ("日本·手动", "日本·自动"):
                        h = mi.get(f"/proxies/{mem}").get("extra", {}).get(HURL, {})
                        hist[mem] = h.get("alive")
                    row["手动优先眼里的成员 alive"] = hist
                    row["日本·手动优先"] = mi.group("日本·手动优先")["now"]
                samples.append(row)
                time.sleep(0.5)
            req = mh.http_via_proxy(MIX, "jp-probe.qzx-lab-probe.net", BASE)
        finally:
            mi.stop()
            lab.stop()
        first = samples[0]
        rej = [s["t"] for s in samples if s["日本·自动"] == "REJECT"]
        res[variant].append({"run": k, "first_sample": first, "REJECT_seen_at": rej, "last_sample": samples[-1],
                             "req_after_12s": req})
        print(variant, k, "首个采样", first, "| 日本·自动=REJECT 的采样时刻", rej, "| 12 秒时", samples[-1])
json.dump(res, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)

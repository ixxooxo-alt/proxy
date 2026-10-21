#!/usr/bin/env python3
"""E2：方案 ③（日本 = select[日本·自动, 日本的节点]；日本·自动 = url-test 严筛选，hidden）在 mihomo v1.19.31 上，
自动测速选中的节点挂掉以后多久换走。只监听 127.0.0.1。
用法：python3 -I e2_timing.py <运行目录> <base_port> <json 参数>
参数：
  interval     订阅（proxy-providers）health-check 的 interval（秒）
  group_interval  url-test 组上写的 interval（默认同上；用来核对“组上的 interval 不起作用”）
  mode         refuse | blackhole | egress   n1 出故障的方式
  traffic      seq（一个接一个，间隔 period 秒）| burst（每 period 秒同时发 k 个）| idle（故障前 idle_before 秒停流量，故障后 idle_after 秒恢复）
  select       auto（日本 选 日本·自动）| fixed（日本 手选“🇯🇵 Tokyo 02”，日本·自动 没被选中）
  mft          url-test 组的 max-failed-times（不写 = 内核默认 5）
  t_fail       启动后第几秒让 n1 出故障；t_end 第几秒结束"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

OUT, BASE = sys.argv[1], int(sys.argv[2])
P = json.loads(sys.argv[3])
os.makedirs(OUT, exist_ok=True)
MIX, API = BASE + 7, BASE + 8
INTERVAL = P["interval"]
GI = P.get("group_interval", INTERVAL)
F = mh.filters()
HC = {"url": "http://www.gstatic.com/generate_204", "expected-status": "204"}
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("日本 03", 3, 120), ("香港 01", 4, 20)]
lab_nodes = [{"id": f"n{i}", "delay_ms": d} for _, i, d in NODES]
NAME = {f"n{i}": n for n, i, _ in NODES}

auto = {"name": "日本·自动", "type": "url-test", "include-all-providers": True, "filter": F["strict"]["日本"],
        "empty-fallback": "REJECT", **HC, "interval": GI, "timeout": 5000, "lazy": True, "tolerance": 50, "hidden": True}
if P.get("mft"):
    auto["max-failed-times"] = P["mft"]
groups = [
    {"name": "国外默认", "type": "select", "proxies": ["日本", "香港", "全部节点"]},
    {"name": "日本", "type": "select", "proxies": ["日本·自动"], "include-all-providers": True,
     "filter": F["wide"]["日本"], "empty-fallback": "REJECT"},
    auto,
    {"name": "香港", "type": "select", "proxies": ["香港·自动"], "include-all-providers": True,
     "filter": F["wide"]["香港"], "empty-fallback": "REJECT"},
    {"name": "香港·自动", "type": "url-test", "include-all-providers": True, "filter": F["strict"]["香港"],
     "empty-fallback": "REJECT", **HC, "interval": GI, "timeout": 5000, "lazy": True, "tolerance": 50, "hidden": True},
    {"name": "全部节点", "type": "select", "include-all-providers": True, "filter": "(?i)^.*$", "empty-fallback": "REJECT"},
]
conf = {
    "mixed-port": MIX, "allow-lan": False, "bind-address": "127.0.0.1", "external-controller": f"127.0.0.1:{API}",
    "mode": "rule", "log-level": "debug", "ipv6": False, "unified-delay": True, "tcp-concurrent": True,
    "find-process-mode": "off", "profile": {"store-selected": False, "store-fake-ip": False},
    "proxy-providers": {"订阅1": {"type": "file", "path": "./sub1.yaml",
                                 "health-check": {"enable": True, **HC, "interval": INTERVAL, "timeout": 5000, "lazy": True}}},
    "proxy-groups": groups,
    "rules": ["MATCH,国外默认"],
}
cfg = os.path.join(OUT, "config.yaml")
mh.write_yaml(cfg, conf)
mh.write_yaml(os.path.join(OUT, "sub1.yaml"), {"proxies": [mh.socks_node(n, BASE, i) for n, i, _ in NODES]})
json.dump(P, open(os.path.join(OUT, "params.json"), "w"))
rc, out = mh.check(OUT, cfg)
REC = open(os.path.join(OUT, "driver.jsonl"), "w", buffering=1)
T0 = None
lock = threading.Lock()


def rec(**kw):
    kw["t"] = round(time.time() - T0, 3)
    with lock:
        REC.write(json.dumps(kw, ensure_ascii=False) + "\n")


lab = mh.Lab(BASE, lab_nodes, OUT)
mi = mh.Mihomo(OUT, cfg, API)
T0 = time.time()
rec(ev="start", check=[rc, out.splitlines()[-1][:120]], params=P)
stop = threading.Event()
traffic_on = threading.Event()
traffic_on.set()


def one(tag):
    res, secs = mh.http_via_proxy(MIX, "jp.example", BASE)
    rec(ev="req", tag=tag, res=res, secs=secs)


def traffic():
    period, k = P.get("period", 2.0), P.get("k", 4)
    i = 0
    while not stop.is_set():
        if not traffic_on.is_set():
            time.sleep(0.2)
            continue
        i += 1
        t = time.time()
        if P["traffic"] == "burst":
            ths = [threading.Thread(target=one, args=(f"b{i}.{j}",)) for j in range(k)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        else:
            one(f"s{i}")
        time.sleep(max(0.0, period - (time.time() - t)) if P["traffic"] == "burst" else period)


def sampler():
    last = None
    while not stop.is_set():
        try:
            now = mi.group("日本·自动")["now"]
            sel = mi.group("日本")["now"]
        except Exception as e:
            now, sel = "api-err:" + type(e).__name__, None
        if (now, sel) != last:
            rec(ev="now", auto=now, jp=sel)
            last = (now, sel)
        time.sleep(0.5)


time.sleep(2)
if P.get("select") == "fixed":
    rec(ev="select", res=mi.select("日本", "🇯🇵 Tokyo 02"))
for g, n in P.get("selects", []):                 # 例如 [["国外默认", "香港"]]：流量只经过香港，看日本·自动还测不测
    rec(ev="select", group=g, name=n, res=mi.select(g, n))
threading.Thread(target=sampler, daemon=True).start()
tt = threading.Thread(target=traffic, daemon=True)
tt.start()
t_fail, t_end = P["t_fail"], P["t_end"]
idle_before, idle_after = P.get("idle_before"), P.get("idle_after")
done_fail = done_off = done_on = False
while time.time() - T0 < t_end:
    el = time.time() - T0
    if P["traffic"] == "idle" and not done_off and el >= t_fail - idle_before:
        traffic_on.clear()
        rec(ev="traffic_off")
        done_off = True
    if not done_fail and el >= t_fail:
        rec(ev="fail", node="n1", mode=P["mode"], lab=lab.mode("n1", P["mode"]).strip())
        done_fail = True
    if P["traffic"] == "idle" and done_fail and not done_on and el >= t_fail + idle_after:
        traffic_on.set()
        rec(ev="traffic_on")
        done_on = True
    time.sleep(0.1)
stop.set()
time.sleep(1)
mi.stop()
lab.stop()
# 实验台记下的源站事件（健康检查到达时间、请求经哪个节点）换算成相对时间并入
for e in lab.events():
    if e.get("kind") in ("probe", "hello", "mode", "node_blackhole", "node_egress_broken", "node_connect"):
        e["t"] = round(e["t"] - T0, 3)
        e["ev"] = "lab_" + e.pop("kind")
        with lock:
            REC.write(json.dumps(e, ensure_ascii=False) + "\n")
REC.close()
print("done", OUT)

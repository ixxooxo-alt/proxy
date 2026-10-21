"""实验驱动：起 lab.py 和 sing-box（官方二进制），按时间表改节点状态 / 发流量 / 切选择组，记录 clash API 的 now 和探测到达时间。
用法：python3 -I driver.py <sing-box 二进制> <场景名> <输出目录> [interval秒]
所有监听都在 127.0.0.1。"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

BIN, SCEN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
INTERVAL = int(sys.argv[4]) if len(sys.argv) > 4 else 30
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

OFF = int(sys.argv[5]) if len(sys.argv) > 5 else 0
HTTP_PORT, BASE, CTRL, API = 47100 + OFF, 47110 + OFF, 47130 + OFF, 47140 + OFF
IN_PORTS = {"in-a": 47151 + OFF, "in-b": 47152 + OFF, "in-c": 47153 + OFF}
N = 4
DELAYS = "0,100,200,300"          # n1 最快
URL = f"http://127.0.0.1:{HTTP_PORT}/generate_204"


def nodes_ob():
    return [{"type": "socks", "tag": f"n{i}", "server": "127.0.0.1", "server_port": BASE + i, "version": "5"}
            for i in range(1, N + 1)]


def urltest(tag, members, tolerance=50, interrupt=False):
    return {"type": "urltest", "tag": tag, "outbounds": members, "url": URL, "interval": f"{INTERVAL}s",
            "tolerance": tolerance, "idle_timeout": "30m", "interrupt_exist_connections": interrupt}


R19 = lambda interrupt=False: [urltest("jp-auto", NODES, interrupt=interrupt),
                               {"type": "selector", "tag": "jp-manual", "outbounds": NODES},
                               {"type": "selector", "tag": "jp", "outbounds": ["jp-auto", "jp-manual"], "default": "jp-auto"}]


NODES = [f"n{i}" for i in range(1, N + 1)]

NODES = [f"n{i}" for i in range(1, N + 1)]
# ---- 场景 ----
# 每个场景：groups（出站）、routes（入站 -> 组）、watch（要记录 now 的组）、timeline [(秒, 动作, 参数...)]、end
SCENARIOS = {
    # r19 的形状：jp = selector[jp-auto, jp-manual]；有流量时 n1 拒绝连接
    "auto_refuse_traffic": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp-manual", "outbounds": NODES},
                {"type": "selector", "tag": "jp", "outbounds": ["jp-auto", "jp-manual"], "default": "jp-auto"}],
        routes={"in-a": "jp"}, watch=["jp-auto", "jp"],
        timeline=[(5, "traffic", "in-a", 2.0), (95, "node", "n1", "down"), (215, "node", "n1", "up")],
        end=300),
    # 同上，但 n1 停掉之前就没有流量了：只靠定时测速
    "auto_refuse_idle": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp-manual", "outbounds": NODES},
                {"type": "selector", "tag": "jp", "outbounds": ["jp-auto", "jp-manual"], "default": "jp-auto"}],
        routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (40, "traffic_off", "in-a"), (95, "node", "n1", "down")],
        end=240),
    # 节点“不回应”（接受连接但不回话，像被墙或机房断网）；有流量
    "auto_hang_traffic": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp-manual", "outbounds": NODES},
                {"type": "selector", "tag": "jp", "outbounds": ["jp-auto", "jp-manual"], "default": "jp-auto"}],
        routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (95, "node", "n1", "hang")],
        end=230),
    # 试一个“手动优先”的替代写法：urltest[jp-manual, jp-auto]，tolerance 拉满
    "mf_urltest_trick": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp-manual", "outbounds": NODES, "default": "n3"},
                urltest("jp-mf", ["jp-manual", "jp-auto"], tolerance=65535)],
        routes={"in-a": "jp-mf"}, watch=["jp-mf", "jp-manual", "jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (95, "node", "n3", "down"), (185, "node", "n3", "up"),
                  (275, "select", "jp-manual", "n4")],
        end=330),
    # SFA 的“测速”按钮走的函数（这里用 clash API /group/<名>/delay 触发同一组函数）：节点停掉后手动点一次测速
    "test_button": dict(
        groups=R19(), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (30, "traffic_off", "in-a"), (40, "node", "n1", "down"),
                  (50, "groupdelay", "jp")],
        end=70),
    "test_button_auto": dict(
        groups=R19(), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (30, "traffic_off", "in-a"), (40, "node", "n1", "down"),
                  (50, "groupdelay", "jp-auto")],
        end=70),
    # 节点“冻住”（像断网：现有连接不断也不走数据，新连接不回话）；一条长连接看 interrupt_exist_connections 的作用
    "freeze_int_false": dict(
        groups=R19(False), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (10, "stream", "in-a"), (95, "node", "n1", "freeze")],
        end=200),
    "freeze_int_true": dict(
        groups=R19(True), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (10, "stream", "in-a"), (95, "node", "n1", "freeze")],
        end=200),
    # 简易版一层的写法：jp = selector[jp-auto, 各节点]；国外默认 = selector[jp, 各节点]
    "simple_onelayer": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp", "outbounds": ["jp-auto"] + NODES, "default": "jp-auto"},
                {"type": "selector", "tag": "fd", "outbounds": ["jp"] + NODES, "default": "jp"}],
        routes={"in-a": "fd"}, watch=["fd", "jp", "jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (20, "select", "jp", "n3"), (35, "select", "fd", "n4"),
                  (50, "select", "fd", "jp"), (60, "node", "n3", "down")],
        end=80),
    # 按 interval 计算时间：第一次定时测速（5+I 秒）之后 5 秒停掉 n1
    "gen_idle": dict(
        groups=R19(), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (15, "traffic_off", "in-a"), (10 + INTERVAL, "node", "n1", "down")],
        end=25 + 3 * INTERVAL),
    "gen_traffic": dict(
        groups=R19(), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (10 + INTERVAL, "node", "n1", "down")],
        end=25 + 2 * INTERVAL),
    "gen_hang_traffic": dict(
        groups=R19(), routes={"in-a": "jp"}, watch=["jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (10 + INTERVAL, "node", "n1", "hang")],
        end=45 + 2 * INTERVAL),
    # 同上，tolerance 改成 50000（65535 会让 uint16 的“延迟 + 容差”溢出）
    "mf_trick_50000": dict(
        groups=[urltest("jp-auto", NODES), {"type": "selector", "tag": "jp-manual", "outbounds": NODES, "default": "n3"},
                urltest("jp-mf", ["jp-manual", "jp-auto"], tolerance=50000)],
        routes={"in-a": "jp-mf"}, watch=["jp-mf", "jp-manual", "jp-auto"],
        timeline=[(5, "traffic", "in-a", 2.0), (100, "node", "n3", "down"), (190, "node", "n3", "up"),
                  (280, "select", "jp-manual", "n4"), (300, "node", "n1", "down")],
        end=360),
    # 手选单个节点（selector 直接放节点）：挂了以后会怎样（对照）
    "manual_only": dict(
        groups=[{"type": "selector", "tag": "jp-manual", "outbounds": NODES, "default": "n3"}],
        routes={"in-a": "jp-manual"}, watch=["jp-manual"],
        timeline=[(5, "traffic", "in-a", 2.0), (40, "node", "n3", "down")],
        end=80),
}

S = SCENARIOS[SCEN]
conf = {
    "log": {"level": "debug", "timestamp": True},
    "inbounds": [{"type": "mixed", "tag": t, "listen": "127.0.0.1", "listen_port": p} for t, p in IN_PORTS.items()],
    "outbounds": nodes_ob() + S["groups"] + [{"type": "direct", "tag": "direct"}],
    "route": {"rules": [{"inbound": [i], "outbound": g} for i, g in S["routes"].items()], "final": "direct"},
    "experimental": {"clash_api": {"external_controller": f"127.0.0.1:{API}"}},
}
cfg = os.path.join(OUT, "config.json")
with open(cfg, "w") as f:
    json.dump(conf, f, ensure_ascii=False, indent=1)

ev_path = os.path.join(OUT, "events.jsonl")
open(ev_path, "w").close()
rec = open(ev_path, "a", buffering=1)
rec_lock = threading.Lock()


def log(**kw):
    kw.setdefault("t", round(time.time(), 3))
    with rec_lock:
        rec.write(json.dumps(kw) + "\n")


chk = subprocess.run([BIN, "check", "-c", cfg], capture_output=True, text=True)
log(kind="check", rc=chk.returncode, out=(chk.stdout + chk.stderr)[-500:])
if chk.returncode != 0:
    print("check failed", chk.stdout, chk.stderr)
    sys.exit(1)

lab = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "lab.py"), str(HTTP_PORT), str(BASE), str(CTRL), str(N),
                        ev_path, DELAYS])
time.sleep(1.0)
sb_log = open(os.path.join(OUT, "sing-box.log"), "w")
T0 = time.time()
log(kind="start", t0=T0, interval=INTERVAL, bin=BIN, scen=SCEN)
sb = subprocess.Popen([BIN, "run", "-c", cfg, "-D", OUT], stdout=sb_log, stderr=subprocess.STDOUT)

stop = threading.Event()
traffic = {}


def http_get(host, port, path, method="GET", body=None, timeout=3.0):
    s = socket.create_connection((host, port), timeout=timeout)
    s.settimeout(timeout)
    data = f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
    if body is not None:
        data += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    data += "\r\n" + (body or "")
    s.sendall(data.encode())
    buf = b""
    while True:
        try:
            c = s.recv(65536)
        except socket.timeout:
            break
        if not c:
            break
        buf += c
    s.close()
    return buf.decode(errors="replace")


def traffic_loop(inb, period, flag):
    port = IN_PORTS[inb]
    while not stop.is_set() and not flag.is_set():
        t = time.time()
        try:
            r = http_get("127.0.0.1", port, f"http://127.0.0.1:{HTTP_PORT}/hello", timeout=5.0)
            ok = r.startswith("HTTP/1.1 200")
            node = r.split("node=")[-1].strip() if ok else None
            log(kind="req", inb=inb, ok=ok, node=node, dur=round(time.time() - t, 3), head=r[:40] if not ok else "")
        except Exception as e:
            log(kind="req", inb=inb, ok=False, err=repr(e)[:80], dur=round(time.time() - t, 3))
        time.sleep(max(0.0, period - (time.time() - t)))


def stream_loop(inb):
    port = IN_PORTS[inb]
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(f"GET http://127.0.0.1:{HTTP_PORT}/stream HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    s.settimeout(600)
    last = time.time()
    log(kind="stream_start")
    while not stop.is_set():
        try:
            c = s.recv(4096)
        except Exception as e:
            log(kind="stream_end", how=repr(e)[:80], gap=round(time.time() - last, 2))
            return
        if not c:
            log(kind="stream_end", how="closed", gap=round(time.time() - last, 2))
            return
        now = time.time()
        if now - last > 2.5:
            log(kind="stream_gap", gap=round(now - last, 2))
        last = now


def watcher():
    last = {}
    while not stop.is_set():
        for g in S["watch"]:
            try:
                r = http_get("127.0.0.1", API, "/proxies/" + urllib.parse.quote(g), timeout=1.0)
                j = json.loads(r.split("\r\n\r\n", 1)[1])
                now = j.get("now")
                if last.get(g) != now:
                    log(kind="now", group=g, now=now)
                    last[g] = now
            except Exception:
                pass
        time.sleep(0.5)


threading.Thread(target=watcher, daemon=True).start()
pending = sorted(S["timeline"], key=lambda x: x[0])
while time.time() - T0 < S["end"]:
    while pending and time.time() - T0 >= pending[0][0]:
        a = pending.pop(0)
        log(kind="action", action=list(a[1:]), at=a[0])
        if a[1] == "traffic":
            flag = threading.Event()
            traffic[a[2]] = flag
            threading.Thread(target=traffic_loop, args=(a[2], a[3], flag), daemon=True).start()
        elif a[1] == "traffic_off":
            traffic[a[2]].set()
        elif a[1] == "node":
            http_get("127.0.0.1", CTRL, f"/set?node={a[2]}&state={a[3]}")
        elif a[1] == "groupdelay":
            t1 = time.time()
            r = http_get("127.0.0.1", API, "/group/" + urllib.parse.quote(a[2]) + "/delay?timeout=5000", timeout=8)
            log(kind="groupdelay_result", dur=round(time.time() - t1, 3), resp=r.split("\r\n\r\n", 1)[-1][:200])
        elif a[1] == "stream":
            threading.Thread(target=stream_loop, args=(a[2],), daemon=True).start()
        elif a[1] == "select":
            r = http_get("127.0.0.1", API, "/proxies/" + urllib.parse.quote(a[2]), method="PUT",
                         body=json.dumps({"name": a[3]}))
            log(kind="select_result", resp=r[:40])
    time.sleep(0.1)

stop.set()
time.sleep(0.5)
sb.terminate()
lab.terminate()
sb.wait(5)
lab.wait(5)
print("done", SCEN, OUT)

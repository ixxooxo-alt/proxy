"""“节点接受连接但不回话”时，各协议出站的自动测速能不能按时判失败（1.14.1 / 1.12.0 对比）。
用法：python3 -I hangtypes.py <sing-box 二进制> <输出目录> <端口偏移>
lab 的 n1 一开始就设成 hang；X-hang 出站都指向 n1 的端口；n2 是正常的 SOCKS 节点。只监听 127.0.0.1。"""
import json
import os
import socket
import subprocess
import sys
import time

BIN, OUT, OFF = sys.argv[1], sys.argv[2], int(sys.argv[3])
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)
HTTP_PORT, BASE, CTRL, API = 47100 + OFF, 47110 + OFF, 47130 + OFF, 47140 + OFF
URL = f"http://127.0.0.1:{HTTP_PORT}/generate_204"
HP = BASE + 1

hang = {
    "socks-hang": {"type": "socks", "server": "127.0.0.1", "server_port": HP, "version": "5"},
    "ss-hang": {"type": "shadowsocks", "server": "127.0.0.1", "server_port": HP, "method": "aes-128-gcm",
                "password": "test-only-not-a-secret"},
    "vmess-hang": {"type": "vmess", "server": "127.0.0.1", "server_port": HP,
                   "uuid": "00000000-0000-4000-8000-000000000001", "security": "auto"},
    "trojan-hang": {"type": "trojan", "server": "127.0.0.1", "server_port": HP, "password": "test-only",
                    "tls": {"enabled": True, "server_name": "example.invalid", "insecure": True}},
}
obs = [{"tag": t, **o} for t, o in hang.items()]
obs.append({"type": "socks", "tag": "n2", "server": "127.0.0.1", "server_port": BASE + 2, "version": "5"})
for t in hang:
    obs.append({"type": "urltest", "tag": "ut-" + t, "outbounds": [t, "n2"], "url": URL, "interval": "30s",
                "idle_timeout": "30m"})
obs.append({"type": "direct", "tag": "direct"})
conf = {"log": {"level": "debug", "timestamp": True}, "outbounds": obs, "route": {"final": "direct"},
        "experimental": {"clash_api": {"external_controller": f"127.0.0.1:{API}"}}}
cfg = os.path.join(OUT, "config.json")
json.dump(conf, open(cfg, "w"), indent=1)
ev = os.path.join(OUT, "events.jsonl")
open(ev, "w").close()


def http_get(port, path, timeout=3.0):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
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
    return buf.decode(errors="replace").split("\r\n\r\n", 1)[-1]


print("check:", subprocess.run([BIN, "check", "-c", cfg], capture_output=True, text=True).stderr[-300:] or "ok")
lab = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "lab.py"), str(HTTP_PORT), str(BASE), str(CTRL), "2", ev, "0,100"])
time.sleep(1.0)
http_get(CTRL, "/set?node=n1&state=hang")
log = open(os.path.join(OUT, "sing-box.log"), "w")
T0 = time.time()
sb = subprocess.Popen([BIN, "run", "-c", cfg, "-D", OUT], stdout=log, stderr=subprocess.STDOUT)
res = {}
time.sleep(25)
for t in hang:
    g = "ut-" + t
    res[g] = {"now_at_25s": json.loads(http_get(API, "/proxies/" + g)).get("now")}
# 第二次测速：第一次如果还卡着，这里会立刻返回空结果
for t in hang:
    g = "ut-" + t
    t1 = time.time()
    r = http_get(API, f"/group/{g}/delay?timeout=20000", timeout=25)
    res[g]["second_test"] = r.strip()[:120]
    res[g]["second_test_secs"] = round(time.time() - t1, 2)
    res[g]["now_after"] = json.loads(http_get(API, "/proxies/" + g)).get("now")
sb.terminate()
lab.terminate()
sb.wait(5)
lab.wait(5)
print(json.dumps(res, indent=1))

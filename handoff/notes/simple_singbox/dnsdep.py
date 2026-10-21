"""“国外默认”选了一个挂掉的单节点时，路由里的 resolve 动作（dns-foreign 经国外默认）失败会不会让连接失败。
用法：python3 -I dnsdep.py <sing-box 二进制> <输出目录> <端口偏移>
最小复现：dns-foreign = 本机 TCP DNS 替身（任何名字都答 127.0.0.1），detour = fd（selector[n1 正常, n2 已停]）；
路由：in-a 先 resolve(dns-foreign)，再 127.0.0.0/8 -> direct。只监听 127.0.0.1。"""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time

BIN, OUT, OFF = sys.argv[1], sys.argv[2], int(sys.argv[3])
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)
HTTP_PORT, BASE, CTRL, API, MIX, DNSP = (47100 + OFF, 47110 + OFF, 47130 + OFF, 47140 + OFF, 47151 + OFF, 47160 + OFF)
queries = []


def dns_server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", DNSP))
    srv.listen(16)
    while True:
        c, a = srv.accept()
        threading.Thread(target=dns_conn, args=(c, a), daemon=True).start()


def dns_conn(c, a):
    try:
        while True:
            h = c.recv(2)
            if len(h) < 2:
                return
            ln = struct.unpack("!H", h)[0]
            q = b""
            while len(q) < ln:
                q += c.recv(ln - len(q))
            qid = q[:2]
            # 问题段：从第 12 字节到名字结尾 + 4
            i = 12
            while q[i] != 0:
                i += q[i] + 1
            qend = i + 5
            question = q[12:qend]
            qtype = struct.unpack("!H", q[i + 1:i + 3])[0]
            queries.append((time.time(), a[0], qtype))
            if qtype == 1:
                ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + socket.inet_aton("127.0.0.1")
                resp = qid + b"\x81\x80" + struct.pack("!HHHH", 1, 1, 0, 0) + question + ans
            else:
                resp = qid + b"\x81\x80" + struct.pack("!HHHH", 1, 0, 0, 0) + question
            c.sendall(struct.pack("!H", len(resp)) + resp)
    except Exception:
        pass
    finally:
        c.close()


threading.Thread(target=dns_server, daemon=True).start()
conf = {
    "log": {"level": "debug", "timestamp": True},
    "dns": {"servers": [{"type": "tcp", "tag": "dns-foreign", "server": "127.0.0.1", "server_port": DNSP, "detour": "fd"}],
            "strategy": "ipv4_only"},
    "inbounds": [{"type": "mixed", "tag": "in-a", "listen": "127.0.0.1", "listen_port": MIX}],
    "outbounds": [{"type": "socks", "tag": "n1", "server": "127.0.0.1", "server_port": BASE + 1, "version": "5"},
                  {"type": "socks", "tag": "n2", "server": "127.0.0.1", "server_port": BASE + 2, "version": "5"},
                  {"type": "selector", "tag": "fd", "outbounds": ["n1", "n2"], "default": "n1"},
                  {"type": "direct", "tag": "direct"}],
    "route": {"rules": [{"inbound": ["in-a"], "action": "resolve", "server": "dns-foreign"},
                        {"ip_cidr": ["127.0.0.0/8"], "outbound": "direct"}],
              "final": "direct"},
    "experimental": {"clash_api": {"external_controller": f"127.0.0.1:{API}"}},
}
cfg = os.path.join(OUT, "config.json")
json.dump(conf, open(cfg, "w"), indent=1)
ev = os.path.join(OUT, "events.jsonl")
open(ev, "w").close()
chk = subprocess.run([BIN, "check", "-c", cfg], capture_output=True, text=True)
print("check:", chk.returncode, chk.stderr[-300:])
lab = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "lab.py"), str(HTTP_PORT), str(BASE), str(CTRL), "2", ev, "0,0"])
time.sleep(1.0)


def raw(port, data, timeout=6.0):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(data.encode())
    buf = b""
    while True:
        try:
            c = s.recv(65536)
        except socket.timeout:
            buf += b"<timeout>"
            break
        except Exception as e:
            buf += repr(e).encode()
            break
        if not c:
            break
        buf += c
    s.close()
    return buf.decode(errors="replace")


raw(CTRL, "GET /set?node=n2&state=down HTTP/1.1\r\nHost: x\r\n\r\n")
log = open(os.path.join(OUT, "sing-box.log"), "w")
sb = subprocess.Popen([BIN, "run", "-c", cfg, "-D", OUT], stdout=log, stderr=subprocess.STDOUT)
time.sleep(1.5)


def req(name):
    t = time.time()
    r = raw(MIX, f"GET http://{name}:{HTTP_PORT}/hello HTTP/1.1\r\nHost: {name}:{HTTP_PORT}\r\nConnection: close\r\n\r\n")
    return {"name": name, "secs": round(time.time() - t, 2), "resp": (r.split("\r\n")[0] + " | " + r.split("\r\n\r\n")[-1]).strip()[:80]}


out = {"fd=n1(正常)": req("unlisted-a.example")}
body = json.dumps({"name": "n2"})
raw(API, f"PUT /proxies/fd HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}")
out["fd=n2(已停)"] = req("unlisted-b.example")
out["dns_queries_received"] = len(queries)
sb.terminate()
lab.terminate()
sb.wait(5)
lab.wait(5)
print(json.dumps(out, ensure_ascii=False, indent=1))

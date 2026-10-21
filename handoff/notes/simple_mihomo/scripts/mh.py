"""实验共用的小工具：取仓库里现成的筛选正则、写 mihomo 配置、起停 mihomo 和实验台、调控制口。
只读仓库；所有输出写到调用者给的运行目录里。所有监听都在 127.0.0.1。"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import yaml

REPO = "/home/user/proxy"
HERE = os.path.dirname(os.path.abspath(__file__))
MIHOMO = os.environ.get("MIHOMO_BIN", "/root/proxy-vendor/bin/mihomo-linux-amd64-v1.19.31")
GEODATA = os.environ.get("GEODATA_DIR", "/root/proxy-vendor/geodata")
REGIONS = ["香港", "日本", "韩国", "台湾", "新加坡", "美国"]


def dist(flavor="core"):
    with open(os.path.join(REPO, "dist", "mihomo", f"mihomo-{flavor}.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def filters():
    """{'wide': {地区: 正则}, 'strict': {地区: 正则}, 'other': 正则}，原样取自 dist/mihomo/mihomo-core.yaml。"""
    g = {x["name"]: x for x in dist()["proxy-groups"]}
    return {"wide": {r: g[f"{r}·手动"]["filter"] for r in REGIONS},
            "strict": {r: g[f"{r}·自动"]["filter"] for r in REGIONS},
            "other": g["其他地区"]["filter"]}


def info_common():
    """提示行排除（regions.yaml 的 info 规则第 1、2 条），用生成器自己的函数拼出来（不写 .pyc 进仓库）。"""
    sys.dont_write_bytecode = True
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from generator import model as gm, regions as gr      # noqa: E402
    m = gm.load(REPO, include_local=False)
    return gr._Composer(m.region_spec).info_common()


class Dumper(yaml.SafeDumper):
    pass


def write_yaml(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(obj, f, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=1 << 20)


def socks_node(name, base, idx, udp=False):
    return {"name": name, "type": "socks5", "server": "127.0.0.1", "port": base + 10 + idx, "udp": udp}


def copy_geodata(home):
    for src, dst in {"geosite.dat": "GeoSite.dat", "geoip.dat": "GeoIP.dat", "geoip.metadb": "geoip.metadb",
                     "country.mmdb": "Country.mmdb", "GeoLite2-ASN.mmdb": "GeoLite2-ASN.mmdb"}.items():
        p = os.path.join(GEODATA, src)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(home, dst))


def check(home, cfg):
    r = subprocess.run([MIHOMO, "-t", "-d", home, "-f", cfg], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def wait_port(port, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


class Lab:
    def __init__(self, base, nodes, home):
        self.base = base
        self.ev = os.path.join(home, "events.jsonl")
        open(self.ev, "w").close()
        nf = os.path.join(home, "lab_nodes.json")
        json.dump(nodes, open(nf, "w"))
        self.log = open(os.path.join(home, "lab.stdout"), "w")
        self.p = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "lab.py"), str(base), nf, self.ev],
                                  stdout=self.log, stderr=subprocess.STDOUT)
        if not wait_port(base + 1):
            raise RuntimeError("实验台没起来")

    def mode(self, node, m):
        return http_get(self.base + 1, f"/mode?node={node}&m={m}")

    def events(self):
        out = []
        with open(self.ev, encoding="utf-8") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
        return out

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def http_get(port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return r.read().decode()


class Mihomo:
    def __init__(self, home, cfg, api_port):
        self.home, self.api = home, api_port
        self.logf = open(os.path.join(home, "mihomo.log"), "a")
        self.p = subprocess.Popen([MIHOMO, "-d", home, "-f", cfg], stdout=self.logf, stderr=subprocess.STDOUT)
        if not wait_port(api_port, 30):
            raise RuntimeError("mihomo 没起来，看 mihomo.log")

    def get(self, path):
        q = urllib.parse.quote(path, safe="/?=&")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.api}{q}", timeout=10) as r:
            return json.loads(r.read().decode() or "null")

    def req(self, method, path, body=None):
        q = urllib.parse.quote(path, safe="/?=&")
        data = json.dumps(body).encode() if body is not None else None
        rq = urllib.request.Request(f"http://127.0.0.1:{self.api}{q}", data=data, method=method,
                                    headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(rq, timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def select(self, group, name):
        return self.req("PUT", f"/proxies/{group}", {"name": name})

    def group(self, name):
        return self.get(f"/proxies/{name}")

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(10)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
        self.logf.close()


def http_via_proxy(mix_port, host, port, path="/hello", timeout=10.0):
    """经 mihomo 的 mixed 端口发一个 HTTP 代理请求（每次新连接）。返回 (结果, 耗时)。结果：node=nX / HTTP 状态行 / timeout / 异常。"""
    t = time.time()
    try:
        s = socket.create_connection(("127.0.0.1", mix_port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(f"GET http://{host}:{port}{path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode())
        buf = b""
        while True:
            c = s.recv(65536)
            if not c:
                break
            buf += c
        s.close()
        txt = buf.decode(errors="replace")
        status = txt.split("\r\n", 1)[0]
        body = txt.split("\r\n\r\n", 1)[1].strip() if "\r\n\r\n" in txt else ""
        res = body if status.startswith("HTTP/1.1 200") and body.startswith("node=") else (status or "empty")
    except socket.timeout:
        res = "timeout"
    except OSError as e:
        res = "oserr:" + type(e).__name__
    return res, round(time.time() - t, 3)

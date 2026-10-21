#!/usr/bin/env python3
"""E6：用生成器实际写出的简易版（dist/mihomo/mihomo-simple-core.yaml，2026-10-21）核对“境外 DNS 不跟着国外默认里手选的节点走”
（docs/10 第六节的方案 2，使用者 2026-10-21 定的“1②”）。mihomo v1.19.31。
和 E3 的区别：策略组不改写，原样用简易版的（地区组直接是节点、国外默认 = 七个地区 + 全部节点、内部组“境外DNS”）。
只换掉跑实验必须换的：
  - 订阅换成本机文件，节点是实验台的 SOCKS5（n1 日本 01、n2 🇯🇵 Tokyo 02、n3 香港 01、n4 美国 01、n5 美国 02）；
    健康检查地址改成 http（实验台没有 TLS），间隔等其余设置照生成的（订阅上 3600 秒、lazy）
  - DNS 服务器换成本机替身，但“走哪条路”不变：
      境外 DoH（https://1.1.1.1/dns-query#境外DNS 等）-> tcp://1.1.1.1:53#境外DNS：仍然经“境外DNS”组去问；
        节点收到 CONNECT 1.1.1.1:53 / 8.8.8.8:53 时转给实验台的“境外 DNS”替身（直连去 1.1.1.1 在这台机器上连不通）
      国内 DoH、direct / proxy-server / default 解析器 -> 本机“国内 DNS”替身；system -> 本机“系统 DNS”替身
  - 端口、控制口、dns.listen 只开在 127.0.0.1；geo-auto-update 关掉（只用控制口手动触发一次）；不记住选择（store-selected 关）
各段（每段一个全新的 mihomo 进程和目录，避免 DNS 缓存）：
  alive        国外默认 -> 美国 -> 美国 02（n5），n5 正常
  fd-refuse    同上，n5 端口关闭（connection refused）
  fd-blackhole 同上，n5 接受连接但不回话
  dns-refuse   n5 正常；“境外DNS”当前用的节点端口关闭：每 2 秒发一个要靠境外 DNS 判断的连接，记下多久恢复
  dns-blackhole 同上，那个节点不回话
用法：python3 -I e6_simple_dist.py <运行目录> <base_port> [段名,段名…]"""
import json
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

OUT, BASE = sys.argv[1], int(sys.argv[2])
PHASES = sys.argv[3].split(",") if len(sys.argv) > 3 else ["alive", "fd-refuse", "fd-blackhole", "dns-refuse", "dns-blackhole"]
os.makedirs(OUT, exist_ok=True)
MIX, API, DNSL = BASE + 7, BASE + 8, BASE + 9
DDNS, SDNS = BASE + 3, BASE + 4
ZONE = "qzx-lab-probe.net"     # 不在 .example / .test 这类保留域下：那些在 geosite:private 里，会交给 system
DNS_GROUP = "境外DNS"
FOREIGN = ["https://1.1.1.1/dns-query#" + DNS_GROUP, "https://8.8.8.8/dns-query#" + DNS_GROUP]
DOMESTIC = ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"]
F_STAND = ["tcp://1.1.1.1:53#" + DNS_GROUP, "tcp://8.8.8.8:53#" + DNS_GROUP]
D_STAND = [f"tcp://127.0.0.1:{DDNS}"]
S_STAND = [f"tcp://127.0.0.1:{SDNS}"]
HURL = "http://www.gstatic.com/generate_204"
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("香港 01", 3, 20), ("美国 01", 4, 40), ("美国 02", 5, 30)]
NODE_ID = {name: f"n{i}" for name, i, _ in NODES}

conf = mh.dist("simple-core")
dns = conf["dns"]
assert dns["respect-rules"] is True and dns["nameserver"] == FOREIGN, dns["nameserver"]
assert any(r == f"DOMAIN,testingcf.jsdelivr.net,{DNS_GROUP}" for r in conf["rules"])
groups = {g["name"]: g for g in conf["proxy-groups"]}
assert groups[DNS_GROUP]["type"] == "url-test" and groups[DNS_GROUP]["hidden"] is True


def stand(v):
    if v == FOREIGN:
        return F_STAND
    if v == DOMESTIC:
        return D_STAND
    if v == ["system"]:
        return S_STAND
    raise RuntimeError(f"没见过的服务器列表 {v}")


dns["nameserver"] = F_STAND
dns["direct-nameserver"] = D_STAND
dns["proxy-server-nameserver"] = D_STAND
dns["default-nameserver"] = [f"127.0.0.1:{DDNS}"]
for key in ("nameserver-policy", "proxy-server-nameserver-policy"):
    dns[key] = {k: stand(v) for k, v in dns[key].items()}
dns["listen"] = f"127.0.0.1:{DNSL}"
conf.update({"mixed-port": MIX, "allow-lan": False, "bind-address": "127.0.0.1", "external-controller": f"127.0.0.1:{API}",
             "log-level": "debug", "find-process-mode": "off", "geo-auto-update": False,
             "profile": {"store-selected": False, "store-fake-ip": False}})
conf["tun"]["enable"] = False
hc = dict(conf["proxy-providers"]["订阅1"]["health-check"])
assert hc["interval"] == 3600, hc
hc["url"] = HURL
conf["proxy-providers"] = {"订阅1": {"type": "file", "path": "./sub1.yaml", "health-check": hc}}
for g in conf["proxy-groups"]:
    if "url" in g:
        g["url"] = HURL
cfg = os.path.join(OUT, "config.yaml")
mh.write_yaml(cfg, conf)
mh.write_yaml(os.path.join(OUT, "sub1.yaml"), {"proxies": [mh.socks_node(n, BASE, i, udp=True) for n, i, _ in NODES]})
mh.copy_geodata(OUT)
rc, out = mh.check(OUT, cfg)
print("mihomo -t：", rc, out.splitlines()[-1][:200])
if rc != 0:
    print(out[-2000:])
    sys.exit(1)


def dns_query(host, qtype=1, timeout=6.0):
    """向 mihomo 的 dns.listen 发一次 UDP 查询；返回 (结果, 耗时)。"""
    t = time.time()
    q = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + b"".join(
        bytes([len(p)]) + p.encode() for p in host.split(".")) + b"\x00" + struct.pack("!HH", qtype, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(q, ("127.0.0.1", DNSL))
        r, _ = s.recvfrom(4096)
        rcode = r[3] & 0x0F
        an = struct.unpack("!H", r[6:8])[0]
        ips = []
        if an:
            i = 12
            while r[i] != 0:
                i += r[i] + 1
            i += 5
            for _ in range(an):
                if r[i] & 0xC0 == 0xC0:
                    i += 2
                else:
                    while r[i] != 0:
                        i += r[i] + 1
                    i += 1
                typ, _, _, ln = struct.unpack("!HHIH", r[i:i + 10])
                i += 10
                if typ == 1:
                    ips.append(socket.inet_ntoa(r[i:i + ln]))
                i += ln
        res = f"rcode={rcode} " + (",".join(ips) if ips else "no-answer")
    except socket.timeout:
        res = "timeout"
    finally:
        s.close()
    return res, round(time.time() - t, 2)


def udp_once(host, port=443, hold=6.0):
    """经 mixed 端口做 SOCKS5 UDP ASSOCIATE，发一个目标写成域名的 UDP 包，控制连接保持 hold 秒。"""
    try:
        with socket.create_connection(("127.0.0.1", MIX), timeout=5) as c:
            c.settimeout(5)
            c.sendall(b"\x05\x01\x00")
            if c.recv(2) != b"\x05\x00":
                return "handshake-failed"
            c.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
            rep = c.recv(64)
            if len(rep) < 10 or rep[1] != 0:
                return f"associate-failed {rep!r}"
            relay = (socket.inet_ntoa(rep[4:8]), struct.unpack("!H", rep[8:10])[0])
            if relay[0] == "0.0.0.0":
                relay = ("127.0.0.1", relay[1])
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.sendto(b"\x00\x00\x00\x03" + bytes([len(host)]) + host.encode() + struct.pack("!H", port) + b"probe", relay)
                time.sleep(hold)
            return "sent"
    except OSError as e:
        return "oserr:" + type(e).__name__


report = {"check": [rc, out.splitlines()[-1][:200]], "phases": []}
for phase in PHASES:
    home = os.path.join(OUT, phase)
    os.makedirs(home, exist_ok=True)
    mh.write_yaml(os.path.join(home, "sub1.yaml"), {"proxies": [mh.socks_node(n, BASE, i, udp=True) for n, i, _ in NODES]})
    pcfg = os.path.join(home, "config.yaml")
    mh.write_yaml(pcfg, conf)
    mh.copy_geodata(home)
    lab = mh.Lab(BASE, [{"id": f"n{i}", "delay_ms": d} for _, i, d in NODES], home)
    mi = mh.Mihomo(home, pcfg, API)
    T0 = time.time()
    res = {"phase": phase, "http": {}, "dns": {}, "udp": {}}
    try:
        time.sleep(3)
        res["select"] = {"国外默认": mi.select("国外默认", "美国"), "美国": mi.select("美国", "美国 02"),
                         "Microsoft": mi.select("Microsoft", "DIRECT")}
        # 先问一次让“境外DNS”定下当前节点（第一次用到它时 mihomo 才测速；订阅上 lazy）
        res["warmup"] = dns_query(f"warmup-{phase}.{ZONE}")
        time.sleep(1)
        res["now"] = {g: mi.group(g)["now"] for g in ["国外默认", "美国", "日本", "OpenAI", "Microsoft", DNS_GROUP]}
        dns_node = NODE_ID.get(res["now"][DNS_GROUP])
        print(f"[{phase}] now：", res["now"], "境外DNS 用的是", dns_node)
        if phase in ("fd-refuse", "fd-blackhole"):
            lab.mode("n5", phase.split("-")[1])
        elif phase in ("dns-refuse", "dns-blackhole"):
            if dns_node in (None, "n5"):
                raise RuntimeError(f"境外DNS 当前用的节点是 {dns_node}，这一段要求它和国外默认用的 n5 不同")
            lab.mode(dns_node, phase.split("-")[1])
        time.sleep(1)
        res["t_mode"] = round(time.time() - T0, 2)
        if phase.startswith("dns-"):
            # 每 2 秒发一个连接，目标是一个新名字（不在任何规则里）：判断最后的 GEOIP,CN 要在本机解析，交给境外 DNS（经“境外DNS”）；
            # 替身给 cn 开头的名字答国内地址，所以 DNS 通的时候连接直连成功（node=direct），不通的时候失败。
            # 注意：设备自己发来的 A 查询在假地址模式下直接拿假地址，不经过境外 DNS，不能拿来测这件事。最多 120 秒
            series = []
            t_start = time.time()
            first_ok = None
            while time.time() - t_start < 120:
                r = mh.http_via_proxy(MIX, f"cnsite-seq{len(series)}-{phase}.{ZONE}", BASE, timeout=20.0)
                series.append({"t": round(time.time() - t_start, 2), "res": r[0], "secs": r[1],
                               "now": mi.group(DNS_GROUP)["now"]})
                if r[0] == "node=direct" and first_ok is None:
                    first_ok = series[-1]["t"]
                if first_ok is not None and series[-1]["t"] - first_ok > 6:
                    break
                time.sleep(2)
            res["dns_series"] = series
            res["dns_first_ok_after_s"] = first_ok
            print(f"  [{phase}] 第一次恢复：{first_ok} 秒；境外DNS 现在用 {series[-1]['now']}")
        else:
            http_cases = {
                "没被规则认出的域名（走国外默认）": f"unlisted-{phase}.{ZONE}",
                "没被规则认出、境外 DNS 会答国内地址的域名": f"cnsite-{phase}.{ZONE}",
                "系统联网检测 captive.apple.com（规则直连）": "captive.apple.com",
                "geosite:cn 里的国内域名": "www.baidu.com",
                "OpenAI（服务组 -> 日本 -> 日本 01，节点正常）": f"tcp-{phase}.openai.com",
                "geolocation-!cn 里的境外域名（国外默认）": f"{phase}.wikipedia.org",
                "Microsoft 手动切成 DIRECT，域名在境外 DNS 策略里": f"loop-{phase}.onmicrosoft.com",
            }
            for label, host in http_cases.items():
                r = mh.http_via_proxy(MIX, host, BASE, timeout=20.0)
                res["http"][label] = {"host": host, "res": r[0], "secs": r[1]}
                print(f"  [{phase}] HTTP {label}: {host} -> {r}")
            for host in ("www.msftconnecttest.com", "www.msftncsi.com", "captive.apple.com", "time.apple.com",
                         f"unlisted-{phase}.{ZONE}", "www.baidu.com", f"nas-{phase}"):
                r = dns_query(host)
                res["dns"][host] = {"res": r[0], "secs": r[1]}
                print(f"  [{phase}] DNS {host}: {r}")
            uhost = f"udp-{phase}.openai.com"
            res["udp"][uhost] = udp_once(uhost)
            print(f"  [{phase}] UDP {uhost}: {res['udp'][uhost]}")
            tg = time.time()
            st, body = mi.req("POST", "/configs/geo", {})
            res["geo_update"] = {"status": st, "body": body[:200], "secs": round(time.time() - tg, 2)}
            print(f"  [{phase}] POST /configs/geo -> {st} {body[:120]!r} ({res['geo_update']['secs']}s)")
    finally:
        mi.stop()
        lab.stop()
    evs = lab.events()
    for e in evs:
        e["t"] = round(e["t"] - T0, 2)
    res["lab_events"] = [e for e in evs if e.get("kind") in ("dns", "node_connect", "node_udp_assoc", "node_udp_packet",
                                                              "hello", "mode", "node_blackhole", "node_cmd_unsupported")]
    # 汇总：境外 DNS 的查询经哪些节点到了替身；GEO 数据的下载连接到了哪个节点
    res["foreign_dns_via"] = sorted({e["via"] for e in res["lab_events"] if e.get("kind") == "dns" and e.get("server") == "foreign"})
    res["geo_connect_nodes"] = sorted({e["node"] for e in res["lab_events"]
                                       if e.get("kind") == "node_connect" and e.get("host") == "testingcf.jsdelivr.net"})
    print(f"  [{phase}] 境外 DNS 替身收到的查询经过：{res['foreign_dns_via']}；GEO 数据下载连到：{res['geo_connect_nodes']}")
    report["phases"].append(res)
json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
print("done")

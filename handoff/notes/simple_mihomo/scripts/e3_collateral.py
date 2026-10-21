#!/usr/bin/env python3
"""E3：方案 ③ 下“国外默认”选了一个挂掉的单个节点，会连累什么（mihomo v1.19.31，用仓库的真实配置）。
配置 = dist/mihomo/mihomo-core.yaml，原样保留规则、DNS 结构（respect-rules 等）、嗅探；只换掉：
  - proxy-groups 换成方案 ③（scripts/simple.py；“全部节点”用 E1b 的紧凑写法 D）；健康检查地址改成 http（实验台没有 TLS）
  - 订阅换成本机文件，节点是实验台的 SOCKS5（n1 日本 01、n2 🇯🇵 Tokyo 02、n3 香港 01、n4 美国 01、n5 美国 02）
  - DNS 服务器换成本机替身，但“走哪条路”不变：
      境外 DoH（1.1.1.1 / 8.8.8.8）-> tcp://1.1.1.1:53、tcp://8.8.8.8:53：地址不变，respect-rules 下照样按规则匹配（MATCH -> 国外默认）；
        节点收到 CONNECT 1.1.1.1:53 / 8.8.8.8:53 时转给实验台的“境外 DNS”替身。直连去 1.1.1.1 在这台机器上连不通。
      国内 DoH（223.5.5.5 / 1.12.12.12）、direct / proxy-server / default 解析器 -> 本机“国内 DNS”替身（127.0.0.1，规则里 127/8 直连，
        和真实配置里国内 DNS 按 GEOIP,CN 直连是同一个结果）；system 不动。
  - 端口、控制口、dns.listen 只开在 127.0.0.1；geo-auto-update 关掉（只用控制口手动触发一次）
做法：国外默认 -> 全部节点 -> “美国 02”（n5）。三段：n5 正常 / n5 端口关闭（connection refused）/ n5 不回话（blackhole）。
每段发同一批请求（名字带段名，避免 DNS 缓存），记结果、耗时、替身收到的查询、节点收到的连接 / UDP 包。
用法：python3 -I e3_collateral.py <运行目录> <base_port>"""
import json
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402
import simple  # noqa: E402

OUT, BASE = sys.argv[1], int(sys.argv[2])
OPT = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
# 可选：dns_via = 组名 —— 境外 DNS 服务器写成 “地址#组名”，不再按规则走（mihomo 的写法：config.go parseNameServer 的 #片段）
os.makedirs(OUT, exist_ok=True)
MIX, API, DNSL = BASE + 7, BASE + 8, BASE + 9
DDNS = BASE + 3
SDNS = BASE + 4
S_STAND = [f"tcp://127.0.0.1:{SDNS}"]
ZONE = "qzx-lab-probe.net"     # 不在 .example / .test 这类保留域下：那些在 geosite:private 里，会交给 system
FOREIGN = ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]
DOMESTIC = ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"]
F_STAND = ["tcp://1.1.1.1:53", "tcp://8.8.8.8:53"]
if OPT.get("dns_via"):
    F_STAND = [x + "#" + OPT["dns_via"] for x in F_STAND]
D_STAND = [f"tcp://127.0.0.1:{DDNS}"]

conf = mh.dist("core")
dns = conf["dns"]
assert dns["respect-rules"] is True and dns["nameserver"] == FOREIGN


def stand(v):
    if v == FOREIGN:
        return F_STAND
    if v == DOMESTIC:
        return D_STAND
    if v == ["system"]:
        return S_STAND                 # system 换成本机替身（只为不让查询离开这台机器；mihomo 的 system 本来就直接发，不按规则走）
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
HURL = "http://www.gstatic.com/generate_204"
conf["proxy-providers"] = {"订阅1": {"type": "file", "path": "./sub1.yaml",
                                    "health-check": {"enable": True, "url": HURL, "expected-status": "204",
                                                     "interval": 300, "timeout": 5000, "lazy": True}}}
groups = simple.simple_groups(conf, simple.all_nodes_filter_compact())
for g in groups:
    if "url" in g:
        g["url"] = HURL
if OPT.get("dns_fallback_group"):
    # 设想：境外 DNS 平时跟着“国外默认”走，“国外默认”测速失败时退到各地区的自动组（没有在真机上试过）
    groups.append({"name": OPT["dns_via"], "type": "fallback",
                   "proxies": ["国外默认"] + [f"{r}·自动" for r in mh.REGIONS],
                   "url": HURL, "expected-status": "204", "interval": 300, "timeout": 5000, "lazy": True,
                   "max-failed-times": 3, "hidden": True})
conf["proxy-groups"] = groups
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("香港 01", 3, 20), ("美国 01", 4, 40), ("美国 02", 5, 30)]
mh.write_yaml(os.path.join(OUT, "sub1.yaml"), {"proxies": [mh.socks_node(n, BASE, i, udp=True) for n, i, _ in NODES]})
cfg = os.path.join(OUT, "config.yaml")
mh.write_yaml(cfg, conf)
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
for phase, mode in [x for x in (("alive", "up"), ("refuse", "refuse"), ("blackhole", "blackhole"))
                    if x[0] in OPT.get("phases", ["alive", "refuse", "blackhole"])]:
    # 每段用全新的 mihomo 进程和目录：mihomo 的 DNS 缓存过期以后仍会先回旧答案再去后台刷新，同一个进程里前一段的答案会盖住后一段
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
        res["select"] = {"国外默认": mi.select("国外默认", "全部节点"), "全部节点": mi.select("全部节点", "美国 02"),
                         "Microsoft": mi.select("Microsoft", "DIRECT")}
        res["now"] = {g: mi.group(g)["now"] for g in ["国外默认", "全部节点", "OpenAI", "日本", "日本·自动", "Microsoft"]
                      + ([OPT["dns_via"]] if OPT.get("dns_fallback_group") else [])}
        print(f"[{phase}] now：", res["now"])
        if mode != "up":
            lab.mode("n5", mode)
        time.sleep(1)
        res["t_mode"] = round(time.time() - T0, 2)
        http_cases = {
            "没被规则认出的域名": f"unlisted-{phase}.{ZONE}",
            "没被规则认出、境外 DNS 会答国内地址的域名": f"cnsite-{phase}.{ZONE}",
            "系统联网检测 captive.apple.com（规则直连）": "captive.apple.com",
            "geosite:cn 里的国内域名": "www.baidu.com",
            "OpenAI（服务组 -> 日本 -> 日本·自动，节点正常）": f"tcp-{phase}.openai.com",
            "geolocation-!cn 里的境外域名（国外默认）": f"{phase}.wikipedia.org",
            "Microsoft 手动切成 DIRECT，域名在境外 DNS 策略里": f"loop-{phase}.onmicrosoft.com",
        }
        for label, host in http_cases.items():
            r = mh.http_via_proxy(MIX, host, BASE, timeout=20.0)
            res["http"][label] = {"host": host, "res": r[0], "secs": r[1]}
            print(f"  [{phase}] HTTP {label}: {host} -> {r}")
        for host in ("www.msftconnecttest.com", "www.msftncsi.com", "captive.apple.com", "time.apple.com",
                     "connectivitycheck.platform.hicloud.com", f"unlisted-{phase}.{ZONE}", "www.baidu.com", f"nas-{phase}"):
            r = dns_query(host)
            res["dns"][host] = {"res": r[0], "secs": r[1]}
            print(f"  [{phase}] DNS {host}: {r}")
        uhost = f"udp-{phase}.openai.com"
        res["udp"][uhost] = udp_once(uhost)
        print(f"  [{phase}] UDP {uhost}: {res['udp'][uhost]}")
        if OPT.get("dns_fallback_group"):
            res["dns_group_now_end"] = mi.group(OPT["dns_via"])["now"]
            print(f"  [{phase}] {OPT['dns_via']} now = {res['dns_group_now_end']}")
            # 再发一遍前两项，看第一次失败以后是否已经退到别的出口
            for label, host in (("再试：没被规则认出的域名", f"unlisted2-{phase}.{ZONE}"),
                                ("再试：境外 DNS 会答国内地址的域名", f"cnsite2-{phase}.{ZONE}")):
                r = mh.http_via_proxy(MIX, host, BASE, timeout=20.0)
                res["http"][label] = {"host": host, "res": r[0], "secs": r[1]}
                print(f"  [{phase}] HTTP {label}: {host} -> {r}")
        if phase in ("alive", "refuse"):
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
    report["phases"].append(res)
json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
print("done")

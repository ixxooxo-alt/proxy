#!/usr/bin/env python3
"""一次性核对（2026-10-07，处理 GPT 对 r13 的审核时做的；不参与生成和测试，结果记在 docs/08 第 9 轮）。

审核报告 R13-F01 说：mihomo 的 WireGuard 出站连接还没有解析的目标时，用默认解析器（DNS 段的 nameserver / nameserver-policy）
在本机解析目标域名，所以 qwen.ai 这类“名字归国内 DNS、路由走代理组”的域名会被交给国内 DNS。
核实时读 mihomo v1.19.31 源码又看到：几乎所有代理协议转发 UDP 前都会调用 ResolveUDP（adapter/outbound/base.go），
同样用默认解析器在本机解析目标域名。这里用官方内核把两件事都实际跑一遍：

  出口：规则、DNS 段的结构原样（同 tools/check_real_routes.py 的 mihomo_dial_probe）；系统 / 国内 / 境外三类 DNS 各换成一个
        本机替身（A 都答 127.0.0.1）；原来默认直连的组仍然直连，其余策略组都换成同一个测试节点，节点的服务器是 127.0.0.1 上
        一个没人监听的端口——每次拨号都落在本机，连不出去。WireGuard 节点的密钥是每次运行随机生成的，不写进任何文件。
  测试节点：socks5、shadowsocks、trojan、wireguard，以及 wireguard 打开 remote-dns-resolve（dns 写一个公共地址，查询走隧道，
        隧道连不通）作对照。
  流量：TCP——经本机代理端口发 CONNECT 主机:443；UDP——经同一个端口做 SOCKS5 UDP ASSOCIATE，发一个目标是“主机:443”的
        UDP 包（域名形式）；UDP（假地址）——先向内核的 DNS 端口查这个主机拿到假地址，再发目标是“假地址:443”的 UDP 包
        （开了 TUN 时程序发 QUIC 就是这样进来的）。
  主机：qwen.ai（国内域名集合收了、路由按产品规则走代理组：待决事项第 16 项那一类）、chatgpt.com（境外）、
        www.qq.com（国内，默认直连）。每种“节点 × 流量”单独起一次内核，看三类替身各收到了哪些名字的查询。

sing-box（自查同一类问题）：dist/sing-box/sing-box-1.14.json 的 DNS 规则、路由规则原样；dns-cn / dns-foreign / dns-local 换成本机
        替身（dns-fakeip 保留），TUN 入站换成本机回环上的 mixed 入站；默认直连的组仍直连，其余策略组都换成测试出站
        （socks、shadowsocks，或者 WireGuard 端点），服务器同样是 127.0.0.1 上没人监听的端口。流量和上面一样（不做假地址那一种：
        mixed 入站没有假地址）。主机多一个 time.windows.com（待决事项第 15 项：DNS 规则交给 dns-cn、路由归 Microsoft 组）。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r13_review_probes.py [mihomo 配置 sing-box 1.14 配置]
  不给路径时用 dist/ 里现在的两份。2026-10-07 跑了两遍（handoff/release/r14-as-used/README.md 有命令）：
    r13_review_probes.r13.out  GPT 审的 r13（提交 bf42e8b）的配置——R13-F01 说的就是它；
    r13_review_probes.out      r14 的配置——nameserver-policy 加了产品域名那一层之后。
"""
import base64
import ipaddress
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import check_real_routes as crr  # noqa: E402
import real_data as rd  # noqa: E402
from generator.model import load  # noqa: E402

HOSTS = ("qwen.ai", "chatgpt.com", "www.qq.com")
NODE = "测试节点"


def node(kind: str, port: int) -> dict:
    base = {"name": NODE, "server": "127.0.0.1", "port": port, "udp": True}
    if kind == "socks5":
        return {**base, "type": "socks5"}
    if kind == "shadowsocks":
        return {**base, "type": "ss", "cipher": "aes-128-gcm", "password": "probe"}
    if kind == "trojan":
        return {**base, "type": "trojan", "password": "probe", "sni": "probe.invalid", "skip-cert-verify": True}
    if kind.startswith("wireguard"):
        key = lambda: base64.b64encode(os.urandom(32)).decode()   # noqa: E731  随机的一次性密钥
        wg = {**base, "type": "wireguard", "ip": "172.16.0.2", "private-key": key(), "public-key": key(), "mtu": 1280}
        if kind == "wireguard+remote-dns":
            wg.update({"remote-dns-resolve": True, "dns": ["1.1.1.1"]})
        return wg
    raise ValueError(kind)


def socks5_udp(port: int, target_host: str, target_ip: str = None, wait: float = 6.0) -> None:
    """经 SOCKS5（mixed-port）做 UDP ASSOCIATE，发一个 UDP 包给 target:443；控制连接保持 wait 秒。"""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
        c.settimeout(5)
        c.sendall(b"\x05\x01\x00")
        if c.recv(2) != b"\x05\x00":
            raise RuntimeError("SOCKS5 握手失败")
        c.sendall(b"\x05\x03\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
        rep = c.recv(64)
        if len(rep) < 10 or rep[1] != 0:
            raise RuntimeError(f"UDP ASSOCIATE 失败：{rep!r}")
        relay = (socket.inet_ntoa(rep[4:8]), struct.unpack("!H", rep[8:10])[0])
        if relay[0] == "0.0.0.0":
            relay = ("127.0.0.1", relay[1])
        if target_ip:
            addr = b"\x01" + socket.inet_aton(target_ip)
        else:
            addr = b"\x03" + bytes([len(target_host)]) + target_host.encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.sendto(b"\x00\x00\x00" + addr + struct.pack("!H", 443) + b"probe", relay)
            time.sleep(wait)


def run_case(binary, geodata_dir, model, config_text, kind, transport):
    orig = yaml.safe_load(config_text)
    conf = rd.mihomo_dial_base(config_text)
    dns = conf["dns"]
    fake_net = ipaddress.ip_network(dns["fake-ip-range"], strict=False)
    kind_of = {"system": "system"}
    for srv in list(model.dns["domestic_doh"]) + list(model.dns["domestic_plain"]):
        kind_of[srv] = "domestic"
    for srv in model.dns["foreign_doh"]:
        kind_of[srv] = "foreign"
    stubs = {k: crr.DnsStub(k, crr._Loopback()) for k in ("system", "domestic", "foreign")}

    def stand_in(servers):
        out = []
        for srv in [servers] if isinstance(servers, str) else list(servers):
            addr = f"127.0.0.1:{stubs[kind_of[srv]].port}"
            if addr not in out:
                out.append(addr)
        return out

    for key in crr.MIHOMO_DNS_SERVER_LISTS:
        if key in dns:
            dns[key] = stand_in(dns[key])
    for key in crr.MIHOMO_DNS_POLICIES:
        if key in dns:
            dns[key] = {pattern: stand_in(servers) for pattern, servers in dns[key].items()}
    home = tempfile.mkdtemp(prefix="r13-probe-")
    try:
        for st in stubs.values():
            st.start()
        closed = crr.free_port_tcp_udp()
        port, dns_port = crr.free_port_tcp_udp(), crr.free_port_tcp_udp()
        dns["listen"] = f"127.0.0.1:{dns_port}"
        conf.update({
            "mixed-port": port, "allow-lan": False, "bind-address": "127.0.0.1", "log-level": "debug",
            "find-process-mode": "off", "geo-auto-update": False, "profile": {"store-selected": False, "store-fake-ip": False},
            "proxies": [node(kind, closed)],
            "proxy-groups": [{"name": g["name"], "type": "select",
                              "proxies": ["DIRECT" if (g.get("proxies") or [None])[0] == "DIRECT" else NODE]}
                             for g in orig["proxy-groups"]],
        })
        for src, dst in {"geosite.dat": "GeoSite.dat", "geoip.dat": "GeoIP.dat", "geoip.metadb": "geoip.metadb"}.items():
            if os.path.exists(os.path.join(geodata_dir, src)):
                shutil.copy(os.path.join(geodata_dir, src), os.path.join(home, dst))
        cfg = os.path.join(home, "probe.yaml")
        with open(cfg, "w", encoding="utf-8") as f:
            yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False, width=100000)
        logp = os.path.join(home, "log.txt")
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "-d", home, "-f", cfg], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not crr.wait_port(port, proc):
                    raise RuntimeError("mihomo 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                # 测试节点连不通，内核记的是“dial … error”而不是“match”，所以只等日志里出现这个目标
                if not crr.wait_log(logp, lambda: crr.connect_once(port, crr.CANARY, wait=1.0), f"--> {crr.CANARY}:443", proc):
                    raise RuntimeError("mihomo 启动后一直没有处理连接")
                before = {k: len(st.seen) for k, st in stubs.items()}
                fake = {}
                if transport == "udp-fakeip":
                    for h in HOSTS:
                        got = crr.dns_exchange(dns_port, h, 1)
                        ips = got[1] if got else []
                        fake[h] = ips[0] if ips and ipaddress.ip_address(ips[0]) in fake_net else None
                    # 设备查询本身由内核用假地址回答，不应该有替身收到；收到了也照实记下（下面单独列）
                    before_traffic = {k: len(st.seen) for k, st in stubs.items()}
                else:
                    before_traffic = before
                for h in HOSTS:
                    if transport == "tcp":
                        crr.connect_once(port, h, wait=4.0, hold=4.0)
                    elif transport == "udp-domain":
                        socks5_udp(port, h, wait=4.0)
                    else:
                        if fake[h] is None:
                            raise RuntimeError(f"{h} 没有拿到假地址")
                        socks5_udp(port, h, target_ip=fake[h], wait=4.0)
                time.sleep(1.0)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log_text = open(logp, encoding="utf-8", errors="replace").read()
        res = {}
        for h in HOSTS:
            during_query = [k for k, st in stubs.items() if any(q.rstrip(".") == h for q, _ in st.seen[before[k]:before_traffic[k]])]
            during = sorted({(k, t) for k, st in stubs.items() for q, t in st.seen[before_traffic[k]:] if q.rstrip(".") == h})
            who = sorted({k for k, _ in during})
            types = sorted({{1: "A", 28: "AAAA", 65: "HTTPS"}.get(t, str(t)) for _, t in during})
            lines = [ln.split("msg=", 1)[-1].strip().strip('"') for ln in log_text.splitlines()
                     if f"resolve {h} " in ln or f"[DNS] {h} -->" in ln]
            res[h] = {"who": who or ["none"], "types": types, "query_phase": during_query, "log": lines[:4]}
        return res
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(home, ignore_errors=True)


SB_HOSTS = ("qwen.ai", "chatgpt.com", "www.qq.com", "time.windows.com")
SB_NODE = "测试出站"


def sb_outbound(kind: str, port: int):
    """返回 (出站 或 None, 端点 或 None)。"""
    if kind == "socks":
        return {"type": "socks", "tag": SB_NODE, "server": "127.0.0.1", "server_port": port}, None
    if kind == "shadowsocks":
        return {"type": "shadowsocks", "tag": SB_NODE, "server": "127.0.0.1", "server_port": port,
                "method": "aes-128-gcm", "password": "probe"}, None
    if kind == "wireguard":
        key = lambda: base64.b64encode(os.urandom(32)).decode()   # noqa: E731  随机的一次性密钥
        return None, {"type": "wireguard", "tag": SB_NODE, "address": ["172.16.0.2/32"], "private_key": key(), "mtu": 1280,
                      "peers": [{"address": "127.0.0.1", "port": port, "public_key": key(), "allowed_ips": ["0.0.0.0/0"]}]}
    raise ValueError(kind)


def run_singbox_case(binary, srs_dir, kind, transport, config_path=None):
    config_path = config_path or os.path.join(ROOT, "dist", "sing-box", "sing-box-1.14.json")
    conf = json.load(open(config_path, encoding="utf-8"))
    stubs = {tag: crr.DnsStub(tag, crr._Loopback()) for tag in ("dns-cn", "dns-foreign", "dns-local")}
    for srv in conf["dns"]["servers"]:
        if srv["tag"] in stubs:
            port, tag = stubs[srv["tag"]].port, srv["tag"]
            srv.clear()
            srv.update({"type": "udp", "tag": tag, "server": "127.0.0.1", "server_port": port})
    closed = crr.free_port_tcp_udp()
    mixed = crr.free_port_tcp_udp()
    conf["log"] = {"level": "debug", "timestamp": False}
    conf["inbounds"] = [{"type": "mixed", "tag": "probe-in", "listen": "127.0.0.1", "listen_port": mixed}]
    for rs in conf["route"]["rule_set"]:
        if rs["type"] == "remote":
            tag = rs["tag"]
            rs.clear()
            rs.update({"type": "local", "tag": tag, "format": "binary",
                       "path": os.path.abspath(os.path.join(srs_dir, crr.SB_SRS[tag]))})
    conf["route"].pop("auto_detect_interface", None)
    conf.pop("experimental", None)
    conf.pop("http_clients", None)
    conf["route"].pop("default_http_client", None)
    outs = []
    for o in conf["outbounds"]:
        if o["type"] in ("selector", "urltest"):
            direct = o.get("default", (o.get("outbounds") or [None])[0]) == "DIRECT"
            outs.append({"type": "selector", "tag": o["tag"], "outbounds": ["DIRECT" if direct else SB_NODE]})
        else:
            outs.append(o)
    ob, ep = sb_outbound(kind, closed)
    if ob:
        outs.append(ob)
    if ep:
        conf["endpoints"] = [ep]
    conf["outbounds"] = outs
    tmp = tempfile.mkdtemp(prefix="r13-probe-sb-")
    try:
        for st in stubs.values():
            st.start()
        cfg = os.path.join(tmp, "probe.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False)
        logp = os.path.join(tmp, "log.txt")
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "run", "-c", cfg, "-D", tmp, "--disable-color"], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not crr.wait_port(mixed, proc) or not crr.wait_log(logp, lambda: None, "sing-box started", proc):
                    raise RuntimeError("sing-box 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-1200:])
                for h in SB_HOSTS:
                    if transport == "tcp":
                        crr.connect_once(mixed, h, wait=4.0, hold=4.0)
                    else:
                        socks5_udp(mixed, h, wait=4.0)
                time.sleep(1.0)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log_text = open(logp, encoding="utf-8", errors="replace").read()
        res = {}
        for h in SB_HOSTS:
            during = sorted({(k, t) for k, st in stubs.items() for q, t in st.seen if q.rstrip(".") == h})
            who = sorted({k for k, _ in during})
            types = sorted({{1: "A", 28: "AAAA", 65: "HTTPS"}.get(t, str(t)) for _, t in during})
            outbound_lines = [ln.strip()[:160] for ln in log_text.splitlines()
                              if h in ln and ("outbound" in ln or "lookup" in ln or "exchange" in ln)]
            res[h] = {"who": who or ["none"], "types": types, "log": outbound_lines[:3]}
        return res
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    binary, geodata = os.environ["MIHOMO_BIN"], os.environ["GEODATA_DIR"]
    model = load(ROOT, include_local=False)
    mihomo_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "mihomo", "mihomo-core.yaml")
    singbox_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dist", "sing-box", "sing-box-1.14.json")
    config_text = open(mihomo_path, encoding="utf-8").read()
    head = next(ln for ln in config_text.splitlines() if ln.startswith("# 统一源版本"))
    # 统一源版本以配置文件头上写的为准（下一行）：跑 r13 的配置时，工程本身已经是 r14
    ver = subprocess.run([binary, "-v"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"mihomo：{ver}；geodata：{os.environ.get('GEODATA_ORIGIN', geodata)}")
    print(f"配置：{os.path.relpath(mihomo_path, ROOT) if mihomo_path.startswith(ROOT) else os.path.basename(mihomo_path)}"
          f"（{head.lstrip('# ')}）的规则和 DNS 段原样；三类 DNS 换成本机替身；默认直连的组仍直连，其余策略组都换成测试节点。")
    print("结果：收到这个名字查询的替身（system / domestic / foreign），none = 三类替身都没有收到。\n")
    plan = [("socks5", "tcp"), ("socks5", "udp-domain"), ("socks5", "udp-fakeip"),
            ("shadowsocks", "tcp"), ("shadowsocks", "udp-domain"), ("shadowsocks", "udp-fakeip"),
            ("trojan", "udp-domain"),
            ("wireguard", "tcp"), ("wireguard", "udp-domain"),
            ("wireguard+remote-dns", "tcp")]
    label = {"tcp": "TCP", "udp-domain": "UDP（目标写域名）", "udp-fakeip": "UDP（目标是假地址）"}
    for kind, transport in plan:
        res = run_case(binary, geodata, model, config_text, kind, transport)
        print(f"{kind:22s} {label[transport]}")
        for h in HOSTS:
            r = res[h]
            extra = f"（查询类型 {'/'.join(r['types'])}）" if r["types"] else ""
            qp = f"；设备查询那一步收到的替身：{'+'.join(r['query_phase'])}" if r["query_phase"] else ""
            print(f"    {h:14s} → {'+'.join(r['who'])}{extra}{qp}")
            for ln in r["log"]:
                print(f"        日志：{ln[:160]}")
    sb_bin, srs_dir = os.environ["SINGBOX_BIN"], os.environ["SRS_DIR"]
    sb_ver = subprocess.run([sb_bin, "version"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"\nsing-box：{sb_ver}；{os.path.basename(singbox_path)} 的 DNS 规则和路由规则原样；"
          f"dns-cn / dns-foreign / dns-local 换成本机替身；默认直连的组仍直连，其余策略组都换成测试出站。\n")
    for kind, transport in (("socks", "tcp"), ("socks", "udp-domain"), ("shadowsocks", "tcp"), ("shadowsocks", "udp-domain"),
                            ("wireguard", "tcp"), ("wireguard", "udp-domain")):
        res = run_singbox_case(sb_bin, srs_dir, kind, transport, singbox_path)
        print(f"{kind:22s} {label[transport]}")
        for h in SB_HOSTS:
            r = res[h]
            extra = f"（查询类型 {'/'.join(r['types'])}）" if r["types"] else ""
            print(f"    {h:16s} → {'+'.join(r['who'])}{extra}")
            for ln in r["log"]:
                print(f"        日志：{ln}")
    print("\n说明：none 只说明这条路径上没有查询；测试节点连不出去，所以看不到节点真正连通以后的行为。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""一次性核对（2026-10-13，处理 GPT 对 r15 的审核时做的；不参与生成和测试，结果记在 docs/08 第 11 轮）。

r15 的出站核对里，sing-box 1.14.1 经 SOCKS 出口转发“目标写成域名”的 UDP 包时没有发出，内核日志写
`packet upload closed: unsupported address`；1.12.0 能把域名交给节点（docs/03“出站时的解析”）。审核报告第三节说原因没查到底，
建议在能跑的环境里定位：同一个规范的 SOCKS5 接收端，分别发域名和 IPv4 目标，去掉再加回 sniff、resolve、selector；
再用本机配对的服务端看 Shadowsocks / Trojan / VMess。这里照做（虚拟网卡没法在这台机器上开，没有做）。

每一项都是一个最小的 sing-box 配置：mixed 入站（本机端口）→ 路由 → 出口。往 mixed 入站做 SOCKS5 UDP ASSOCIATE，各发一个
目标是域名（udp-probe.example:443）和 IPv4（192.0.2.10:443，文档专用地址）的 UDP 包，看：
  SOCKS 出口：接收端（tools/check_real_routes.py 的 Socks5Recorder，按 RFC 1928 检查报文）收到了什么；
  Shadowsocks / Trojan / VMess 出口：连本机另一个 sing-box（同一版本）的对应入站，看服务端日志里“入站的 UDP 连接到哪里”；
另外都记内核日志里有没有 unsupported address。DNS 只在 resolve 那一项用到（本机替身，给每个名字一个本机地址）。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out

2026-10-15（r18）：内核停下以后，先停下接收端和 DNS 替身（等它们把已经收到的处理完），再读它们的记录——GPT 审核 r17 的
R17-F01 说的那一类问题，这里以前是直接读。handoff/notes/r18_singbox_1143_probes.py 用这里的函数在 sing-box 1.14.3 上再跑一遍。
"""
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_real_routes as crr  # noqa: E402

DOMAIN = "udp-probe.example"
IPV4 = "192.0.2.10"
PASSWORD = "r15-probe-password"
UUID = "b7f3c2a8-3c1e-4c55-9d2e-3f6a1b0c9e11"


def udp_once(port: int, target: str, wait: float = 3.0) -> str:
    """经本机 mixed 入站做 UDP ASSOCIATE，发一个目标为 target:443 的 UDP 包。返回握手结果（ok / 失败原因）。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
            c.settimeout(5)
            c.sendall(b"\x05\x01\x00")
            if c.recv(2) != b"\x05\x00":
                return "SOCKS5 握手失败"
            c.sendall(b"\x05\x03\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
            rep = c.recv(64)
            if len(rep) < 10 or rep[1] != 0:
                return f"UDP ASSOCIATE 失败：{rep!r}"
            relay = (socket.inet_ntoa(rep[4:8]), struct.unpack("!H", rep[8:10])[0])
            if relay[0] == "0.0.0.0":
                relay = ("127.0.0.1", relay[1])
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
                addr = b"\x01" + socket.inet_aton(target)
            else:
                addr = b"\x03" + bytes([len(target)]) + target.encode()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.sendto(b"\x00\x00\x00" + addr + struct.pack("!H", 443) + b"probe", relay)
                time.sleep(wait)
            return "ok"
    except OSError as e:
        return f"{type(e).__name__}: {e}"


def start(binary: str, conf: dict, tmp: str, name: str, port: int):
    cfg = os.path.join(tmp, name + ".json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False)
    logp = os.path.join(tmp, name + ".log")
    log = open(logp, "w", encoding="utf-8")
    proc = subprocess.Popen([binary, "run", "-c", cfg, "-D", tmp, "--disable-color"], stdout=log, stderr=subprocess.STDOUT)
    if not crr.wait_port(port, proc) or not crr.wait_log(logp, lambda: None, "sing-box started", proc):
        proc.terminate()
        log.close()
        with open(logp, encoding="utf-8", errors="replace") as f:
            raise RuntimeError(f"{name} 没有启动成功：" + f.read()[-600:])
    return proc, log, logp


def stop(proc, log) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


def read(logp: str) -> str:
    with open(logp, encoding="utf-8", errors="replace") as f:
        return f.read()


def client_conf(mixed: int, outbound: dict, rules: list, final: str, selector, dns_port: int = None) -> dict:
    """selector：False = 路由直接交给出口；True = 中间隔一个只含这个出口的选择组；"urltest" = 隔一个自动测速组。"""
    outs = [outbound]
    if selector == "urltest":
        outs.append({"type": "urltest", "tag": "sel", "outbounds": [outbound["tag"]], "url": "http://127.0.0.1:1/", "interval": "10m"})
    elif selector:
        outs.append({"type": "selector", "tag": "sel", "outbounds": [outbound["tag"]]})
    conf = {"log": {"level": "debug", "timestamp": False},
            "inbounds": [{"type": "mixed", "tag": "in", "listen": "127.0.0.1", "listen_port": mixed}],
            "outbounds": outs,
            "route": {"rules": rules, "final": "sel" if selector else final}}
    if dns_port:
        conf["dns"] = {"servers": [{"type": "udp", "tag": "stub", "server": "127.0.0.1", "server_port": dns_port}]}
    return conf


def socks_variants(binary: str) -> None:
    variants = [("最简（没有路由规则，final 直接是 SOCKS 出口）", [], False, False),
                ("加 selector（final 是只含 SOCKS 出口的选择组）", [], True, False),
                ("加 sniff（路由第一条是 sniff 动作）", [{"action": "sniff"}], False, False),
                ("sniff + selector", [{"action": "sniff"}], True, False),
                ("加 resolve（路由第一条是 resolve 动作，交给本机 DNS 替身）", [{"action": "resolve", "server": "stub"}], False, True),
                ("resolve + selector（先解析成地址，再交给选择组）", [{"action": "resolve", "server": "stub"}], True, True),
                ("selector 换成 urltest（final 是只含 SOCKS 出口的自动测速组）", [], "urltest", False)]
    for title, rules, selector, use_dns in variants:
        answers = crr._PerHostLoopback([DOMAIN])
        stub = crr.DnsStub("stub", answers) if use_dns else None
        rec = crr.Socks5Recorder()
        tmp = tempfile.mkdtemp(prefix="r15-probe-")
        mixed = crr.free_port_tcp_udp()
        try:
            rec.start()
            if stub:
                stub.start()
            conf = client_conf(mixed, {"type": "socks", "tag": "node", "server": "127.0.0.1", "server_port": rec.port},
                               rules, "node", selector, stub.port if stub else None)
            proc, log, logp = start(binary, conf, tmp, "client", mixed)
            try:
                hs = {t: udp_once(mixed, t) for t in (DOMAIN, IPV4)}
                time.sleep(1.0)
            finally:
                stop(proc, log)
            if not rec.stop():
                raise RuntimeError("接收端没有停下，收到的包可能没有记全")
            if stub:
                crr.close_stubs([stub])
            text = read(logp)
            udp = [(k, a) for t, k, a in rec.seen if t == "udp"]
            print(f"  {title}")
            print(f"    客户端握手：域名 {hs[DOMAIN]}，IPv4 {hs[IPV4]}")
            print(f"    接收端收到的 UDP 包（类型, 目标）：{udp or '没有'}；不合规的报文：{rec.invalid or '没有'}")
            if stub:
                print(f"    DNS 替身收到的查询：{[q for q, _ in stub.seen] or '没有'}（{DOMAIN} 的回答是 {answers.get(DOMAIN)}）")
            bad = [ln.strip() for ln in text.splitlines() if "unsupported address" in ln]
            print(f"    日志里的 unsupported address：{len(bad)} 行" + (f"，例如 {bad[0][:160]}" if bad else ""))
        except Exception as e:                        # noqa: BLE001  一次性核对：一项失败照样跑下一项
            print(f"  {title}：没有跑成（{type(e).__name__}: {e}）")
        finally:
            rec.stop()
            if stub:
                stub.stop()
            shutil.rmtree(tmp, ignore_errors=True)


def make_cert(tmp: str):
    crt, key = os.path.join(tmp, "probe.crt"), os.path.join(tmp, "probe.key")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-keyout", key, "-out", crt, "-days", "1", "-subj", "/CN=probe.local"],
                   check=True, capture_output=True)
    return crt, key


def paired_variants(binary: str, selector: bool) -> None:
    """客户端出口连本机另一个 sing-box 的对应入站；服务端的路由直接拒绝（不往外发），只看它的日志里入站的 UDP 连接去哪。
    selector：客户端的路由和出口之间隔不隔一个选择组（本项目的配置里，规则交给的都是选择组）。"""
    for proto in ("shadowsocks", "trojan", "vmess"):
        tmp = tempfile.mkdtemp(prefix="r15-pair-")
        mixed, srv_port = crr.free_port_tcp_udp(), crr.free_port_tcp_udp()
        try:
            inbound = {"type": proto, "tag": "srv-in", "listen": "127.0.0.1", "listen_port": srv_port}
            outbound = {"type": proto, "tag": "node", "server": "127.0.0.1", "server_port": srv_port}
            if proto == "shadowsocks":
                inbound.update({"method": "aes-128-gcm", "password": PASSWORD})
                outbound.update({"method": "aes-128-gcm", "password": PASSWORD})
            elif proto == "trojan":
                crt, key = make_cert(tmp)
                inbound.update({"users": [{"name": "probe", "password": PASSWORD}],
                                "tls": {"enabled": True, "certificate_path": crt, "key_path": key}})
                outbound.update({"password": PASSWORD, "tls": {"enabled": True, "server_name": "probe.local", "insecure": True}})
            else:
                inbound.update({"users": [{"name": "probe", "uuid": UUID, "alterId": 0}]})
                outbound.update({"uuid": UUID, "security": "auto", "alter_id": 0})
            server = {"log": {"level": "debug", "timestamp": False}, "inbounds": [inbound],
                      "outbounds": [{"type": "direct", "tag": "direct"}],
                      "route": {"rules": [{"action": "reject"}], "final": "direct"}}
            sproc, slog, slogp = start(binary, server, tmp, "server", srv_port)
            try:
                cproc, clog, clogp = start(binary, client_conf(mixed, outbound, [], "node", selector), tmp, "client", mixed)
                try:
                    hs = {t: udp_once(mixed, t) for t in (DOMAIN, IPV4)}
                    time.sleep(1.0)
                finally:
                    stop(cproc, clog)
            finally:
                stop(sproc, slog)
            stext, ctext = read(slogp), read(clogp)
            got = sorted(set(re.findall(r"inbound packet connection to (\S+)", stext)))
            bad = [ln.strip() for ln in (ctext + stext).splitlines() if "unsupported address" in ln]
            print(f"  {proto}{'（隔一个选择组）' if selector else ''}：客户端握手 域名 {hs[DOMAIN]}、IPv4 {hs[IPV4]}；服务端日志里入站的 UDP 连接去：{got or '没有'}；"
                  f"unsupported address {len(bad)} 行" + (f"，例如 {bad[0][:160]}" if bad else ""))
        except Exception as e:                        # noqa: BLE001
            print(f"  {proto}：没有跑成（{type(e).__name__}: {e}）")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    for label, env in (("sing-box 1.14.1", "SINGBOX_BIN"), ("sing-box 1.12.0", "SINGBOX112_BIN")):
        binary = os.environ.get(env)
        if not binary or not os.path.exists(binary):
            print(f"{label}：没有找到（{env}），跳过")
            continue
        version = subprocess.run([binary, "version"], capture_output=True, text=True).stdout.splitlines()[0]
        print(f"{label}（{version}）")
        print(" SOCKS 出口 → 本机 SOCKS5 接收端：")
        socks_variants(binary)
        print(" 配对的服务端（同一版本；服务端只记日志、一律拒绝）：")
        paired_variants(binary, False)
        paired_variants(binary, True)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

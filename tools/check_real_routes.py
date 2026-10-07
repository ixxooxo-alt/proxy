#!/usr/bin/env python3
"""用官方内核和真实的上游数据文件，核对“每个主机最后交给哪个组、sing-box 的 DNS 查询交给谁”。

为什么要有这个工具（2026-10-03 GPT 审核 F01）：以前的路由测试里，“国内域名集合”“广告集合”只是几条样本，
所以统一源里写着“qwen.ai 落入国外默认”、而真实的国内域名集合收了 qwen.ai 这件事，测试看不出来。
这个工具把 tests/cases.yaml 的全部路由用例（含“跟随上游数据的已知行为”一节）、统一源里写了去向的排除项，
交给官方内核和真实数据实际判断一遍。

做了什么：
  1. mihomo：规则原样，所有策略组的出口换成 REJECT（直接写 DIRECT 的规则换成一个同样指向 REJECT 的替身组），
     只开本机回环上的一个临时端口，对每个主机发一次 CONNECT，从日志里读“命中了哪条规则、交给哪个组”。
  2. sing-box：路由规则、DNS 规则原样；远程规则集换成本地的 .srs 文件，直连出站换成 block，TUN 入站换成本机回环上的
     一个代理端口和一个 DNS 端口，三个 DNS 服务器换成本机的替身（只记录收到了什么查询）。
     对每个主机发一次 CONNECT 读路由结果；对 tests/cases.yaml 的 singbox_dns 用例各发一次查询，看是哪个 DNS 服务器接的。
  3. sing-box 拨号时的解析（2026-10-04 审核 r9 的 F02）：上面第 2 步把直连出站换成了 block、也没有节点，碰不到
     “节点连接自己的服务器 / 直连出站连接域名形式的目标时，名字交给哪个 DNS 服务器解析”这条路。这一步另起一次内核：
     配置里带几个节点（服务器地址取自 tests/cases.yaml 的 singbox_dial），直连出站保持原样，拨号是真的；
     DNS 替身不管问什么都答 127.0.0.1，节点端口是本机一个没人监听的端口，所以每次拨号都是连本机被拒绝，不会连到外面。
  4. mihomo 里名字交给哪一类 DNS 解析（2026-10-05 审核 r10 的 R10-F01）：第 1 步把出口都换成了 REJECT、也没有节点，
     同样碰不到拨号。这一步另起一次内核：规则、DNS 段的结构原样；系统 DNS、国内 DNS、境外 DNS 三类服务器各换成一个本机替身
     （都答 127.0.0.1）；加几个节点（服务器地址取自 tests/cases.yaml 的 mihomo_dial，端口是本机一个没人监听的端口），直连保持直连。
     看的是：节点服务器的名字、域名形式的直连目标（mihomo_dial），以及设备发来的 DNS 查询（mihomo_dns，r11 时只有和局域网名字
     有关的几条，之后加的见第 5 步），各是哪一类替身收到的。再把三处有关的设置各去掉一处重跑，确认每一处只管它自己那条路。
  5. “国外的连接，名字不要让国内 DNS 看到”的三项固定核对（2026-10-06）。用的还是第 3、4 步的办法，用例多了两类
     （tests/cases.yaml 的 singbox_dial / mihomo_dial 里 kind: proxied、unlisted，mihomo_dns 里后加的几条）：
       走代理组的域名——规则判断时不解析，三个 DNS 替身都收不到它；
       没被任何域名规则接住的域名——只有境外 DNS 的替身收到；
       境外 DNS 不应答——把境外替身改成只收不答、每个连接保持 14 秒（比内核的 DNS 超时长）重跑一遍，
       收到查询的替身必须和正常那一遍相同：内核没有转去问国内 / 系统 DNS。只试了“只收不答”这一种失败方式（替身是 UDP 的），
       连接被重置、证书错误、SERVFAIL 这些没有试，结论不能直接推到真实的 DoH 故障上。
  5b. 出站时的解析（2026-10-07，GPT 审核 r13 的 R13-F01）：第 4、5 步把走代理的组换成了 REJECT，拒绝出口不拨号，
     看不到“出口自己为连接解析目标”。这一步把它们换成真的出口（SOCKS5 / WireGuard，连本机一个没人监听的端口），
     分别发 TCP 连接和 UDP 包（tests/cases.yaml 的 outbound_resolve），看目标域名有没有被拿去解析、交给了哪一类 DNS。
     mihomo 转发 UDP、经 WireGuard 出口时都会在本机解析目标；sing-box 的代理出站把域名交给节点，WireGuard 端点按 DNS 规则解析。
     再把 mihomo 的 nameserver-policy 里“走代理组的产品域名”那一层去掉重跑，确认这项核对看得出它。
  6. 国内 DNS 与路由的逐条扫描（2026-10-06，tools/dns_route_consistency.py；r12 时叫“全集一致性”）：把“名字会交给国内 DNS”的集合
     逐条取代表主机扫一遍，看路由有没有把其中哪个交给代理组；不一致的主机和抽出来的一批主机再交给官方内核核对。
  7. 把同一批主机在各个集合里的成员关系，连同上面几步的结果，记成快照（--write-snapshot → tests/data/real_sets.json）。
     sing-box 两个版本的官方记录分开存（1.14 的在 official.singbox，1.12 的在 official.singbox112）。
     tests/test_real_data.py 用这份快照离线重跑全部用例，并核对“模拟器 = 官方内核的记录 = 人工写的期望”。
全程不联网：路由核对的出口都是 REJECT / block，拨号核对的每次拨号都落在 127.0.0.1；DNS 查询只到本机替身。
路由核对的解析结果用 tests/fixtures.yaml 里假定的（没列出的按境外 IP 算）。
不开 TUN、不设系统代理、不读也不改正在使用的代理配置。

Loon / Quantumult X 没有可以在电脑上运行的官方内核，这里只把它们订阅的上游规则文件（blackmatrix7 的固定快照：
远程广告集合；Loon 严格版另订阅的国内域名集合 ChinaMax_Domain）读进来记进快照，路由结果仍由模拟器按官方文档描述的
匹配顺序推算——不是这两个 App 的实测。标准版和严格版（2026-10-06）各算一遍；严格版引用的自有远程规则文件用这次生成的内容。
读这些上游文件时另数一件事：Loon 订阅的文件里，按 IP 判断的规则是不是都带 no-resolve。Loon 严格版靠“全部 IP 规则都不为域名解析”
成立，本地规则由写盘前的结构检查管，上游文件里的只能在这里数；有不带的算不符合（模拟器是按“都带”算的）。

用法：
  python3 tools/check_real_routes.py --mihomo <mihomo> --singbox <sing-box 1.14> [--singbox-112 <sing-box 1.12>] \\
      --geodata-dir <MetaCubeX 的 geosite.dat / geoip.dat / geoip.metadb 所在目录> \\
      --srs-dir <SagerNet 的 geosite-cn.srs 等四个文件所在目录> \\
      --bm7 <blackmatrix7/ios_rule_script 的检出目录> [--dlc <domain-list-community 的检出目录>] \\
      [--geodata-origin 文字] [--srs-origin 文字] [--bm7-origin 文字] [--write-snapshot]
数据文件怎么来：
  geodata：MetaCubeX/meta-rules-dat 的发布文件（mihomo 配置里 geox-url 指向的就是它）。
  srs：SagerNet/sing-geosite 与 sing-geoip 的 rule-set 分支（配置里远程规则集的地址）；需要
       geosite-category-ads-all.srs、geosite-cn.srs、geosite-geolocation-!cn.srs、geoip-cn.srs。
  bm7：需要 rule/Loon/AdvertisingLite/、rule/QuantumultX/AdvertisingLite/、rule/Loon/ChinaMax/ 三个目录。
上游数据每天都在变：结论只对这次用到的文件成立，文件的 SHA-256 会打印出来并写进快照。
退出码：0 全部一致；1 有不一致；2 参数或环境问题。
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build as builder  # noqa: E402
import dns_route_consistency as drc  # noqa: E402
import emulate  # noqa: E402  （tests/emulate.py：自制模拟器，这里拿它和官方内核的结果对比）
import real_data as rd  # noqa: E402
from generator import emit_mihomo, emit_singbox  # noqa: E402
from generator import strict as strict_mod  # noqa: E402
from generator.model import build_plan, load  # noqa: E402
from generator.util import safe_stdout, sha256_text  # noqa: E402

DEFAULT_FOREIGN_IP = "203.0.113.77"       # 文档用保留地址（TEST-NET-3）：没在 fixtures 里列出的主机一律解析到它，当作“境外 IP”
DIRECT_STANDIN = "直连替身"
NONE = "none"                             # 拨号 / 连接用例的结果：没有任何一个 DNS 替身收到关于这个名字的查询
SILENT_HOLD = 14.0                        # “境外 DNS 只收不答”那一遍，每个连接保持这么多秒：mihomo 的 DNS 超时是 5 秒，sing-box 是 10 秒
SAMPLE_SIZE = 200                         # 逐条扫描：除了不一致的主机，另外抽多少个一致的主机交给官方内核核对
SB_SRS = {"geosite-category-ads-all": "geosite-category-ads-all.srs", "geosite-cn": "geosite-cn.srs",
          "geosite-geolocation-!cn": "geosite-geolocation-!cn.srs", "geoip-cn": "geoip-cn.srs"}


def run(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def free_port_tcp_udp() -> int:
    """TCP 和 UDP 上都空着的一个端口（mihomo 的 dns.listen 两种都监听）。"""
    for _ in range(50):
        port = free_port()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise RuntimeError("找不到 TCP、UDP 都空着的本机端口")


def hostport(target: str) -> str:
    return f"[{target}]:443" if ":" in target else f"{target}:443"


# ---------------------------------------------------------------------------
# 本机 DNS 替身
# ---------------------------------------------------------------------------

def _skip_name(data: bytes, i: int) -> int:
    """跳过从 i 开始的一个域名，返回它后面的位置。域名是一串标签，以 0 结束，或者以一个压缩指针（高两位是 11、占两个字节）
    结束——指针可以出现在任何一个标签边界上，例如“cdn + 指向 example.com 的指针”（RFC 1035 第 4.1.4 节）。
    只跳过、不展开指针：这里只需要找到名字后面的类型和长度。高两位是 01 / 10 的保留写法、越界，都按读不懂处理。
    2026-10-07 处理 GPT 对 r13 的审核（R13-F04）时改的：以前只看名字的第一个字节是不是指针，“标签 + 指针”这种合法的
    写法会读错，正常的 CNAME + A 应答被报成 rcode--1。"""
    while True:
        n = data[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:
            if i + 1 >= len(data):
                raise IndexError("压缩指针不完整")
            return i + 2
        if n & 0xC0:
            raise ValueError("保留的标签类型")
        i += n + 1


def _parse_question(data: bytes):
    """读问题区的名字和类型。查询里的名字是问题区的第一个名字，前面没有可指向的内容，不会用压缩指针。"""
    i, labels = 12, []
    while data[i]:
        n = data[i]
        labels.append(data[i + 1:i + 1 + n].decode("ascii", "replace"))
        i += n + 1
    qtype = struct.unpack("!H", data[i + 1:i + 3])[0]
    return ".".join(labels).lower(), qtype, i + 5


class DnsStub(threading.Thread):
    """只监听 127.0.0.1 的 UDP 端口。A 查询按 answers 作答（没有的给 DEFAULT_FOREIGN_IP），其他类型回空应答；
    记录收到的每一次查询。silent=True 时只记录、不回答（模拟“这个 DNS 服务器不应答”）。"""

    def __init__(self, name: str, answers: dict, silent: bool = False):
        super().__init__(daemon=True)
        self.label, self.answers, self.seen, self.silent = name, answers, [], silent
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]

    def run(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except OSError:
                return
            try:
                qname, qtype, end = _parse_question(data)
            except (IndexError, struct.error):
                continue
            self.seen.append((qname, qtype))
            if self.silent:
                continue
            ip = self.answers.get(qname, DEFAULT_FOREIGN_IP)
            answer = b""
            if qtype == 1 and ":" not in ip:
                answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton(ip)
            head = data[:2] + b"\x81\x80\x00\x01" + (b"\x00\x01" if answer else b"\x00\x00") + b"\x00\x00\x00\x00"
            try:
                self.sock.sendto(head + data[12:end] + answer, addr)
            except OSError:
                return

    def close(self):
        self.sock.close()


def dns_query(port: int, host: str, qtype: int):
    """向本机端口发一次查询，返回应答里的 A / AAAA 记录地址列表（没应答返回 None）。"""
    got = dns_exchange(port, host, qtype)
    return None if got is None else got[1]


def dns_exchange(port: int, host: str, qtype: int):
    """向本机端口发一次查询，返回 (应答码, 应答里的 A / AAAA 记录地址列表, 应答里的记录总数)；没应答返回 None。
    记录总数把别的类型（HTTPS、TXT、CNAME……）也算进去：“空应答”要看它是不是 0，不能只看地址列表
    （2026-10-07 以前只读 A 记录，应答里只有 AAAA 或别的记录时会被当成空应答，见 reply_kind）。"""
    q = struct.pack("!HHHHHH", 0x2468, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode("ascii") for p in host.split(".")) + b"\x00" + struct.pack("!HH", qtype, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(5)
        s.sendto(q, ("127.0.0.1", port))
        try:
            data, _ = s.recvfrom(4096)
        except OSError:
            return None
    try:
        rcode = struct.unpack("!H", data[2:4])[0] & 0x0F
        count = struct.unpack("!H", data[6:8])[0]
        _, _, i = _parse_question(data)
        ips = []
        for _ in range(count):
            i = _skip_name(data, i)
            rtype, _, _, rlen = struct.unpack("!HHIH", data[i:i + 10])
            i += 10
            if rtype == 1:
                ips.append(socket.inet_ntoa(data[i:i + 4]))
            elif rtype == 28:
                ips.append(socket.inet_ntop(socket.AF_INET6, data[i:i + 16]))
            i += rlen
            if i > len(data):
                raise IndexError("记录比应答长")
        return rcode, ips, count
    except (IndexError, struct.error, ValueError):
        return -1, [], 0                      # 读不懂这个应答（reply_kind 记成 unparsed）


def reply_kind(reply, fake_net) -> str:
    """内核自己回答的一次查询（没有任何替身收到它）算哪一种：no-reply（没有应答）、unparsed（应答读不懂）、
    fake-ip（地址全在假地址段里）、
    empty（应答码正常、一条记录都没有）、rcode-N（别的应答码）、answer:地址（有 A / AAAA 记录、不是假地址）、
    records:N（有 N 条记录、都不是地址，例如 HTTPS 记录）。
    2026-10-07 处理 GPT 对 r12 的审核时发现：以前 dns_exchange 只读 A 记录，这里按“没有 A 记录”判 empty，
    所以 AAAA 查询拿到地址、HTTPS 查询拿到记录时也会被记成 empty。r12 的快照里没有 AAAA 类型的用例，文档里“AAAA 为空”
    那句话没有用这个工具实际看过；2026-10-07 修了这里、加了一条 AAAA 用例（tests/cases.yaml 的 mihomo_dns）。"""
    if reply is None:
        return "no-reply"
    rcode, ips, count = reply
    if rcode == -1:
        return "unparsed"                     # 应答格式读不懂（2026-10-07 以前会显示成 rcode--1，看不出是工具没读懂）
    if ips and all(ipaddress.ip_address(x) in fake_net for x in ips):
        return "fake-ip"
    if rcode == 0 and count == 0:
        return "empty"
    if rcode:
        return f"rcode-{rcode}"
    return "answer:" + ",".join(ips) if ips else f"records:{count}"


def connect_once(port: int, target: str, wait: float = 6.0, hold: float = 0.0) -> None:
    """经本机代理端口发一次 CONNECT。hold > 0 时收到应答以后不马上断开，最多再保持这么多秒（对方先断开就结束）：
    内核通常先回 200 再去判断规则、解析、拨号，客户端一断开，后面的事可能跟着取消——要看“DNS 超时以后内核做了什么”，
    就得让这个连接一直开着。"""
    hp = hostport(target)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.settimeout(wait)
            s.sendall(f"CONNECT {hp} HTTP/1.1\r\nHost: {hp}\r\n\r\n".encode())
            try:
                s.recv(1024)
            except OSError:
                pass
            end = time.time() + hold
            while hold and time.time() < end:
                s.settimeout(max(0.1, end - time.time()))
                try:
                    if not s.recv(1024):
                        break
                except socket.timeout:
                    break
                except OSError:
                    break
    except OSError:
        pass


def wait_port(port: int, proc, seconds: float = 30) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


CANARY = "startup-canary.invalid"


def wait_log(logp: str, poke, needle: str, proc, seconds: float = 60) -> bool:
    """反复执行 poke()，直到日志里出现 needle。"""
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        poke()
        with open(logp, encoding="utf-8", errors="replace") as f:
            if needle in f.read():
                return True
        time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# mihomo
# ---------------------------------------------------------------------------

def mihomo_probe(binary: str, geodata_dir: str, config_text: str, targets: list, dns_map: dict) -> dict:
    """返回 {目标: (命中的规则, 交给的组)}。规则原样；组的出口都是 REJECT。"""
    orig = yaml.safe_load(config_text)
    rules = []
    for line in orig["rules"]:
        parts = [x.strip() for x in line.split(",")]
        i = 1 if parts[0] == "MATCH" else 2
        if parts[i] == "DIRECT":
            parts[i] = DIRECT_STANDIN
        rules.append(",".join(parts))
    stub = DnsStub("mihomo-dns", dns_map)
    stub.start()
    port = free_port()
    conf = {
        "mixed-port": port, "allow-lan": False, "bind-address": "127.0.0.1", "mode": "rule", "log-level": "info",
        "ipv6": True, "geodata-mode": bool(orig.get("geodata-mode", False)), "geo-auto-update": False,
        "dns": {"enable": True, "ipv6": False, "nameserver": [f"127.0.0.1:{stub.port}"],
                "default-nameserver": [f"127.0.0.1:{stub.port}"]},
        "sniffer": {"enable": False},
        "proxy-groups": [{"name": g["name"], "type": "select", "proxies": ["REJECT"]} for g in orig["proxy-groups"]]
                        + [{"name": DIRECT_STANDIN, "type": "select", "proxies": ["REJECT"]}],
        "rules": rules,
    }
    home = tempfile.mkdtemp(prefix="real-mihomo-")
    try:
        for src, dst in {"geosite.dat": "GeoSite.dat", "geoip.dat": "GeoIP.dat", "geoip.metadb": "geoip.metadb",
                         "country.mmdb": "Country.mmdb", "GeoLite2-ASN.mmdb": "GeoLite2-ASN.mmdb"}.items():
            p = os.path.join(geodata_dir, src)
            if os.path.exists(p):
                shutil.copy(p, os.path.join(home, dst))
        cfg = os.path.join(home, "probe.yaml")
        with open(cfg, "w", encoding="utf-8") as f:
            yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False, width=100000)
        logp = os.path.join(home, "log.txt")
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "-d", home, "-f", cfg], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not wait_port(port, proc):
                    raise RuntimeError("mihomo 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                # 端口先于规则引擎就绪：先反复发一个试探连接，直到日志里出现它的匹配结果，再发正式的
                if not wait_log(logp, lambda: connect_once(port, CANARY, wait=1.0), f"--> {CANARY}:443 match", proc):
                    raise RuntimeError("mihomo 启动后一直没有处理连接：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                for t in targets:
                    connect_once(port, t)
                time.sleep(1.0)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        got = {}
        with open(logp, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.search(r"--> (\S+) match (.+?) using (.+?)\"?\s*$", line)
                if m:
                    group = m.group(3).split("[")[0]
                    got.setdefault(m.group(1), (m.group(2), "DIRECT" if group == DIRECT_STANDIN else group))
        return {t: got.get(hostport(t)) for t in targets}
    finally:
        stub.close()
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# sing-box
# ---------------------------------------------------------------------------

QTYPE = {"A": 1, "AAAA": 28, "HTTPS": 65, "TXT": 16}


def singbox_probe(binary: str, srs_dir: str, config_text: str, targets: list, dns_cases: list, dns_map: dict,
                  silent: tuple = (), hold: float = 0.0):
    """返回 (路由 {目标: (命中的规则, 出站)}, DNS {(主机, 类型): 服务器标签})。
    silent：这几个标签的 DNS 替身只收不答。hold > 0 时，查询都发完以后再等这么多秒，然后按“整个过程里哪些替身收到过
    这个名字这个类型的查询”重新认一遍——超时以后有没有改问别的服务器，只有这样才看得到。这种用法下 targets 要留空
    （连接也会引起查询，会和查询用例混在一起）。"""
    if hold and targets:
        raise ValueError("hold 只用于单独核对 DNS 查询，targets 要留空")
    conf = json.loads(config_text)
    stubs = {tag: DnsStub(tag, dns_map, silent=tag in silent) for tag in ("dns-cn", "dns-foreign", "dns-local")}
    for st in stubs.values():
        st.start()
    fake_net = None
    for srv in conf["dns"]["servers"]:
        if srv["tag"] in stubs:
            port = stubs[srv["tag"]].port
            tag = srv["tag"]
            srv.clear()
            srv.update({"type": "udp", "tag": tag, "server": "127.0.0.1", "server_port": port})
        elif srv.get("type") == "fakeip":
            fake_net = ipaddress.ip_network(srv["inet4_range"])
    mixed, dns_in = free_port(), free_port(socket.SOCK_DGRAM)
    conf["log"] = {"level": "debug", "timestamp": False}
    conf["inbounds"] = [{"type": "mixed", "tag": "probe-in", "listen": "127.0.0.1", "listen_port": mixed},
                        {"type": "direct", "tag": "dns-in", "listen": "127.0.0.1", "listen_port": dns_in, "network": "udp"}]
    for o in conf["outbounds"]:
        if o["type"] == "direct":
            o["type"] = "block"                 # 直连出站也换成拒绝：不发起任何对外连接
    for rs in conf["route"]["rule_set"]:
        if rs["type"] == "remote":
            tag = rs["tag"]
            rs.clear()
            rs.update({"type": "local", "tag": tag, "format": "binary",
                       "path": os.path.abspath(os.path.join(srs_dir, SB_SRS[tag]))})
    conf["route"].pop("auto_detect_interface", None)
    conf.pop("experimental", None)              # 不写缓存文件
    final = conf["route"]["final"]
    tmp = tempfile.mkdtemp(prefix="real-singbox-")
    try:
        cfg = os.path.join(tmp, "probe.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False)
        logp = os.path.join(tmp, "log.txt")
        dns_got = {}
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "run", "-c", cfg, "-D", tmp, "--disable-color"], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not wait_port(mixed, proc) or not wait_log(logp, lambda: None, "sing-box started", proc):
                    raise RuntimeError("sing-box 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                for c in dns_cases:
                    before = {k: len(v.seen) for k, v in stubs.items()}
                    ips = dns_query(dns_in, c["host"], QTYPE[c["type"]])
                    time.sleep(0.05)
                    asked = [k for k, v in stubs.items() if len(v.seen) > before[k]]
                    if ips and fake_net is not None and all(ipaddress.ip_address(x) in fake_net for x in ips):
                        where = "dns-fakeip" if not asked else "dns-fakeip+" + "+".join(asked)
                    elif len(asked) == 1:
                        where = asked[0]
                    else:
                        where = "+".join(asked) if asked else ("没有应答" if ips is None else "没有服务器收到查询")
                    dns_got[(c["host"], c["type"])] = where
                if hold:
                    time.sleep(hold)
                    for c in dns_cases:
                        late = sorted(k for k, v in stubs.items() if (c["host"].lower(), QTYPE[c["type"]]) in v.seen)
                        if late:
                            dns_got[(c["host"], c["type"])] = "+".join(late)
                # 每个连接要等嗅探超时（没有后续数据），所以并发着发；按日志里的连接编号对应回去
                with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
                    list(pool.map(lambda t: connect_once(mixed, t), targets))
                time.sleep(1.0)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        conn_target, conn_result = {}, {}
        with open(logp, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.search(r"\[(\d+) [^\]]*\] inbound/mixed\[probe-in\]: inbound connection to (\S+)\s*$", line)
                if m:
                    conn_target[m.group(1)] = m.group(2)
                    continue
                m = re.search(r"\[(\d+) [^\]]*\] router: match\[\d+\] ?(.*?) => (route\((.+)\)|reject)\s*$", line)
                if m and m.group(1) not in conn_result:
                    conn_result[m.group(1)] = (m.group(2).strip()[:120], m.group(4) if m.group(4) else "REJECT")
        routes = {}
        for cid, hp in conn_target.items():
            routes.setdefault(hp, conn_result.get(cid, ("没有规则命中（route.final）", final)))
        return {t: routes.get(hostport(t)) for t in targets}, dns_got
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(tmp, ignore_errors=True)


class _Loopback(dict):
    """拨号核对用的 DNS 应答：不管问什么名字都答 127.0.0.1，所以拨号不会离开本机。"""

    def get(self, key, default=None):
        return "127.0.0.1"


def singbox_dial_probe(binary: str, srs_dir: str, model, plan, variant: str, cases: list, strip_fix: bool = False,
                       silent: tuple = (), hold: float = 0.0) -> dict:
    """sing-box 处理一个连接的过程里，名字交给哪个 DNS 服务器解析（2026-10-04 审核 r9 的 F02）。返回 {用例的键: 结果}。
    结果是收到这个名字的查询的替身的标签；一个都没有收到记 none（2026-10-06 加的 kind: proxied 期望的就是它）。
    silent：这几个标签的替身只收不答；hold：每个连接保持多少秒不断开（见 connect_once）。两个一起用，
    看“这个 DNS 服务器不应答时，内核会不会转去问别的”。

    上面的 singbox_probe 把直连出站换成了 block、没有节点，所以碰不到“拨号时解析”这条路。这里单独起一次内核：
      - 配置由生成器带着几个节点生成（节点的服务器地址取自用例），直连出站保持原样，拨号过程是真的；
      - 三个 DNS 服务器换成本机替身，不管问什么都答 127.0.0.1；节点的端口是本机一个没人监听的端口——
        所以每次拨号最后都是连 127.0.0.1 被拒绝，不会有任何连接离开本机；
      - 每个节点配一条只给它用的路由规则，发一次 CONNECT 让内核去连这个节点；直连用例直接 CONNECT 那个主机；
      - 看替身：节点服务器的名字、直连目标的名字，分别是哪个替身收到的查询。
    strip_fix=True 时把这一版加的两处修正拿掉（节点上的 domain_resolver、局域网后缀的 resolve 规则），用来确认
    这项核对对它要防的错误是敏感的。"""
    node_cases = [c for c in cases if c["kind"] == "node"]
    closed = free_port()                                   # 取到就放掉：没人监听，连上去立刻被拒绝
    # 配置由 real_data.singbox_dial_base 生成：测试里核对“拨号记录对应现在的配置”时用的是同一个函数
    conf, tag_of = rd.singbox_dial_base(model, plan, variant, cases, closed)
    if strip_fix:
        for o in conf["outbounds"]:
            o.pop("domain_resolver", None)
        conf["route"]["rules"] = [r for r in conf["route"]["rules"]
                                  if not (r.get("action") == "resolve" and r.get("server") == emit_singbox.LOCAL_DNS_TAG)]
    stubs = {tag: DnsStub(tag, _Loopback(), silent=tag in silent) for tag in ("dns-cn", "dns-foreign", "dns-local")}
    for st in stubs.values():
        st.start()
    for srv in conf["dns"]["servers"]:
        if srv["tag"] in stubs:
            port, tag = stubs[srv["tag"]].port, srv["tag"]
            srv.clear()
            srv.update({"type": "udp", "tag": tag, "server": "127.0.0.1", "server_port": port})
    mixed = free_port()
    conf["log"] = {"level": "debug", "timestamp": False}
    conf["inbounds"] = [{"type": "mixed", "tag": "probe-in", "listen": "127.0.0.1", "listen_port": mixed}]
    for rs in conf["route"]["rule_set"]:
        if rs["type"] == "remote":
            tag = rs["tag"]
            rs.clear()
            rs.update({"type": "local", "tag": tag, "format": "binary",
                       "path": os.path.abspath(os.path.join(srs_dir, SB_SRS[tag]))})
    conf["route"].pop("auto_detect_interface", None)
    conf.pop("experimental", None)
    probe_host = {c["server"]: f"dial-probe-{i + 1}.invalid" for i, c in enumerate(node_cases)}
    conf["route"]["rules"] = ([{"domain": [probe_host[c["server"]]], "outbound": tag_of[c["server"]]} for c in node_cases]
                              + conf["route"]["rules"])
    targets = [probe_host[c["server"]] if c["kind"] == "node" else c["host"] for c in cases]
    tmp = tempfile.mkdtemp(prefix="dial-singbox-")
    try:
        cfg = os.path.join(tmp, "probe.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False)
        logp = os.path.join(tmp, "log.txt")
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "run", "-c", cfg, "-D", tmp, "--disable-color"], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not wait_port(mixed, proc) or not wait_log(logp, lambda: None, "sing-box started", proc):
                    raise RuntimeError("sing-box 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                started = time.time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(8, len(targets) if hold else 8)) as pool:
                    list(pool.map(lambda t: connect_once(mixed, t, wait=4.0, hold=hold), targets))
                time.sleep(max(0.5, started + hold + 2.0 - time.time()) if hold else 0.5)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        out = {}
        for c in cases:
            name = rd.dial_name(c).lower().rstrip(".")
            asked = [tag for tag, st in stubs.items() if any(q.lower().rstrip(".") == name for q, _ in st.seen)]
            out[rd.dial_key(c)] = asked[0] if len(asked) == 1 else ("+".join(asked) if asked else NONE)
        return out
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(tmp, ignore_errors=True)


MIHOMO_DNS_SERVER_LISTS = ("default-nameserver", "proxy-server-nameserver", "direct-nameserver", "nameserver", "fallback")
MIHOMO_DNS_POLICIES = ("nameserver-policy", "proxy-server-nameserver-policy")
MIHOMO_DNS_OTHER = ("enable", "ipv6", "enhanced-mode", "fake-ip-range", "fake-ip-filter-mode", "fake-ip-filter", "respect-rules",
                    "direct-nameserver-follow-policy")


def _drop_lan_policy(dns: dict) -> None:
    """把 nameserver-policy 里交给 system 的几条改成交给国内 DNS。r11–r14 只有第一条（局域网后缀）交给 system，那时这里
    直接删掉它（名字落到 geosite:cn,private 那条，交给国内 DNS）；2026-10-07 起还有不带点的名字（*）和 private 集合两条
    （待决事项 14 方案二），局域网后缀下的名字大多也在 private 集合里，只删第一条看不出变化，所以三条一起改回国内 DNS。"""
    policy = dns["nameserver-policy"]
    first = next(iter(policy))
    if policy[first] != ["system"]:
        raise KeyError("nameserver-policy 的第一条不是“局域网后缀 → system”")
    domestic = policy.get("geosite:cn")
    if not domestic:
        raise KeyError("nameserver-policy 里没有 geosite:cn 那一条")
    for k, v in list(policy.items()):
        if v == ["system"]:
            policy[k] = list(domestic)


def strip_product_layer(policy: dict, model) -> dict:
    """去掉 nameserver-policy 里“走代理组的产品域名”那一层：只去掉 generator/emit_mihomo.py 的 product_dns_policy 写进去的
    那些键，局域网后缀、不带点的名字、要真实地址的名单、geosite 几条都不动（2026-10-07 起策略里多了后两样，以前的写法
    “只留第一条和 geosite 条目”会把它们一起去掉，自检就不只看那一层了）。"""
    keys = {pattern for pattern, _ in emit_mihomo.product_dns_policy(model, build_plan(model))}
    missing = sorted(keys - set(policy))
    if missing:
        raise KeyError(f"nameserver-policy 里没有产品域名那一层的这些键：{missing[:5]}")
    return {k: v for k, v in policy.items() if k not in keys}


# 自检时从 DNS 段里去掉的东西：名字 → (说明, 怎么去掉)
MIHOMO_DIAL_WITHOUT = {
    "node-policy": ("proxy-server-nameserver-policy", lambda dns: dns.pop("proxy-server-nameserver-policy")),
    "follow-policy": ("direct-nameserver-follow-policy", lambda dns: dns.pop("direct-nameserver-follow-policy")),
    "lan-policy": ("nameserver-policy 里交给系统 DNS 的几条（局域网后缀、不带点的名字、private 集合；改成国内 DNS）", _drop_lan_policy),
}


def mihomo_dial_probe(binary: str, geodata_dir: str, model, config_text: str, cases: list, dns_cases: list = (),
                      without: str = None, silent: tuple = (), hold: float = 0.0):
    """mihomo 里名字交给哪一类 DNS 解析（2026-10-05 审核 r10 的 R10-F01）。返回 (拨号 {用例的键: 结果}, 查询 {(主机, 类型): 结果})。
    结果是 system（系统 DNS）、domestic（国内 DNS）、foreign（境外 DNS）之一——收到这个名字的查询的是哪一类的替身；
    一个都没有收到时，拨号 / 连接用例记 none；查询用例看内核自己回了什么：fake-ip（给了假地址）、empty（回了一个
    没有记录的正常应答）、no-reply（5 秒内没有应答）、rcode-N（别的应答码），以及 answer:地址、records:N（见 reply_kind）。
    silent：这几类的替身只收不答；hold：每个连接保持多少秒不断开（见 connect_once）。两个一起用，
    看“这一类 DNS 不应答时，内核会不会转去问别的”（2026-10-06）。

    mihomo 内核里有三个互不相干的解析器，这里各走一遍：
      节点连接自己的服务器（cases 里 kind: node）     proxy-server-nameserver，例外写在 proxy-server-nameserver-policy 里；
      直连出口连接域名形式的目标（kind: direct）       direct-nameserver，开了 direct-nameserver-follow-policy 时先看 nameserver-policy；
      设备上的程序发来的 DNS 查询（dns_cases）          nameserver 和 nameserver-policy。
    mihomo_probe 把出口都换成了 REJECT、没有节点，前两条路碰不到；第三条路以前只有 sing-box 那边核对过。做法：
      - 生成的配置里，规则、DNS、嗅探和几个开关原样保留（real_data.mihomo_dial_base）；
      - DNS 段里出现的每个服务器按它在统一源里属于哪一类，换成那一类的本机替身：system → 系统 DNS 的替身，
        国内的 DoH / 明文地址 → 国内替身，境外 DoH → 境外替身。哪个字段、哪条策略用哪一类，结构没有动；
        替身不管问什么都答 127.0.0.1，所以每次拨号都落在本机，不会有连接离开这台机器；
      - 加几个 SOCKS 节点（服务器地址取自用例，端口是本机一个没人监听的端口），每个节点配一条只给它用的规则；
        策略组换成固定出口：原来默认直连的仍然直连，其余的拒绝；
      - 节点用例：发一次 CONNECT 让内核去连这个节点；直连用例：直接 CONNECT 那个主机；
        查询用例：向内核在本机临时开的 DNS 端口（dns.listen）发一次查询。
    without 用来自检，从 DNS 段里去掉一样东西再跑（MIHOMO_DIAL_WITHOUT）。
    没有验证的：system 这个写法在真实系统上向谁查询（这里换成了替身）、真实节点的连通、TUN 接管下的表现。"""
    names = [rd.dial_name(c).lower().rstrip(".") for c in cases]
    dns_names = [c["host"].lower().rstrip(".") for c in dns_cases]
    if len(set(names + dns_names)) != len(names) + len(dns_names):
        raise RuntimeError("拨号用例、查询用例里有重复的名字，分不清查询是哪一条用例引起的")
    orig = yaml.safe_load(config_text)
    conf = rd.mihomo_dial_base(config_text)
    dns = conf["dns"]
    unknown = sorted(set(dns) - set(MIHOMO_DNS_SERVER_LISTS) - set(MIHOMO_DNS_POLICIES) - set(MIHOMO_DNS_OTHER))
    if unknown:
        raise RuntimeError(f"生成的 mihomo 配置的 dns 段多了字段 {unknown}：拨号核对不知道它里面有没有 DNS 服务器要换成替身")
    if without:
        what, drop = MIHOMO_DIAL_WITHOUT[without]
        try:
            drop(dns)
        except KeyError as e:
            raise RuntimeError(f"自检要去掉 {what}，但生成的配置里没有它（{e}）")
    fake_net = ipaddress.ip_network(dns["fake-ip-range"], strict=False)
    kind_of = {"system": "system"}
    for srv in list(model.dns["domestic_doh"]) + list(model.dns["domestic_plain"]):
        kind_of[srv] = "domestic"
    for srv in model.dns["foreign_doh"]:
        kind_of[srv] = "foreign"
    stubs = {k: DnsStub(k, _Loopback(), silent=k in silent) for k in ("system", "domestic", "foreign")}
    home = tempfile.mkdtemp(prefix="dial-mihomo-")
    try:
        def stand_in(servers) -> list:
            out = []
            for srv in [servers] if isinstance(servers, str) else list(servers):
                if srv not in kind_of:
                    raise RuntimeError(f"dns 段里的服务器 {srv} 不在统一源的三类 DNS 里，拨号核对不知道该换成哪个替身")
                addr = f"127.0.0.1:{stubs[kind_of[srv]].port}"
                if addr not in out:
                    out.append(addr)
            return out

        for key in MIHOMO_DNS_SERVER_LISTS:
            if key in dns:
                dns[key] = stand_in(dns[key])
        for key in MIHOMO_DNS_POLICIES:
            if key in dns:
                dns[key] = {pattern: stand_in(servers) for pattern, servers in dns[key].items()}
        for st in stubs.values():
            st.start()
        closed = free_port()                               # 取到就放掉：没人监听，连上去立刻被拒绝
        proxies = rd.dial_proxies(cases, closed)
        node_of = {p["server"]: p["name"] for p in proxies}
        probe_host = {srv: f"dial-probe-{i + 1}.invalid" for i, srv in enumerate(node_of)}
        port, dns_port = free_port(), free_port_tcp_udp()
        dns["listen"] = f"127.0.0.1:{dns_port}"            # 只给查询用例用；生成的配置里没有这一项
        conf.update({
            "mixed-port": port, "allow-lan": False, "bind-address": "127.0.0.1", "log-level": "debug",
            "find-process-mode": "off", "geo-auto-update": False, "profile": {"store-selected": False, "store-fake-ip": False},
            "proxies": proxies,
            "proxy-groups": [{"name": g["name"], "type": "select",
                              "proxies": ["DIRECT" if (g.get("proxies") or [None])[0] == "DIRECT" else "REJECT"]}
                             for g in orig["proxy-groups"]],
            "rules": [f"DOMAIN,{probe_host[srv]},{node_of[srv]}" for srv in node_of] + list(conf["rules"]),
        })
        targets = [probe_host[c["server"]] if c["kind"] == "node" else c["host"] for c in cases]
        for src, dst in {"geosite.dat": "GeoSite.dat", "geoip.dat": "GeoIP.dat", "geoip.metadb": "geoip.metadb",
                         "country.mmdb": "Country.mmdb", "GeoLite2-ASN.mmdb": "GeoLite2-ASN.mmdb"}.items():
            src_path = os.path.join(geodata_dir, src)
            if os.path.exists(src_path):
                shutil.copy(src_path, os.path.join(home, dst))
        cfg = os.path.join(home, "probe.yaml")
        with open(cfg, "w", encoding="utf-8") as f:
            yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False, width=100000)
        logp = os.path.join(home, "log.txt")
        with open(logp, "w", encoding="utf-8") as log:
            proc = subprocess.Popen([binary, "-d", home, "-f", cfg], stdout=log, stderr=subprocess.STDOUT)
            try:
                if not wait_port(port, proc):
                    raise RuntimeError("mihomo 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                if not wait_log(logp, lambda: connect_once(port, CANARY, wait=1.0), f"--> {CANARY}:443 match", proc):
                    raise RuntimeError("mihomo 启动后一直没有处理连接：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                answers = {}
                started = time.time()
                if hold:
                    # 查询先发（不应答的那一类要等到客户端这边超时），连接随后并发着发、各自保持 hold 秒；
                    # 最后保证从开始算起至少过了 hold 秒再收尾，超时以后的任何动作都落在观察时间里
                    for c, name in zip(dns_cases, dns_names):
                        answers[name] = dns_exchange(dns_port, c["host"], QTYPE[c["type"]])
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
                        list(pool.map(lambda t: connect_once(port, t, wait=4.0, hold=hold), targets))
                    time.sleep(max(1.0, started + hold + 2.0 - time.time()))
                else:
                    for t in targets:
                        connect_once(port, t, wait=4.0)
                    for c, name in zip(dns_cases, dns_names):
                        answers[name] = dns_exchange(dns_port, c["host"], QTYPE[c["type"]])
                    time.sleep(1.0)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

        def asked_by(name):
            return [k for k, st in stubs.items() if any(q.lower().rstrip(".") == name for q, _ in st.seen)]

        out, dns_out = {}, {}
        for c, name in zip(cases, names):
            asked = asked_by(name)
            out[rd.dial_key(c)] = asked[0] if len(asked) == 1 else ("+".join(asked) if asked else NONE)
        for c, name in zip(dns_cases, dns_names):
            asked = asked_by(name)
            if asked:
                where = asked[0] if len(asked) == 1 else "+".join(asked)
            else:
                where = reply_kind(answers.get(name), fake_net)
            dns_out[(c["host"], c["type"])] = where
        return out, dns_out
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# 出站时的解析（2026-10-07，GPT 审核 r13 的 R13-F01）
# ---------------------------------------------------------------------------

# 场景见 tools/real_data.py 的 OUTBOUND_SCENARIOS（哪个内核 - 测试出口的类型 - 流量）。
# mihomo 记哪一类替身收到（system / domestic / foreign / none），sing-box 记 DNS 服务器标签
OUTBOUND_NODE = "核对用的出口"


def _throwaway_key() -> str:
    """WireGuard 的一次性随机密钥：只在这一次运行里用，配置写在临时目录、用完就删，不写进任何文件。"""
    return base64.b64encode(os.urandom(32)).decode()


def socks5_udp_once(port: int, host: str, wait: float = 4.0) -> None:
    """经本机的 SOCKS5 端口做 UDP ASSOCIATE，发一个目标是“host:443”（域名形式）的 UDP 包；控制连接保持 wait 秒。"""
    try:
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
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.sendto(b"\x00\x00\x00\x03" + bytes([len(host)]) + host.encode() + struct.pack("!H", 443) + b"probe", relay)
                time.sleep(wait)
    except OSError:
        pass


def _send_all(port: int, hosts: list, transport: str) -> None:
    """每个主机发一次（并发；查询按名字归属，互不干扰），每个连接保持 4 秒，让内核走完选出口、拨号这一段。"""
    if transport not in ("tcp", "udp"):
        raise ValueError(transport)
    send = (lambda h: connect_once(port, h, wait=4.0, hold=4.0)) if transport == "tcp" else (lambda h: socks5_udp_once(port, h, wait=4.0))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(hosts))) as pool:
        list(pool.map(send, hosts))
    time.sleep(1.0)


def mihomo_outbound_probe(binary: str, geodata_dir: str, model, config_text: str, hosts: list, outbound: str,
                          transport: str, without_product_layer: bool = False) -> dict:
    """连接交给代理出口以后，mihomo 还会不会在本机解析目标域名、交给哪一类 DNS（2026-10-07，GPT 审核 r13 的 R13-F01）。
    返回 {主机: system / domestic / foreign / none}（收到这个名字的查询的替身；都没有收到记 none）。

    mihomo_dial_probe 把走代理的组换成了 REJECT：拒绝出口不拨号，碰不到“出口自己为连接解析目标”这条路。实际上
      - WireGuard 这类按 IP 转发的出口，目标还是域名时用默认解析器在本机解析（v1.19.31 adapter/outbound/wireguard.go）；
      - 几乎所有代理协议转发 UDP 前都先在本机解析目标域名（adapter/outbound/base.go 的 ResolveUDP，
        socks5.go、shadowsocks.go、trojan.go、vmess.go、hysteria2.go…… 的 ListenPacketContext 都调用它）。
    默认解析器按 nameserver-policy 选服务器，所以名字归国内 DNS 的域名就被交给了国内 DNS。做法同 mihomo_dial_probe：
    规则、DNS 段的结构原样，三类 DNS 各换成本机替身（都答 127.0.0.1）；默认直连的组仍直连，其余策略组都换成一个测试出口
    （socks5 或 wireguard，服务器是本机一个没人监听的端口，WireGuard 用一次性随机密钥）——每次拨号都落在本机。
    transport：tcp 发 CONNECT 主机:443；udp 经 SOCKS5 UDP ASSOCIATE 发一个目标是“主机:443”的 UDP 包（开了 TUN 时程序发 QUIC，
    目标是假地址，内核按假地址找回域名，走的是同一条路；2026-10-07 的一次性核对两种都试过，结果相同）。
    without_product_layer：去掉 nameserver-policy 里走代理组的产品域名那一层（r13 以前的样子），用来自检。"""
    conf = rd.mihomo_dial_base(config_text)
    orig = yaml.safe_load(config_text)
    dns = conf["dns"]
    if without_product_layer:
        dns["nameserver-policy"] = strip_product_layer(dns["nameserver-policy"], model)
    kind_of = {"system": "system"}
    for srv in list(model.dns["domestic_doh"]) + list(model.dns["domestic_plain"]):
        kind_of[srv] = "domestic"
    for srv in model.dns["foreign_doh"]:
        kind_of[srv] = "foreign"
    stubs = {k: DnsStub(k, _Loopback()) for k in ("system", "domestic", "foreign")}

    def stand_in(servers) -> list:
        out = []
        for srv in [servers] if isinstance(servers, str) else list(servers):
            if srv not in kind_of:
                raise RuntimeError(f"dns 段里的服务器 {srv} 不在统一源的三类 DNS 里，不知道该换成哪个替身")
            addr = f"127.0.0.1:{stubs[kind_of[srv]].port}"
            if addr not in out:
                out.append(addr)
        return out

    for key in MIHOMO_DNS_SERVER_LISTS:
        if key in dns:
            dns[key] = stand_in(dns[key])
    for key in MIHOMO_DNS_POLICIES:
        if key in dns:
            dns[key] = {pattern: stand_in(servers) for pattern, servers in dns[key].items()}
    closed = free_port_tcp_udp()
    node = {"name": OUTBOUND_NODE, "server": "127.0.0.1", "port": closed, "udp": True}
    if outbound == "socks5":
        node["type"] = "socks5"
    elif outbound == "wireguard":
        node.update({"type": "wireguard", "ip": "172.16.0.2", "private-key": _throwaway_key(),
                     "public-key": _throwaway_key(), "mtu": 1280})
    else:
        raise ValueError(outbound)
    port = free_port_tcp_udp()
    conf.update({
        "mixed-port": port, "allow-lan": False, "bind-address": "127.0.0.1", "log-level": "debug",
        "find-process-mode": "off", "geo-auto-update": False, "profile": {"store-selected": False, "store-fake-ip": False},
        "proxies": [node],
        "proxy-groups": [{"name": g["name"], "type": "select",
                          "proxies": ["DIRECT" if (g.get("proxies") or [None])[0] == "DIRECT" else OUTBOUND_NODE]}
                         for g in orig["proxy-groups"]],
    })
    home = tempfile.mkdtemp(prefix="outbound-mihomo-")
    try:
        for st in stubs.values():
            st.start()
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
                if not wait_port(port, proc):
                    raise RuntimeError("mihomo 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                # 测试出口连不通，内核记的是“dial … error”而不是“match”，所以只等日志里出现这个目标
                if not wait_log(logp, lambda: connect_once(port, CANARY, wait=1.0), f"--> {CANARY}:443", proc):
                    raise RuntimeError("mihomo 启动后一直没有处理连接：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                _send_all(port, hosts, transport)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        out = {}
        for h in hosts:
            asked = [k for k, st in stubs.items() if any(q.lower().rstrip(".") == h for q, _ in st.seen)]
            out[h] = "+".join(asked) if asked else NONE
        return out
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(home, ignore_errors=True)


def singbox_outbound_probe(binary: str, srs_dir: str, config_text: str, hosts: list, outbound: str, transport: str) -> dict:
    """同上，sing-box 这一边（自查同一类问题）。返回 {主机: 收到查询的 DNS 服务器标签，或 none}。
    DNS 规则、路由规则原样；dns-cn / dns-foreign / dns-local 换成本机替身（dns-fakeip 保留），TUN 入站换成本机回环上的
    mixed 入站；默认直连的组仍直连，其余策略组都换成测试出口（socks 出站，或 WireGuard 端点）。
    sing-box 的代理出站把域名原样交给节点（TCP、UDP 都是）；WireGuard 端点要 IP，按 DNS 规则解析
    （v1.14.1 protocol/wireguard/endpoint.go 的 DialContext：dnsRouter.Lookup，不指定服务器）。"""
    conf = json.loads(config_text)
    stubs = {tag: DnsStub(tag, _Loopback()) for tag in ("dns-cn", "dns-foreign", "dns-local")}
    for srv in conf["dns"]["servers"]:
        if srv["tag"] in stubs:
            port, tag = stubs[srv["tag"]].port, srv["tag"]
            srv.clear()
            srv.update({"type": "udp", "tag": tag, "server": "127.0.0.1", "server_port": port})
    closed, mixed = free_port_tcp_udp(), free_port_tcp_udp()
    conf["log"] = {"level": "debug", "timestamp": False}
    conf["inbounds"] = [{"type": "mixed", "tag": "probe-in", "listen": "127.0.0.1", "listen_port": mixed}]
    for rs in conf["route"]["rule_set"]:
        if rs["type"] == "remote":
            tag = rs["tag"]
            rs.clear()
            rs.update({"type": "local", "tag": tag, "format": "binary", "path": os.path.abspath(os.path.join(srs_dir, SB_SRS[tag]))})
    conf["route"].pop("auto_detect_interface", None)
    conf["route"].pop("default_http_client", None)
    conf.pop("experimental", None)
    conf.pop("http_clients", None)
    outs = []
    for o in conf["outbounds"]:
        if o["type"] in ("selector", "urltest"):
            direct = (o.get("default") or (o.get("outbounds") or [None])[0]) == "DIRECT"
            outs.append({"type": "selector", "tag": o["tag"], "outbounds": ["DIRECT" if direct else OUTBOUND_NODE]})
        else:
            outs.append(o)
    if outbound == "socks":
        outs.append({"type": "socks", "tag": OUTBOUND_NODE, "server": "127.0.0.1", "server_port": closed})
    elif outbound == "wireguard":
        conf["endpoints"] = [{"type": "wireguard", "tag": OUTBOUND_NODE, "address": ["172.16.0.2/32"], "mtu": 1280,
                              "private_key": _throwaway_key(),
                              "peers": [{"address": "127.0.0.1", "port": closed, "public_key": _throwaway_key(),
                                         "allowed_ips": ["0.0.0.0/0"]}]}]
    else:
        raise ValueError(outbound)
    conf["outbounds"] = outs
    tmp = tempfile.mkdtemp(prefix="outbound-singbox-")
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
                if not wait_port(mixed, proc) or not wait_log(logp, lambda: None, "sing-box started", proc):
                    raise RuntimeError("sing-box 没有启动成功：" + open(logp, encoding="utf-8", errors="replace").read()[-800:])
                _send_all(mixed, hosts, transport)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        out = {}
        for h in hosts:
            asked = [tag for tag, st in stubs.items() if any(q.lower().rstrip(".") == h for q, _ in st.seen)]
            out[h] = "+".join(asked) if asked else NONE
        return out
    finally:
        for st in stubs.values():
            st.close()
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 成员快照
# ---------------------------------------------------------------------------

def mihomo_dns_sets(config_text: str) -> list:
    """mihomo 配置的 dns 段里引用到的 geosite 集合名（nameserver-policy、fake-ip-filter 里的 geosite:甲,乙）。"""
    dns = yaml.safe_load(config_text)["dns"]
    names = []
    for key in list(dns.get("nameserver-policy", {})) + list(dns.get("fake-ip-filter", [])):
        if key.startswith("geosite:"):
            names += [n for n in key[len("geosite:"):].split(",") if n not in names]
    return names


def build_membership(a, model, files, hosts, ips):
    """读入各端引用的真实集合，算出每个主机 / IP 的成员关系。
    返回 (hosts 表, ips 表, 数据来源, 值得留意的地方, 集合规模, 提示行, 读进来的集合本身)。"""
    notes = []
    sources = {}

    def src(family, path, origin):
        sources.setdefault(family, {})[os.path.basename(path)] = {"sha256": rd.sha256_file(path), "bytes": os.path.getsize(path),
                                                                   "origin": origin}

    geosite_path = os.path.join(a.geodata_dir, "geosite.dat")
    geoip_path = os.path.join(a.geodata_dir, "geoip.dat")
    dns_only = [n for n in mihomo_dns_sets(files["mihomo/mihomo-core.yaml"]) if n not in rd.MIHOMO_SETS]
    geo = rd.read_geosite_dat(geosite_path, wanted=set(rd.MIHOMO_SETS) | set(dns_only))
    lost = [n for n in list(rd.MIHOMO_SETS) + dns_only if n not in geo]
    if lost:
        raise RuntimeError(f"geosite.dat 里没有配置引用的集合 {lost}")
    src("mihomo", geosite_path, a.geodata_origin)
    for extra in ("geoip.metadb", "geoip.dat"):
        if os.path.exists(os.path.join(a.geodata_dir, extra)):
            src("mihomo", os.path.join(a.geodata_dir, extra), a.geodata_origin)
    cn_nets = rd.read_geoip_dat(geoip_path, "cn") if os.path.exists(geoip_path) else []
    srs_sets, srs_nets = {}, {}
    for tag, fn in SB_SRS.items():
        p = os.path.join(a.srs_dir, fn)
        data = rd.decompile_srs(a.singbox, p)
        src("singbox", p, a.srs_origin)
        if tag in rd.SINGBOX_IP_SETS:
            srs_nets[tag] = rd.srs_networks(data)
        else:
            srs_sets[tag] = rd.srs_domain_set(data)
            bad = [pat for pat, rx in srs_sets[tag].regex if rx is None]
            if bad:
                notes.append(f"{tag}：{len(bad)} 条正则 Python 不认识，成员判断时跳过了：{bad[:3]}")
    remote = {}
    for family, urls in rd.upstream_remote_lists(model).items():      # 广告集合；Loon 严格版另有国内域名集合
        for url in urls:
            p = rd.bm7_local_path(a.bm7, url)
            if not os.path.exists(p):
                raise RuntimeError(f"blackmatrix7 的检出目录里没有 {os.path.relpath(p, a.bm7)}（配置订阅了 {url}）")
            remote.setdefault(family, {})[url] = rd.read_rule_list(p)
            src(family, p, a.bm7_origin)

    host_rec = {}
    for h in hosts:
        host_rec[h] = {
            "mihomo": {n: geo[n].why(h) for n in rd.MIHOMO_SETS if geo[n].why(h)},
            "singbox": {n: srs_sets[n].why(h) for n in rd.SINGBOX_SETS if srs_sets[n].why(h)},
            "loon": {u: rl.host_hits(h)[0] for u, rl in remote["loon"].items() if rl.host_hits(h)},
            "quantumultx": {u: rl.host_hits(h)[0] for u, rl in remote["quantumultx"].items() if rl.host_hits(h)},
        }
    ip_rec = {}
    for ip in ips:
        addr = ipaddress.ip_address(ip)
        ip_rec[ip] = {
            "mihomo": {"cn": any(addr.version == n.version and addr in n for n in cn_nets)},
            "singbox": {"cn": any(addr.version == n.version and addr in n for n in srs_nets["geoip-cn"])},
            "loon": {u: rl.ip_hits(ip)[0] for u, rl in remote["loon"].items() if rl.ip_hits(ip)},
            "quantumultx": {u: rl.ip_hits(ip)[0] for u, rl in remote["quantumultx"].items() if rl.ip_hits(ip)},
        }

    # 上游集合里值得留意的地方
    tld = sorted(x for x in geo["cn"].suffix if "." not in x)
    known_tld = None
    if a.dlc and os.path.exists(os.path.join(a.dlc, "data", "tld-cn")):
        known_tld = set()
        with open(os.path.join(a.dlc, "data", "tld-cn"), encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip().split(" ")[0]
                if line and ":" not in line:
                    known_tld.add(line.encode("idna").decode("ascii") if not line.isascii() else line)
    stray = [x for x in tld if known_tld is not None and x not in known_tld]
    oddities = {"mihomo_cn_whole_tld": tld, "mihomo_cn_whole_tld_not_in_dlc_tld_cn": stray if known_tld is not None else None,
                "singbox_cn_has_ms": bool(srs_sets["geosite-cn"].why("example.ms"))}
    sizes = {"mihomo": {n: len(geo[n]) for n in rd.MIHOMO_SETS}, "singbox": {n: len(srs_sets[n]) for n in rd.SINGBOX_SETS},
             "mihomo_dns_only": {n: len(geo[n]) for n in dns_only},
             "singbox_ip": {n: len(v) for n, v in srs_nets.items()}, "mihomo_geoip_cn": len(cn_nets),
             # ip_resolving：按 IP 判断、又不带 no-resolve 的规则有几条（Loon 严格版要求是 0，见下面 main 里的核对）
             "loon": {u: {"domain": len(rl.domains.full), "suffix": len(rl.domains.suffix), "keyword": len(rl.domains.keyword),
                          "ip": len(rl.nets), "ignored": rl.ignored, "ip_resolving": len(rl.ip_resolving),
                          "ip_resolving_examples": rl.ip_resolving[:3]} for u, rl in remote["loon"].items()},
             "quantumultx": {u: {"domain": len(rl.domains.full), "suffix": len(rl.domains.suffix),
                                 "keyword": len(rl.domains.keyword), "ip": len(rl.nets), "ignored": rl.ignored}
                             for u, rl in remote["quantumultx"].items()}}
    loaded = {"mihomo": geo, "mihomo_cn_nets": cn_nets, "singbox": srs_sets, "singbox_cn_nets": srs_nets["geoip-cn"]}
    return host_rec, ip_rec, sources, oddities, sizes, notes, loaded


# ---------------------------------------------------------------------------
# 国内 DNS 与路由的逐条扫描
# ---------------------------------------------------------------------------

def _official_selection(rec: dict) -> list:
    """交给官方内核核对的主机：不一致的全部、默认直连组的全部，加上按固定间隔抽出来的一批一致的。"""
    special = [x["host"] for x in rec["mismatch"]] + [x["host"] for x in rec["default_direct"]]
    rest = [h for h in rec["_routes"] if h not in set(special)]
    return sorted(set(special) | set(drc.sample(rest, SAMPLE_SIZE)))


def check_consistency(a, model, files, loaded, dns_map) -> tuple:
    """逐条扫描（说明见 tools/dns_route_consistency.py）。返回 (记进快照的记录, 不一致的说明)。
    “不一致的说明”指的是核对本身出了问题（模拟器和官方内核对不上等）；扫出来的“名字交给国内 DNS、连接走代理组”的主机
    不算在这里——它们记在记录的 mismatch 里，是不是都属于已知类别由 tests/test_real_data.py 判断。"""
    failures, out = [], {}
    domestic = list(model.dns["domestic_doh"]) + list(model.dns["domestic_plain"])

    def show(label, rec):
        sw = rec["swept"]
        print(f"  {label}：扫了 {sw['hosts']} 个代表主机（集合条目 {sw['from_sets']} 个、规则的值 {sw['from_rules']} 个；"
              f"集合规模 {sw['sets']}；正则 {sw['skipped']['regex']} 条、关键词 {sw['skipped']['keyword']} 条取不出代表主机，没有扫）")
        print(f"      名字会交给国内 DNS 的 {rec['to_domestic']} 个：路由是国内直连 / 直连 / 拦截的 {rec['consistent']} 个；"
              f"归默认直连、可以切换的组的 {len(rec['default_direct'])} 个；走代理组的 {len(rec['mismatch'])} 个")
        by = {}
        for x in rec["mismatch"]:
            by.setdefault((x["via"], x["route"]), []).append(x["host"])
        for (via, route), hs in sorted(by.items()):
            print(f"      走代理组：来自 {via}、路由交给 {route} 的 {len(hs)} 个，例如 {'、'.join(hs[:4])}")

    # ---- mihomo ----
    core = files["mihomo/mihomo-core.yaml"]
    conf = yaml.safe_load(core)
    fx = drc.LiveFixtures("mihomo", loaded["mihomo"], loaded["mihomo_cn_nets"], dns_map, DEFAULT_FOREIGN_IP)
    rec = drc.sweep_mihomo(conf, loaded["mihomo"], fx, domestic)
    show("mihomo", rec)
    sel = _official_selection(rec)
    # 两种算法互相核对：抽出来的主机用逐条模拟再算一遍
    slow = {h: emulate.mihomo_route(conf, emulate.Conn(host=h), fx) for h in sel}
    bad = [f"{h}：快速判断 {rec['_routes'][h]}，逐条模拟 {slow[h]}" for h in sel if slow[h] != rec["_routes"][h]]
    got = mihomo_probe(a.mihomo, a.geodata_dir, core, sel, dns_map)
    bad += [f"{h}：模拟器 {rec['_routes'][h]}，官方内核 {got.get(h) and got[h][1]}" for h in sel
            if not got.get(h) or got[h][1] != rec["_routes"][h]]
    _, asked = mihomo_dial_probe(a.mihomo, a.geodata_dir, model, core, [], [{"host": h, "type": "TXT"} for h in sel])
    bad += [f"{h}：TXT 查询应该交给国内 DNS，官方内核 {asked[(h, 'TXT')]}" for h in sel if asked[(h, "TXT")] != "domestic"]
    print(f"      [{'符合' if not bad else '不符合'}] 官方内核核对 {len(sel)} 个主机（走代理组的和默认直连组的全部，另抽 {SAMPLE_SIZE} 个）："
          + ("路由结果与模拟器相同；TXT 查询都由国内 DNS 的替身收到" if not bad else f"{len(bad)} 处对不上"))
    for x in bad[:20]:
        print("        " + x)
    failures += [f"mihomo 逐条扫描：{x}" for x in bad]
    out["mihomo"] = _consistency_record(rec, len(sel))
    # 自检（2026-10-07，r14）：把 nameserver-policy 里“走代理组的产品域名”那一层拿掉（r13 的样子）再扫。走代理组的应该多出一大批；
    # 多出来的这些就是那一层管到的主机，交给官方内核查一次 TXT，现在应该都由境外 DNS 的替身收到
    stripped = yaml.safe_load(core)
    stripped["dns"]["nameserver-policy"] = strip_product_layer(stripped["dns"]["nameserver-policy"], model)
    fx2 = drc.LiveFixtures("mihomo", loaded["mihomo"], loaded["mihomo_cn_nets"], dns_map, DEFAULT_FOREIGN_IP)
    rec2 = drc.sweep_mihomo(stripped, loaded["mihomo"], fx2, domestic)
    back = sorted({x["host"] for x in rec2["mismatch"]} - {x["host"] for x in rec["mismatch"]})
    ok = len(back) > 20
    print(f"      自检：去掉 nameserver-policy 里“走代理组的产品域名”那一层再扫，走代理组的从 {len(rec['mismatch'])} 个变成 "
          f"{len(rec2['mismatch'])} 个" + ("——这一层仍然需要，这项核对看得见它要防的错误" if ok
                                         else "——没有明显变化：这项核对没有起作用，或者上游数据变了"))
    if not ok:
        failures.append("mihomo 逐条扫描：自检没有看到差别")
    _, asked = mihomo_dial_probe(a.mihomo, a.geodata_dir, model, core, [], [{"host": h, "type": "TXT"} for h in back])
    wrong = [f"{h}：{asked[(h, 'TXT')]}" for h in back if asked[(h, "TXT")] != "foreign"]
    print(f"      [{'符合' if not wrong else '不符合'}] 多出来的 {len(back)} 个（产品域名那一层管到的）交给官方内核查 TXT："
          + ("都只由境外 DNS 的替身收到" if not wrong else f"{len(wrong)} 个不是，例如 {'、'.join(wrong[:5])}"))
    failures += [f"mihomo 逐条扫描（产品域名那一层）：{x}" for x in wrong]
    out["mihomo"]["without_product_dns_rules"] = len(rec2["mismatch"])
    out["mihomo"]["product_layer_checked"] = len(back)

    # ---- sing-box ----
    runs = [("singbox", "1.14", a.singbox)] + ([("singbox112", "1.12", a.singbox_112)] if a.singbox_112 else [])
    for key, variant, binary in runs:
        rel = f"sing-box/sing-box-{variant}.json"
        conf = json.loads(files[rel])
        fx = drc.LiveFixtures("singbox", loaded["singbox"], loaded["singbox_cn_nets"], dns_map, DEFAULT_FOREIGN_IP)
        rec = drc.sweep_singbox(conf, loaded["singbox"], fx)
        show(f"sing-box {variant}", rec)
        sel = _official_selection(rec)
        cases = [{"host": h, "type": t} for h in sel for t in ("A", "HTTPS")]
        routes, dns_got = singbox_probe(binary, a.srs_dir, files[rel], sel, cases, dns_map)
        bad = [f"{h}：模拟器 {rec['_routes'][h]}，官方内核 {routes.get(h) and routes[h][1]}" for h in sel
               if not routes.get(h) or routes[h][1] != rec["_routes"][h]]
        for c in cases:
            sim = emulate.singbox_dns(conf, c["host"], c["type"], fx)
            if dns_got.get((c["host"], c["type"])) != sim:
                bad.append(f"{c['host']} {c['type']}：模拟器 {sim}，官方内核 {dns_got.get((c['host'], c['type']))}")
        print(f"      [{'符合' if not bad else '不符合'}] 官方内核核对 {len(sel)} 个主机："
              + ("路由结果、A 与 HTTPS 查询的去向都与模拟器相同" if not bad else f"{len(bad)} 处对不上"))
        for x in bad[:20]:
            print("        " + x)
        failures += [f"sing-box {variant} 逐条扫描：{x}" for x in bad]
        out[key] = _consistency_record(rec, len(sel))
        if key == "singbox":
            # 自检：把 DNS 规则里“走代理组的产品域名”那一层拿掉再扫。不一致的应该多出一大批——说明这项核对看得见它要防的错误
            stripped = json.loads(files[rel])
            stripped["dns"]["rules"] = [r for r in stripped["dns"]["rules"] if r.get("rule_set") != "product-proxied"]
            fx2 = drc.LiveFixtures("singbox", loaded["singbox"], loaded["singbox_cn_nets"], dns_map, DEFAULT_FOREIGN_IP)
            n = len(drc.sweep_singbox(stripped, loaded["singbox"], fx2)["mismatch"])
            ok = n > len(rec["mismatch"]) + 20
            print(f"      自检：去掉 DNS 规则里“走代理组的产品域名”那一层再扫，走代理组的从 {len(rec['mismatch'])} 个变成 {n} 个"
                  + ("——这一层仍然需要，这项核对看得见它要防的错误" if ok else "——没有明显变化：这项核对没有起作用，或者上游数据变了"))
            out[key]["without_product_dns_rules"] = n
            if not ok:
                failures.append("sing-box 逐条扫描：自检没有看到差别")
    return out, failures


def _consistency_record(rec: dict, checked: int) -> dict:
    return {"swept": rec["swept"], "to_domestic": rec["to_domestic"], "consistent": rec["consistent"],
            "default_direct": rec["default_direct"], "mismatch": rec["mismatch"], "official_checked": checked}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mihomo", required=True)
    ap.add_argument("--singbox", required=True, help="sing-box 1.14.x")
    ap.add_argument("--singbox-112", help="sing-box 1.12.x（用 1.12 兼容版配置再跑一遍）")
    ap.add_argument("--geodata-dir", required=True)
    ap.add_argument("--srs-dir", required=True)
    ap.add_argument("--bm7", required=True)
    ap.add_argument("--dlc")
    ap.add_argument("--geodata-origin", default="MetaCubeX/meta-rules-dat 的发布文件")
    ap.add_argument("--srs-origin", default="SagerNet/sing-geosite、sing-geoip 的 rule-set 分支")
    ap.add_argument("--bm7-origin", default="blackmatrix7/ios_rule_script 的检出目录")
    ap.add_argument("--write-snapshot", action="store_true")
    a = ap.parse_args(argv)
    safe_stdout()
    for label, path in (("--mihomo", a.mihomo), ("--singbox", a.singbox), ("--geodata-dir", a.geodata_dir),
                        ("--srs-dir", a.srs_dir), ("--bm7", a.bm7)):
        if not os.path.exists(path):
            print(f"{label} 指向的 {path} 不存在", file=sys.stderr)
            return 2
    missing = [fn for fn in SB_SRS.values() if not os.path.exists(os.path.join(a.srs_dir, fn))]
    if missing or not os.path.exists(os.path.join(a.geodata_dir, "geosite.dat")):
        print(f"数据文件不全：缺 {missing or 'geosite.dat'}", file=sys.stderr)
        return 2

    model = load(ROOT, include_local=False)
    plan = build_plan(model)
    files = builder.render_public(model, plan)
    # 严格版引用的自有远程规则文件：内容就是这次生成的产物，登记给模拟器
    base = model.strict["publish_base"]
    emulate.register_own_lists(base, {base + rel: files[rel] for rel in strict_mod.OWN_FILES})
    fix = rd._load("tests/fixtures.yaml")
    dns_map = dict(fix["dns"])
    probes = rd.collect_probes(model)
    dns_cases = rd.dns_cases()
    dial_cases = rd.dial_cases()
    mihomo_dial_cases, mihomo_dns_cases = rd.dial_cases("mihomo"), rd.dns_cases("mihomo")
    hosts, ips = rd.all_hosts(model), rd.all_ips(model)
    targets = sorted({p["host"] or p["ip"] for p in probes})

    print(f"统一源 {model.project['project']['source_version']}；用例与排除项共 {len(probes)} 条，"
          f"不同的目标 {len(targets)} 个；DNS 去向用例 sing-box {len(dns_cases)} 条、mihomo {len(mihomo_dns_cases)} 条，"
          f"拨号解析用例 sing-box {len(dial_cases)} 条、mihomo {len(mihomo_dial_cases)} 条")
    host_rec, ip_rec, sources, oddities, sizes, notes, loaded = build_membership(a, model, files, hosts, ips)
    print("数据文件：")
    for family, fs in sources.items():
        for name, info in fs.items():
            print(f"  [{family}] {name}：SHA-256 {info['sha256']}（{info['bytes']} 字节；{info['origin']}）")
    print("集合规模：mihomo " + "、".join(f"{k} {v}" for k, v in sizes["mihomo"].items())
          + "（只在 DNS 段里用到的：" + "、".join(f"{k} {v}" for k, v in sizes["mihomo_dns_only"].items()) + "）"
          + "；sing-box " + "、".join(f"{k} {v}" for k, v in sizes["singbox"].items()))
    for family in ("loon", "quantumultx"):
        for u, n in sizes[family].items():
            print(f"  [{family}] {u.rsplit('/', 1)[-1]}：域名 {n['domain']}、后缀 {n['suffix']}、关键词 {n['keyword']}、IP 段 {n['ip']}"
                  + ("" if family != "loon" or not n["ip"] else
                     "（都带 no-resolve）" if not n["ip_resolving"] else f"（其中 {n['ip_resolving']} 条不带 no-resolve）")
                  + (f"；没有读的规则类型 {n['ignored']}" if n["ignored"] else ""))
    for x in notes:
        print("  注意：" + x)
    print("上游集合里值得留意的：MetaCubeX 的 cn 集合里整段顶级域的条目 " + str(len(oddities["mihomo_cn_whole_tld"])) + " 个"
          + (f"，其中不在 domain-list-community 的 tld-cn 里的：{oddities['mihomo_cn_whole_tld_not_in_dlc_tld_cn']}"
             if oddities["mihomo_cn_whole_tld_not_in_dlc_tld_cn"] is not None else "（没给 --dlc，未与 tld-cn 对比）")
          + f"；SagerNet 的 geosite-cn 是否把 example.ms 算作国内：{'是' if oddities['singbox_cn_has_ms'] else '否'}")
    print()

    failures = []
    snap = {"hosts": host_rec, "ips": ip_rec, "sizes": sizes}     # sizes：模拟器用它确认“配置订阅的上游规则文件，快照里都有记录”

    # Loon 严格版的前提之一：它订阅的上游规则文件里，按 IP 判断的规则都带 no-resolve。本地规则由写盘前的结构检查管；
    # 上游文件的内容本工程管不到，只能每次核对时数一遍。有不带的，没被域名规则接住的域名就会为那条规则在本机解析
    # （模拟器对 Loon 的远程规则是按“不会为它解析”算的，所以这里不符合时模拟器的结论也不能用）。
    resolving = {u: n for u, n in sizes["loon"].items() if n["ip_resolving"]}
    n_ip = sum(n["ip"] for n in sizes["loon"].values())
    print(f"Loon 订阅的上游规则文件 {len(sizes['loon'])} 个，按 IP 判断的规则共 {n_ip} 条："
          + ("都带 no-resolve（严格版里域名连接不会为它们在本机解析）" if not resolving else "有不带 no-resolve 的"))
    for u, n in resolving.items():
        msg = (f"Loon：上游规则文件 {u.rsplit('/', 1)[-1]} 里有 {n['ip_resolving']} 条按 IP 判断的规则不带 no-resolve"
               f"（例如 {'；'.join(n['ip_resolving_examples'])}）——严格版里没被域名规则接住的域名会为它在本机解析")
        print("  [不符合] " + msg)
        failures.append(msg)
    print()

    def emu(client, target):
        fam = "mihomo" if client.startswith("mihomo") else "singbox"
        fx = emulate.SnapshotFixtures(snap, fam, dns_map)
        conn = emulate.Conn(host=None if _is_ip(target) else target, ip=target if _is_ip(target) else None)
        conf = emulate.parse_mihomo(files[CLIENT[client]]) if fam == "mihomo" else emulate.parse_singbox(files[CLIENT[client]])
        return (emulate.mihomo_route if fam == "mihomo" else emulate.singbox_route)(conf, conn, fx)

    official = {}

    # ---- mihomo ----
    code, ver = run([a.mihomo, "-v"])
    ver = ver.splitlines()[0] if ver else f"（退出码 {code}）"
    print(f"mihomo：{ver}")
    same_rules = yaml.safe_load(files["mihomo/mihomo-core.yaml"])["rules"] == yaml.safe_load(files["mihomo/mihomo-profile.yaml"])["rules"]
    print(f"  mihomo-core.yaml 与 mihomo-profile.yaml 的规则段{'完全相同，只跑一份' if same_rules else '不同！'}")
    if not same_rules:
        failures.append("两份 mihomo 配置的规则段不同")
    got = mihomo_probe(a.mihomo, a.geodata_dir, files["mihomo/mihomo-core.yaml"], targets, dns_map)
    official["mihomo"] = {"version": ver, "config": "mihomo/mihomo-core.yaml",
                          "config_sha256": sha256_text(files["mihomo/mihomo-core.yaml"]),
                          "routing_sha256": rd.routing_digest("mihomo/mihomo-core.yaml", files["mihomo/mihomo-core.yaml"]),
                          "routes": {t: list(v) for t, v in got.items() if v}}
    failures += compare("mihomo", "mihomo", probes, got, lambda t: emu("mihomo-core", t))
    # 名字交给哪一类 DNS 解析：设备发来的查询、直连出口拨号、节点连接自己的服务器，三条路各走一遍
    # （拨号是真的，三类 DNS 各换成一个本机替身）
    core_text = files["mihomo/mihomo-core.yaml"]
    same_dial = rd.mihomo_dial_base(core_text) == rd.mihomo_dial_base(files["mihomo/mihomo-profile.yaml"])
    print(f"  拨号核对原样保留的部分（规则、DNS、嗅探和几个开关），两份 mihomo 配置{'完全相同，只跑一份' if same_dial else '不同！'}")
    if not same_dial:
        failures.append("两份 mihomo 配置里拨号核对要原样保留的部分不同")
    dial, dns_got = mihomo_dial_probe(a.mihomo, a.geodata_dir, model, core_text, mihomo_dial_cases, mihomo_dns_cases)
    dns_key = lambda c: f"{c['host']} {c['type']}"  # noqa: E731
    dns_rec = {dns_key(c): dns_got[(c["host"], c["type"])] for c in mihomo_dns_cases}
    bad = [f"{k}：期望 {c['expect']}，官方内核 {dns_rec[k]}" for c in mihomo_dns_cases for k in [dns_key(c)] if dns_rec[k] != c["expect"]]
    print(f"  [{'符合' if not bad else '不符合'}] DNS 去向 {len(mihomo_dns_cases)} 条（设备发来的查询交给哪一类 DNS。"
          "system 是系统 DNS 的替身，domestic 国内，foreign 境外；fake-ip 是直接给假地址，empty 是直接回空应答，都不向上游查询）："
          + ("官方内核与人工期望一致" if not bad else f"有 {len(bad)} 条不一致"))
    for c in mihomo_dns_cases:
        print(f"      {dns_key(c)} → {dns_rec[dns_key(c)]}" + ("（已知限制的现状，见 docs/06）" if c.get("limit") else ""))
    failures += [f"mihomo DNS：{x}" for x in bad]
    bad = [f"{rd.dial_key(c)}：期望 {c['expect']}，官方内核 {dial[rd.dial_key(c)]}" for c in mihomo_dial_cases
           if dial[rd.dial_key(c)] != c["expect"]]
    print(f"  [{'符合' if not bad else '不符合'}] 连接时的解析 {len(mihomo_dial_cases)} 条（节点服务器的名字、域名形式的直连目标、"
          "走代理组的域名、没被域名规则接住的域名，各交给哪一类 DNS；none = 三类替身都没有收到关于它的查询）："
          + ("官方内核与人工期望一致" if not bad else f"有 {len(bad)} 条不一致"))
    for c in mihomo_dial_cases:
        print(f"      {rd.dial_key(c)} → {dial[rd.dial_key(c)]}")
    failures += [f"mihomo 拨号解析：{x}" for x in bad]
    mihomo_dial_record = {"dns": dns_rec, "dial": dial, "dial_sha256": rd.dial_digest("mihomo", rd.mihomo_dial_base(core_text))}
    # 自检：三处设置各拿掉一处再跑。应该只有它管的那几条变回国内 DNS，别的不变——三个解析器各管各的
    lan_dial = {kind: [rd.dial_key(c) for c in mihomo_dial_cases if c["kind"] == kind and c["expect"] == "system"]
                for kind in ("node", "direct")}
    lan_dns = [dns_key(c) for c in mihomo_dns_cases if c["expect"] == "system"]
    for without, should in (("node-policy", lan_dial["node"]), ("follow-policy", lan_dial["direct"]),
                            ("lan-policy", lan_dns + lan_dial["direct"])):
        d2, q2 = mihomo_dial_probe(a.mihomo, a.geodata_dir, model, core_text, mihomo_dial_cases, mihomo_dns_cases, without=without)
        q2 = {dns_key(c): q2[(c["host"], c["type"])] for c in mihomo_dns_cases}
        tag = without.replace("-", "_")
        mihomo_dial_record["dns_without_" + tag], mihomo_dial_record["dial_without_" + tag] = q2, d2
        before, now = {**q2, **d2}, {**dns_rec, **dial}
        moved = [k for k in now if before[k] != now[k]]
        ok = sorted(moved) == sorted(should) and bool(should) and all(before[k] == "domestic" for k in moved)
        what = MIHOMO_DIAL_WITHOUT[without][0]
        print(f"      自检：去掉 {what}{' ' if what[-1].isascii() else ''}后，"
              + ("、".join(f"{k} → {before[k]}" for k in moved) if moved else "结果没有变化")
              + ("——只有它管的这几条变了，这一处仍然需要" if ok
                 else f"——应该变回 domestic 的是 {should}，实际不是这样：这项核对没有起作用，或者内核的行为变了"))
        if not ok:
            failures.append(f"mihomo 拨号解析：去掉 {MIHOMO_DIAL_WITHOUT[without][0]} 的自检结果不对")
    # 境外 DNS 不应答（2026-10-06）：境外替身只收不答，连接各保持 SILENT_HOLD 秒。收到查询的替身必须和正常那一遍相同
    sil_cases = rd.silent_cases(mihomo_dial_cases)
    d3, q3 = mihomo_dial_probe(a.mihomo, a.geodata_dir, model, core_text, sil_cases, mihomo_dns_cases,
                               silent=("foreign",), hold=SILENT_HOLD)
    q3 = {dns_key(c): q3[(c["host"], c["type"])] for c in mihomo_dns_cases}
    bad = [f"{k}：正常 {dial[k]}，境外 DNS 不应答时 {v}" for k, v in d3.items() if v != dial[k]]
    bad += [f"{k}：正常 {dns_rec[k]}，境外 DNS 不应答时 {v}" for k, v in q3.items() if v != dns_rec[k]]
    asked_foreign = [k for k, v in {**d3, **q3}.items() if v == "foreign"]
    if not asked_foreign:
        bad.append("这一遍里没有任何用例问到境外 DNS：核对没有起作用")
    print(f"  [{'符合' if not bad else '不符合'}] 境外 DNS 不应答（境外替身只收不答，每个连接保持 {SILENT_HOLD:.0f} 秒）："
          f"连接 {len(d3)} 条、查询 {len(q3)} 条，"
          + (f"收到查询的替身与正常那一遍完全相同；其中 {len(asked_foreign)} 条只有境外替身收到——没有转去问国内 / 系统 DNS"
             if not bad else f"有 {len(bad)} 条不一样"))
    for x in bad[:20]:
        print("      " + x)
    failures += [f"mihomo 境外 DNS 不应答：{x}" for x in bad]
    mihomo_dial_record["dial_foreign_silent"], mihomo_dial_record["dns_foreign_silent"] = d3, q3
    # 出站时的解析（2026-10-07，GPT 审核 r13 的 R13-F01）：走代理的组换成真的出口（连本机空端口），看出口自己会不会再解析
    ob_cases = rd.outbound_cases()
    ob_hosts = [c["host"] for c in ob_cases]
    ob_rec = {}
    for scen in rd.OUTBOUND_SCENARIOS:
        core, outbound, transport = scen.split("-")
        if core == "mihomo":
            ob_rec[scen] = mihomo_outbound_probe(a.mihomo, a.geodata_dir, model, core_text, ob_hosts, outbound, transport)
    bad = [f"{scen} {c['host']}：期望 {c['expect'][scen]}，官方内核 {ob_rec[scen][c['host']]}"
           for scen in ob_rec for c in ob_cases if ob_rec[scen][c["host"]] != c["expect"][scen]]
    print(f"  [{'符合' if not bad else '不符合'}] 出站时的解析 {len(ob_cases)} 个主机 × {len(ob_rec)} 种出口"
          "（走代理的组换成 SOCKS5 走 TCP、SOCKS5 走 UDP、WireGuard 走 TCP，出口连本机空端口；"
          "看出口自己会不会再解析目标、交给哪一类 DNS；none = 三类替身都没有收到）："
          + ("官方内核与人工期望一致" if not bad else f"有 {len(bad)} 条不一致"))
    for c in ob_cases:
        print(f"      {c['host']}：" + "，".join(f"{scen[len('mihomo-'):]} → {ob_rec[scen][c['host']]}"
                                             + ("（已知限制的现状，见 docs/06）" if scen in c.get("limit", []) else "")
                                             for scen in ob_rec))
    failures += [f"mihomo 出站时的解析：{x}" for x in bad]
    # 自检：去掉 nameserver-policy 里产品域名那一层（r13 的样子）再跑 WireGuard 那一种。应该只有 product: true 的主机变回国内 DNS
    without = mihomo_outbound_probe(a.mihomo, a.geodata_dir, model, core_text, ob_hosts, "wireguard", "tcp", without_product_layer=True)
    should = sorted(c["host"] for c in ob_cases if c.get("product"))
    moved = sorted(h for h in ob_hosts if without[h] != ob_rec["mihomo-wireguard-tcp"][h])
    ok = moved == should and bool(should) and all(without[h] == "domestic" for h in moved)
    print("      自检：去掉 nameserver-policy 里走代理组的产品域名那一层后，WireGuard 出口下 "
          + ("、".join(f"{h} → {without[h]}" for h in moved) if moved else "结果没有变化")
          + ("——只有这一类变回国内 DNS，这一层仍然需要" if ok
             else f"——应该变回 domestic 的是 {should}，实际不是这样：这项核对没有起作用，或者内核的行为变了"))
    if not ok:
        failures.append("mihomo 出站时的解析：去掉产品域名那一层的自检结果不对")
    mihomo_dial_record["outbound"], mihomo_dial_record["outbound_without_product_layer"] = ob_rec, without
    official["mihomo"].update(mihomo_dial_record)

    # ---- sing-box ----
    runs = [("singbox-1.14", a.singbox, "sing-box/sing-box-1.14.json")]
    if a.singbox_112:
        runs.append(("singbox-1.12", a.singbox_112, "sing-box/sing-box-1.12.json"))
    for client, binary, rel in runs:
        code, ver = run([binary, "version"])
        ver = ver.splitlines()[0] if ver else f"（退出码 {code}）"
        print(f"{client}：{ver}，配置 {rel}")
        routes, dns_got = singbox_probe(binary, a.srs_dir, files[rel], targets, dns_cases, dns_map)
        failures += compare(client, "singbox", probes, routes, lambda t, c=client: emu(c, t))
        conf = emulate.parse_singbox(files[rel])
        fx = emulate.SnapshotFixtures(snap, "singbox", dns_map)
        bad = []
        for c in dns_cases:
            real = dns_got.get((c["host"], c["type"]))
            sim = emulate.singbox_dns(conf, c["host"], c["type"], fx)
            if real != c["expect"] or sim != c["expect"]:
                bad.append(f"{c['host']} {c['type']}：期望 {c['expect']}，官方内核 {real}，模拟器 {sim}")
        print(f"  [{'符合' if not bad else '不符合'}] DNS 去向 {len(dns_cases)} 条：官方内核、模拟器、人工期望"
              + ("三者一致" if not bad else f"有 {len(bad)} 条不一致"))
        for x in bad[:20]:
            print("      " + x)
        failures += [f"{client} DNS：{x}" for x in bad]
        # 拨号时的解析：节点服务器的名字、域名形式的直连目标交给哪个 DNS 服务器（真实拨号，DNS 是本机替身）
        variant = client.split("-", 1)[1]
        dial = singbox_dial_probe(binary, a.srs_dir, model, plan, variant, dial_cases)
        bad = [f"{rd.dial_key(c)}：期望 {c['expect']}，官方内核 {dial[rd.dial_key(c)]}" for c in dial_cases
               if dial[rd.dial_key(c)] != c["expect"]]
        print(f"  [{'符合' if not bad else '不符合'}] 连接时的解析 {len(dial_cases)} 条（节点服务器的名字、域名形式的直连目标、"
              "走代理组的域名、没被域名规则接住的域名，各交给哪个 DNS 服务器；none = 三个替身都没有收到关于它的查询）："
              + ("官方内核与人工期望一致" if not bad else f"有 {len(bad)} 条不一致"))
        for c in dial_cases:
            print(f"      {rd.dial_key(c)} → {dial[rd.dial_key(c)]}")
        failures += [f"{client} 拨号解析：{x}" for x in bad]
        before = singbox_dial_probe(binary, a.srs_dir, model, plan, variant, dial_cases, strip_fix=True)
        moved = [rd.dial_key(c) for c in dial_cases if before[rd.dial_key(c)] != dial[rd.dial_key(c)]]
        print("      自检：去掉节点上的 domain_resolver 和局域网后缀的 resolve 规则后，"
              + ("、".join(f"{k} → {before[k]}" for k in moved) + "——这两处修正仍然需要" if moved
                 else "结果没有变化——这项核对没有起作用，或者内核的行为变了"))
        if not moved:
            failures.append(f"{client} 拨号解析：自检没有看到差别")
        # 境外 DNS 不应答（2026-10-06）：dns-foreign 的替身只收不答。连接那一半各保持 SILENT_HOLD 秒；
        # 查询那一半（设备发来的 DNS 查询）全部发完后再等 SILENT_HOLD 秒，按整个过程里谁收到过来认
        sil = rd.silent_cases(dial_cases)
        d3 = singbox_dial_probe(binary, a.srs_dir, model, plan, variant, sil, silent=("dns-foreign",), hold=SILENT_HOLD)
        _, q3 = singbox_probe(binary, a.srs_dir, files[rel], [], dns_cases, dns_map, silent=("dns-foreign",), hold=SILENT_HOLD)
        q3 = {f"{h} {q}": v for (h, q), v in q3.items()}
        normal_dns = {f"{h} {q}": v for (h, q), v in dns_got.items()}
        bad = [f"{k}：正常 {dial[k]}，境外 DNS 不应答时 {v}" for k, v in d3.items() if v != dial[k]]
        bad += [f"{k}：正常 {normal_dns[k]}，境外 DNS 不应答时 {v}" for k, v in q3.items() if v != normal_dns[k]]
        asked_foreign = [k for k, v in {**d3, **q3}.items() if v == "dns-foreign"]
        if not asked_foreign:
            bad.append("这一遍里没有任何用例问到境外 DNS：核对没有起作用")
        print(f"  [{'符合' if not bad else '不符合'}] 境外 DNS 不应答（dns-foreign 的替身只收不答，保持 {SILENT_HOLD:.0f} 秒）："
              f"连接 {len(d3)} 条、查询 {len(q3)} 条，"
              + (f"收到查询的替身与正常那一遍完全相同；其中 {len(asked_foreign)} 条只有境外替身收到——没有转去问国内 / 系统 DNS"
                 if not bad else f"有 {len(bad)} 条不一样"))
        for x in bad[:20]:
            print("      " + x)
        failures += [f"{client} 境外 DNS 不应答：{x}" for x in bad]
        # 出站时的解析（2026-10-07，自查 GPT 审核 r13 的 R13-F01 在 sing-box 上有没有）
        sb_ob = {}
        for scen in rd.OUTBOUND_SCENARIOS:
            core, outbound, transport = scen.split("-")
            if core == "singbox":
                sb_ob[scen] = singbox_outbound_probe(binary, a.srs_dir, files[rel], ob_hosts, outbound, transport)
        bad = [f"{scen} {c['host']}：期望 {c['expect'][scen]}，官方内核 {sb_ob[scen][c['host']]}"
               for scen in sb_ob for c in ob_cases if sb_ob[scen][c["host"]] != c["expect"][scen]]
        print(f"  [{'符合' if not bad else '不符合'}] 出站时的解析 {len(ob_cases)} 个主机 × {len(sb_ob)} 种出口"
              "（走代理的组换成 SOCKS 走 UDP、WireGuard 端点走 TCP）：" + ("官方内核与人工期望一致" if not bad else f"有 {len(bad)} 条不一致"))
        for c in ob_cases:
            print(f"      {c['host']}：" + "，".join(f"{scen[len('singbox-'):]} → {sb_ob[scen][c['host']]}"
                                                 + ("（已知限制的现状，见 docs/06）" if scen in c.get("limit", []) else "")
                                                 for scen in sb_ob))
        failures += [f"{client} 出站时的解析：{x}" for x in bad]
        # 两个版本的官方记录分开存：1.14 的在 singbox，1.12 的在 singbox112（测试里各比各的）
        official["singbox" if client == "singbox-1.14" else "singbox112"] = {
            "version": ver, "config": rel, "config_sha256": sha256_text(files[rel]),
            "routing_sha256": rd.routing_digest(rel, files[rel]),
            "routes": {t: list(v) for t, v in routes.items() if v},
            "dns": {f"{h} {q}": v for (h, q), v in dns_got.items()},
            "dial": dial, "dial_without_fix": before, "dial_foreign_silent": d3, "dns_foreign_silent": q3, "outbound": sb_ob,
            "dial_sha256": rd.dial_digest("singbox", rd.singbox_dial_base(model, plan, variant, dial_cases)[0])}

    # ---- 自检：把更正拿掉再跑一遍 ----
    upstream_state = self_check(a, files, dns_map)

    # ---- 国内 DNS 与路由的逐条扫描（mihomo、sing-box）----
    print("国内 DNS 与路由的逐条扫描（名字会交给国内 DNS 的集合，逐条取代表主机，看路由有没有把它交给代理组；说明见 tools/dns_route_consistency.py）：")
    consistency, bad = check_consistency(a, model, files, loaded, dns_map)
    failures += bad

    # ---- Loon / Quantumult X：只有模拟器。标准版和严格版各算一遍 ----
    for client, fam, parse, route in (("loon", "loon", emulate.parse_loon, emulate.loon_route),
                                      ("loon-strict", "loon", emulate.parse_loon, emulate.loon_route),
                                      ("quantumultx", "quantumultx", emulate.parse_qx, emulate.qx_route),
                                      ("quantumultx-strict", "quantumultx", emulate.parse_qx, emulate.qx_route)):
        conf = parse(files[CLIENT[client]])
        fx = emulate.SnapshotFixtures(snap, fam, dns_map)
        strict = client in rd.STRICT_KEYS
        bad, resolved = [], []
        for p in probes:
            t = p["host"] or p["ip"]
            trace = {}
            got1 = route(conf, emulate.Conn(host=p["host"], ip=p["ip"]), fx, trace=trace)
            want = p["expect"][client if strict else fam]
            if got1 != want and not (want == "广告拦截" and got1 == "REJECT"):
                bad.append(f"{t}：期望 {want}，模拟器 {got1}（{p['src']}）")
            if trace.get("resolved"):
                resolved.append(t)
        n_hosts = len({p["host"] for p in probes if p["host"]})
        print(f"{client}（没有官方内核，只有模拟器 + 真实的上游规则文件" + ("和这次生成的自有清单" if strict else "") + f"）：{len(probes)} 条，"
              + ("全部符合人工期望" if not bad else f"{len(bad)} 条不符合"))
        print(f"      为了判断 IP 规则而在本机解析过的域名：{n_hosts} 个里 {len(set(resolved))} 个"
              + ("（严格版应该是 0）" if strict else "（标准版的已知行为：没被域名规则接住的域名都要先解析）"))
        if strict and resolved:
            bad.append("严格版仍有域名要在本机解析后才能判断：" + "、".join(sorted(set(resolved))[:10]))
        for x in bad[:30]:
            print("      " + x)
        failures += [f"{client}：{x}" for x in bad]

    if a.write_snapshot:
        if failures:
            print("\n有不一致，没有写快照。")
        else:
            out = {
                "about": "核对用到的主机在真实上游集合里的成员关系，以及官方内核对同一批主机的判断结果。"
                         "由 tools/check_real_routes.py --write-snapshot 生成，不要手改；上游数据更新后结论可能变化。"
                         "hosts / ips 下各端的含义：mihomo、singbox 是“在哪个集合里（命中的条目）”；"
                         "loon、quantumultx 是“被哪个远程规则文件命中”。ips 的 cn 表示是否在国内 IP 段里"
                         "（mihomo 取自同一次发布的 geoip.dat，官方内核实际用的是 geoip.metadb；"
                         "Loon / Quantumult X 用 App 自带的库，拿不到，测试里假定与 mihomo 的一致）。"
                         "official 下是官方内核那一次运行的记录：mihomo；singbox（1.14 版配置 + 1.14 内核）；"
                         "singbox112（1.12 兼容版配置 + 1.12 内核）。dial 是拨号时名字交给谁解析："
                         "sing-box 记的是 DNS 服务器的标签，dial_without_fix 是把节点上的 domain_resolver 和局域网后缀的 "
                         "resolve 规则拿掉后的同一项结果；mihomo 记的是哪一类 DNS（system 系统、domestic 国内、foreign 境外，"
                         "核对时各换成一个本机替身），它的 dns 是设备发来的查询交给哪一类（没有替身收到时记内核自己回了什么："
                         "fake-ip 是直接给了假地址，empty 是直接回了一条记录都没有的应答）。mihomo 另有三组自检记录，是从 DNS 段里各去掉一样东西后的同一批结果："
                         "…_without_node_policy 去掉 proxy-server-nameserver-policy，…_without_follow_policy 去掉 "
                         "direct-nameserver-follow-policy，…_without_lan_policy 把 nameserver-policy 里交给系统 DNS 的几条改成国内 DNS。"
                         "这些都是生成快照那一天的记录，自动测试只是重放它，不会重新启动内核。"
                         "每份记录里有两个摘要，测试用它们确认记录对应的就是现在生成的配置：routing_sha256 是当时那份配置的"
                         "规则段与 DNS 段的摘要，管路由和 DNS 去向的记录；dial_sha256 是拨号核对那份配置里影响拨号解析的部分"
                         "（见 tools/real_data.py 的 dial_digest）的摘要，管拨号记录。"
                         "2026-10-06 起另有：dial 里 kind 为 proxied / unlisted 的用例（走代理组的域名、没被域名规则接住的域名，"
                         "连接过程中名字被哪个替身收到；none 表示都没有收到）；dial_foreign_silent / dns_foreign_silent 是把境外 DNS 的替身"
                         "改成只收不答、每个连接保持十几秒重跑的同一批结果，应当与正常那一遍相同；"
                         "consistency 是国内 DNS 与路由的逐条扫描（tools/dns_route_consistency.py）：swept 是扫了多少代表主机，"
                         "to_domestic 是其中名字会交给国内 DNS 的，consistent 是路由为国内直连 / 直连 / 拦截的，default_direct 是归默认直连、"
                         "可切换的组的，mismatch 是走代理组的（by_ip 表示它没被域名规则接住，去向取决于假定的解析结果），"
                         "official_checked 是交给官方内核核对过的主机数。2026-10-07 起另有 outbound：出站时的解析"
                         "（tests/cases.yaml 的 outbound_resolve：走代理的组换成真的出口、连本机空端口，看出口自己会不会再解析目标、交给谁），"
                         "mihomo 的 outbound_without_product_layer 是去掉 nameserver-policy 里产品域名那一层后的同一项自检。"
                         "loon 一类的成员记录里除了广告集合，还有 Loon 严格版订阅的"
                         "国内域名集合；严格版引用的自有远程规则文件不在快照里（它们就是产物本身）。",
                "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
                "source_version": model.project["project"]["source_version"],
                "assumed_dns": {"note": "解析结果是假定的：tests/fixtures.yaml 的 dns；没列出的主机一律当作解析到境外 IP",
                                "default": DEFAULT_FOREIGN_IP},
                "sources": sources, "sizes": sizes, "oddities": oddities, "without_corrections": upstream_state,
                "official": official, "consistency": consistency, "hosts": host_rec, "ips": ip_rec,
            }
            os.makedirs(os.path.dirname(rd.SNAPSHOT), exist_ok=True)
            with open(rd.SNAPSHOT, "w", encoding="utf-8", newline="\n") as f:
                json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
            print(f"\n已写入 {os.path.relpath(rd.SNAPSHOT, ROOT)}（主机 {len(host_rec)} 个，IP {len(ip_rec)} 个）")
    print()
    print("全部一致" if not failures else f"{len(failures)} 处不一致")
    return 1 if failures else 0


def self_check(a, files, dns_map) -> dict:
    """把针对上游数据加的更正（Qwen 国际版的显式规则、sing-box DNS 上的产品规则）从配置里拿掉，再交给官方内核：
    一是确认上面的检查对它们要防的错误是敏感的（拿掉以后确实会走错）；
    二是看上游数据现在的状态——哪天上游不再把这些域名算作国内，这里会显示“已经不需要”，更正可以删掉（留着也无害）。
    只打印，不影响退出码。
    没有更正、决定跟随上游的（整段 .ms），不在这里：它是 cases.yaml 的 upstream_followed 里的普通核对项，结果打印在各内核那一段。"""
    print("自检（把更正拿掉以后，官方内核怎么判断）：")
    state = {}
    conf = yaml.safe_load(files["mihomo/mihomo-core.yaml"])
    drop = {"DOMAIN-SUFFIX,qwen.ai,国外默认", "DOMAIN-SUFFIX,qwenlm.ai,国外默认"}
    kept = [r for r in conf["rules"] if r not in drop]
    if len(conf["rules"]) - len(kept) != len(drop):
        print("  没能从 mihomo 配置里找到要拿掉的两条规则（生成器的输出变了？）")
        return state
    conf["rules"] = kept
    got = mihomo_probe(a.mihomo, a.geodata_dir, yaml.safe_dump(conf, allow_unicode=True, sort_keys=False, width=100000),
                       ["chat.qwen.ai"], dns_map)
    for host, what in (("chat.qwen.ai", "Qwen 的显式规则"),):
        rule, group = got.get(host) or ("没有结果", "?")
        needed = group == "国内直连"
        state[f"mihomo {host}"] = {"group": group, "rule": rule, "correction_needed": needed}
        print(f"  mihomo：去掉 {what}后 {host} → {group}（{rule}）——"
              + ("更正仍然需要" if needed else "上游数据已经变了，这条更正现在是多余的（留着无害）"))
    conf = json.loads(files["sing-box/sing-box-1.14.json"])
    for r in conf["route"]["rules"]:
        if "qwen.ai" in r.get("domain_suffix", []):
            r["domain_suffix"] = [x for x in r["domain_suffix"] if x not in ("qwen.ai", "qwenlm.ai")] or ["placeholder.invalid"]
    rules = conf["dns"]["rules"]
    i_cn = next(i for i, r in enumerate(rules) if r.get("rule_set") == "geosite-cn")
    conf["dns"]["rules"] = rules[:2] + rules[i_cn:]
    routes, dns_got = singbox_probe(a.singbox, a.srs_dir, json.dumps(conf, ensure_ascii=False), ["chat.qwen.ai"],
                                    [{"host": "chat.qwen.ai", "type": "A"}, {"host": "music.apple.com", "type": "A"}], dns_map)
    rule, group = routes.get("chat.qwen.ai") or ("没有结果", "?")
    state["singbox chat.qwen.ai"] = {"group": group, "rule": rule, "correction_needed": group == "国内直连"}
    print(f"  sing-box：去掉 Qwen 的显式规则后 chat.qwen.ai → {group}（{rule}）——"
          + ("更正仍然需要" if group == "国内直连" else "上游数据已经变了，这条更正现在是多余的（留着无害）"))
    for host in ("chat.qwen.ai", "music.apple.com"):
        where = dns_got.get((host, "A"))
        state[f"singbox dns {host}"] = {"server": where, "correction_needed": where == "dns-cn"}
        print(f"  sing-box：去掉 DNS 上的产品规则后，{host} 的 A 查询交给 {where}——"
              + ("产品规则仍然需要" if where == "dns-cn" else "这个主机现在不靠它"))
    return state


CLIENT = {"mihomo-core": "mihomo/mihomo-core.yaml", "singbox-1.14": "sing-box/sing-box-1.14.json",
          "singbox-1.12": "sing-box/sing-box-1.12.json", "loon": "loon/loon.conf", "quantumultx": "quantumultx/quantumultx.conf",
          "loon-strict": "loon/loon-strict.conf", "quantumultx-strict": "quantumultx/quantumultx-strict.conf"}


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def compare(client: str, family: str, probes: list, got: dict, emu) -> list:
    """官方内核的结果、模拟器（真实成员快照）、人工期望三者对比。返回不一致的说明。"""
    bad, seen = [], set()
    for p in probes:
        t = p["host"] or p["ip"]
        want = p["expect"][family]
        if family == "singbox" and want == "广告拦截":
            want = "REJECT"
        real = got.get(t)
        sim = emu(t)
        key = (t, want)
        if key in seen:
            continue
        seen.add(key)
        if real is None:
            bad.append(f"{t}：官方内核没有给出结果")
        elif real[1] != want or sim != want:
            bad.append(f"{t}：期望 {want}，官方内核 {real[1]}（{real[0]}），模拟器 {sim}｜{p['src']}｜{p['why'][:60]}")
    print(f"  [{'符合' if not bad else '不符合'}] 路由 {len(seen)} 条：官方内核、模拟器（真实成员快照）、人工期望"
          + ("三者一致" if not bad else f"有 {len(bad)} 条不一致"))
    for x in bad[:40]:
        print("      " + x)
    for p in probes:
        if p.get("followed") and got.get(p["host"]):
            rule, group = got[p["host"]]
            print(f"      其中跟随上游的已知行为：{p['host']} → {group}（{rule}）"
                  + ("；这一端没有差异" if group == p["base"]
                     else f"；按需求本该去 {p['base']}，差异来自上游集合的内容，决定不更正（见 docs/06）"))
    return [f"{client}：{x}" for x in bad]


if __name__ == "__main__":
    sys.exit(main())

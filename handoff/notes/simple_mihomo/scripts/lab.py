#!/usr/bin/env python3
"""本机实验台（只监听 127.0.0.1）。用法：python3 -I lab.py <base_port> <nodes.json> <events.jsonl>

端口（base 起算）：
  base+0  源站 HTTP：HEAD/GET /generate_204 -> 204（健康检查）；其他路径 -> 200，正文 "node=<哪个节点转来的>"
          节点 nX 出站时绑定源地址 127.0.0.(10+X)，源站据此认出节点；127.0.0.1 来的记作 direct
  base+1  控制口：GET /mode?node=n1&m=up|refuse|blackhole|fail|egress ；GET /stats
  base+2  “境外 DNS”替身（TCP DNS）。节点收到 CONNECT 1.1.1.1:53 / 8.8.8.8:53 时转到这里
          答案：名字以 loop 开头的 -> 127.0.0.1；以 cn 开头的 -> 223.5.5.5（GeoIP 属 CN）；其余 -> 93.184.216.34（非 CN）；
          AAAA 等其他类型 -> 空的 NOERROR
  base+3  “国内 DNS”替身（TCP 和 UDP 都听）：A 一律答 127.0.0.1；其他类型 -> 空的 NOERROR
  base+4  “系统 DNS”替身（TCP 和 UDP 都听），答法同“国内 DNS”替身；只是为了不让实验里的查询离开这台机器
  base+10+X  节点 nX：最小 SOCKS5（无认证，只支持 CONNECT）。除了上面的 DNS 地址，CONNECT 到哪里都转给源站
节点模式：
  up        正常转发（按 nodes.json 的 delay_ms 在建立连接和每段回程数据上加延迟）
  refuse    关掉监听口并断开现有连接：新连接得到 connection refused（像节点进程挂了 / 端口关了）
  blackhole 接受 TCP 但永不回话；现有连接也停住不再转发（像丢包、机房断网）
  fail      SOCKS 握手后对 CONNECT 回失败码 0x05
  egress    SOCKS 回成功，随即断开（像“连上节点但节点出不去”）
  reset     接受 TCP 后立刻 RST（握手很快失败，但错误里不是 connection refused）
每个事件记一行 JSON 到 events.jsonl。"""
import asyncio
import ipaddress
import json
import struct
import sys
import time
from urllib.parse import urlparse, parse_qs

BASE = int(sys.argv[1])
NODES = json.load(open(sys.argv[2]))          # [{"id": "n1", "delay_ms": 10}, ...]
EVF = open(sys.argv[3], "a", buffering=1)
ORIGIN, CTRL, FDNS, DDNS, SDNS = BASE, BASE + 1, BASE + 2, BASE + 3, BASE + 4
DNS_TARGETS = {("1.1.1.1", 53), ("8.8.8.8", 53)}
ST = {}                                        # id -> dict(mode, delay, server, conns)


def ev(**kw):
    kw["t"] = round(time.time(), 3)
    EVF.write(json.dumps(kw, ensure_ascii=False) + "\n")


def node_of_src(ip):
    if ip == "127.0.0.1":
        return "direct"
    try:
        last = int(ip.split(".")[-1])
        return f"n{last - 10}" if last > 10 else ip
    except ValueError:
        return ip


async def read_head(reader):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data


# ---------------- 源站 ----------------
async def origin_handler(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    node = node_of_src(peer)
    try:
        while True:                             # 支持 keep-alive：统一延迟（unified-delay）会在同一连接上发两次 HEAD
            head = await read_head(reader)
            if not head:
                break
            line = head.split(b"\r\n", 1)[0].decode(errors="replace")
            parts = line.split()
            method, path = (parts[0], parts[1]) if len(parts) >= 2 else ("?", "?")
            close = b"connection: close" in head.lower()
            if path.startswith("/generate_204"):
                ev(kind="probe", node=node, method=method)
                writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n" +
                             (b"Connection: close\r\n" if close else b"") + b"\r\n")
            else:
                body = f"node={node}\n".encode()
                ev(kind="hello", node=node, method=method, path=path)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n" % len(body) +
                             (b"Connection: close\r\n" if close else b"") + b"\r\n" + (body if method != "HEAD" else b""))
            await writer.drain()
            if close:
                break
    except Exception as e:
        ev(kind="origin_err", err=repr(e)[:100])
    finally:
        try:
            writer.close()
        except Exception:
            pass


# ---------------- DNS 替身 ----------------
def parse_q(q):
    i = 12
    labels = []
    while q[i] != 0:
        ln = q[i]
        labels.append(q[i + 1:i + 1 + ln].decode(errors="replace"))
        i += ln + 1
    qtype = struct.unpack("!H", q[i + 1:i + 3])[0]
    return ".".join(labels).lower(), qtype, q[12:i + 5]


def answer(q, which):
    name, qtype, question = parse_q(q)
    qid = q[:2]
    ip = None
    if qtype == 1:
        if which == "foreign":
            if name.startswith("loop"):
                ip = "127.0.0.1"
            else:
                ip = "223.5.5.5" if name.startswith("cn") else "93.184.216.34"
        else:
            ip = "127.0.0.1"
    if ip:
        ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + ipaddress.IPv4Address(ip).packed
        resp = qid + b"\x81\x80" + struct.pack("!HHHH", 1, 1, 0, 0) + question + ans
    else:
        resp = qid + b"\x81\x80" + struct.pack("!HHHH", 1, 0, 0, 0) + question
    return name, qtype, ip, resp


def make_tcp_dns(which):
    async def handler(reader, writer):
        peer = writer.get_extra_info("peername")[0]
        try:
            while True:
                h = await reader.readexactly(2)
                ln = struct.unpack("!H", h)[0]
                q = await reader.readexactly(ln)
                name, qtype, ip, resp = answer(q, which)
                ev(kind="dns", server=which, via=node_of_src(peer), proto="tcp", name=name, qtype=qtype, ans=ip)
                writer.write(struct.pack("!H", len(resp)) + resp)
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
    return handler


class UdpDns(asyncio.DatagramProtocol):
    def __init__(self, which):
        self.which = which

    def connection_made(self, transport):
        self.tr = transport

    def datagram_received(self, data, addr):
        try:
            name, qtype, ip, resp = answer(data, self.which)
            ev(kind="dns", server=self.which, via=node_of_src(addr[0]), proto="udp", name=name, qtype=qtype, ans=ip)
            self.tr.sendto(resp, addr)
        except Exception as e:
            ev(kind="dns_err", err=repr(e)[:100])


# ---------------- 节点 ----------------
class UdpRelay(asyncio.DatagramProtocol):
    """节点的 UDP 中继：记下收到的包的目标（SOCKS5 UDP 头里的地址类型和地址），不转发。"""
    def __init__(self, nid):
        self.nid = nid

    def datagram_received(self, data, addr):
        try:
            atyp = data[3]
            if atyp == 1:
                dst, rest = str(ipaddress.IPv4Address(data[4:8])), data[8:]
            elif atyp == 3:
                ln = data[4]
                dst, rest = data[5:5 + ln].decode(errors="replace"), data[5 + ln:]
            elif atyp == 4:
                dst, rest = str(ipaddress.IPv6Address(data[4:20])), data[20:]
            else:
                dst, rest = "?", b""
            port = int.from_bytes(rest[:2], "big") if len(rest) >= 2 else None
            ev(kind="node_udp_packet", node=self.nid, atyp=atyp, dst=dst, port=port)
        except Exception as e:
            ev(kind="node_udp_err", node=self.nid, err=repr(e)[:80])


async def pipe(r, w, st, delay=0.0):
    try:
        while True:
            d = await r.read(65536)
            if not d:
                break
            while st["mode"] == "blackhole":
                await asyncio.sleep(0.2)
            if delay:
                await asyncio.sleep(delay)
            w.write(d)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


def make_node(nid, idx):
    st = ST[nid]

    async def handle(reader, writer):
        st["conns"].add(writer)
        try:
            if st["mode"] == "blackhole":
                ev(kind="node_blackhole", node=nid)
                await asyncio.sleep(3600)
                return
            if st["mode"] == "reset":                      # 接受 TCP 后立刻重置（RST），握手马上失败，错误里没有 "connection refused"
                await asyncio.sleep(0.05)
                ev(kind="node_reset", node=nid)
                writer.transport.abort()
                return
            g = await reader.readexactly(2)
            await reader.readexactly(g[1])
            writer.write(b"\x05\x00")
            await writer.drain()
            h = await reader.readexactly(4)
            cmd, atyp = h[1], h[3]
            if atyp == 1:
                host = str(ipaddress.IPv4Address(await reader.readexactly(4)))
            elif atyp == 3:
                ln = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(ln)).decode(errors="replace")
            elif atyp == 4:
                host = str(ipaddress.IPv6Address(await reader.readexactly(16)))
            else:
                return
            port = int.from_bytes(await reader.readexactly(2), "big")
            mode = st["mode"]
            if cmd == 3 and mode == "up":                  # UDP ASSOCIATE：只收包、记下目标写法（域名还是地址），不转发
                loop = asyncio.get_running_loop()
                tr, _ = await loop.create_datagram_endpoint(lambda: UdpRelay(nid), local_addr=(f"127.0.0.{10 + idx}", 0))
                a = tr.get_extra_info("sockname")
                ev(kind="node_udp_assoc", node=nid)
                writer.write(b"\x05\x00\x00\x01" + ipaddress.IPv4Address(a[0]).packed + a[1].to_bytes(2, "big"))
                await writer.drain()
                try:
                    await reader.read()                    # 控制连接断开 = 关联结束
                finally:
                    tr.close()
                return
            if cmd != 1:
                writer.write(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                ev(kind="node_cmd_unsupported", node=nid, cmd=cmd)
                return
            if mode == "blackhole":
                ev(kind="node_blackhole", node=nid, host=host, port=port)
                await asyncio.sleep(3600)
                return
            if mode == "fail":
                writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                ev(kind="node_fail_reply", node=nid, host=host, port=port)
                return
            if mode == "egress":
                writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                ev(kind="node_egress_broken", node=nid, host=host, port=port)
                return
            delay = st["delay"]
            if delay:
                await asyncio.sleep(delay)
            if (host, port) in DNS_TARGETS:
                dst = ("127.0.0.1", FDNS)
            else:
                dst = ("127.0.0.1", ORIGIN)
            ev(kind="node_connect", node=nid, host=host, port=port)
            ur, uw = await asyncio.open_connection(dst[0], dst[1], local_addr=(f"127.0.0.{10 + idx}", 0))
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            st["conns"].add(uw)
            await asyncio.gather(pipe(reader, uw, st), pipe(ur, writer, st, delay))
        except Exception as e:
            if not isinstance(e, asyncio.IncompleteReadError):
                ev(kind="node_err", node=nid, err=repr(e)[:100])
        finally:
            st["conns"].discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    return handle


async def start_node(nid, idx):
    ST[nid]["server"] = await asyncio.start_server(make_node(nid, idx), "127.0.0.1", BASE + 10 + idx)


async def set_mode(nid, m):
    st = ST[nid]
    idx = int(nid[1:])
    old = st["mode"]
    st["mode"] = m
    if m in ("refuse", "fail", "egress", "reset"):
        for w in list(st["conns"]):          # 进程挂了 / 状态变了：现有连接断开
            try:
                w.transport.abort()
            except Exception:
                pass
    if m == "refuse" and st["server"] is not None:
        st["server"].close()
        await st["server"].wait_closed()
        st["server"] = None
    if m != "refuse" and st["server"] is None:
        await start_node(nid, idx)
    ev(kind="mode", node=nid, old=old, new=m)


async def ctrl_handler(reader, writer):
    head = await read_head(reader)
    line = head.split(b"\r\n", 1)[0].decode()
    u = urlparse(line.split()[1])
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if u.path == "/mode":
        await set_mode(q["node"], q["m"])
        body = f"{q['node']}={q['m']}\n".encode()
    else:
        body = json.dumps({k: v["mode"] for k, v in ST.items()}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
    await writer.drain()
    writer.close()


async def main():
    loop = asyncio.get_running_loop()
    await asyncio.start_server(origin_handler, "127.0.0.1", ORIGIN)
    await asyncio.start_server(make_tcp_dns("foreign"), "127.0.0.1", FDNS)
    await asyncio.start_server(make_tcp_dns("domestic"), "127.0.0.1", DDNS)
    await loop.create_datagram_endpoint(lambda: UdpDns("domestic"), local_addr=("127.0.0.1", DDNS))
    await asyncio.start_server(make_tcp_dns("system"), "127.0.0.1", SDNS)
    await loop.create_datagram_endpoint(lambda: UdpDns("system"), local_addr=("127.0.0.1", SDNS))
    for n in NODES:
        ST[n["id"]] = {"mode": "up", "delay": n.get("delay_ms", 0) / 1000, "server": None, "conns": set()}
        await start_node(n["id"], int(n["id"][1:]))
    await asyncio.start_server(ctrl_handler, "127.0.0.1", CTRL)
    ev(kind="lab_ready", base=BASE, nodes=[n["id"] for n in NODES])
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

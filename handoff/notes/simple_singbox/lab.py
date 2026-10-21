"""本机实验台：只监听 127.0.0.1。
- 目标 HTTP 服务（127.0.0.1:HTTP_PORT）：HEAD/GET /generate_204 回 204；GET /hello 回 200，正文写明经哪个节点来的。
  节点 i 连目标时绑定源地址 127.0.0.(10+i)，所以服务端从来源地址就知道是哪个节点转发的。
- N 个最小 SOCKS5 节点（127.0.0.1:BASE+i），只支持无认证 CONNECT。
- 控制口（127.0.0.1:CTRL_PORT）：GET /set?node=n1&state=up|down|hang[&delay=ms]，GET /stats。
每次请求记一行 JSON 到 events.jsonl（时间、种类、节点）。"""
import asyncio
import json
import sys
import time
import urllib.parse

HTTP_PORT, BASE, CTRL_PORT, N = (int(x) for x in sys.argv[1:5])
LOG = sys.argv[5]
delays = {f"n{i}": int(d) for i, d in enumerate(sys.argv[6].split(","), start=1)}
T0 = time.time()

nodes = {}          # name -> dict(state, server, conns:set)
logf = open(LOG, "a", buffering=1)


def log(**kw):
    kw["t"] = round(time.time(), 3)
    logf.write(json.dumps(kw) + "\n")


async def read_head(reader):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            break
        data += chunk
    return data


async def http_handler(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    try:
        node = "n%d" % (int(peer.split(".")[-1]) - 10) if peer != "127.0.0.1" else "direct"
    except ValueError:
        node = "?"
    try:
        head = await read_head(reader)
        line = head.split(b"\r\n", 1)[0].decode(errors="replace")
        parts = line.split()
        method, path = (parts[0], parts[1]) if len(parts) >= 2 else ("?", "?")
        if path.startswith("/stream"):
            log(kind="stream_open", node=node)
            writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
            await writer.drain()
            for _ in range(900):
                writer.write(b".")
                await writer.drain()
                await asyncio.sleep(1)
            return
        if path.startswith("/generate_204"):
            log(kind="probe", node=node, method=method)
            writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
        else:
            body = f"node={node}\n".encode()
            log(kind="hello", node=node, method=method)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        await writer.drain()
    except Exception as e:
        log(kind="http_err", err=repr(e))
    finally:
        writer.close()


async def pipe(r, w, st=None):
    try:
        while True:
            b = await r.read(65536)
            if not b:
                break
            while st is not None and st["state"] == "freeze":
                await asyncio.sleep(0.2)
            w.write(b)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


def make_socks_handler(name, idx):
    async def handler(reader, writer):
        st = nodes[name]
        st["conns"].add(writer)
        try:
            if st["state"] in ("hang", "freeze"):
                log(kind="socks_hang", node=name)
                await asyncio.sleep(3600)
                return
            g = await reader.readexactly(2)
            await reader.readexactly(g[1])
            writer.write(b"\x05\x00")
            await writer.drain()
            h = await reader.readexactly(4)
            atyp = h[3]
            if atyp == 1:
                host = ".".join(str(x) for x in await reader.readexactly(4))
            elif atyp == 3:
                ln = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(ln)).decode()
            elif atyp == 4:
                import ipaddress
                host = str(ipaddress.IPv6Address(await reader.readexactly(16)))
            else:
                writer.close()
                return
            port = int.from_bytes(await reader.readexactly(2), "big")
            if st["delay"]:
                await asyncio.sleep(st["delay"] / 1000)
            if st["state"] != "up":
                writer.close()
                return
            tr, tw = await asyncio.open_connection(host, port, local_addr=(f"127.0.0.{10 + idx}", 0))
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            st["conns"].add(tw)
            await asyncio.gather(pipe(reader, tw, st), pipe(tr, writer, st))
        except Exception as e:
            log(kind="socks_err", node=name, err=repr(e)[:120])
        finally:
            st["conns"].discard(writer)
            try:
                writer.close()
            except Exception:
                pass
    return handler


async def start_node(name, idx):
    st = nodes[name]
    st["server"] = await asyncio.start_server(make_socks_handler(name, idx), "127.0.0.1", BASE + idx)


async def set_state(name, state, delay=None):
    st = nodes[name]
    idx = int(name[1:])
    if delay is not None:
        st["delay"] = delay
    old = st["state"]
    st["state"] = state
    for w in list(st["conns"]):          # 状态变了：断开现有连接
        if state not in ("up", "freeze"):
            try:
                w.transport.abort()
            except Exception:
                pass
    if state == "down" and st["server"] is not None:
        st["server"].close()
        await st["server"].wait_closed()
        st["server"] = None
    if state in ("up", "hang", "freeze") and st["server"] is None:
        await start_node(name, idx)
    log(kind="set", node=name, state=state, old=old, delay=st["delay"])


async def ctrl_handler(reader, writer):
    head = await read_head(reader)
    line = head.split(b"\r\n", 1)[0].decode()
    path = line.split()[1]
    u = urllib.parse.urlparse(path)
    q = dict(urllib.parse.parse_qsl(u.query))
    if u.path == "/set":
        await set_state(q["node"], q["state"], int(q["delay"]) if "delay" in q else None)
        body = b"ok\n"
    else:
        body = json.dumps({k: {"state": v["state"], "delay": v["delay"]} for k, v in nodes.items()}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
    await writer.drain()
    writer.close()


async def main():
    await asyncio.start_server(http_handler, "127.0.0.1", HTTP_PORT)
    for i in range(1, N + 1):
        name = f"n{i}"
        nodes[name] = {"state": "up", "server": None, "conns": set(), "delay": delays.get(name, 0)}
        await start_node(name, i)
    await asyncio.start_server(ctrl_handler, "127.0.0.1", CTRL_PORT)
    log(kind="lab_ready")
    await asyncio.Event().wait()


asyncio.run(main())

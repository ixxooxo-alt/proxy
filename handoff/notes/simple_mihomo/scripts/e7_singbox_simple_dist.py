#!/usr/bin/env python3
"""E7：sing-box 上同一件事——用生成器实际写出的简易版（emit_singbox 的 simple=True，带实验台的节点）核对
“境外 DNS（dns-foreign）经内部组“境外DNS”去问，不跟着国外默认里手选的节点走”，以及“境外DNS”用的节点挂了以后会怎样
（sing-box 的自动测速组只在定时检查时换节点：简易版 1 小时一次）。实验台和 E6 共用（scripts/lab.py），节点是 SOCKS5。
配置除了跑实验必须换的都不动：
  - 入站换成本机回环上的 mixed（原来是 TUN）；规则集换成本机的 .srs（$SRS_DIR，原来经“境外DNS”下载）；
  - dns-cn 换成本机“国内 DNS”替身；dns-foreign 换成 tcp://1.1.1.1:53，detour 不动（仍是“境外DNS”）——节点收到
    CONNECT 1.1.1.1:53 时转给实验台的“境外 DNS”替身；自动测速地址改成 http（实验台没有 TLS）；
  - 开 clash API（只听 127.0.0.1）用来选节点、看当前节点、触发测速；不开 cache_file（不记住选择）。
各段（每段一个全新的 sing-box 进程）：
  fd-refuse   国外默认 -> 美国 -> 美国 02（n5），n5 端口关闭：没被规则认出的域名要先经境外 DNS 解析
  dns-refuse  n5 正常；“境外DNS”当前用的节点端口关闭：每 5 秒发一个要靠境外 DNS 判断的连接，60 秒；
              然后经 clash API 对“境外DNS”测一次速（SFA 上点“测速”走的是同一组函数），再发几个
请求的目标：cn 开头的名字境外替身答 223.5.5.5（GeoIP 属 CN）→ 应该交给“国内直连”（直连到 223.5.5.5，这台机器上连不出去，
只看内核日志里的去向）；其余名字答 93.184.216.34 → 走国外默认。
用法：python3 -I e7_singbox_simple_dist.py <sing-box 二进制> <运行目录> <base_port> [段名,段名…]
      环境变量 SB_VARIANT=1.12 时用 1.12 兼容版的配置（规则集用 download_detour，没有 http_clients），配 sing-box 1.12 的二进制"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

BIN, OUT, BASE = sys.argv[1], sys.argv[2], int(sys.argv[3])
PHASES = sys.argv[4].split(",") if len(sys.argv) > 4 else ["fd-refuse", "dns-refuse"]
SRS = os.environ.get("SRS_DIR", "/root/proxy-vendor/srs")
os.makedirs(OUT, exist_ok=True)
MIX, API = BASE + 7, BASE + 8
DDNS = BASE + 3
ZONE = "qzx-lab-probe.net"
DNS_GROUP = "境外DNS"
HURL = "http://www.gstatic.com/generate_204"
NODES = [("日本 01", 1, 10), ("🇯🇵 Tokyo 02", 2, 60), ("香港 01", 3, 20), ("美国 01", 4, 40), ("美国 02", 5, 30)]
NODE_ID = {name: f"n{i}" for name, i, _ in NODES}

sys.dont_write_bytecode = True
sys.path.insert(0, mh.REPO)
from generator import emit_singbox, nodes as nodeconv  # noqa: E402
from generator.model import build_plan, load  # noqa: E402

m = load(mh.REPO, include_local=False)
plan = build_plan(m)
proxies = [{"name": n, "type": "socks5", "server": "127.0.0.1", "port": BASE + 10 + i, "udp": True} for n, i, _ in NODES]
# 2026-10-23（R20-F02）起完整版、简易版各自转换节点；这里只生成简易版。E7 是在两版共用一批节点时跑的，这几个节点名
# 和两版的组名都不重名（下一行断言没有改名），所以改成只避开简易版的组名以后，交给内核的配置一样
conv, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(m, simple=True))
assert not report and not renamed, (report, renamed)
VARIANT = os.environ.get("SB_VARIANT", "1.14")
conf = json.loads(emit_singbox.build(m, plan, VARIANT, conv, renamed, simple=True))
ob = {o["tag"]: o for o in conf["outbounds"]}
servers = {s["tag"]: s for s in conf["dns"]["servers"]}
assert servers["dns-foreign"]["detour"] == DNS_GROUP
if VARIANT == "1.14":
    assert conf["http_clients"][0]["detour"] == DNS_GROUP
else:
    assert all(rs.get("download_detour") == DNS_GROUP for rs in conf["route"]["rule_set"] if rs["type"] == "remote")
assert ob[DNS_GROUP]["type"] == "urltest" and ob[DNS_GROUP]["interval"] == "3600s", ob[DNS_GROUP]
print("境外DNS 的成员：", ob[DNS_GROUP]["outbounds"], "；国外默认：", ob["国外默认"]["outbounds"])

conf["log"] = {"level": "debug", "timestamp": True}
conf["inbounds"] = [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": MIX}]
servers["dns-cn"].clear()
servers["dns-cn"].update({"type": "tcp", "tag": "dns-cn", "server": "127.0.0.1", "server_port": DDNS})
servers["dns-foreign"].clear()
servers["dns-foreign"].update({"type": "tcp", "tag": "dns-foreign", "server": "1.1.1.1", "server_port": 53, "detour": DNS_GROUP})
conf.pop("http_clients", None)
conf["route"].pop("default_http_client", None)
conf["route"].pop("auto_detect_interface", None)
conf["route"]["rule_set"] = [rs if rs["type"] == "inline" else
                             {"type": "local", "tag": rs["tag"], "format": "binary", "path": os.path.join(SRS, rs["tag"] + ".srs")}
                             for rs in conf["route"]["rule_set"]]
for o in conf["outbounds"]:
    if o["type"] == "urltest":
        o["url"] = HURL
conf["experimental"] = {"clash_api": {"external_controller": f"127.0.0.1:{API}"}}
cfg = os.path.join(OUT, "config.json")
json.dump(conf, open(cfg, "w"), ensure_ascii=False, indent=1)
chk = subprocess.run([BIN, "check", "-c", cfg], capture_output=True, text=True)
print("sing-box check：", chk.returncode, chk.stderr.strip()[-300:])
if chk.returncode != 0:
    sys.exit(1)


def api(method, path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(f"http://127.0.0.1:{API}" + urllib.parse.quote(path, safe="/?=&"), data=data, method=method,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def now(group):
    return json.loads(api("GET", f"/proxies/{group}")[1]).get("now")


def request(host):
    """经 mixed 入口发一个 HTTP 代理请求；返回 (结果, 耗时)。结果：node=nX / 状态行 / timeout / 异常。"""
    return mh.http_via_proxy(MIX, host, BASE, timeout=8.0)


def outcome(log_text, host):
    """从内核日志里读这个名字：解析成功还是失败（“dns: lookup succeed / failed for <名字>”），连接交给了哪个出站
    （“open connection to [地址] using outbound/<类型>[<标签>]”）。"""
    lines = [ln for ln in log_text.splitlines() if host in ln]
    lookup = ("succeed" if any(f"lookup succeed for {host}" in ln for ln in lines)
              else "failed" if any(f"lookup failed for {host}" in ln for ln in lines) else "none")
    used = [x.group(2) + " -> " + x.group(1) for ln in lines
            for x in [re.search(r"open connection to \[([^\]]+)\] using outbound/\w+\[([^\]]+)\]", ln)] if x]
    return {"lookup": lookup, "outbound": used}


report = {"check": chk.returncode, "phases": []}
for phase in PHASES:
    home = os.path.join(OUT, phase)
    os.makedirs(home, exist_ok=True)
    lab = mh.Lab(BASE, [{"id": f"n{i}", "delay_ms": d} for _, i, d in NODES], home)
    logf = open(os.path.join(home, "sing-box.log"), "w")
    sb = subprocess.Popen([BIN, "run", "-c", cfg, "-D", home], stdout=logf, stderr=subprocess.STDOUT)
    T0 = time.time()
    res = {"phase": phase, "requests": []}
    try:
        if not mh.wait_port(API, 20):
            raise RuntimeError("sing-box 没起来，看 sing-box.log")
        time.sleep(2)
        res["select"] = [api("PUT", "/proxies/国外默认", {"name": "美国"})[0], api("PUT", "/proxies/美国", {"name": "美国 02"})[0]]
        warm = request(f"unlisted-warmup-{phase}.{ZONE}")
        time.sleep(1)
        res["now"] = {g: now(g) for g in ("国外默认", "美国", DNS_GROUP)}
        res["warmup"] = warm
        dns_node = NODE_ID.get(res["now"][DNS_GROUP])
        print(f"[{phase}] now：{res['now']}；境外DNS 用的是 {dns_node}；预热请求 {warm}")
        if phase == "fd-refuse":
            lab.mode("n5", "refuse")
            time.sleep(1)
            for host in (f"cnsite-{phase}.{ZONE}", f"unlisted-{phase}.{ZONE}"):
                r = request(host)
                res["requests"].append({"t": round(time.time() - T0, 2), "host": host, "res": r[0], "secs": r[1]})
                print(f"  [{phase}] {host} -> {r}")
        else:
            if dns_node in (None, "n5"):
                raise RuntimeError(f"境外DNS 当前用的节点是 {dns_node}，这一段要求它和国外默认用的 n5 不同")
            lab.mode(dns_node, "refuse")
            t1 = time.time()
            i = 0
            while time.time() - t1 < 60:
                host = f"cnsite-seq{i}-{phase}.{ZONE}"
                r = request(host)
                res["requests"].append({"t": round(time.time() - t1, 2), "host": host, "res": r[0], "secs": r[1], "now": now(DNS_GROUP)})
                i += 1
                time.sleep(5)
            st, body = api("GET", f"/group/{DNS_GROUP}/delay?url={urllib.parse.quote(HURL, safe='')}&timeout=5000", timeout=15)
            res["manual_test"] = {"t": round(time.time() - t1, 2), "status": st, "body": body[:200], "now_after": now(DNS_GROUP)}
            print(f"  [{phase}] 手动测速：{st} {body[:120]}；境外DNS 现在用 {res['manual_test']['now_after']}")
            for j in range(3):
                host = f"cnsite-after{j}-{phase}.{ZONE}"
                r = request(host)
                res["requests"].append({"t": round(time.time() - t1, 2), "host": host, "res": r[0], "secs": r[1], "now": now(DNS_GROUP)})
                time.sleep(2)
    finally:
        sb.terminate()
        try:
            sb.wait(10)
        except subprocess.TimeoutExpired:
            sb.kill()
        logf.close()
        lab.stop()
    log_text = open(os.path.join(home, "sing-box.log"), encoding="utf-8", errors="replace").read()
    for r in res["requests"]:
        r.update(outcome(log_text, r["host"]))
        print(f"  [{phase}] t={r['t']} {r['host']}: {r['res']}；解析 {r['lookup']}；去向 {r['outbound']}"
              + (f"；境外DNS={r.get('now')}" if "now" in r else ""))
    evs = lab.events()
    res["foreign_dns_via"] = sorted({e["via"] for e in evs if e.get("kind") == "dns" and e.get("server") == "foreign"})
    print(f"  [{phase}] 境外 DNS 替身收到的查询经过：{res['foreign_dns_via']}")
    report["phases"].append(res)
json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
print("done")

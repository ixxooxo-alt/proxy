"""一次性核对（2026-10-21）：使用者 2026-10-20 发来的 Loon“DNS 记录”截图里，国内 DoH 给出的地址归谁、算不算中国。

用法（在仓库根目录，source ~/proxy-vendor/env.sh 之后）：
    "$SINGBOX_BIN" rule-set decompile "$SRS_DIR/geoip-cn.srs" -o /tmp/geoip-cn.json
    python3 -I handoff/notes/r19_loon_dns_ip_lookup.py "$GEODATA_DIR" /tmp/geoip-cn.json > handoff/notes/r19_loon_dns_ip_lookup.out

地址是从截图上抄的（截图本身不进仓库）。截图里还有一条节点服务器名字的查询，那是机场的信息，没有抄进来。
三份地址库都是 handoff/setup_env.sh 登记过的：GeoLite2-ASN.mmdb、country.mmdb（MetaCubeX 2026-10-05 发布文件）、
sing-geoip 的 geoip-cn.srs（2026-09-12）。Loon 自己用哪份地址库判断 GEOIP，没有核对。
MaxMind 格式只用到读取所需的最小部分，自己写的，没有用第三方库。
"""
import ipaddress
import json
import struct
import sys

# （域名，截图里显示的 DNS 服务器，地址）；截图底部被搜索框挡住一部分的两条标了“部分遮挡”
RECORDS = [
    ("bbc.gscontxt.net", "1.12.12.12", ["158.178.243.190", "138.2.79.27", "129.150.58.80", "129.150.52.17"]),
    ("web-cdn.api.bbci.co.uk", "223.5.5.5", ["157.240.12.36"]),
    ("open.live.bbc.co.uk", "223.5.5.5", ["202.160.129.36"]),
    ("r.bbci.co.uk", "223.5.5.5", ["202.160.130.52"]),
    ("federated-id.live.api.bbc.co.uk", "223.5.5.5", ["108.160.167.158"]),
    ("a1.api.bbc.co.uk", "223.5.5.5", ["173.255.209.47"]),
    ("bag.api.bbc.co.uk", "1.12.12.12", ["202.160.130.118"]),
    ("mybbc-analytics.files.bbci.co.uk", "223.5.5.5", ["104.244.46.211"]),
    ("nav.files.bbci.co.uk", "223.5.5.5", ["66.220.148.145"]),
    ("nsi.activity.api.bbc.com", "223.5.5.5（部分遮挡）", ["69.162.134.178"]),
    ("idcta.api.bbc.com", "（部分遮挡）", ["108.160.166.42"]),
    ("vod-hls-ww-live.akamaized.net", "1.12.12.12（部分遮挡）", ["23.206.188.213", "23.206.188.206"]),
    ("vod-thumb-ww-live.akamaized.net", "（部分遮挡）", ["23.63.84.147", "23.63.84.153"]),
    ("api.revenuecat.com", "223.5.5.5", ["13.33.183.36", "13.33.183.21", "13.33.183.24", "13.33.183.61"]),
    ("wetype.weixin.qq.com", "223.5.5.5", ["120.233.18.62"]),
    ("kt-prod.ess.apple.com", "223.5.5.5", ["17.145.16.2"]),
    ("configuration.apple.com", "1.12.12.12", ["183.250.178.87", "183.250.178.90", "183.250.178.130",
                                                "183.250.178.131", "183.250.178.89", "183.250.178.91",
                                                "183.250.178.88"]),
    ("amp-api-edge.apps.apple.com", "1.12.12.12", ["183.250.178.91", "183.250.178.8", "183.250.178.9"]),
]


def mmdb_open(path):
    buf = open(path, "rb").read()
    mark = buf.rfind(b"\xab\xcd\xefMaxMind.com")
    meta, _ = _decode(buf, mark + 14, mark + 14)
    return buf, meta


def _decode(buf, pos, base):
    ctrl = buf[pos]
    pos += 1
    typ = ctrl >> 5
    if typ == 1:  # 指针
        ss, v = (ctrl >> 3) & 3, ctrl & 7
        b = buf[pos:pos + ss + 1]
        pos += ss + 1
        off = [(v << 8) | b[0], ((v << 16) | int.from_bytes(b, "big")) + 2048,
               ((v << 24) | int.from_bytes(b, "big")) + 526336, int.from_bytes(b, "big")][ss]
        return _decode(buf, base + off, base)[0], pos
    if typ == 0:
        typ = 7 + buf[pos]
        pos += 1
    size = ctrl & 0x1F
    if size == 29:
        size, pos = 29 + buf[pos], pos + 1
    elif size == 30:
        size, pos = 285 + int.from_bytes(buf[pos:pos + 2], "big"), pos + 2
    elif size == 31:
        size, pos = 65821 + int.from_bytes(buf[pos:pos + 3], "big"), pos + 3
    if typ == 2:
        return buf[pos:pos + size].decode("utf-8"), pos + size
    if typ == 3:
        return struct.unpack(">d", buf[pos:pos + 8])[0], pos + 8
    if typ == 4:
        return buf[pos:pos + size].hex(), pos + size
    if typ in (5, 6, 9, 10):
        return int.from_bytes(buf[pos:pos + size], "big"), pos + size
    if typ == 8:
        return int.from_bytes(buf[pos:pos + size].rjust(4, b"\0"), "big", signed=True), pos + size
    if typ in (7, 11):
        out = {} if typ == 7 else []
        for _ in range(size):
            if typ == 7:
                k, pos = _decode(buf, pos, base)
                out[k], pos = _decode(buf, pos, base)
            else:
                v, pos = _decode(buf, pos, base)
                out.append(v)
        return out, pos
    if typ == 14:
        return bool(size), pos
    if typ == 15:
        return struct.unpack(">f", buf[pos:pos + 4])[0], pos + 4
    raise ValueError(f"不认识的类型 {typ}")


def mmdb_lookup(db, ip):
    buf, meta = db
    n, rs = meta["node_count"], meta["record_size"]
    nbytes = rs * 2 // 8
    data = nbytes * n + 16

    def rec(node, bit):
        b = buf[node * nbytes:(node + 1) * nbytes]
        if rs == 24:
            return int.from_bytes(b[3:6] if bit else b[0:3], "big")
        if rs == 28:
            return (((b[3] & 0x0F) << 24) | int.from_bytes(b[4:7], "big")) if bit else \
                (((b[3] >> 4) << 24) | int.from_bytes(b[0:3], "big"))
        return int.from_bytes(b[4:8] if bit else b[0:4], "big")

    node = 0
    if meta["ip_version"] == 6:          # IPv4 地址在 IPv6 树里从 ::/96 开始
        for _ in range(96):
            node = rec(node, 0)
            if node >= n:
                break
    for ch in format(int(ipaddress.ip_address(ip)), "032b"):
        if node >= n:
            break
        node = rec(node, int(ch))
    if node <= n:
        return None
    return _decode(buf, data + (node - n) - 16, data)[0]


def main():
    geodata, geoip_cn_json = sys.argv[1], sys.argv[2]
    asn = mmdb_open(geodata + "/GeoLite2-ASN.mmdb")
    country = mmdb_open(geodata + "/country.mmdb")
    rs = json.load(open(geoip_cn_json, encoding="utf-8"))
    cn_nets = [ipaddress.ip_network(c) for r in rs["rules"] for c in r.get("ip_cidr", [])]
    cn_v4 = [x for x in cn_nets if x.version == 4]
    print("域名\tDNS 服务器（截图）\t地址\tASN 组织（GeoLite2-ASN）\tcountry.mmdb\tgeoip-cn")
    for host, server, ips in RECORDS:
        for ip in ips:
            a = mmdb_lookup(asn, ip) or {}
            c = mmdb_lookup(country, ip) or {}
            in_cn = any(ipaddress.ip_address(ip) in net for net in cn_v4)
            print("\t".join([host, server, ip,
                             f"AS{a.get('autonomous_system_number')} {a.get('autonomous_system_organization')}",
                             str((c.get("country") or {}).get("iso_code")),
                             "CN" if in_cn else "-"]))


if __name__ == "__main__":
    main()

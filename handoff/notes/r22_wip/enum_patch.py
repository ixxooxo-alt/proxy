"""把 F03 同一类自查的白名单改进 generator/nodes.py 和 generator/verify.py（在仓库根目录运行）。"""
p = "generator/nodes.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep('''# sing-box 1.14 各出站是否有 network 字段（option/*.go 的结构体）；http、anytls 没有（审核 F01）''',
'''# 原样写给 sing-box、取值有限的字段（全项目复核 F03 的同一类，2026-11-18）：sing-box 1.14.1、1.12.0 建出站时只认下面这些，
# 别的取值报错，整份配置都启动不了（不只是少一个节点）。取值表是拿两个官方程序逐个跑 sing-box check 得来的
# （handoff/notes/r22_singbox_enum_sweep.out）。不在表里的跳过这个节点、写进报告。例如 mihomo 文档列着的 aes-128-ccm、
# chacha8-ietf-poly1305、lea-128-gcm 等加密方式，mihomo 认的 chrome120、firefox120、safari16 指纹，sing-box 都不认
SS_METHODS = {"aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
              "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305", "none",
              "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
              "rc4-md5", "chacha20-ietf", "xchacha20"}
VMESS_SECURITY = {"auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-cfb"}
VLESS_FLOWS = {"xtls-rprx-vision"}
TUIC_CONGESTION = {"cubic", "new_reno", "bbr"}
UTLS_FINGERPRINTS = {"chrome", "firefox", "edge", "safari", "360", "qq", "ios", "android", "random", "randomized",
                     "chrome_psk", "chrome_psk_shuffle", "chrome_padding_psk_shuffle", "chrome_pq", "chrome_pq_psk"}
MUX_PROTOCOLS = {"smux", "yamux", "h2mux"}


def _enum(v, allowed: set, key: str):
    if not isinstance(v, str) or v not in allowed:
        raise Unsupported(f"{key}={json.dumps(v, ensure_ascii=False)}：sing-box 1.14.1、1.12.0 都不认这个取值"
                          "（建出站时报错，整份配置启动不了），跳过这个节点")
    return v


# sing-box 1.14 各出站是否有 network 字段（option/*.go 的结构体）；http、anytls 没有（审核 F01）''')

rep('''    if not enabled:
        if reality:
            raise Unsupported("提供了 reality-opts 却未启用 TLS，无法确定原意")
        return None          # 未启用 TLS 时 servername / alpn / 指纹在 mihomo 中同样不生效
    t = {"enabled": True}''', '''    if not enabled:
        if reality:
            raise Unsupported("提供了 reality-opts 却未启用 TLS，无法确定原意")
        return None          # 未启用 TLS 时 servername / alpn / 指纹在 mihomo 中同样不生效
    # client-fingerprint：没写、写 none 在 mihomo 里都是不用 uTLS（v1.19.31 component/tls/utls.go 的 GetFingerprint），
    # 以前把 none 原样写成 uTLS 指纹，sing-box 不认、整份配置启动不了（全项目复核 F03 的同一类）
    if cf in (None, "", "none"):
        cf = None
    else:
        _enum(cf, UTLS_FINGERPRINTS, "client-fingerprint")
    if reality and not cf:
        # sing-box 的 Reality 必须带 uTLS（不带时建出站报 uTLS is required by reality client）；
        # mihomo 也一样，连接时报 REALITY is based on uTLS（transport/vmess/tls.go）
        raise Unsupported("Reality 要有 client-fingerprint（uTLS 指纹）：订阅里没写或写的是 none，sing-box 建出站时报错，mihomo 连接时也报错")
    t = {"enabled": True}''')

rep('''        mx = {"enabled": True, "protocol": smux.get("protocol", "h2mux")}''',
    '''        mx = {"enabled": True, "protocol": _enum(smux.get("protocol", "h2mux"), MUX_PROTOCOLS, "smux.protocol")}''')
rep('''        ob["method"] = _req(d, used, "cipher")''', '''        ob["method"] = _enum(_req(d, used, "cipher"), SS_METHODS, "cipher")''')
rep('''        ob["security"] = _take(d, used, "cipher", "auto")''',
    '''        ob["security"] = _enum(_take(d, used, "cipher") or "auto", VMESS_SECURITY, "cipher")''')
rep('''        flow = _take(d, used, "flow")
        if flow:
            ob["flow"] = flow''', '''        flow = _take(d, used, "flow")
        if flow:
            ob["flow"] = _enum(flow, VLESS_FLOWS, "flow")''')
rep('''        cc = _take(d, used, "congestion-controller")
        if cc:
            ob["congestion_control"] = cc''', '''        cc = _take(d, used, "congestion-controller")
        if cc:
            ob["congestion_control"] = _enum(cc, TUIC_CONGESTION, "congestion-controller")''')
open(p, "w", encoding="utf-8").write(s)

p = "generator/verify.py"
s = open(p, encoding="utf-8").read()
rep('''        if isinstance(tls, dict) and "insecure" in tls and tls["insecure"] is not True:
            problems.append(f"节点 {o.get('tag')} 的 tls.insecure 是 {tls['insecure']!r}：只在订阅要求跳过证书校验时写，写了就是 true")''',
'''        if isinstance(tls, dict) and "insecure" in tls and tls["insecure"] is not True:
            problems.append(f"节点 {o.get('tag')} 的 tls.insecure 是 {tls['insecure']!r}：只在订阅要求跳过证书校验时写，写了就是 true")
        # 同一类（F03）：sing-box 只认一部分取值的字段，取值表和转换器共用（generator/nodes.py，来自官方程序的逐个核对）
        utls = tls.get("utls") if isinstance(tls, dict) else None
        mux = o.get("multiplex")
        for field, value, allowed in (
                ("method", o.get("method") if t == "shadowsocks" else None, nodes.SS_METHODS),
                ("security", o.get("security") if t == "vmess" else None, nodes.VMESS_SECURITY),
                ("flow", o.get("flow") or None if t == "vless" else None, nodes.VLESS_FLOWS),
                ("congestion_control", o.get("congestion_control") if t == "tuic" else None, nodes.TUIC_CONGESTION),
                ("tls.utls.fingerprint", utls.get("fingerprint") if isinstance(utls, dict) and utls.get("enabled") else None,
                 nodes.UTLS_FINGERPRINTS),
                ("multiplex.protocol", mux.get("protocol") if isinstance(mux, dict) and mux.get("enabled") else None,
                 nodes.MUX_PROTOCOLS)):
            if value is not None and value not in allowed:
                problems.append(f"节点 {o.get('tag')} 的 {field} 是 {value!r}：sing-box 1.14.1、1.12.0 不认，建出站时报错")
        if isinstance(tls, dict) and isinstance(tls.get("reality"), dict) and tls["reality"].get("enabled") and \\
                not (isinstance(utls, dict) and utls.get("enabled")):
            problems.append(f"节点 {o.get('tag')} 用了 Reality 却没有 uTLS：sing-box 建出站时报错")''')
open(p, "w", encoding="utf-8").write(s)
print("patched")

p = "generator/verify.py"
s = open(p, encoding="utf-8").read()
rep("from . import strict as strict_mod\n", "from . import nodes\nfrom . import strict as strict_mod\n")
open(p, "w", encoding="utf-8").write(s)
print("import added")

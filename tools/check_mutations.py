#!/usr/bin/env python3
"""变异检查：在项目副本里逐一注入与各轮改动相关的错误，确认测试能发现。

每个变异在临时目录的独立副本里进行，不改动项目本身。副本不含 dist/，这样“产物与统一源一致”那项检查不会
替语义测试把错误兜住（副本里那一项会显示为 skipped）。
用法：python3 tools/check_mutations.py [M1 M2 …]      不带参数时跑全部；每个变异约 1 分钟（共 35 个）。
退出码：有变异没被发现时为 1。
"""
import os, re, shutil, subprocess, sys, tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_case(name, edits, expect_in_output=None):
    tmp = tempfile.mkdtemp(prefix="mut-")
    dst = os.path.join(tmp, "p")
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    for rel, fn in edits:
        p = os.path.join(dst, rel)
        s = open(p, encoding="utf-8").read()
        s2 = fn(s)
        assert s2 != s, f"{name}: 变异没有生效 {rel}"
        open(p, "w", encoding="utf-8").write(s2)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=dst,
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    last = [l for l in out.splitlines() if l.startswith(("FAILED", "OK", "Ran "))]
    failing = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", out, re.M)))
    caught = r.returncode != 0
    extra = ""
    if expect_in_output:
        extra = "；输出含预期信息" if expect_in_output in out else "；未见预期信息"
    print(f"[{'发现' if caught else '未发现'}] {name}：{' / '.join(last)}；失败项 {[f'{c.split(chr(46))[-1]}.{t}' for t, c in failing]}{extra}")
    shutil.rmtree(tmp)
    return caught

def move_apple_ai_after_apple(s):
    m = re.search(r"(  # ---------- Apple AI.*?\n)(  - id: apple_media\n)", s, re.S)
    block = m.group(1)
    s = s.replace(block, "", 1)
    i = s.index("  - id: google\n")
    return s[:i] + block + "\n" + s[i:]

cases = [
    ("M1 Apple AI 服务挪到 Apple 之后（书写位置）", [("source/services/bigtech.yaml", move_apple_ai_after_apple)], "书写顺序"),
    ("M2 国内常用网站也写进 Loon / QX", [("source/services/misc.yaml", lambda s: s.replace("    clients: [mihomo, singbox]\n", "", 1))], "ad.12306.cn"),
    ("M3 删掉一条 Apple AI 规则（smoot.apple.com）", [("source/services/bigtech.yaml", lambda s: re.sub(r"      - \{suffix: smoot\.apple\.com,[^\n]*\n", "", s, 1))], "不增不减"),
    ("M4 从 Apple 组删掉 apple-dns.net", [("source/services/bigtech.yaml", lambda s: s.replace("      - {suffix: apple-dns.net, ev: dlc}\n", "", 1))], "apple-dns.net"),
    ("M5 Apple AI 默认改成日本", [("source/groups.yaml", lambda s: s.replace("{name: Apple AI,  category: AI, default: 美国", "{name: Apple AI,  category: AI, default: 日本", 1))], "Apple AI"),
    ("M6 恢复关键词规则 siri", [("source/services/bigtech.yaml", lambda s: s.replace("      - {suffix: siri.com, ev: dlc,", "      - {keyword: siri, ev: apple-ai-req, note: x}\n      - {suffix: siri.com, ev: dlc,", 1))], None),
    ("M7 sora.com 放回 OpenAI", [("source/services/ai.yaml", lambda s: s.replace("    rules:\n", "    rules:\n      - {suffix: sora.com, ev: maintainer, note: x}\n", 1))], "sora.com"),
    ("M8 Grok 组去掉 spacex.ai 登录域", [("source/services/ai.yaml", lambda s: re.sub(r"      - \{suffix: spacex\.ai,[^\n]*\n", "", s, 1))], "accounts.spacex.ai"),
    ("M9 azure.com 放回 Microsoft", [("source/services/bigtech.yaml", lambda s: s.replace("  - id: microsoft\n", "  - id: microsoft\n", 1).replace("      - {suffix: microsoft.com,", "      - {suffix: azure.com, ev: dlc}\n      - {suffix: microsoft.com,", 1))], None),
    ("M10 byteoversea.com 放回 TikTok", [("source/services/streaming.yaml", lambda s: s.replace("      - {suffix: tiktok.com,", "      - {suffix: byteoversea.com, ev: dlc}\n      - {suffix: tiktok.com,", 1))], "byteoversea"),
    # ---- 2026-09-30 审核修复（Astra r5）----
    ("M11 mihomo 去掉局域网后缀的系统 DNS（F04）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '                ",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"],\n', "", 1))], "nameserver"),
    ("M12 graph.instagram.com 放回自有拦截（F05）", [("source/adblock.yaml", lambda s: re.sub(
        r"  - \{suffix: graph\.instagram\.com, ev: meta-ig-api,[^\n]*\n", "", s, 1).replace(
        "local_tracking:\n", "local_tracking:\n  - {suffix: graph.instagram.com, ev: dlc, note: x}\n", 1))], "graph.instagram.com"),
    ("M13 HTTP 出站又写 network 字段（F01）", [("generator/nodes.py", lambda s: s.replace(
        'NETWORK_FIELD = {"shadowsocks",', 'NETWORK_FIELD = {"http", "shadowsocks",', 1))], "network"),
    ("M14 v2ray-plugin 的 mux=false 又被省略（F03）", [("generator/nodes.py", lambda s: s.replace(
        '("0" if o.get("mux") is False', '("1" if o.get("mux") is False', 1))], "mux=0"),
    ("M15 缺密码又写成字符串 None（F12）", [("generator/nodes.py", lambda s: s.replace(
        '        ob["password"] = _req(d, used, "password")\n        plugin = _take(d, used, "plugin")',
        '        ob["password"] = str(d.get("password"))\n        used.add("password")\n        plugin = _take(d, used, "plugin")', 1))], None),
    ("M16 节点与组同名不再改名（F02）", [("generator/nodes.py", lambda s: s.replace(
        "        if tag in taken:\n            n = 1", "        if False:\n            n = 1", 1))], None),
    ("M17 私密步骤失败前先写公开产物（F07）", [("build.py", lambda s: s.replace(
        "    # ---------- 2. 私密产物", "    write_all({os.path.join(a.out, rel): text for rel, text in files.items()})\n    # ---------- 2. 私密产物", 1))], None),
    ("M18 --check 又跳过 manifest（F10）", [("build.py", lambda s: s.replace(
        "            path = os.path.join(a.out, rel)\n            if not os.path.exists(path):",
        "            path = os.path.join(a.out, rel)\n            if rel == \"manifest.json\":\n                continue\n            if not os.path.exists(path):", 1))], None),
    ("M19 公开产物又带上 local.yaml（F11）", [("build.py", lambda s: s.replace(
        "        model = load(root, include_local=False)", "        model = load(root, include_local=True)", 1))], "corp-secret"),
    ("M20 写盘前不再做结构检查（F09，源校验与产物检查两层都关掉）", [
        ("generator/model.py", lambda s: s.replace(
            'if e.get("target") is not None and e["target"] not in names | {"DIRECT"}:', "if False:", 1).replace(
            "        if grp.name in grp.members:", "        if False:", 1)),
        ("generator/verify.py", lambda s: s.replace(
            '    """files：{相对路径: 内容}。按文件名判断格式，返回“文件：问题”列表。"""\n',
            '    """files：{相对路径: 内容}。按文件名判断格式，返回“文件：问题”列表。"""\n    return []\n', 1))], None),
    ("M21 检查脚本又总是返回 0（F08）", [("tools/run_checks.sh", lambda s: s.replace("  exit 1\nfi", "  exit 0\nfi", 1))], None),
    ("M22 xAI 放回其他 AI（与 Cursor 合并的决定）", [("source/services/ai.yaml", lambda s: s.replace(
        "  - id: xai\n    group: Grok", "  - id: xai\n    group: 其他 AI", 1))], "Grok"),
    # ---- 2026-10-02 节点名称分地区 ----
    ("M23 香港不再让位", [("source/regions.yaml", lambda s: s.replace("    yields: true\n", "", 1))], "香港"),
    ("M24 🇨🇳 当成其他国家的国旗", [("source/regions.yaml", lambda s: s.replace(
        "  neutral_flags: [CN, EU, UN]", "  neutral_flags: [EU, UN]", 1))], "台湾"),
    ("M25 信息词加回单独的“流量”", [("source/regions.yaml", lambda s: s.replace(
        "    words: [剩余, 剩餘,", "    words: [流量, 剩余, 剩餘,", 1))], "大流量"),
    ("M26 英文代码不再要求前后不挨字母", [("generator/regions.py", lambda s: s.replace(
        'parts.append(_guard(latin, True) + r"(?<![A-Za-z])" + before + _trie(latin, True) + r"(?![A-Za-z])")',
        'parts.append(_guard(latin, True) + before + _trie(latin, True))', 1))], "RUS"),
    ("M27 不再处理中转词", [("source/regions.yaml", lambda s: re.sub(
        r"  transit_after: \[[^\]]*\]", "  transit_after: []", s, 1))], "中转"),
    ("M28 国旗不按成对对齐", [("generator/regions.py", lambda s: s.replace(
        'return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})(?:{_RI}{_RI})*"',
        'return f"(?!(?!{_RI}))" + self.before', 1))], "🇨🇳🇺🇸"),
    ("M29 各地区的组都用了日本的正则", [("generator/groups.py", lambda s: s.replace(
        'nf = NodeFilter(label=r["id"], regex=node_rx[r["id"]])', 'nf = NodeFilter(label=r["id"], regex=node_rx["jp"])', 1))], None),
    ("M30 词表里删掉“达拉斯”", [("source/regions.yaml", lambda s: s.replace("达拉斯, ", "", 1))], "达拉斯"),
    ("M31 正则里用回肯定前瞻（含等号）", [("generator/regions.py", lambda s: s.replace(
        'return "(?!)" if x is None else "(?!(?!.*" + x + "))"', 'return "(?!)" if x is None else "(?=.*" + x + ")"', 1))], None),
    ("M32 其他国家的词不再压过地区词", [("generator/regions.py", lambda s: s.replace(
        'by_text = (_neg(self.eff([oid])) + "(?:" + _pos(self.eff([r.id])) + "|"',
        'by_text = ("(?:" + _pos(self.eff([r.id])) + "|"', 1))], "英国"),
    ("M33 mihomo 的别名指错地区", [("generator/emit_mihomo.py", lambda s: s.replace(
        'self.name = {rx: "flt-" + labels[rx] for rx, n in count.items() if n > 1}',
        'self.name = {rx: "flt-x" for rx, n in count.items() if n > 1}', 1))], None),
    ("M34 via 不再要求单独成词（Monrovia、Bolivia 里的 via 也算）", [("generator/regions.py", lambda s: s.replace(
        "            if _ASCII_LETTERS.match(b):\n                latin_before.append(lit(b))",
        "            if False:\n                latin_before.append(lit(b))", 1))], "Monrovia"),
    ("M35 信息词里删掉“过滤掉”", [("source/regions.yaml", lambda s: s.replace(", 过滤掉, 過濾掉]", "]", 1))], "过滤掉"),
]
only = sys.argv[1:]
res = [run_case(*c) for c in cases if not only or c[0].split()[0] in only]
print(f"合计 {sum(res)}/{len(res)} 被发现")
sys.exit(0 if all(res) else 1)

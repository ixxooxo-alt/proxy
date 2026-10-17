#!/usr/bin/env python3
"""变异检查：在项目副本里逐一注入与各轮改动相关的错误，确认测试能发现。

每个变异在临时目录的独立副本里进行，不改动项目本身。副本不含 dist/，这样“产物与统一源一致”那项检查不会
替语义测试把错误兜住（副本里那一项会显示为 skipped）。
用法：python3 tools/check_mutations.py [M1 M2 …]      不带参数时跑全部；每个变异约 4 分钟（2026-10-07：测试一遍约 230 秒；共 170 个，可以分几批同时跑，见 handoff/release/run_mutations.sh）
      python3 tools/check_mutations.py --check-edits  只确认每个变异的改动还能套到当前代码上（不跑测试，几秒钟）
      python3 tools/check_mutations.py --help         显示这段说明
退出码：有变异没被发现、或者测试没有正常结束（超时）时为 1。超时不算“被发现”：测试卡住和测试报错是两回事。
认不出的参数（写错的选项、不存在的编号）为 2，什么都不跑。

有一个变异（M45，回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，
专门的那项测试把匹配放在子进程里并带超时，所以能正常报出来（需要等它的 5 分钟超时）。
"""
import os, re, shutil, subprocess, sys, tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 1800          # 一个变异最多等这么多秒


def apply_edits(name, edits, dst):
    for rel, fn in edits:
        p = os.path.join(dst, rel)
        with open(p, encoding="utf-8") as f:
            s = f.read()
        s2 = fn(s)
        assert s2 != s, f"{name}: 变异没有生效 {rel}"
        with open(p, "w", encoding="utf-8") as f:
            f.write(s2)


def run_case(name, edits, expect_in_output=None, tests=None):
    """tests：只跑这几项测试（unittest 的写法，如 test_regions.Portability.test_x）；缺省跑全部。"""
    tmp = tempfile.mkdtemp(prefix="mut-")
    dst = os.path.join(tmp, "p")
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    try:
        apply_edits(name, edits, dst)
        if tests:
            cmd, cwd = [sys.executable, "-m", "unittest"] + list(tests), os.path.join(dst, "tests")
        else:
            cmd, cwd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"], dst
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"[超时] {name}：{TIMEOUT} 秒内测试没有结束（不算被发现）", flush=True)
            return False
        out = r.stdout + r.stderr
        last = [l for l in out.splitlines() if l.startswith(("FAILED", "OK", "Ran "))]
        failing = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", out, re.M)))
        caught = r.returncode != 0
        extra = "（只跑了 " + "、".join(t.split(".")[-1] for t in tests) + "）" if tests else ""
        if expect_in_output:
            extra += "；输出含预期信息" if expect_in_output in out else "；未见预期信息"
        print(f"[{'发现' if caught else '未发现'}] {name}：{' / '.join(last)}；"
              f"失败项 {[f'{c.split(chr(46))[-1]}.{t}' for t, c in failing]}{extra}", flush=True)
        return caught
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def move_apple_ai_after_apple(s):
    m = re.search(r"(  # ---------- Apple AI.*?\n)(  - id: apple_media\n)", s, re.S)
    block = m.group(1)
    s = s.replace(block, "", 1)
    i = s.index("  - id: google\n")
    return s[:i] + block + "\n" + s[i:]


def drop_service(sid):
    """从服务文件里删掉一个服务：从它的 “- id:” 行（连同紧挨着的上方注释）到下一个服务或分节注释之前。"""
    def fn(s):
        lines = s.split("\n")
        i = lines.index(f"  - id: {sid}")
        a = i
        while a > 0 and lines[a - 1].startswith("  #"):
            a -= 1
        b = i + 1
        while b < len(lines) and not lines[b].startswith(("  - id: ", "  # ")):
            b += 1
        return "\n".join(lines[:a] + lines[b:])
    return fn


def drop_loon_domain_list(s):
    return re.sub(r'    - \{url: "[^"\n]*AdvertisingLite_Domain\.list",\n(?:       .*\n)*?       source: [^\n]*\}\n', "", s, count=1)


def add_whole_ms_rule(s):
    """r8 里有过、r9 按用户决定删掉的那条：只写进 mihomo 的 DOMAIN-SUFFIX,ms → 国外默认。"""
    return s.rstrip("\n") + """

  - id: whole_ms
    group: 国外默认
    title: 变异检查用：整段 .ms
    clients: [mihomo]
    rules:
      - {suffix: ms, ev: maintainer, note: 变异检查用}
"""


def append_case_without_snapshot(s):
    return s.replace("cases:\n", "cases:\n  - {host: brand-new-host.example.org, expect: 国外默认, why: 变异检查用}\n", 1)


cases = [
    ("M1 Apple AI 服务挪到 Apple 之后（书写位置）", [("source/services/bigtech.yaml", move_apple_ai_after_apple)], "书写顺序"),
    ("M2 国内常用网站也写进 Loon / QX", [("source/services/misc.yaml", lambda s: s.replace("    clients: [mihomo, singbox, stash]\n", "", 1))], "ad.12306.cn"),
    ("M3 删掉一条 Apple AI 规则（smoot.apple.com）", [("source/services/bigtech.yaml", lambda s: re.sub(r"      - \{suffix: smoot\.apple\.com,[^\n]*\n", "", s, count=1))], "不增不减"),
    ("M4 从 Apple 组删掉 apple-dns.net", [("source/services/bigtech.yaml", lambda s: s.replace("      - {suffix: apple-dns.net, ev: dlc}\n", "", 1))], "apple-dns.net"),
    ("M5 Apple AI 默认改成日本", [("source/groups.yaml", lambda s: s.replace("{name: Apple AI,  category: AI, default: 美国", "{name: Apple AI,  category: AI, default: 日本", 1))], "Apple AI"),
    ("M6 恢复关键词规则 siri", [("source/services/bigtech.yaml", lambda s: s.replace("      - {suffix: siri.com, ev: dlc,", "      - {keyword: siri, ev: apple-ai-req, note: x}\n      - {suffix: siri.com, ev: dlc,", 1))], None),
    ("M7 sora.com 放回 OpenAI", [("source/services/ai.yaml", lambda s: s.replace("    rules:\n", "    rules:\n      - {suffix: sora.com, ev: maintainer, note: x}\n", 1))], "sora.com"),
    ("M8 Grok 组去掉 spacex.ai 登录域", [("source/services/ai.yaml", lambda s: re.sub(r"      - \{suffix: spacex\.ai,[^\n]*\n", "", s, count=1))], "accounts.spacex.ai"),
    ("M9 azure.com 放回 Microsoft", [("source/services/bigtech.yaml", lambda s: s.replace("  - id: microsoft\n", "  - id: microsoft\n", 1).replace("      - {suffix: microsoft.com,", "      - {suffix: azure.com, ev: dlc}\n      - {suffix: microsoft.com,", 1))], None),
    ("M10 byteoversea.com 放回 TikTok", [("source/services/streaming.yaml", lambda s: s.replace("      - {suffix: tiktok.com,", "      - {suffix: byteoversea.com, ev: dlc}\n      - {suffix: tiktok.com,", 1))], "byteoversea"),
    # ---- 2026-09-30 审核修复（Astra r5）----
    ("M11 mihomo 去掉局域网后缀的系统 DNS（F04）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '    policy = {",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"], DOTLESS_NAME: ["system"]}\n',
        '    policy = {DOTLESS_NAME: ["system"]}\n', 1))], "nameserver"),
    ("M12 graph.instagram.com 放回自有拦截（F05）", [("source/adblock.yaml", lambda s: re.sub(
        r"  - \{suffix: graph\.instagram\.com, ev: meta-ig-api,[^\n]*\n", "", s, count=1).replace(
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
            '    out: List[str] = []\n    for rel, text in sorted(files.items()):\n',
            '    out: List[str] = []\n    return out\n    for rel, text in sorted(files.items()):\n', 1))], None),
    ("M21 检查脚本又总是返回 0（F08）", [("tools/run_checks.sh", lambda s: s.replace("  exit 1\nfi", "  exit 0\nfi", 1))], None),
    ("M22 xAI 放回其他 AI（与 Cursor 合并的决定）", [("source/services/ai.yaml", lambda s: s.replace(
        "  - id: xai\n    group: Grok", "  - id: xai\n    group: 其他 AI", 1))], "Grok"),
    # ---- 2026-10-02 节点名称分地区 ----
    ("M23 香港不再让位", [("source/regions.yaml", lambda s: s.replace("    yields: true\n", "", 1))], "香港"),
    ("M24 🇨🇳 当成其他国家的国旗", [("source/regions.yaml", lambda s: s.replace(
        "  neutral_flags: [CN, EU, UN]", "  neutral_flags: [EU, UN]", 1))], "台湾"),
    ("M25 提示行又回到“名字里任何位置出现提示词就算”（2026-10-03 审核 F02；正则和逐步判断一起改回去）", [("generator/regions.py", lambda s: s.replace(
        '            out += "(?!" + _LABEL_PREFIX + _alt(labels) + _COLON + ")"', '            out += "(?!.*" + _alt(labels) + ")"', 1).replace(
        'self._label = re.compile(_LABEL_PREFIX + "(" + "|".join(labels) + ")" + _COLON, re.I) if labels else None',
        'self._label = re.compile(".*(" + "|".join(labels) + ")", re.I) if labels else None', 1))], "全网站解锁"),
    ("M26 英文代码不再要求前后不挨字母", [("generator/regions.py", lambda s: s.replace(
        'branches.append(r"(?<![A-Za-z])" + _trie(latin, True) + r"(?![A-Za-z])")', 'branches.append(_trie(latin, True))', 1))], "RUS"),
    ("M27 不再处理中转词", [("source/regions.yaml", lambda s: re.sub(
        r"  transit_after: \[[^\]]*\]", "  transit_after: []", s, count=1))], "中转"),
    ("M28 国旗不按成对对齐", [("generator/regions.py", lambda s: s.replace(
        'return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})" + self.run_after + f"(?:{_RI}{_RI})*"',
        'return f"(?!(?!{_RI}))" + self.before + self.run_after', 1))], "🇨🇳🇺🇸"),
    ("M29 各地区的手动组都用了日本的正则", [("generator/groups.py", lambda s: s.replace(
        'nf = NodeFilter(label=r["id"], regex=node_rx[r["id"]])', 'nf = NodeFilter(label=r["id"], regex=node_rx["jp"])', 1))], None),
    ("M30 词表里删掉“达拉斯”", [("source/regions.yaml", lambda s: s.replace("达拉斯, ", "", 1))], "达拉斯"),
    ("M31 正则里用回肯定前瞻（含等号）", [("generator/regions.py", lambda s: s.replace(
        'return "(?!)" if x is None else "(?!(?!.*" + x + "))"', 'return "(?!)" if x is None else "(?=.*" + x + ")"', 1))], None),
    ("M32 其他国家的国名不再压过地区词", [("generator/regions.py", lambda s: s.replace(
        'by_text_loose = neg_e(region_flag, other_name) + "(?:"', 'by_text_loose = neg_e(region_flag) + "(?:"', 1))], "英国"),
    ("M33 mihomo 的别名指错地区", [("generator/emit_mihomo.py", lambda s: s.replace(
        'self.name = {rx: "flt-" + labels[rx] for rx, n in count.items() if n > 1}',
        'self.name = {rx: "flt-x" for rx, n in count.items() if n > 1}', 1))], None),
    ("M34 via 不再要求单独成词（Monrovia、Bolivia 里的 via 也算）", [("generator/regions.py", lambda s: s.replace(
        "            if _ASCII_LETTERS.match(b):\n                latin_before.append(lit(b))",
        "            if False:\n                latin_before.append(lit(b))", 1))], "Monrovia"),
    ("M35 提示词里删掉“过滤掉”", [("source/regions.yaml", lambda s: s.replace(
        "工单, 工單,\n            过滤掉, 過濾掉]", "工单, 工單]", 1))], "过滤掉"),
    # ---- 2026-10-04 GPT 审核（r7）之后 ----
    ("M36 去掉 Qwen 国际版的显式规则（F01：又只剩一句说明）", [("source/services/ai.yaml", drop_service("qwen_intl"))], "chat.qwen.ai"),
    ("M37 加回 mihomo 上整段 .ms 的规则（2026-10-04 用户决定删掉、跟随上游）", [("source/services/bigtech.yaml", add_whole_ms_rule)], "example.ms"),
    ("M38 sing-box 的 DNS 不再先看产品规则（F01 的 DNS 部分）", [("generator/emit_singbox.py", lambda s: s.replace(
        "            *product_dns,\n", "", 1))], "chat.qwen.ai"),
    ("M39 Loon 又只订阅 AdvertisingLite.list（漏掉三万多条域名所在的 _Domain.list）", [
        ("source/adblock.yaml", drop_loon_domain_list)], "Domain"),
    ("M40 排除项的去向写错（js.stripe.com 的 to 写成 OpenAI）", [("source/services/ai.yaml", lambda s: s.replace(
        "{host: js.stripe.com, ev: openai-net, to: 国外默认,", "{host: js.stripe.com, ev: openai-net, to: OpenAI,", 1))], "js.stripe.com"),
    ("M41 去掉“解锁”这类词（F03：解锁说明里的地名又算落地）", [("source/regions.yaml", lambda s: s.replace(
        "  unlock: [解锁, 解鎖, unlock]", "  unlock: []", 1))], "解锁"),
    ("M42 六个地区的国名不再压过别国的城市词（F05）", [("generator/regions.py", lambda s: s.replace(
        'other_text = "(?:" + pos_e(other_name) + "|" + pos_e(other_city) + neg_e(region_name) + ")"',
        'other_text = "(?:" + pos_e(other_name) + "|" + pos_e(other_city) + ")"', 1).replace(
        'by_text_loose = neg_e(region_flag, other_name) + "(?:" + neg_e(other_city) + "|" + pos_e(region_name) + ")"',
        'by_text_loose = neg_e(region_flag, other_name) + neg_e(other_city)', 1))], "奥克兰"),
    ("M43 自动 / 故障转移 / 负载均衡用回宽的那条筛选（F04）", [("generator/groups.py", lambda s: s.replace(
        'nf_auto = NodeFilter(label=r["id"] + AUTO_SUFFIX, regex=node_rx_strict[r["id"]])',
        'nf_auto = NodeFilter(label=r["id"] + AUTO_SUFFIX, regex=node_rx[r["id"]])', 1))], None),
    ("M44 严的那条不再排除别的地区的有效词（“日本-美国 01”进两个自动组）", [("generator/regions.py", lambda s: s.replace(
        "            only = pos_e(self.eff([r.id])) + neg_e(self.eff(rivals))     # 它有有效的词，对手都没有",
        "            only = pos_e(self.eff([r.id]))", 1))], "日本-美国 01"),
    ("M45 “跳过解锁说明”的两个分支能匹配同一个字符（回溯失控）", [("generator/regions.py", lambda s: s.replace(
        'self.pre = ("(?:(?!" + self.marker + ").|"', 'self.pre = ("(?:[^解]|(?!" + self.marker + ").|"', 1))], "回溯失控",
     ["test_regions.Portability.test_long_names_do_not_blow_up"]),
    ("M46 香港对别的地区的城市词也无条件让位（F05：“香港 01 纽约时报”进美国的自动组）", [("generator/regions.py", lambda s: s.replace(
        '                text_l = (mine + by_text_loose + "(?:" + neg_e(self.eff(rivals)) + "|"\n'
        '                          + pos_e(self.eff([r.id], "core")) + neg_e(self.eff(rivals, "core")) + ")")',
        '                text_l = mine + by_text_loose + neg_e(self.eff(rivals))', 1).replace(
        "                if yielders:\n                    only +=", "                if False:\n                    only +=", 1).replace(
        "            if yielder is not None and yielder.id in eff_core and not any(r.id in eff_core for r in winners):",
        "            if False:", 1))], "纽约时报"),
    ("M47 解锁说明不认竖线和右括号（一直管到名字结尾）", [("generator/regions.py", lambda s: s.replace(
        '_CLAUSE_REST = "[^" + _PIPES + _OPEN + _CLOSE + "]*[" + _PIPES + _CLOSE + "]"', '_CLAUSE_REST = "(?!)"', 1))], "【解锁美国】日本 01"),
    ("M48 提示行的“词 + 冒号”不再要求前面没有数字和竖线", [("generator/regions.py", lambda s: s.replace(
        '_LABEL_PREFIX = "[^0-9０-９|｜丨]*"', '_LABEL_PREFIX = ".*"', 1))], "官网：abc.com"),
    ("M49 写盘前不再检查规则集与 DNS 服务器的引用", [("generator/verify.py", lambda s: s.replace(
        '    for where, rules in (("路由规则", route.get("rules", [])), ("DNS 规则", dns.get("rules", []))):',
        '    for where, rules in ():', 1))], "不存在的规则集"),
    ("M50 加了路由用例但没有重新生成真实数据快照", [("tests/cases.yaml", append_case_without_snapshot)], "重新运行"),
    ("M51 Loon 的“手动优先”兜底成员用回宽的筛选", [("generator/groups.py", lambda s: s.replace(
        "                    backup_nodes=nf_auto,", "                    backup_nodes=nf,", 1))], None),
    ("M52 把单个字的“港”当成国名一级（“关西空港 大阪 01”变成说不清）", [("source/regions.yaml", lambda s: s.replace(
        "      words: [香港]\n", "      words: [香港, 港]\n", 1).replace(
        "    patterns:\n      - '(?<!香)港(?![日韩韓美])'\n", "", 1))], "关西空港"),
    ("M53 sing-box 的 DNS 把走代理组的域名交给国内 DNS", [("generator/emit_singbox.py", lambda s: s.replace(
        'product_dns.append({**match, "query_type": ["A", "AAAA"], "server": "dns-fakeip"})',
        'product_dns.append({**match, "query_type": ["A", "AAAA"], "server": "dns-cn"})', 1))], "dns-fakeip"),
    # ---- 2026-10-05 GPT 审核（r9）之后：F01、F02，以及这一版接入的图标 ----
    ("M54 严的那条又接受“名字里只提到它一个地区”（审核 r9 F01：解锁 / 中转位置上的地名又能进自动组）", [
        ("generator/regions.py", lambda s: s.replace(
            "            text_s = mine + by_text_strict + only\n",
            '            text_s = mine + by_text_strict + "(?:" + only + "|" + neg(self.txt(others if not r.yields else rivals)) + ")"\n',
            1))], "日本中转 01"),
    ("M55 逐步判断里，不在落地位置的地名又能进自动组（审核 r9 F01 的另一套实现）", [("generator/regions.py", lambda s: s.replace(
        "        auto = list(groups) if len(groups) == 1 and not clash and not unplaced else []",
        "        auto = list(groups) if len(groups) == 1 and not clash else []", 1))], "日本中转 01"),
    ("M56 sing-box：节点服务器是局域网名字时不再指定系统 DNS（审核 r9 F02）", [("generator/emit_singbox.py", lambda s: s.replace(
        '        if isinstance(server, str) and "domain_resolver" not in n and is_lan_name(server, lan_names):',
        "        if False:", 1))], "gateway.lan"),
    ("M57 sing-box：去掉“局域网后缀先用系统 DNS 解析”的路由规则（审核 r9 F02 的另一半）", [("generator/emit_singbox.py", lambda s: s.replace(
        '        {"domain_suffix": list(p["lan"]["domain_suffix"]), "action": "resolve", "server": LOCAL_DNS_TAG},\n', "", 1))], None),
    ("M58 sing-box：不带点的主机名不算局域网里的名字", [("generator/emit_singbox.py", lambda s: s.replace(
        '    if "." not in h:\n        return True\n', "", 1))], "homeproxy"),
    ("M59 sing-box：默认解析器改成经代理的 DNS（公网域名节点的解析策略被连带改掉）", [("generator/emit_singbox.py", lambda s: s.replace(
        '        "default_domain_resolver": "dns-cn",', '        "default_domain_resolver": "dns-foreign",', 1))], "默认解析器"),
    ("M60 图标地址不做百分号编码（名字里的空格、汉字原样写进配置行）", [("generator/model.py", lambda s: s.replace(
        '        return ic["base_url"] + urllib.parse.quote(file_name + ic.get("ext", ".png"), safe="")',
        '        return ic["base_url"] + file_name + ic.get("ext", ".png")', 1))], "img-url"),
    ("M61 图标张冠李戴（没有改名登记的组都指向同一张图）", [("generator/model.py", lambda s: s.replace(
        '        return (ic.get("renamed") or {}).get(group_name) or group_name',
        '        return (ic.get("renamed") or {}).get(group_name) or "OpenAI"', 1))], "不是它自己的图"),
    ("M62 策略组找不到图标时不报错（公开配置悄悄少一个图标）", [("generator/model.py", lambda s: s.replace(
        "            if self.icons_strict:\n                raise SourceError(", "            if False:\n                raise SourceError(", 1))],
     "SourceError"),
    ("M63 地名和中转词之间只认空格（“香港-中转-01”又进了自动类的组）", [("generator/regions.py", lambda s: s.replace(
        '_JOIN = r"[\\s_·・.\\x2F—–-]*"', '_JOIN = r"\\s*"', 1))], "香港-中转-01"),
    ("M64 .gitignore 不再忽略带订阅的私密产物目录", [(".gitignore", lambda s: s.replace("dist/private/\n", "", 1))],
     "dist/private/"),
    # ---- 2026-10-05 交付前自查：同一类问题（不在落地位置的地名 / 国旗进了自动类的组）里补上的几处 ----
    ("M65 国旗又不看后面接的是什么（“🇯🇵中转 01”“IEPL 01 🇺🇸解锁”又进自动类的组；正则这一套）", [("generator/regions.py", lambda s: s.replace(
        'return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})" + self.run_after + f"(?:{_RI}{_RI})*"',
        'return f"(?!(?!{_RI}))" + self.before + f"(?<!{_RI})(?:{_RI}{_RI})*"', 1))], "🇯🇵中转 01"),
    ("M66 国旗又不看后面接的是什么（逐步判断这一套）", [("generator/regions.py", lambda s: s.replace(
        "                        or (self._after is not None and bool(self._after.match(name, j)))\n"
        "                        or (self._same_token is not None and bool(self._same_token.match(name, i))))\n",
        "                        )\n", 1))], "🇯🇵中转 01"),
    ("M67 不在落地位置的国旗又不算“提到了这个地区”（“🇯🇵中转 01”掉进其他地区，日本的手动组里选不到）", [("generator/regions.py", lambda s: s.replace(
        "            seen = pos(_alt([self.txt([r.id]), self.aflag([r.id])]))\n", "            seen = mine\n", 1).replace(
        "        nothing = neg(_alt([self.txt(ids), self.aflag(ids)]))\n", "        nothing = neg(self.txt(ids))\n", 1).replace(
        "            groups = [r.id for r in s.regions if r.id in txt or r.id in seen_flags]\n",
        "            groups = [r.id for r in s.regions if r.id in txt]\n", 1))], "🇯🇵中转 01"),
    ("M68 “其他地区”那条不排除带地区国旗的名字（“🇯🇵中转 01”同时进日本和其他地区）", [("generator/regions.py", lambda s: s.replace(
        "        nothing = neg(_alt([self.txt(ids), self.aflag(ids)]))\n", "        nothing = neg(self.txt(ids))\n", 1))], "🇯🇵中转 01"),
    ("M69 via / 经 后面、“解锁”前面又只认空格（“via-HK-01”“日本-解锁-01”又进自动类的组）", [("generator/regions.py", lambda s: s.replace(
        '_GAP = r"[\\s_-]"', '_GAP = r"\\s"', 1))], "via-HK-01"),
    ("M70 单个字的“港”在更长的词里又单独算（“经香港 01”“港日中转 01”又进香港的自动组）", [("source/regions.yaml", lambda s: s.replace(
        "      - '(?<!香)港(?![日韩韓美])'\n", "      - '港'\n", 1))], "经香港 01"),
    # ---- 2026-10-05 GPT 审核 r10（R10-F01 与对摘要的建议）----
    ("M71 mihomo：去掉节点服务器的解析策略（审核 r10 R10-F01：服务器是 gateway.lan 的节点又去问国内的公共 DNS）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '            "proxy-server-nameserver-policy": node_server_dns_policy(p["lan"]["domain_suffix"]),\n', "", 1))], "proxy-server-nameserver-policy"),
    ("M72 mihomo：节点服务器的解析策略里去掉不带点的名字（服务器是 homeproxy 的节点，两个内核的做法又不一样）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '        DOTLESS_NAME: ["system"],\n', "", 1))], "homeproxy"),
    ("M73 mihomo：清空 proxy-server-nameserver（respect-rules 和节点的解析策略都要求它不为空，内核会拒绝加载）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '            "proxy-server-nameserver": list(dns["domestic_doh"]),\n', '            "proxy-server-nameserver": [],\n', 1))], "不能为空"),
    ("M74 sing-box：直连出站指定用境外 DNS 解析（审核 r10 举的例子：规则段与 DNS 段的摘要看不到这个改动）", [("generator/emit_singbox.py", lambda s: s.replace(
        '    outbounds.append({"type": "direct", "tag": DIRECT_TAG})\n',
        '    outbounds.append({"type": "direct", "tag": DIRECT_TAG, "domain_resolver": "dns-foreign"})\n', 1))], "拨号核对用的配置变了"),
    ("M75 拨号记录的摘要又只算规则段和 DNS 段（出站改了、拨号记录过期也不提示）", [("tools/real_data.py", lambda s: s.replace(
        '        part = {"dns": base["dns"], "route": base["route"], "outbounds": outbounds}\n',
        '        part = {"dns": base["dns"], "route": base["route"]}\n', 1))], "dial_digest"),
    # ---- 2026-10-06 r12：Loon / Quantumult X 严格版、“国外的连接名字不让国内 DNS 看到”的核对、Apple Push ----
    ("M76 Loon 严格版：GEOIP,CN 又没有 no-resolve（没被接住的域名又要在本机解析）", [("generator/emit_loon.py", lambda s: s.replace(
        '        L.append("GEOIP,CN,国内直连,no-resolve")\n', '        L.append("GEOIP,CN,国内直连")\n', 1))], "no-resolve"),
    ("M77 Loon 严格版：没有订阅国内域名清单（国内网站全部走代理）", [("generator/emit_loon.py", lambda s: s.replace(
        '        for x in m.strict["domestic_lists"]["loon"]:\n', '        for x in []:\n', 1))], "国内直连"),
    ("M78 Loon 严格版：国内域名清单排到广告集合前面（清单里的域名下的广告主机拦不到）", [("generator/emit_loon.py", lambda s: s.replace(
        """            L.append(f"{url}, policy=国内直连, tag={x['tag']}, enabled=true")\n""",
        """            L.insert(L.index("[Remote Rule]") + 1, f"{url}, policy=国内直连, tag={x['tag']}, enabled=true")\n""", 1))], "广告"),
    ("M79 Loon 严格版：订阅的是混着关键词和 IP 规则的 ChinaMax.list，不是只含域名的那一份", [("source/strict.yaml", lambda s: s.replace(
        "rule/Loon/ChinaMax/ChinaMax_Domain.list", "rule/Loon/ChinaMax/ChinaMax.list", 1))], "ChinaMax"),
    ("M80 Quantumult X 严格版：没有域名兜底", [("generator/emit_qx.py", lambda s: s.replace(
        """        L.append(f"{strict_mod.own_url(m, fb['own'])}, tag={fb['tag']}, force-policy=国外默认, update-interval=86400, "\n"""
        """                 "opt-parser=false, enabled=true")\n""", "", 1))], "兜底"),
    ("M81 Quantumult X 严格版：域名兜底不是最后一条（排到了国内域名清单前面，国内网站全部走代理）", [("generator/emit_qx.py", lambda s: s.replace(
        """        L.append(f"{strict_mod.own_url(m, fb['own'])}, tag={fb['tag']}, force-policy=国外默认, update-interval=86400, "\n"""
        """                 "opt-parser=false, enabled=true")\n""",
        """        L.insert(len(L) - 3, f"{strict_mod.own_url(m, fb['own'])}, tag={fb['tag']}, force-policy=国外默认, """
        """update-interval=86400, opt-parser=false, enabled=true")\n""", 1))], "兜底"),
    ("M82 Quantumult X 严格版：域名兜底交给了“国内直连”", [("generator/emit_qx.py", lambda s: s.replace(
        "tag={fb['tag']}, force-policy=国外默认, update-interval=86400", "tag={fb['tag']}, force-policy=国内直连, update-interval=86400", 1))], "国外默认"),
    ("M83 域名兜底文件里的关键词不是“.”（只接住含 com 的域名）", [("generator/strict.py", lambda s: s.replace(
        'FALLBACK_KEYWORD = "."', 'FALLBACK_KEYWORD = "com"', 1))], "HOST-KEYWORD"),
    ("M84 Loon：“要真实地址的名单”不固定直连（time.apple.com 又跟着 Apple 组；2026-10-07 起标准版、严格版都有这一段）", [("generator/emit_loon.py", lambda s: s.replace(
        "    emit(plan.real_ip_direct, by_service=False)\n", "", 1))], "DIRECT"),
    ("M85 Quantumult X：“要真实地址的名单”不固定直连（同上）", [("generator/emit_qx.py", lambda s: s.replace(
        "    emit(plan.real_ip_direct, by_service=False)\n", "", 1))], "DIRECT"),
    ("M86 自有清单不去掉已被本地规则覆盖的条目（qwen.ai 又出现在国内清单里）", [("generator/strict.py", lambda s: s.replace(
        "    kept_s = [x for x in suffix if not covered(x, False)]\n", "    kept_s = list(suffix)\n", 1))], "qwen.ai"),
    ("M87 标准版被牵连：Loon 标准版的 GEOIP,CN 也带上了 no-resolve（标准版不再靠解析认国内网站）", [("generator/emit_loon.py", lambda s: s.replace(
        '        L.append("GEOIP,CN,国内直连")\n', '        L.append("GEOIP,CN,国内直连,no-resolve")\n', 1))], "unknown-cn.example"),
    ("M88 标准版被牵连：Quantumult X 标准版也带上了国内清单和域名兜底", [("generator/emit_qx.py", lambda s: s.replace(
        '    if strict:\n        L.append("# 6 国内域名清单（严格版）：排在广告集合之后；本地的产品规则仍然优先于它")\n',
        '    if True:\n        L.append("# 6 国内域名清单（严格版）：排在广告集合之后；本地的产品规则仍然优先于它")\n', 1))], "标准版"),
    ("M89 国内域名清单的数据文件被手改：加了一条已被别的后缀覆盖的条目", [("source/data/cn-domains.txt", lambda s: s.replace(
        "\n.baidu.com\n", "\n.baidu.com\n.tieba.baidu.com\n", 1))], "覆盖"),
    ("M90 国内域名清单的数据文件里没有整段 .cn", [("source/data/cn-domains.txt", lambda s: s.replace("\n.cn\n", "\n", 1))], "cn"),
    ("M91 mihomo：默认的 DNS 换成国内的（没被域名规则接住的域名改问国内 DNS；官方内核的记录过期）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '            "nameserver": foreign,\n', '            "nameserver": list(dns["domestic_doh"]),\n', 1))], "重新运行"),
    ("M92 sing-box：路由里的 resolve 动作改用国内 DNS（没被域名规则接住的域名改问国内 DNS）", [("generator/emit_singbox.py", lambda s: s.replace(
        '    rules.append({"action": "resolve", "server": "dns-foreign"})', '    rules.append({"action": "resolve", "server": "dns-cn"})', 1))], "重新运行"),
    ("M93 “境外 DNS 不应答”那一遍不再包含没被接住的域名（那一遍等于什么也没证明）", [("tools/real_data.py", lambda s: s.replace(
        'SILENT_KINDS = ("proxied", "unlisted")', 'SILENT_KINDS = ("proxied",)', 1))], "重新运行"),
    # M94 r12–r14 是“把 sing-box 那一类已知的不一致从清单里拿掉”。2026-10-07 那一类处理掉了（待决事项 15、14），清单是空的，
    # 改成反方向：登记一类已经没有主机的不一致（处理掉的类别忘了从登记里删）
    ("M94 逐条扫描：登记了一类已经没有主机的不一致（处理掉的类别没从清单里删）", [("tests/cases.yaml", lambda s: s.replace(
        "  singbox: []\n", "  singbox:\n    - {kind: real_ip, why: \"已经处理掉的一类，待决事项 15\"}\n", 1))], "已知类别"),
    ("M95 去掉 Apple Push 的规则（推送又跟着 Apple 组）", [("source/services/bigtech.yaml", drop_service("apple_push"))], "Apple Push"),
    ("M96 Apple Push 的默认出口改成国外默认（需求是默认直连，需要时手动切）", [("source/groups.yaml", lambda s: s.replace(
        "  - {name: Apple Push,     category: 大厂, default: DIRECT, options: [国外默认, 香港,",
        "  - {name: Apple Push,     category: 大厂, default: 国外默认, options: [DIRECT, 香港,", 1))], "Apple Push"),
    ("M97 图标登记里漏了 Apple Push（组加了，图没有登记）", [("source/icons.yaml", lambda s: s.replace(
        '"Apple Music／TV", "Apple Push", "Bahamut"', '"Apple Music／TV", "Bahamut"', 1))], "没有图标"),
    ("M98 上游的 Loon 广告集合里有一条 IP 规则不带 no-resolve（改的是快照里的记录：Loon 严格版会为它在本机解析）",
     [("tests/data/real_sets.json", lambda s: s.replace('"ip_resolving": 0', '"ip_resolving": 1', 1))], "no-resolve"),
    ("M99 sing-box：境外 DNS（dns-foreign）不再经“国外默认”发出（从本机直接连境外 DoH）", [("generator/emit_singbox.py", lambda s: s.replace(
        '"server": host_of(dns["foreign_doh"][0]), "detour": "国外默认"}', '"server": host_of(dns["foreign_doh"][0])}', 1))],
     "经国外默认发出"),
    ("M100 核对工具又只读 A 记录、按“没有 A 记录”判空应答（AAAA 拿到地址、HTTPS 拿到记录也记成 empty）", [("tools/check_real_routes.py", lambda s: s.replace(
        "            elif rtype == 28:\n                ips.append(socket.inet_ntop(socket.AF_INET6, data[i:i + 16]))\n", "", 1).replace(
        "    if rcode == 0 and count == 0:\n", "    if rcode == 0 and not ips:\n", 1))], "不是空应答"),
    # 2026-10-07（r14，GPT 审核 r13）
    ("M101 核对工具又只在名字的第一个字节看压缩指针（“标签 + 指针”的合法名字读错，CNAME + A 的应答记成读不懂）",
     [("tools/check_real_routes.py", lambda s: s.replace(
         "            i = _skip_name(data, i)\n",
         "            if data[i] & 0xC0:\n                i += 2\n            else:\n                while data[i]:\n"
         "                    i += data[i] + 1\n                i += 1\n", 1))], "CNAME + A 的正常应答要读出地址和记录数"),
    ("M102 mihomo：nameserver-policy 里又没有“走代理组的产品域名 → 境外 DNS”那一层（r13 的样子：UDP、WireGuard 时这类名字交给国内 DNS）",
     [("generator/emit_mihomo.py", lambda s: s.replace(
         "    for pattern, to_foreign in product_dns_policy(m, plan):\n        if pattern in policy:\n"
         "            raise ValueError(f\"nameserver-policy 里 {pattern} 写了两次：要真实地址的名单和产品规则重复了\")\n"
         "        policy[pattern] = foreign if to_foreign else domestic_layer\n",
         "", 1))], "默认走代理"),
    ("M103 mihomo：产品域名那一层把默认直连的组（Apple 那几个）也交给境外 DNS（直连时会拿境外 DNS 的结果）",
     [("generator/emit_mihomo.py", lambda s: s.replace(
         "    is_direct = {id(r): r.target in direct for r in rules}\n",
         '    is_direct = {id(r): r.target == "国内直连" for r in rules}\n', 1))], "却交给境外 DNS"),
    ("M104 核对工具查 nameserver-policy 时按“第一条命中”而不是 mihomo 的域名树（更宽的写法挡住更具体的）",
     [("tools/dns_route_consistency.py", lambda s: s.replace(
         "    def _search(self, node: dict, parts: List[str]):\n        if not parts:\n",
         '    def _search(self, node: dict, parts: List[str]):\n        if parts and node.get("") is not None:\n'
         '            return node[""].get(None)\n        if not parts:\n', 1))], "b.a.com"),
    # ---- 2026-10-07：用户把待决事项一次定下来以后（第 5、7、8、14、15、19 项；docs/06）----
    ("M105 sing-box：“要真实地址的名单”不固定直连（time.windows.com 又跟着 Microsoft 组；待决事项 15）",
     [("generator/emit_singbox.py", lambda s: s.replace(
         "    rules += _chunk(plan.real_ip_direct, target_map)    # 要真实地址的名单：DNS 规则交给 dns-cn，连接也固定直连（待决事项第 15 项）\n",
         "", 1))], "time.windows.com"),
    ("M106 mihomo：“要真实地址的名单”不固定直连（待决事项 15）", [("generator/emit_mihomo.py", lambda s: s.replace(
        "    emit(plan.real_ip_direct, by_service=False)\n", "", 1))], "time.windows.com"),
    ("M107 mihomo：要真实地址的名单路由直连了，DNS 却没写明交给国内（又落到默认的境外 DNS；待决事项 15）",
     [("generator/emit_mihomo.py", lambda s: s.replace(
         "    for r in plan.real_ip_direct:\n        policy[(\"+.\" + r.value) if r.kind == \"suffix\" else r.value] = domestic_layer\n",
         "", 1))], "localhost.ptlogin2.qq.com"),
    ("M108 mihomo：不带点的名字又交给国内的公共 DNS（nameserver-policy 里没有 *；待决事项 14）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '    policy = {",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"], DOTLESS_NAME: ["system"]}\n',
        '    policy = {",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"]}\n', 1))], "'*'"),
    ("M109 mihomo：private 集合又和 cn 合在一起交给国内 DNS（待决事项 14）", [("generator/emit_mihomo.py", lambda s: s.replace(
        '    policy["geosite:private"] = ["system"]\n    policy["geosite:cn"] = list(dns["domestic_doh"])\n',
        '    policy["geosite:cn,private"] = list(dns["domestic_doh"])\n', 1))], "geosite:private"),
    ("M110 Quantumult X 严格版没有订阅上游大清单的副本（待决事项 19）", [("source/strict.yaml", lambda s: s.replace(
        "      - {own: quantumultx/rules/cn-domains-max.list, tag: 国内域名-ChinaMax}\n", "", 1))], "cn-domains-max"),
    ("M111 上游大清单副本的数据文件被手改（少了一条，文件头的条数对不上）", [("source/data/cn-domains-max.txt", lambda s: s.replace(
        "\n.0.zone\n", "\n", 1))], "111008"),
    ("M112 去掉友盟的直连规则（Loon / QX 上友盟又被上游的关键词 umeng 整个拦掉；待决事项 7）",
     [("source/services/misc.yaml", drop_service("umeng"))], "msg.umeng.com"),
    ("M113 友盟上游标了 @ads 的子域漏了一条（aaid.umeng.com 不再被拦；待决事项 7）", [("source/adblock.yaml", lambda s: s.replace(
        "  - {suffix: aaid.umeng.com, ev: dlc, note: 友盟统计 / 跟踪（上游标为 @ads）}\n", "", 1))], "aaid.umeng.com"),
    ("M114 Bilibili 港澳台的默认出口又改回台湾（待决事项 5）", [("source/groups.yaml", lambda s: s.replace(
        "default: DIRECT, options: [台湾, 香港, 国外默认,", "default: 台湾, options: [DIRECT, 香港, 国外默认,", 1))], "Bilibili 港澳台"),
    ("M115 Apple AI 又整段收了 ls.apple.com（Apple 地图 / 定位又走美国；待决事项 8）", [("source/services/bigtech.yaml", lambda s: s.replace(
        "      - {suffix: mask-h2.icloud.com,", "      - {suffix: ls.apple.com, ev: apple-ai-req, note: x}\n      - {suffix: mask-h2.icloud.com,", 1))],
     "gsp-ssl.ls.apple.com"),
    ("M116 版本对比报告里只换了先后的条目又不写改了什么（只剩一个空的“改动 X：”）", [("tools/compare_versions.py", lambda s: s.replace(
        "    if not gone and not come and ta != tb:\n", "    if False:\n", 1))], "顺序改了"),
    ("M117 docs/04 里 Quantumult X 大清单副本那一行又按自有清单的数据算条数", [("generator/audit.py", lambda s: s.replace(
        "strict_mod.max_entries(m, plan) if is_max else ", "", 1))], "cn-domains-max"),
    ("M118 “国内直连”又能切到国外默认（待决事项 17：固定直连）", [("source/groups.yaml", lambda s: s.replace(
        "  - {name: 国内直连, category: 基础, default: DIRECT, options: [],", "  - {name: 国内直连, category: 基础, default: DIRECT, options: [国外默认],", 1))],
     "国内直连"),
    ("M119 阿里妈妈又漏了上游写成关键词的 afpapi.alimama.com（GPT 审核 r14 的 R14-F02）", [("source/adblock.yaml", lambda s: s.replace(
        "  - {suffix: afpapi.alimama.com, ev: bm7-snap,", "  # - {suffix: afpapi.alimama.com, ev: bm7-snap,", 1))], "afpapi.alimama.com"),
    ("M120 核对工具的域名树又先去掉两头的空白、不检查写法（比内核宽；GPT 审核 r14 的建议 S02）", [("tools/dns_route_consistency.py", lambda s: s.replace(
        "            parts = valid_and_split(pattern)\n", "            parts = pattern.strip().lower().split(\".\")\n", 1))], "not raised"),
    ("M121 大清单副本的文件头又不写本项目改了什么、哪天改的（GPL-2.0 第 2 条 a 款；GPT 审核 r14 的建议 S03）", [("generator/strict.py", lambda s: s.replace(
        "        f\"GPL-2.0 原文：{GPL2_URL}\"]\n", "        \"\"]\n", 1))], "gpl-2.0.html"),
    ("M122 出站核对认不回节点收到的地址（SOCKS 走 UDP 时节点收到的 IP 全记成没收到；GPT 审核 r14 的建议 S01）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        h = addr if kind == \"domain\" else answers.host_of.get(addr) if kind == \"ip\" else None\n",
        "        h = addr if kind == \"domain\" else None\n", 1))], "b.example"),
    ("M123 SOCKS5 接收端又不看客户端提供的方法，一律选“不要认证”（GPT 审核 r15 的 R15-F01）", [("tools/check_real_routes.py", lambda s: s.replace(
        "            if 0 not in methods:\n", "            if False:\n", 1))], "test_refuses_what_rfc1928_says_to_refuse"),
    ("M124 SOCKS5 接收端又收分了片的 UDP 包（FRAG 不是 0 也记成节点收到了；R15-F01）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        if data[2] != 0:\n", "        if False:\n", 1))], "test_refuses_what_rfc1928_says_to_refuse"),
    ("M125 控制连接断了以后 UDP 关联还在，接着收包（R15-F01）", [("tools/check_real_routes.py", lambda s: s.replace(
        "                        if not c.recv(4096):\n                            return", "                        if not c.recv(4096):\n                            pass", 1))],
     "test_refuses_what_rfc1928_says_to_refuse"),
    ("M126 认主机时又不分 TCP / UDP 的记录（GPT 审核 r15 的建议）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        if t != transport:\n            continue\n", "", 1))], "test_records_names_and_addresses"),
    ("M127 大清单副本的内容变了，“最后一次改动”的日期和校验值没跟着改（GPT 审核 r15 的建议）", [("generator/strict.py", lambda s: s.replace(
        "这个文件里共 {len(suffix) + len(full)} 条。", "这个文件里一共 {len(suffix) + len(full)} 条。", 1))], "MAX_LIST_CONTENT_SHA256"),
    ("M128 读内核日志又不关文件（r15 测试日志里那条 ResourceWarning）", [("tools/check_real_routes.py", lambda s: s.replace(
        "    with open(logp, encoding=\"utf-8\", errors=\"replace\") as f:\n        text = f.read()\n",
        "    text = open(logp, encoding=\"utf-8\", errors=\"replace\").read()\n", 1))], "ResourceWarning"),
    # ---- Stash（2026-10-13，r16）----
    ("M129 Stash 严格版的 GEOIP,CN 又不带 no-resolve（没被域名规则接住的域名又要在本机解析）", [("generator/emit_stash.py", lambda s: s.replace(
        '        add("GEOIP,CN,国内直连,no-resolve")\n', '        add("GEOIP,CN,国内直连")\n', 1))], "no-resolve"),
    ("M130 Stash 的占位节点连得上（端口改成 Stash 自己的代理端口）", [("generator/emit_stash.py", lambda s: s.replace(
        "PLACEHOLDER_PORT = 1\n", "PLACEHOLDER_PORT = 7890\n", 1))], "test_one_placeholder_per_region_that_cannot_connect"),
    ("M131 Stash 没有占位节点（某个地区一个节点都没有时组是空的，Stash 当作直连）", [("generator/emit_stash.py", lambda s: s.replace(
        "             for name in placeholders(m).values()]\n", "             for name in []]\n", 1))], "占位节点"),
    ("M132 Stash 严格版的国内域名清单排到 GEOSITE,geolocation-!cn 前面（境外集合里的域名也被它接走）", [("generator/emit_stash.py", lambda s: s.replace(
        '    add("GEOSITE,geolocation-!cn,国外默认")\n    if strict:\n        for x in m.strict["domestic_lists"]["stash"]:\n'
        '            add(f"RULE-SET,{x[\'tag\']},国内直连")\n',
        '    if strict:\n        for x in m.strict["domestic_lists"]["stash"]:\n            add(f"RULE-SET,{x[\'tag\']},国内直连")\n'
        '    add("GEOSITE,geolocation-!cn,国外默认")\n', 1))], "geolocation-!cn 之后"),
    ("M133 Stash 的 nameserver 换成境外 DNS（直连的连接拿境外 DNS 的结果，国内网站可能变慢）", [("generator/emit_stash.py", lambda s: s.replace(
        '        "nameserver": list(dns["domestic_doh"]),\n', '        "nameserver": list(dns["foreign_doh"]),\n', 1))], "test_dns_block"),
    ("M134 Stash 的局域网后缀不交给系统 DNS", [("generator/emit_stash.py", lambda s: s.replace(
        '        "nameserver-policy": {"+." + s: "system" for s in lan},\n', '        "nameserver-policy": {"+.lan": "system"},\n', 1))],
     "test_stash_uses_system_dns_for_lan_suffixes"),
    ("M135 国内常用网站的补充规则又不写进 Stash（和 mihomo 的规则不再逐条相同）", [("source/services/misc.yaml", lambda s: s.replace(
        "    clients: [mihomo, singbox, stash]\n", "    clients: [mihomo, singbox]\n", 1))], "test_standard_rules_are_the_mihomo_rules"),
    ("M136 模拟器不认 Stash 的 RULE-SET（严格版的国内域名清单在测试里等于没有）", [("tests/emulate.py", lambda s: s.replace(
        '            if c.host and fx.remote_host_hit(rp["url"], c.host):\n                return target\n            continue\n',
        '            continue\n', 1))], "only-in-chinamax-sample"),
    ("M137 Stash 的 PayPal 固定节点没带占位节点（那个节点被删掉以后组是空的）", [("generator/emit_stash.py", lambda s: s.replace(
        '        return "^(?:" + lit(nf.pinned) + "|" + lit(ph) + ")$"\n', '        return nf.final_regex()\n', 1))],
     "test_pinned_paypal_node_keeps_its_placeholder"),
    ("M138 生成 Stash 配置时不核对占位节点", [("generator/emit_stash.py", lambda s: s.replace(
        "    check_placeholders(m, groups)\n", "", 1))], "test_build_refuses_a_broken_stash_config"),
    ("M139 结构检查不看筛选能不能选中占位节点", [("generator/verify.py", lambda s: s.replace(
        "            if len(hit) != 1:\n", "            if False:\n", 1))], "test_missing_placeholder"),
    ("M140 Stash 的 DNS 段里 +. 开头的写法又不加引号（和文档的例子不一样）", [("generator/emit_stash.py", lambda s: s.replace(
        '    style = "\'" if data.startswith(("+", "*")) else None\n', "    style = None\n", 1))], "test_wildcard_keys_are_quoted_like_the_docs"),
    ("M141 模拟器不记 Stash 为了判断 IP 规则在本机解析过（严格版“不在本机解析”的检查失灵）", [("tests/emulate.py", lambda s: s.replace(
        '                if trace is not None:\n                    trace["resolved"] = True\n', "", 1))], "标准版里没被域名规则接住的域名应该要先解析"),
    # ---- GPT 审核 r16（2026-10-14，r17）----
    ("M142 Stash 的筛选又不排除内置策略的名字（“其他地区”又会收进 DIRECT；R16-F01）", [("generator/emit_stash.py", lambda s: s.replace(
        "    return exclude_builtins(nf.final_regex())\n", "    return nf.final_regex()\n", 1))], "内置策略"),
    ("M143 生成 Stash 配置时不核对筛选会不会选中内置策略（R16-F01）", [("generator/emit_stash.py", lambda s: s.replace(
        "        if builtin:\n            raise ValueError(", "        if False:\n            raise ValueError(", 1))],
     "test_build_refuses_a_filter_that_picks_a_builtin_policy"),
    ("M144 结构检查不看筛选会不会选中内置策略（R16-F01）", [("generator/verify.py", lambda s: s.replace(
        "            if builtin:\n                problems.append(", "            if False:\n                problems.append(", 1))],
     "test_filter_that_picks_a_builtin_policy"),
    ("M145 Stash 筛选排除内置策略排得太宽（名字以 DIRECT 等开头的节点也不选了）", [("generator/emit_stash.py", lambda s: s.replace(
        '"|".join(BUILTIN_POLICIES) + ")$)"', '"|".join(BUILTIN_POLICIES) + "))"', 1))], "test_prefix_changes_nothing_for_node_names"),
    ("M146 SOCKS5 接收端又不记地址类型不认识的请求（R16-F02）", [("tools/check_real_routes.py", lambda s: s.replace(
        '                self._bad("请求里的地址类型不认识", str(atyp))\n', "", 1))], "test_records_every_request_it_refuses"),
    ("M147 SOCKS5 接收端又不记只发了一部分就断开的握手、请求（R16-F02）", [("tools/check_real_routes.py", lambda s: s.replace(
        "            if got[0]:\n", "            if False:\n", 1))], "test_records_every_request_it_refuses"),
    ("M148 SOCKS5 接收端又不记不支持的命令（R16-F02）", [("tools/check_real_routes.py", lambda s: s.replace(
        '                self._bad("不支持的命令（这里只认 CONNECT、UDP ASSOCIATE）", str(cmd))\n', "", 1))],
     "test_records_every_request_it_refuses"),
    ("M149 SOCKS5 接收端把一个字节都没发的连接也记成不合规（正常的核对也会报错）", [("tools/check_real_routes.py", lambda s: s.replace(
        "            if got[0]:\n", "            if True:\n", 1))], "test_records_every_request_it_refuses"),
    ("M150 DNS 替身又把读不懂的查询直接丢掉（R16-F02 之后自查的同类问题）", [("tools/check_real_routes.py", lambda s: s.replace(
        "                self.unparsed.append(data[:64].hex())\n", "                pass\n", 1))], "test_dns_stub_keeps_queries_it_cannot_read"),
    ("M151 关 DNS 替身时收到过读不懂的查询也不报错", [("tools/check_real_routes.py", lambda s: s.replace(
        "    if bad:\n        raise RuntimeError(\"DNS 替身", "    if False:\n        raise RuntimeError(\"DNS 替身", 1))],
     "test_dns_stub_keeps_queries_it_cannot_read"),
    ("M152 有一处出站核对直接关 DNS 替身（不经 close_stubs，读不懂的查询不报错）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        close_stubs([stub])\n", "        stub.close()\n", 1))], "test_every_dns_stub_is_closed_through_close_stubs"),
    ("M153 出站核对的报错分支读内核日志又不关文件（和 r15 那条 ResourceWarning 同一类）", [("tools/check_real_routes.py", lambda s: s.replace(
        '    with open(logp, encoding="utf-8", errors="replace") as f:\n        return f.read()[-n:]\n',
        '    return open(logp, encoding="utf-8", errors="replace").read()[-n:]\n', 1))], "test_code_closes_the_files_it_opens"),
    ("M154 版本对比报告又认不出 Stash 带前缀的筛选（写成“未知的正则”）", [("tools/compare_versions.py", lambda s: s.replace(
        '            ("Stash宽 ", _stash_variant(new_loose)), ("Stash严 ", _stash_variant(new_strict)),\n', "", 1))],
     "test_stash_filters_get_their_own_label"),
    # 2026-10-15（r18，GPT 审核 r17 的 R17-F01：停下时没等接收线程处理完就汇总）
    ("M155 DNS 替身停下时又不等接收线程（只关 socket 就返回，r17 的样子）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        self._dns_stop_event.set()\n        if self.is_alive():\n            self.join(timeout)\n        if self.is_alive():\n            return False\n",
        "        self._dns_stop_event.set()\n", 1))], "test_close_stubs_waits_for_a_query_already_received"),
    ("M156 close_stubs 不管替身有没有停下（接收线程没结束也当没问题）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        if not st.stop(timeout):\n", "        if not st.stop(timeout) and False:\n", 1))],
     "test_close_stubs_reports_a_receiver_that_does_not_finish"),
    ("M157 有一处核对（sing-box 拨号）在替身停下以前就汇总", [("tools/check_real_routes.py", lambda s: s.replace(
        "        close_stubs(stubs.values())                    # 内核停了：替身把已经收到的处理完、线程结束，再汇总（R17-F01）\n        out = {}\n",
        "        out = {}\n", 1))], "test_every_dns_stub_is_closed_through_close_stubs"),
    ("M158 测试节点停下时又不等处理连接的线程，一律说停好了", [("tools/check_real_routes.py", lambda s: s.replace(
        "        for t in threads:\n            t.join(max(0.0, end - time.monotonic()))\n        return not any(t.is_alive() for t in threads)\n",
        "        return True\n", 1))], "test_recorder_stop_waits_for_a_request_already_received"),
    ("M159 有一处出站核对（mihomo）在测试节点停下以前就汇总", [("tools/check_real_routes.py", lambda s: s.replace(
        "        if recorder and not recorder.stop():\n"
        "            raise RuntimeError(f\"测试节点没有停下（{transport}），收到的请求可能没有记全，这一项的结果不记\")\n", "", 1))],
     "test_every_dns_stub_is_closed_through_close_stubs"),
    ("M160 测试节点又把超时记成“不完整”（GPT 审核 r17 的建议：两种分开记）", [("tools/check_real_routes.py", lambda s: s.replace(
        ", timed_out=True) from None\n", ") from None\n", 1))], "test_recorder_tells_a_timeout_from_a_cut_off"),
    ("M161 测试节点停下时丢掉 UDP 口里已经到了、还没读的包", [("tools/check_real_routes.py", lambda s: s.replace(
        "                if self._closing.is_set():\n                    # stop()", "                if self._closing.is_set():\n                    return\n                    # stop()", 1))],
     "test_recorder_stop_keeps_udp_packets_already_received"),
    ("M162 DNS 替身一停下就不收了（socket 里已经排着的查询不处理）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        self.sock.settimeout(STUB_POLL)\n        while True:\n", "        self.sock.settimeout(STUB_POLL)\n        while not self._dns_stop_event.is_set():\n", 1))],
     "test_close_stubs_waits_for_a_query_already_received"),
    # 2026-10-15（r19 送审稿，GPT 审核 r18 的 R18-F01–F03）
    ("M163 DNS 替身的停止标记又叫 _stop（盖住 Python 3.12 及以前 Thread 自己的 _stop 方法）", [("tools/check_real_routes.py",
        lambda s: s.replace("self._dns_stop_event", "self._stop"))], "test_threads_do_not_shadow_thread_internals"),
    ("M164 测试节点停下时又不看控制连接（断开以后才到的 UDP 包也记下）", [("tools/check_real_routes.py", lambda s: s.replace(
        "                    while not self._control_closed(c):\n", "                    while True:\n", 1))],
     "test_recorder_stop_ignores_udp_packets_after_the_control_connection_closed"),
    ("M165 sing-box 的查询和连接又放在同一遍里", [("tools/check_real_routes.py", lambda s: s.replace(
        "    if targets and dns_cases:\n        _, dns_got = _singbox_run(", "    if False:\n        _, dns_got = _singbox_run(", 1))],
     "test_singbox_probe_runs_queries_and_connections_separately"),
    ("M166 不应答的那一遍以外，拿到 fake-ip 的查询也只记收到它的替身", [("tools/check_real_routes.py", lambda s: s.replace(
        "    if hold and asked:\n        return \"+\".join(asked)\n", "    if asked:\n        return \"+\".join(asked)\n", 1))],
     "test_dns_attribution_uses_name_and_type_after_stubs_stop"),
    # 2026-10-17（GPT 审核 r19 送审稿的 R19-F01、R19-S01）
    ("M167 停下时清 UDP 队列又只在开头看一次控制连接（清到一半断开以后的包也记下）", [("tools/check_real_routes.py", lambda s: s.replace(
        "                    while not self._control_closed(c):\n                        if not select.select([u], [], [], 0)[0]:\n",
        "                    if self._control_closed(c):\n                        return\n                    while True:\n"
        "                        if not select.select([u], [], [], 0)[0]:\n", 1))],
     "test_recorder_stop_ignores_udp_packets_after_the_control_connection_closes_mid_drain"),
    ("M168 查询用例的去向只看名字、不看类型（审核报告里那一处改法）", [("tools/check_real_routes.py", lambda s: s.replace(
        "        asked = [k for k, v in stubs.items() if key in v.seen]\n",
        "        asked = [k for k, v in stubs.items() if any(q == key[0] for q, qt in v.seen)]\n", 1))],
     "test_dns_attribution_uses_the_real_stubs_after_they_stop"),
    ("M169 替身没停下也认查询的去向", [("tools/check_real_routes.py", lambda s: s.replace(
        "    if not all(st.stopped for st in stubs.values()):\n", "    if False:\n", 1))],
     "test_dns_attribution_uses_the_real_stubs_after_they_stop"),
    ("M170 sing-box 在替身停下以前就认查询的去向", [("tools/check_real_routes.py", lambda s: s.replace(
        "        close_stubs(stubs.values())                    # 内核停了：替身把已经收到的处理完、线程结束，再汇总（R17-F01）\n        dns_got = _attribute_dns(dns_cases, answers, stubs, fake_net, hold)\n",
        "        dns_got = _attribute_dns(dns_cases, answers, stubs, fake_net, hold)\n        close_stubs(stubs.values())                    # 内核停了：替身把已经收到的处理完、线程结束，再汇总（R17-F01）\n", 1))],
     "test_every_dns_stub_is_closed_through_close_stubs"),
]


def main(argv):
    known = [c[0].split()[0] for c in cases]
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    unknown = [x for x in argv if x != "--check-edits" and x not in known]
    if unknown:
        # 认不出的参数不能当成“没有参数”：那样会把全部变异跑一遍（一小时左右）
        print(f"认不出的参数：{'、'.join(unknown)}。能用的是 --check-edits、--help，或者变异的编号（{known[0]} … {known[-1]}）。", file=sys.stderr)
        return 2
    if "--check-edits" in argv:
        tmp = tempfile.mkdtemp(prefix="mut-")
        try:
            bad = 0
            for c in cases:
                dst = os.path.join(tmp, c[0].split()[0])
                shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "dist", "docs", "tests" if not any(
                    rel.startswith("tests/") for rel, _ in c[1]) else "__none__"))
                try:
                    apply_edits(c[0], c[1], dst)
                except (AssertionError, ValueError, AttributeError) as e:
                    bad += 1
                    print(f"[套不上] {c[0]}：{e}")
                shutil.rmtree(dst, ignore_errors=True)
            print(f"{len(cases) - bad}/{len(cases)} 个变异的改动能套到当前代码上")
            return 1 if bad else 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    only = [x for x in argv if not x.startswith("--")]
    res = [run_case(*c) for c in cases if not only or c[0].split()[0] in only]
    print(f"合计 {sum(res)}/{len(res)} 被发现", flush=True)
    return 0 if res and all(res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

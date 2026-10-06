#!/usr/bin/env python3
"""变异检查：在项目副本里逐一注入与各轮改动相关的错误，确认测试能发现。

每个变异在临时目录的独立副本里进行，不改动项目本身。副本不含 dist/，这样“产物与统一源一致”那项检查不会
替语义测试把错误兜住（副本里那一项会显示为 skipped）。
用法：python3 tools/check_mutations.py [M1 M2 …]      不带参数时跑全部；每个变异一两分钟（共 100 个，可以分两批同时跑）
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
        s = open(p, encoding="utf-8").read()
        s2 = fn(s)
        assert s2 != s, f"{name}: 变异没有生效 {rel}"
        open(p, "w", encoding="utf-8").write(s2)


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
    ("M2 国内常用网站也写进 Loon / QX", [("source/services/misc.yaml", lambda s: s.replace("    clients: [mihomo, singbox]\n", "", 1))], "ad.12306.cn"),
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
        '                ",".join("+." + s for s in p["lan"]["domain_suffix"]): ["system"],\n', "", 1))], "nameserver"),
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
    ("M84 Loon 严格版：“要真实地址的名单”不固定直连（time.apple.com 又跟着 Apple 组）", [("generator/emit_loon.py", lambda s: s.replace(
        "        emit(plan.real_ip_direct, by_service=False)\n", "", 1))], "DIRECT"),
    ("M85 Quantumult X 严格版：“要真实地址的名单”不固定直连", [("generator/emit_qx.py", lambda s: s.replace(
        "        emit(plan.real_ip_direct, by_service=False)\n", "", 1))], "DIRECT"),
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
        '            "nameserver": list(dns["foreign_doh"]),\n', '            "nameserver": list(dns["domestic_doh"]),\n', 1))], "重新运行"),
    ("M92 sing-box：路由里的 resolve 动作改用国内 DNS（没被域名规则接住的域名改问国内 DNS）", [("generator/emit_singbox.py", lambda s: s.replace(
        '    rules.append({"action": "resolve", "server": "dns-foreign"})', '    rules.append({"action": "resolve", "server": "dns-cn"})', 1))], "重新运行"),
    ("M93 “境外 DNS 不应答”那一遍不再包含没被接住的域名（那一遍等于什么也没证明）", [("tools/real_data.py", lambda s: s.replace(
        'SILENT_KINDS = ("proxied", "unlisted")', 'SILENT_KINDS = ("proxied",)', 1))], "重新运行"),
    ("M94 逐条扫描：把 sing-box 那一类已知的不一致从清单里拿掉（扫出来的主机没有归属）", [("tests/cases.yaml", lambda s: s.replace(
        "    - {kind: real_ip, why:", "    - {kind: something_else, why:", 1))], "已知类别"),
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

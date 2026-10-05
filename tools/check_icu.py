#!/usr/bin/env python3
"""用 ICU 的正则引擎跑一遍节点筛选正则，和 Python 的结果、手写的期望逐个对比。

为什么要有这一步：Loon 和 Quantumult X 用什么正则引擎，官方没有说明。推断是苹果系统自带的 NSRegularExpression
（底层是 ICU）：两者都是苹果平台的原生应用，官方和社区的示例里用到的前瞻、(?i) 等写法 ICU 都支持。
mihomo 用的是 regexp2（源码可查），sing-box 的分组在生成时用 Python 完成。
三个引擎的语法细节不完全一样，所以生成器只用它们都支持的写法，并在这里用 ICU 实际验证一遍。
这仍然不是真机验证：没有经过 Loon / Quantumult X 自己的配置解析，不是 iOS 上的那一份 ICU，
而且“它们用的是 ICU”本身是推断。

检查的正则（每个地区两条：手动组用的宽的、自动 / 故障转移 / 负载均衡用的严的；“其他地区”一条，共 13 条）：
  1. 当前统一源的（--public 时不读 source/local.yaml）：和 Python 的结果、tests/node_names.yaml 的手写期望对比；
     带上了你自己的 local.yaml 时只和 Python 对比（你的补充会改变分组，手写期望不再适用）。
  2. 加上 tests/local_overlay_sample.yaml 那份虚构的“本地补充”之后的：local.yaml 里写了 node_names 时，
     私密配置里的正则多出补充词和“整个名字完全相同”的分支，这条路径也要在 ICU 上跑一遍。

  3. 长名字（2026-10-04 加）：把“解锁”、地区词、国旗、括号、提示行的词各自重复到几百个字符，再加一批随机拼的。
     正常的节点名没有这么长；这里查的是“回溯失控”——正则写得不好时，匹配时间会随名字长度成倍增长，
     表现为客户端刷新节点时卡死。要求：每次匹配都在时间上限内结束，ICU、Python、逐步判断三者结果相同。
     写这套正则时真的出过一次（“跳过解锁说明”的两个分支能匹配同一个字符），所以单独留了这项检查。

用法：python3 tools/check_icu.py [--public] [--verbose]
      python3 tools/check_icu.py --public --long-names-only     只做第 3 项里不需要 ICU 的部分（Python 引擎 + 逐步判断）；
                                                                tests/test_regions.py 在子进程里带超时调用它
找 ICU 的顺序：Linux 的 libicui18n（系统自带或发行版软件包）、macOS 的 libicucore、Windows 10 1903 及以上的 icu.dll。
退出码：0 一致；1 有不一致；2 这台机器上找不到可用的 ICU（没有做检查）。
"""
import argparse
import ctypes
import ctypes.util
import json
import os
import random
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from generator import regions  # noqa: E402
from generator.model import load  # noqa: E402
from generator.regions import flag  # noqa: E402
from generator.util import safe_stdout  # noqa: E402

import yaml  # noqa: E402


def _load_icu():
    """返回 (库, 符号后缀, 说明)。找不到时返回 (None, "", 原因)。"""
    candidates = []
    if sys.platform == "darwin":
        candidates += ["/usr/lib/libicucore.dylib", "libicucore.dylib"]
    elif sys.platform.startswith("win"):
        candidates += ["icu.dll", "icuin.dll"]
    found = ctypes.util.find_library("icui18n")
    if found:
        candidates.append(found)
    candidates += [f"libicui18n.so.{v}" for v in range(90, 59, -1)]
    tried = []
    for name in candidates:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            tried.append(name)
            continue
        m = re.search(r"\.so\.(\d+)", name)
        suffixes = ([f"_{m.group(1)}"] if m else []) + [""] + [f"_{v}" for v in range(90, 59, -1)]
        for suf in suffixes:
            if hasattr(lib, "uregex_open" + suf):
                return lib, suf, name
        tried.append(name + "（没有 uregex_open）")
    return None, "", "没有找到 ICU 库（试过 " + "、".join(tried[:6]) + " 等）"


# ICU 自带的两道保险：回溯栈上限（默认 8 MB）和时间上限（默认不限）。这里把时间上限设上：
# 万一某条正则回溯失控，得到的是一个错误码，而不是整个检查卡死。单位是引擎的“步数”，量级大约是毫秒。
ICU_TIME_LIMIT = 5000
ICU_ERRORS = {66321: "回溯栈溢出 U_REGEX_STACK_OVERFLOW", 66322: "超过时间上限 U_REGEX_TIME_OUT"}
LONG_LENGTHS = (120, 400)          # 长名字检查用的两档长度（字符数）
SLOW_MS = 1500                     # 单次匹配超过这么多毫秒就算失败（正常是零点几到十几毫秒）


class ICURegex:
    """ICU C 接口 uregex_* 的最小封装：模式和文本都按 UTF-16 传入。"""

    def __init__(self, lib, suf: str, pattern: str):
        self._open = getattr(lib, "uregex_open" + suf)
        self._open.restype = ctypes.c_void_p
        self._open.argtypes = [ctypes.c_char_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_void_p,
                               ctypes.POINTER(ctypes.c_int32)]
        self._set = getattr(lib, "uregex_setText" + suf)
        self._set.restype = None
        self._set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
        self._find = getattr(lib, "uregex_find" + suf)
        self._find.restype = ctypes.c_int8
        self._find.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
        self._close = getattr(lib, "uregex_close" + suf)
        self._close.restype = None
        self._close.argtypes = [ctypes.c_void_p]
        self._pb = pattern.encode("utf-16-le")
        st = ctypes.c_int32(0)
        perr = ctypes.create_string_buffer(256)          # UParseError
        self._h = self._open(self._pb, len(self._pb) // 2, 0, perr, ctypes.byref(st))
        if st.value > 0 or not self._h:
            raise ValueError(f"ICU 不接受这条正则（错误码 {st.value}）")
        limit = getattr(lib, "uregex_setTimeLimit" + suf, None)
        if limit is not None:
            limit.restype = None
            limit.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
            limit(self._h, ICU_TIME_LIMIT, ctypes.byref(st))

    def search(self, text: str) -> bool:
        tb = text.encode("utf-16-le")
        st = ctypes.c_int32(0)
        self._set(self._h, tb, len(tb) // 2, ctypes.byref(st))
        r = self._find(self._h, 0, ctypes.byref(st))
        if st.value > 0:
            raise ValueError(f"ICU 匹配出错（{ICU_ERRORS.get(st.value, '错误码 ' + str(st.value))}）")
        return bool(r)

    def close(self):
        if self._h:
            self._close(self._h)
            self._h = None


def _hand_written():
    with open(os.path.join(ROOT, "tests", "node_names.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def sample_expect_auto():
    """{名字: 期望进哪个地区的自动 / 故障转移 / 负载均衡}（严的那套）。说不清落地的、其他地区的、提示行都是空。"""
    d = _hand_written()
    out = {}
    for k, names in d["expect"].items():
        for n in names:
            out[n] = [] if k in ("info", "other") else [k]
    for e in d["manual_only"]:
        out[e["name"]] = []
    return out


def sample_names():
    """手写样本（带期望）+ CLDR / 时区库的国家、城市名（独立来源）。返回 (名字列表, {名字: 期望进哪些地区的手动组})。"""
    d = _hand_written()
    expect = {}
    for k, names in d["expect"].items():
        for n in names:
            expect[n] = [] if k == "info" else [k]
    for e in d["manual_only"]:
        expect[e["name"]] = sorted(e["groups"])
    names = list(expect)
    with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
        ref = json.load(f)
    for c in ref["regions"]:
        fl = flag(c["code"])
        names += [f"{fl} {c['zh_hans']} 01", f"{c['zh_hans']} 01", f"{c['zh_hant']} 01", f"{c['en']} 01",
                  f"{c['code']}-01", f"{fl} {c['code']} 01"]
    names += [z["city"] + " 01" for z in ref["tz_cities"]]
    return list(dict.fromkeys(names)), expect


def overlay_sample():
    """tests/local_overlay_sample.yaml：虚构的本地补充。返回 (node_names 的内容, {名字: 期望的组})。"""
    with open(os.path.join(ROOT, "tests", "local_overlay_sample.yaml"), encoding="utf-8") as f:
        d = yaml.safe_load(f)
    return d["node_names"], {e["name"]: sorted(e["groups"]) for e in d["expect"]}


def overlay_expect_auto():
    """本地补充样例里每个名字期望进哪个地区的自动组：没单独写的，就是它进的那个地区（其他地区没有自动组）。"""
    with open(os.path.join(ROOT, "tests", "local_overlay_sample.yaml"), encoding="utf-8") as f:
        d = yaml.safe_load(f)
    return {e["name"]: sorted(e.get("auto", [g for g in e["groups"] if g != "other"])) for e in d["expect"]}


def overlay_regexes():
    """当前词表加上那份虚构的本地补充后拼出的正则（不读、不写 source/local.yaml）。返回 (宽的, 严的)。"""
    with open(os.path.join(ROOT, "source", "regions.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    spec, errors = regions.parse(data, overlay_sample()[0])
    if errors:
        raise ValueError("本地补充样例与当前词表冲突：" + "；".join(errors))
    return regions.compose_all(spec)


def stress_names(spec, length):
    """专门用来找“回溯失控”的长名字，每个大约 length 个字符：
    “解锁”这类词（完整的、只有半截的、带各种括号和竖线的）、地区词、国旗（成对的、落单的、后面接着中转词或“解锁”的）、
    中转词、箭头、提示行的词、括号、分隔符和连接符，各自重复很多遍，前后再接上正常的节点名；另有 60 个固定种子随机拼的。"""
    f = flag
    units = list(spec.unlock) + ["Unlock ", "解锁|", "解锁(", "解锁)", "（解锁", "解锁 美国 | ", "解", "u", "un", "unloc",
                                 "解锁：美国(Netflix)/"]
    units += ["美国 ", "US ", "香港", "日本→", "via ", "经", "HK-", "新加坡中转", "伦敦 ", "London ", "美国 伦敦 ", "德国"]
    units += [f("US"), f("US")[0], f("US") + f("JP"), f("DE"), f("CN") + "→", f("HK") + " "]
    units += ["官网", "到期", "Expire", "流量", "群", "剩余流量", "：", ":"]
    units += ["|", "(", ")", "【", "】", "｜", "丨", "[", "]", "（", "）"]
    units += ["a", " ", "0", "-", "_", "→", "\u200d", "é"]
    # 2026-10-05：连接符、国旗后面接中转词 / 解锁、via 后面隔连字符——这一版新加的几处前瞻、后顾各自重复很多遍
    units += ["·", ".", "/", "—", "香港·", "日本·中转·", "日本-中转-", "美国-解锁 ", "via-", "经_",
              f("JP") + "中转", f("JP") + " Relay ", f("US") + "解锁", f("US") + f("JP") + "·", f("HK") + "-"]
    out = []
    for u in units:
        s = u * max(1, length // len(u))
        out += [s, s + " 日本 01", "香港 01 " + s, s + "|美国", s + "："]
    rnd = random.Random(length)
    words = [x for w in spec.regions + [spec.other] for x in w.words + w.latin + [f(c) for c in w.flags]]
    tokens = (words + spec.after + spec.before + spec.arrows + spec.unlock + spec.info_words + spec.info_colon
              + spec.info_latin + ["|", "(", ")", "【", "】", " ", "-", "01", ":", "："])
    for _ in range(60):
        s = ""
        while len(s) < length:
            s += rnd.choice(tokens) + rnd.choice(["", " ", "|"])
        out.append(s)
    return list(dict.fromkeys(out))


def long_name_check(spec, loose, strict, engine, label):
    """长名字 × 13 条正则：每次匹配都要在 SLOW_MS 内结束、不出错，分组要和逐步判断（Classifier）相同。
    engine(正则) 返回一个 名字 → 是否匹配 的函数。返回 (问题列表, 给人看的一行结果)。"""
    cl = regions.Classifier(spec)
    compiled = ([(0, k, engine(v)) for k, v in loose.items()] + [(1, k, engine(v)) for k, v in strict.items()])
    problems, slowest, count = [], (0.0, "", ""), 0
    for length in LONG_LENGTHS:
        names = stress_names(spec, length)
        count += len(names)
        got = {n: ([], []) for n in names}
        for which, gid, match in compiled:
            for n in names:
                t = time.perf_counter()
                try:
                    hit = match(n)
                except ValueError as e:
                    problems.append(f"{'严' if which else '宽'} {gid}：{n[:30]!r}…（{len(n)} 个字符）{e}")
                    continue
                dt = time.perf_counter() - t
                if dt > slowest[0]:
                    slowest = (dt, f"{'严' if which else '宽'} {gid}", f"{n[:16]}…（{len(n)} 个字符）")
                if hit:
                    got[n][which].append(gid)
        for n in names:
            v = cl.classify(n)
            if sorted(got[n][0]) != sorted(v.groups) or sorted(got[n][1]) != sorted(v.auto):
                problems.append(f"{n[:30]!r}…（{len(n)} 个字符）：{label} {sorted(got[n][0])} / {sorted(got[n][1])}，"
                                f"逐步判断 {sorted(v.groups)} / {sorted(v.auto)}")
    if slowest[0] * 1000 > SLOW_MS:
        problems.append(f"最慢的一次匹配用了 {slowest[0] * 1000:.0f} 毫秒（上限 {SLOW_MS}）：{slowest[1]}，{slowest[2]}")
    line = (f"长名字（{'、'.join(str(x) for x in LONG_LENGTHS)} 个字符两档，共 {count} 个）× {len(compiled)} 条正则，{label}："
            + ("全部按时结束，分组与逐步判断完全一致" if not problems else f"有 {len(problems)} 个问题")
            + f"；最慢的一次 {slowest[0] * 1000:.1f} 毫秒（{slowest[1]}，{slowest[2]}）")
    return problems, line


def compare(lib, suf, rxs, names, expect, verbose=False):
    """每条正则用 ICU 和 Python 各跑一遍。返回 (与 Python 不一致的, 与期望不符的, 平均每次匹配的微秒数)；
    ICU 不接受某条正则时抛 ValueError。expect 为 None 时不比期望。"""
    diffs, total = [], 0.0
    icu_groups = {n: [] for n in names}
    for gid, rx in rxs.items():
        try:
            icu = ICURegex(lib, suf, rx)
        except ValueError as e:
            raise ValueError(f"{gid}：{e}")
        py = re.compile(rx)
        t = time.perf_counter()
        hits = [icu.search(n) for n in names]
        dt = time.perf_counter() - t
        total += dt
        icu.close()
        for n, h in zip(names, hits):
            if h:
                icu_groups[n].append(gid)
            if h != bool(py.search(n)):
                diffs.append(f"{gid}：{n!r} ICU={h} Python={not h}")
        if verbose:
            print(f"  {gid}：正则 {len(rx.encode('utf-8'))} 字节，ICU 平均 {dt / len(names) * 1e6:.0f} 微秒 / 次")
    wrong = [f"{n!r}：期望 {want}，ICU 得到 {sorted(icu_groups[n])}" for n, want in (expect or {}).items()
             if sorted(icu_groups[n]) != want]
    return diffs, wrong, total / (len(names) * len(rxs)) * 1e6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public", action="store_true", help="不读 source/local.yaml")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--long-names-only", action="store_true",
                    help="只做长名字检查里不需要 ICU 的部分（Python 引擎 + 逐步判断）")
    a = ap.parse_args(argv)
    safe_stdout()
    if a.long_names_only:
        model = load(ROOT, include_local=not a.public)
        problems, line = long_name_check(model.region_spec, model.node_regexes(), model.node_regexes_strict(),
                                         lambda rx: (lambda n, c=re.compile(rx): bool(c.search(n))), "Python")
        print(line)
        for x in problems[:20]:
            print("  " + x)
        return 1 if problems else 0
    lib, suf, where = _load_icu()
    if lib is None:
        print(f"没有做 ICU 检查：{where}")
        return 2
    model = load(ROOT, include_local=not a.public)
    has_local = (not a.public) and os.path.exists(os.path.join(ROOT, "source", "local.yaml"))
    rxs, strict = model.node_regexes(), model.node_regexes_strict()
    names, expect = sample_names()
    expect_auto = sample_expect_auto()
    print(f"ICU 库：{where}" + (f"（符号后缀 {suf}）" if suf else ""))
    print(f"统一源 {model.project['project']['source_version']}；筛选正则 {len(rxs) + len(strict)} 条"
          f"（宽 {len(rxs)} 条、严 {len(strict)} 条）× {len(names)} 个节点名（其中 {len(expect)} 个有手写的期望）")
    failed = False
    avgs = []
    for label, rx_set, exp in (("宽的那套（手动组用）", rxs, expect), ("严的那套（自动 / 故障转移 / 负载均衡用）", strict, expect_auto)):
        if a.verbose:
            print(label + "：")
        try:
            diffs, wrong, avg = compare(lib, suf, rx_set, names, None if has_local else exp, a.verbose)
        except ValueError as e:
            print(f"[不一致] {label}：{e}")
            return 1
        avgs.append(avg)
        print(f"{label}：ICU 与 Python 的匹配结果{'完全一致' if not diffs else f'有 {len(diffs)} 处不一致'}；"
              + ("没有比手写期望（带上了 source/local.yaml，你的补充会改变分组；加 --public 可以比）" if has_local
                 else f"ICU 的分组与手写期望{'完全一致' if not wrong else f'有 {len(wrong)} 个不符'}"))
        for x in (diffs + wrong)[:20]:
            print("  " + x)
        failed = failed or bool(diffs or wrong)
    # 各端每刷新一次节点列表要匹配多少次：Loon 13 条筛选各一次；Quantumult X 每个策略各一条（6 个手动 + 18 个自动类 + 其他地区 + PayPal）
    loon = (len(rxs) * avgs[0] + len(strict) * avgs[1]) * 300 / 1000
    qx = ((len(rxs) + 1) * avgs[0] + 3 * len(strict) * avgs[1]) * 300 / 1000
    print(f"ICU 平均每次匹配：宽 {avgs[0]:.0f} 微秒、严 {avgs[1]:.0f} 微秒（含调用开销；本机 CPU，手机会慢几倍）。"
          f"按 300 个节点估算：Loon {loon:.0f} 毫秒，Quantumult X（26 个策略各一条）{qx:.0f} 毫秒")

    # 带本地补充的那套正则（私密配置里的写法）
    _, o_expect = overlay_sample()
    o_names = list(dict.fromkeys(list(o_expect) + names))
    o_loose, o_strict = overlay_regexes()
    for label, rx_set, exp in (("宽", o_loose, o_expect), ("严", o_strict, overlay_expect_auto())):
        try:
            o_diffs, o_wrong, _ = compare(lib, suf, rx_set, o_names, exp)
        except ValueError as e:
            print(f"[不一致] 带本地补充样例的正则（{label}）：{e}")
            return 1
        print(f"带本地补充样例（tests/local_overlay_sample.yaml）的正则（{label}）× {len(o_names)} 个节点名："
              f"ICU 与 Python {'完全一致' if not o_diffs else f'{len(o_diffs)} 处不一致'}；"
              f"{len(exp)} 个手写期望{'全部符合' if not o_wrong else f'有 {len(o_wrong)} 个不符'}")
        for x in (o_diffs + o_wrong)[:20]:
            print("  " + x)
        failed = failed or bool(o_diffs or o_wrong)

    # 长名字：ICU、Python 各跑一遍，都和逐步判断比
    for label, engine in (("ICU", lambda rx: ICURegex(lib, suf, rx).search),
                          ("Python", lambda rx: (lambda n, c=re.compile(rx): bool(c.search(n))))):
        problems, line = long_name_check(model.region_spec, rxs, strict, engine, label)
        print(line)
        for x in problems[:20]:
            print("  " + x)
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

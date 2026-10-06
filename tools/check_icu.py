#!/usr/bin/env python3
"""用 ICU 的正则引擎跑一遍节点筛选正则，和 Python 的结果、手写的期望逐个对比。

为什么要有这一步：Loon 和 Quantumult X 用什么正则引擎，官方没有说明。推断是苹果系统自带的 NSRegularExpression
（底层是 ICU）：两者都是苹果平台的原生应用，官方和社区的示例里用到的前瞻、(?i) 等写法 ICU 都支持。
mihomo 用的是 regexp2（源码可查），sing-box 的分组在生成时用 Python 完成。
三个引擎的语法细节不完全一样，所以生成器只用它们都支持的写法，并在这里用 ICU 实际验证一遍。
这仍然不是真机验证：没有经过 Loon / Quantumult X 自己的配置解析，不是 iOS 上的那一份 ICU，
而且“它们用的是 ICU”本身是推断。

检查两套正则：
  1. 当前统一源的（--public 时不读 source/local.yaml）：和 Python 的结果、tests/node_names.yaml 的手写期望对比；
     带上了你自己的 local.yaml 时只和 Python 对比（你的补充会改变分组，手写期望不再适用）。
  2. 加上 tests/local_overlay_sample.yaml 那份虚构的“本地补充”之后的：local.yaml 里写了 node_names 时，
     私密配置里的正则多出补充词和“整个名字完全相同”的分支，这条路径也要在 ICU 上跑一遍。

用法：python3 tools/check_icu.py [--public] [--verbose]
找 ICU 的顺序：Linux 的 libicui18n（系统自带或发行版软件包）、macOS 的 libicucore、Windows 10 1903 及以上的 icu.dll。
退出码：0 一致；1 有不一致；2 这台机器上找不到可用的 ICU（没有做检查）。
"""
import argparse
import ctypes
import ctypes.util
import json
import os
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

    def search(self, text: str) -> bool:
        tb = text.encode("utf-16-le")
        st = ctypes.c_int32(0)
        self._set(self._h, tb, len(tb) // 2, ctypes.byref(st))
        r = self._find(self._h, 0, ctypes.byref(st))
        if st.value > 0:
            raise ValueError(f"ICU 匹配出错（错误码 {st.value}）")
        return bool(r)

    def close(self):
        if self._h:
            self._close(self._h)
            self._h = None


def sample_names():
    """手写样本（带期望）+ CLDR / 时区库的国家、城市名（独立来源）。返回 (名字列表, {名字: 期望的组})。"""
    with open(os.path.join(ROOT, "tests", "node_names.yaml"), encoding="utf-8") as f:
        d = yaml.safe_load(f)
    expect = {}
    for k, names in d["expect"].items():
        for n in names:
            expect[n] = [] if k == "info" else [k]
    for e in d["both"]:
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


def overlay_regexes():
    """当前词表加上那份虚构的本地补充后拼出的正则（不读、不写 source/local.yaml）。"""
    with open(os.path.join(ROOT, "source", "regions.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    spec, errors = regions.parse(data, overlay_sample()[0])
    if errors:
        raise ValueError("本地补充样例与当前词表冲突：" + "；".join(errors))
    return regions.compose(spec)


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
    a = ap.parse_args(argv)
    safe_stdout()
    lib, suf, where = _load_icu()
    if lib is None:
        print(f"没有做 ICU 检查：{where}")
        return 2
    model = load(ROOT, include_local=not a.public)
    has_local = (not a.public) and os.path.exists(os.path.join(ROOT, "source", "local.yaml"))
    rxs = model.node_regexes()
    names, expect = sample_names()
    print(f"ICU 库：{where}" + (f"（符号后缀 {suf}）" if suf else ""))
    print(f"统一源 {model.project['project']['source_version']}；{len(rxs)} 条筛选正则 × {len(names)} 个节点名"
          f"（其中 {len(expect)} 个有手写的期望）")
    try:
        diffs, wrong, avg = compare(lib, suf, rxs, names, None if has_local else expect, a.verbose)
    except ValueError as e:
        print(f"[不一致] {e}")
        return 1
    print(f"ICU 与 Python 的匹配结果：{'完全一致' if not diffs else f'{len(diffs)} 处不一致'}")
    for x in diffs[:20]:
        print("  " + x)
    if has_local:
        print("ICU 的分组与手写期望：没有比（带上了 source/local.yaml，你的补充会改变分组；加 --public 可以比）")
    else:
        print(f"ICU 的分组与手写期望：{'完全一致' if not wrong else f'{len(wrong)} 个不符'}")
    for x in wrong[:20]:
        print("  " + x)
    print(f"ICU 平均每次匹配 {avg:.0f} 微秒（含调用开销；本机 CPU，手机会慢几倍）。"
          f"按 300 个节点估算：Loon {len(rxs) * 300 * avg / 1000:.0f} 毫秒，"
          f"Quantumult X（每个模式组各一条，约 26 条）{26 * 300 * avg / 1000:.0f} 毫秒")

    # 带本地补充的那套正则（私密配置里的写法）
    _, o_expect = overlay_sample()
    o_names = list(dict.fromkeys(list(o_expect) + names))
    try:
        o_diffs, o_wrong, _ = compare(lib, suf, overlay_regexes(), o_names, o_expect)
    except ValueError as e:
        print(f"[不一致] 带本地补充样例的正则：{e}")
        return 1
    print(f"带本地补充样例（tests/local_overlay_sample.yaml）的正则 × {len(o_names)} 个节点名："
          f"ICU 与 Python {'完全一致' if not o_diffs else f'{len(o_diffs)} 处不一致'}；"
          f"{len(o_expect)} 个手写期望{'全部符合' if not o_wrong else f'有 {len(o_wrong)} 个不符'}")
    for x in (o_diffs + o_wrong)[:20]:
        print("  " + x)
    return 1 if diffs or wrong or o_diffs or o_wrong else 0


if __name__ == "__main__":
    sys.exit(main())

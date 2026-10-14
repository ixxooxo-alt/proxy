"""一次性核对（2026-10-14，r17；不参与测试）：Stash 两份配置里实际写的节点筛选（r17 起开头多一段排除内置策略名的前缀），
在 ICU 74 上能不能编译、结果和 Python 是否相同；加不加前缀，样本名字上的结果是否只差内置策略名那几个。

为什么要做：tools/check_icu.py 核对的是四端共用的 13 条正则，Stash 写进配置的是这 13 条开头再加 (?!(?:DIRECT|REJECT|REJECT-DROP)$)，
那一项没有覆盖。Stash 用什么正则引擎文档没写（docs/06），这里的结果只说明 ICU 和 Python 接受这种写法，不说明 Stash 接受。

用法（仓库根目录）：python3 handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

import yaml  # noqa: E402

import check_icu  # noqa: E402
from generator import emit_stash  # noqa: E402

BUILTIN = [x for n in emit_stash.BUILTIN_POLICIES for x in (n, n.lower(), n.title())]
HEAD = "(?i)^(?!(?:DIRECT|REJECT|REJECT-DROP)$)"


def main():
    lib, suf, how = check_icu._load_icu()
    if lib is None:
        print("没有 ICU：" + how)
        return 2
    print(f"ICU 库：{how}（符号后缀 {suf or '无'}）")
    names, _ = check_icu.sample_names()
    names = names + BUILTIN + ["DIRECT 01", "🇭🇰 香港 Direct 02", "Reject 01", "REJECT-DROP-1", "directx", " DIRECT"]
    print(f"名字：{len(names)} 个（check_icu.py 用的样本 + 内置策略名的几种写法 + 6 个只是含有这些字样的名字）")
    bad = 0
    for rel in ("stash/stash.yaml", "stash/stash-strict.yaml"):
        with open(os.path.join(ROOT, "dist", rel), encoding="utf-8") as f:
            conf = yaml.safe_load(f)
        filters = {}
        for g in conf["proxy-groups"]:
            if "filter" in g:
                filters.setdefault(g["filter"], []).append(g["name"])
        print(f"\n{rel}：带筛选的组 {sum(len(v) for v in filters.values())} 个，不同的筛选 {len(filters)} 条")
        for rx, groups in filters.items():
            assert rx.startswith(HEAD), groups
            plain = "(?i)^" + rx[len(HEAD):]
            icu, icu_plain = check_icu.ICURegex(lib, suf, rx), check_icu.ICURegex(lib, suf, plain)
            py, py_plain = re.compile(rx), re.compile(plain)
            diff_engine = [n for n in names if icu.search(n) != bool(py.search(n))]
            diff_prefix = [n for n in names if icu.search(n) != icu_plain.search(n)]
            picked_builtin = [n for n in BUILTIN if icu.search(n)]
            plain_builtin = [n for n in BUILTIN if icu_plain.search(n)]
            icu.close()
            icu_plain.close()
            ok = not diff_engine and set(diff_prefix) <= set(BUILTIN) and not picked_builtin
            bad += not ok
            print(f"  [{'符合' if ok else '不符合'}] {groups[0]}{'（另有 ' + str(len(groups) - 1) + ' 个组同一条）' if len(groups) > 1 else ''}："
                  f"{len(rx)} 个字符；ICU 与 Python 不同的 {len(diff_engine)} 个；ICU 上加不加前缀结果不同的 {len(diff_prefix)} 个"
                  f"（{'、'.join(diff_prefix) or '无'}）；加前缀后选中内置策略名 {len(picked_builtin)} 个；不加前缀会选中 {len(plain_builtin)} 个")
    print("\n" + ("全部符合" if not bad else f"有 {bad} 条不符合"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

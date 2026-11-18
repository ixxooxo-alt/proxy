#!/usr/bin/env python3
"""数一数 tests/test_regions.py 里 test_every_region_word_and_flag_in_a_non_landing_position_is_manual_only 套出多少个名字。

那项测试只断言“多于 30000 个”，不打印个数；docs/02 写的“六个地区词表里的每个词、每面国旗（N 个）套进 126 种写法，共 M 个名字”
就是照它的循环数出来的。这一版词表加了“港台 / 港臺 / 港新”，个数变了，所以重数一遍。只数个数，不做分类（分类由那项测试做）。
循环照抄那项测试（2026-11-18 的写法）；测试改了这里要跟着改。
用法：python3 -B handoff/notes/r22_draft/count_region_words.py <工程目录> [<工程目录> ...]
"""
import os
import re
import subprocess
import sys

CODE = r'''
import os, re, sys
sys.path.insert(0, ".")
sys.path.insert(0, "tests")
import test_regions as T
from generator import regions
s = T.spec()
templates = []
for word in ("中转", "中繼", "转", "入口", "Relay", "transit"):
    templates += ["{w}" + j + word + " 01" for j in ("", " ", "-", "_", "·", ".", "/", "—", " - ")]
for word in ("via", "VIA", "经", "經"):
    templates += [lead + word + gap + "{w} 01" for gap in (" ", "-", "_") for lead in ("", "IEPL ")]
templates += ["经{w} 01", "IEPL 經{w} 01"]
templates += ["{w}" + gap + arrow + " 01" for arrow in s.arrows for gap in ("", " ")]
for word in ("解锁", "解鎖", "Unlock"):
    templates += [word + gap + "{w} 01" for gap in (" ", ": ", "：", "-")]
    templates += ["Premium 01 | " + word + " {w}", "Premium 01 [" + word + " {w}]"]
    templates += ["{w}" + gap + word + " 01" for gap in (" ", "-", "_")]
templates += ["解锁{w} 01", "{w}解锁 01", "01 {w}解鎖"]
items_total, count = 0, 0
for r in s.regions:
    items = r.words + r.latin + [regions.flag(c) for c in r.flags] + (["港"] if r.id == "hk" else [])
    items_total += len(items)
    for w in items:
        for t in templates:
            if w.isascii() and re.search(r"[A-Za-z]\{w\}|\{w\}[A-Za-z]", t):
                continue
            count += 1
print(f"词和国旗 {items_total} 个，写法 {len(templates)} 种，名字 {count} 个")
'''

for root in sys.argv[1:]:
    r = subprocess.run([sys.executable, "-B", "-c", CODE], cwd=root, capture_output=True, text=True)
    print(f"{os.path.basename(os.path.abspath(root))}：{(r.stdout + r.stderr).strip()}")
    if r.returncode:
        sys.exit(r.returncode)

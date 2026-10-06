#!/usr/bin/env python3
"""生成 / 核对 source/data/cn-domains.txt：严格版（Loon / Quantumult X）用的国内域名清单。

数据来源是 domain-list-community（v2fly，MIT 授权）的 cn 列表：tld-cn（国内相关的顶级域）加 geolocation-cn
（国内公司与服务），按固定快照（source/evidence.yaml 里 dlc 登记的提交）展开。sing-box 那一端用的 geosite-cn 也源自它。
为什么要自己生成一份（2026-10-06）：严格版要先按域名认出国内网站再直连；Quantumult X 没有只含域名的上游成品可以直接订阅
（blackmatrix7 给它的 ChinaMax.list 里混着 13 条关键词、65 条 UA 规则），Loon 那份只含域名的 ChinaMax_Domain.list 又不含
整段顶级域（.cn 等写在另一个带关键词的文件里）。

用法：
  python3 tools/update_cn_list.py --dlc <domain-list-community 的检出目录>           重新生成数据文件
  python3 tools/update_cn_list.py --dlc <检出目录> --check                           只核对：现有文件必须和重新生成的逐字节相同
取舍（写在生成的文件头里）：
  - 正则条目不收：Loon / Quantumult X 的域名规则写不了正则；
  - 带 @ads 的条目照收：和 geosite:cn 的范围保持一致（这两端的广告集合排在这份清单之前）；
  - 已经被清单里别的后缀覆盖的条目去掉（例如整段 cn 之下的 12306.cn）：匹配范围不变，规则条数少一半以上。
退出码：0 正常；1 --check 发现不一致；2 参数或环境问题（检出目录的提交不是登记的那个等）。
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import check_upstream_evidence as cue  # noqa: E402
from generator.strict import CN_DATA_REL, parse_cn_domains  # noqa: E402
from generator.util import safe_stdout, valid_domain  # noqa: E402

LIST_NAME = "cn"
LICENSE_REL = "source/data/LICENSE-domain-list-community.txt"


def derive(dlc_dir: str):
    """返回 (后缀集合, 精确域名集合, 统计)。"""
    own, inc = cue.parse_dlc(os.path.join(dlc_dir, "data"))
    rules = cue.resolve(own, inc, LIST_NAME)
    stats = {"resolved": len(rules), "regexp": 0, "keyword": 0, "invalid": []}
    suffix, full = set(), set()
    for kind, value, _attrs in rules:
        if kind == "regexp":
            stats["regexp"] += 1
        elif kind == "keyword":
            stats["keyword"] += 1
        elif not valid_domain(value):
            stats["invalid"].append(value)
        elif kind == "domain":
            suffix.add(value)
        else:
            full.add(value)
    stats["suffix_before"], stats["full_before"] = len(suffix), len(full)

    def covered(name: str, itself: bool) -> bool:
        """name 是否已经被别的后缀条目覆盖（itself=True 时同名的后缀条目也算，用于精确域名）。"""
        parts = name.split(".")
        return any(".".join(parts[i:]) in suffix for i in range(0 if itself else 1, len(parts)))

    suffix_kept = {s for s in suffix if not covered(s, False)}
    full_kept = {f for f in full if not covered(f, True)}
    return suffix_kept, full_kept, stats


def render(dlc_dir: str, commit: str, date: str) -> str:
    suffix, full, st = derive(dlc_dir)
    lines = [
        "# 国内域名清单：严格版（Loon / Quantumult X）按它认出国内网站、交给“国内直连”。由 tools/update_cn_list.py 生成，不要手改。",
        "# 来源：v2fly/domain-list-community 的 cn 列表（tld-cn 加 geolocation-cn，展开 include），"
        f"固定快照 {commit}（{date}）。",
        "# 授权：MIT，Copyright (c) 2018-2019 V2Ray；许可全文见本项目的 " + LICENSE_REL + "。",
        f"# 展开后 {st['resolved']} 条；正则 {st['regexp']} 条、关键词 {st['keyword']} 条不收（这两端的域名规则写不了正则，关键词范围太宽）；"
        "带 @ads 的条目照收（与 geosite:cn 范围一致）。",
        f"# 去重后后缀 {st['suffix_before']} 条、精确域名 {st['full_before']} 条；再去掉已被清单里别的后缀覆盖的条目"
        f"（匹配范围不变），剩下后缀 {len(suffix)} 条、精确域名 {len(full)} 条。",
        "# 写法：每行一个域名。以“.”开头的表示这个域名和它的全部子域；不带点开头的只表示这一个主机。",
    ]
    if st["invalid"]:
        lines.append(f"# 写法不合规、没有收的条目 {len(st['invalid'])} 条：" + "、".join(sorted(st["invalid"])[:20]))
    key = lambda d: (d.split(".")[::-1])                    # noqa: E731  按“从顶级域往下”排序，同一家的域名排在一起
    lines += ["." + s for s in sorted(suffix, key=key)]
    lines += sorted(full, key=key)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dlc", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    safe_stdout()
    if not os.path.isdir(os.path.join(a.dlc, "data")):
        print(f"{a.dlc} 不是 domain-list-community 的检出目录（没有 data/）", file=sys.stderr)
        return 2
    info = cue.git_info(a.dlc)
    # 直接读登记表，不加载整个统一源：数据文件还不存在（第一次生成）时，统一源本身是加载不了的
    with open(os.path.join(ROOT, "source", "evidence.yaml"), encoding="utf-8") as f:
        want = str(yaml.safe_load(f)["evidence"]["dlc"].get("snapshot", ""))
    if info["commit"] != want:
        print(f"检出目录的提交 {info['commit'] or '（读不到）'} 不是 source/evidence.yaml 里 dlc 登记的 {want}", file=sys.stderr)
        return 2
    text = render(a.dlc, info["commit"], info["date"][:10])
    path = os.path.join(ROOT, *CN_DATA_REL.split("/"))
    lic_src, lic_dst = os.path.join(a.dlc, "LICENSE"), os.path.join(ROOT, *LICENSE_REL.split("/"))
    with open(lic_src, encoding="utf-8") as f:
        lic = f.read()
    suffix, full = parse_cn_domains(text)
    summary = f"后缀 {len(suffix)} 条、精确域名 {len(full)} 条（快照 {info['commit'][:8]}，{info['date'][:10]}）"
    if a.check:
        problems = []
        for p, expect, what in ((path, text, CN_DATA_REL), (lic_dst, lic, LICENSE_REL)):
            if not os.path.exists(p):
                problems.append(f"{what} 不存在")
                continue
            with open(p, encoding="utf-8") as f:
                if f.read() != expect:
                    problems.append(f"{what} 与按固定快照重新生成的不一样（手改过，或者换了快照没有重新生成）")
        if problems:
            print("不一致：\n  - " + "\n  - ".join(problems))
            return 1
        print(f"{CN_DATA_REL} 与按固定快照重新生成的逐字节相同：{summary}")
        print(f"{LICENSE_REL} 与上游的 LICENSE 相同")
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for p, content in ((path, text), (lic_dst, lic)):
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print(f"已写入 {CN_DATA_REL}：{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

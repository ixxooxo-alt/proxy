#!/usr/bin/env python3
"""核对策略组图标：配置里写的每个图标地址，在图标仓库里是不是真有那张图。

图片不在本工程里（在用户自己的图标仓库 https://github.com/ixxooxo-alt/icon ），本工程只在 source/icons.yaml 里登记
“哪个策略组用哪张图”。自动测试只能检查地址写得对不对；图片在不在，要拿图标仓库的检出目录来对：

  git clone https://github.com/ixxooxo-alt/icon.git <目录>
  python3 tools/check_icons.py --icon-repo <目录>

检查的内容：
  1. 三个带图标的客户端产物（Loon、Quantumult X、mihomo）里，每个策略组的图标地址都指向检出目录里存在的文件；
  2. 那个文件是 PNG，宽高和目录名一致（256px 目录里是 256×256）；
  3. source/icons.yaml 的 available 和目录里实际有的图一致（仓库里多了图只提示，少了图算失败）；
  4. 图标仓库自己公布的地址清单（icon-urls.json）里对应的地址，和本工程生成的逐个相同；清单里没有的组不比、单独列出
     （还没有上传的，以及图标仓库后来单独加、没有写进清单的图，例如 2026-10-06 的 Apple Push——文件本身照样按 1、2 核对）；
  5. 检出目录的提交和 icons.yaml 里登记的 checked_commit 是否相同（不同只提示：图标仓库会继续更新）。
只读取文件，不联网，不修改图标仓库。退出码：0 全部符合；1 有不符合；2 参数或环境问题。
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build as builder  # noqa: E402
from generator.model import build_plan, load  # noqa: E402
from generator.util import safe_stdout  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_size(path: str):
    """(宽, 高, 颜色类型)；不是 PNG 时返回 None。只读文件头，不解码图片。"""
    with open(path, "rb") as f:
        head = f.read(33)
    if len(head) < 26 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
        return None
    width, height, _depth, color = struct.unpack(">IIBB", head[16:26])
    return width, height, color


def icons_from_outputs(files: dict) -> dict:
    """{产物: {策略组名: 图标地址}}，从生成的文本里读。"""
    import yaml
    out = {}
    for rel, text in files.items():
        got = {}
        if rel.startswith("mihomo/"):
            for g in yaml.safe_load(text)["proxy-groups"]:
                if "icon" in g:
                    got[g["name"]] = g["icon"]
        elif rel.startswith(("loon/", "quantumultx/")) and rel.endswith(".conf"):      # 标准版和严格版；rules/ 下的规则文件不是配置
            loon = rel.startswith("loon/")
            section, want = None, "Proxy Group" if loon else "policy"
            for line in text.splitlines():
                if line.startswith("["):
                    section = line.strip("[]")
                    continue
                if section != want or not line.strip() or line.startswith(("#", ";")):
                    continue
                m = re.search(r",img-url = (\S+)$" if loon else r", img-url=(\S+)$", line)
                if m:
                    name = line.split(" = ", 1)[0] if loon else line.split("=", 1)[1].split(",", 1)[0].strip()
                    got[name] = m.group(1)
        else:
            continue
        out[rel] = got
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icon-repo", required=True, help="图标仓库的检出目录")
    a = ap.parse_args(argv)
    safe_stdout()
    if not os.path.isdir(a.icon_repo):
        print(f"--icon-repo 指向的 {a.icon_repo} 不是目录", file=sys.stderr)
        return 2
    model = load(ROOT, include_local=False)
    ic = model.icons
    if not ic.get("enabled"):
        print("source/icons.yaml 没有启用图标（enabled: false 或没有这个文件），没有可核对的。")
        return 0
    files = builder.render_public(model, build_plan(model))
    per_output = icons_from_outputs(files)
    base = ic["base_url"]
    size_dir = urlparse(base).path.rstrip("/").rsplit("/", 1)[-1]          # 256px
    folder = os.path.join(a.icon_repo, size_dir)
    failures, notes = [], []
    if not os.path.isdir(folder):
        print(f"图标仓库里没有 {size_dir}/ 目录", file=sys.stderr)
        return 2

    head = subprocess.run(["git", "-C", a.icon_repo, "rev-parse", "HEAD"], capture_output=True, text=True)
    commit = head.stdout.strip() if head.returncode == 0 else "（不是 git 检出目录，读不到提交）"
    when = subprocess.run(["git", "-C", a.icon_repo, "log", "-1", "--format=%cd", "--date=iso"], capture_output=True, text=True)
    print(f"统一源 {model.project['project']['source_version']}；图标地址前缀 {base}")
    print(f"图标仓库检出目录的提交：{commit}" + (f"（{when.stdout.strip()}）" if when.returncode == 0 and when.stdout.strip() else ""))
    print(f"icons.yaml 登记的 checked_commit：{ic.get('checked_commit')}（{ic.get('checked')}）")
    if head.returncode == 0 and commit != ic.get("checked_commit"):
        notes.append("检出目录的提交和登记的不同：这次核对的是检出目录里现在的文件。核对通过后可以把 icons.yaml 的 checked_commit 改成这个提交")

    pending = set(ic.get("pending") or [])          # 已经写进配置、图还没有传到图标仓库的（文件名）
    want_px = int(size_dir[:-2]) if re.fullmatch(r"\d+px", size_dir) else None
    on_disk = sorted(f[:-len(ic.get("ext", ".png"))] for f in os.listdir(folder) if f.endswith(ic.get("ext", ".png")))
    missing_files = sorted(set(ic["available"]) - set(on_disk))
    extra_files = sorted(set(on_disk) - set(ic["available"]))
    if missing_files:
        failures.append(f"available 里登记了、{size_dir}/ 里没有的图：{missing_files}")
    if extra_files:
        notes.append(f"{size_dir}/ 里有、available 里没登记的图（不影响现有配置）：{extra_files}")

    total_bytes, checked, seen_urls = 0, 0, {}
    waiting_files, uploaded = set(), set()
    for rel, got in sorted(per_output.items()):
        bad = []
        for name, url in got.items():
            if not url.startswith(base):
                bad.append(f"{name}：地址不在登记的前缀下 {url}")
                continue
            file_name = unquote(url[len(base):])
            path = os.path.join(folder, file_name)
            stem = file_name[:-len(ic.get("ext", ".png"))]
            if not os.path.isfile(path):
                if stem in pending:                 # 登记为“还没有上传”的：不算不符合，但要说清楚
                    waiting_files.add(file_name)
                    continue
                bad.append(f"{name}：图标仓库里没有 {size_dir}/{file_name}")
                continue
            if stem in pending:
                uploaded.add(stem)
            info = png_size(path)
            if info is None:
                bad.append(f"{name}：{size_dir}/{file_name} 不是 PNG")
            elif want_px and (info[0], info[1]) != (want_px, want_px):
                bad.append(f"{name}：{size_dir}/{file_name} 是 {info[0]}×{info[1]}，不是 {want_px}×{want_px}")
            if url not in seen_urls:
                seen_urls[url] = name
                total_bytes += os.path.getsize(path)
            checked += 1
        n_wait = sum(1 for url in got.values() if unquote(url[len(base):]) in waiting_files)
        print(f"  [{'符合' if not bad else '不符合'}] {rel}：{len(got)} 个策略组的图标"
              + ((f"里 {len(got) - n_wait} 个" if n_wait else "") + "都在图标仓库里，是 PNG，尺寸对" if not bad else f"，{len(bad)} 个有问题")
              + (f"；{n_wait} 个还没有上传（已登记在 pending）" if n_wait else ""))
        for x in bad[:20]:
            print("      " + x)
        failures += [f"{rel}：{x}" for x in bad]
    counts = {rel: len(got) for rel, got in per_output.items()}
    if len(set(counts.values())) != 1:
        failures.append(f"各端带图标的策略组数量不一样：{counts}")
    same = all(got == next(iter(per_output.values())) for got in per_output.values())
    print(f"  [{'符合' if same else '不符合'}] 各端同一个策略组用的是同一个地址")
    if not same:
        failures.append("各端同一个策略组的图标地址不一样")
    print(f"用到的图片 {len(seen_urls)} 张，合计 {total_bytes:,} 字节（客户端显示图标时要下载；缓存不缓存、多久刷新由各客户端决定，没有核对）")

    listing = os.path.join(a.icon_repo, "icon-urls.json")
    if os.path.exists(listing):
        with open(listing, encoding="utf-8") as f:
            published = {x["group_name"]: x.get(f"url_{size_dir}") for x in json.load(f)}
        first = next(iter(per_output.values()))
        # 清单里没有的组不拿来比：还没有传到图标仓库的（icons.yaml 的 pending），以及图已经在图标仓库里、
        # 但图标仓库没有把它写进清单的。后一种的文件上面已经核对过（存在、是 PNG、尺寸对）；文件不在又没有登记 pending 的，上面已经算不符合
        waiting = [n for n in first if model.icon_file(n) in pending and n not in published]
        unlisted = [n for n in first if n not in published and n not in waiting]
        compared = {n: u for n, u in first.items() if n in published}
        diff = [(n, u, published.get(n)) for n, u in compared.items() if published.get(n) != u]
        print(f"  [{'符合' if not diff else '不符合'}] 与图标仓库公布的地址清单（icon-urls.json 的 url_{size_dir}）对比："
              + (f"{len(compared)} 个地址逐个相同" if not diff else f"{len(diff)} 个不同")
              + (f"；{len(waiting)} 个还没有上传的不在清单里，没有比：{'、'.join(waiting)}" if waiting else "")
              + (f"；{len(unlisted)} 个图在图标仓库里、清单没有收，没有比：{'、'.join(unlisted)}" if unlisted else ""))
        for n in unlisted:
            notes.append(f"图标仓库公布的地址清单（icon-urls.json，共 {len(published)} 项）里没有 {n}：这个组的图标地址没有和清单比过，"
                         f"文件本身核对过（{size_dir}/{model.icon_file(n)}{ic.get('ext', '.png')} 存在，是 PNG，尺寸对）")
        for n, mine, theirs in diff[:20]:
            print(f"      {n}：本工程 {mine}，清单 {theirs}")
        failures += [f"与 icon-urls.json 不同：{n}" for n, _, _ in diff]
    else:
        notes.append("图标仓库里没有 icon-urls.json，没有做地址清单的对比")

    for file_name in sorted(waiting_files):
        notes.append(f"{size_dir}/{file_name} 还没有传到图标仓库（icons.yaml 的 pending 里登记了）：配置里这个组的图标地址现在打不开，"
                     "App 里这个组没有图标，分流不受影响。图传上去以后重新跑这项核对")
    for stem in sorted(uploaded):
        notes.append(f"pending 里登记的 {stem} 现在已经在图标仓库里了，这次已经按普通图标核对过（是 PNG、尺寸对）："
                     "可以把它从 pending 挪到 available，并更新 checked_commit")
    for x in notes:
        print("注意：" + x)
    print()
    print("全部符合" if not failures else f"{len(failures)} 处不符合")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""看一批节点名各自会被分到哪个地区组、为什么（Loon、Quantumult X、Clash、sing-box 四端用的是同一套规则）。

用法：
  python3 tools/check_node_names.py 节点名.txt            每行一个节点名
  python3 tools/check_node_names.py --clash 订阅.yaml     Clash / mihomo 格式的订阅文件：只读取节点名称
  python3 tools/check_node_names.py -                      从标准输入读，每行一个节点名
选项：
  --all         列出每一个节点（默认只列需要你看一眼的：没认出的、说不清落地只进手动组的、按中转规则判断的、
                被当成提示行的、名字里有提示行常用的词但仍按节点处理的）
  --public      不读 source/local.yaml（看公开版配置的结果）。默认有 local.yaml 就带上里面的 node_names
  --out 文件    把报告另存一份

只处理节点名称，不读取也不输出服务器地址、密码等其他字段；不联网。订阅链接不要贴进来，贴节点名就够了。
名称只是初筛：这里判断的是“名字写的是哪里”，不证明节点实际从哪里出去。
退出码：0 正常（有没认出的节点也是 0，这是报告不是校验）；2 输入读不了或统一源有错；3 两种判断方式结果不一致（请反馈）。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from generator import nodes as nodeconv, regions  # noqa: E402
from generator.model import SourceError, load  # noqa: E402
from generator.util import safe_stdout  # noqa: E402


def read_names(a) -> list:
    if a.clash:
        with open(a.clash, encoding="utf-8") as f:
            proxies = nodeconv.load_clash_proxies(f.read())
        names = [str(p["name"]) for p in proxies if isinstance(p, dict) and p.get("name") is not None]
    else:
        if a.file == "-":
            text = sys.stdin.read()
        else:
            with open(a.file, encoding="utf-8-sig") as f:
                text = f.read()
        names = [line.strip() for line in text.splitlines()]
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def main(argv=None, root: str = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="每行一个节点名的文本文件；- 表示标准输入")
    ap.add_argument("--clash", help="Clash / mihomo 格式的订阅文件（只读取节点名称）")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    safe_stdout()
    if bool(a.file) == bool(a.clash):
        ap.error("请给出一个节点名文件（或 -），或者用 --clash 指定订阅文件，二选一")
    try:
        names = read_names(a)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"读不了输入：{e}", file=sys.stderr)
        return 2
    if not names:
        print("没有读到任何节点名。", file=sys.stderr)
        return 2
    try:
        model = load(root, include_local=not a.public)
    except SourceError as e:
        print(e, file=sys.stderr)
        return 2
    has_local = (not a.public) and os.path.exists(os.path.join(root, "source", "local.yaml"))
    lines, stats = regions.render_report(model.region_spec, names, show_all=a.all)
    head = (f"统一源 {model.project['project']['source_version']}，"
            + ("含 source/local.yaml 的补充（对应 dist/private/ 里的配置）" if has_local else "公开版词表（对应 dist/ 里的配置）"))
    text = "\n".join([head] + lines) + "\n"
    sys.stdout.write(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return 3 if stats["inconsistent"] else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""打交付包：把工程里该交付的文件收进一个 zip。

用法：python3 handoff/release/pack.py <输出的 zip 路径> [--root 工程目录] [--without-handoff]
  --root             缺省是这个脚本所在的仓库
  --without-handoff  不收 CLAUDE.md 和 handoff/。r12 的交付包就是这样的（那时还没有这两样）

不收的：.git、__pycache__、*.pyc、dist/private/、source/local.yaml、生成中断时留下的 .new-* / .bak-*、
以“.”开头的文件（.gitignore 除外）。zip 里的顶层目录叫 proxy-rules/。文件名里有中文：Python 的 zipfile 会自动设 UTF-8 标志。
打完以后打印文件数、字节数和 SHA-256。同一批文件、同样的修改时间，打出来的 zip 逐字节相同
（2026-10-06 用它在 r12 的工程目录上重打过一次，SHA-256 与当时发出去的那个包一致）；从 git 检出的目录修改时间不同，SHA-256 也就不同。
打完用 handoff/release/verify_package.sh 解包核对。
"""
import argparse
import hashlib
import os
import sys
import zipfile

SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
KEEP_DOTFILES = {".gitignore"}
# 少了这些就说明目录不对或者工程不完整，直接报错
MUST = (".gitignore", "README.md", "README.zh-CN.md", "00-审核说明.md", "PROJECT_STATE.md", "build.py",
        "dist/manifest.json", "docs/05-验收记录.md", "docs/06-已知限制与待决事项.md", "docs/08-外部审核记录.md",
        "docs/evidence/tests.log", "docs/evidence/mutations.log", "docs/evidence/real-route-check.log",
        "tools/run_checks.sh", "tests/cases.yaml")


def wanted(rel, without_handoff):
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return False
    if rel.startswith("dist/private/") or rel == "source/local.yaml":
        return False
    if without_handoff and (rel == "CLAUDE.md" or parts[0] == "handoff"):
        return False
    base = parts[-1]
    if base.endswith((".pyc", ".pyo")) or ".new-" in base or ".bak-" in base:
        return False
    if base.startswith(".") and rel not in KEEP_DOTFILES:
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ap.add_argument("--without-handoff", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out = os.path.abspath(a.out)
    if out.startswith(root + os.sep):
        sys.exit("输出的 zip 不能放在工程目录里面（下一次打包会把它也收进去）")
    files = []
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/")
            if wanted(rel, a.without_handoff):
                files.append(rel)
            else:
                print("跳过", rel)
    for must in MUST:
        if must not in files:
            sys.exit(f"工程里没有 {must}：目录不对，或者工程不完整")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.write(os.path.join(root, rel), "proxy-rules/" + rel)
    with open(out, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(len(files), "个文件", os.path.getsize(out), "字节")
    print("SHA-256", digest)


if __name__ == "__main__":
    main()

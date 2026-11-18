#!/usr/bin/env python3
"""打交付包：把一个 Git 提交里该交付的文件收进一个 zip。

用法：python3 handoff/release/pack.py <输出的 zip 路径> [--root 工程目录] [--rev 提交] [--without-handoff]
  --root             缺省是这个脚本所在的仓库
  --rev              打哪个提交，缺省 HEAD
  --without-handoff  不收 CLAUDE.md 和 handoff/。r12 的交付包就是这样的（那时还没有这两样）

2026-11-18 起（全项目复核 F05）只从提交里取文件：文件清单是 git ls-tree -r <提交>，内容是提交里的对象，不看工作目录。
以前遍历工作目录，只排除字面上的 dist/private/ 和 source/local.yaml：用 --out 生成到别的目录的私密产物、放在工程里的节点文件，
都会被收进要公开交付的包。现在没提交的东西进不了包；提交里要是有私密产物（任何一层叫 private 的目录、local.yaml），直接报错不打包。
另外要求工作区干净（跟踪的文件没有没提交的改动，也没有没跟踪、没被忽略的文件），这样包、提交、工作目录三者是同一份东西。
所以顺序是先提交、再打包、再用 handoff/release/verify_package.sh 解包核对（它拿包和同一个提交比）。

不收的：__pycache__、*.pyc、生成中断时留下的 .new-* / .bak-*、以“.”开头的文件（.gitignore、.gitattributes 除外）——正常不会被提交，这里再挡一层。
zip 里的顶层目录叫 proxy-rules/。每个文件的修改时间都写成那个提交的时间（UTC），权限照提交里的（644 或 755），
所以同一个提交打出来的 zip 逐字节相同。文件名里有中文：Python 的 zipfile 会自动设 UTF-8 标志。
打完以后打印提交号、文件数、字节数和 SHA-256。
"""
import argparse
import hashlib
import os
import subprocess
import sys
import time
import zipfile

SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
KEEP_DOTFILES = {".gitignore", ".gitattributes"}  # .gitattributes 是 2026-11-18 加的（全项目复核 F06），送审稿打包时发现以前漏收
# 少了这些就说明目录不对或者工程不完整，直接报错
MUST = (".gitignore", "README.md", "README.zh-CN.md", "00-审核说明.md", "PROJECT_STATE.md", "build.py",
        "dist/manifest.json", "docs/05-验收记录.md", "docs/06-已知限制与待决事项.md", "docs/08-外部审核记录.md",
        "docs/evidence/tests.log", "docs/evidence/mutations.log", "docs/evidence/real-route-check.log",
        "tools/run_checks.sh", "tests/cases.yaml")


def forbidden(rel):
    """绝不能进交付包的：私密产物（任何一层叫 private 的目录）、个人覆盖 local.yaml。verify_package.sh 也用同一条判断。"""
    parts = rel.split("/")
    return "private" in parts[:-1] or parts[-1] == "local.yaml"


def wanted(rel, without_handoff):
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return False
    if without_handoff and (rel == "CLAUDE.md" or parts[0] == "handoff"):
        return False
    base = parts[-1]
    if base.endswith((".pyc", ".pyo")) or ".new-" in base or ".bak-" in base:
        return False
    if base.startswith(".") and rel not in KEEP_DOTFILES:
        return False
    return True


def git(root, *args, binary=False):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} 出错：{r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout if binary else r.stdout.decode("utf-8")


def tree_files(root, commit):
    """[(路径, 权限, 对象号)]：提交里的全部文件。子模块、符号链接直接报错（这个仓库没有，出现了就是有问题）。"""
    out = []
    for entry in git(root, "ls-tree", "-r", "-z", "--full-tree", commit, binary=True).split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, obj = meta.decode().split()
        path = path.decode("utf-8")
        if kind != "blob" or mode not in ("100644", "100755"):
            sys.exit(f"提交里的 {path} 不是普通文件（{kind} {mode}），不打包")
        out.append((path, int(mode, 8), obj))
    return sorted(out)


def blob(root, obj):
    return git(root, "cat-file", "blob", obj, binary=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--without-handoff", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    out = os.path.abspath(a.out)
    if out == root or out.startswith(root + os.sep):
        sys.exit("输出的 zip 不能放在工程目录里面")
    dirty = git(root, "status", "--porcelain", "--untracked-files=all")
    if dirty.strip():
        sys.exit("工作区不干净（下面这些没提交、或者没跟踪也没被忽略），先提交或者移走再打包：\n" + dirty)
    commit = git(root, "rev-parse", "--verify", a.rev + "^{commit}").strip()
    when = time.gmtime(int(git(root, "show", "-s", "--format=%ct", commit).strip()))[:6]
    entries = tree_files(root, commit)
    bad = [p for p, _, _ in entries if forbidden(p)]
    if bad:
        sys.exit("提交里有私密产物或 local.yaml，不打包（它们本来就不该被提交）：\n  " + "\n  ".join(bad))
    files = []
    for rel, mode, obj in entries:
        if wanted(rel, a.without_handoff):
            files.append((rel, mode, obj))
        else:
            print("跳过", rel)
    names = {rel for rel, _, _ in files}
    for must in MUST:
        if must not in names:
            sys.exit(f"提交里没有 {must}：提交不对，或者工程不完整")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, mode, obj in files:
            info = zipfile.ZipInfo("proxy-rules/" + rel, date_time=when)
            info.create_system = 3                      # Unix：下面的权限才有意义
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, blob(root, obj), compresslevel=9)
    with open(out, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print("提交", commit)
    print(len(files), "个文件", os.path.getsize(out), "字节")
    print("SHA-256", digest)


if __name__ == "__main__":
    main()

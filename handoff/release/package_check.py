#!/usr/bin/env python3
"""verify_package.sh 用的两件事（2026-11-18，全项目复核 F05–F07）。

  python3 package_check.py unpack <zip> <解到哪个目录> <仓库> <提交> [--without-handoff]
      检查 zip 本身（CRC、每个名字都在 proxy-rules/ 下、不带 .. 和绝对路径），解开，再和提交逐个文件比：
      提交里该交付的（和 pack.py 同一套取舍）包里都要有、内容相同；包里不能多出别的；包里不能有私密产物、local.yaml、
      .git、缓存、生成中断留下的临时文件。有任何一项不符，退出码 1。
  python3 package_check.py may-remove <仓库> <目录>
      这个目录能不能删：它和仓库是同一个、包含仓库、或者在仓库里面，都不能删（退出码 1）；
      判断用解析过符号链接的绝对路径。只做判断，不删任何东西（verify_package.sh 删之前先问它；自测也只调用这一项）。
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack  # noqa: E402  同目录的 pack.py：同一套取舍（wanted、forbidden）、同样读提交

TOP = "proxy-rules/"


def junk(rel):
    """不该出现在包里、但也不算私密的：缓存、版本库、生成中断留下的临时文件、点开头的文件。"""
    parts = rel.split("/")
    base = parts[-1]
    return (any(p in pack.SKIP_DIRS for p in parts) or base.endswith((".pyc", ".pyo")) or ".new-" in base
            or ".bak-" in base or (base.startswith(".") and rel not in pack.KEEP_DOTFILES))


def unpack(zpath, dest, repo, rev, without_handoff):
    problems = []
    try:
        z = zipfile.ZipFile(zpath)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"!!! 打不开 zip：{e}")
        return 1
    with z:
        bad_crc = z.testzip()
        if bad_crc:
            problems.append(f"zip 里 {bad_crc} 的校验和不对")
        # 每一个条目（文件和目录）都查（GPT 审核 r22 送审稿 R22-F03、另一个 AI 的 F04：以前只查文件条目；同名的条目按名字合成一条，
        # 前面那个的内容从来没有和提交比过，换个解压工具解出来的却可能是它）。同名、文件和目录撞名、路径里有空段或“.”的，都不解开
        infos = z.infolist()

        def unsafe(n):
            parts = n.rstrip("/").split("/")
            return (not n.startswith(TOP) or n.startswith("/") or "\\" in n or ".." in parts or "." in parts or "" in parts
                    or ":" in parts[0])
        bad = [i.filename for i in infos if unsafe(i.filename)]
        if bad:
            print("!!! 包里有不在 proxy-rules/ 下、带 .. 或 .、空段、绝对路径的名字，不解开：\n  " + "\n  ".join(bad[:20]))
            return 1
        seen, dups = set(), []
        for i in infos:
            key = i.filename.rstrip("/")
            if key in seen:
                dups.append(i.filename)
            seen.add(key)
        files = [i for i in infos if not i.is_dir()]
        file_names = {i.filename for i in files}
        clash = sorted({p for i in infos for p in ["/".join(i.filename.rstrip("/").split("/")[:k])
                                                   for k in range(1, len(i.filename.rstrip("/").split("/")))] if p in file_names})
        if dups or clash:
            print("!!! 包里有同名的条目，或者一个名字既是文件又是目录，不解开：\n  " + "\n  ".join((dups + clash)[:20]))
            return 1
        os.makedirs(dest)                     # 必须是新目录：不往已有的目录里解
        z.extractall(dest)
        got = {i.filename[len(TOP):]: z.read(i) for i in files}
    print(f"包里 {len(got)} 个文件")
    # 不该有的文件：私密的单独列，其余的也算不通过
    secret = sorted(r for r in got if pack.forbidden(r))
    if secret:
        problems.append("包里有私密产物或 local.yaml：" + "、".join(secret))
    junky = sorted(r for r in got if junk(r) and r not in secret)
    if junky:
        problems.append("包里有缓存、版本库、临时文件或点开头的文件：" + "、".join(junky[:20]))
    # 和提交逐个比（pack.py 同一套取舍）
    commit = pack.git(repo, "rev-parse", "--verify", rev + "^{commit}").strip()
    want = {rel: obj for rel, _, obj in pack.tree_files(repo, commit) if pack.wanted(rel, without_handoff)}
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want) - set(secret) - set(junky))
    differ = sorted(r for r in set(want) & set(got) if got[r] != pack.blob(repo, want[r]))
    for label, xs in (("提交里有、包里没有", missing), ("包里多出来的", extra), ("内容和提交不同", differ)):
        if xs:
            problems.append(f"{label} {len(xs)} 个：" + "、".join(xs[:20]) + ("……" if len(xs) > 20 else ""))
    print(f"提交 {commit}：该交付的 {len(want)} 个文件")
    if problems:
        for p in problems:
            print("!!! " + p)
        return 1
    print("包和提交逐个文件相同；没有私密产物、缓存和临时文件")
    return 0


def inside(child, parent):
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def may_remove(repo, path):
    repo, path = os.path.realpath(repo), os.path.realpath(path)
    if inside(repo, path):
        print(f"不能删 {path}：仓库 {repo} 就是它或者在它里面")
        return 1
    if inside(path, repo):
        print(f"不能删 {path}：它在仓库 {repo} 里面")
        return 1
    print(f"可以删 {path}")
    return 0


def main(argv):
    if len(argv) >= 5 and argv[0] == "unpack":
        return unpack(argv[1], argv[2], argv[3], argv[4], "--without-handoff" in argv[5:])
    if len(argv) == 3 and argv[0] == "may-remove":
        return may_remove(argv[1], argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""打包、验包脚本的自测（2026-11-18，全项目复核 F05–F07 要求的“一个好包、几个坏包作验收”）。不改仓库，也不删仓库以外不是自己建的东西。

做法：在仓库以外新建一个临时目录，把仓库的当前提交（HEAD）克隆一份（工作区干净），用这里的 pack.py 从克隆打一个包，
再拿 verify_package.sh 核对这个好包和由它改出来的一批坏包，看退出码和报出来的原因对不对：
  好包（--skip-tests）                            → 0
  少一个文件、多一个私密产物（dist/private 和别的目录下的 private）、多一个没提交的文件、改了一份产物、
  带一个令牌样子的字符串、名字带 ..、目录条目带 ..、同名的两个条目、一个名字既是文件又是目录
                                                  → 1，说出是哪一项，并且不运行包里的程序（2026-11-19 起，R22-F01）
  和提交相符、但提交本身有问题的包（在克隆里建临时提交、从它打包，用克隆里的验包脚本拿包和那个提交比）：
    提交里的产物和规则源不一致 → 1，报 build.py --check；测试目录只剩一个会失败的测试、一个测试也没有 → 1，报测试那一项；
    测试会在 unittest 的汇总以后打印文字（没设 PYTHONUNBUFFERED）的正确包 → 0、核对通过（R22-F02）
另外：工作目录下已经有一个叫 proxy-rules 的目录（F07 的情形：以前它会被删掉）→ 核对以后它还在；
package_check.py may-remove 对仓库本身、仓库的上一级、仓库里面的目录、指向仓库的符号链接说“不能删”，对无关目录说“可以删”（只判断，不删）；
pack.py 在工作区不干净时拒绝打包。
用法（仓库根目录，先提交）：python3 handoff/release/selftest_package.py    最后一行是“自测通过”，退出码 0。约三四分钟。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.dirname(os.path.dirname(HERE)))
TOP = "proxy-rules/"
results = []


def run(cmd, env=None, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, **kw)
    return r.returncode, r.stdout + r.stderr


def check(label, ok, detail=""):
    results.append((label, ok))
    print(f"[{'符合' if ok else '不符合'}] {label}" + (f"\n    {detail}" if detail and not ok else ""))


def rewrite(src, dst, drop=lambda n: False, add=(), change=None):
    """由好包改出一个坏包：drop 去掉哪些名字，add 加上 (名字, 内容)，change 改一个已有文件 (名字, 函数)。"""
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zi.infolist():
            if drop(info.filename):
                continue
            data = zi.read(info.filename)
            if change and info.filename == change[0]:
                data = change[1](data)
            zo.writestr(info, data)
        for name, data in add:
            zo.writestr(name, data)


def verify(zpath, work, *extra, script_root=None, env=None):
    """script_root：用哪一份工程里的 verify_package.sh（它拿包和那份工程里的提交比）；缺省是这个仓库。"""
    here = os.path.join(script_root, "handoff", "release") if script_root else HERE
    return run(["bash", os.path.join(here, "verify_package.sh"), zpath, work, *extra], env=env)


def fixture_commit(clone, label, edit):
    """在克隆里建一个临时提交（不推送，克隆用完就删）：edit(clone) 改工作区，提交，返回提交号。
    “构建失败”“测试失败”这类情形要从和包相符的提交来，验包才会真的运行它们（GPT 审核 r22 送审稿 R22-F01）。"""
    edit(clone)
    run(["git", "-C", clone, "add", "-A"])
    rc, out = run(["git", "-C", clone, "-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid",
                   "commit", "-q", "-m", label])
    if rc != 0:
        raise SystemExit(f"临时提交失败：{out}")
    return run(["git", "-C", clone, "rev-parse", "HEAD"])[1].strip()


def replace_tests(files):
    """把克隆里的 tests/ 换成只有这几个文件。"""
    def edit(clone):
        shutil.rmtree(os.path.join(clone, "tests"))
        os.makedirs(os.path.join(clone, "tests"))
        for name, text in files.items():
            with open(os.path.join(clone, "tests", name), "w", encoding="utf-8") as f:
                f.write(text)
    return edit


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-package-")
    try:
        clone = os.path.join(tmp, "clone")
        rc, out = run(["git", "clone", "-q", "--no-hardlinks", REPO, clone])
        if rc != 0:
            print(out)
            return 2
        head = run(["git", "-C", REPO, "rev-parse", "HEAD"])[1].strip()
        good = os.path.join(tmp, "good.zip")
        rc, out = run([sys.executable, "-I", os.path.join(HERE, "pack.py"), good, "--root", clone])
        check("pack.py 从干净的克隆打包", rc == 0 and f"提交 {head}" in out, out[-500:])
        if rc != 0:
            return 1
        rc2, out2 = run([sys.executable, "-I", os.path.join(HERE, "pack.py"), os.path.join(tmp, "again.zip"), "--root", clone])
        same = rc2 == 0 and open(good, "rb").read() == open(os.path.join(tmp, "again.zip"), "rb").read()
        check("同一个提交打两次，zip 逐字节相同", same)
        with open(os.path.join(clone, "nodes.yaml"), "w", encoding="utf-8") as f:
            f.write("proxies: []\n")
        rc, out = run([sys.executable, "-I", os.path.join(HERE, "pack.py"), os.path.join(tmp, "dirty.zip"), "--root", clone])
        check("工作区有没跟踪的文件时 pack.py 拒绝打包", rc != 0 and "工作区不干净" in out and not os.path.exists(os.path.join(tmp, "dirty.zip")),
              out[-300:])
        os.remove(os.path.join(clone, "nodes.yaml"))

        work = os.path.join(tmp, "work")
        os.makedirs(os.path.join(work, "proxy-rules"))          # F07：工作目录下已有一个叫 proxy-rules 的目录
        marker = os.path.join(work, "proxy-rules", "别删我.txt")
        with open(marker, "w", encoding="utf-8") as f:
            f.write("x\n")
        rc, out = verify(good, work, "--skip-tests")
        check("好包：退出码 0", rc == 0 and "除了没跑的测试，其余各项都通过" in out and "包和提交逐个文件相同" in out, out[-800:])
        check("工作目录下原有的 proxy-rules 没被删", os.path.exists(marker))
        check("通过以后本轮目录删掉了", [n for n in os.listdir(work) if n.startswith("run-")] == [])

        token = "gh" + "p_" + "A1b2C3d4" * 5        # 令牌的样子，拼出来的，不是真的
        not_run = "没有运行（包和提交对不上，不运行包里的程序"
        cases = [
            ("少一个文件", dict(drop=lambda n: n == TOP + "tools/run_checks.sh"), ["提交里有、包里没有 1 个：tools/run_checks.sh"]),
            ("多一个 dist/private 下的私密产物", dict(add=[(TOP + "dist/private/loon.conf", "x\n")]),
             ["包里有私密产物或 local.yaml：dist/private/loon.conf"]),
            ("多一个别的目录下的 private（--out 生成到别处的私密产物）", dict(add=[(TOP + "export/private/sing-box-1.14.json", "{}\n")]),
             ["包里有私密产物或 local.yaml：export/private/sing-box-1.14.json"]),
            ("多一个 local.yaml", dict(add=[(TOP + "source/local.yaml", "x: 1\n")]), ["包里有私密产物或 local.yaml：source/local.yaml"]),
            ("多一个没提交的文件", dict(add=[(TOP + "nodes.yaml", "proxies: []\n")]), ["包里多出来的 1 个：nodes.yaml"]),
            ("多一个缓存文件", dict(add=[(TOP + "generator/__pycache__/x.pyc", "x")]), ["包里有缓存、版本库、临时文件"]),
            ("改了一份产物", dict(change=(TOP + "dist/loon/loon.conf", lambda b: b + b"# changed\n")),
             ["内容和提交不同 1 个：dist/loon/loon.conf"]),
            ("带一个令牌样子的字符串", dict(add=[(TOP + "docs/x.md", f"token {token}\n")]),
             ["包里多出来的 1 个：docs/x.md", "不通过：扫描有命中：GitHub / API 令牌"]),
            ("名字带 ..", dict(add=[(TOP + "../evil.txt", "x\n")]), ["不解开"]),
            # GPT 审核 r22 送审稿 R22-F03、另一个 AI 的 F04：目录条目也要查；同名条目在解开之前就拒绝
            ("目录条目带 ..", dict(add=[(TOP + "../evil-dir/", "")]), ["不解开"]),
            ("同名的两个条目", dict(add=[(TOP + "README.md", "另一份内容\n")]), ["同名的条目"]),
            ("一个名字既是文件又是目录", dict(add=[(TOP + "build.py/x.txt", "x\n")]), ["既是文件又是目录"]),
        ]
        for i, (label, edit, needles) in enumerate(cases):
            bad = os.path.join(tmp, f"bad{i}.zip")
            rewrite(good, bad, **edit)
            rc, out = verify(bad, work, "--skip-tests")
            check(f"坏包（{label}）：退出码 1，说出原因，不运行包里的程序",
                  rc == 1 and all(n in out for n in needles) and "核对没有通过" in out and not_run in out
                  and "产物与统一源一致" not in out, f"退出码 {rc}；" + out[-600:])

        # 包和提交相符、但提交本身有问题：从克隆里的临时提交打包，用克隆里的验包脚本（它和这里的相同）拿包和那个提交比，
        # 这时才运行包里的 build.py 和测试（R22-F01：以前这几种是改坏的包，验包在比对失败以后照样运行它们）
        base = run(["git", "-C", clone, "rev-parse", "HEAD"])[1].strip()
        failing = "import unittest\n\nclass T(unittest.TestCase):\n    def test_fails(self):\n        self.fail('故意失败')\n"
        prints = ("import unittest\n\nclass T(unittest.TestCase):\n    def test_prints(self):\n"
                  "        print('测试自己打印的一行字')\n        self.assertTrue(True)\n")

        def tamper_dist(c):
            with open(os.path.join(c, "dist", "loon", "loon.conf"), "a", encoding="utf-8") as f:
                f.write("# changed\n")
        no_unbuffered = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
        for label, edit, extra, want_rc, needles in (
                ("提交里的产物和规则源不一致", tamper_dist, ["--skip-tests"], 1, ["包和提交逐个文件相同", "不通过：build.py --check（退出码 1）"]),
                ("测试目录只剩一个会失败的测试", replace_tests({"test_fail.py": failing}), [], 1, ["不通过：测试（退出码 1）"]),
                ("一个测试也没有", replace_tests({"test_nothing.py": "import unittest\n"}), [], 1, ["不通过：测试"]),
                # R22-F02：标准输出有缓冲时，测试自己打印的字排在 unittest 的汇总后面；以前按“最后一行是 OK”判，正确的包也不通过
                ("测试会在汇总以后打印文字的正确包", replace_tests({"test_prints.py": prints}), [], 0, ["核对通过", "测试自己打印的一行字"])):
            sha = fixture_commit(clone, label, edit)
            zpath = os.path.join(tmp, f"fixture-{sha[:7]}.zip")
            rc, out = run([sys.executable, "-I", os.path.join(clone, "handoff", "release", "pack.py"), zpath, "--root", clone])
            if rc == 0:
                rc, out = verify(zpath, work, "--rev", sha, *extra, script_root=clone, env=no_unbuffered)
            check(f"和提交相符的包（{label}）：退出码 {want_rc}", rc == want_rc and all(n in out for n in needles), f"退出码 {rc}；" + out[-600:])
            run(["git", "-C", clone, "reset", "-q", "--hard", base])
        check("坏包核对以后，工作目录下原有的 proxy-rules 还在", os.path.exists(marker))

        # 删目录之前的判断（只判断，不删）
        link = os.path.join(tmp, "link-to-repo")
        os.symlink(REPO, link)
        for label, path, want in (("仓库本身", REPO, 1), ("仓库的上一级", os.path.dirname(REPO), 1),
                                  ("仓库里的 dist", os.path.join(REPO, "dist"), 1), ("指向仓库的符号链接", link, 1),
                                  ("无关的临时目录", os.path.join(tmp, "work"), 0)):
            rc, out = run([sys.executable, "-I", os.path.join(HERE, "package_check.py"), "may-remove", REPO, path])
            check(f"may-remove {label} → {'可以删' if want == 0 else '不能删'}", rc == want, out)
        check("仓库还在", os.path.isfile(os.path.join(REPO, "build.py")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [label for label, ok in results if not ok]
    print()
    print(f"共 {len(results)} 项，" + ("自测通过" if not bad else f"{len(bad)} 项不符合：" + "、".join(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())

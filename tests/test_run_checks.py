"""tools/run_checks.sh 必须把失败传出来（审核 F08：以前测试失败时脚本仍返回 0）。
在临时副本里放一个只含一条测试的 tests/ 目录，分别让它通过和失败，看脚本的退出码。
另外：变异检查工具遇到认不出的参数时什么都不跑（2026-10-05：写错一个选项曾经让它把全部变异跑了起来）。"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.assertTrue(False)\n"
# 这些环境变量会让脚本多跑可选的步骤（官方内核、上游源码、图标仓库……）；临时副本里没有那些工具，所以先去掉
SCRUB = ("MIHOMO_BIN", "SINGBOX_BIN", "SINGBOX112_BIN", "GEODATA_DIR", "MIHOMO_SRC", "SINGBOX_SRC", "DLC_SRC", "BM7_SRC",
         "SRS_DIR", "ICON_REPO")


@unittest.skipUnless(shutil.which("bash"), "需要 bash")
class RunChecksExitCode(unittest.TestCase):
    def run_with(self, test_source):
        d = tempfile.mkdtemp()
        try:
            for name in ("source", "generator"):
                shutil.copytree(os.path.join(ROOT, name), os.path.join(d, name),
                                ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(os.path.join(ROOT, "build.py"), d)
            os.makedirs(os.path.join(d, "tools"))
            shutil.copy(os.path.join(ROOT, "tools", "run_checks.sh"), os.path.join(d, "tools"))
            os.makedirs(os.path.join(d, "tests"))
            with open(os.path.join(d, "tests", "test_only.py"), "w", encoding="utf-8") as f:
                f.write(test_source)
            env = {k: v for k, v in os.environ.items() if k not in SCRUB}
            env["PYTHON"] = sys.executable        # 跑测试的同一个解释器（Windows 的虚拟环境里常常没有 python3）
            r = subprocess.run(["bash", os.path.join(d, "tools", "run_checks.sh")], cwd=d, env=env,
                               capture_output=True, text=True, timeout=300)
            with open(os.path.join(d, "docs", "evidence", "tests.log"), encoding="utf-8") as f:
                log = f.read()
            return r.returncode, r.stdout + r.stderr, log
        finally:
            shutil.rmtree(d)

    def test_failure_propagates(self):
        code, out, log = self.run_with(FAILING)
        self.assertNotEqual(code, 0, out)
        self.assertIn("退出码：1", log)
        self.assertIn("自动测试", out)

    def test_success_returns_zero(self):
        code, out, log = self.run_with(PASSING)
        self.assertEqual(code, 0, out)
        self.assertIn("退出码：0", log)


class OptionalStepsAreListed(unittest.TestCase):
    def test_every_optional_variable_is_scrubbed_here(self):
        """脚本里每个“给了才跑”的环境变量都要列在 SCRUB 里：漏了的话，带着那个变量跑全套检查时，
        上面两项测试的临时副本会去跑一个副本里没有的工具，然后莫名其妙地失败。"""
        with open(os.path.join(ROOT, "tools", "run_checks.sh"), encoding="utf-8") as f:
            script = f.read()
        gates = set(re.findall(r'\[ -n "\$\{([A-Z0-9_]+):-\}" \]', script))
        origins = {v for v in gates if v.endswith("_ORIGIN")}        # 只是写进日志的说明文字，不决定跑不跑
        self.assertIn("ICON_REPO", gates)
        self.assertEqual(sorted(gates - origins - set(SCRUB)), [])


class MutationToolArguments(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_mutations.py"), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_unknown_arguments_run_nothing(self):
        for args in (["--hlep"], ["M999"], ["M1", "--all"]):
            r = self.run_tool(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("认不出的参数", r.stderr, args)
            self.assertEqual(r.stdout, "", f"{args}：不该开始跑任何变异")
        r = self.run_tool("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check-edits", r.stdout)
        self.assertNotIn("[发现]", r.stdout)


class MutationJudge(unittest.TestCase):
    """GPT 审核 r22 送审稿 R22-F16：“发现”要看失败项自己。以前在全部输出里找预设的字：别的测试失败、通过的测试恰好打印了
    这几个字也算；预设的测试名是另一个测试名的开头也算。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_mutations_for_test", os.path.join(ROOT, "tools", "check_mutations.py"))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @staticmethod
    def output(failures, printed=""):
        sep = "=" * 70
        body = "".join(f"{sep}\nFAIL: {m} ({c})\n{'-' * 70}\nTraceback (most recent call last):\nAssertionError: {msg}\n\n"
                       for m, c, msg in failures)
        return printed + body + "-" * 70 + "\nRan 9 tests in 1.000s\n\nFAILED (failures=%d)\n" % len(failures)

    def test_expected_text_must_be_in_a_failure_of_its_own(self):
        out = self.output([("test_other", "test_x.X.test_other", "数量不对")], printed="国外默认\n")
        self.assertFalse(self.mod.judge(out, 1, "国外默认")[0], "预设的字只出现在通过的测试打印的内容里")
        out = self.output([("test_fallback", "test_strict.S.test_fallback", "兜底应交给 国外默认")])
        self.assertTrue(self.mod.judge(out, 1, "国外默认")[0])

    def test_expected_test_name_must_match_exactly(self):
        out = self.output([("test_generated_outputs_pass_the_structure_check",
                            "test_stash.S.test_generated_outputs_pass_the_structure_check", "x")])
        self.assertFalse(self.mod.judge(out, 1, "test_generated_outputs_pass")[0], "只是名字开头相同")
        out = self.output([("test_generated_outputs_pass", "test_simple.Verifier.test_generated_outputs_pass", "x")])
        self.assertTrue(self.mod.judge(out, 1, "test_generated_outputs_pass")[0])
        self.assertTrue(self.mod.judge(out, 1, "test_simple.Verifier.test_generated_outputs_pass")[0])
        self.assertFalse(self.mod.judge(out, 1, "test_strict.StrictOutputs.test_generated_outputs_pass")[0])

    def test_unfinished_or_empty_runs_are_not_caught(self):
        self.assertFalse(self.mod.judge("Traceback (most recent call last):\nImportError: x\n", 1, None)[0])
        self.assertFalse(self.mod.judge("-" * 70 + "\nRan 9 tests in 1.000s\n\nOK\n", 0, None)[0])


if __name__ == "__main__":
    unittest.main()

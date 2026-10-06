"""tools/run_checks.sh 必须把失败传出来（审核 F08：以前测试失败时脚本仍返回 0）。
在临时副本里放一个只含一条测试的 tests/ 目录，分别让它通过和失败，看脚本的退出码。"""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.assertTrue(False)\n"
SCRUB = ("MIHOMO_BIN", "SINGBOX_BIN", "SINGBOX112_BIN", "GEODATA_DIR", "MIHOMO_SRC", "SINGBOX_SRC", "DLC_SRC", "BM7_SRC")


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


if __name__ == "__main__":
    unittest.main()

# r17 出版本时实际运行的命令（2026-10-14，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r17 实际用的命令和文件名，下一版照着改。r17 定稿了两次（04:02 作废，04:20 是交付的这一版）。

1. **定稿前**：`python3 tools/check_real_routes.py … --write-snapshot`（03:29–03:44，重新生成 `tests/data/real_sets.json`；参数和 `tools/run_checks.sh` 里的相同）、`python3 -m unittest discover -s tests`、`python3 build.py --check`、`python3 tools/check_mutations.py --check-edits`。新加的变异只跑相关的测试模块试过（`check_mutations.run_case(名字, 改动, 预期信息, ["test_stash"])` 这样调用，脚本没有留在仓库里）。
2. **第一次定稿（作废）**：04:02:52，代码状态哈希和时间在 `~/proxy-work/freeze17a-state.txt`、`freeze17a-time.txt`；随后开始的变异检查（`~/proxy-work/mut17a/`，跑完 7 类）、全部检查（`checks17a.out`）在 04:10 版本对比查出问题以后停掉（`pgrep -f '[c]heck_mutations\.py' | xargs -r kill`，再停掉 `run_checks.sh` 和它启动的 `check_real_routes.py`、内核进程，删掉 `/tmp/mut-*`）。
3. **第二次定稿**：`bash handoff/release/code_state.sh > ~/proxy-work/freeze17-state.txt`，时间写进 `~/proxy-work/freeze17-time.txt`（`2026-10-14 04:20:38`）。
4. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut17`（04:21 开始；三批：编号除以 3 余 1、余 2、整除）。它写下 `mut-start-<段>.txt`、`code-state-<段>.txt`、三批的日志 `mut-A-…`、`mut-B-…`、`mut-C-…`。
5. **全部检查，第一遍**（第二次定稿以后、和变异检查同时跑）：`bash tools/run_checks.sh > ~/proxy-work/checks17.out`，开始、结束时间记在 `~/proxy-work/checks17-time.txt`；最后一行“全部检查通过。”。跑完以后把这一遍的日志复制到 `~/proxy-work/checks17-logs/`（`finalize.py` 要读第一遍 ICU 的耗时），再 `git checkout -- docs/evidence/*.log` 不留在工作区。
6. **运行环境核对**（04:21）：按 `~/proxy-vendor/SOURCES.txt` 重新算 12 个文件的 SHA-256、看 5 个源码目录的提交号和有没有改动（17 项都对）；Stash 文档包按它自带的 `MANIFEST.txt`（制表符分隔：原网址、文件名、下载时间、大小、SHA-256、完整性）核对 45 个文件（都对）。结果在 `~/proxy-work/vendor17-check.txt`（第一次定稿以后那一遍在 `vendor17a-check.txt`，里面头一次解析 MANIFEST 的格式写错了、显示 0 个，第二遍按制表符解析才对）。
7. **一次性核对**：`python3 handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out`（时间记在 `~/proxy-work/icu17-time.txt`）；`python3 handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out`（时间记在 `~/proxy-work/probe17-time.txt`）。
8. **版本对比**：r16 从 git 取到仓库以外 `mkdir -p ~/proxy-work/r16 && git archive a999d81 | tar -x -C ~/proxy-work/r16`（r7 用以前取出的 `~/proxy-work/r7`），然后（时间记在 `~/proxy-work/cmp17-time.txt`）
   - `python3 tools/compare_versions.py --old ~/proxy-work/r16 --old-label r16 --new-label r17 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r17 --write --out docs/evidence/与r7的对比.md`
9. 变异跑完：在 `~/proxy-work/mut17/segments.json` 里每一段写一项（`{"start": …, "code_state": …, "logs": [三份日志]}`），然后 `python3 handoff/release/r17-as-used/assemble.py ~/proxy-work/mut17`（写出 `mut-result.json`、`mut-lines.txt`）。
10. **变异日志**：`python3 handoff/release/r17-as-used/write_mutlog.py ~/proxy-work/mut17 "2026-10-14 04:20"`（写 `docs/evidence/mutations.log`）。
11. **全部检查，第二遍**（交付的日志是这一遍的）：`bash tools/run_checks.sh > ~/proxy-work/checks17b.out`，开始、结束时间记在 `~/proxy-work/checks17b-time.txt`；最后一行“全部检查通过。”。
12. **数字核对**：`python3 handoff/release/r17-as-used/finalize.py ~/proxy-work/mut17 --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
13. `bash handoff/release/code_state.sh`：与第 3 步记下的相同。
14. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.14-r17.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.14-r17.zip`。

# r15 出版本时实际运行的命令（2026-10-13，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r15 实际用的命令和文件名，下一版照着改。r15 只定稿了一次（03:56）。

1. **定稿前**：`python3 -m unittest discover -s tests`（266 项通过）、`python3 build.py --check`、`python3 tools/check_mutations.py --check-edits`（122/122）。
2. **定稿**：代码状态哈希写进 `~/proxy-work/freeze15-state.txt`（`bash handoff/release/code_state.sh` 的输出），时间写进 `~/proxy-work/freeze15-time.txt`。
3. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut15`（三批：编号除以 3 余 1、余 2、整除）。它写下 `mut-start-<段>.txt`、`code-state-<段>.txt`、三批的日志 `mut-A-…`、`mut-B-…`、`mut-C-…`。
   第一段（03:57 开始）跑完 24 类（M1–M24）时工作环境重新启动（04:24 前后，机器重启，后台进程没了）。05:10 先核对代码状态哈希、Python / PyYAML / ICU 的版本、`~/proxy-vendor/SOURCES.txt` 里 12 个文件的 SHA-256 和 5 个源码目录的提交号（结果在 `~/proxy-work/env15-seg2.txt`），删掉被打断的临时副本（`/tmp/mut-*`），再只带剩下的编号跑第二段：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut15 M25 M26 … M122`（98 类，日志 `mut-?-20261013T051134Z.log`）。
4. **全部检查**（和变异检查同时跑）：`bash tools/run_checks.sh > ~/proxy-work/checks15.out`，开始、结束时间记在 `~/proxy-work/checks15-time.txt`；最后一行“全部检查通过。”。
5. **运行环境核对**：按 `~/proxy-vendor/SOURCES.txt` 重新算 12 个文件的 SHA-256、看 5 个源码目录的提交号和有没有改动（17 项都对），时间记在 `~/proxy-work/vendor15-check.txt`。
6. **一次性核对**：`python3 handoff/notes/r14_review_probes.py > handoff/notes/r14_review_probes.out`（开始、结束时间记在 `~/proxy-work/probe15-time.txt`，每行最后是“日期 时间”）。
7. **版本对比**：r14 从 git 取到仓库以外 `mkdir -p ~/proxy-work/r14 && git archive 3f45668 | tar -x -C ~/proxy-work/r14`（r7 用以前取出的 `~/proxy-work/r7`，来自 `baseline-r7` 分支），然后
   - `python3 tools/compare_versions.py --old ~/proxy-work/r14 --old-label r14 --new-label r15 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r15 --write --out docs/evidence/与r7的对比.md`
8. 变异跑完：在 `~/proxy-work/mut15/segments.json` 里每一段写一项（`{"start": …, "code_state": …, "logs": [三份日志]}`，这一版两段），然后 `python3 handoff/release/r15-as-used/assemble.py ~/proxy-work/mut15`（写出 `mut-result.json`、`mut-lines.txt`）。
9. **变异日志**：`python3 handoff/release/r15-as-used/write_mutlog.py ~/proxy-work/mut15 "2026-10-13 03:56"`（写 `docs/evidence/mutations.log`）。
10. **数字核对**：`python3 handoff/release/r15-as-used/finalize.py ~/proxy-work/mut15 --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
11. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
12. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.13-r15.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.13-r15.zip`。

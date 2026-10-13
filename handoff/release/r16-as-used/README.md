# r16 出版本时实际运行的命令（2026-10-13，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r16 实际用的命令和文件名，下一版照着改。r16 只定稿了一次（11:42）。

1. **定稿前**：`python3 -m unittest discover -s tests`（294 项通过）、`python3 build.py --check`、`python3 tools/check_mutations.py --check-edits`（141/141）。
2. **定稿**：代码状态哈希写进 `~/proxy-work/freeze16-state.txt`（`bash handoff/release/code_state.sh` 的输出），时间写进 `~/proxy-work/freeze16-time.txt`（`2026-10-13 11:42:07`）。
3. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut16`（11:43 开始；三批：编号除以 3 余 1、余 2、整除）。它写下 `mut-start-<段>.txt`、`code-state-<段>.txt`、三批的日志 `mut-A-…`、`mut-B-…`、`mut-C-…`。
   第一段跑完 19 类（M1–M18、M21）以后（最后一条结果 12:07）工作环境停了，15:28 机器重新启动。15:29 先核对代码状态哈希、Python / PyYAML / ICU 的版本、`~/proxy-vendor/SOURCES.txt` 里 12 个文件的 SHA-256 和 5 个源码目录的提交号（结果在 `~/proxy-work/env16-seg2.txt`），删掉被打断的临时副本（`/tmp/mut-*`，变异工具自己建的项目副本），再只带剩下的编号跑第二段：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut16 <剩下的 122 个编号>`（编号列在 `~/proxy-work/mut16/rest-seg2.txt`，日志 `mut-?-20261013T153017Z.log`）。
4. **全部检查，第一遍**（定稿以后、和变异检查同时跑）：`bash tools/run_checks.sh > ~/proxy-work/checks16.out`，开始、结束时间记在 `~/proxy-work/checks16-time.txt`（11:43–12:04）；最后一行“全部检查通过。”。
5. **运行环境核对**：按 `~/proxy-vendor/SOURCES.txt` 重新算 12 个文件的 SHA-256、看 5 个源码目录的提交号和有没有改动（17 项都对）；Stash 文档包按它自带的 `MANIFEST.txt` 核对 45 个文件的 SHA-256（都对）。时间和结果记在 `~/proxy-work/vendor16-check.txt`（11:43）。
6. **一次性核对**：`python3 handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out`（开始、退出码、结束时间记在 `~/proxy-work/probe16-time.txt`，11:45–11:48）。
7. **版本对比**：r15 从 git 取到仓库以外 `mkdir -p ~/proxy-work/r15 && git archive dc90da7 | tar -x -C ~/proxy-work/r15`（r7 用以前取出的 `~/proxy-work/r7`，来自 `baseline-r7` 分支），然后（11:45，时间记在 `~/proxy-work/cmp16-time.txt`）
   - `python3 tools/compare_versions.py --old ~/proxy-work/r15 --old-label r15 --new-label r16 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r16 --write --out docs/evidence/与r7的对比.md`
8. 变异跑完：在 `~/proxy-work/mut16/segments.json` 里每一段写一项（`{"start": …, "code_state": …, "logs": [三份日志]}`，这一版两段），然后 `python3 handoff/release/r16-as-used/assemble.py ~/proxy-work/mut16`（写出 `mut-result.json`、`mut-lines.txt`）。
9. **变异日志**：`python3 handoff/release/r16-as-used/write_mutlog.py ~/proxy-work/mut16 "2026-10-13 11:42"`（写 `docs/evidence/mutations.log`）。
10. **规则证据的记录**：`python3 tools/check_upstream_evidence.py --dlc "$DLC_SRC" --bm7 "$BM7_SRC" --write`（重写 `docs/evidence/upstream-snapshot.json`、`上游规则对照.md`；和 r15 时的比，只有“国内常用网站写进哪些客户端”多了 `stash`——r16 改了 `source/services/misc.yaml` 的 `clients`，以前的记录没有跟着重写）。
11. **全部检查，第二遍**（交付的日志是这一遍的）：`bash tools/run_checks.sh > ~/proxy-work/checks16b.out`，开始、结束时间记在 `~/proxy-work/checks16b-time.txt`；最后一行“全部检查通过。”。
12. **数字核对**：`python3 handoff/release/r16-as-used/finalize.py ~/proxy-work/mut16 --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
13. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
14. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.13-r16.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.13-r16.zip`。

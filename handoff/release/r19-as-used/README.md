# r19 出版本时实际运行的命令（2026-10-17，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境；r18 手工加的 `SINGBOX1143_BIN` 还在，这一版没有用）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r19 实际用的命令和文件名，下一版照着改。r19 是**先审后跑**的：2026-10-15 先推了送审稿（只跑快速检查，见 `docs/08` 第 14 轮“验证”），2026-10-17 GPT 审完送审稿、按意见改完以后定稿一次。

1. **定稿前**：`python3 tools/check_real_routes.py … --write-snapshot`（重新生成 `tests/data/real_sets.json`；参数和 `tools/run_checks.sh` 里的相同；开始、结束时间记在 `~/proxy-work/snap19-time.txt`，输出在 `snap19.out`）、`python3 -m unittest discover -s tests`、`python3 build.py --check`、`python3 tools/check_mutations.py --check-edits`。新加的变异和受影响的旧变异只跑 `test_real_data.Socks5RecorderTool` 试过（`check_mutations.run_case(名字, 改动, 预期信息, ["test_real_data.Socks5RecorderTool"])`）。版本对比先预览过一次（`compare_versions.py` 不带 `--write`，输出没有留）。r18 从 git 取到仓库以外：`mkdir -p ~/proxy-work/r18 && git archive ead8ca8 | tar -x -C ~/proxy-work/r18`。**第一次（08:01–08:16）漏传了 `--srs-origin`、`--bm7-origin`**：快照里 12 处“数据从哪来”的说明成了缺省的写法（核对结果和 r18 的相同），所以按 `run_checks.sh` 的完整参数重新生成了一次；第一次的输出改名留在 `~/proxy-work/snap19-first-wrong-origin.out`。以后生成快照，参数从 `run_checks.sh` 里整段照抄。
2. **定稿**：`bash handoff/release/code_state.sh > ~/proxy-work/freeze19-state.txt`，时间写进 `~/proxy-work/freeze19-time.txt`。
3. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut19`（三批：编号除以 3 余 1、余 2、整除）。
4. **全部检查，第一遍**（定稿以后、和变异检查同时跑）：`bash tools/run_checks.sh > ~/proxy-work/checks19.out`，开始、结束时间记在 `~/proxy-work/checks19-time.txt`。跑完把日志复制到 `~/proxy-work/checks19-logs/`，再 `git checkout -- docs/evidence/*.log`。
5. **全部测试在 Python 3.12、3.11 上**（r19 起）：一个后台任务依次跑 `python3.12 -m unittest discover -s tests > ~/proxy-work/py312-19.out`、`python3.11 … > ~/proxy-work/py311-19.out`；`~/proxy-work/py19-time.txt` 七行：“开始 …”、`python3.12 --version`、“exit 0”、“中间 …”、`python3.11 --version`、“exit 0”、“结束 …”。
6. **运行环境核对**：`python3 handoff/release/r19-as-used/vendor_check.py > ~/proxy-work/vendor19-check.txt`。
7. **一次性核对和版本对比**（一个后台任务，按顺序；每一项的时间文件三行：“开始 …”“exit 0”“结束 …”）：
   - `icu19-time.txt`：`python3 handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out`
   - `probe19-time.txt`：`python3 handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out`
   - 版本对比（`cmp19-time.txt`）：`python3 tools/compare_versions.py --old ~/proxy-work/r18 --old-label r18 --new-label r19 --write`，再 `--old ~/proxy-work/r7 --old-label r7 --new-label r19 --write --out docs/evidence/与r7的对比.md`
   - r18 的两项一次性核对（`r18_close_race_probe.py`、`r18_singbox_1143_probes.py`）这一版没有重跑。
8. 变异跑完：`~/proxy-work/mut19/segments.json`（每一段一项），`python3 handoff/release/r19-as-used/assemble.py ~/proxy-work/mut19`，再 `python3 handoff/release/r19-as-used/write_mutlog.py ~/proxy-work/mut19 "<定稿时间>"`。
9. **全部检查，第二遍**（交付的日志是这一遍的）：`bash tools/run_checks.sh > ~/proxy-work/checks19b.out`，时间记在 `~/proxy-work/checks19b-time.txt`。
10. **数字核对**：`python3 handoff/release/r19-as-used/finalize.py ~/proxy-work/mut19 --dry`，再不带 `--dry` 跑（最后打印“核对通过”）。
11. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
12. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.17-r19.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.17-r19.zip`。

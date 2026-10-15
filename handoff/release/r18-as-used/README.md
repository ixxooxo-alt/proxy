# r18 出版本时实际运行的命令（2026-10-15，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境；这一版手工加了 `SINGBOX1143_BIN`，见 `handoff/README.md` 第 15 节）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r18 实际用的命令和文件名，下一版照着改。r18 定稿一次。

1. **定稿前**：`python3 tools/check_real_routes.py … --write-snapshot`（01:52–02:08，重新生成 `tests/data/real_sets.json`；参数和 `tools/run_checks.sh` 里的相同；开始、结束时间记在 `~/proxy-work/snap18-time.txt`，输出在 `snap18.out`）、`python3 -m unittest discover -s tests`、`python3 build.py --check`、`python3 tools/check_mutations.py --check-edits`。新加的变异和受影响的旧变异只跑 `test_real_data.Socks5RecorderTool` 试过（`check_mutations.run_case(名字, 改动, 预期信息, ["test_real_data.Socks5RecorderTool"])` 这样调用，脚本没有留在仓库里）。定稿前另做过一遍 1.14.3 的核对和版本对比的预览（输出没有留，定稿以后都重跑了）；提交 `61bc038`（WIP）推到会话分支。
2. **定稿**：`bash handoff/release/code_state.sh > ~/proxy-work/freeze18-state.txt`，时间写进 `~/proxy-work/freeze18-time.txt`（`2026-10-15 02:14:10`）。
3. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut18`（02:15 开始；三批：编号除以 3 余 1、余 2、整除）。它写下 `mut-start-<段>.txt`、`code-state-<段>.txt`、三批的日志 `mut-A-…`、`mut-B-…`、`mut-C-…`。
   **中间工作环境停了一次**：第一段（`…T021521Z`）跑完 127 类时（04:40 前后）机器停了，06:09 重新启动。先 `bash handoff/release/code_state.sh`（与定稿时相同）、看 Python / PyYAML / ICU 的版本、`python3 handoff/release/r18-as-used/vendor_check.py > ~/proxy-work/vendor18b-check.txt`（都对），删掉上一段留在 `/tmp` 的 `mut-*` 副本，从三份日志里找出还没有结果的编号（写在 `~/proxy-work/mut18/remaining-seg2.txt`：M128–M162，35 个），再 `MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut18 $(cat ~/proxy-work/mut18/remaining-seg2.txt)`（第二段 `…T061236Z`，06:12 开始）。
4. **全部检查，第一遍**（定稿以后、和变异检查同时跑）：`bash tools/run_checks.sh > ~/proxy-work/checks18.out`，开始、结束时间记在 `~/proxy-work/checks18-time.txt`；最后一行“全部检查通过。”。跑完以后把这一遍的日志复制到 `~/proxy-work/checks18-logs/`（`finalize.py` 要读第一遍 ICU 的耗时），再 `git checkout -- docs/evidence/*.log` 不留在工作区。
5. **运行环境核对**（02:15）：`python3 handoff/release/r18-as-used/vendor_check.py > ~/proxy-work/vendor18-check.txt`——按 `~/proxy-vendor/SOURCES.txt` 重新算 13 个文件的 SHA-256（r17 是 12 个，多的是 sing-box 1.14.3）、看 5 个源码目录的提交号和有没有改动；Stash 文档包按它自带的 `MANIFEST.txt` 核对 45 个文件。
6. **一次性核对和版本对比**（按顺序，一个后台任务；命令照下面）：每一项的开始、退出码、结束记在 `~/proxy-work/<名字>-time.txt`（三行：“开始 …”“exit 0”“结束 …”）。
   - `race18-time.txt`：`python3 handoff/notes/r18_close_race_probe.py ~/proxy-work/r17 > handoff/notes/r18_close_race_probe.out`（r17 从 git 取到仓库以外：`mkdir -p ~/proxy-work/r17 && git archive 88a1e38 | tar -x -C ~/proxy-work/r17`）
   - `icu18-time.txt`：`python3 handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out`
   - `probe18-time.txt`：`python3 handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out`
   - `p1143-time.txt`：`python3 handoff/notes/r18_singbox_1143_probes.py > handoff/notes/r18_singbox_1143_probes.out`（它自己另写 `handoff/notes/r18_singbox_1143_full.out`）
   - 版本对比（时间记在 `~/proxy-work/cmp18-time.txt`）：
     - `python3 tools/compare_versions.py --old ~/proxy-work/r17 --old-label r17 --new-label r18 --write`
     - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r18 --write --out docs/evidence/与r7的对比.md`
7. 变异跑完：在 `~/proxy-work/mut18/segments.json` 里每一段写一项（这一版两段）（`{"start": …, "code_state": …, "logs": [三份日志]}`），然后 `python3 handoff/release/r18-as-used/assemble.py ~/proxy-work/mut18`（写出 `mut-result.json`、`mut-lines.txt`）。
8. **变异日志**：`python3 handoff/release/r18-as-used/write_mutlog.py ~/proxy-work/mut18 "2026-10-15 02:14"`（写 `docs/evidence/mutations.log`）。
9. **全部检查，第二遍**（交付的日志是这一遍的）：`bash tools/run_checks.sh > ~/proxy-work/checks18b.out`，开始、结束时间记在 `~/proxy-work/checks18b-time.txt`；最后一行“全部检查通过。”。
10. **数字核对**：`python3 handoff/release/r18-as-used/finalize.py ~/proxy-work/mut18 --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
11. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
12. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.15-r18.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.15-r18.zip`。

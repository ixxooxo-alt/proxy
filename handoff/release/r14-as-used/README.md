# r14 出版本时实际运行的命令（2026-10-07，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r14 实际用的命令和文件名，下一版照着改。

1. **定稿**（02:05:22）：代码状态哈希写进 `~/proxy-work/freeze14-state.txt`（`bash handoff/release/code_state.sh` 的输出），时间写进 `~/proxy-work/freeze14-time.txt`。
2. **变异检查**（02:05:45 开始）：`bash handoff/release/run_mutations.sh ~/proxy-work/mut14`。它写下 `mut-start-20261007T020545Z.txt`、`code-state-20261007T020545Z.txt`、两批的日志 `mut-A-…`、`mut-B-…`。
3. 变异跑完：在 `~/proxy-work/mut14/segments.json` 里写一段（这次没有中断）：
   `[{"start": "mut-start-20261007T020545Z.txt", "code_state": "code-state-20261007T020545Z.txt", "logs": ["mut-A-20261007T020545Z.log", "mut-B-20261007T020545Z.log"]}]`，
   然后 `python3 handoff/release/r14-as-used/assemble.py ~/proxy-work/mut14`（写出 `mut-result.json`、`mut-lines.txt`）。
4. **全部检查**：`bash tools/run_checks.sh`，最后一行“全部检查通过。”。
5. **版本对比**：r13 从 git 取到仓库以外 `mkdir -p ~/proxy-work/r13 && git archive bf42e8b | tar -x -C ~/proxy-work/r13`（r7 用以前取出的 `~/proxy-work/r7`，来自 `baseline-r7` 分支），然后
   - `python3 tools/compare_versions.py --old ~/proxy-work/r13 --old-label r13 --new-label r14 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r14 --write --out docs/evidence/与r7的对比.md`
6. **一次性核对**（`handoff/notes/`，不参与测试）：
   - `python3 handoff/notes/r13_review_probes.py ~/proxy-work/r13/dist/mihomo/mihomo-core.yaml ~/proxy-work/r13/dist/sing-box/sing-box-1.14.json > handoff/notes/r13_review_probes.r13.out`（GPT 审的 r13 的配置）
   - `python3 handoff/notes/r13_review_probes.py > handoff/notes/r13_review_probes.out`（这一版的配置）
   - `python3 handoff/notes/r13_strict_routes.py > handoff/notes/r13_strict_routes.out`
   - `python3 handoff/notes/r14_policy_order.py > handoff/notes/r14_policy_order.out`
7. **变异日志**：`python3 handoff/release/r14-as-used/write_mutlog.py ~/proxy-work/mut14 "2026-10-07 02:05"`（写 `docs/evidence/mutations.log`）。
8. **数字核对**：`python3 handoff/release/r14-as-used/finalize.py ~/proxy-work/mut14 --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
9. `bash handoff/release/code_state.sh`：与第 1 步记下的相同。
10. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.07-r14.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.07-r14.zip`。

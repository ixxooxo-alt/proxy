# r14 出版本时实际运行的命令（2026-10-07，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r14 实际用的命令和文件名，下一版照着改。

r14 前后定稿过三次，只有最后一次的结果算数（`docs/05`“已验证的事实”开头）：

- 02:05 定稿的是只做了审核那一半的生成器 1.6.0（文件 `~/proxy-work/freeze14-*.txt`、变异日志 `~/proxy-work/mut14/`）。变异检查跑到一半，使用者让我先把待决事项一次定完，那一版没有交付。
- 06:20 定稿的是 1.7.0（`freeze14b-*.txt`、`mut14b/`）。变异检查开始几分钟后，我在版本对比报告里发现只换了先后的条目不写改了什么（变异 M116 那一处），停下来改 `tools/compare_versions.py`。
- 06:29 定稿的是交付的这一版（`freeze14c-*.txt`、`mut14c/`），下面的命令都是这一次的。

1. **定稿**：代码状态哈希写进 `~/proxy-work/freeze14c-state.txt`（`bash handoff/release/code_state.sh` 的输出），时间写进 `~/proxy-work/freeze14c-time.txt`。
2. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut14c`（三批：编号除以 3 余 1、余 2、整除）。它写下 `mut-start-<段>.txt`、`code-state-<段>.txt`、三批的日志 `mut-A-…`、`mut-B-…`、`mut-C-…`。
3. 变异跑完：在 `~/proxy-work/mut14c/segments.json` 里每一段写一项（`{"start": …, "code_state": …, "logs": [三份日志]}`），然后 `python3 handoff/release/r14-as-used/assemble.py ~/proxy-work/mut14c`（写出 `mut-result.json`、`mut-lines.txt`）。
4. **全部检查**：`bash tools/run_checks.sh`，最后一行“全部检查通过。”。
5. **版本对比**：r13 从 git 取到仓库以外 `mkdir -p ~/proxy-work/r13 && git archive bf42e8b | tar -x -C ~/proxy-work/r13`（r7 用以前取出的 `~/proxy-work/r7`，来自 `baseline-r7` 分支），然后
   - `python3 tools/compare_versions.py --old ~/proxy-work/r13 --old-label r13 --new-label r14 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r14 --write --out docs/evidence/与r7的对比.md`
6. **一次性核对**（`handoff/notes/`，不参与测试）：
   - `python3 handoff/notes/r13_review_probes.py ~/proxy-work/r13/dist/mihomo/mihomo-core.yaml ~/proxy-work/r13/dist/sing-box/sing-box-1.14.json > handoff/notes/r13_review_probes.r13.out`（GPT 审的 r13 的配置）
   - `python3 handoff/notes/r13_review_probes.py > handoff/notes/r13_review_probes.out`（这一版的配置）
   - `python3 handoff/notes/r13_strict_routes.py ~/proxy-work/r13/dist > handoff/notes/r13_strict_routes.r13.out`（r13 的两份严格版和它们引用的自有规则文件）
   - `python3 handoff/notes/r13_strict_routes.py > handoff/notes/r13_strict_routes.out`（这一版）
   - `python3 handoff/notes/r14_policy_order.py > handoff/notes/r14_policy_order.out`
7. **变异日志**：`python3 handoff/release/r14-as-used/write_mutlog.py ~/proxy-work/mut14c "<第 1 步记下的定稿时间，到分钟>"`（写 `docs/evidence/mutations.log`）。
8. **数字核对**：`python3 handoff/release/r14-as-used/finalize.py ~/proxy-work/mut14c --dry`，看清要替换的内容，再不带 `--dry` 跑一遍（填占位符，最后打印“核对通过”）。
9. `bash handoff/release/code_state.sh`：与第 1 步记下的相同。
10. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.07-r14.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.07-r14.zip`。

# r21 出版本时实际运行的命令（2026-10-31，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r21 实际用的命令和文件名，下一版照着改。r21 也是**先审后跑**的：2026-10-31 先推了送审稿（代码 `1366d17`、文档 `c29d633`，只跑快速检查，见 `handoff/notes/r21_draft/`），同一天 GPT 审完（审核 PR #8）、按意见改完以后定稿一次。

0. **对照用的旧版本**（都在仓库以外）：
   - r20：`~/proxy-work/r20`，`git archive f45eb89 | tar -x -C ~/proxy-work/r20` 取的（送审稿时）。`f45eb89` 是只改了文档的 r20b，代码和产物与 r20 正式版 `aeb3d4d` 相同。版本对比和 `r21_private_vs_r20.py` 用这个目录；`finalize.py` 拿 r20 的日志、快照比时用 `git show f45eb89:…`。
   - r7：`~/proxy-work/r7`（以前各版就有的 `git worktree`，`f8bfa92`），版本对比的第二份。
1. **定稿前**（16:28–16:57）：
   - `python3 -B handoff/notes/r21_private_vs_r20.py ~/proxy-work/r20 <仓库> <临时目录>` 试跑过一次（PR #8 处理完以后，输出没有留）。
   - M177、M3 的预设关键字改了，`tests/test_simple.py` 的 `SameAsFullOutsideGroups.test_mihomo` 补了两句断言（`docs/08` 第 19 轮的补记）；`python3 -B tools/check_mutations.py --check-edits`（210/210）；全部测试 `python3 -B -m unittest discover -s tests`（16:39 开始，348 项通过）；同时试跑 `python3 -B tools/check_mutations.py M3 M177`、`… M176 M210`（16:39 起）：M3、M176、M177 被发现、输出含预设信息，**M210 没被发现**（348 项全部通过：规则源和写盘前检查拒绝时 `build.py` 都返回 2，预设的生成流程测试分不出来）。
   - 版本号递增（生成器 1.12.1、简易版 2026.10.31-2），`python3 -B build.py && python3 -B build.py --check`；`test_s*.py`、`test_build_pipeline.py` 先跑了一遍（132、12 项通过）。
   - 加了 `tests/test_stash.py` 的 `test_select_interval_in_the_source_must_be_negative`，M210 的预设改成它；全部测试重跑（16:50 开始，349 项通过），同时 `python3 -B tools/check_mutations.py M210`（被发现，输出含预设信息）。这几次的输出在会话的临时目录，没有留。
   - 版本对比预览过一次（`compare_versions.py` 不带 `--write`，版本号递增以前），报告里没有“未知的正则”，也没有说不出改了什么的“改动”。
   - `tests/data/real_sets.json` **没有**重新生成：mihomo、sing-box 完整版的规则和 DNS 段没有变（`finalize.py` 核对它和 r20 的逐字节相同）。
   - 定稿前的状态提交成 `cf1da85`（推到了会话分支）。
2. **定稿**（16:57:23）：`python3 -B build.py --check && date -u +"%Y-%m-%d %H:%M:%S" > ~/proxy-work/freeze21-time.txt && bash handoff/release/code_state.sh > ~/proxy-work/freeze21-state.txt`。代码状态 `eca139fa64d9b4ea4e2d286a358b4c1ca616d700e12eeb4c4631704068a7c32a`。
3. **变异检查**：`MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut21`（17:01:20 开始，段名 `20261031T170120Z`；三批：编号除以 3 余 1、余 2、整除，各 70 类）。
4. **和变异检查同时跑的一串**：`nohup bash handoff/release/r21-as-used/chain21.sh > ~/proxy-work/chain21.log 2>&1 &`（17:01 启动），按顺序：全部检查第一遍（`checks21.out`、`checks21-time.txt`，日志复制到 `checks21-logs/` 以后 `git checkout -- docs/evidence/*.log`）；全部测试在 Python 3.12、3.11 上（`py312-21.out`、`py311-21.out`、`py21-time.txt`）；运行环境核对（`vendor21-check.txt`）；一次性核对（`icu21-time.txt`：`r17_stash_filters_icu.py`；`probe21-time.txt`：`r15_review_probes.py`；`pv21-time.txt`：`r21_private_vs_r20.py ~/proxy-work/r20 <仓库> ~/proxy-work/pv21`，输出写到 `handoff/notes/r21_private_vs_r20.out`）；版本对比（`cmp21-time.txt`：和 r20、r7 比，`--write`）；全部做完写 `chain21-done.txt`。r18 的两项一次性核对这一版没有重跑；r20 的 `r20_full_private_same.py` 这一版不成立（Stash 完整版变了），没有跑。
5. 第 5、6 步：`nohup bash handoff/release/r21-as-used/after21.sh 20261031T170120Z "2026-10-31 16:57" > ~/proxy-work/after21.log 2>&1 &`（17:01 启动），等三批变异日志都写出“合计 N/N 被发现”再接着跑（有一批没正常结束或有没被发现的就停下），汇总（`segments.json`、`assemble.py`、`write_mutlog.py`），再等 `chain21-done.txt` 出现以后跑第二遍全部检查（`checks21b.out`、`checks21b-time.txt`）。
   实际：变异 22:30:34 跑完（一段，三批各 70 类，都是“合计 70/70 被发现”），`after21.sh` 22:30:38 接着汇总，第二遍全部检查 22:30–22:49，“全部检查通过。”。汇总里有一类“未见预期信息”：M182（sing-box 的 `idle_timeout` 照旧 30 分钟），这一版“境外DNS”的间隔改成 600 秒以后它不改变产物，只由 `test_duration_parser` 发现；关键字留到下一版改代码时再改（`handoff/README.md` 第 18 节第 8 条）。
6. **数字核对**：`python3 handoff/release/r21-as-used/finalize.py ~/proxy-work/mut21 --dry`，再不带 `--dry` 跑（最后打印“核对通过”）。跑之前按日志改了几处出版脚本（都在 `handoff/`，不算代码，代码状态不变）：
   - `write_mutlog.py` 里写的版本还是送审稿的（生成器 1.12.0、简易版 2026.10.31-1），改对，并补上 M182 的说明，重写了 `mutations.log`；
   - `finalize.py`：`official-check.log` 和 r20 比时去掉内核日志的时间戳和临时目录名，`real-route-check.log` 去掉那一行开头的统一源版本（这一版变了）；版本对比报告每份只列前 40 条改动，按汇总行核对；`not_seen` 是 `['M182']`。`finalize.py` 的前三处是 17:35 前后用第一遍的日志预检（`chain21.sh` 跑完以后）时查出来的，`write_mutlog.py` 的版本和 M182 是 22:50 变异跑完以后看日志查出来的。
7. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
8. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.3x-r21.zip`（日期按打包那天），再 `bash handoff/release/verify_package.sh` 同一个包。

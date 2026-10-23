# r20 出版本时实际运行的命令（2026-10-23，UTC）

都在仓库根目录、`source ~/proxy-vendor/env.sh` 之后运行（`handoff/setup_env.sh` 写的环境）。工作文件放在仓库以外的 `~/proxy-work/`。
步骤的道理见上一级的 `README.md`；这里只记 r20 实际用的命令和文件名，下一版照着改。r20 也是**先审后跑**的：2026-10-21 先推了简易版的送审稿 `4d3349d`（只跑快速检查，见 `docs/10` 第八节），2026-10-23 GPT 审完（审核 PR #6）、按意见改完以后定稿一次。

0. **对照用的旧版本**（都在仓库以外）：
   - r19：`~/proxy-work/r19`。2026-10-21 写送审稿时 `git fetch origin main` 以后 `git archive origin/main | tar -x -C ~/proxy-work/r19` 取的。当时 `main` 是 `85eaa7c`：r19 正式版 `628ed8a` 之后只多了文档和使用者加的宣传动图，`git diff --stat 628ed8a 85eaa7c -- build.py generator source tests tools dist .gitignore` 是空的；2026-10-23 又用 `diff -rq` 核对过这个目录和 `git archive 85eaa7c` 的内容相同。版本对比和 `r20_full_private_same.py` 用这个目录；`finalize.py` 拿 r19 的日志、快照比时用 `git show 628ed8a:…`。
   - 送审稿：`git worktree add --detach ~/proxy-work/r20-draft 4d3349d`（只有 `r20_full_private_same.py` 用）。
   - r7：`~/proxy-work/r7`（以前各版就有的 `git worktree`，`f8bfa92`），版本对比的第二份。
1. **定稿前**（12:38–13:02）：`python3 -B build.py && python3 -B build.py --check`；`python3 -B -m unittest discover -s tests -p test_simple.py`；全部测试 `python3 -B -m unittest discover -s tests`（12:55 开始，345 项通过，输出在会话的临时目录，没有留）。新加和改写的变异（M195、M197–M202）分三个后台任务试跑：`python3 -B tools/check_mutations.py M195 M197 M198`、`… M199 M200`、`… M201 M202`（12:46 起，7 类都被发现）。试跑时最后几处改动（版本号、`NodesPerLayout` 改用临时目录里的规则源）还在做，所以这几次只作参考，正式结果是第 3 步的。`r20_full_private_same.py` 试跑过一次，版本对比预览过一次（`compare_versions.py` 不带 `--write`），输出都没有留。完整版的配置和 r19 逐字节相同，所以 `tests/data/real_sets.json` **没有**重新生成（`finalize.py` 核对它和 r19 的逐字节相同）。
2. **定稿**（13:02:54）：`python3 -B build.py --check && date -u +"%Y-%m-%d %H:%M:%S" > ~/proxy-work/freeze20-time.txt && bash handoff/release/code_state.sh > ~/proxy-work/freeze20-state.txt`。
3. **变异检查**：紧接着 `MUT_BATCHES=3 bash handoff/release/run_mutations.sh ~/proxy-work/mut20`（13:06 开始；三批：编号除以 3 余 1、余 2、整除，68、67、67 类）。
4. **和变异检查同时跑的一串**（第 4–7 步写成了一个脚本：`bash ~/proxy-work/chain20.sh`，后台跑；同目录的 `chain20.sh` 是它的副本），按顺序：
   - 全部检查第一遍：`bash tools/run_checks.sh > ~/proxy-work/checks20.out`（时间在 `checks20-time.txt`；`.out` 最后补一行 `exit <退出码>`）。跑完把日志复制到 `~/proxy-work/checks20-logs/`，再 `git checkout -- docs/evidence/*.log`。
   - 全部测试在 Python 3.12、3.11 上：`python3.12 -B -m unittest discover -s tests > ~/proxy-work/py312-20.out`、`python3.11 … > ~/proxy-work/py311-20.out`；`~/proxy-work/py20-time.txt` 七行（“开始 …”、`python3.12 --version`、“exit 0”、“中间 …”、`python3.11 --version`、“exit 0”、“结束 …”）。
   - 运行环境核对：`python3 -B handoff/release/r20-as-used/vendor_check.py > ~/proxy-work/vendor20-check.txt`。
   - 一次性核对（每一项的时间文件三行：“开始 …”“exit 0”“结束 …”）：`icu20-time.txt` 是 `python3 -B handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out`；`probe20-time.txt` 是 `python3 -B handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out`；`fp20-time.txt` 是 `python3 -B handoff/notes/r20_full_private_same.py ~/proxy-work/r19 ~/proxy-work/r20-draft <仓库> ~/proxy-work/fp20 > handoff/notes/r20_full_private_same.out`（这一版新加的，R20-F02 的同类自查）。r18 的两项一次性核对（`r18_close_race_probe.py`、`r18_singbox_1143_probes.py`）这一版没有重跑。
   - 版本对比（`cmp20-time.txt`）：`python3 -B tools/compare_versions.py --old ~/proxy-work/r19 --old-label r19 --new-label r20 --write`，再 `--old ~/proxy-work/r7 --old-label r7 --new-label r20 --write --out docs/evidence/与r7的对比.md`。
   - 全部做完写 `~/proxy-work/chain20-done.txt`。
5. 第 5、6 步也写成了脚本：`nohup bash handoff/release/r20-as-used/after20.sh > ~/proxy-work/after20.log 2>&1 &`（13:45 前后启动），等三批变异日志都写出“合计 N/N 被发现”再接着跑，有一批没正常结束或有没被发现的就停下。
   实际：变异 19:00:15 跑完（一段，三批 68、67、67 类都是“合计 N/N 被发现”），`after20.sh` 19:00:36 接着汇总，第二遍全部检查 19:00:36–19:21:46，“全部检查通过。”。
   变异跑完：`~/proxy-work/mut20/segments.json`（每一段一项），`python3 handoff/release/r20-as-used/assemble.py ~/proxy-work/mut20`，再 `python3 handoff/release/r20-as-used/write_mutlog.py ~/proxy-work/mut20 "2026-10-23 13:02"`。
6. **全部检查，第二遍**（交付的日志是这一遍的）：`bash tools/run_checks.sh > ~/proxy-work/checks20b.out`，`.out` 最后补一行 `exit <退出码>`，开始、结束时间记在 `~/proxy-work/checks20b-time.txt`（两行）。
7. **数字核对**：`python3 handoff/release/r20-as-used/finalize.py ~/proxy-work/mut20 --dry`，再不带 `--dry` 跑（最后打印“核对通过”）。
   跑之前按变异日志改了两处出版脚本（都在 `handoff/`，不算代码，代码状态不变）：
   - **M16 只跑了 343 项**（以前是全部）：这一版起，节点和组同名又不改名时，sing-box 生成时直接报出站标签重名，简易版带节点的测试类 `SingboxWithNodes` 初始化失败（2 项没跑），另有 3 项失败。在临时副本上复现过（报错“sing-box 出站标签重名：['DIRECT', '日本']”）。`write_mutlog.py` 原来把没跑满的几类都说成“统一源校验直接拒绝”，对 M16 不对，改成分开写，重写了 `mutations.log`；`finalize.py` 的 `PARTIAL_EXPECTED` 加上 M16。
   - **M177 记“未见预期信息”**：它预设的关键字是 `test_mihomo`（送审稿时 M171–M196 只核对过改动能套上，没有真跑），实际由写盘前检查（“GEO 数据的下载主机 … 没有交给 境外DNS”）和 `test_simple` 的 `test_routing_digest_equals_the_full_one_apart_from_the_dns_path` 发现，失败项是对的。关键字在 `tools/check_mutations.py` 里，改它就要重新定稿，留到下一版改代码时一起改；写进了 `docs/05`。
8. `bash handoff/release/code_state.sh`：与第 2 步记下的相同。
9. **打包**：`python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-2026.10.23-r20.zip`，再 `bash handoff/release/verify_package.sh ~/proxy-work/proxy-rules-review-2026.10.23-r20.zip`。

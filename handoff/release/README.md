# 出一版的步骤

这是 r10–r12 实际用的做法，照着做，下一版的证据和前几版就接得上。命令都在仓库根目录运行；先 `source` 过 `handoff/setup_env.sh` 写出的 `env.sh`。
工作文件（变异日志、旧版本的检出、打出来的包）放在仓库以外，下面用 `~/proxy-work/`。

## 一、改

1. 改 `source/`（规则、分组、DNS），需要时改 `generator/`、`tests/`、`tools/`。
   - 版本号：`source/project.yaml` 的 `source_version`（改了规则数据就递增，`年.月.日-序号`）；`build.py` 的 `GENERATOR_VERSION`（改了生成器就递增）。
   - 交付包 / 分支用 `rNN` 编号，接着上一版往下排（上一版是 r12）。
2. `python3 build.py`，`python3 -m unittest discover -s tests`。
3. 改了规则、DNS、出站，或者换了上游数据：重新生成快照
   `python3 tools/check_real_routes.py --mihomo "$MIHOMO_BIN" --singbox "$SINGBOX_BIN" --singbox-112 "$SINGBOX112_BIN" --geodata-dir "$GEODATA_DIR" --srs-dir "$SRS_DIR" --bm7 "$BM7_SRC" --dlc "$DLC_SRC" --geodata-origin "$GEODATA_ORIGIN" --srs-origin "$SRS_ORIGIN" --bm7-origin "$BM7_ORIGIN" --write-snapshot`
   （约 5–7 分钟）。不重新生成的话，“记录对应现在的配置”那两项测试会失败——这是故意的：`tests/data/real_sets.json` 里是官方内核的实际结果，配置变了它就过期。有不符合时工具拒绝写快照，先看清楚是配置错了还是期望该改。
   其他会写文件的工具：`tools/check_upstream_evidence.py --dlc … --bm7 … --write`（规则证据变了）、`tools/update_cn_list.py --dlc …`（换了 domain-list-community 快照）、`tools/check_cursor_report.py --write`。
4. 新行为配测试；每修一类错，在 `tools/check_mutations.py` 里加一个把它改回去的变异（`Mnn`），`python3 tools/check_mutations.py --check-edits` 确认每个变异都还套得上当前代码。
5. 写文档（见 `CLAUDE.md` 里各文件的分工）。还没跑出来的数字先写占位符 `⟦名字⟧`，最后由核对脚本填，不要先估一个数写上去。

## 二、定稿，跑全部检查

6. **定稿**：代码不再改了，记下代码状态哈希：`bash handoff/release/code_state.sh`。从这里到打包，`build.py`、`generator/`、`source/`、`tests/`、`tools/`、`.gitignore` 一个字都不能动；动了就重新定稿，后面全部重来（r12 定稿了三次）。
7. **变异检查**：`bash handoff/release/run_mutations.sh ~/proxy-work/mut`（后台两批并行，r12 的 98 类约 80 分钟）。等它的时候可以写文档。
   云端机器闲置会被回收，后台进程跟着没了、日志还在：把剩下的编号再跑一段（脚本开头有说明）。
8. 变异跑完以后：`bash tools/run_checks.sh`（7–10 分钟；重写 `docs/evidence/*.log`）。最后一行必须是“全部检查通过。”。
9. **版本对比**（旧版本从 git 里检出来，见 `handoff/README.md` 第 2 节）：
   - `python3 tools/compare_versions.py --old ~/proxy-work/r12 --old-label r12 --new-label r13 --write`
   - `python3 tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r13 --write --out docs/evidence/与r7的对比.md`
   `--old` 指向的目录里的生成器会被执行，只用这个仓库自己历史里的版本。
10. **汇总变异日志**成 `docs/evidence/mutations.log`：全部编号都在、都是“发现”、没有超时；开头写明运行时间、Python / PyYAML 版本、统一源摘要、代码状态哈希在运行前后相同、有没有分段。`r12-as-used/assemble.py`、`write_mutlog.py` 是 r12 用的，可以照着改（日志文件名、类数、说明文字要换）。
    还要看一眼：有没有哪一类**只**靠“记录对应现在的配置”那两项测试发现（r12 有两类：M91、M92，已经如实写进文档，并列为下一版要补的断言）。
11. **核对文档里的数字**：每个数字都要能在日志或产物里找到。`r12-as-used/finalize.py` 是 r12 的核对脚本——它读日志和产物，断言文档里的说法与之一致，再填占位符；每一版按当版的内容重写一份。断言失败时改文档或者查原因，不要改断言去迁就。
12. 再算一次代码状态哈希，必须和第 6 步相同。

## 三、打包，交付

13. `python3 handoff/release/pack.py ~/proxy-work/proxy-rules-review-<日期>-rNN.zip`，再 `bash handoff/release/verify_package.sh <那个 zip>`：逐文件相同、`build.py --check` 通过、测试通过、扫描没有命中。
    包的文件数、字节数、SHA-256 写在给使用者的消息里（审核方的报告通常会写明它审的是哪个包）；不要写进包里的文档——写进去包就变了。r10–r12 都是这样做的。
14. 提交、交给使用者（`handoff/README.md` 第 5 节）。`main` 等使用者说可以再更新。

## 这个目录里的脚本

| 文件 | 作用 | 状态 |
|---|---|---|
| `code_state.sh` | 算代码状态哈希 | 通用。2026-10-06 在 r12 的工程目录上算出的值与 r12 定稿时记录的相同 |
| `run_mutations.sh` | 后台分两批跑变异检查，记开始时间和代码状态 | 通用。2026-10-06 在全新的克隆里用两类变异（M97、M98）试过，都被发现；r12 当时是手敲的同样两条命令 |
| `pack.py` | 打交付包 | 通用。2026-10-06 在 r12 的工程目录上重打，与发出去的包逐字节相同 |
| `verify_package.sh` | 解包核对 | 通用。2026-10-06 用它核对过 r12 的包（加 `--without-handoff`）：逐文件相同、244 项测试通过、扫描没有命中 |
| `r12-as-used/assemble.py`、`write_mutlog.py`、`finalize.py` | r12 汇总变异日志、写 `mutations.log`、核对文档数字用的脚本 | **原样存档，不能直接用**：里面的类数、日志文件名、数字、说明文字都是 r12 的，路径假定日志和它放在同一个目录。当作下一版的样子来改 |

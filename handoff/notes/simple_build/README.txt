简易版送审稿（r20 送审稿）的快速检查（2026-10-21；不属于 tools/run_checks.sh，也不进出版流程）

为什么在这里：照 2026-10-15 定的“先审后跑”，送审稿只跑快速检查，审完、改完、定稿以后才跑 tools/run_checks.sh 全套
（那时日志写进 docs/evidence/，docs/05 按新的一版重写）。这一次的输出放在这里，结论写在 docs/10 第八节。

怎么跑的（source ~/proxy-vendor/env.sh 以后，在仓库根目录）：
  bash handoff/notes/simple_build/run_quick.sh <r19 交付包解压后的工程目录>
代码是提交 6f7f6a6（日志开头写着；“代码和产物与提交相同”指 build.py、generator、source、dist、tests、tools 和提交相同，
文档不影响检查结果，是检查跑完以后才补的）。官方程序、上游源码、图标仓库都是 handoff/setup_env.sh 登记的版本。
日志里的本机目录换成了 <repo>（仓库）、<tmp>（临时目录）、<r19>（r19 的工程目录）。

文件
- run_quick.sh：上面那条命令。
- logs/build-check.log：python3 build.py --check（产物与统一源一致）。
- logs/tests-py3.13.log、tests-py3.12.log、tests-py3.11.log：全部测试（-v），三个版本并行跑；各 342 项，全部通过。
- logs/official-check.log：tools/check_official.py（mihomo -t 四份、sing-box check 十次、三项自检、mihomo 实际分组三次）。
- logs/icu-check.log：tools/check_icu.py --public --verbose（ICU 74；多了“全部节点”那一条）。
- logs/upstream-field-check.log：tools/verify_with_upstream_source.py（8,368 个字段 / 取值）。
- logs/icons-check.log：tools/check_icons.py（16 份配置、82 个组名、81 张图）。
- logs/compare-r19.log 和 与r19的对比.md：tools/compare_versions.py 和 r19 比。第五节：十份完整版配置逐字节相同、十份简易版是新增；
  第六节最后：严格版引用的四个规则文件和 r19 一模一样；第七节：十份简易版对照同一版的完整版（只有策略组、文件头说明，
  mihomo 另有境外 DNS 地址的 #境外DNS、一条 GEO 数据下载的规则、订阅上的检查间隔，sing-box 另有 detour 不同；Loon 的
  [Remote Filter] 条目先后不同，是按第一次被引用的先后排的，不影响结果）。
- logs/mutations-check-edits.log：tools/check_mutations.py --check-edits（196 类的改动都能套上；变异检查本身没有跑）。

没有在这里跑的：变异检查、tools/check_real_routes.py（理由见 docs/10 第八节）、Cursor 对照报告核对和规则上游快照核对
（这次没有改规则，结果和 r19 相同的前提是 source/ 的规则数据没变：git diff 里 source/ 只改了 project.yaml 的 simple 一节、
groups.yaml 两个组的 note_simple 和 icons.yaml 一条借图的登记）。官方内核实测“境外DNS”的 E6、E7 在 handoff/notes/simple_mihomo/。

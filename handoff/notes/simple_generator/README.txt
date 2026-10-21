简易版的生成器原型和核对（2026-10-21；只是原型，不是正式实现）

目的：在动手写简易版以前，确认 docs/10-简易版框架.md 里的写法生成得出来、官方检查过得去，
数出要改多少处、测试会漏掉什么。结论写在 docs/10 第七、八节。

做法：把仓库（r19 的代码；那时提交里只有文档变了）复制到仓库以外的一个目录，用 patch_proto.py
在副本上做 27 处“原文必须正好出现一次”的替换（10 个文件），在副本里一次生成完整版和简易版。
仓库本身没有改。正式实现时按 docs/10 第八节重新做，不照搬这份原型。

重跑（在仓库以外准备好副本目录 <proto>，source ~/proxy-vendor/env.sh 以后）：
  （<proto> 里放仓库的 build.py、generator/、source/、tests/、tools/ 的副本）
  python3 -B patch_proto.py <proto>                       # 套原型改法
  python3 -B <proto>/build.py --out <proto>/out           # 一次生成完整版和简易版（25 个公开文件）
  python3 -B check_proto.py <仓库> <proto>                 # → logs/check_proto.out
  python3 -B same_groups.py <proto>/out                    # → logs/same_groups.out
  python3 -B digests.py <proto>                            # → logs/digests.out
  python3 -B verify_skip_demo.py <仓库> <proto>/out        # → logs/verify_skip_demo.out
  python3 -B proto_all_nodes.py <仓库>                     # → logs/proto_all_nodes.out
  python3 -B proto_overlay.py <仓库>                       # → logs/proto_overlay.out（脚本里 import 了 proto_all_nodes）
  python3 -B icu_any.py <proto>                            # → logs/icu_any.out
  python3 -B mihomo_simple_grouping.py <proto> "$MIHOMO_BIN" "$GEODATA_DIR"   # → logs/mihomo_simple_grouping.out
logs/ 里的 .out 是 2026-10-21 重跑的输出（第一次是分析时跑的，结果相同）。
logs/official_checks.out：同一天对原型的简易版跑 mihomo -t（v1.19.31）和 sing-box check（1.14.1、1.12.0；
  公开模板和带测试样例节点的两种）的输出，全部 exit=0。
logs/proto-tests.log：只把简易版产物加进副本、不登记进测试时跑全部测试的输出；
logs/proto2-tests.log：用 patch_tests_proto2.py 把简易版登记进 tests/helpers.py 以后的输出。
两份日志里的本机目录换成了 <scratch>。proto-tests.log 里有 5 项 ERROR 是因为副本里没有 docs/、.gitignore
  等文件（Cursor 对照报告、Git 忽略、上游证据那几项），和简易版无关；和简易版有关的只有 1 项 FAIL
  （test_fifteen_public_outputs）。proto2-tests.log 里 6 项 FAIL、3 项 ERROR 都是登记简易版以后要改的测试，
  docs/10 第八节说了是哪几类。

关键结果
- check_proto.out：完整版 10 份配置和 4 个规则文件与仓库 dist/ 逐字节相同（14/14）；10 份简易版除策略组以外
  和对应的完整版相同；模拟器上 10 对 × 239 个用例，结果没有一处不同；简易版结构检查没有问题。
- same_groups.out：同名的组里，只有“国外默认”和六个地区组写法不同（sing-box 只有六个地区组不同）。
- digests.out：简易版和完整版的规则段加 DNS 段摘要、拨号核对用的部分都相同，所以官方内核的核对记录可以共用。
- verify_skip_demo.out：现在的写盘前检查（generator/verify.py）按完整文件名认文件，同一处错误放进
  loon.conf 会报，放进 loon-simple.conf 什么都不报。正式实现必须先改这里。
- proto_all_nodes.out、proto_overlay.out：“全部节点”这条筛选 8,254 字节（带本地补充的样例 8,593 字节；
  项目自己定的上限是 16,000）；在 2,058 个样本名、2 万个随机名上和“宽的七条取并集”没有一处不同。
- icu_any.out：ICU 74 上和 Python 没有不同。
- mihomo_simple_grouping.out：官方 mihomo v1.19.31 用 2,290 个假节点（其中提示行 38 个）实际分组：
  “日本”第一项是“日本·自动”、共 110 项、当前选中“日本·自动”；“国外默认”前七项是七个地区、共 2,259 项、
  当前选中“日本”，提示行一个都没进来；和 Python 按同一条正则算的结果逐个相同。

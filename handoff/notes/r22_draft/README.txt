r22 送审稿（2026-11-18：三份全项目复核和使用者的 Claude 域名清单）的快速检查。不是出版本时的全套检查（tools/run_checks.sh、变异检查全套），那些等审完、
按意见改完、定稿以后再跑；所以 docs/05 和 docs/evidence/ 的检查日志仍是 r21 的（docs/evidence/ 里改了的只有规则数据：upstream-snapshot.json、上游规则对照.md，
和新存档的两份审核报告）。

  bash handoff/notes/r22_draft/run_quick.sh <r21b 的工程目录>
    （照 handoff/notes/r21_draft/run_quick.sh 改的：对比的旧版本换成 r21b，另加打包验包自测、r22 相对 r21b 的私密产物对比、sing-box 取值核对。
     r21b 用的是会话分支 b9a9f14 的检出，代码和产物与 main 上的 r21b（a6671c1）相同）
  2026-11-18 07:29–07:40（UTC），提交 166f5e4（代码和产物与提交相同，日志第 3 行）：
    build-check.log            python3 build.py --check：产物与统一源一致
    tests-py3.13/3.12/3.11.log 全部测试，各 369 项通过
    official-check.log         官方 mihomo v1.19.31（-t）、sing-box v1.14.1 / v1.12.0（check），含简易版、带样例节点的私密配置（样例节点 26 个）和实际分组：全部符合预期（样例节点转换 23 个、其中改名 3 个，跳过 3 个——跳过的是故意放进样例的不支持的写法）
    icu-check.log              节点筛选正则在 ICU 上（“港X”“臺中”改了正则）：宽、严两套和简易版的“全部节点”那一条，ICU 与 Python、与手写期望都完全一致，长名字都按时结束
    upstream-field-check.log   配置里的字段名在 mihomo / sing-box 源码里都有（这一版新写了 reverse_mapping）
    icons-check.log            图标地址都在图标仓库里
    compare-r21b.log           tools/compare_versions.py，报告是同目录的 与r21b的对比.md。报告里 r21b 简易版的几条筛选显示成“<筛选：未知的正则>”：
                               工具只给当前版本的简易版筛选（全部节点、Stash 全部节点、境外DNS）起了名字，这一版“港”的正则变了，r21b 的对不上。
                               不影响配置；定稿前改工具（旧版的这几条也起名、补测试），记进 docs/08 第 23 轮
    mutations-check-edits.log  248 类变异的改动都能套到当前代码上
    selftest-package.log       打包、验包脚本的自测（好包、坏包、删除前的判断）
    private-vs-r21b.log        handoff/notes/r22_private_vs_r21b.py：带本地补充、虚构订阅和节点的私密产物，相对 r21b 只差有意改的地方；私密 manifest 本身也核对
    singbox-enum-sweep.log     handoff/notes/r22_singbox_enum_sweep.py：sing-box 1.14.1、1.12.0 认哪些取值
  另外（不在 run_quick.sh 里）：
    count-region-words.log     handoff/notes/r22_draft/count_region_words.py：docs/02 写的“每个词、每面国旗套进 126 种写法”一共多少个名字（那项测试不打印个数）。
                               r21b 399 个词、49,976 个名字（和以前记的相同），r22 402 个、50,354 个
    real-routes-snapshot.log   官方内核快照（tests/data/real_sets.json）最后一次重新生成的输出（规则和 DNS 改了，按 handoff/release/README.md 第 3 步重新生成；
                               这一版生成过两次，第一次在 PR #10 那一份改完时，第二次在另两份改完以后，这里是第二次的：用例与排除项 303 条、
                               不同的目标 283 个，三个官方内核和模拟器的结果全部一致，写入主机 279 个、IP 28 个。第二次检查点 f902ed2 以前这里误放了
                               第一次的输出（293 条、273 个目标、主机 269 个），换掉了）
    mutations-trial-a/b/c.log  第一批试跑：PR #10 那一份加的 M211–M224 和改写的 M14、M182，在当时的代码上各跑一遍全部测试（那时“发现”的口径已经收紧），都被发现
    mutations-trial2-a/b/c.log 第二批试跑：M225–M248 和改写的 M70、M102、M107，在提交 166f5e4 上（a 批先跑了基线；b、c 批用 --skip-baseline）：⟦第二批结果⟧
日志里本机的仓库目录、临时目录、r21b 目录、工作目录换成了 <repo>、<tmp>、<r21b>、<work>；放官方程序和上游数据的目录（~/proxy-vendor）照原样留着，和 docs/evidence/ 的日志一样。

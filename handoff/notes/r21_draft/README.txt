r21 送审稿（2026-10-31：使用者定的三个测速间隔）的快速检查。不是出版本时的全套检查（tools/run_checks.sh、变异检查全套），那些等 GPT 审完、
按意见改完、定稿以后再跑；所以 docs/05 和 docs/evidence/ 仍是 r20 的。

  bash handoff/notes/r21_draft/run_quick.sh <r20 的工程目录>
    （照 handoff/notes/simple_build/run_quick.sh 改的：对比的旧版本换成 r20，输出换到这个目录。r20 用 git archive f45eb89 取到仓库以外；
     f45eb89 是只改了文档的 r20b，代码和产物与 r20 的 aeb3d4d 相同）
  2026-10-31 08:37–08:49（UTC），提交 1366d17（代码和产物与提交相同，日志第 3 行）：
    build-check.log            python3 build.py --check：产物与统一源一致
    tests-py3.13/3.12/3.11.log 全部测试，各 348 项通过
    official-check.log         官方 mihomo v1.19.31（-t）、sing-box v1.14.1 / v1.12.0（check），含简易版和实际分组：全部符合预期
    icu-check.log              节点筛选正则在 ICU 上（筛选没有改）
    upstream-field-check.log   配置里的字段名在 mihomo / sing-box 源码里都有
    icons-check.log            图标地址都在图标仓库里
    compare-r20.log            tools/compare_versions.py，报告是同目录的 与r20的对比.md
    mutations-check-edits.log  209 类变异的改动都能套到当前代码上
  另外（不在 run_quick.sh 里）：新加和改写的 9 类变异 M201–M209 在同一份代码上各跑一遍全部测试（三批同时跑，08:33 起），
    9 类都被发现、输出都含预设的信息：mutations-trial-a.log、-b.log、-c.log。
日志里本机的仓库目录、临时目录、r20 目录换成了 <repo>、<tmp>、<r20>；放官方程序和上游数据的目录（~/proxy-vendor）照原样留着，和 docs/evidence/ 的日志一样。

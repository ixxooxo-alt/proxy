r22 第二份送审稿（2026-11-19：第一份送审稿 f60ee42 的两份审核，docs/08 第 24、25 轮）的快速检查。不是出版本时的全套检查（tools/run_checks.sh、
变异检查全套），那些等审完、按意见改完、定稿以后再跑；所以 docs/05 和 docs/evidence/ 的检查日志仍是 r21 的（docs/evidence/ 这一轮新加的只有
两份审核报告的存档：gpt-r22-draft/、review-r22-draft/）。第一份送审稿的快速检查在 handoff/notes/r22_draft/。

  bash handoff/notes/r22_draft2/run_quick.sh <r21b 的工程目录> <第一份送审稿 f60ee42 的工程目录>
    （照 handoff/notes/r22_draft/run_quick.sh 改的：私密产物改成和第一份送审稿比，另加官方程序核对；打包验包自测去掉 PYTHONUNBUFFERED 跑。
     r21b 用的是会话分支 b9a9f14 的检出；第一份送审稿用的是 git archive f60ee42 解出来的目录）
  ⟦快速检查时间⟧（UTC），提交 ⟦代码提交⟧（代码和产物与提交相同，日志第 3 行）：
    build-check.log            python3 build.py --check：产物与统一源一致
    tests-py3.13/3.12/3.11.log 全部测试，各 ⟦测试数⟧ 项通过
    official-check.log         官方 mihomo v1.19.31（-t）、sing-box v1.14.1 / v1.12.0（check），含简易版、带样例节点的私密配置和实际分组：⟦官方检查结果⟧
    icu-check.log              节点筛选正则在 ICU 上（“港德 / 港英 / 港法 / 港欧 / 港歐”改成了前面不能是“香”的片段）：⟦ICU 结果⟧
    upstream-field-check.log   配置里的字段名在 mihomo / sing-box 源码里都有
    icons-check.log            图标地址都在图标仓库里
    compare-r21b.log           tools/compare_versions.py，报告是同目录的 与r21b的对比.md（r21b 简易版的几条筛选仍显示成“未知的正则”：
                               工具的问题，定稿前改，见 handoff/README.md 第 19 节第 7 条）
    mutations-check-edits.log  272 类变异的改动都能套到当前代码上
    selftest-package.log       打包、验包脚本的自测（好包、坏包、对不上时不运行包里的程序、和提交相符的构建失败 / 测试失败 / 测试在汇总后打印文字）
    private-vs-draft1.log      handoff/notes/r22b_private_vs_r22draft.py：带本地补充、虚构订阅和节点的私密产物，相对第一份送审稿只差这一轮有意改的地方
    review-probes.log          handoff/notes/r22b_review_probes.py：官方 mihomo、sing-box 核对订阅读法、重复键（含查的范围：最外层、proxies、proxy-providers 怎么读）、SS2022 密钥、QUIC 上的 uTLS
    singbox-enum-sweep.log     handoff/notes/r22_singbox_enum_sweep.py：sing-box 1.14.1、1.12.0 认哪些取值（和第一份送审稿时相同的核对）
  另外（不在 run_quick.sh 里）：
    mutations-trial-a/b/c.log  变异试跑：这一轮新加的 M249–M272、改写的 M15 / M185 / M232 / M237 / M264，和四个预设是一段文字的旧变异（M2、M82、M240、M242，
                               看收紧后的“发现”判据会不会误判），在提交 ⟦试跑提交⟧ 上（a 批先跑了基线；b、c 批用 --skip-baseline）：⟦试跑结果⟧
日志里本机的仓库目录、临时目录、r21b 目录、第一份送审稿的目录、工作目录换成了 <repo>、<tmp>、<r21b>、<draft1>、<work>；
放官方程序和上游数据的目录（~/proxy-vendor）照原样留着，和 docs/evidence/ 的日志一样。

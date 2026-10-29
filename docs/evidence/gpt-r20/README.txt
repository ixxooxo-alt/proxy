GPT 对 r20 正式版的审核报告。审的是会话分支 claude/r12-gpt-review-handling-q4onlv 的提交 aeb3d4dcb157164a572f367c4671091913283f11
（r20：统一源 2026.10.17-1，生成器 1.11.1，简易版 2026.10.23-1；2026-10-23 定稿后跑了全套检查）。
审核方开了审核 PR #7（https://github.com/ixxooxo-alt/proxy/pull/7，草稿，base 是上面的会话分支，head 分支 audit/r20-aeb3d4d-review-20261029，
提交 454efc7ecce55d50d42e6992018408b1ec3ad01d，2026-10-29 23:56:54 +0800）。一个问题一个提交，5 个提交，父提交链从 aeb3d4d 开始：
530aa94（R20-F06）、7f35e77（F07）、d273983（F08）、10f3d41（F09）、454efc7（README，总结、独立复核和设计判断，含建议 S01、S02）。
PR 里只新增了 handoff/reviews/r20-aeb3d4d/ 下的这 5 个文件；没有改 main、生成器、配置、规则、需求原文和既有证据，没有合并。
用户 2026-10-29 在对话里转述了结论并给了 PR 的链接（原话见 docs/00“补充（2026-10-29，GPT 审完 r20 正式版）”一节）。

这里的 5 个文件是从 454efc7 里原样取出的（git show 454efc7:handoff/reviews/r20-aeb3d4d/<文件名>；git hash-object 与下面的 blob 相同）：
  README.md   blob 1719ee27ff879b8d1ac47d50e0486a5b0b0235d7  6,146 字节  SHA-256 09aef151ea816d22d2245f3214c591cd0f0c8a119fd2038c72115c0657e3a37f
  R20-F06.md  blob c0e5b9e149af0ac59f3353579366bb37113072bb  1,732 字节  SHA-256 79457c987f6329b479886bc272a1c0871575192d6cf46e19d19f748eb525ee56
  R20-F07.md  blob 45bda70bcc9a6976d8d2de27755ca18b25a5f655  2,405 字节  SHA-256 ce497d0d029030c6f61609e8d860a4ed6f0903c47889c153d9649f3cecfd5945
  R20-F08.md  blob 1d768e38881ef14820bc0086f6687c9e83f63757  1,024 字节  SHA-256 0d4fc880a363d0ec52ae3b864a8921d07cd44b8a5c16662e7dad634b87ed6066
  R20-F09.md  blob f5b397f35ffdf903f98539729c92cd64506e78f5  1,425 字节  SHA-256 0c389abbb704dbb7a74240a6b1a1f64f7856b54232b47dda53626ed8f20324d1
报告里的链接指向审核方提交里的路径（handoff/reviews/r20-aeb3d4d/），这里的文件名相同、放在本目录。
PR 的说明是报告结论的摘要，没有另存。PR 本身照 00-审核说明.md 的规则不合并：报告存在这里，逐条核实与处理见 docs/08-外部审核记录.md 第 18 轮。

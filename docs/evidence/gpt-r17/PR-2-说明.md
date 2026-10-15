# 审核 r17 88a1e38：修复复核与 DNS 替身收尾竞态

审核固定提交 88a1e38（r17，统一源 2026.10.14-1／生成器 1.10.0），基线 a999d81。本 PR 只新增完整审核报告，不修改已有代码、配置、日志或需求原文，不合并。

上轮三项的主要修复正确，本轮未确认新增配置层面的错误。

**R17-F01：文档不符／测试工具可靠性，中。**
- 位置：`tools/check_real_routes.py:188–224`，尤其 DnsStub.close 和 close_stubs；调用点在结果计算后由 finally 关闭。
- 原因：socket 关闭后马上检查 unparsed，却未等待接收线程结束。查询已收到但诊断尚未写入时，可以先返回成功、后留下异常。
- 复现：原始实现的本机 100 轮“发送后立即关闭”探针，99 轮返回时未报错、随后才记录异常；另用 Event 控制交错复现。该比例不是正常全套检查的漏报率，没有证据说交付日志已受影响。
- 依据：[本提交代码](https://github.com/ixxooxo-alt/proxy/blob/88a1e388e38adaecdffe0e99e70e7c702169446d/tools/check_real_routes.py#L188)、[Python Thread.join](https://docs.python.org/3.12/library/threading.html#threading.Thread.join)。
- 建议：停止发送端、完成接收线程收尾，再汇总 seen/unparsed 和计算结果；增加唤醒／超时与有界 join，未结束时报未完成；加确定性并发回归用例。无需改生产 DNS／分流。

报告附非阻断措辞建议、Stash 新旧官方材料差异、第 22 项及真机边界。

本轮独立验证：build --check；305 项测试全部通过、无跳过；Stash 实际筛选的 ICU/Python 核对；版本对比正文与交付报告一致；快照除日期、版本及 mihomo 配置摘要外全部结果不变；产物与代码摘要一致。154 类变异仅核实存档，未重跑；真实 App／TUN／原 ZIP 字节未核对。

# proxy r19 正式版审核报告

审核日期：2026-10-17。仓库：`ixxooxo-alt/proxy`。

审核对象固定为 `claude/r12-gpt-review-handling-q4onlv` 的提交 `628ed8a0c2d9062d0150b100607e9637957eec38`，统一源 `2026.10.17-1`，生成器 `1.10.2`。主要对照送审稿 `08051e5`，产物和验收数字另对照 r18 `ead8ca8`。没有审核或修改 main。

**结论：这次没有发现新的、已确认的代码阻断问题。R19-F01 和 R19-S01 的修复通过复核；本机 317 项测试全部通过。新增确认问题只有一项低严重度的文档计数未更新，涉及两处。** 分两遍运行造成的缓存交互空白已经写明，属于仍未覆盖的场景；不能据此宣布真机行为已经验证。

## 1. 新增确认问题

### R19-F02：验收说明沿用了旧版的两处测试计数

严重程度：**低／文档不符**。不涉及配置导入失败、分流错误或新发现的 DNS 泄漏。

**位置一：`docs/05-验收记录.md:51`，“自动测试”行。**

该行先说本版 317 项通过，后面仍写“比 r17 多 6 项”，并列出 r18 新增的六项测试。这会让读者误以为 r19 相比 r17 只增加了六项，也没有交代本轮实际新增的测试。

仓库各版的 `docs/evidence/tests.log` 分别是：r17 **305**，r18 **311**，r19 **317**。所以 r19 比 r17 多 **12** 项，比 r18 多 **6** 项。r19 的六项为送审稿新增四项，再加正式版的“清 UDP 队列中途控制连接断开”和“用真实 DNS 替身认查询归属”两项。

建议：将本行改为“317 项；比 r18 多 6 项（比 r17 多 12 项）”，列出 r19 新增内容；原来介绍 r18 六项测试的文字保留时，明确标为历史变化。**317 本身正确，实际通过结果也正确；错的是比较基准和增量说明。**

依据：[本版文档第 51 行](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/docs/05-验收记录.md#L51)、[r17 测试日志](https://github.com/ixxooxo-alt/proxy/blob/88a1e38/docs/evidence/tests.log)、[r18 测试日志](https://github.com/ixxooxo-alt/proxy/blob/ead8ca8/docs/evidence/tests.log)、[本版测试日志](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/docs/evidence/tests.log)。本次也在 Python 3.12.14 上独立跑出了 317 项全部通过。

**位置二：`docs/06-已知限制与待决事项.md:311`，“Python 版本”项。**

该行说“等 UDP 进队列的两项测试读 Linux 的 `/proc/net/udp`，别的系统上会跳过”。正式版增加中途断开测试以后，调用 `_wait_udp_queued` 的已经有三项：

- `tests/test_real_data.py:1133`：停止时保留已接收的 UDP 包。
- `tests/test_real_data.py:1208`：控制连接已经关闭后，不计入后到的包。
- `tests/test_real_data.py:1249`：清队列中途控制连接关闭后，不计入后到的包。

建议：把“两项”改成“三项”。这是跨平台测试覆盖说明的计数问题，不表示 Linux 上有三项失败。本次三项均实际运行并通过。

依据：[限制说明第 311 行](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/docs/06-已知限制与待决事项.md#L311)、[三个测试及队列等待函数](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tests/test_real_data.py#L1133)。

## 2. 上轮修复复核

### R19-F01：UDP 清队列中途断开

**修复成立。** `tools/check_real_routes.py:1047–1057` 已经在每次取下一包前调用 `_control_closed`。上一版是进入清队列分支前只检查一次，中途关闭以后仍能继续接收后面的包；现在不再有这个已复现的问题。

本次重跑上轮的固定顺序探针：先接收 `first.example`；停止过程中取出 `drain.example` 并拦住处理；关闭控制连接，确认服务端读得到 EOF；再把 `after-close.example` 放进 UDP 队列；最后放行。结果只记录前两个，第三个没有记入，停止返回成功，`invalid` 为空。控制连接保持打开的对照场景则三个都记入。

`tests/test_real_data.py:1249–1308` 的新增测试同样用 Event、已可读的 TCP EOF 和已进入接收队列的 UDP 包固定先后，覆盖了实际反例。它的超时是防止测试挂住的上限，不是靠睡固定时长猜测谁先执行。

我还把 M167 的“只在开头检查一次”改回去运行相关测试类，新测试能发现错误。

检查控制连接与读取 UDP 包之间仍存在很短的观察间隔，不能把此实现说成跨 TCP/UDP 的原子事件排序。`docs/06:310` 已明确这一点，按“看到断开以前取出的包照常核对”解释。本次没有证据表明这个已说明的边界会破坏现有核对结果，不另列为缺陷。

依据：[生产代码](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tools/check_real_routes.py#L1036)、[新增测试](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tests/test_real_data.py#L1249)。

### R19-S01：DNS 归属测试现在真的调用生产函数

**修复成立。** `tools/check_real_routes.py:470–481` 的 `_attribute_dns` 是实际核对调用的函数。它先要求全部替身已经停止，再按“规范化后的名字＋查询类型”匹配记录；`_singbox_run` 在停止内核、关闭替身以后调用它。

`tests/test_real_data.py:1310–1347` 通过真实 UDP 向真实的 `DnsStub` 发出同名 A 和 HTTPS 查询：A 送国内替身，HTTPS 送境外替身；国内查询在记录前被 Event 拦住。测试既检查提前归属会报错，也检查停止完成后 A 和 HTTPS 各自归属正确；另一个只取得假地址的用例不会沾上迟到的国内记录。这次不是在测试里另抄一遍匹配算法。

本次独立重跑上轮包含真实 DNS 替身的探针：迟到的 `late.example/A` 归国内，`fake.example/A` 仍只归 fake-ip，同名但未发送的 HTTPS 不被 A 冒认。该探针替换了外部进程和查询返回值来控制事件顺序，不是一次官方 sing-box 内核运行，也不用于证明真实超时长度。

定向变异结果：M168（只看名字不看类型）和 M169（允许提前归属）均被真实替身测试发现；M170（调用提前到关闭前）被已有生命周期源码检查发现。M167–M170 本次各跑了 `Socks5RecorderTool` 的 19 项测试，四类均被发现。没有把这四类的重跑写成重跑了全部 170 类。

依据：[实际归属函数与两遍入口](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tools/check_real_routes.py#L470)、[真实替身测试](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tests/test_real_data.py#L1310)、[生命周期检查](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tests/test_real_data.py#L1414)、[新增变异](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/tools/check_mutations.py#L537)。

## 3. 分两遍运行与缓存：已确认的覆盖边界

`singbox_probe` 把查询与连接拆成两次 `_singbox_run`，各启一次内核，避免连接自行产生的查询污染 DNS 用例的归属。这个取舍适合分别测 DNS 去向与路由选择，不建议为恢复缓存覆盖再把两类记录无区分地混在一起。

但它不覆盖同一个内核里“先 DNS 查询、再用所得地址连接”共享 DNS/fake-ip 缓存的行为。`docs/06:309` 已准确写明；不能用两遍都正确推出共享缓存也正确。生产路径的 TUN、fake-ip 地址回查、真实代理节点，也不能由这两个独立入口自动得到验证。

这不是新发现的配置错误。若以后要补，适合另加专门的集成场景：同一进程先查 A/AAAA，再向返回的假地址发连接，分别核对上游查询和节点收到的目标；必要时覆盖缓存命中、过期及策略切换。它应有独立的预期结果，不能只比较现有两个结果表是否一样。本轮不要求重写已有核对工具。

## 4. 数字、产物与时间线

| 项目 | 本次核对结果 |
| --- | --- |
| 全部单元测试 | 本机 Linux，Python 3.12.14／PyYAML 6.0.3：`Ran 317 tests in 168.847s`，`OK`，没有跳过。交付日志为 Python 3.13.16／PyYAML 6.0.1，317 项、186.164 秒、退出码 0；两次耗时不同不构成错误。 |
| 生成结果 | `python3 build.py --check` 通过；manifest 中 14 个文件的摘要逐个相符，加 manifest 自身共 15 个公开产物。 |
| 变异定义 | `python3 tools/check_mutations.py --check-edits` 为 170/170；交付日志有 M1–M170 各一次，无缺项或重复，全部标记“发现”。本次另实跑 M167–M170。 |
| 快照对应性检查 | 重数交付变异日志：规则/DNS 摘要检查出现 43 类，拨号摘要检查出现 47 类；仅靠这两种摘要检查发现的为 0 类，与文档一致。 |
| 生产配置变化 | 与 r18 比，配置规则、DNS 和策略组语义未变。sing-box 两份与四个规则文件逐字节相同；其余为版本注释及三份严格版注释的变化。 |
| 严格版大小 | Loon 243,329→243,377；Quantumult X 406,506→406,554；Stash 252,769→252,817 字节，与 docs/05 一致。 |
| 版本对比报告 | 本次重新生成的 r18→r19 报告与提交中的报告正文一致，只有输出末尾多一个换行。 |
| `real_sets.json` | 与 r18 只有三个叶值不同：生成日期、统一源版本、mihomo 配置摘要。其余内容包括路由/DNS/拨号记录相同，支持“核对结果未变”，不是本次重新运行全部官方内核得到的结论。 |
| 旧审核报告存档 | `docs/evidence/gpt-r18/` 与 `gpt-r19-draft/` 内的报告，和本审核环境留存的原报告逐字节相同。 |

本次计算出的代码状态哈希与交付记录相同：

```text
34cef64e555896d17bbe3191670dc9a7c292287f124010f262b6cc03ffd36516
```

统一源摘要也与 manifest、各份日志一致：

```text
25018e637174b9692dfbb066ad1cf75a4123a070b10f1fc7525a4389bb14ebdc
```

时间线没有发现前后矛盾：定稿为 08:39:15 UTC；变异日志记第一段 08:40:53–10:46:14、123 类，第二段 11:50:49–12:42:00、47 类，合计 170。随后交付用常规日志的时间从 13:08:45 延续到 13:26:51，符合 docs/05 的“第二遍 13:08–13:26”。不要把它与第一次并行检查或 10 月 15 日送审稿快速检查混为一遍。

`handoff/release/r19-as-used/assemble.py` 会比较各段开始记录的代码哈希与当前哈希，拒绝缺失/重复的变异编号或未发现的结果，并要求最后一段有完整合计。因此中断后只重跑尚未留下结果的类别、再合并，在这个流程下是合理的。

**证据限度：**本次看到的是仓库提交的汇总日志和脚本。分段原始日志、`segments.json`、重启后环境核对原文及单独 Python 3.11/3.12 运行日志不在这次可见材料里，不能把“汇总记录内部一致”说成我独立目击或重新验证了重启前后的全部环境。分段结束时间的脚本来源是日志文件 mtime，也不应解释成每个变异都有独立签名的结束时间。这不构成本次发现的虚假记录。

依据：[验收时间线](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/docs/05-验收记录.md#L24)、[变异日志](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/docs/evidence/mutations.log)、[分段汇总程序](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/handoff/release/r19-as-used/assemble.py)、[当时使用的步骤](https://github.com/ixxooxo-alt/proxy/blob/628ed8a0c2d9062d0150b100607e9637957eec38/handoff/release/r19-as-used/README.md)。

## 5. 本次未作的验证

- 没有重新跑全部 170 类变异和全部官方内核核对。对交付日志的检查、快照比较、四类定向变异和本机 317 项测试，已经在上文分别标明。
- 没有在本次环境运行 Python 3.10、3.11 或 3.13；独立运行的是 3.12.14，上一版的 `_stop` 同名问题在这个版本上不再出现。
- 没有进行 Stash 或其他客户端的手机/桌面 App 真机验证。Stash 正则引擎、订阅失败与空组处理等既有未验证事项，没有因为本轮工具测试通过而变成已验证。
- 本次没有拿到 ZIP 的字节，不能确认交付包 SHA-256 `7246f5b9f4a0ef8dc61e628e8cceeed3a6e68002854025dc5e84ab2bf66bdaa5`，也没有执行解包核对。Git 内容一致不能替代 ZIP 校验。

本次建议改动仅为 R19-F02 的文档说明。没有提出新的规则、DNS 或策略组修改，也没有修改 main、覆盖原证据或合并 PR。

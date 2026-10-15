# proxy r18 独立增量审核报告

审核提交：**ead8ca886ffe93cce289e96a1fa4ce50910e41ef**，仓库 `ixxooxo-alt/proxy`，分支 `claude/r12-gpt-review-handling-q4onlv`。统一源 **2026.10.15-1**，生成器 **1.10.1**。基线为 r17 的 `88a1e388e38adaecdffe0e99e70e7c702169446d`。审核日期：2026-10-15（UTC+8）。

先读本提交的 `00-审核说明.md`、`docs/08` 第 13 轮，再核对增量、源码、存档与独立探针。本文不审核 main，不修改用户配置，不合并 PR。下面的临时实验均未改动被审工作树。

## 结论

**R17-F01 的处理方向正确，但 r18 仍有三处已确认的核对工具问题：Python 兼容性、UDP 关联结束后的误记录、逐条 DNS 查询的归属。没有确认新增生产配置的导入失败、分流错误或实际 DNS 泄漏。**

| 编号 | 类别及优先级 | 已确认的影响 | 没有证明的事 |
|---|---|---|---|
| R18-F01 | 文档不符／测试工具可靠性；高 | DNS 停止标记覆盖 Thread 的内部方法，Python 3.12 的正常停止即报 TypeError；不符合 Python 3.10+ 的声明 | 不否定作者在 Python 3.13 的通过记录；不是客户端配置故障 |
| R18-F02 | 文档不符／测试工具可靠性；中 | UDP 停止分支跳过控制连接 EOF 检查，能把关联结束后才到的包计为合规 seen | 没有证明官方内核存档中的六处 UDP 版本差异由它造成 |
| R18-F03 | 文档不符／测试工具可靠性；中 | 逐条查询按各替身的总条数增量认归属，迟到的上一条可以错算给下一条；查询超时并不建立同步关系 | 用受控 DNS 调度器复现了记账逻辑；未在官方 sing-box 上端到端复现此时序，也未证明当前快照错记 |

**独立检查结果：** 原始提交在本机 Python 3.12.14／PyYAML 6.0.3 下执行全部 **311 项测试，1 failure、4 errors**，根因均关联 F01（含清理阶段和子线程结果的连带错误）。只在临时副本中把三个 `self._stop` 引用重命名后，`test_real_data.py` 的 **57 项全部通过**。这 57 项是修正实验的结果，不能写成原始 r18 的全部测试通过。

生成检查、14 个登记产物摘要、代码状态哈希、配置语义增量、版本对比正文与快照差异核对通过。162 类变异只复核存档，没有全量重跑。原始交付 ZIP 未取得，不能核验其原始大小和 SHA-256。

## R18-F01：DnsStub._stop 覆盖 Thread._stop，声明支持的 Python 版本无法正常收尾

**类别：文档不符／测试工具可靠性；优先级高。已独立运行确认。**

**位置：**

- `tools/check_real_routes.py:191`：`self._stop = threading.Event()`。
- 同文件 `202`、`228–235`：使用这个 Event，并调用继承来的 `is_alive()`／`join()`。
- `README.md:66`、`README.zh-CN.md:31`、`00-审核说明.md:83`：声明 Python 3.10+。

**为什么错：** DnsStub 继承 threading.Thread。CPython 3.10、3.11、3.12 的 Thread 在 `join()` 或 `is_alive()` 确认线程结束时会调用 `self._stop()`；实例上的 Event 遮住了这个可调用方法。于是接收线程正常退出后，调用者得到的不是 True 或预期 RuntimeError，而是：

```text
File tools/check_real_routes.py, line 230, in stop
    self.join(timeout)
File threading.py, in _wait_for_tstate_lock
    self._stop()
TypeError: 'Event' object is not callable
```

最小复现（Python 3.12，在固定提交的工程根目录运行；不需内核或网络出口）：

```python
import sys
sys.path.insert(0, "tools")
import check_real_routes as c
s = c.DnsStub("probe", {})
s.start()
s.stop()  # TypeError: 'Event' object is not callable
```

本轮原始完整测试的结尾是：

```text
Ran 311 tests in 170.618s
FAILED (failures=1, errors=4)
```

涉及三个测试方法：`test_close_stubs_reports_a_receiver_that_does_not_finish`、`test_close_stubs_waits_for_a_query_already_received`、`test_dns_stub_keeps_queries_it_cannot_read`；其中有重复记入的 cleanup error，**不是五个不同测试方法都坏了**。子线程的 TypeError 也使结果列表为空。收尾异常还会阻止 close_stubs 继续关闭后续替身，并产生未关闭 socket 的警告。

**与作者日志的关系：** `docs/evidence/tests.log` 写的是 Python 3.13.16、311 项 OK。CPython 3.13 已改用 `_handle.join()`，没有沿用这条 `_stop()` 路径，因此两个环境的结果并不矛盾。缺口是支持范围和只测一个版本，不是据此认定作者伪造通过记录。

**建议：** 将这个 Event 的三个引用改为不会撞上 Thread 内部成员的专用名称（例如 `_dns_stop_event`）；保留现有轮询和 join 设计。至少在一个声明支持的旧版本运行真实启动／停止用例，不要只靠 AST 扫描。无需为这点把整个项目最低版本抬到 3.13。

**修正实验：** 临时副本仅作上述三处重命名，`python3 -m unittest discover -s tests -p test_real_data.py -v` 得到 `Ran 57 tests in 25.281s / OK`，包括六项新增测试；未把该临时修改写回被审分支。

**依据：** [本提交 DnsStub](https://github.com/ixxooxo-alt/proxy/blob/ead8ca886ffe93cce289e96a1fa4ce50910e41ef/tools/check_real_routes.py#L177)；CPython 官方源码 [3.10 的 _wait_for_tstate_lock](https://github.com/python/cpython/blob/v3.10.0/Lib/threading.py#L1094)、[3.11 同一方法](https://github.com/python/cpython/blob/v3.11.0/Lib/threading.py#L1118)、[3.12 的调用点](https://github.com/python/cpython/blob/v3.12.14/Lib/threading.py#L1155)、[3.13 的 join](https://github.com/python/cpython/blob/v3.13.0/Lib/threading.py#L1054)。3.12 为实际运行证据，3.10／3.11 的同类影响由源码确认，未分别安装运行。

## R18-F02：UDP 停止分支绕过控制 TCP 的 EOF，关联结束后的包仍进入合规记录

**类别：文档不符／测试工具可靠性；优先级中。已在原始 r18 接收端独立复现。**

**位置：**

- `tools/check_real_routes.py:1017–1026`：一看到 `_closing`，直接循环 recvfrom 并调用 `_take_udp`，不再检查控制连接。
- 同文件 `1027–1036`：只有常规分支检查 TCP EOF，并优先结束关联。
- 同文件 `880–887`、`docs/08:871`：声称记录的请求符合列出的 RFC 条件，并声称控制连接断开的仍照旧立刻结束。
- `tests/test_real_data.py:1130–1162`：新增排队 UDP 用例在断言以前一直保持控制连接打开，没有覆盖“控制连接已关闭，再进入停止分支”。

**为什么错：** 新分支注释写“控制连接还开着”，但代码没有验证这个前提。接收线程正在处理第一个包时，TCP 可以先关闭；随后到来的第二个包停在 UDP 队列里。此时 stop 设标记，线程恢复后先进入排空分支，既不检查 TCP 也不核对关联是否已经结束，第二个包便进入 seen，invalid 仍为空。

**固定顺序复现：**

1. 完成真实 SOCKS5 UDP ASSOCIATE，保持一个客户端 UDP socket。
2. 发 `before.example`；用 Event 把工作线程停在这个包的原地址解析函数前。
3. 关闭客户端控制 TCP；在服务端 socket 用 `select` 加 `recv(MSG_PEEK)` **确认已经能读到 EOF**，不是仅假设 FIN 已送达。
4. 这以后才发 `after-close.example` 的 UDP 包。
5. 另一个线程调用原始 `rec.stop()`，等 `_closing` 标记已经置位，再放行第一个包的原解析函数。

原始 r18 返回：

```text
stop() -> True
seen -> [('udp', 'domain', 'before.example'),
         ('udp', 'domain', 'after-close.example')]
invalid -> []
```

对照用例不关闭控制连接时，两份已经到达的包也都被记录，这是新排空逻辑应该保留的正常行为。问题是它没有区分两种关联状态。上述解析仍由原函数完成，没有伪造解析结果。

**依据：** [RFC 1928 第 6 节 UDP ASSOCIATE](https://www.rfc-editor.org/rfc/rfc1928#section-6) 规定控制 TCP 结束时该 UDP 关联结束；[本提交 _associate](https://github.com/ixxooxo-alt/proxy/blob/ead8ca886ffe93cce289e96a1fa4ce50910e41ef/tools/check_real_routes.py#L1007) 及当前接收端自己的分类约定。

**建议：** 停止时仍须先核对控制连接生命周期；已观察到 EOF 的关联应结束，不把其后到达的数据报记成合规请求。需要保留收尾残留作诊断时，单独记录，不能并入合规 seen。补成对回归：控制连接打开时排完已到达的包；控制连接 EOF 已确认后才到达的包不进入 seen。原有的源地址、RSV、FRAG 检查继续保留。

**边界：** 这是本机诊断接收端的记账问题，不是代理软件本身接受了这些包。作者正常探针发送后有观察窗口，本轮没有证据说明现有日志恰好发生上述交错，不能据此抹掉全部 UDP 结果。

## R18-F03：逐条 DNS 归属仍按总条数增量，超时后的迟到记录会被认给下一条

**类别：文档不符／测试工具可靠性；优先级中。记账逻辑的反例已确认；官方内核下的触发尚未验证。**

**位置：**

- `tools/check_real_routes.py:464–466`：新增理由称只收不答的替身在客户端等到超时时“也早已记下”。
- 同文件 `507–519`：before 只存 `len(v.seen)`，asked 只比较整个列表是否增长，**没有检查增长的记录是否属于本条 host／qtype**。
- 同文件 `533–537`：只在 hold 非零时按最终 host／qtype 重新识别；普通调用不会修正 dns_got。
- `docs/08:872`：重复上述时间等待足以证明处理完的推理。

**正确与不正确的推理要分开：**

- DnsStub 先 append、再 sendto，所以本次真正收到该替身应答时，可以证明**那个作答替身已记下本次请求**。这一半成立。
- 客户端超时仅表示未等到应答，不能证明另一个接收线程已经运行到 append；上轮 R17-F01 本来就是“收到但尚未记下”的问题。等几秒或 sleep(0.05) 不是同步关系。这一半不成立。
- 即使最终的 close_stubs 已等完，普通调用也不会重算先前已写进 dns_got 的错误归属。

**独立反例：** 执行从本提交 AST 取出的**原样逐条查询循环**；上游使用真实 DnsStub 和真实 UDP。仅在临时加载的模块里重命名 F01 的停止 Event，以隔离 Python 3.12 的兼容问题。入口是一个受控的本机 DNS 调度器，**不是官方 sing-box**：

| 顺序 | 真实收发和受控时序 | 原始循环如何记账 |
|---|---|---|
| 1 | late.example/A 已送到只收不答的国内替身；Event 暂停其解析 | before 中国内替身条数为 0 |
| 2 | 调用本项目原始 dns_query，真实等待其 5 秒 socket timeout，返回 None；替身仍暂停 | late.example 记成“没有应答”，而不是收到它的 dns-cn |
| 3 | 下一条 fake.example/A 的 before 已取完；入口收到第二条查询后才放行第一条，并等它确实记入 seen | 国内条数因 late.example 从 0 变 1 |
| 4 | 入口对第二条返回真实 DNS A 应答 198.18.0.2；第二条没有交给国内替身 | fake.example 被记成 dns-fakeip+dns-cn |
| 5 | 停下替身、读取最终记录 | 国内替身实际只有 [('late.example', 1)]，dns_got 未修正 |

最后两份数据是：

```text
dns_got:
  late.example/A -> 没有应答
  fake.example/A -> dns-fakeip+dns-cn
dns-cn 最终 seen:
  [('late.example', 1)]
```

这证明的是两处错误归属及新增论证的不充分，**不是声称官方 sing-box 已被观察到采用这个调度**，也不是把“查询没应答”错误当作“没有上游查询”的充分证据。

**建议：** 查询归属必须以规范化后的 host＋qtype 记录为依据，并在采样已经同步完成后定稿。将 DNS 查询采样与连接探针分开，在查询专用的一遍停内核、等替身后汇总，同时保留原始返回值用于判断 fake-IP／无应答；不能直接把包含连接探针的最终 seen 全算成设备 DNS 查询，原函数对 hold＋targets 的限制已经说明二者会混淆。为“查询超时后才记下”和“上一条迟到、下一条拿到 fake-IP”补确定性用例。只收窄注释、不改记账，不能消除这个反例。

**依据：** [本提交 singbox_probe](https://github.com/ixxooxo-alt/proxy/blob/ead8ca886ffe93cce289e96a1fa4ce50910e41ef/tools/check_real_routes.py#L457)、[DnsStub 的记录与应答顺序](https://github.com/ixxooxo-alt/proxy/blob/ead8ca886ffe93cce289e96a1fa4ce50910e41ef/tools/check_real_routes.py#L209)、[原始 dns_exchange 的 5 秒预算](https://github.com/ixxooxo-alt/proxy/blob/ead8ca886ffe93cce289e96a1fa4ce50910e41ef/tools/check_real_routes.py#L261)。结论由这些代码与上述实际超时／UDP 反例支持，不依赖猜测 Stash 或 sing-box 的内部线程实现。

## R17-F01 的主要改法与六项测试

**应保留的部分：**

- DNS 按短超时接收；停止后继续处理排队数据，直至一次空闲超时，join 后才关闭 socket。发送端已经结束、没有新发送者时，这个设计能处理“已收到但未解析”和“还在 socket 队列”的两类数据；F01 是名称冲突，不是否定这个设计。
- 六个主核对函数把显式 close_stubs 移到汇总之前；两个出站核对也先调用 recorder.stop，并拒绝线程未结束时的结果。finally 负责异常清理，方向正确。
- SOCKS 保留每个已接受连接的工作线程，先停接入线程再取工作线程清单并等待，避免漏掉清单尚在变化的线程；CONNECT 成功后的 _hold 可被停止标记打断，不必白等八秒。
- timeout 与对方中途断开分别记原因，仍拒绝不完整采样的结果，正确；8 秒是每次 recv 的预算，说明也改准了。
- 境外 DNS 不应答那一遍的 hold 汇总已挪到停止之后，按 host／qtype 聚合。这部分不再有上轮“先汇总再关”的同一缺口；F03 指的是仍在运行中的普通逐条归属。

**关于 5 秒和 IDLE_TIMEOUT＋2 秒：** 它们是检查工具的有界等待预算，不是协议保证。正常解析和本机报文处理通常远少于此；命名修正实验的 57 项未遇到正常关闭误报。高负载或被阻塞时仍可能报未完成，这是保守失败，不能为了“全部通过”忽略。SOCKS 请求的总时间仍可能超过一次 recv 的预算，默认 stop 等待到期返回 False 是正确处理。

**R18-S01（建议，低）：测试比原来强，但“完全不靠时间”的表述仍偏满。** 位置：`tests/test_real_data.py:1002–1005`、`1053–1054`、`1101–1102`、`1157`。Event 固定了接收工作已进入解析的顺序，这确实覆盖旧缺口；然而两个“关闭方还没返回”的断言依赖 `join(0.5)`，未先确认关闭方已经设停止标记。旧实现若该线程恰好未被调度，可能绕过这一观察点。UDP 用例还显式 sleep(0.2) 等待回环投递。应先确认关闭函数已经进入停止阶段，以可读事件确认队列里有第二包，再放行解析；超时只用作防挂死。测试超时分类本身使用 0.5 秒则是被测行为，无需假称可以完全不用时间。162 个变异通常被发现，不能证明所有调度都被确定地覆盖。

另一个低成本收尾建议：各处 `proc.wait(timeout=10)` 超时后 `proc.kill()` 还应再 wait 以确认退出并回收；SOCKS 的总等待截止时间宜用 monotonic。当前没有据此确认正常日志错误，不另计为正式问题。

## 严格版说明与 Stash 的复核

**已落实：** `docs/03:168、257`、`source/strict.yaml`、`generator/strict.py` 及三份严格版的主要注释已经补上“不为判断规则在本机解析”。Loon 不再凭空保证代理端如何解析；Stash TCP 保留“一般”的限定。配置语义没有随这次说明变化，手机不用仅为注释重新导入。

**R18-S02（建议，低）：顶部摘要仍可顺手统一。** `docs/03:8` 的 Loon 严格版仍简称“这类域名不解析”，QX 写“同 Loon”；同文件 `26` 仍写“其余域名不在本机解析”。正文 `225–229` 已明确程序自发 DNS、非 A／AAAA、UDP 和协议等边界，因此这是摘要与正文的措辞一致性建议，不是新确认的泄漏。统一加“为了判断规则”即可，不用再改运行配置。配置注释和 `source/strict.yaml:9` 的“能打开，会慢”也宜写成可能受速度或地域访问限制，未作实测不能保证能打开或必然变慢。

**Stash：** 两份 YAML 相对 r17 语义相同，内置名排除前缀、占位节点和 DNS 都没变。本轮再次运行 `r17_stash_filters_icu.py`，每份 13 条不同正则、2,305 个样本的 ICU／Python 检查通过；这不能确定 Stash 真正的正则引擎。

本轮能打开现行官方 [策略组](https://stash.wiki/proxy-protocols/proxy-groups) 页面，再次确认有 `hidden: true`。它仍不能反推目标 iOS 3.4.0／macOS 4.2.0 一定支持。r18 写成“作者自己的机器未核对、未启用”是诚实的证据分层，不要求启用。

本轮亦打开官方 [DNS](https://stash.wiki/features/dns-server) 和 [远程代理集](https://stash.wiki/proxy-protocols/proxy-providers) 页面；没有找到足以确定 filter 使用 ICU／RE2／regexp2 的官方依据。不能因 Apple 平台或兼容 Clash 就指定引擎。空 provider 的 DIRECT 替代、空组视为 DIRECT，与 r17 记录的风险一致；官方说明仍不足以证明筛选顺序和筛选后的注入行为。四种故障真机验收应继续保留。

这次没有重新下载比对全部 44 项旧文档。r16 当时比对一致的结论只属于当时取到的页面；现行内容后来出现 hidden 等变化，不应混成“旧快照一直等于现网页”。

## 第 22 项与 sing-box 1.14.3

**作者存档与描述一致。**

- `r18_singbox_1143_probes.out` 的七种 SOCKS 组合都收到域名和 IPv4；resolve 的两种收到的是解析后的地址。SS／Trojan／VMess 的直接与 selector 配对记录均收到了域名目标。没有把“客户端握手成功”单独当成“服务端收到了 UDP”。
- 实际配置的版本对照恰好列六个变化：qwen.ai、download.microsoft.com、chatgpt.com，以及切组后的 www.apple.com、www.apple.com.cn、api.bilibili.com；全是 SOCKS UDP 的 received 从 `-` 变 `domain`，DNS 仍是 none。
- `r18_singbox_1143_full.out` 最后确实是“6 处不一致／退出码 1”，不是整套测试退出码 0。正文明确解释人工期望按 1.14.1 编写，两个出站段各有三条版本差异，其余路由、DNS 和扫描一致，**没有把这次 exit 1 隐瞒成全通过**。
- 本轮重新读到的上游源码：[v1.14.1 common/interrupt/conn.go:49](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/interrupt/conn.go#L49) 仅嵌入 net.PacketConn；[v1.14.3:36–43](https://github.com/SagerNet/sing-box/blob/v1.14.3/common/interrupt/conn.go#L36) 改为 N.NetPacketConn 并使用 bufio.NewPacketConn。它和存档的改善方向直接相关。

**本轮独立运行的限制：** 已用既有、前轮核验过官方摘要的 Linux 二进制尝试直接出口／selector 两种最小配置。1.14.1 两次均因 `create netlink socket: operation not permitted` 退出 1；1.14.3 两次均启动退出 -11、无日志。没有完成转发，不能把空 seen 解读成 UDP 丢包。这些是本审核环境的限制，不推翻作者另一环境的运行记录，也不能写成本轮成功重跑了 1.14.3。未重复下载同一份二进制制造“新证据”。

**决定落实合理：** `docs/00` 追加原话“22 项选 3”“那就 1”，`docs/06:14–20` 据此先核对、再维持配置；两份 sing-box JSON 相对 r17 逐字节相同。没有替使用者改做方案②。

① 中浏览器可能退回 TCP、语音／游戏／UDP-only 未必能退回、1.14.2 未测、真实节点和 SFA 的 TUN＋fake-IP 路径未测，主要代价已列。② 仍保留作用范围、可切 DIRECT 的组、DNS 自身回路、失败、缓存、A／AAAA、额外 RTT、CDN 和回包验证等要求，也正确说明不能把 resolve 简单放到终止 route 动作之后。

应继续把“1.14.3 在所测 Linux 代理端口路径不再丢这类包”作为事实，把“用户升级后可解决其手机问题”作为待真机验证的推断。不能由两个版本的有限探针推广成所有未来版本、协议、设备均通过；建议以实际打包内核版本和真机日志核对升级效果。F02 说明诊断工具仍需补强，但本轮没有证据证明存档的这六个变化是假象。

## 数字、产物、快照与交付包

| 核对项 | 本轮结果 | 证据性质 |
|---|---|---|
| 固定提交及版本 | ead8ca886ffe93cce289e96a1fa4ce50910e41ef；2026.10.15-1／1.10.1 | Git、本地代码 |
| build.py --check | 产物与统一源一致，含 manifest | 独立运行 |
| 统一源＋生成器摘要 | 7ff519e8ee51dd7ebcd85f6960d47f8cc5e8d79132559754f9d2da70fb2c56a4 | 重新生成核对 |
| 代码状态哈希 | bb52375baa680b56ea48fc8515f0ea839eb872c0fc13de6980225a5641d7f622 | 独立重算，与定稿记录一致 |
| 产物 | 14 个登记文件摘要全部匹配；加 manifest 共 15 个 | 独立重算 |
| 相对 r17 的运行配置 | YAML 语义相同；Loon／QX 去注释后条目相同；两份 sing-box 与四份规则文件逐字节相同 | 独立比较 |
| 版本对比报告 | 重算 222 行；除命令多出本轮 --out 路径，正文与存档一致 | 独立运行 |
| real_sets.json | 恰好三个叶字段变化：generated、source_version、mihomo/config_sha256；所有路由／DNS／出站结果不变 | 独立结构比较 |
| 原始 r18 单元测试 | 311 项，1 failure／4 errors，170.618 秒，见 F01 | 本轮 Python 3.12.14 实跑 |
| 临时修正 F01 的 test_real_data | 57 项 OK，25.281 秒；不是全部 311 项重跑 | 单独修正实验 |
| 作者完整测试日志 | Python 3.13.16／PyYAML 6.0.1，311 项、262.090 秒、OK | 复核存档，不冒充本轮结果 |
| 变异日志 | 正好 162 条 [发现] 记录，M1–M162 唯一、无缺号；127＋35＝162 | 复核存档；未全量重跑 |
| 官方路由等完整批次 | 存档为 270 个不同目标，各版结果对应；本轮未成功重跑官方内核 | 复核存档及快照 |
| 上轮报告存档 | 18,140 字节；SHA-256 abdd917e8b07cec91746c94214fe50d9ddbb2ecdf734c85605e30cb325f10e36，与原审核 PR 内容一致 | 独立重算 |
| Git 工程文件数 | 231 个 | 独立计数；不能替代 ZIP 校验 |

`docs/05` 对事实／推断／未验证的主要划分合理：官方 Linux 代理端口观察与 SFA 真机推断已分开，Stash 数据近似与模拟器边界已标明。存档时间线的两段变异、重启复核与第二遍交付检查没有发现数字矛盾。需要修正的“支持版本”“逐条查询一定已记下”和关联生命周期见 F01–F03；测试数量、变异发现率和相同快照都不能代替这些边界验证。

**ZIP 的明确边界：** 本轮提供的消息有文件名、大小和摘要，但没有取得可读取的 `proxy-rules-review-2026.10.15-r18.zip` 原始字节；按确切文件名搜索亦未取得。因此没有核验声称的 2,821,162 字节和 `61ab29b1e74364f41f6fea771844e5b950317824bdc43c35a03cc402ad655efa`。没有运行原包的 verify_package.sh，也不以重新打一个 ZIP 冒充原包校验。拿不到原包不是认定交付包错误，亦不妨碍上述固定提交的审核。

**交付建议：** 先修 F01–F03 的核对工具与对应回归，再在明确记录的 Python 版本下重跑受影响的检查；继续保留 Stash、Loon、QX、SFA 真机尚未验收的状态。无需因此改用户已经选定的 DNS／分流策略或发布 main。

# r19 送审稿审核：08051e5

审核日期：2026-10-16（UTC+8）。仓库 `ixxooxo-alt/proxy`，分支 `claude/r12-gpt-review-handling-q4onlv`，固定提交 `08051e541306ac26ea6943558abc7aab76089306`；基线 r18 `ead8ca886ffe93cce289e96a1fa4ce50910e41ef`。

这是送审稿审核，不是 r19 最终交付验收。先读了 `00-审核说明.md` 的送审稿说明、`docs/08-外部审核记录.md` 第 14 轮。未改 main、生成配置、原始需求或已有证据；没有合并 PR。

## 结论

R18-F01 已修复；R18-F03 的实际实现正确；R18-F02 修掉了上一份报告的固定复现，但清队列过程中断线还有一个遗漏。新发现 **1 项核对工具问题（中）**，另有 **1 项补测试建议（低）**。没有确认新增的生产配置导入失败、分流错误或实际 DNS 泄漏。

大白话：这次不是换了验证机器才报错。原样 315 项测试在我这里的 Python 3.12 上全部通过。剩下的是测试节点“开始收尾时还连着，但收尾到一半才断线”的判断遗漏；另有一段测试没有真正测到生产函数里的查询类型筛选。

`dist/`、`source/`、`generator/` 和 `tests/data/real_sets.json` 与 r18 均无 Git 差异。这两项本身不要求手机重新导入配置。

## 已确认的问题

### R19-F01：UDP 清队列只检查一次控制连接，清到一半断线后的包仍记成合规

- **分类 / 严重程度**：文档不符 / 测试工具可靠性；中。不是生产配置的安全漏洞。
- **位置**：`tools/check_real_routes.py:1036–1047`，尤其 `1039–1040` 的一次性检查和 `1042–1047` 的内部循环；相关回归测试 `tests/test_real_data.py:1206–1245`；`docs/08-外部审核记录.md` 第 14 轮 R18-F02 的完成描述需相应补充。
- **确认方式**：原样 r19 代码，本机真实 TCP/UDP socket，用 Event 固定先后；服务端 `select` + `MSG_PEEK` 已看到 EOF 以后才发送最后一个包。没有替换地址解析器或判定结果。

**为什么还会错**：`_control_closed(c)` 只在进入清队列分支时调用一次。进入 `while True` 后，不再看控制连接，持续 `recvfrom` / `_take_udp`，直到 UDP 队列暂时为空。第一次检查为“还开着”，不代表整个清队列期间一直开着。

固定复现顺序：

1. 建立 UDP ASSOCIATE，发送 `first.example`，在处理处暂停。
2. 排入 `drain.example`，启动 `rec.stop()`，确认 `_closing` 已设置，再放行第一个包。
3. 第二个包在停止分支的清队列循环里被取出，处理处暂停。此时新增的一次控制连接检查已经通过。
4. 关闭客户端控制连接，并在服务端确认可以读取 EOF。
5. **这以后**才发送 `after-close.example`，放行第二个包。

原样结果：`stop()` 返回 `True`；`seen` 包含三个域名，包括 `after-close.example`；`invalid == []`。保持控制连接打开的对照也记录三个包，符合对照预期。上一轮的“开始收尾前就已断线”复现另行重放：r19 正确地只保留第一个包，因此不是说这一轮没有修任何东西。

**依据**：[RFC 1928 第 6 节 UDP ASSOCIATE](https://www.rfc-editor.org/rfc/rfc1928#section-6) 规定该 UDP 关联随建立它的 TCP 连接结束而结束。项目正常接收分支 `1048–1054` 也在每一轮优先处理控制连接结束。停止分支不应只靠进入时的一次检查维持这项保证。

**建议修复**：清队列每次准备接收下一包时继续检查控制连接；看到 EOF / 连接错误立即结束关联，不把之后的包加入合规 `seen`。可以复用控制连接优先的接收逻辑，避免正常运行、停止时各自维护不同语义。至少新增上面“清到一半才断线”的 Event 回归，与“始终开着、排队包保留”“进入清队列前已断线”两种情况成组。已接收且发生在断线之前的第二个包不必追溯删除。

在内存里仅给内层循环每一轮补上 `_control_closed` 检查后，同一探针不再记录 `after-close.example`，保持打开的对照仍记录全部三个包。这个实验验证建议对本反例有效，不表示跨 TCP/UDP 的所有极限交错已经被形式化证明；没有改仓库代码。

**影响边界**：确认的是接收端在上述受控交错下误记，未证明官方内核交付核对时出现过。正式调用方通常先结束内核再停止接收端，此时控制连接往往早已关闭，所以本例不证明 r18 或这次快速检查的结果错误，也不推翻第 22 项的 1.14.3 存档结论。

## 建议与测试覆盖

### R19-S01：F03 新测试验证了结果格式，但未守住实际函数中的名字＋类型匹配

- **分类 / 严重程度**：建议；低。当前 F03 实现没有被本项判为错误。
- **位置**：`tests/test_real_data.py:1274–1290`，特别是 `1283–1284`；`1292–1314`；实际匹配位于 `tools/check_real_routes.py:550–553`。

`test_dns_attribution_uses_name_and_type_after_stubs_stop` 自己在测试内部写了一遍 `(host, qtype) in v`，然后只把算好的标签列表传给 `_dns_where`。而真正按名字和类型匹配的代码在 `_singbox_run`。另一个新测试把 `_singbox_run` 整个替换为 fake，只验证两次调用的拆分；其 AST 检查只排除 `len(….seen)` 写法。这样可以验证格式分支与拆分，但不能证明实际筛选和停下后归属都受回归测试保护。

**已验证的覆盖缺口**：在独立临时副本中，仅将生产函数的一行：

```python
asked = [k for k, v in stubs.items() if key in v.seen]
```

故意改成忽略查询类型：

```python
asked = [k for k, v in stubs.items() if any(q == key[0] for q, qt in v.seen)]
```

执行 `python3 -m unittest discover -s tests -p test_real_data.py -v`，**61 项仍全部通过，26.136 秒**。这不是全套变异检查的结果，也没有把它冒充成已有 M163–M166 之一。它说明同名 A / HTTPS 的实际筛选以后写坏，当前相关测试未必发现。

**建议**：调用真实 `_singbox_run`，只替换外部进程启动 / 就绪检测等边界；让真实 DNS 替身在 Event 放行前尚未记下 `late.example/A`，在收尾时才完成，另有 `fake.example/A` 和 `late.example/HTTPS`。断言实际返回值，验证只按名字的变异必失败。也可把真实归属逻辑提取到接收 `host + qtype + stopped stubs` 的函数，用行为测试覆盖并保留真实调用链检查；不要只在测试里重写筛选表达式。

我另外用真实替身、真实 UDP 以及受控进程边界运行了原样 `_singbox_run`：在 `terminate()` 前 `seen` 仍为空，收尾时才放行记录，最后三个结果分别为 `dns-cn`、`dns-fakeip`、`没有服务器收到查询`，三个替身均已停止。因此当前实现本身经这个反例验证是对的。该探针把客户端超时结果设为 `None`，未声称运行了真实 sing-box 或实际等待了五秒超时。

## 上一轮逐项复核

| 项目 | 本轮判断与依据 |
|---|---|
| R18-F01 | 改名 `_dns_stop_event` 正确；原样 `DnsStub.start(); stop()` 在 Python 3.12.14 返回 True，315 项全过。Thread 成员并集防回归测试有针对性，且与 [Python Thread 子类只覆盖构造器 / run 的约定](https://docs.python.org/3.12/library/threading.html#thread-objects) 一致；静态名字检查不代替多版本运行。 |
| R18-F02 | 原报告的“进入收尾前已断线”复现已通过；仍有 R19-F01 所述“清队列期间断线”遗漏。 |
| R18-F03 | 按 `(规范化名字, 查询类型)`、在 `close_stubs` 完成以后归属，且查询 / 连接分别启动内核，修复方向和实际实现正确。结果格式保留 fake-ip / 无应答信息；hold 的排序及已收到查询优先行为与旧逻辑一致。测试还应补 R19-S01。 |
| mihomo 是否也必须拆分 | `mihomo_dial_probe:726–729` 拒绝所有重复规范化名字，包含查询用例彼此重复及查询 / 拨号重名。因此当前不具有 sing-box 同名 A / HTTPS 和连接混记的前提；不应仅因它按名字汇总就认定这批结果错。若今后允许同名不同类型，须同步改归属机制。 |
| 分两遍的其他影响 | 查询遍不再给连接遍预热 DNS / fake-IP 缓存；两次临时配置均移除 `experimental`，没有共享持久缓存。这改变了检查条件，测的是各自新内核下的查询和连接，不再覆盖“先查询后连接共享状态”的交互。对于分别核对 DNS 与路由的既定目的，拆分合理；如要验证缓存交互，应另加明确场景，不能混回去靠总记录猜归属。 |
| R18-S01 | 等待 `_dns_stop_event` / `_closing` 后再观察提前返回，比原来稳妥；UDP 用 `/proc/net/udp` 的可观察条件替代固定 sleep 合理。两项 UDP 测试在没有该接口的系统上会 skip，源码已明确，不应将它们描述成所有系统都运行过。仍保留的 0.5 秒是否提前返回观测已披露，不另列重复问题。 |
| 收尾建议 | 六处 `kill()` 后补 `wait()`、接收端期限改 `monotonic()`，方向正确，没有发现由此次修改引入的新错误。 |
| R18-S02 | `docs/03` 两处摘要已加“为判断规则”的限制；“能打开，会慢”注释延到最终版与送审说明一致，本轮不把已明确延期的修改报为漏修。定稿前仍须落实。 |

## 检查结果及边界

独立执行环境：Linux，Python 3.12.14，PyYAML 6.0.3。全部日志输出到仓库外，固定提交工作树保持干净。

| 本轮独立检查 | 结果 |
|---|---|
| `python3 build.py --check` | 产物与统一源一致，含 manifest。 |
| `python3 -m unittest discover -s tests -v` | **315 项通过，169.533 秒，0 失败 / 0 错误 / 0 跳过**。 |
| `python3 tools/check_mutations.py --check-edits` | **166/166** 改动能套上；没有运行 166 类全套变异。 |
| F01 最小复现 | 正常返回 True，不再 TypeError。 |
| 原 R18-F02 复现重放 | 已关闭场景只记第一个包；保持打开场景保留排队包。 |
| F03 实际函数的受控迟到记录 | 正确区分迟到 A、另一个名字的 fake-IP 和同名 HTTPS。 |
| 清队列中断线的新探针 | 确认 R19-F01；内存中最小补检查后本反例消失。 |
| 忽略查询类型的临时变异 | 相关 61 项仍通过，确认 R19-S01 的覆盖缺口。 |
| 修改的三个 Python 文件按 3.10 grammar 解析 | 通过；仅语法检查，不等于在 Python 3.10 上运行通过。 |
| 产物 / 规则源 / 生成器 / 官方快照 | 与 r18 无差异；没有改手机配置内容。 |
| 上轮报告归档 | 与我交付的 r18 报告逐字节一致，SHA-256 `c7ac5471f11bb57373e4e9002953d20539d15b3301d0d5b67bf733afa34e8f53`。 |

没有确认到其他只在 Python 3.13 成立的新增代码。本机仅实际运行 3.12；作者在 `docs/08` 记载 3.11 / 3.12 / 3.13 均通过，本轮没有独立重跑 3.10、3.11、3.13。3.10 支持下限仍缺运行证据，但已经明确披露，不应把“没有测试”写成“确认不兼容”。

作者这次官方 mihomo / sing-box 全套结果与快照一致，是 `docs/08` 的运行记录陈述；送审稿明确没有提交那次日志。我本轮没有独立重跑官方内核全批次，不能将这句话改标成审核方已复现；上轮审核环境的官方内核启动限制也不能当成内核丢包。原快照未改本身不证明新工具重跑一定相同。

按使用者“先审后跑”的安排，未定稿、未跑满 166 类变异、未更新正式版数字、未打包，都不是这一稿的交付缺陷。Stash 真机、正则实际引擎、订阅失败四种情况、SFA / TUN、真实 DoH 和性能仍沿用已列出的未验证边界，本轮没有新增实测依据。

## R19-F01 可独立运行的复现

将以下内容存成仓库根目录外的脚本，在 **08051e5 仓库根目录**执行 `python3 /脚本路径/probe.py`。只使用本机回环和 `.example` 合成名字；不改配置或文件。

```python
import json
import select
import socket
import struct
import sys
import threading
sys.path.insert(0, "tools")
import check_real_routes as c

def packet(host):
    return b"\0\0\0\3" + bytes([len(host)]) + host.encode() + struct.pack("!H", 443) + b"x"

first, drain, go_first, go_drain = [threading.Event() for _ in range(4)]
rec = c.Socks5Recorder()
take, associate = rec._take_udp, rec._associate
accepted, result = [], []
rec._associate = lambda s, *a: (accepted.append(s), associate(s, *a))[1]

def gate(data, *args):
    if b"first.example" in data:
        first.set()
        assert go_first.wait(10)
    if b"drain.example" in data:
        assert rec._closing.is_set()
        drain.set()
        assert go_drain.wait(10)
    return take(data, *args)

rec._take_udp = gate
rec.start()
control = socket.create_connection(("127.0.0.1", rec.port), timeout=5)
stopper = threading.Thread(target=lambda: result.append(rec.stop()))
try:
    control.sendall(b"\5\1\0")
    assert control.recv(2) == b"\5\0"
    control.sendall(b"\5\3\0\1" + bytes(6))
    reply = control.recv(10)
    relay = (socket.inet_ntoa(reply[4:8]), struct.unpack("!H", reply[8:10])[0])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.sendto(packet("first.example"), relay)
        assert first.wait(5)
        udp.sendto(packet("drain.example"), relay)
        stopper.start()
        assert rec._closing.wait(5)
        go_first.set()
        assert drain.wait(5)
        control.close()
        assert select.select(accepted, [], [], 5)[0]
        assert accepted[0].recv(1, socket.MSG_PEEK) == b""
        udp.sendto(packet("after-close.example"), relay)
        go_drain.set()
    stopper.join(5)
    assert not stopper.is_alive()
    print(json.dumps({"stop": result, "seen": rec.seen, "invalid": rec.invalid}, indent=2))
finally:
    go_first.set()
    go_drain.set()
    control.close()
    rec.stop()
```

本轮观察的原样输出中 `seen` 含 `first.example`、`drain.example`、`after-close.example`；修好后最后一个不应出现。示例握手 `recv` 是本机最小探针，正式回归测试可用完整长度读取辅助函数。

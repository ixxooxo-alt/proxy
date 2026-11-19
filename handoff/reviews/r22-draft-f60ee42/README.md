# r22 送审稿审核 · f60ee42

**结论：先修再定稿。** 没有发现 20 份公开配置普遍不能导入，没有观察到使用者的订阅、凭据或设备流量已经泄漏。但已确认三类会影响交付的事：一条不合规的 SS2022 输入可以使整份私密 SFA 配置无法启动；固定直连在域名别名或特定本地补充下不能保证原定去向；一个逐文件正确、测试全过的包会被正式验包命令判失败。反过来，验包脚本也会在文件未通过比对时运行包里的代码。

**对象**：会话分支上的 `f60ee428e4bfc5472b1450f6bfbcc553322e83f4`，对照 `b9a9f14`。未把 `main` 或审核对象之后的提交算进来。范围包括 `166f5e4` **之后**的实现改动：`be463a1` 修改了打包脚本以保留 `.gitattributes`。以下“实跑”指本次运行；“源码确认”指固定版本在所述输入下的代码路径，不等于在手机或公网观察到了后果。下文例子只用公开服务、地名、保留域名和标量。

## 已确认的问题

### R22-F01　包与提交不同，验包仍执行包里的程序

**严重程度：安全或泄漏，高；发布工具。**

**位置与依据：**[handoff/release/verify_package.sh:52–76](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/verify_package.sh#L52-L76)、[handoff/release/selftest_package.py:99–119](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/selftest_package.py#L99-L119)。内容比对失败只在 `FAILED` 数组里记一笔；只要解开的目录有 `build.py`，就继续运行它，正常模式还发现并运行包里的测试。自测甚至要求不符提交的测试实际执行。最终退出 1 是对的，但此时已经执行过未经核对的代码。

**建议：**路径、文件集合或内容比对失败后，保留诊断并立即返回非零；后续可只用可信工具做静态扫描。测试“构建失败 / 测试失败”的场景应当来自与指定临时提交**相符**的夹具，另断言比对失败时执行阶段从未开始。本条是控制流程审阅，没有运行不可信程序，也没有证据表明交付包被动过。

### R22-F02　完全正确的包被正式验包命令判失败

**严重程度：建议，高；阻断发布验收。**

**实跑：**从审核提交新打的包有 650 个文件，逐个文件及生成检查均通过；解包副本的 unittest 跑了 369 项、无跳过、结果 `OK`。不带 `--skip-tests` 的验包命令却退出 **1**，唯一失败理由为“测试：最后一行不是 OK”。

**位置与依据：**[handoff/release/verify_package.sh:69–77](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/verify_package.sh#L69-L77) 合并标准输出与错误输出，并把整个文件的最后一行当 unittest 的结果。Python 的 [TextTestRunner](https://docs.python.org/3.12/library/unittest.html#unittest.TextTestRunner) 默认把汇总写到标准错误；本次汇总之后还有测试自身缓冲的标准输出。[handoff/release/selftest_package.py:80–87](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/selftest_package.py#L80-L87) 对正确包使用 `--skip-tests`，所以“24 项自测通过”和这次失败不矛盾。

**建议：**让一个可信的测试运行器以 `result.testsRun > 0`、`result.wasSuccessful()` 和进程退出码作判据；日志留作诊断。给正确包加一项不带跳过开关的验收，覆盖测试本身会打印文字的情况。

### R22-F03　ZIP 的同名成员未纳入逐项核对

**严重程度：安全或泄漏；交付包内容核验。**

**位置与依据：**[handoff/release/package_check.py:37–63](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/package_check.py#L37-L63)。先取得成员文件名，解包后再按名字 `z.read(n)`，并建成以文件名为键的字典。同名成员因此合成一条；集合、数量、内容和解包后的扫描都不能证明 ZIP 的每一个物理成员都与提交一致。标准库[明确区分按名称与按 ZipInfo 读取](https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.open)。这是验包判据的问题；没有证据表明本次正确包含重复项。

**建议：**解包前对每个 `ZipInfo` 检查并规范化成员路径，重复目标以及文件与目录冲突立即拒绝；按唯一条目比对，再解包。回归测试用两条同名、无敏感内容的成员即可。


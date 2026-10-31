# r21 送审稿审核：c29d633

审核日期：2026-10-31。对象为 `ixxooxo-alt/proxy` 的 `claude/r12-gpt-review-handling-q4onlv`，完整提交 `c29d63369b6f4810979de84da1264c7e9f2815b7`。对比基准是只改文档的 r20b `f45eb89`。没有审核或修改 `main`。

**结论：三个值的生成正确，没有确认新的导入失败、分流错误或泄漏。确认三项文档问题；Stash 嵌套组的运行效果仍需真机验证。** 本 PR 只增加审核报告，每项问题单独提交；不修改配置、生成器、已有证据或需求原话。

## 确认的问题

| 编号 | 严重程度 | 结论 |
|---|---|---|
| [R21-F01](R21-F01.md) | P2 / 文档不符 | sing-box 闲置超过 30 分钟时，定时器可能仍没停；下一次拨号不一定立即重测。 |
| [R21-F02](R21-F02.md) | P3 / 文档不符 | Stash 官方文档已明确同一代理共享测速结果，验收表不该说“文档没写”。 |
| [R21-F03](R21-F03.md) | P3 / 文档不符 | 当前审核入口、框架说明和 README 仍夹着 r20 的旧间隔、旧的“完整版逐字节未变”及变异数量。 |

每个文件包含位置、依据和建议。F01 的反例来自指定版本源码，不是手机实测；F02 不把共享结果等同于探测请求必定去重。

## 配置和校验核对

| 项目 | 当前产物 | 校验及测试结论 |
|---|---|---|
| Stash 完整版，两份 | 各 57 个 select 为 `-1`；其余各 24 个自动类组（12 fallback、6 url-test、6 load-balance）为 `300` + `lazy: true` | `emit_stash._group_dict` 正确区分两版；`verify.check_stash(simple=False)` 拦漏写、非整数/布尔值、选择组非负和自动类组非正；测试另核对精确值及 lazy。 |
| Stash 简易版，两份 | 各 51 个 select 为 `3600`，没有 lazy 字段 | `check_outputs` 正确传 `simple=True`，避免套用完整版的负数要求；`check_simple` 按规则源核对精确整数值。标准版和严格版均有覆盖。 |
| sing-box 简易版，1.12 / 1.14 | “境外DNS”是 `600s` / `30m` | emitter 只对 `foreign_dns` 角色采用新间隔；`check_simple` 校验 600 秒，通用检查校验 interval 不超过 idle_timeout，测试核对精确的 `600s` / `30m`。mihomo 仍是 3600 秒。 |
| 模型层 | 三项均从 `source/project.yaml` 读取 | `_check_stash_interval` 按项目约束拒绝 0、1–59、小数、字符串和布尔值；“至少 60 秒”是项目限制，不是从 Stash 官方文档推出来的最小值。sing-box 间隔另要求至少 60 的整数。 |
| M201–M209 | 9 类针对遗漏 interval、误用旧值或删掉相应校验 | 改动与当前代码对应，相关测试有直接断言；归档试跑日志显示 9/9 被发现。本次未重跑这 9 类或全套变异。 |

校验范围要准确描述：完整版 Stash 的写盘前检查查的是“选择组负数 / 自动类正数”，不是所有参数都精确等于源值；精确的 `-1`、`300`、`lazy: true` 另有测试保护。sing-box 写盘前检查的 idle_timeout 是大小关系检查，精确的 30 分钟也由测试保护。没有把这两层合说成写盘前已经逐值核对。

一个小建议（不作为当前配置错误）：`model._check_stash_interval` 会接受完整版选择组的正数，而 `check_stash` 随后必定拒绝。若该设置今后提供给维护者调整，可在模型层就明确“完整版目前只允许负数”，或统一两层的策略，避免通过源校验后才报错。当前值 `-1` 不受影响。

## Stash 嵌套组及使用者要求

官方[策略组文档](https://stash.wiki/proxy-protocols/proxy-groups#定时执行延迟测试)支持 `select` 的 interval、负数关闭、嵌套递归测试、lazy 跳过未使用的组；官方[延迟测试文档](https://stash.wiki/proxy-protocols/proxy-benchmark)说明结果按代理共享。因此给选择组写 `-1`，保留 fallback / url-test / load-balance 的正数间隔，有文档层面的依据。

**仍未证实**：父 fallback 递归测试时，具体如何对待子 select 的 `-1`，以及所选子节点健康状态怎样反映到组成员。没有找到目标 iOS 3.4.0 / macOS 4.2.0 的公开实现或足够明确的版本说明，不能报成确定错误，也不能保证自动兜底完全不受影响。当前保留真机验收是合适的。

建议在 `docs/09` 第 1c 节第 16 步把两种情况分别记录：手动节点也在自动候选里，以及手动节点只在宽筛选里、不在严筛选的自动候选里。后一种更能区分“父 fallback 真正检测了手动成员”和“其他自动组恰好测了同一节点”。检查正常、失效、恢复后的最终出口；仅看显示的毫秒数不够。这个建议不要求现在制造真实节点故障，也不要求公开节点资料。

`docs/00:1259–1280` 的解释结合此前“保留同地区自动兜底”的上下文是合理的，也与本次用户明确列出的三个值一致。本轮不另提需求确认。对外宜说“关掉 Stash 完整版**选择组自己的定时测速**”；它不表示全部测速停止，也不表示选择组里的延迟数字不会再被其他组更新。

sing-box 的 `600s` / `30m` 合法：官方 [URLTest 文档](https://sing-box.sagernet.org/configuration/outbound/urltest/)给出这两个字段，v1.14.1 [`NewURLTestGroup`](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/group/urltest.go#L223-L234)要求 interval 不大于 idle_timeout。健康节点因测速历史较新而跳过部分轮次的解释有源码依据，但“约 20 分钟”仍是条件性的估计，不是精确调度保证。F01 修正的是停止/重启的状态边界，不否定选 10 分钟这个取舍。

## 独立核对及边界

- Python **3.12.14**：`python3 -m unittest discover -s tests -v`，**348 项，266.528 秒，OK，无 skipped**。
- `python3 build.py --check`：通过，含 manifest。
- `python3 tools/check_mutations.py --check-edits`：**209/209** 改动可套用。这不是 209 类变异都被测试发现。
- 独立比较 r20b 和当前产物：去掉文本注释或解析 YAML/JSON 后，仅有两份 Stash 完整版各 57 个 interval、两份 Stash 简易版各 51 个 interval、两份 sing-box 简易版各 2 个时长字段变化。两份 sing-box 完整版逐字节相同；规则文件逐字节相同。
- `1366d17` 与被审提交的 `build.py / generator / source / dist / tests / tools` 相同，快速检查日志可以对应到当前代码。归档的 Python 3.13、3.12、3.11 日志各 348 项 OK，官方程序等检查均记录退出码 0；M201–M209 试跑日志合计 9/9。
- `docs/05` 明确标注仍是 r20 的验收；`docs/evidence/` 与 r20b 无改动。送审阶段保留旧数字是正确的，不要求提前换成 r21 全套通过。
- 本次没有重跑 `tools/run_checks.sh`、全套变异或打包。当前运行环境尝试启动官方 sing-box 1.14.1 时，在初始化阶段报 `create netlink socket: operation not permitted`；所以没有新增官方内核运行时实测。这个环境限制没有作为项目错误报告。
- 没有 Stash / SFA 真机验收。未把旧 E6/E7 实验台结果当成 r21 新间隔的实测。

所有已确认问题都在说明层；本轮没有要求改动用户选定的三个值，也没有要求重写项目。

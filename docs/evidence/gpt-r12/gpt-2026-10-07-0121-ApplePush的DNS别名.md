**有 3 个可以考虑的补充，都是推送服务的 DNS 别名。**

你现在的 `push.apple.com` 后缀规则已经覆盖 `init`、`courier`、`api`、`sandbox` 等子域，不需要逐个重复添加；苹果官方列出的也是 `*.push.apple.com`。:chatgpt-content-reference{index="0"}

我刚实际查询 DNS，还确认了这些别名：

| 可补充的后缀 | 本次查询中对应的连接 |
|---|---|
| `push-apple.com.akadns.net` | 推送初始化、API，以及 courier 的最终解析别名 |
| `courier-push-apple.com.akadns.net` | `1-courier.push.apple.com` 的解析别名 |
| `courier2-push-apple.com.akadns.net` | `1-courier2.push.apple.com` 的解析别名 |

**这三条属于可选补充。** 如果客户端按原始 `push.apple.com` 域名分流，现有规则已经能接住；只有连接被识别成这些别名时，补充规则才有作用。因此，它们的存在不代表上一版一定漏分流。

要补就限定这三个后缀，统一指向 **Apple Push**，不要扩大到整个 `akadns.net`。

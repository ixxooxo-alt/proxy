简易版设计用的 sing-box 一次性实验（2026-10-20 运行，2026-10-21 整理进仓库）

目的：回答使用者对“简易版”的几个问题——sing-box 上能不能做“手选、挂了自动换”，
自动测速组在节点挂了以后多久换走，检查间隔 300 秒 / 180 秒的差别，“国外默认”选了一个
挂掉的单个节点会连累什么。结论写在 docs/10-简易版框架.md。不属于 tools/run_checks.sh，也不进出版流程。
（当时的结论写在提交 b7b38fd 里按方案 ③ 写的那一版 docs/10；使用者 2026-10-21 改定纯手选以后 docs/10 重写了，
新版第 6.1 节引用了这里的 dnsdep-* 结果。）

环境
- 官方二进制：handoff/setup_env.sh 登记的 sing-box 1.14.1、1.12.0、1.14.3（SHA-256 与登记的一致）。
- 全部只监听 127.0.0.1。lab.py 起本机的最小 SOCKS5“节点”和一个目标 HTTP 服务：
  /generate_204 回 204（给自动测速用），/hello 回 200 并写明经哪个节点来；节点可以随时改成
  down（拒绝连接）、hang（接受连接但不回话）、freeze（已有连接不断也不传数据）。
- 不是手机，不是真实网络，节点是 SOCKS5；“挂了”只模拟了上面三种，没有模拟丢包、限速。

文件
- driver.py：起 lab.py 和 sing-box，按时间表改节点状态、发请求、切选择组，经 clash API 记下
  各组当前选中的节点（now）。用法：
    python3 -I driver.py <sing-box 二进制> <场景名> <输出目录> [interval 秒，默认 30] [端口偏移]
- summarize.py：把 events.jsonl 整理成相对时间线。用法：python3 -I summarize.py <输出目录> [--probes]
- dnsdep.py：“国外默认”= 一个已停掉的节点时，路由里为判断 IP 规则做的解析（dns-foreign 经国外默认）
  失败会怎样。用法：python3 -I dnsdep.py <sing-box 二进制> <输出目录> <端口偏移>
- hangtypes.py：节点“接受连接但不回话”时，SOCKS、Shadowsocks、VMess、Trojan 出站的自动测速能不能
  按时判失败。用法同 dnsdep.py。配置里的密码、UUID 是测试用的占位值，不是真实凭据。
- runs/<版本>-<场景>[-i<interval>]/：每次运行的 config.json（实际交给内核的配置）和 events.jsonl；
  dnsdep-*、hang-* 另有 sing-box.log。版本前缀：114 = 1.14.1，112 = 1.12.0，1143 = 1.14.3；
  没有 -i 后缀的是 interval 30 秒。早几次运行用的是同一脚本较早的版本（之后只加了场景和 freeze），
  每次实际用的配置以该目录下的 config.json 为准。
- summary.out：2026-10-21 对 runs/ 下每个目录（dnsdep-*、hang-* 除外，它们的格式不同）重跑
  summarize.py --probes 的输出。
- typecheck/：写 fallback / load-balance 等类型、interval 大于 idle_timeout 时 sing-box check / run 的输入。

关键结果（时间都是 summary.out 里“节点停掉”到“改走别的节点”之间的秒数；节点都是在一次测速后约 5 秒停掉，接近最坏情况）
- 114-gen_traffic-i300：一直有请求、连接被拒，310.1 秒停掉，605.1 秒换走，用了 295.0 秒，期间 147 个请求失败。
- 114-gen_traffic-i180：同上，interval 180 秒，190.1 → 365.2 秒，约 175 秒，87 个请求失败。
- 114-gen_idle-i300：停掉时没有请求，310.0 → 905.4 秒，595.4 秒（约 2 个 interval）。
- 114-gen_idle-i180：同上，190.1 → 545.4 秒，355.3 秒。
- 114-gen_* / 112-gen_* / 1143-gen_*（interval 30 秒）：三个版本结果相同（差 0.1 秒以内）。
- 114-simple_onelayer、112-simple_onelayer：jp = selector[jp-auto, 各节点]，fd（国外默认）= selector[jp, 各节点]；
  在 jp、fd 里直接选节点立即生效；选中的节点停掉后不会自动换（请求一直失败）。
- dnsdep-1.14.1、dnsdep-1.12.0：国外默认 = 正常节点时，没被规则认出的域名先解析、再连接，成功；
  国外默认 = 已停的节点时，sing-box.log 里是 “router: lookup … connection refused”，连接被关掉。
- hang-114：四种协议都在测速开始后约 15 秒报 “context deadline exceeded”（单次测速超时固定 15 秒）。
  hang-112：1.12.0 上只有 SOCKS 节点那一轮测速一直结束不了，之后的测速都被跳过。
- 114-mf_urltest_trick、114-mf_trick_50000（及 112-）：用 urltest 套 selector 凑“手动优先”不可靠
  （容差 65535 溢出；不切回；改选不生效；1.12.0 与 1.14.1 行为不同）。不采用。

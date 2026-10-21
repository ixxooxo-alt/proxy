简易版设计用的 mihomo 一次性实验（2026-10-21；不属于 tools/run_checks.sh，也不进出版流程）

目的：方案 ③ 在 mihomo 上的写法、成员顺序和默认选中；“X·自动”在节点挂了以后多久换走；
“国外默认”选了一个挂掉的单个节点会连累什么。结论写在 docs/10-简易版框架.md 第 4.2、5.3、六节——指提交 b7b38fd 里
按方案 ③ 写的那一版 docs/10；使用者 2026-10-21 改定纯手选以后 docs/10 重写了，章节号不再对应（文末 E6、E7 两项指的是新版）。

环境
- 官方 mihomo v1.19.31（SHA-256 与 handoff/setup_env.sh 登记的一致），源码提交 ab405bad。
- 全部只监听 127.0.0.1。scripts/lab.py 起本机的最小 SOCKS5“节点”、测速用的 HTTP 服务（实验台没有 TLS，
  所以测速地址用的是 http）、DNS 替身。节点可以改成 refuse（端口关闭）、reset（握手后立刻断开）、
  blackhole（连得上但不回话）、egress（连上节点但出不去）。
- 节点是 SOCKS5；mihomo 的 SOCKS5 客户端不看回复码（transport/socks5/socks5.go:269），所以“出不去”在内核看来
  和“连上了、没有数据”一样。真实机场的协议没有试。

文件
- scripts/：实验脚本。e1_structure.py（成员顺序、默认选中、store-selected、隐藏组能不能被选）、
  e1b_allnodes.py（“全部节点”几种正则写法和真值比）、e2_timing.py 与 batch_e2*.sh（切换时间）、
  e3_collateral.py（国外默认 = 停掉的节点时的连带影响；也用来跑 e3c、e3d）、e4_profiles.py（profile 与 core、
  简易版与完整版之间差什么）、e5_startrace.py（启动时的竞态）、summarize.py（整理切换时间）。
- runs/<场景>.out、.stdout：每个实验的输出；runs/summary_all.json：切换时间汇总；runs/<场景>/summary.json、
  report.json：单个场景的结果；正文里引用的几组切换时间另留了 driver.jsonl（每个请求的记录）；
  e3v2、e3c-dnsvia、e5 留了 mihomo.log；e1、e1b、t180-blackhole-seq 留了实际交给内核的 config.yaml。
  其余的大日志和配置没有收进仓库（可以用脚本重跑）。本机目录换成了 <OPT>、<scratch>。
- runs/e3：第一次跑的连带实验，作废——测试用的名字是 .example，被 geosite:private 交给了 system，有几条查询
  发到了沙箱的系统 DNS；重跑（e3v2）时改了名字，system 也换成了本机替身。

重跑（source ~/proxy-vendor/env.sh 以后，在放脚本的目录里）
  python3 -I scripts/e1_structure.py runs/e1 48100
  python3 -I scripts/e1b_allnodes.py runs/e1b 48200
  bash scripts/batch_e2.sh；bash scripts/batch_e2b.sh
  python3 -u -I scripts/e3_collateral.py runs/e3v2 49300
  python3 -I scripts/e4_profiles.py runs/e4
  python3 -u -I scripts/e5_startrace.py runs/e5 49800 4
  （e3c、e3d、单跑的两个切换时间场景要另加 JSON 参数，见对应的 .out 开头。）

关键结果
- e1.out：“日本” = [日本·自动, 日本 01, 🇯🇵 Tokyo 02, 日本-美国 03]，选中“日本·自动”；没有韩国节点时“韩国”只剩
  “韩国·自动”，它是 REJECT（拒绝，不直连）；重启后选择还在；手选的节点从订阅里消失后，组回到第一项。
  加 exclude-filter 会把写明的“日本·自动”也删掉；filter 用反引号拆开会让成员按 filter 的先后重排。
- e1b.out：“全部节点”只用现有正则末尾判断提示行的那一段，649 个样本名里有 15 个提示行漏进来；
  按七条宽筛选取并集，结果和真值完全一致。
- summary_all.json（每个请求结束后隔 2 秒再发下一个；节点在一次检查刚结束时出故障，接近最坏）：
  连接被拒：30 / 180 / 300 秒间隔下 0.7 / 0.3 / 1.7 秒换走，没有请求失败；
  连得上但不回话：40.3 / 191.5 / 312.5 秒，期间失败 6 / 28 / 45 个；
  连上节点但出不去：30.3 / 181.5 / 302.0 秒，失败 15 / 91 / 150 个；
  不回话、每次 4 个并发、max-failed-times 3：30 秒档 10.2 秒、180 秒档 13.3 秒。
  组上的 interval 不起作用、订阅上的才起作用：gi-prov300-group30、gi-prov30-group300。
- e3v2.out：国外默认 = 一个停掉的节点时，没被规则认出的域名 502；不在 geosite:cn、境外 DNS 会答国内地址的网站 502；
  geosite:cn 里的国内网站照常直连；走 OpenAI 组（节点正常）的 TCP 正常、UDP 因为解析不了被丢；手动切成直连、
  域名在境外 DNS 策略里的组 502；问 www.msftconnecttest.com、www.msftncsi.com、captive.apple.com 得到 SERVFAIL。
- e3c-dnsvia.out：境外 DNS 写成 https://1.1.1.1/dns-query#日本·自动 以后，上面 DNS 那几项都恢复；没被认出的境外网站
  仍然失败（连接本身走国外默认）。e3d-dnsfallback.out：用 fallback[国外默认, 各地区·自动] 时，启动后约 10 秒内
  OpenAI 请求被拒，不采用。
- e4.out：两份简易版都过 mihomo -t；简易版和完整版只差 proxy-groups（前提是两版的检查间隔相同）。
- e5.out：方案 ③ 启动 4 次都正常。附带发现（完整版）：启动 4 次里有 2 次，“日本·自动”在前约 10 秒是 REJECT，
  “日本·手动优先”把两个成员都记成不可用，到第 12 秒还是这样（要等下一次检查）；这时它仍然用“日本·手动”。
注意：这几组实验里“国外默认”经过一个叫“全部节点”的中间组；docs/10 采用的写法是把全部节点直接放进“国外默认”
（生成器原型和官方分组核对见 handoff/notes/simple_generator/），DNS 跟着“国外默认”走这一点两种写法相同。

2026-10-21 写好简易版以后（纯手选，docs/10）加的两项：用生成器实际写出的简易版配置，核对“境外 DNS 不跟着国外默认里
手选的节点走”（使用者定的方案 2，“1②”）。实验台和上面相同（scripts/lab.py，本机 SOCKS5 节点、DNS 替身）。
- scripts/e6_simple_dist.py（mihomo v1.19.31）：配置 = dist/mihomo/mihomo-simple-core.yaml，策略组原样不改；订阅换成本机文件、
  DNS 服务器换成本机替身但走的路不变（境外 DNS 仍写成“地址#境外DNS”）。用法：python3 -I scripts/e6_simple_dist.py runs/e6 49900
- scripts/e7_singbox_simple_dist.py（sing-box）：配置 = 生成器带实验台节点生成的 sing-box 简易版（1.14 版；SB_VARIANT=1.12 时用 1.12
  兼容版），入站、规则集、DNS 替身同样只换必须换的。用法：python3 -I scripts/e7_singbox_simple_dist.py "$SINGBOX_BIN" runs/e7-1.14.1 50100；
  SB_VARIANT=1.12 python3 -I scripts/e7_singbox_simple_dist.py "$SINGBOX112_BIN" runs/e7-1.12.0 50200
- 输出：runs/e6.out、runs/e7-1.14.1.out、runs/e7-1.12.0.out（屏幕输出）；runs/e6/、runs/e7-*/ 下是 report.json、实际交给内核的配置
  （e6 的 config.yaml、e7 的 config.json）、每一段的内核日志（e7 另有实验台事件 events.jsonl）。本机目录换成了 <scratch>、<OPT>、<repo>。
关键结果
- e6.out，国外默认 -> 美国 -> 美国 02，美国 02 端口关闭 / 不回话（fd-refuse、fd-blackhole）：没被规则认出的境外网站失败（502，
  连接本身走的就是那个节点）；境外 DNS 会答国内地址的网站直连成功、系统联网检测的几个名字解析正常、手动切成直连的
  Microsoft 组正常、UDP 照常发出——E3（DNS 跟着国外默认）时这几项都失败。境外 DNS 替身收到的查询都经 n1（“境外DNS”当时用的
  日本 01），GEO 数据下载的连接也到了 n1，没有一次经过挂掉的 n5。
- e6.out，“境外DNS”自己用的节点挂了（dns-refuse、dns-blackhole；每 2 秒发一个要靠境外 DNS 判断的连接）：端口关闭时 2.12 秒、
  不回话时 14.19 秒以后恢复（换到香港 01）；恢复以前那几个连接没有失败，而是因为解析不出地址、没能被 GEOIP,CN 认成国内，
  落到最后的国外默认（走了代理）。不是等 1 小时一次的定时检查：连接被拒马上重测，其他失败按 max-failed-times 3 计数
  （adapter/outboundgroup/groupbase.go，见新版 docs/10 第 6.3 节）。
- e6 第一次跑时 dns-* 两段用的是“设备直接问 A 记录”，假地址模式下这种查询直接拿假地址，不经过境外 DNS，测不到东西，
  改成发连接以后重跑（就是现在的 e6.out）。另试过实验台的 egress、fail 两种节点模式：它们只影响新连接，而 mihomo 的 DNS 连接
  是开着的旧连接，所以测不到东西，没有收进来。
- e7-1.14.1.out、e7-1.12.0.out（sing-box）：国外默认 -> 美国 02 端口关闭时，没被规则认出的名字照样经“境外DNS”（n1）解析成功，
  国内地址的交给了“国内直连”（这台机器连不出去 223.5.5.5，连接超时是环境的原因，内核日志里去向是对的）；
  “境外DNS”自己用的节点（日本 01）端口关闭后，60 秒里每 5 秒一次、共 12 次解析全部失败，连接被关掉——sing-box 的自动测速组
  不因为连接失败重测，要等下一次定时检查（简易版 1 小时）；经 clash API 对“境外DNS”测一次速（SFA 上“测速”按钮走的同一组函数）
  以后马上换到香港 01，之后都成功。两个版本结果相同（1.12.0 的手动测速接口回的是空的 {}，但同样换了节点）。

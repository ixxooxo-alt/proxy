#!/bin/bash
# 并行跑 E2 的全部场景（每个场景自己的端口段，全部 127.0.0.1）
cd "$(dirname "$0")/.."
source /root/proxy-vendor/env.sh
run() { # 名字 端口 参数
  timeout 900 python3 -I scripts/e2_timing.py "runs/$1" "$2" "$3" > "runs/$1.stdout" 2>&1 &
}
run t30-blackhole-seq        48400 '{"interval":30,"mode":"blackhole","traffic":"seq","period":2,"select":"auto","t_fail":32,"t_end":110}'
run t30-blackhole-burst      48440 '{"interval":30,"mode":"blackhole","traffic":"burst","period":3,"k":4,"select":"auto","t_fail":32,"t_end":100}'
run t30-blackhole-burst-mft3 48480 '{"interval":30,"mode":"blackhole","traffic":"burst","period":3,"k":4,"select":"auto","mft":3,"t_fail":32,"t_end":100}'
run t30-egress-seq           48520 '{"interval":30,"mode":"egress","traffic":"seq","period":2,"select":"auto","t_fail":32,"t_end":110}'
run t30-refuse-idle          48560 '{"interval":30,"mode":"refuse","traffic":"idle","period":2,"select":"auto","t_fail":32,"idle_before":15,"idle_after":60,"t_end":125}'
run t30-blackhole-idle       48600 '{"interval":30,"mode":"blackhole","traffic":"idle","period":2,"select":"auto","t_fail":32,"idle_before":15,"idle_after":60,"t_end":160}'
run t30-refuse-seq-fixed     48640 '{"interval":30,"mode":"refuse","traffic":"seq","period":2,"select":"fixed","t_fail":32,"t_end":100}'
run gi-prov300-group30       48680 '{"interval":300,"group_interval":30,"mode":"refuse","traffic":"seq","period":2,"select":"auto","t_fail":5000,"t_end":100}'
run gi-prov30-group300       48720 '{"interval":30,"group_interval":300,"mode":"refuse","traffic":"seq","period":2,"select":"auto","t_fail":5000,"t_end":100}'
run t180-refuse-seq          48760 '{"interval":180,"mode":"refuse","traffic":"seq","period":2,"select":"auto","t_fail":182,"t_end":215}'
run t180-blackhole-seq       48800 '{"interval":180,"mode":"blackhole","traffic":"seq","period":2,"select":"auto","t_fail":182,"t_end":400}'
run t180-blackhole-burst     48840 '{"interval":180,"mode":"blackhole","traffic":"burst","period":3,"k":4,"select":"auto","t_fail":182,"t_end":230}'
run t180-egress-seq          48880 '{"interval":180,"mode":"egress","traffic":"seq","period":2,"select":"auto","t_fail":182,"t_end":400}'
run t300-refuse-seq          48920 '{"interval":300,"mode":"refuse","traffic":"seq","period":2,"select":"auto","t_fail":302,"t_end":330}'
run t300-blackhole-seq       48960 '{"interval":300,"mode":"blackhole","traffic":"seq","period":2,"select":"auto","t_fail":302,"t_end":640}'
run t300-egress-seq          49000 '{"interval":300,"mode":"egress","traffic":"seq","period":2,"select":"auto","t_fail":302,"t_end":640}'
wait
echo ALL-DONE

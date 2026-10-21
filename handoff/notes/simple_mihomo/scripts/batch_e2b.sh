#!/bin/bash
cd "$(dirname "$0")/.."
source /root/proxy-vendor/env.sh
run() { timeout 600 python3 -I scripts/e2_timing.py "runs/$1" "$2" "$3" > "runs/$1.stdout" 2>&1 & }
run t30-viahk-refuse           49400 '{"interval":30,"mode":"refuse","traffic":"seq","period":2,"select":"auto","selects":[["国外默认","香港"]],"t_fail":32,"t_end":100}'
run t180-blackhole-burst-mft3  49440 '{"interval":180,"mode":"blackhole","traffic":"burst","period":3,"k":4,"select":"auto","mft":3,"t_fail":182,"t_end":230}'
run t30-blackhole-burst6       49480 '{"interval":30,"mode":"blackhole","traffic":"burst","period":3,"k":6,"select":"auto","t_fail":32,"t_end":70}'
wait
echo ALL-DONE

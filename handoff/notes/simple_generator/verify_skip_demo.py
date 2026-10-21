"""演示：仓库现在的 verify.check_outputs 按完整文件名分派，新文件名的 Loon / QX / Stash 配置会被悄悄跳过。只读仓库。"""
import os, sys
REPO, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, REPO)
sys.dont_write_bytecode = True
from generator import verify
with open(os.path.join(OUT, "loon", "loon-simple.conf"), encoding="utf-8") as f:
    t = f.read()
broken = t.replace("国外默认 = select,日本,", "国外默认 = select,不存在的组,", 1)
assert broken != t
for name in ("loon/loon.conf", "loon/loon-simple.conf"):
    print(name, "→", verify.check_outputs({name: broken}) or "（没有报任何问题）")

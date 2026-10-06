#!/usr/bin/env bash
# 打印“代码状态哈希”：build.py、generator/、source/、tests/、tools/、.gitignore 里全部文件内容的合并哈希。
# 用处：代码定稿（冻结）时记下它；变异检查跑完、打包之前再算一次，两次必须相同——
# 证明日志里的每一项检查都是在同一份代码上跑的。docs/、dist/、README、handoff/ 不算在内。
# r12 定稿时的值：0dc17ff6733642c11c36116b3627ff8c17dfb3171e45b7d8eeab2420dbb05c3f
# 注意：source/local.yaml（个人覆盖，不进仓库）如果存在会被算进去；出公开版本时不应该有这个文件。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
find build.py generator source tests tools .gitignore -type f -not -path '*/__pycache__/*' -not -name '*.pyc' \
  | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -d' ' -f1

#!/bin/sh
# Cloudflare Pages 构建入口。
#
# 背景：Pages 镜像里的 Python 由 asdf 管理，不同时段 `python` / `python3`
# 哪个可用并不稳定（实测出现过只有 `python` 指向 3.13、没有 `python3` 的情况）。
# 这里做一次探测，明确挑出 3.6+ 的解释器再执行，避免镜像差异导致构建失败。
#
# 用法：在 Cloudflare Pages 把 Build command 设为 `sh scripts/cf-build.sh`

set -e

# 用 shell 内建参数展开取脚本所在目录，不依赖外部 dirname（构建镜像里可能缺失）
SELF_DIR=${0%/*}
[ "$SELF_DIR" = "$0" ] && SELF_DIR=.
cd "$SELF_DIR/.." || {
    echo "ERROR: 无法进入仓库根目录（SELF_DIR=$SELF_DIR）" >&2
    exit 1
}
ROOT=$(pwd)
echo "Repo root: $ROOT"

find_py() {
    for candidate in python3 python python3.11 python3.13 python3.12; do
        if command -v "$candidate" >/dev/null 2>&1; then
            # 必须 >= 3.6（build.py 使用 f-string，且绝不能落到 python2）
            if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

PY=$(find_py) || {
    echo "ERROR: 未找到 Python 3.6+ 解释器" >&2
    echo "PATH=$PATH" >&2
    exit 1
}

echo "Using interpreter: $PY ($($PY -V 2>&1))"
exec "$PY" scripts/build.py "$@"

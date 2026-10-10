#!/bin/bash
# Text Reconstructor 开发模式一键启动
# 用法: bash scripts/dev.sh
# 效果: 启动 Python 后端 + 启动 Tauri 开发窗口 (前端热更新)

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

echo "=================================="
echo " Text Reconstructor 开发模式"
echo " 前端修改热更新，无需手动重启"
echo "=================================="

# Kill any previous instances
kill $(pgrep -f "uvicorn text_reconstructor") 2>/dev/null || true
kill $(pgrep -f "vite") 2>/dev/null || true

# Step 1: 启动 Python 后端
echo ""
echo "[1/2] 启动 Python 后端 (port 18231) ..."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate deep_learning_env
uvicorn text_reconstructor.api:app --host 127.0.0.1 --port 18231 --reload &
PYTHON_PID=$!
echo "  Python PID: $PYTHON_PID"

# Wait for Python to start
sleep 2
echo "  Python backend started"

# Step 2: 启动 Tauri 开发窗口
echo ""
echo "[2/2] 启动 Tauri 开发窗口 ..."
cd "$ROOT/app"
npm run tauri dev &
TAURI_PID=$!
echo "  Tauri PID: $TAURI_PID"

echo ""
echo "=================================="
echo " 运行中..."
echo " Python 后端: http://127.0.0.1:18231"
echo " Tauri 窗口: 前端热更新 (改代码即生效)"
echo ""
echo " 停止: 按 Ctrl+C"
echo "=================================="

# Wait for either process to exit
trap "kill $PYTHON_PID $TAURI_PID 2>/dev/null; echo '已停止'" EXIT
wait

#!/bin/bash
# Text Reconstructor 重建脚本 (轻量版)
# 用法: bash scripts/rebuild.sh
# 效果: 编译前端 + 编译 Tauri .app
# 后端通过 conda 自动启动, 不内嵌 PyInstaller (省 ~3GB)

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

echo "=================================="
echo " Text Reconstructor 重建 (轻量版)"
echo "=================================="

# Step 0: 杀掉旧后端进程，确保新代码生效
echo ""
echo "[0/3] 清理旧后端 ..."
if lsof -i :18231 >/dev/null 2>&1; then
    OLD_PID=$(lsof -t -i :18231 2>/dev/null | head -1)
    echo "  杀掉旧后端 PID=$OLD_PID"
    kill $OLD_PID 2>/dev/null || true
    sleep 1
fi
# 杀掉旧 .app 进程
pkill -f "TextReconstructor.app" 2>/dev/null || true
sleep 1

# Step 1: 编译前端
echo ""
echo "[1/3] 编译前端 ..."
cd "$ROOT/app"
npm run build 2>&1 | tail -3

# Step 2: 编译 Tauri .app bundle
echo ""
echo "[2/3] 编译 Tauri .app (约 1-3 分钟) ..."
source "$HOME/.cargo/env"
npm run tauri build 2>&1 | tail -5

# Step 3: codesign + 安装
echo ""
echo "[3/3] 安装到 /Applications/ ..."
rm -rf "/Applications/TextReconstructor.app"
codesign --force --deep --sign - "$ROOT/app/src-tauri/target/release/bundle/macos/TextReconstructor.app" 2>&1 | tail -1
cp -r "$ROOT/app/src-tauri/target/release/bundle/macos/TextReconstructor.app" "/Applications/TextReconstructor.app"

echo ""
echo "=================================="
echo " 完成!"
echo " .app 已安装到 /Applications/TextReconstructor.app"
echo ""
echo " 双击打开即可使用 (后端自动通过 conda 启动)"
echo "=================================="

#!/usr/bin/env bash
# ===========================================================
#  run_tests.sh — 一键运行 server-inspector 完整测试套件
#  用法：bash run_tests.sh
# ===========================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="$SCRIPT_DIR/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "⚠️  未找到 venv/bin/python，请先创建虚拟环境："
    echo "   python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "✅ 使用虚拟环境 Python: $PYTHON"

# 确保 pytest 和 pytest-cov 已安装
"$PYTHON" -m pip install --quiet pytest pytest-cov

# 3. 运行测试（带覆盖率报告）
echo ""
echo "🚀 开始运行测试..."
echo "========================================"

pytest tests/ \
    -v \
    --tb=short \
    --cov=app \
    --cov-report=term-missing \
    --cov-report=html:reports/coverage_html \
    -p no:warnings \
    "$@"

echo ""
echo "========================================"
echo "✅ 测试完成！覆盖率报告已生成至 reports/coverage_html/index.html"

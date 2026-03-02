#!/bin/bash
# =============================================================
# 前端资源本地化下载脚本（适用于内网部署）
# 将 Bootstrap 5、jQuery、Chart.js、Bootstrap Icons 下载到本地
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATIC_DIR="$SCRIPT_DIR/app/static"
CSS_DIR="$STATIC_DIR/css"
JS_DIR="$STATIC_DIR/js"
FONTS_DIR="$STATIC_DIR/fonts"

mkdir -p "$CSS_DIR" "$JS_DIR" "$FONTS_DIR"

echo "========================================"
echo "  医院IT巡检系统 - 前端资源本地化下载"
echo "========================================"
echo ""

# Bootstrap 5.3.3
echo "[1/5] 下载 Bootstrap 5.3.3..."
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" -o "$CSS_DIR/bootstrap.min.css"
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" -o "$JS_DIR/bootstrap.bundle.min.js"
echo "  ✅ Bootstrap 5.3.3 下载完成"

# Bootstrap Icons 1.11.3
echo "[2/5] 下载 Bootstrap Icons 字体..."
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" -o "$CSS_DIR/bootstrap-icons.min.css"
mkdir -p "$FONTS_DIR/bootstrap-icons"
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2" -o "$FONTS_DIR/bootstrap-icons/bootstrap-icons.woff2"
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff" -o "$FONTS_DIR/bootstrap-icons/bootstrap-icons.woff"

# 修改 bootstrap-icons.min.css 的字体路径指向本地
sed -i.bak 's|../fonts/|../fonts/bootstrap-icons/|g' "$CSS_DIR/bootstrap-icons.min.css"
rm -f "$CSS_DIR/bootstrap-icons.min.css.bak"
echo "  ✅ Bootstrap Icons 下载完成"

# jQuery 3.7.1
echo "[3/5] 下载 jQuery 3.7.1..."
curl -fsSL "https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js" -o "$JS_DIR/jquery.min.js"
echo "  ✅ jQuery 下载完成"

# Chart.js 4.4.4
echo "[4/5] 下载 Chart.js 4.4.4..."
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js" -o "$JS_DIR/chart.min.js"
echo "  ✅ Chart.js 下载完成"

# 尝试下载 SimHei 中文字体（用于 PDF 导出）
echo "[5/5] 获取中文字体（SimHei.ttf）..."
FONT_PATH="$FONTS_DIR/SimHei.ttf"
if [ -f "$FONT_PATH" ]; then
    echo "  ✅ SimHei.ttf 已存在，跳过"
elif [ -f "/Windows/Fonts/simhei.ttf" ]; then
    cp "/Windows/Fonts/simhei.ttf" "$FONT_PATH"
    echo "  ✅ 从 Windows 字体目录复制完成"
elif [ -f "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc" ]; then
    cp "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc" "$FONT_PATH"
    echo "  ✅ 从系统 WQY 字体复制完成（兼容模式）"
elif [ -f "/usr/share/fonts/wps-office/SIMHEI.TTF" ]; then
    cp "/usr/share/fonts/wps-office/SIMHEI.TTF" "$FONT_PATH"
    echo "  ✅ 从 WPS Office 字体复制完成"
else
    echo "  ⚠️  未找到 SimHei.ttf，尝试下载文泉驿字体作为备用..."
    curl -fsSL "https://github.com/adobe-fonts/source-han-sans/releases/download/2.004R/SourceHanSansSC-Regular.otf" \
         -o "$FONT_PATH" 2>/dev/null || {
        echo "  ⚠️  字体下载失败，PDF 中文可能显示不正常"
        echo "     请手动将 SimHei.ttf 放到: $FONTS_DIR/"
    }
fi

echo ""
echo "========================================"
echo "  ✅ 所有资源下载完成！"
echo "  资源目录: $STATIC_DIR"
echo "========================================"

#!/bin/bash
# =============================================================
# 医院IT服务器自动巡检系统 — Linux 一键部署脚本
# 支持: CentOS 7/8, RHEL 7/8/9, Ubuntu 18.04/20.04/22.04
# 运行: sudo bash deploy.sh
# =============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="inspector"
APP_PORT=5000
VENV_DIR="$SCRIPT_DIR/venv"
SERVICE_NAME="server-inspector"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "=============================================="
echo "  🏥 医院IT服务器巡检系统 一键部署"
echo "=============================================="
echo ""

# 检查 root 权限
[ "$EUID" -ne 0 ] && error "请使用 sudo 或 root 用户运行此脚本"

# 检测操作系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    error "无法检测操作系统"
fi
info "检测到系统: $OS $VER"

# 安装 Python 3
info "检查 Python 3..."
if ! command -v python3 &>/dev/null; then
    info "安装 Python 3..."
    case $OS in
        centos|rhel|rocky|almalinux)
            yum install -y python3 python3-pip python3-venv 2>/dev/null || \
            yum install -y python39 python39-pip 2>/dev/null || \
            error "无法安装 Python3，请手动安装"
            ;;
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y python3 python3-pip python3-venv
            ;;
        *)
            error "不支持的操作系统: $OS"
            ;;
    esac
fi

PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
info "Python 版本: $PY_VER"

# 安装系统依赖（编译器等）
info "安装系统依赖..."
case $OS in
    centos|rhel|rocky|almalinux)
        yum install -y gcc libffi-devel openssl-devel python3-devel 2>/dev/null || true
        ;;
    ubuntu|debian)
        apt-get install -y gcc libffi-dev libssl-dev python3-dev 2>/dev/null || true
        ;;
esac

# 创建虚拟环境
info "创建 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
success "虚拟环境: $VENV_DIR"

# 安装依赖
info "安装 Python 依赖包（可能需要几分钟）..."
"$VENV_DIR/bin/pip" install --upgrade pip -q

# 先尝试使用 whl 离线包
if [ -d "$SCRIPT_DIR/packages" ]; then
    info "发现离线包目录，使用离线安装..."
    "$VENV_DIR/bin/pip" install --no-index --find-links="$SCRIPT_DIR/packages" -r "$SCRIPT_DIR/requirements.txt" -q
else
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi
success "依赖安装完成"

# 下载前端资源
if [ ! -f "$SCRIPT_DIR/app/static/js/bootstrap.bundle.min.js" ]; then
    info "下载前端静态资源..."
    bash "$SCRIPT_DIR/download_resources.sh" || warn "前端资源下载失败，请检查网络或手动运行 download_resources.sh"
else
    info "前端资源已存在，跳过下载"
fi

# 初始化数据库和目录
info "初始化数据库..."
mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/exports" "$SCRIPT_DIR/uploads"
"$VENV_DIR/bin/python" -c "
from app import create_app
app = create_app()
print('数据库初始化完成')
" 2>/dev/null || warn "数据库初始化有警告，通常可忽略"
success "数据库初始化完成"

# 创建 systemd 服务
info "配置 systemd 服务..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=医院IT服务器自动巡检系统
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SCRIPT_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="FLASK_ENV=production"
ExecStart=${VENV_DIR}/bin/python ${SCRIPT_DIR}/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
success "systemd 服务已设置（开机自启）"

# 配置防火墙
info "配置防火墙..."
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=${APP_PORT}/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    success "firewalld 已放行端口 $APP_PORT"
elif command -v ufw &>/dev/null; then
    ufw allow ${APP_PORT}/tcp 2>/dev/null || true
    success "ufw 已放行端口 $APP_PORT"
else
    warn "未检测到防火墙工具，请手动放行端口 $APP_PORT"
fi

# 等待服务启动
sleep 3

# 检查服务状态
echo ""
if systemctl is-active --quiet ${SERVICE_NAME}; then
    success "服务启动成功！"
else
    warn "服务未能正常启动，查看日志："
    journalctl -u ${SERVICE_NAME} -n 20 --no-pager
fi

# 获取服务器IP
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo -e "  ${GREEN}✅ 部署完成！${NC}"
echo ""
echo "  访问地址: http://${SERVER_IP}:${APP_PORT}"
echo "  默认账号: admin"
echo "  默认密码: admin123"
echo ""
echo "  常用命令："
echo "    查看状态: systemctl status ${SERVICE_NAME}"
echo "    查看日志: journalctl -u ${SERVICE_NAME} -f"
echo "    重启服务: systemctl restart ${SERVICE_NAME}"
echo "    停止服务: systemctl stop ${SERVICE_NAME}"
echo ""
echo -e "  ${YELLOW}⚠️  请登录后立即修改默认密码！${NC}"
echo "=============================================="

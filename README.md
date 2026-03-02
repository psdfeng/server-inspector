# Server Inspector

轻量化服务器巡检平台，支持 Linux / Windows / macOS 服务器的统一巡检、告警、报表导出和运维看板。

## 功能概览

- 服务器管理：单台添加、批量 Excel 导入、分组管理
- 巡检能力：
  - Linux / macOS：SSH 巡检
  - Windows：WinRM 巡检（支持常见 Win10/11/Server 2019 场景）
- 指标采集：CPU、内存、磁盘、监听端口、Top 进程、服务异常
- 告警中心：阈值告警、确认/批量确认、未处理告警追踪
- 巡检记录：列表、详情、删除、服务器历史记录
- 报告导出：HTML / Word / PDF，可指定某次巡检记录导出
- 自动化：支持每日定时自动巡检（可在界面配置时间）
- 健康检查：`/healthz`

## 技术栈

- Python 3.9+
- Flask + SQLAlchemy
- APScheduler
- Paramiko（Linux/macOS SSH）
- pywinrm（Windows WinRM）
- Bootstrap + Chart.js

## 快速启动

1. 安装依赖

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

2. 启动服务（前台长会话）

```bash
PORT=8003 ./venv/bin/python run.py
```

3. 访问系统

- 登录页：`http://127.0.0.1:8003/auth/login`
- 默认管理员：
  - 用户名：`admin`
  - 密码：`admin123`

## Windows 巡检说明

- 巡检协议：WinRM（不是 RDP 3389）
- 常见端口：5985（HTTP）/5986（HTTPS）
- 建议填写管理员账号（如 `Administrator`）与密码
- 系统会自动尝试常见 WinRM 端口与协议组合，适配内网环境

## 目录结构

```text
app/
  models/        # 数据模型
  routes/        # 路由
  services/      # 巡检、调度、导出等核心逻辑
  templates/     # 前端模板
  static/        # 静态资源
tests/           # 测试用例
docs/            # 文档
run.py           # 启动入口
requirements.txt # 依赖
```

## 测试

```bash
./venv/bin/pytest -q
```

## 生产部署建议

请参考部署文档：[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

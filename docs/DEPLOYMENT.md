# 部署说明

## 1. 环境要求

- Linux/macOS
- Python 3.9+
- 可访问目标服务器网络（SSH/WinRM）

## 2. 安装

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

## 3. 启动（前台长会话）

```bash
PORT=5001 ./venv/bin/python run.py
```

## 4. 核心配置

可通过环境变量覆盖：

- `PORT`：服务端口（默认 5001）
- `SECRET_KEY`：Flask 会话密钥
- `ENCRYPT_KEY`：服务器密码加密密钥

示例：

```bash
SECRET_KEY='your-secret' ENCRYPT_KEY='your-enc-key' PORT=5001 ./venv/bin/python run.py
```

## 5. Windows 巡检前置条件

- 目标机启用 WinRM 服务
- 放通 5985/5986（至少一个）
- 使用管理员账号密码
- 注意：RDP 3389 可用不代表 WinRM 可用

## 6. 健康检查

```bash
curl http://127.0.0.1:5001/healthz
```

## 7. 常见问题

### 7.1 报错：`Windows巡检需要安装 pywinrm 依赖`

```bash
./venv/bin/python -m pip install pywinrm==0.4.3
```

### 7.2 巡检显示离线但可以远程桌面连接

- 检查是否启用 WinRM，而不是只开了 RDP
- 检查 5985/5986 端口连通性
- 检查账号密码是否正确


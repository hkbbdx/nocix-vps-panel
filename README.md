# NOCIX VPS 控制面板

用于管理 NOCIX 监控和自动下单任务的 FastAPI + React 控制面板。

主要特性：

- 支持多个 NOCIX 商品监控任务
- 使用 NOCIX 账户中已保存的 PayPal 付款方式
- 支持库存恢复后自动进入下单流程
- 任务密码使用 Fernet 加密保存
- Telegram 配置通过面板加密保存
- Selenium Firefox 仅运行在 Docker 内部网络
- 支持任务状态、订单历史、运行日志和 Telegram 通知
- 前端面板由 FastAPI 直接提供
- 支持 Debian VPS Docker Compose 部署

面板不接收或保存 PayPal 登录凭据，也不包含信用卡输入字段。

## Debian VPS 部署

以下命令假设你使用全新的 Debian VPS，并且已经可以通过 SSH 登录。请先
按照 Docker 官方 Debian 文档安装 Docker Engine 和 Compose 插件，然后确认：

```sh
docker --version
docker compose version
```

将项目上传到 VPS，进入项目目录并创建私有配置文件：

```sh
cp .env.example .env
chmod 600 .env
```

为 `API_KEY` 设置一个强随机值。可以使用下面的命令生成：

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

生成有效的 Fernet 加密密钥：

```sh
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

将生成的两个值填写到 `.env`。请单独备份 Fernet 密钥；如果密钥丢失，已经
加密保存的任务密码将无法恢复。不要把 `.env` 提交到 GitHub。

`HOST` 和 `LOG_LEVEL` 会由 API 启动入口读取。当前生产部署固定使用 `8000`
端口（port 8000），容器内外都监听 `8000`。容器启动时会暂时使用 root 创建并设置数据目录
权限，随后以 UID `10001` 的 `appuser` 用户运行 Uvicorn。首次创建 `./data`
目录时不需要手动修改宿主机权限。

Telegram 凭据不会从 `.env` 读取。请只在通过鉴权的面板（authenticated panel）中配置 Telegram，
这样凭据会在保存到 SQLite 前进行加密。

防火墙只开放 SSH 和面板端口。使用 UFW 时：

```sh
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

启动前先验证 Compose 配置：

```sh
docker compose config
```

构建并启动 API 和内部浏览器服务：

```sh
docker compose up -d --build
curl http://127.0.0.1:8000/api/health
```

健康检查接口应返回：

```json
{"status":"ok"}
```

查看服务日志：

```sh
docker compose logs -f api
docker compose logs -f browser
```

浏览器的 WebDriver 和 VNC 端口不会发布到宿主机。不要将 `4444` 或 `5900`
端口开放或代理到公网。

## 更新和备份

拉取新代码并重新构建镜像，不会修改持久化 SQLite 数据目录：

```sh
git pull
docker compose up -d --build
```

备份 SQLite 数据库前先停止 API，确保备份内容一致：

```sh
mkdir -p backups
docker compose stop api
cp data/nocix.db "backups/nocix-$(date +%Y%m%d-%H%M%S).db"
docker compose start api
```

请使用单独且受限的方式备份 `.env` 和 Fernet 密钥。恢复数据库时必须使用
同一个 `DATA_ENCRYPTION_KEY`。

启动时，`init_db()` 会检查持久化 SQLite 数据库，并通过 `schema_version` 表
执行幂等的增量迁移。已有数据会保留，任务状态、订单价格和错误字段会使用
安全默认值补充。升级前请停止 API 并备份数据库。如果需要回滚，请恢复备份
并使用相匹配的应用版本，同时保留原 Fernet 密钥。

## 安全说明

当前部署通过 HTTP 提供 `8000` 端口。任何能够观察网络连接的人都可能截获
API Key 和面板流量。只应在可信网络中使用，或通过 SSH 隧道访问；如果需要
公网访问，请在 API 前配置正确的 HTTPS 反向代理。API Key 不能替代 TLS。

公开接口只有：

```text
GET /api/health
```

其他 `/api/*` 接口都需要请求头：

```text
X-API-Key: 你的面板密钥
```

React 单页应用由 FastAPI 提供，前端路由会回退到 `index.html`。

## 本地验证

```sh
npm --prefix frontend run build
python -m pytest -q
python -m compileall -q backend
docker compose config
```

测试使用虚拟 worker 和模拟 HTTP transport，不会启动 Selenium、访问 NOCIX、
发送 Telegram 消息或提交真实订单。

普通的下单前失败只会终止当前尝试，用户可以通过明确的 `Start monitor` 操作
重新启动。只要提交动作已经开始，如果任务或订单结果无法可靠持久化，worker
就会保留任务所有权并报告不确定的持久化失败；任务不会被释放成可重试的
`stopped` 或 `failed` 状态，也不会再次提交订单。

## 目录结构

```text
backend/       FastAPI 后端、任务管理、数据库和 worker
frontend/      React/Vite 控制面板
nocix_fucker/  Selenium 浏览器和 NOCIX 下单逻辑
tests/         Python 和前端相关测试
Dockerfile     前端构建与 API 运行镜像
docker-compose.yml
.env.example   配置模板，不包含真实凭据
```

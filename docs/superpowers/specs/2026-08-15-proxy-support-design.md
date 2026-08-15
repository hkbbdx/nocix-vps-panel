# 代理支持设计规格

## 目标

为 NOCIX 面板增加 HTTP 和 SOCKS5 代理支持，采用“全局默认代理 + 任务覆盖”模式，
使每个 Selenium 监控任务可以继承全局代理、自定义代理或强制直连。

## 行为

- 默认不使用代理，保持现有直连行为。
- 全局代理配置位于设置页，默认值供任务继承。
- 每个任务可选择：
  - `继承全局代理`
  - `使用自定义代理`
  - `该任务直连`
- 任务自定义代理优先级最高。
- 代理只作用于该任务的 Selenium 浏览器，不改变面板 API、SQLite 或 Telegram 的网络路径。
- 活动任务不能修改代理配置，必须先停止任务。

## 支持格式

```text
http://host:port
http://username:password@host:port
socks5://host:port
socks5://username:password@host:port
```

拒绝 FTP、SOCKS4、缺少端口、userinfo 不完整、query/fragment、空主机和非法端口。
代理用户名、密码、主机和端口必须通过严格解析，不能把原始 URL 拼接到日志或错误消息中。

## 存储与安全

- 全局代理 URL 使用现有 `DATA_ENCRYPTION_KEY` 通过 Fernet 加密后保存到 `settings` 表。
- 任务自定义代理 URL 使用同一密钥加密保存到 `tasks` 表。
- API 只返回代理类型、模式和 `configured` 状态，不返回 URL、用户名或密码。
- 日志、Telegram 和 API 错误只显示脱敏的 scheme/host/port，永不显示认证信息。
- 代理凭据不进入 `.env`、GitHub、浏览器 URL 或持久化日志。

## Selenium 实现

- 无认证 HTTP/SOCKS5 使用 Firefox Selenium proxy capabilities。
- SOCKS5 用户名密码使用 Firefox 的 `socksUsername` 和 `socksPassword` 能力。
- HTTP 用户名密码通过当前浏览器 session 的临时认证扩展提供，不写入共享目录。
- session 结束后删除临时扩展文件。
- 如果代理初始化失败，任务写入 ERROR 日志并停止；不会创建订单失败记录，因为尚未进入下单流程。

## API

任务创建/更新增加：

```text
proxy_mode: inherit | custom | direct
proxy_url: 仅 custom 模式允许，创建/更新请求使用，响应不返回原文
```

设置页增加全局代理字段。新增：

```text
POST /api/proxy/test
```

代理测试只验证通过代理建立浏览器连接并访问安全检测地址，不启动 NOCIX 下单，不发送 Telegram 消息。

## 数据迁移

SQLite 增量迁移增加：

- `tasks.proxy_mode`
- `tasks.proxy_url_ciphertext`
- `settings.proxy_enabled`
- `settings.proxy_url_ciphertext`

迁移幂等，不删除现有任务、订单、日志或加密密钥。旧任务默认 `proxy_mode=inherit`，
全局代理为空时仍然直连。

## 前端

- 任务表单增加代理模式和自定义代理地址。
- 设置页增加全局代理开关、代理地址和测试按钮。
- 中英文都提供翻译，默认简体中文。
- 已配置代理只显示“已配置/Configured”，不回显敏感字段。
- 表单显示支持格式示例和脱敏验证错误。

## 测试

- HTTP/SOCKS5 无认证和账号密码 URL 解析。
- 非法 scheme、端口、userinfo、query/fragment 拒绝。
- Fernet 加密存储和 API 脱敏响应。
- 全局继承、任务自定义、任务直连优先级。
- worker 将解析后的代理传入 Selenium。
- HTTP 认证扩展生成、清理和敏感信息隔离。
- 代理连接失败记录 ERROR，不创建订单失败。
- 全局和任务配置接口鉴权、迁移和代理测试。
- 中英文前端渲染、表单校验、测试按钮反馈。
- 现有 Python 测试、前端测试和生产构建继续通过。

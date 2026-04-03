# AI Gateway - Go版本

这是一个用Go语言重写的AI Gateway项目，用于管理和代理AI服务（如OpenAI、Gemini）的请求。

## 功能特性

- **网关代理**: 支持Chat Completions、Embeddings、Images、Audio等API
- **多提供商支持**: 支持OpenAI、Gemini等多种AI服务提供商
- **智能路由**: 基于权重的随机路由选择，支持自动禁用失败路由
- **认证授权**: JWT认证、API Key认证、TOTP双因素认证
- **计费系统**: 基于Token的成本计算和余额管理
- **日志记录**: 请求日志和详情记录，支持GZIP压缩存储
- **代理支持**: HTTP/HTTPS代理，支持NO_PROXY和CIDR配置
- **前端界面**: Vue 3 + Element Plus 管理后台，嵌入二进制文件

## 快速开始

### 环境要求

- Go 1.22+
- Node.js 20+ (仅开发/构建前端时需要)
- SQLite 3

### 编译运行

```bash
# 下载依赖
go mod tidy

# 构建前端（首次或前端有更新时）
cd web && npm ci && npm run build && cd ..

# 编译
go build -o ai-gateway ./cmd/server

# 运行
./ai-gateway
```

### Docker部署

```bash
# 构建镜像
docker build -t ai-gateway .

# 运行容器
docker run -d \
  --name ai-gateway \
  -p 3000:3000 \
  -v ai-gateway-data:/app \
  -e JWT_SECRET=your-secret-key \
  ai-gateway

# 或使用 docker-compose
docker-compose up -d
```

### Docker 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET` | JWT签名密钥，**强烈建议设置** | 首次运行自动生成 |
| `HTTP_PROXY` | HTTP代理地址 | 空 |
| `HTTPS_PROXY` | HTTPS代理地址 | 空 |
| `NO_PROXY` | 不使用代理的地址 | 空 |

> **安全提示**: 如果不设置 `JWT_SECRET`，系统会在首次启动时自动生成一个随机密钥并存储在数据库中。但如果数据库丢失，用户将无法登录。建议在生产环境中设置固定的 `JWT_SECRET`。

### 默认管理员账户

首次运行时，系统会自动创建默认管理员账户：

- **用户名**: `root`
- **密码**: `root`

> **重要**: 请在生产环境中立即修改默认密码！

## 项目结构

```
ai-gateway/
├── cmd/server/main.go          # 应用入口
├── embed.go                    # 前端资源嵌入
├── configs/config.yaml         # 配置文件
├── VERSION                     # 版本号
├── internal/
│   ├── config/                 # 配置管理
│   ├── models/                 # 数据模型
│   ├── repository/             # 数据访问层
│   ├── service/                # 业务逻辑层
│   ├── handler/                # HTTP处理器
│   ├── middleware/             # 中间件
│   └── utils/                  # 工具函数
├── web/                        # Vue 前端项目
│   ├── src/                    # 前端源码
│   └── dist/                   # 构建产物
├── go.mod
├── Dockerfile
└── Makefile
```

## API端点

### 认证API
- `POST /api/auth/login` - 用户登录

### 用户管理API (需JWT认证)
- `GET /api/users` - 获取用户列表
- `POST /api/users` - 创建用户
- `GET /api/users/:id` - 获取用户
- `PUT /api/users/:id` - 更新用户
- `DELETE /api/users/:id` - 删除用户
- `PUT /api/users/:id/balance` - 调整余额

### 当前用户API
- `GET /api/users/me` - 获取当前用户信息
- `POST /api/users/me/change-password` - 修改密码
- `POST /api/users/me/totp/setup` - 设置TOTP
- `POST /api/users/me/totp/verify` - 验证TOTP
- `POST /api/users/me/totp/disable` - 禁用TOTP

### 提供商管理API
- `GET /api/providers` - 获取提供商列表
- `POST /api/providers` - 创建提供商
- `GET /api/providers/:id` - 获取提供商
- `PUT /api/providers/:id` - 更新提供商
- `DELETE /api/providers/:id` - 删除提供商
- `GET /api/providers/:id/load-models` - 加载模型列表
- `POST /api/providers/:id/sync-models` - 同步模型

### 渠道管理API
- `GET /api/channels` - 获取渠道列表
- `POST /api/channels` - 创建渠道
- `GET /api/channels/:id` - 获取渠道
- `PUT /api/channels/:id` - 更新渠道
- `DELETE /api/channels/:id` - 删除渠道

### 模型管理API
- `GET /api/models` - 获取模型列表
- `POST /api/models` - 创建模型
- `GET /api/models/:id` - 获取模型
- `PUT /api/models/:id` - 更新模型
- `DELETE /api/models/:id` - 删除模型
- `GET /api/models/:id/routes` - 获取模型路由

### API密钥管理
- `GET /api/keys` - 获取密钥列表
- `POST /api/keys` - 创建密钥
- `PUT /api/keys/:id` - 更新密钥
- `DELETE /api/keys/:id` - 禁用密钥

### 日志与统计
- `GET /api/logs` - 获取日志列表
- `GET /api/logs/:id` - 获取日志详情
- `GET /api/stats` - 获取统计数据
- `DELETE /api/cleanup/log-details` - 清理日志详情

### 网关API (需API Key认证)
- `POST /api/v1/chat/completions` - 聊天补全
- `GET /api/v1/models` - 模型列表
- `POST /api/v1/embeddings` - 文本嵌入
- `POST /api/v1/images/generations` - 图像生成
- `POST /api/v1/audio/transcriptions` - 音频转录
- `GET /api/v1/dashboard/billing/usage` - 使用统计
- `GET /api/v1/dashboard/billing/subscription` - 订阅信息

## 配置

配置文件 `configs/config.yaml`:

```yaml
server:
  port: 3000
  mode: release

database:
  path: ai-gateway.db

auth:
  jwt_secret: ${JWT_SECRET}
  jwt_expiry: 8h

timeout:
  upstream: 240s
  model_load: 30s

proxy:
  http_proxy: ${HTTP_PROXY:}
  https_proxy: ${HTTPS_PROXY:}
  no_proxy: ${NO_PROXY:}
```

## 版本管理

版本号存储在 `VERSION` 文件中。发布流程：

1. 更新 `VERSION` 文件中的版本号
2. 推送到 main 分支
3. GitHub Actions 自动构建并发布 Docker 镜像

## 数据库

项目使用SQLite数据库，表结构与TypeScript版本完全兼容。

### 主要数据表
- `User` - 用户表
- `Provider` - 提供商表
- `Channel` - 渠道表
- `Model` - 模型表
- `ModelRoute` - 模型路由表
- `GatewayApiKey` - API密钥表
- `Log` - 日志表
- `LogDetail` - 日志详情表
- `Settings` - 系统配置表

## 开发

```bash
# 运行开发模式（后端）
go run ./cmd/server

# 运行前端开发服务器
cd web && npm run dev

# 运行测试
go test -v ./...

# 运行前端测试
cd web && npm run test:run
```

## 许可证

MIT License
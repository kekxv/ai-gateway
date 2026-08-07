# Lean AI Gateway

**[English](README.md)** | **[中文](README.zh-CN.md)**

Lean AI Gateway 是一个专注于多 AI 提供商的网关，支持 OpenAI、Claude 和 Gemini 的 HTTP/SSE 协议，以及 OpenAI Realtime 和 Gemini Live 的 WebSocket 协议。它提供模型别名、加权路由、API Key 作用域控制、基于 MySQL 的路由健康检查、精确的 `Decimal` 计费，以及 GZIP 压缩的脱敏审计日志，无需 Redis、Celery 或 Kafka。

服务在 MySQL 之外完全无状态。每个容器运行一个 Uvicorn 进程，通过水平扩展容器来提升容量。

## 功能特性

- 兼容 OpenAI、Claude 和 Gemini 的 HTTP API，并支持 SSE 流式响应。
- 支持 OpenAI Realtime 与 Gemini Live WebSocket 中继。
- 自动转换 OpenAI、Claude、Gemini 三种请求/响应协议；OpenAI Responses 默认原生透传，
  其他按下述端点规则处理。
- 基于权重的随机路由，使用 MySQL 保存健康状态、冷却时间和半开探测，并自动避开故障路由。
- 单个提供商可配置多种协议、可选模型自动发现、HTTP/HTTPS 代理，以及支持主机、端口、
  IPv4/IPv6 和 CIDR 的 `NO_PROXY` 规则。
- 支持规范模型、模型别名、精确的每百万 Token 价格和提供商专用 `upstream_model`。多个启用模型可共享
  同一别名，网关会按已配置权重从其可用路由中随机选择；规范模型名仍保持唯一。模型目录会返回别名，但
  转发到上游前始终会改写为提供商的原始模型名。
- API Key 独立管理，可授权全部资源、指定提供商、指定模型，或同时限定提供商与模型集合。
- 支持公开注册并确保首位用户唯一成为管理员，同时提供 JWT access/refresh 认证、角色权限控制、
  修改密码，以及 TOTP 首次绑定、安全换绑和关闭。
- 普通用户可在控制台浏览已启用模型和别名，并创建、编辑、轮换或删除自己的 API Key；所有者由登录
  身份确定，供应商作用域仍只允许管理员配置。
- 基于 `Decimal` 的精确余额、预留、结算、调账和不可变账本。
- 脱敏请求日志、后端游标分页，以及 GZIP 压缩的请求/响应详情。
- 支持供应商和模型级别的价格倍率配置，灵活调整计费价格。
- 管理员可勾选多个模型，在弹窗中按价格分段对比输入、输出、缓存读取和缓存写入的成本价与用户价范围；
  路由仅用于汇总当前有效供应商的价格范围，不作为对比对象。
- 模型分段计费长度上限支持直接输入 Token，或使用 `K` 单位（`1K = 1000 Token`）；保存到后端时
  统一换算为整数 Token，因此不改变原有的分段边界和计费规则。
- 提供按角色隔离的账单统计，支持日期范围、模型和 API Key 筛选；管理员还可按供应商筛选，并对比
  上游成本、用户收费价格和毛利。
- 提供中文 Vue 3 管理控制台，覆盖日常网关运维。
- 管理员可备份/导入目录，并可从旧版 SQLite 迁移目录。

## 支持的接口

| 接口 | 路径 | 模式 |
| --- | --- | --- |
| OpenAI Chat Completions | `/v1/chat/completions` | HTTP、SSE |
| OpenAI Responses API | `/v1/responses` | HTTP、SSE |
| OpenAI Embeddings | `/v1/embeddings` | HTTP |
| OpenAI Completions (Legacy) | `/v1/completions` | HTTP |
| OpenAI 模型目录 | `/v1/models`、`/v1/models/{model}` | HTTP |
| OpenAI Realtime | `/v1/realtime` | WebSocket |
| Claude Messages | `/anthropic/v1/messages`（推荐）、`/v1/messages`（兼容别名） | HTTP、SSE |
| Claude 模型目录 | `/anthropic/v1/models`、`/anthropic/v1/models/{model}`；旧 `/v1/models` 通过 `anthropic-version` 区分 | HTTP |
| Gemini Generate Content | `/v1beta/models/{model}:generateContent` | HTTP |
| Gemini Stream Generate Content | `/v1beta/models/{model}:streamGenerateContent` | SSE |
| Gemini 模型目录 | `/v1beta/models` | HTTP |
| Gemini Live | `/v1beta/live` | WebSocket |
| 管理控制台 | `/console/` | 浏览器 SPA |
| OpenAPI 文档 | `/docs`、`/redoc`、`/openapi.json` | HTTP |

有关 OpenAI API 端点的详细信息，请参阅 [OpenAI API 参考文档](docs/openai-api-reference.md)。

### OpenAI API 兼容性

网关支持多种 OpenAI API 格式，以兼容各种 CLI 工具和应用程序：

- **Chat Completions API** (`/v1/chat/completions`)：标准的聊天补全端点
- **Responses API** (`/v1/responses`)：OpenAI 后端默认原生透传；Claude、Gemini 或明确不支持 Responses 的 OpenAI 兼容后端使用可移植转换。
- **Embeddings API** (`/v1/embeddings`)：生成文本嵌入，用于 RAG 和向量操作
- **Completions API** (`/v1/completions`)：向后兼容的旧版文本补全端点

Responses API 接受两种格式：
```json
// 简单字符串输入
{"model": "gpt-4", "input": "你好，最近怎么样？"}

// 结构化对话历史
{"model": "gpt-4", "input": [{"role": "user", "content": "你好"}]}
```

OpenAI 提供商协议默认支持原生 Responses。仅当 OpenAI 兼容后端只提供 Chat Completions
而不提供 Responses 时，才设置 `supports_responses=false`，启用 Responses 到 Chat 的可移植
回退。其他情况下，Responses 原生字段会转发到 `/v1/responses`。Embeddings 和 Legacy
Completions 必须选择 OpenAI 路由，并分别转发到 `/v1/embeddings` 和 `/v1/completions`；
不会转换为 Chat、Claude 或 Gemini。可移植字段范围见[协议兼容性](docs/protocol-compatibility.md)。

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2
- MySQL 8.4（提供的 Compose 服务是官方支持的本地开发环境）
- Node.js 22 和 npm（仅用于控制台开发与前端测试）

## 一条命令启动 Docker 示例

如需快速进行一次性本地体验，[`example/`](example/) 目录会构建网关、启动 MySQL、执行数据库迁移、
提供不包含内置账户凭据的管理控制台：

```bash
cd example
docker compose up
```

打开 <http://127.0.0.1:8000/console/register> 注册第一个账户；该账户会成为管理员，之后注册的
账户为普通用户。公开注册默认开启，管理员可在“安全设置 → 公开注册”中关闭或重新开启。关闭后，
注册页会隐藏表单，注册接口也会拒绝创建新账户。初始化和清理方法见[示例说明](example/README.md)。

## 本地启动

创建本地环境文件并替换网关密钥：

```bash
cp .env.example .env
uv run python - <<'PY'
import secrets
from cryptography.fernet import Fernet

print("GATEWAY_JWT_SECRET=" + secrets.token_urlsafe(48))
print("GATEWAY_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
PY
```

将生成的值粘贴到 `.env` 文件中。永远不要提交 `.env`。Compose 从该文件读取 `MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD` 和 `MYSQL_ROOT_PASSWORD`，并使用相同的值构建网关数据库 URL。文件中的默认值仅用于本地开发；在第一次运行 `docker compose up`（会初始化非临时卷）之前，请替换两个 MySQL 密码。MySQL 初始化变量不会更改已有卷中的密码。要轮换现有部署的密码，请使用旧凭据登录，执行 `ALTER USER`，然后更新环境变量并重启网关；详见运维手册。由于 Compose 会将 `MYSQL_PASSWORD` 嵌入 SQLAlchemy URL，请使用 URL 安全的密码字符（`A-Z`、`a-z`、`0-9`、`.`、`_`、`~`、`-`）。对于本地宿主机运行，请保持 `GATEWAY_DATABASE_URL` 与这些值一致，并使用 `127.0.0.1:3306`。

MySQL 仅发布在 `127.0.0.1:3306`；不会暴露到外部主机接口。根目录的 `compose.yaml` 是常规开发和部署使用的规范 Compose 文件；`example/compose.yaml` 则是独立、可随时丢弃的一键演示。

启动 MySQL，安装冻结的依赖集，迁移后再启动应用：

```bash
docker compose up -d mysql
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 <http://127.0.0.1:8000/console/register> 创建第一个管理员。自动化部署仍可选择使用
`scripts/create_admin.py` 进行非交互式初始化。

检查就绪状态：

```bash
curl --fail http://127.0.0.1:8000/health
```

`/health` 仅在 MySQL 可达时返回 `200 {"status":"ok"}`。如果数据库未迁移到 `0010` 版本，启动也会拒绝。

### 管理控制台开发

迁移数据库后，分别在两个终端运行后端和 Vite 开发服务器；若尚无用户，请在
`/console/register` 创建第一个管理员：

```bash
# 终端 1：后端
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2：前端开发服务器
npm ci --prefix frontend
npm --prefix frontend run dev
# 打开 http://127.0.0.1:5173/console/
```

如需在本地模拟生产环境，编译控制台并让 FastAPI 从公共网关进程提供服务：

```bash
npm --prefix frontend run build
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/console/
```

公共模型网关仍在 `8000` 端口；编译后的控制台使用同源，不需要单独的生产 Node 进程。`5173` 端口仅用于 Vite 开发服务器。

所有已登录用户都可浏览启用中的模型和别名、管理自己的 API Key，并访问账户安全设置。普通用户的
Key 可授权全部模型或指定启用模型，不能选择供应商，也不能指定其他所有者。管理员还可使用以下功能：

- 用量、成本、健康状态和资源统计仪表盘；
- 按供应商、模型和 API Key 的账单趋势与明细；管理员可对比上游成本、用户收费价格和毛利；
- 提供商协议、凭据、模型同步、模型、别名和加权路由管理；支持勾选不同模型，按分段对比成本价与
  用户价范围，并使用 Token 或 `K` 配置分段长度上限；
- 用户、余额、不可变账本，以及全局和供应商作用域的 API Key 管理；
- 一次性 API Key 展示，以及明确的复制/下载确认流程；
- 请求日志筛选、后端游标翻页和脱敏 JSON 详情查看；
- 修改密码，以及 TOTP 首次绑定、经过校验的安全换绑和关闭。

TOTP 默认由服务端生成随机密钥。“安全设置”页面也为迁移和托管身份验证器提供高级的自定义密钥
选项。自定义值必须符合 RFC 4648 Base32，解码后至少为 160 bit；系统会移除空格和连字符并转换为
大写。只能使用安全工具随机生成、已安全备份且未在其他账户复用的密钥：弱密钥或复用密钥可能导致
账户被接管，丢失密钥则可能导致无法登录。页面会明确显示上述警告，并要求勾选风险确认后才能提交。
新密钥会以加密的待确认状态保存，只有使用它生成的验证码确认成功后才会启用；换绑期间原密钥仍然
有效。

JWT access 和 refresh token 仅保存在 `sessionStorage`，不会写入 `localStorage`。提供商凭据、
TOTP 验证码、密码和完整 API Key 不会持久化，也不会在一次性流程结束后再次显示。

### 目录备份与旧版迁移

管理员可在“供应商”页面导出或合并提供商/模型目录。默认导出会脱敏；控制台在下载包含上游凭据的
备份前会明确警告并要求确认。要从旧 Go 项目
[`kekxv/ai-gateway`](https://github.com/kekxv/ai-gateway) 的 SQLite 数据库迁移某个用户关联的
渠道、供应商、模型、别名、路由、价格和倍率，可先生成标准目录包，再从“供应商”页面导入：

```bash
uv run python scripts/export_legacy_sqlite_catalog.py /path/to/ai-gateway.db \
  --user admin@example.com \
  --include-unowned \
  --include-secrets \
  --output legacy-user-catalog.json
```

完整步骤见[目录备份与旧版 SQLite 迁移说明](docs/catalog-import-export.md)，其中包含旧用户查询、
参数解释、管理 API 导入示例、迁移后校验、密钥处理和回滚限制。`--include-unowned` 通常必需，
因为旧版本没有始终填写管理员创建记录的 `userId`；使用 `--include-secrets` 生成的文件包含上游
密钥，必须受保护，并在导入成功后删除或转存到受控的加密备份位置。

## Docker 部署

对于容器部署，在 `.env` 中设置 `GATEWAY_ENVIRONMENT=production`，使用非示例的 JWT、Fernet
和 MySQL 密钥，数据库主机名保持 `compose.yaml` 的覆盖值（`mysql`）。三个管理员引导变量均可
不设置：服务启动后在 `/console/register` 注册第一个账户即可。首个成功提交的注册用户成为管理员，
之后注册的用户为普通用户。

自动化部署也可在首次启动前设置以下变量，以非交互方式创建管理员；TOTP 密钥可选，但必须为
Base32 且解码后至少 160 bit：

```bash
uv run python -c 'import pyotp; print(pyotp.random_base32())'

# 将生成值及其他引导变量写入 .env 或由密钥管理系统提供的环境文件：
# GATEWAY_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
# GATEWAY_BOOTSTRAP_ADMIN_PASSWORD=<高强度初始密码>
# GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET=<生成的-base32-密钥>

docker compose up -d --build
docker compose ps
```

一次性的 `setup` 服务会等待 MySQL、执行全部迁移，并可选择创建管理员。三个引导变量全部为空时，
它会跳过管理员创建，改由注册页完成初始化；只要配置了任意一项，就必须同时提供邮箱和密码，TOTP 仍为可选。引导值仅在
该邮箱首次创建时生效：后续部署或并发初始化都不会覆盖已有管理员的密码或 TOTP 配置。首次启动成功后，
请从部署环境删除全部三个引导变量（尤其是密码和 TOTP 密钥）；后续 Compose 重启仍会正常执行迁移并
启动网关。具体应先从 `.env` 或密钥来源删除三个值，再执行 `docker compose rm -f setup` 删除仍携带
初始化秘密的已退出 setup 容器。长期运行的 `gateway` 服务会显式将三个变量覆盖为空，因此其容器环境
不会保留这些值；后续启动会用空值重新创建 setup。

运行时容器和 setup 容器都以非 root 用户 `gateway` 身份运行。Compose 使其根文件系统只读，
将 `/tmp` 挂载为 tmpfs，删除所有 Linux 能力，并启用 `no-new-privileges`。在 Kubernetes 或其他
编排器中，应在启动对应版本网关镜像之前，通过单独、串行的 release job 执行
`alembic upgrade head` 和可选的 `scripts/create_admin.py`。

### 已发布镜像

完整 CI 质量任务通过后，默认分支和版本标签会将多阶段生产镜像发布到 GitHub Container Registry：

```bash
docker pull ghcr.io/<owner>/<repository>:latest
docker pull ghcr.io/<owner>/<repository>:<commit-sha>
docker pull ghcr.io/<owner>/<repository>:1.2.3
```

默认分支构建会发布 `latest`、分支名和短提交 SHA。`v1.2.3` 这样的标签会发布 `1.2.3`、
`1.2`、`1` 和提交 SHA。请将占位符替换为该仓库的小写 GitHub 所有者与仓库名。

最终镜像包含 Python 运行时和已编译的 Vue 控制台，以非 root 用户 `gateway` 运行，且不包含
Node.js 或 npm。镜像默认使用生产模式，因此启动时必须提供有效的 JWT、Fernet 和数据库密钥。

## 重要配置

常用配置示例和运维说明见 [`.env.example`](.env.example) 与[运维手册](docs/operations.md)。
最重要的配置项如下：

| 配置项 | 用途 |
| --- | --- |
| `GATEWAY_DATABASE_URL` | MySQL 应用数据库的异步 SQLAlchemy URL |
| `GATEWAY_DATABASE_POOL_SIZE` | 每个网关进程保留的常驻连接数；默认 `20` |
| `GATEWAY_DATABASE_MAX_OVERFLOW` | 超出常驻连接池后允许临时创建的连接数；默认 `20` |
| `GATEWAY_DATABASE_POOL_TIMEOUT_SECONDS` | 等待池中连接的最长秒数，超时后返回数据库错误；默认 `30` |
| `GATEWAY_DATABASE_POOL_RECYCLE_SECONDS` | 连接在下一次签出时被替换前的最长存活秒数；默认 `1800` |
| `GATEWAY_JWT_SECRET` | 签发 access/refresh token；应使用唯一的高熵值 |
| `GATEWAY_ENCRYPTION_KEY` | 加密提供商凭据、请求头和 TOTP 密钥的 Fernet key |
| `GATEWAY_BOOTSTRAP_ADMIN_EMAIL` | 可选的首次初始化管理员邮箱；配置时必须同时提供密码 |
| `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD` | 首次初始化管理员密码；成功后应删除 |
| `GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET` | 可选、至少 160 bit 的首次初始化 Base32 TOTP 密钥；成功后应删除 |
| `GATEWAY_HTTP_PROXY`、`GATEWAY_HTTPS_PROXY` | 可选的提供商出站代理 |
| `GATEWAY_NO_PROXY` | 逗号分隔的主机、后缀、端口、IP、CIDR 或 `*` 绕过规则 |
| `GATEWAY_AUDIT_BODY_LIMIT_BYTES` | 审计详情保留的请求/响应正文大小上限 |
| `GATEWAY_BILLING_DEFAULT_MAX_OUTPUT_TOKENS` | 请求未指定输出上限时的预留回退值 |

每个网关进程最多打开 `GATEWAY_DATABASE_POOL_SIZE + GATEWAY_DATABASE_MAX_OVERFLOW` 条应用连接。
MySQL `max_connections` 应高于该数值乘以网关进程数后的结果，并为迁移、运维和其他客户端预留余量。
连接池签出超时表示本进程连接需求过高或存在长事务，与无法连接 MySQL 是两类不同故障。

生产启动会拒绝示例 JWT 与加密密钥。所有凭据都应保存在密钥管理系统中。提供的 Compose `setup`
服务就是串行 release step；其他编排器应在启动新版本应用前，通过单独 release job 执行相同的
迁移和可选管理员初始化。

## 获取网关 API Key

普通用户登录控制台后，可在“接口密钥”页面创建和管理自己的 Key，并在“可用模型”页面查看可授权的
模型。管理员还可使用管理 API 创建用户、提供商、模型、别名、路由、任意用户的 API Key 和余额调整。
`/docs` 的交互式 API 文档列出了所有字段。只有 API Key 创建或轮换响应会包含原始密钥；请立即保存。

```bash
export GATEWAY_URL=http://127.0.0.1:8000
export ADMIN_TOKEN="$({
  curl --silent --fail "$GATEWAY_URL/auth/login" \
    -H 'content-type: application/json' \
    -d '{"email":"admin@example.com","password":"replace-me"}'
} | uv run python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
```

以下示例假设配置已完成：

```bash
export GATEWAY_API_KEY='sk-gw-replace-me'
export MODEL_ALIAS='friendly-chat'
```

别名在入站时被接受，并在向提供商发起请求或 WebSocket 握手之前被重写为所选的 `ModelRoute.upstream_model`。

## OpenAI 兼容的 HTTP 和 SSE

非流式：

```bash
curl --fail "$GATEWAY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":128}"
```

流式：

```bash
curl --no-buffer --fail "$GATEWAY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":128,\"stream\":true}"
```

## Claude 兼容的 HTTP 和 SSE

Anthropic SDK 建议使用独立的 Base URL。SDK 会继续追加 `/v1/messages` 等原生资源路径：

```bash
export ANTHROPIC_BASE_URL="$GATEWAY_URL/anthropic"
```

原有 `/v1/messages` 继续作为向后兼容别名。每个提供商协议仍使用自己的上游
`base_url`，新增的公共路径前缀不会改变上游配置。

非流式：

```bash
curl --fail "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "x-api-key: $GATEWAY_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"max_tokens\":128,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

流式：

```bash
curl --no-buffer --fail "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "x-api-key: $GATEWAY_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"max_tokens\":128,\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

## Gemini 兼容的 HTTP 和 SSE

非流式：

```bash
curl --fail "$GATEWAY_URL/v1beta/models/$MODEL_ALIAS:generateContent" \
  -H "x-goog-api-key: $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}],"generationConfig":{"maxOutputTokens":128}}'
```

流式：

```bash
curl --no-buffer --fail \
  "$GATEWAY_URL/v1beta/models/$MODEL_ALIAS:streamGenerateContent?alt=sse" \
  -H "x-goog-api-key: $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}],"generationConfig":{"maxOutputTokens":128}}'
```

## OpenAI Realtime WebSocket

使用 `websocat`：

```bash
websocat \
  -H="Authorization: Bearer $GATEWAY_API_KEY" \
  -H='Sec-WebSocket-Protocol: realtime' \
  "ws://127.0.0.1:8000/v1/realtime?model=$MODEL_ALIAS"
```

然后发送如下帧：

```json
{"type":"session.update","session":{"model":"friendly-chat","modalities":["text"]}}
```

## Gemini Live WebSocket

```bash
websocat \
  -H="x-goog-api-key: $GATEWAY_API_KEY" \
  -H='Sec-WebSocket-Protocol: gemini-live' \
  ws://127.0.0.1:8000/v1beta/live
```

当模型未在查询字符串中指定时，第一帧必须标识模型：

```json
{"setup":{"model":"models/friendly-chat","generationConfig":{"responseModalities":["TEXT"]}}}
```

WebSocket 是透明的同协议中继：文本/二进制帧、ping/pong 和 close 细节都会被传播；客户端凭据会被移除，提供商凭据会被注入到上游。

## 质量门禁

测试需要专用的 `gateway_test` schema。`docker compose up -d mysql mysql-test-setup` 会创建/授权该 schema，即使在升级现有的持久化 MySQL 卷时也是如此。fixture 会拒绝数据库名中不包含 `test` 的 URL，拒绝应用 schema，并且只从该隔离 schema 中删除网关表和 `alembic_version`。

```bash
docker compose up -d mysql mysql-test-setup
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src scripts
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm exec --prefix frontend -- playwright install --with-deps chromium
E2E_ADMIN_EMAIL='admin@example.com' E2E_ADMIN_PASSWORD='short-lived-password' \
  npm --prefix frontend run e2e
docker build -t lean-ai-gateway:test .
docker compose config --quiet
```

浏览器 E2E 必须使用已迁移且没有用户的全新应用数据库。首个用例会用 `E2E_ADMIN_EMAIL` 和
`E2E_ADMIN_PASSWORD` 注册，并验证该账户能进入管理员页面。E2E 测试套件仅使用 MySQL 和本地回环
假提供商；它不需要真实的提供商凭据或公共网络访问。测试会创建带唯一名称的资源，按依赖关系逆序删除
可安全删除的资源，并停用因不可变账本历史而不能删除的用户。

## 更多文档

- [架构](docs/architecture.md)
- [协议兼容性](docs/protocol-compatibility.md)
- [运维手册](docs/operations.md)
- 运行时 API 参考：`/docs` 或 `/redoc`

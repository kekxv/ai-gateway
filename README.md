# AI Gateway

AI Gateway 是一个全栈 AI 服务网关，提供统一的 API 接口和网页管理界面，用于管理 AI 渠道、模型、密钥和用量统计。

## 功能特性

### 后端 API
- `/api/v1/chat/completions`: 核心 AI 网关代理端点
- `/api/v1/models`: 模型列表 API
- `/api/v1/embeddings`: 嵌入向量 API
- `/api/v1/images/generations`: 图像生成 API
- `/api/v1/images/edits`: 图像编辑 API
- `/api/v1/images/variations`: 图像变体 API
- `/api/v1/audio/transcriptions`: 音频转录 API
- `/api/v1/audio/translations`: 音频翻译 API
- `/api/channels`: 渠道管理 API
- `/api/models`: 模型管理 API
- `/api/keys`: 密钥管理 API
- `/api/users`: 用户管理 API
- `/api/logs`: 日志查询 API
- `/api/providers`: AI 服务提供商管理 API

### 前端管理界面
- `/dashboard`: 仪表盘，显示统计信息
- `/channels`: 渠道管理页面
- `/models`: 模型管理页面
- `/keys`: 密钥管理页面
- `/users`: 用户管理页面
- `/logs`: 日志查询页面
- `/providers`: AI 服务提供商管理页面
- `/profile`: 用户个人资料和账单信息

## 技术栈

- **核心框架**: Next.js 15 (App Router)
- **数据库**: SQLite with [sqlite](https://www.npmjs.com/package/sqlite) and [sqlite3](https://www.npmjs.com/package/sqlite3)
- **语言**: TypeScript
- **UI**: Tailwind CSS 和 React 组件
- **认证**: JWT 令牌和 API 密钥
- **国际化**: i18next 和 next-i18next

## 快速开始

### 开发环境

1. **克隆仓库**:
   ```bash
   git clone <repository-url>
   cd ai-gateway
   ```

2. **安装依赖**:
   ```bash
   npm install
   ```

3. **启动开发服务器**:
   ```bash
   npm run dev
   ```
   应用程序将在 `http://localhost:3000` 启动。

### 生产环境部署

## 一键部署 (Vercel)

点击下方按钮，一键将此项目部署到 Vercel:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fkekxv%2Fai-gateway)

**注意**: 请将上面的链接替换为您自己的 GitHub 仓库地址。

部署时，Vercel 会引导您完成以下操作：
1.  创建 Git 仓库的副本。
2.  自动识别 Next.js 项目并配置构建设置。
3.  您需要**手动配置环境变量**，特别是 `DATABASE_URL`。对于 SQLite，您可以保留默认值 `file:./dev.db`。


#### 使用 Docker 部署

##### 使用在线镜像

1. **获取 Docker 镜像**:
  ```shell
  docker pull ghcr.io/kekxv/ai-gateway:latest
  ```

2. **运行 Docker 容器**:
   ```bash
   docker run -d -p 3000:3000 --name ai-gateway ghcr.io/kekxv/ai-gateway:latest
   ```

3. **持久化数据库** (可选):
   ```bash
   docker run -d -p 3000:3000 -e DATABASE_URL="/db/ai-gateway.db" -v $(pwd)/data:/db --name ai-gateway ghcr.io/kekxv/ai-gateway:latest
   ```


##### 本地构建

1. **构建 Docker 镜像**:
   ```bash
   docker build -t ai-gateway .
   ```

2. **运行 Docker 容器**:
   ```bash
   docker run -d -p 3000:3000 --name ai-gateway ai-gateway
   ```

3. **持久化数据库** (可选):
   ```bash
   docker run -d -p 3000:3000 -e DATABASE_URL="/db/ai-gateway.db" -v $(pwd)/data:/db --name ai-gateway ai-gateway
   ```

#### 手动部署

1. **安装依赖**:
   ```bash
   npm install
   ```

2. **构建项目**:
   ```bash
   npm run build
   ```

3. **启动生产服务器**:
   ```bash
   npm start
   ```

## 环境变量

项目使用以下环境变量：

- `DATABASE_URL`: 数据库文件路径 (默认: `file:./ai-gateway.db`)
- `JWT_SECRET`: JWT 签名密钥 (首次启动时自动生成)
- `NEXT_PUBLIC_SITE_NAME`: 站点名称 (默认: "AI Gateway")

## 数据库结构

项目使用 SQLite 数据库，包含以下主要表：

- `User`: 用户表
- `Provider`: AI 服务提供商表
- `Channel`: 渠道表
- `Model`: 模型表
- `GatewayApiKey`: 网关 API 密钥表
- `Log`: 请求日志表
- `LogDetail`: 请求详细信息表

数据库会自动初始化和迁移。

## 认证方式

### 管理界面认证
- 使用 JWT 令牌进行用户认证
- 通过 `/api/auth/login` 端点获取令牌

### API 访问认证
- 使用 API 密钥进行认证
- 在请求头中添加: `Authorization: Bearer <api_key>`

## 国际化

项目支持中英文两种语言，通过 `next-i18next` 实现。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进项目。

## 许可证

[MIT License](LICENSE)

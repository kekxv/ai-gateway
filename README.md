# AI Gateway (类 one-api) 设计方案

## 1. 项目目标

本项目旨在创建一个全栈 AI 服务网关，提供一个统一的 API 接口，并配备一个网页管理界面，用以可视化地管理渠道、模型、密钥和用量，核心体验对标 `one-api`。

## 2. 核心功能

### 后端 API

- `/api/v1/chat/completions`: 核心的 AI 网关代理端点。
- `/api/channels`: 用于管理渠道 (上游 AI 提供商) 的 CRUD API。
- `/api/models`: 用于管理模型的 CRUD API。
- `/api/keys`: 用于管理此网关自身的访问令牌的 CRUD API。
- `/api/users`: 用户管理 API。
- `/api/logs`: 日志查询 API。
- `/api/providers`: AI 服务提供商管理 API。

### 前端管理界面 (App Router)

- `/dashboard`: 仪表盘，显示基本统计信息。
- `/channels`: 渠道管理页面，增删改查渠道配置。
- `/models`: 模型管理页面，管理模型的启用状态和路由规则。
- `/keys`: 令牌管理页面，生成和管理访问令牌。
- `/users`: 用户管理页面。
- `/logs`: 日志查询页面。
- `/providers`: AI 服务提供商管理页面。

## 3. 技术选型

- **核心框架**: Next.js (React + Node.js)
- **数据库**: SQLite (通过 Prisma ORM)
- **语言**: TypeScript
- **UI**: Tailwind CSS
- **包管理器**: npx pnpm

## 4. 快速开始 (开发环境)

1.  **克隆仓库**:
    ```bash
    git clone <your-repository-url>
    cd ai-gateway
    ```

2.  **安装依赖**:
    ```bash
    npx pnpm install
    ```

3.  **配置数据库**:
    运行 Prisma 迁移以创建数据库和表结构。
    ```bash
    npx pnpm prisma migrate dev --name init
    ```
    如果需要填充初始数据，可以运行 seed 命令：
    ```bash
    npx pnpm prisma db seed
    ```

4.  **启动开发服务器**:
    ```bash
    npx pnpm dev
    ```
    应用程序将在 `http://localhost:3000` 启动。

## 5. 部署

### 使用 Docker 快速部署

为了方便部署，我们提供了 Docker 支持。请确保您的系统已安装 Docker。

1.  **构建 Docker 镜像**:
    在项目根目录下运行以下命令：
    ```bash
    docker build -t ai-gateway .
    ```

2.  **运行 Docker 容器**:
    ```bash
    docker run -d -p 3000:3000 --name ai-gateway-app ai-gateway
    ```
    这将在后台运行容器，并将容器的 3000 端口映射到主机的 3000 端口。您可以通过 `http://localhost:3000` 访问应用程序。

3.  **管理数据库 (Docker)**:
    对于 Docker 部署，数据库文件 `dev.db` 将位于容器内部。如果您需要持久化数据库或使用外部数据库，请考虑以下选项：
    -   **挂载卷**: 在 `docker run` 命令中使用 `-v` 参数将主机目录挂载到容器内部的数据库路径，例如：
        ```bash
        docker run -d -p 3000:3000 -v $(pwd)/data:/app/prisma --name ai-gateway-app ai-gateway
        ```
        这将把主机当前目录下的 `data` 文件夹挂载到容器的 `/app/prisma` 路径，使 `dev.db` 文件持久化在主机上。
    -   **使用外部数据库**: 修改 `prisma/schema.prisma` 配置，并设置相应的环境变量来连接外部数据库（如 PostgreSQL, MySQL 等）。

## 6. 一键部署 (Vercel)

点击下方按钮，一键将此项目部署到 Vercel:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2F<YOUR_GITHUB_USERNAME>%2F<YOUR_REPO_NAME>)

**注意**: 请将上面的链接替换为您自己的 GitHub 仓库地址。

部署时，Vercel 会引导您完成以下操作：
1.  创建 Git 仓库的副本。
2.  自动识别 Next.js 项目并配置构建设置。
3.  您需要**手动配置环境变量**，特别是 `DATABASE_URL`。对于 SQLite，您可以保留默认值 `file:./dev.db`。

## 7. CI/CD (GitHub Actions)

本项目包含一个 GitHub Actions 工作流程 (`.github/workflows/docker-image.yml`)，它会在您每次推送到 `main` 分支时自动执行以下操作：

1.  **构建 Docker 镜像**: 基于项目根目录下的 `Dockerfile`。
2.  **推送到 GitHub Container Registry (GHCR)**: 将构建的镜像推送到与您的仓库关联的包注册表中。

镜像将被标记为 `latest` 和当前的 Git SHA，例如 `ghcr.io/your-username/ai-gateway:latest`。

这为您的项目提供了持续集成和部署的基础。

## 8. 贡献

欢迎贡献！请参阅 `CONTRIBUTING.md` (如果存在) 以获取更多信息。

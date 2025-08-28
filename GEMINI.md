# AI Gateway (类 one-api) 设计方案 (Full-Stack Edition)

## 1. 项目目标

创建一个全栈 AI 服务网关，提供一个统一的 API 接口，并配备一个网页管理界面，用以可视化地管理渠道、模型、密钥和用量，核心体验对标 `one-api`。

## 2. 技术选型

- **核心框架**: **Next.js (React + Node.js)**
  - **原因**: 一个强大的全栈框架，能在一个项目中同时处理前端页面渲染和后端 API 路由，完美符合我们的需求。
- **数据库**: **SQLite** (通过 **Prisma** ORM)
  - **原因**: SQLite 是一个轻量级的、基于文件的数据库，适合快速启动。Prisma 是一个现代化的 ORM，可以让我们用 TypeScript 来安全、方便地操作数据库。
- **语言**: **TypeScript**
- **UI**: **Tailwind CSS** (由 `create-next-app` 默认集成)
- **包管理器**: **npm** (由 `create-next-app` 默认设置)

## 3. 核心功能

### 后端 API

- `/api/v1/chat/completions`: 核心的 AI 网关代理端点。
- `/api/channels`: 用于管理渠道 (上游 AI 提供商) 的 CRUD API。
- `/api/models`: 用于管理模型的 CRUD API。
- `/api/keys`: 用于管理此网关自身的访问令牌的 CRUD API。

### 前端管理界面 (App Router)

- `/dashboard`: 仪表盘，显示基本统计信息。
- `/channels`: 渠道管理页面，增删改查渠道配置。
- `/models`: 模型管理页面，管理模型的启用状态和路由规则。
- `/keys`: 令牌管理页面，生成和管理访问令牌。

## 4. 项目里程碑

1.  **项目初始化**: 使用 `create-next-app` 搭建项目骨架。(已完成)
2.  **数据库集成**: 安装并配置 Prisma 和 SQLite。
3.  **数据库建模**: 在 `schema.prisma` 中定义 `Channel`, `Model`, `ApiKey` 等数据模型。
4.  **后端 API 开发**: 实现管理渠道、模型等功能的 API 路由。
5.  **前端页面开发**: 使用 React 和 Tailwind CSS 构建管理界面。
6.  **网关核心逻辑**: 实现 `/api/v1/chat/completions` 的请求转发和认证逻辑。


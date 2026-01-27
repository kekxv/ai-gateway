# 错误日志记录指南

本文档说明了在 `gateway-helpers.ts` 中添加的详细错误日志输出位置。

## 日志输出分类

所有日志都使用 `console.log()` 或 `console.error()` 输出，便于在服务器日志中查看。日志使用标签前缀来分类：

### 1. 认证日志 `[AUTH]`
**位置**: `authenticateRequest()` 函数
- `[AUTH] Missing or invalid Authorization header` - 缺少或格式错误的授权头
- `[AUTH] Invalid or disabled API Key` - API密钥无效或被禁用
- `[AUTH] Failed to update lastUsed` - 更新最后使用时间失败
- `[AUTH] Database error during authentication` - 认证时的数据库错误

### 2. 模型查找日志 `[MODEL]`
**位置**: `findModel()` 函数
- `[MODEL] Error finding model` - 查找模型时的数据库错误

### 3. 路由选择日志 `[ROUTE]`
**位置**: `selectUpstreamRoute()` 函数
- `[ROUTE] No eligible routes found for model` - 模型没有可用的上游路由
- `[ROUTE] Selected route` - 成功选择了上游路由
- `[ROUTE] Error selecting upstream route` - 选择路由时的数据库错误

### 4. 权限检查日志 `[PERMISSION]`
**位置**: `checkApiKeyPermission()` 函数
- `[PERMISSION] API Key not bound to any channels` - API密钥未绑定任何频道
- `[PERMISSION] API Key lacks model access` - API密钥缺少对模型的访问权限
- `[PERMISSION] Error checking API key permission` - 权限检查时的数据库错误

### 5. 余额检查日志 `[BALANCE]`
**位置**: `checkInitialBalance()` 函数
- `[BALANCE] User not found for API Key` - API密钥对应的用户未找到
- `[BALANCE] Insufficient balance for user` - 用户余额不足
- `[BALANCE] Error checking balance` - 余额检查时的数据库错误

### 6. 上游请求日志 `[UPSTREAM]`
**位置**: `handleUpstreamRequest()` 函数
- `[UPSTREAM] Sending request to` - 发送请求到上游服务
- `[UPSTREAM] Response received - Status` - 收到上游响应及HTTP状态
- `[UPSTREAM] Error response from upstream` - 上游返回错误响应（含详细信息）
- `[UPSTREAM] Failed to disable route` - 禁用路由失败
- `[UPSTREAM] Stream response has no body` - 流响应无body
- `[RESPONSE] Success from upstream` - 成功接收上游响应
- `[UPSTREAM] Fatal error in handleUpstreamRequest` - 请求处理中的严重错误

### 7. 流式请求日志 `[STREAMING]`
**位置**: `handleUpstreamRequest()` 函数
- `[STREAMING] Logging stream request for model` - 正在记录流式请求

### 8. 表单请求日志 `[FORM_REQUEST]`
**位置**: `handleUpstreamFormRequest()` 函数
- `[FORM_REQUEST] Sending form request to` - 发送表单请求
- `[FORM_REQUEST] Response received - Status` - 收到表单响应
- `[FORM_REQUEST] Error response from upstream` - 表单请求返回错误
- `[FORM_REQUEST] Failed to disable route` - 禁用路由失败
- `[FORM_REQUEST] Success` - 表单请求成功
- `[FORM_REQUEST] Fatal error` - 表单请求处理错误

### 9. 日志记录日志 `[LOG]`
**位置**: `logRequestAndCalculateCost()` 函数
- `[LOG] Starting to log request` - 开始记录请求
- `[LOG] Cost calculation` - 成本计算详情
- `[LOG] User has insufficient balance` - 用户余额不足详情
- `[LOG] Deducted from user` - 从用户账户扣费
- `[LOG] Added to channel owner` - 添加到频道所有者账户
- `[LOG] Successfully inserted log entry` - 成功插入日志条目
- `[LOG] Stored detailed log for entry` - 存储详细日志
- `[LOG] Failed to store log details` - 存储详细日志失败
- `[LOG] Failed to log request` - 日志记录失败
- `[LOG] Failed to log error request` - 错误请求记录失败
- `[LOG] Failed to log streaming request` - 流请求记录失败
- `[LOG] Failed to log form request error` - 表单错误请求记录失败

## 日志信息示例

### 成功的请求流程

```
[ROUTE] Selected route: {provider: 'OpenAI', modelId: 1, baseURL: 'https://api.openai.com/v1'}
[UPSTREAM] Sending request to: https://api.openai.com/v1/chat/completions | Stream: false
[UPSTREAM] Response received - Status: 200 | Latency: 1234ms
[RESPONSE] Success from upstream: {model: 'gpt-4', provider: 'OpenAI', latency: 1234}
[LOG] Starting to log request: {model: 'gpt-4', apiKeyId: 42, latency: 1234}
[LOG] Cost calculation: {tokens: 150, cost: 3}
[LOG] Deducted from user: {userId: 10, amount: 3}
[LOG] Successfully inserted log entry: {logId: 567, tokens: 150, cost: 3}
```

### 错误流程示例

```
[AUTH] Invalid or disabled API Key: sk-test1...
[ROUTE] No eligible routes found for model: 5
[UPSTREAM] Error response from upstream: {status: 404, statusText: 'Not Found', provider: 'OpenAI', model: 'gpt-5', latency: 456}
[LOG] Failed to log error request: [DatabaseError] ...
```

## 在生产环境中使用

在生产环境中，建议配置以下内容：

1. **日志聚合** - 使用ELK Stack、Splunk或CloudWatch聚合日志
2. **日志级别过滤** - 根据`[TAG]`前缀进行过滤
3. **告警规则** - 对`[ERROR]`和`[WARN]`级别的日志设置告警
4. **日志保留** - 根据需要调整日志保留期限

## 调试技巧

1. **跟踪完整请求流程**：查找相同请求的所有日志标签
2. **识别性能瓶颈**：查找latency值
3. **监控成本**：跟踪成本计算日志
4. **验证权限**：查找PERMISSION和AUTH日志
5. **诊断路由问题**：查找ROUTE和UPSTREAM日志


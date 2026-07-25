# 倍率功能设计文档

## 概述

本功能为 Lean AI Gateway 添加价格倍率（Price Multiplier）机制，支持在供应商（Provider）和模型（Model）级别独立配置倍率，用于灵活调整最终计费价格。

## 设计决策

### 1. 倍率应用方式
- **方案**：乘法叠加
- **公式**：`最终价格 = 基础价格 × 模型倍率 × 供应商倍率`
- **原因**：最直观的计算方式，便于理解和调试

### 2. 供应商倍率存储位置
- **方案**：存储在 Provider 表
- **原因**：一个供应商所有协议共享同一个倍率，配置简单

### 3. 倍率范围
- **范围**：0.10 ~ 10.00
- **默认值**：1.00（无倍率效果）
- **精度**：2 位小数
- **原因**：覆盖大多数商业场景（1折到10倍），避免配置错误

### 4. 模型倍率配置
- **方案**：单一 `price_multiplier` 字段
- **原因**：大多数场景下输入输出的加成比例相同，保持配置简洁

### 5. 实现方案
- **方案**：直接字段扩展
- **原因**：代码路径清晰，倍率逻辑集中在 `calculate_cost()` 一处

### 6. UI 显示
- **方案**：只显示模型倍率，隐藏供应商倍率
- **原因**：简化用户界面，减少认知负担

## 详细设计

### 数据库 Schema 变更

#### Model 表
```python
price_multiplier: Mapped[Decimal] = mapped_column(
    Numeric(4, 2),  # 0.10 ~ 10.00
    default=Decimal("1.00"),
    server_default=text("1.00000000")
)
```

#### Provider 表
```python
price_multiplier: Mapped[Decimal] = mapped_column(
    Numeric(4, 2),  # 0.10 ~ 10.00
    default=Decimal("1.00"),
    server_default=text("1.00000000")
)
```

#### 数据库迁移
创建迁移脚本 `0006_add_price_multipliers.py`：
- 为 `models` 表添加 `price_multiplier` 列
- 为 `providers` 表添加 `price_multiplier` 列
- 设置默认值为 1.0
- 添加 CHECK 约束确保值在 0.1 ~ 10.0 范围内

### 后端定价逻辑变更

#### 修改 `calculate_cost()` 函数
**文件**: `src/ai_gateway/billing/pricing.py`

```python
def calculate_cost(
    model: PricedModel, 
    usage: CanonicalUsage,
    *,
    model_multiplier: Decimal | None = None,
    provider_multiplier: Decimal | None = None,
) -> Decimal:
    """
    最终价格 = (input_tokens * input_price + output_tokens * output_price) 
               / 1_000_000 
               * model_multiplier 
               * provider_multiplier
    
    如果任一倍率为 None，则视为 1.0
    """
    base_cost = (
        usage.input_tokens * model.input_price_per_million +
        usage.output_tokens * model.output_price_per_million
    ) / Decimal("1000000")
    
    multiplier = Decimal("1.0")
    if model_multiplier is not None:
        multiplier *= model_multiplier
    if provider_multiplier is not None:
        multiplier *= provider_multiplier
    
    return (base_cost * multiplier).quantize(Decimal("0.00000001"))
```

#### 修改调用点
需要更新以下调用 `calculate_cost()` 的地方：
1. `src/ai_gateway/billing/service.py` - 预留余额和结算
2. `src/ai_gateway/gateway/service.py` - HTTP 请求处理
3. `src/ai_gateway/gateway/websocket.py` - WebSocket 流式请求

#### 辅助函数
```python
def get_effective_multipliers(
    model: Model,
    route: ModelRoute,
    session: AsyncSession,
) -> tuple[Decimal, Decimal]:
    """返回 (model_multiplier, provider_multiplier)"""
    provider = await session.get(Provider, route.provider_id)
    return (
        model.price_multiplier,
        provider.price_multiplier if provider else Decimal("1.0"),
    )
```

### 后端 API 变更

#### Provider Schema
```python
class ProviderResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    price_multiplier: Decimal  # 新增字段
    created_at: datetime
    updated_at: datetime

class ProviderUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    price_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0.10"),
        le=Decimal("10.00")
    )
```

#### Model Schema
```python
class ModelResponse(BaseModel):
    id: int
    canonical_name: str
    display_name: str
    enabled: bool
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    price_multiplier: Decimal  # 新增字段
    aliases: list[ModelAliasResponse]
    created_at: datetime
    updated_at: datetime

class ModelCreate(BaseModel):
    canonical_name: str
    display_name: str
    enabled: bool = True
    input_price_per_million: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    output_price_per_million: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    price_multiplier: Decimal = Field(
        default=Decimal("1.00"),
        ge=Decimal("0.10"),
        le=Decimal("10.00")
    )
    aliases: list[str] = []

class ModelUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    input_price_per_million: Decimal | None = Field(default=None, ge=Decimal("0"))
    output_price_per_million: Decimal | None = Field(default=None, ge=Decimal("0"))
    price_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0.10"),
        le=Decimal("10.00")
    )
    aliases: list[str] | None = None
```

### 前端 UI 变更

#### Provider 表单
在供应商编辑表单中添加倍率输入框，仅在编辑时可见。

#### Model 表单
在模型编辑表单中添加倍率输入框，显示在价格配置区域。

#### Model 卡片显示
```vue
<div v-if="model.price_multiplier !== '1.00'" class="price-row multiplier">
  <span class="label">价格倍率:</span>
  <el-tag type="warning" size="small">
    {{ model.price_multiplier }}x
  </el-tag>
</div>
```

#### Provider 列表
不显示倍率列（仅在编辑表单中可见）

### 测试策略

#### 单元测试
**文件**: `tests/unit/billing/test_pricing.py`
- 测试 `calculate_cost()` 对不同倍率组合的计算逻辑
- 测试边界值（0.1, 1.0, 10.0）
- 测试错误值验证（负数, 超大值）

#### 集成测试
**文件**: `tests/integration/admin/test_providers.py` 和 `tests/integration/admin/test_models.py`
- 测试 Provider 和 Model API 的倍率字段创建、更新、查询
- 测试范围限制验证

**文件**: `tests/integration/billing/test_billing_flow.py`
- 测试从请求到计费的完整流程中倍率的应用

### 审计日志

#### 后端实现
**文件**: `src/ai_gateway/admin/audit.py`

```python
class AuditAction(StrEnum):
    PROVIDER_MULTIPLIER_UPDATED = "provider_multiplier_updated"
    MODEL_MULTIPLIER_UPDATED = "model_multiplier_updated"

async def log_multiplier_change(
    session: AsyncSession,
    user_id: int,
    resource_type: str,
    resource_id: int,
    old_value: Decimal,
    new_value: Decimal,
):
    """记录倍率变更"""
    audit_log = AuditLog(
        user_id=user_id,
        action=f"{resource_type}_multiplier_updated",
        resource_type=resource_type,
        resource_id=resource_id,
        details={
            "old_multiplier": str(old_value),
            "new_multiplier": str(new_value),
        },
    )
    session.add(audit_log)
    await session.commit()
```

### 文档更新

**文件**: `docs/admin/providers.md` 和 `docs/admin/models.md`
添加倍率配置说明，包括：
- 计算公式
- 配置说明（范围、默认值、精度）
- 使用场景示例
- 注意事项

**文件**: `README.md`
在功能列表中添加倍率功能说明

## 向后兼容性

- 现有数据自动获得默认值 1.0（无倍率效果）
- 不需要数据迁移，新字段立即生效
- 前端表单可以留空或显示默认值
- 现有 API 客户端不受影响

## 实施计划

1. **阶段 1：数据库变更**
   - 创建迁移脚本
   - 执行迁移
   - 验证字段添加

2. **阶段 2：后端实现**
   - 修改 `calculate_cost()` 函数
   - 更新所有调用点
   - 实现 API schema 变更
   - 添加审计日志

3. **阶段 3：前端实现**
   - 更新表单组件
   - 更新卡片显示
   - 添加输入验证

4. **阶段 4：测试**
   - 编写单元测试
   - 编写集成测试
   - 执行测试套件

5. **阶段 5：文档**
   - 更新 API 文档
   - 更新用户指南
   - 更新 README

## 风险与缓解

### 风险 1：倍率计算错误
- **缓解**：详细的单元测试覆盖各种组合场景

### 风险 2：性能影响
- **缓解**：倍率计算为简单的乘法运算，性能影响可忽略

### 风险 3：配置错误
- **缓解**：前后端双重验证，确保值在有效范围内

### 风险 4：审计日志缺失
- **缓解**：在更新 API 中强制调用审计日志记录函数

## 成功标准

1. 所有单元测试和集成测试通过
2. 倍率计算准确无误
3. 前端 UI 正确显示倍率信息
4. 审计日志完整记录所有变更
5. 文档清晰完整

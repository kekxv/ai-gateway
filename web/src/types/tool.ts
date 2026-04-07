// 工具定义类型
export interface ToolDefinition {
  id: string
  name: string              // 工具名称，如 get_weather
  description: string       // 工具描述
  parameters: JSONSchema    // 参数 schema
  type: 'custom' | 'builtin'  // 用户自定义 / 内置
  enabled: boolean
}

// JSON Schema 定义
export interface JSONSchema {
  type: 'object'
  properties: Record<string, SchemaProperty>
  required?: string[]
}

export interface SchemaProperty {
  type: 'string' | 'number' | 'boolean' | 'array' | 'object'
  description?: string
  enum?: string[]
  items?: SchemaProperty
  properties?: Record<string, SchemaProperty>
}

// 工具调用（从 API 接收的格式）
export interface ToolCall {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string  // JSON string
  }
}

// 工具执行结果
export interface ToolCallResult {
  id: string
  toolName: string
  arguments: Record<string, unknown>
  result?: unknown
  error?: string
  status: 'pending' | 'running' | 'success' | 'error'
}

// 内置工具定义
export const BUILTIN_TOOLS: ToolDefinition[] = [
  {
    id: 'get_current_time',
    name: 'get_current_time',
    description: '获取当前时间和日期',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        timezone: {
          type: 'string',
          description: '时区，如 Asia/Shanghai，默认为本地时区'
        }
      }
    }
  },
  {
    id: 'execute_javascript',
    name: 'execute_javascript',
    description: '执行 JavaScript 代码并返回结果。可用于计算、数据处理等。注意：代码中需要使用 return 语句返回结果。',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: '要执行的 JavaScript 代码，需要使用 return 返回结果'
        }
      },
      required: ['code']
    }
  },
  {
    id: 'web_search',
    name: 'web_search',
    description: '在网络上搜索信息',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: '搜索关键词'
        }
      },
      required: ['query']
    }
  },
  {
    id: 'draw_chart',
    name: 'draw_chart',
    description: '绘制图表（柱状图、折线图、饼图等）',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        type: {
          type: 'string',
          description: '图表类型：bar, line, pie, doughnut',
          enum: ['bar', 'line', 'pie', 'doughnut']
        },
        title: {
          type: 'string',
          description: '图表标题'
        },
        labels: {
          type: 'array',
          description: 'X轴标签数组',
          items: { type: 'string' }
        },
        data: {
          type: 'array',
          description: '数据数组',
          items: { type: 'number' }
        }
      },
      required: ['type', 'labels', 'data']
    }
  },
  {
    id: 'save_note',
    name: 'save_note',
    description: '保存笔记内容到本地存储',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        title: {
          type: 'string',
          description: '笔记标题'
        },
        content: {
          type: 'string',
          description: '笔记内容'
        }
      },
      required: ['title', 'content']
    }
  }
]
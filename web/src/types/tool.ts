// 工具定义类型
export interface ToolDefinition {
  id: string
  name: string              // 工具名称，如 get_weather
  description: string       // 工具描述
  parameters: JSONSchema    // 参数 schema
  type: 'custom' | 'builtin'  // 用户自定义 / 内置
  enabled: boolean
  executionCode?: string    // 执行代码（JavaScript），仅自定义工具
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
    id: 'get_location',
    name: 'get_location',
    description: '获取用户当前地理位置（需要用户授权）',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        enableHighAccuracy: {
          type: 'boolean',
          description: '是否启用高精度定位，默认 false'
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
    description: '在网络上搜索信息，返回搜索结果',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: '搜索关键词'
        },
        location: {
          type: 'string',
          description: '搜索位置，如: Austin, Texas, United States（可选，有默认值）'
        },
        hl: {
          type: 'string',
          description: '界面语言，如: en, zh-cn（可选，默认 en）'
        },
        gl: {
          type: 'string',
          description: '国家/地区，如: us, cn（可选，默认 us）'
        }
      },
      required: ['query']
    }
  },
  {
    id: 'fetch_webpage',
    name: 'fetch_webpage',
    description: '获取网页内容，用于读取指定URL的页面数据',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: '要获取的网页URL'
        },
        selector: {
          type: 'string',
          description: 'CSS选择器，用于提取特定内容（可选）'
        }
      },
      required: ['url']
    }
  }
]
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
  items?: SchemaProperty & { required?: string[] }  // Support nested required
  properties?: Record<string, SchemaProperty>
  required?: string[]  // Support required at this level for nested objects
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
        },
        format: {
          type: 'string',
          description: '返回格式：text（纯文本）或 html（保留HTML标签），默认 text'
        }
      },
      required: ['url']
    }
  },
  {
    id: 'web_canvas',
    name: 'web_canvas',
    description: '在Canvas画布上进行绘图，支持矩形、圆形、线条、多边形、文本等。绘制结果直接在页面上显示。',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        width: {
          type: 'number',
          description: '画布宽度，默认400，范围1-2000'
        },
        height: {
          type: 'number',
          description: '画布高度，默认300，范围1-2000'
        },
        backgroundColor: {
          type: 'string',
          description: '背景颜色，如 #ffffff(白色)、#000000(黑色)、transparent(透明)，默认白色'
        },
        operations: {
          type: 'array',
          description: `绘制操作数组。每个操作需显式设置 fill:true 填充或 stroke:true 描边。
支持类型：rect(矩形), circle(圆), ellipse(椭圆), line(线), polygon(多边形), text(文本), arc(弧), bezier(贝塞尔曲线), setStyle(设置样式), translate/rotate/scale/save/restore(变换), clear(清空)`,
          items: {
            type: 'object'
          }
        }
      },
      required: ['operations']
    }
  },
  {
    id: 'execute_javascript',
    name: 'execute_javascript',
    description: '执行 JavaScript 代码并返回结果。代码中的 console.log/console.warn/console.error 输出会被捕获并返回。支持 async/await。',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: '要执行的 JavaScript 代码，使用 return 返回结果'
        },
        timeout: {
          type: 'number',
          description: '执行超时时间(毫秒)，默认5000，最大30000'
        }
      },
      required: ['code']
    }
  },
  {
    id: 'yolo_draw',
    name: 'yolo_draw',
    description: '在用户上传的图片上绘制目标检测边界框。AI负责分类，此工具只负责绘制边界框。结果直接显示在页面上，不回传给 AI。',
    type: 'builtin',
    enabled: true,
    parameters: {
      type: 'object',
      properties: {
        boxes: {
          type: 'array',
          description: '目标检测框数组。坐标格式：x,y 为左上角坐标比例(0-1)，width,height 为宽高比例(0-1)。',
          items: {
            type: 'object',
            properties: {
              x: { type: 'number', description: '左上角 x 坐标比例 (0-1)，0表示最左边' },
              y: { type: 'number', description: '左上角 y 坐标比例 (0-1)，0表示最上边' },
              width: { type: 'number', description: '宽度比例 (0-1)' },
              height: { type: 'number', description: '高度比例 (0-1)' },
              label: { type: 'string', description: '目标标签名称' },
              color: { type: 'string', description: '边界框颜色，如 #ff0000(红色)、#00ff00(绿色)，默认红色' },
              confidence: { type: 'number', description: '置信度 (0-1)，可选' }
            },
            required: ['x', 'y', 'width', 'height']
          }
        },
        color: {
          type: 'string',
          description: '默认边界框颜色，如 #ff0000(红色)，默认红色'
        },
        lineWidth: {
          type: 'number',
          description: '边界框线宽，默认 2'
        },
        fontSize: {
          type: 'number',
          description: '标签字体大小，默认 14'
        },
        showConfidence: {
          type: 'boolean',
          description: '是否显示置信度，默认 true'
        }
      },
      required: ['boxes']
    }
  },
]
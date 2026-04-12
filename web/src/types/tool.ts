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
    description: 'HTML5 Canvas 绘图工具，支持完整的 2D 绘图功能。绘制结果直接在页面上显示。',
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
          description: '背景颜色，如 #ffffff(白色)、transparent(透明)，默认白色'
        },
        operations: {
          type: 'array',
          description: `绘图操作数组。每个操作是一个对象，包含 type 字段指定操作类型。

【基础形状】
- rect: 矩形 {x,y,width,height,fill,stroke,lineWidth}
- roundRect: 圆角矩形 {x,y,width,height,radius/radii,fill,stroke,lineWidth}
- circle: 圆形 {x,y,radius,startAngle,endAngle,fill,stroke,lineWidth}
- ellipse: 椭圆 {x,y,radiusX,radiusY,rotation,startAngle,endAngle,fill,stroke,lineWidth}
- arc: 弧 {x,y,radius,startAngle,endAngle,fill,stroke,lineWidth}
- arcTo: 弧线 {x1,y1,x2,y2,x3,y3,radius,stroke,lineWidth}

【线条路径】
- line: 线段 {x1,y1,x2,y2,stroke,lineWidth}
- moveTo: 移动路径点 {x,y} - 用于 beginPath 后
- lineTo: 添加线段点 {x,y} - 用于 moveTo 后
- polyline: 折线 {points:[{x,y}],stroke,lineWidth}
- polygon: 多边形 {points:[{x,y}],fill,stroke,lineWidth}
- bezier/quadraticCurveTo: 贝塞尔曲线 {cpx,cpy,x,y,stroke} 或 {cp1x,cp1y,cp2x,cp2y,x,y}
- path: SVG路径 {d:"M 0 0 L 100 100",fill,stroke}

【路径操作】
- beginPath: 开始新路径
- closePath: 关闭当前路径
- fillPath: 填充当前路径 {fill}
- strokePath: 描边当前路径 {stroke,lineWidth}
- clip: 裁剪路径

【文字】
- fillText: 填充文字 {text,x,y,font,fill,align,baseline,maxWidth}
- strokeText: 描边文字 {text,x,y,font,stroke,lineWidth,align,baseline,maxWidth}

【图像】
- drawImage: 绘制图片 {src/imageId,x,y,width,height,sx,sy,sWidth,sHeight}

【渐变】
- linearGradient: 线性渐变 {x0,y0,x1,y1,stops:[{offset,color}],applyTo:"fill|stroke"}
- radialGradient: 径向渐变 {x0,y0,r0,x1,y1,r1,stops:[{offset,color}],applyTo}

【样式设置】
- setStyle: 设置样式 {fillStyle,strokeStyle,lineWidth,lineCap,lineJoin,font,globalAlpha,globalCompositeOperation,shadowBlur,shadowColor,shadowOffsetX,shadowOffsetY,lineDash,lineDashOffset,textAlign,textBaseline}

【变形】
- translate: 平移 {x,y}
- rotate: 旋转 {angle} - angle 为弧度
- scale: 缩放 {x,y}
- transform/setTransform: 矩阵变换 {a,b,c,d,e,f} 或 {matrix:[a,b,c,d,e,f]}
- resetTransform: 重置变换

【状态】
- save: 保存当前状态
- restore: 恢复上次保存的状态

【清空】
- clear/clearRect: 清空区域 {x,y,width,height}

通用参数说明：
- fill: 填充颜色或 true(使用默认色)
- stroke: 描边颜色或 true(使用默认色)
- lineWidth: 线条宽度，默认1
- globalCompositeOperation: 合成模式，如 "source-over","multiply","screen","overlay"`,
          items: {
            type: 'object'
          }
        }
      },
      required: ['operations']
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
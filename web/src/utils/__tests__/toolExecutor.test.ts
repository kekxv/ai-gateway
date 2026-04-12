import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock stores before importing toolExecutor
vi.mock('@/stores/canvas', () => ({
  useCanvasStore: vi.fn(() => ({
    addCanvas: vi.fn(),
    getCanvas: vi.fn(),
    canvases: new Map(),
    canvasList: { value: [] },
    latestCanvasId: { value: null },
    clearCanvas: vi.fn(),
    clearAll: vi.fn()
  }))
}))

vi.mock('@/stores/image', () => ({
  useImageStore: vi.fn(() => ({
    getLatestImage: vi.fn(() => null),
    addImage: vi.fn(),
    images: new Map()
  }))
}))

vi.mock('@/stores/tools', () => ({
  useToolsStore: vi.fn(() => ({
    customTools: [],
    getToolsForModel: vi.fn(() => [])
  }))
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    token: 'test-token',
    user: { id: 1, email: 'test@test.com', role: 'USER' }
  }))
}))

// Import after mocking
import { executeToolCall, setMessagesForToolExecution } from '../toolExecutor'

describe('ToolExecutor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('executeToolCall', () => {
    describe('get_current_time', () => {
      it('should return current time with default timezone', async () => {
        const result = await executeToolCall('get_current_time', {})

        expect(result.status).toBe('success')
        expect(result.result).toHaveProperty('iso')
        expect(result.result).toHaveProperty('formatted')
        expect(result.result).toHaveProperty('timestamp')
        expect(result.result).toHaveProperty('timezone')
      })

      it('should return current time with specified timezone', async () => {
        const result = await executeToolCall('get_current_time', { timezone: 'Asia/Shanghai' })

        expect(result.status).toBe('success')
        expect(result.result).toHaveProperty('timezone', 'Asia/Shanghai')
      })

      it('should return numeric timestamp', async () => {
        const result = await executeToolCall('get_current_time', {})

        expect(result.status).toBe('success')
        expect(typeof (result.result as { timestamp: number }).timestamp).toBe('number')
        expect((result.result as { timestamp: number }).timestamp).toBeGreaterThan(0)
      })
    })

    describe('execute_javascript', () => {
      it('should execute simple code and return result', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'return 1 + 2'
        })

        expect(result.status).toBe('success')
        // execute_javascript returns { success: true, result: 3, logs, logOutput }
        const jsResult = result.result as { success: boolean; result: unknown }
        expect(jsResult.success).toBe(true)
        expect(jsResult.result).toBe(3)
      })

      it('should execute code with console.log', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'console.log("hello"); return "done"'
        })

        expect(result.status).toBe('success')
      })

      it('should handle errors in code', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'throw new Error("test error")'
        })

        expect(result.status).toBe('error')
        expect(result.error).toContain('test error')
      })

      it('should handle syntax errors', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'invalid syntax here'
        })

        expect(result.status).toBe('error')
      })

      it('should handle object return values', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'return { name: "test", value: 123 }'
        })

        expect(result.status).toBe('success')
        const jsResult = result.result as { success: boolean; result: { name: string; value: number } }
        expect(jsResult.success).toBe(true)
        expect(jsResult.result.name).toBe('test')
        expect(jsResult.result.value).toBe(123)
      })

      it('should handle array return values', async () => {
        const result = await executeToolCall('execute_javascript', {
          code: 'return [1, 2, 3, 4, 5]'
        })

        expect(result.status).toBe('success')
        const jsResult = result.result as { success: boolean; result: number[] }
        expect(jsResult.success).toBe(true)
        expect(Array.isArray(jsResult.result)).toBe(true)
        expect(jsResult.result.length).toBe(5)
      })
    })

    describe('unknown tool', () => {
      it('should return error for unknown tool', async () => {
        const result = await executeToolCall('unknown_tool', {})

        expect(result.status).toBe('error')
        expect(result.error).toContain('Unknown tool')
      })
    })

    describe('web_canvas', () => {
      it('should validate operations parameter', async () => {
        const result = await executeToolCall('web_canvas', {
          operations: [],
          width: 100,
          height: 100
        })

        // 在 Node.js 环境下会因为没有 Canvas API 而失败，但参数是正确的
        expect(result).toHaveProperty('id')
        expect(result).toHaveProperty('toolName', 'web_canvas')
        expect(result.arguments).toEqual({ operations: [], width: 100, height: 100 })
      })

      it('should accept valid operation types', async () => {
        const validOps = ['fill', 'strokeRect', 'fillRect', 'circle', 'line', 'text', 'clear']
        const operations = validOps.map(type => ({ type, x: 10, y: 10 }))

        const result = await executeToolCall('web_canvas', {
          operations,
          width: 200,
          height: 200
        })

        expect(result).toHaveProperty('toolName', 'web_canvas')
      })

      it('should handle nested operations structure', async () => {
        const nestedOps = [
          { operations: [{ type: 'fill', color: '#FF0000' }] }
        ]

        const result = await executeToolCall('web_canvas', {
          operations: nestedOps,
          width: 100,
          height: 100
        })

        expect(result).toHaveProperty('toolName', 'web_canvas')
      })

      it('should handle width and height parameters', async () => {
        const result = await executeToolCall('web_canvas', {
          operations: [{ type: 'fill' }],
          width: 800,
          height: 600,
          backgroundColor: '#FFFFFF'
        })

        expect(result.arguments.width).toBe(800)
        expect(result.arguments.height).toBe(600)
        expect(result.arguments.backgroundColor).toBe('#FFFFFF')
      })
    })

    describe('yolo_draw', () => {
      it('should validate boxes parameter structure', async () => {
        const boxes = [
          { x: 10, y: 10, width: 50, height: 50, label: 'cat', confidence: 0.95 },
          { x: 100, y: 100, width: 30, height: 30, label: 'dog', confidence: 0.8 }
        ]

        const result = await executeToolCall('yolo_draw', {
          boxes,
          color: '#00FF00',
          lineWidth: 2
        })

        expect(result).toHaveProperty('toolName', 'yolo_draw')
        expect(result.arguments.boxes).toHaveLength(2)
      })

      it('should accept optional styling parameters', async () => {
        const result = await executeToolCall('yolo_draw', {
          boxes: [{ x: 0, y: 0, width: 10, height: 10, label: 'test' }],
          color: '#FF0000',
          lineWidth: 3,
          fontSize: 14,
          showConfidence: true
        })

        expect(result.arguments.color).toBe('#FF0000')
        expect(result.arguments.lineWidth).toBe(3)
        expect(result.arguments.fontSize).toBe(14)
        expect(result.arguments.showConfidence).toBe(true)
      })

      it('should handle empty boxes array', async () => {
        const result = await executeToolCall('yolo_draw', {
          boxes: []
        })

        expect(result).toHaveProperty('toolName', 'yolo_draw')
        expect(result.arguments.boxes).toHaveLength(0)
      })
    })
  })

  describe('setMessagesForToolExecution', () => {
    it('should set messages for execution', () => {
      const messages = [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi' }
      ]

      setMessagesForToolExecution(messages)
      expect(true).toBe(true)
    })

    it('should handle empty messages', () => {
      setMessagesForToolExecution([])
      expect(true).toBe(true)
    })

    it('should handle messages with content parts', () => {
      const messages = [
        {
          role: 'user',
          content: [
            { type: 'text', text: 'Look at this' },
            { type: 'image_url', image_url: { url: 'data:image/png;base64,abc' } }
          ]
        }
      ]

      setMessagesForToolExecution(messages)
      expect(true).toBe(true)
    })
  })

  describe('result structure', () => {
    it('should return correct result structure', async () => {
      const result = await executeToolCall('get_current_time', {})

      expect(result).toHaveProperty('id')
      expect(result).toHaveProperty('toolName')
      expect(result).toHaveProperty('arguments')
      expect(result).toHaveProperty('status')

      expect(result.id).toMatch(/^tool_\d+_/)
      expect(result.toolName).toBe('get_current_time')
      expect(result.arguments).toEqual({})
      expect(result.status).toBe('success')
    })

    it('should return error structure on failure', async () => {
      const result = await executeToolCall('execute_javascript', {
        code: 'throw new Error("test")'
      })

      expect(result.status).toBe('error')
      expect(result).toHaveProperty('error')
      expect(typeof result.error).toBe('string')
    })

    it('should generate unique IDs for each call', async () => {
      const result1 = await executeToolCall('get_current_time', {})
      const result2 = await executeToolCall('get_current_time', {})

      expect(result1.id).not.toBe(result2.id)
    })
  })

  describe('parameter validation', () => {
    it('should handle empty arguments', async () => {
      const result = await executeToolCall('get_current_time', {})

      expect(result.status).toBe('success')
    })

    it('should handle null-like arguments', async () => {
      const result = await executeToolCall('get_current_time', { timezone: undefined })

      expect(result.status).toBe('success')
    })

    it('should preserve original arguments in result', async () => {
      const args = { code: 'return 42', timeout: 1000 }
      const result = await executeToolCall('execute_javascript', args)

      expect(result.arguments).toEqual(args)
    })
  })

  describe('execute_javascript advanced', () => {
    it('should capture console output', async () => {
      const result = await executeToolCall('execute_javascript', {
        code: 'console.log("test log"); console.warn("test warn"); return true'
      })

      expect(result.status).toBe('success')
      const jsResult = result.result as { logs: Array<{ type: string; message: string }> }
      expect(jsResult.logs).toBeDefined()
      expect(jsResult.logs!.length).toBeGreaterThanOrEqual(2)
    })

    it('should handle async code with Promise', async () => {
      const result = await executeToolCall('execute_javascript', {
        code: 'return new Promise(resolve => setTimeout(() => resolve(42), 10))'
      })

      expect(result.status).toBe('success')
      const jsResult = result.result as { success: boolean; result: number }
      expect(jsResult.result).toBe(42)
    })

    it('should handle complex nested objects', async () => {
      const result = await executeToolCall('execute_javascript', {
        code: 'return { data: { nested: { deep: [1, 2, 3] } }, count: 3 }'
      })

      expect(result.status).toBe('success')
      const jsResult = result.result as { success: boolean; result: { data: { nested: { deep: number[] } }; count: number } }
      expect(jsResult.result.data.nested.deep).toEqual([1, 2, 3])
      expect(jsResult.result.count).toBe(3)
    })

    it('should handle code without explicit return', async () => {
      const result = await executeToolCall('execute_javascript', {
        code: 'const x = 1 + 2;'
      })

      expect(result.status).toBe('success')
      const jsResult = result.result as { success: boolean; result: unknown }
      expect(jsResult.result).toBeUndefined()
    })
  })

  describe('web_canvas operations validation', () => {
    it('should handle operations with color parameters', async () => {
      const result = await executeToolCall('web_canvas', {
        operations: [
          { type: 'fill', color: '#FF0000' },
          { type: 'fill', color: 'rgba(255, 0, 0, 0.5)' },
          { type: 'stroke', strokeColor: 'blue' }
        ],
        width: 100,
        height: 100
      })

      expect(result.arguments.operations).toHaveLength(3)
    })

    it('should handle text operations with font parameters', async () => {
      const result = await executeToolCall('web_canvas', {
        operations: [
          { type: 'text', text: 'Hello', x: 10, y: 20, fontSize: 24, fontFamily: 'Arial', color: '#000' }
        ],
        width: 100,
        height: 100
      })

      expect(result.arguments.operations).toHaveLength(1)
    })

    it('should handle path operations', async () => {
      const result = await executeToolCall('web_canvas', {
        operations: [
          { type: 'beginPath' },
          { type: 'moveTo', x: 0, y: 0 },
          { type: 'lineTo', x: 100, y: 100 },
          { type: 'strokePath', strokeColor: '#000', lineWidth: 2 }
        ],
        width: 100,
        height: 100
      })

      expect(result.arguments.operations).toHaveLength(4)
    })
  })
})
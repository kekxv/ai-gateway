import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ToolDefinition, ToolCallResult } from '@/types/tool'
import { BUILTIN_TOOLS } from '@/types/tool'

// Default enabled tools
const DEFAULT_ENABLED_TOOLS = [
  'get_current_time',
  'execute_javascript',
  'web_search',
  'fetch_webpage',
  'web_canvas'
]

export const useToolsStore = defineStore('tools', () => {
  // 自定义工具列表
  const customTools = ref<ToolDefinition[]>([])

  // 内置工具列表
  const builtinTools = ref<ToolDefinition[]>([...BUILTIN_TOOLS])

  // 所有工具
  const allTools = computed(() => [...builtinTools.value, ...customTools.value])

  // 启用的工具 ID 列表
  const enabledToolIds = ref<Set<string>>(new Set())

  // 启用的工具
  const enabledTools = computed(() => allTools.value.filter(t => enabledToolIds.value.has(t.id)))

  // 工具执行结果
  const toolResults = ref<Map<string, ToolCallResult>>(new Map())

  // 从 localStorage 加载启用状态
  function loadEnabledState() {
    try {
      const saved = localStorage.getItem('enabled_tools')
      if (saved) {
        const ids = JSON.parse(saved) as string[]
        enabledToolIds.value = new Set(ids)
      } else {
        // First time: enable default tools
        enabledToolIds.value = new Set(DEFAULT_ENABLED_TOOLS)
        saveEnabledState()
      }
    } catch {
      enabledToolIds.value = new Set(DEFAULT_ENABLED_TOOLS)
    }
  }

  // 保存启用状态到 localStorage
  function saveEnabledState() {
    localStorage.setItem('enabled_tools', JSON.stringify(Array.from(enabledToolIds.value)))
  }

  // 从 localStorage 加载自定义工具
  function loadCustomTools() {
    try {
      const saved = localStorage.getItem('custom_tools')
      if (saved) {
        customTools.value = JSON.parse(saved)
      }
    } catch {
      customTools.value = []
    }
  }

  // 保存自定义工具到 localStorage
  function saveCustomTools() {
    localStorage.setItem('custom_tools', JSON.stringify(customTools.value))
  }

  // 添加自定义工具
  function addTool(tool: Omit<ToolDefinition, 'id' | 'type'>) {
    const newTool: ToolDefinition = {
      ...tool,
      id: `custom_${Date.now()}`,
      type: 'custom'
    }
    customTools.value.push(newTool)
    saveCustomTools()
  }

  // 更新自定义工具
  function updateTool(id: string, updates: Partial<ToolDefinition>) {
    const index = customTools.value.findIndex(t => t.id === id)
    if (index !== -1) {
      customTools.value[index] = { ...customTools.value[index], ...updates }
      saveCustomTools()
    }
  }

  // 删除自定义工具
  function deleteTool(id: string) {
    customTools.value = customTools.value.filter(t => t.id !== id)
    enabledToolIds.value.delete(id)
    saveCustomTools()
    saveEnabledState()
  }

  // 切换工具启用状态
  function toggleTool(id: string) {
    if (enabledToolIds.value.has(id)) {
      enabledToolIds.value.delete(id)
    } else {
      enabledToolIds.value.add(id)
    }
    saveEnabledState()
  }

  // 设置工具启用状态
  function setToolEnabled(id: string, enabled: boolean) {
    if (enabled) {
      enabledToolIds.value.add(id)
    } else {
      enabledToolIds.value.delete(id)
    }
    saveEnabledState()
  }

  // 批量设置启用状态
  function setEnabledTools(ids: string[]) {
    enabledToolIds.value = new Set(ids)
    saveEnabledState()
  }

  // 获取工具定义（用于发送给模型）
  function getToolsForModel() {
    return enabledTools.value.map(tool => ({
      type: 'function',
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters
      }
    }))
  }

  // 设置工具执行结果
  function setToolResult(result: ToolCallResult) {
    toolResults.value.set(result.id, result)
  }

  // 获取工具执行结果
  function getToolResult(id: string) {
    return toolResults.value.get(id)
  }

  // 清除工具执行结果
  function clearToolResults() {
    toolResults.value.clear()
  }

  // 获取单个工具
  function getTool(id: string): ToolDefinition | undefined {
    return allTools.value.find(t => t.id === id)
  }

  // 检查工具名称是否存在
  function isToolNameExists(name: string): boolean {
    return allTools.value.some(t => t.name === name)
  }

  // 检查工具是否启用
  function isToolEnabled(id: string): boolean {
    return enabledToolIds.value.has(id)
  }

  // 初始化时加载
  loadEnabledState()
  loadCustomTools()

  return {
    customTools,
    builtinTools,
    allTools,
    enabledTools,
    enabledToolIds,
    toolResults,
    addTool,
    updateTool,
    deleteTool,
    toggleTool,
    setToolEnabled,
    setEnabledTools,
    getToolsForModel,
    setToolResult,
    getToolResult,
    clearToolResults,
    getTool,
    isToolNameExists,
    isToolEnabled
  }
})
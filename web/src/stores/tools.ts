import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ToolDefinition, ToolCallResult } from '@/types/tool'
import { BUILTIN_TOOLS } from '@/types/tool'

export const useToolsStore = defineStore('tools', () => {
  // 自定义工具列表
  const customTools = ref<ToolDefinition[]>([])

  // 内置工具列表
  const builtinTools = ref<ToolDefinition[]>([...BUILTIN_TOOLS])

  // 所有工具
  const allTools = computed(() => [...builtinTools.value, ...customTools.value])

  // 启用的工具
  const enabledTools = computed(() => allTools.value.filter(t => t.enabled))

  // 工具执行结果
  const toolResults = ref<Map<string, ToolCallResult>>(new Map())

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
    saveCustomTools()
  }

  // 切换工具启用状态
  function toggleTool(id: string) {
    const tool = allTools.value.find(t => t.id === id)
    if (tool) {
      tool.enabled = !tool.enabled
      if (tool.type === 'custom') {
        saveCustomTools()
      }
    }
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

  // 初始化时加载
  loadCustomTools()

  return {
    customTools,
    builtinTools,
    allTools,
    enabledTools,
    toolResults,
    addTool,
    updateTool,
    deleteTool,
    toggleTool,
    getToolsForModel,
    setToolResult,
    getToolResult,
    clearToolResults,
    getTool,
    isToolNameExists
  }
})
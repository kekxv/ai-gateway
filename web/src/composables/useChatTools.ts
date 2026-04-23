import { ref, type Ref } from 'vue'
import { ElMessage } from '@/plugins/element-plus-services'
import { executeToolCall, setMessagesForToolExecution } from '@/utils/toolExecutor'
import { useSkillsStore } from '@/stores/skills'
import type { ToolCall, ToolCallResult } from '@/types/tool'

// Safe JSON parser with artifact cleanup
function cleanTokenizerArtifacts(str: string): string {
  let cleaned = str
  cleaned = cleaned.replace(/<\\?\|[^>|]*\\?\|>/g, '')
  cleaned = cleaned.replace(/<\\?\|[^\s,\}\]]*/g, '')
  cleaned = cleaned.replace(/\"\\?\|/g, '"')
  cleaned = cleaned.replace(/\\?\|\"/g, '"')
  cleaned = cleaned.replace(/<\\?\|/g, '')
  cleaned = cleaned.replace(/\\?\|>/g, '')
  return cleaned
}

function safeParseJson(str: string): Record<string, unknown> {
  if (!str || str.trim() === '') return {}
  try {
    const cleaned = cleanTokenizerArtifacts(str)
    return JSON.parse(cleaned)
  } catch {
    try {
      let aggressiveClean = str
        .replace(/<\\?\|[^>|]*\\?\|>/g, '')
        .replace(/<\\?\|/g, '')
        .replace(/\\?\|>/g, '')
        .replace(/\"\\?\|/g, '"')
        .replace(/\\?\|\"/g, '"')
        .replace(/\\?\|(?![\s,\}\]])/g, '')
        .replace(/[\x00-\x1F]/g, '')
      return JSON.parse(aggressiveClean)
    } catch {
      return {}
    }
  }
}

export function useChatTools(
  messages: Ref<Array<{ role: string; content: string }>>
) {
  const skillsStore = useSkillsStore()

  // Active skill state
  const activeSkillName = ref<string | null>(null)
  const activeSkillInstructions = ref<string | null>(null)

  // Activate a skill by name
  const activateSkill = (skillName: string) => {
    if (!skillName) {
      activeSkillName.value = null
      activeSkillInstructions.value = null
      ElMessage.success('已取消技能')
      return
    }

    const skill = skillsStore.getSkillByName(skillName)
    if (skill) {
      activeSkillName.value = skill.name
      activeSkillInstructions.value = skill.instructions || null
      ElMessage.success(`已激活技能: ${skill.display_name || skill.name}`)
    } else {
      ElMessage.warning('未找到该技能')
    }
  }

  // Deactivate current skill
  const deactivateSkill = () => {
    activeSkillName.value = null
    activeSkillInstructions.value = null
  }

  // Execute tool calls and send results back to AI
  const executeToolCallsAndContinue = async (
    toolCalls: ToolCall[],
    _conversationId: number,
    onToolResult?: (results: ToolCallResult[]) => void
  ): Promise<ToolCallResult[]> => {
    const results: ToolCallResult[] = toolCalls.map(tc => ({
      id: tc.id,
      toolName: tc.function.name,
      arguments: safeParseJson(tc.function.arguments || '{}'),
      status: 'running'
    }))

    // Update UI with running status
    if (onToolResult) onToolResult(results)

    // Execute each tool
    for (let i = 0; i < results.length; i++) {
      const toolCall = results[i]
      try {
        // Set current messages for tool execution (for yolo_draw)
        setMessagesForToolExecution(messages.value.map(m => ({
          role: m.role,
          content: m.content
        })))
        const result = await executeToolCall(toolCall.toolName, toolCall.arguments as Record<string, unknown>)
        results[i] = result
      } catch (e) {
        results[i] = {
          ...toolCall,
          status: 'error',
          error: e instanceof Error ? e.message : String(e)
        }
      }
    }

    // Update UI with final results
    if (onToolResult) onToolResult(results)

    return results
  }

  return {
    activeSkillName,
    activeSkillInstructions,
    activateSkill,
    deactivateSkill,
    executeToolCallsAndContinue,
    safeParseJson
  }
}
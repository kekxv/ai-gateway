<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑工具' : '添加自定义工具'"
    width="600px"
    class="tool-form-dialog"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <!-- 基本信息 -->
      <el-form-item label="工具名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="如: get_weather"
          :disabled="isEdit"
        />
        <div class="form-hint">建议使用下划线分隔的命名方式，如 get_weather_info</div>
      </el-form-item>

      <el-form-item label="工具描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="描述这个工具的功能和用途..."
        />
        <div class="form-hint">清晰的描述有助于AI正确使用此工具</div>
      </el-form-item>

      <!-- 参数定义 -->
      <el-form-item label="参数定义">
        <div class="params-editor">
          <div
            v-for="(param, index) in form.parametersList"
            :key="index"
            class="param-row"
          >
            <el-input v-model="param.name" placeholder="参数名" class="param-name-input" />
            <el-select v-model="param.type" placeholder="类型" class="param-type-select">
              <el-option label="字符串" value="string" />
              <el-option label="数字" value="number" />
              <el-option label="布尔值" value="boolean" />
              <el-option label="数组" value="array" />
            </el-select>
            <el-checkbox v-model="param.required">必填</el-checkbox>
            <button class="remove-param-btn" @click="removeParam(index)">
              <el-icon><Delete /></el-icon>
            </button>

            <!-- 参数详情（可展开） -->
            <div v-if="param.showDetails" class="param-details">
              <el-input v-model="param.description" placeholder="参数描述" />

              <!-- enum值（仅string类型） -->
              <div v-if="param.type === 'string'" class="enum-editor">
                <el-input
                  v-model="param.enumStr"
                  placeholder="可选值（逗号分隔）: option1, option2"
                />
              </div>

              <!-- 数组元素类型 -->
              <div v-if="param.type === 'array'" class="items-editor">
                <el-select v-model="param.itemsType" placeholder="元素类型" style="width: 100%">
                  <el-option label="字符串" value="string" />
                  <el-option label="数字" value="number" />
                </el-select>
              </div>
            </div>

            <button class="expand-param-btn" @click="param.showDetails = !param.showDetails">
              <el-icon>
                <ArrowDown v-if="!param.showDetails" />
                <ArrowUp v-else />
              </el-icon>
              详情
            </button>
          </div>

          <button class="add-param-btn" @click="addParam">
            <el-icon><Plus /></el-icon>
            添加参数
          </button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="submitForm" :loading="submitting">
        {{ isEdit ? '保存修改' : '创建工具' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { ToolDefinition, SchemaProperty } from '@/types/tool'
import { useToolsStore } from '@/stores/tools'

interface ParamFormItem {
  name: string
  type: 'string' | 'number' | 'boolean' | 'array'
  required: boolean
  description: string
  enumStr: string  // 逗号分隔的enum值
  itemsType: 'string' | 'number'
  showDetails: boolean
}

const props = defineProps<{
  modelValue: boolean
  tool: ToolDefinition | null
  isEdit: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'save', tool: Omit<ToolDefinition, 'id' | 'type'>): void
}>()

const toolsStore = useToolsStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const form = reactive({
  name: '',
  description: '',
  parametersList: [] as ParamFormItem[]
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入工具名称', trigger: 'blur' },
    { min: 2, max: 64, message: '名称长度应在2-64字符之间', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: '名称应以小写字母开头，只能包含小写字母、数字和下划线', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (!props.isEdit && value) {
          const exists = toolsStore.isToolNameExists(value)
          if (exists) {
            callback(new Error('工具名称已存在'))
            return
          }
        }
        callback()
      },
      trigger: 'blur'
    }
  ],
  description: [
    { required: true, message: '请输入工具描述', trigger: 'blur' },
    { min: 5, message: '描述至少5个字符', trigger: 'blur' }
  ]
}

const addParam = () => {
  form.parametersList.push({
    name: '',
    type: 'string',
    required: false,
    description: '',
    enumStr: '',
    itemsType: 'string',
    showDetails: false
  })
}

const removeParam = (index: number) => {
  form.parametersList.splice(index, 1)
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.parametersList = []
}

// 监听tool变化，初始化表单数据
watch(() => props.tool, (tool) => {
  if (tool && props.isEdit) {
    form.name = tool.name
    form.description = tool.description
    form.parametersList = Object.entries(tool.parameters.properties)
      .filter(([, prop]) => prop.type !== 'object')
      .map(([name, prop]) => ({
        name,
        type: prop.type as 'string' | 'number' | 'boolean' | 'array',
        required: tool.parameters.required?.includes(name) ?? false,
        description: prop.description || '',
        enumStr: prop.enum?.join(', ') || '',
        itemsType: (prop.items?.type as 'string' | 'number') || 'string',
        showDetails: false
      }))
  } else {
    resetForm()
  }
}, { immediate: true })

// 监听弹窗打开，重置表单（添加模式）
watch(visible, (isOpen) => {
  if (isOpen && !props.isEdit) {
    resetForm()
  }
})

const buildParameters = (): ToolDefinition['parameters'] => {
  const properties: Record<string, SchemaProperty> = {}
  const required: string[] = []

  for (const param of form.parametersList) {
    if (!param.name.trim()) continue

    const prop: SchemaProperty = {
      type: param.type,
      description: param.description || undefined
    }

    if (param.type === 'string' && param.enumStr) {
      prop.enum = param.enumStr.split(',').map(s => s.trim()).filter(Boolean)
    }

    if (param.type === 'array') {
      prop.items = { type: param.itemsType }
    }

    properties[param.name] = prop

    if (param.required) {
      required.push(param.name)
    }
  }

  return {
    type: 'object',
    properties,
    required: required.length > 0 ? required : undefined
  }
}

const submitForm = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  // 验证参数名唯一性
  const paramNames = form.parametersList.map(p => p.name).filter(Boolean)
  const uniqueNames = new Set(paramNames)
  if (paramNames.length !== uniqueNames.size) {
    ElMessage.error('参数名称不能重复')
    return
  }

  submitting.value = true

  try {
    const toolData = {
      name: form.name,
      description: form.description,
      parameters: buildParameters(),
      enabled: props.isEdit ? props.tool!.enabled : true
    }

    emit('save', toolData)
    visible.value = false
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.tool-form-dialog .el-dialog__body {
  padding: 20px 24px;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.params-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 8px;
  flex-wrap: wrap;
}

.param-name-input {
  width: 140px;
}

.param-type-select {
  width: 100px;
}

.remove-param-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #dc2626;
  cursor: pointer;
  border-radius: 4px;
}

.remove-param-btn:hover {
  background: #fee2e2;
}

.param-details {
  width: 100%;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.enum-editor,
.items-editor {
  margin-top: 4px;
}

.expand-param-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 12px;
}

.expand-param-btn:hover {
  color: #374151;
}

.add-param-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  background: transparent;
  color: #667eea;
  border: 1px solid #667eea;
  border-radius: 6px;
  cursor: pointer;
}

.add-param-btn:hover {
  background: #eef2ff;
}
</style>
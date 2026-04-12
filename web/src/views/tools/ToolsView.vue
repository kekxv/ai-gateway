<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('tool.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Builtin Tools -->
    <div class="tools-section">
      <div class="section-header">
        <h3 class="section-title">{{ t('tool.builtin') }}</h3>
        <span class="section-count">{{ builtinTools.length }}</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div
          v-for="tool in builtinTools"
          :key="tool.id"
          class="tool-card"
          :class="{ enabled: isToolEnabled(tool.id) }"
        >
          <div class="card-header">
            <div class="tool-info">
              <h4 class="tool-name">{{ tool.name }}</h4>
              <el-tag size="small" type="info" effect="plain">{{ t('tool.builtin') }}</el-tag>
            </div>
            <el-switch
              :model-value="isToolEnabled(tool.id)"
              @change="toggleTool(tool.id)"
            />
          </div>
          <p class="tool-desc">{{ tool.description }}</p>
          <div class="card-footer">
            <el-button size="small" link type="primary" @click="openDetailDialog(tool)">
              {{ t('tool.viewDetail') }}
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Custom Tools -->
    <div class="tools-section">
      <div class="section-header">
        <h3 class="section-title">{{ t('tool.custom') }}</h3>
        <span class="section-count">{{ toolsStore.customTools.length }}</span>
      </div>
      <div v-if="toolsStore.customTools.length === 0" class="empty-state">
        <div class="text-gray-500 mb-4">{{ t('common.noData') }}</div>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          {{ t('tool.createFirst') }}
        </el-button>
      </div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div
          v-for="tool in toolsStore.customTools"
          :key="tool.id"
          class="tool-card"
          :class="{ enabled: isToolEnabled(tool.id) }"
        >
          <div class="card-header">
            <div class="tool-info">
              <h4 class="tool-name">{{ tool.name }}</h4>
              <el-tag size="small" type="success" effect="plain">{{ t('tool.custom') }}</el-tag>
            </div>
            <el-switch
              :model-value="isToolEnabled(tool.id)"
              @change="toggleTool(tool.id)"
            />
          </div>
          <p class="tool-desc">{{ tool.description }}</p>
          <div class="card-footer">
            <el-button size="small" link type="primary" @click="openEditDialog(tool)">
              {{ t('common.edit') }}
            </el-button>
            <el-button size="small" link type="danger" @click="deleteTool(tool)">
              {{ t('common.delete') }}
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? t('tool.editTitle') : t('tool.createTitle')"
      :width="isMobile ? '95%' : '700px'"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="edit-form">
        <div class="form-row">
          <el-form-item :label="t('tool.name')" prop="name" class="form-item-name">
            <el-input
              v-model="form.name"
              placeholder="e.g., get_weather_info"
              :disabled="isEdit"
            />
            <div class="form-hint">{{ t('tool.nameHint') }}</div>
          </el-form-item>

          <el-form-item :label="t('tool.description')" prop="description" class="form-item-desc">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              placeholder="Describe what this tool does..."
            />
          </el-form-item>
        </div>

        <el-form-item :label="t('tool.parameters')">
          <div class="params-container">
            <div v-if="form.parametersList.length > 0" class="params-list">
              <div v-for="(param, index) in form.parametersList" :key="index" class="param-card">
                <div class="param-main-row">
                  <div class="param-field param-field-name">
                    <label>{{ t('tool.paramName') }}</label>
                    <el-input v-model="param.name" placeholder="e.g., city" />
                  </div>
                  <div class="param-field param-field-type">
                    <label>{{ t('tool.paramType') }}</label>
                    <el-select v-model="param.type">
                      <el-option label="string" value="string" />
                      <el-option label="number" value="number" />
                      <el-option label="boolean" value="boolean" />
                      <el-option label="array" value="array" />
                    </el-select>
                  </div>
                  <div class="param-field param-field-required">
                    <label>{{ t('tool.paramRequired') }}</label>
                    <el-checkbox v-model="param.required" />
                  </div>
                  <div class="param-field param-field-desc">
                    <label>{{ t('tool.paramDesc') }}</label>
                    <el-input v-model="param.description" placeholder="Parameter description" />
                  </div>
                  <div class="param-field param-field-action">
                    <button class="delete-param-btn" @click="removeParam(index)" title="Delete">
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                </div>
                <!-- enum for string type -->
                <div v-if="param.type === 'string'" class="param-extra-row">
                  <label>{{ t('tool.paramEnum') }}</label>
                  <el-input v-model="param.enumStr" placeholder="option1, option2, ..." />
                </div>
                <!-- items for array type -->
                <div v-if="param.type === 'array'" class="param-extra-row">
                  <label>{{ t('tool.paramItemsType') }}</label>
                  <el-select v-model="param.itemsType" style="width: 120px;">
                    <el-option label="string" value="string" />
                    <el-option label="number" value="number" />
                  </el-select>
                </div>
              </div>
            </div>
            <button class="add-param-btn" @click="addParam">
              <el-icon><Plus /></el-icon>
              {{ t('tool.addParam') }}
            </button>
          </div>
        </el-form-item>

        <el-form-item :label="t('tool.executionCode')">
          <div class="code-editor-wrapper">
            <div class="code-editor-header">
              <span class="code-hint">{{ t('tool.codeHint') }}</span>
              <button class="test-code-btn" @click="testCode" :disabled="!form.executionCode">
                <el-icon><VideoPlay /></el-icon>
                {{ t('tool.testRun') }}
              </button>
            </div>
            <textarea
              v-model="form.executionCode"
              class="code-editor"
              placeholder="// Example: Get weather info
const city = args.city || 'Beijing';
const response = await fetch(`https://api.example.com/weather?city=${city}`);
const data = await response.json();
return { city, temperature: data.temp, weather: data.weather };"
              rows="12"
              spellcheck="false"
            ></textarea>
            <div v-if="testResult" class="test-result">
              <div class="test-result-header">
                <span>{{ t('tool.testResult') }}</span>
                <el-tag :type="testResult.success ? 'success' : 'danger'" size="small">
                  {{ testResult.success ? t('common.success') : t('common.error') }}
                </el-tag>
              </div>
              <pre class="test-result-content">{{ testResult.output }}</pre>
            </div>
          </div>
        </el-form-item>

        <!-- JSON Schema Preview -->
        <div class="schema-preview-section">
          <div class="preview-header">
            <span>{{ t('tool.schemaPreview') }}</span>
            <el-tag v-if="!schemaValid" type="danger" size="small">{{ t('tool.schemaError') }}</el-tag>
          </div>
          <pre class="schema-preview">{{ computedSchema }}</pre>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting" :disabled="!canSave">
          {{ isEdit ? t('common.save') : t('common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Detail Dialog for Builtin Tools -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="detailTool?.name"
      :width="isMobile ? '95%' : '600px'"
    >
      <div v-if="detailTool" class="detail-content">
        <div class="detail-section">
          <label class="detail-label">{{ t('tool.description') }}</label>
          <p class="detail-value">{{ detailTool.description }}</p>
        </div>
        <div class="detail-section">
          <label class="detail-label">{{ t('tool.parameters') }}</label>
          <div v-if="Object.keys(detailTool.parameters.properties).length > 0" class="params-detail">
            <div v-for="(prop, name) in detailTool.parameters.properties" :key="name" class="param-detail-item">
              <div class="param-detail-header">
                <span class="param-detail-name">{{ name }}</span>
                <el-tag size="small">{{ prop.type }}</el-tag>
                <el-tag v-if="isRequired(name)" size="small" type="warning">{{ t('tool.required') }}</el-tag>
              </div>
              <p class="param-detail-desc">{{ prop.description || '-' }}</p>
              <div v-if="prop.enum" class="param-detail-extra">
                <span class="extra-label">{{ t('tool.enumValues') }}</span>
                <span class="extra-value">{{ prop.enum.join(', ') }}</span>
              </div>
              <div v-if="prop.type === 'array' && prop.items" class="param-detail-extra">
                <span class="extra-label">{{ t('tool.itemsType') }}</span>
                <el-tag size="small">{{ prop.items.type }}</el-tag>
              </div>
            </div>
          </div>
          <p v-else class="no-params">{{ t('tool.noParams') }}</p>
        </div>
        <div class="detail-section">
          <label class="detail-label">{{ t('tool.jsonSchema') }}</label>
          <pre class="schema-code">{{ formatSchema(detailTool.parameters) }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">{{ t('common.close') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, VideoPlay } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useToolsStore } from '@/stores/tools'
import type { ToolDefinition, SchemaProperty } from '@/types/tool'

const { t } = useI18n()
const toolsStore = useToolsStore()

const builtinTools = computed(() => toolsStore.builtinTools)
const isToolEnabled = (id: string) => toolsStore.isToolEnabled(id)
const toggleTool = (id: string) => toolsStore.toggleTool(id)

const dialogVisible = ref(false)
const detailDialogVisible = ref(false)
const isEdit = ref(false)
const selectedTool = ref<ToolDefinition | null>(null)
const detailTool = ref<ToolDefinition | null>(null)
const formRef = ref<FormInstance>()
const submitting = ref(false)
const isMobile = ref(false)
const testResult = ref<{ success: boolean; output: string } | null>(null)

interface ParamFormItem {
  name: string
  type: 'string' | 'number' | 'boolean' | 'array'
  required: boolean
  description: string
  enumStr: string
  itemsType: 'string' | 'number'
}

const form = reactive({
  name: '',
  description: '',
  parametersList: [] as ParamFormItem[],
  executionCode: ''
})

const rules: FormRules = {
  name: [
    { required: true, message: 'Name is required', trigger: 'blur' },
    { min: 2, max: 64, message: 'Name length should be 2-64 characters', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: 'Name must start with lowercase letter, contain only lowercase, numbers, underscores', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (!isEdit.value && value) {
          const exists = toolsStore.isToolNameExists(value)
          if (exists) {
            callback(new Error('Tool name already exists'))
            return
          }
        }
        callback()
      },
      trigger: 'blur'
    }
  ],
  description: [
    { required: true, message: 'Description is required', trigger: 'blur' },
    { min: 5, message: 'Description must be at least 5 characters', trigger: 'blur' }
  ]
}

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.parametersList = []
  form.executionCode = ''
  testResult.value = null
}

const openCreateDialog = () => {
  isEdit.value = false
  selectedTool.value = null
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (tool: ToolDefinition) => {
  isEdit.value = true
  selectedTool.value = tool
  form.name = tool.name
  form.description = tool.description
  form.executionCode = tool.executionCode || ''
  form.parametersList = Object.entries(tool.parameters.properties)
    .filter(([, prop]) => prop.type !== 'object')
    .map(([name, prop]) => ({
      name,
      type: prop.type as 'string' | 'number' | 'boolean' | 'array',
      required: tool.parameters.required?.includes(name) ?? false,
      description: prop.description || '',
      enumStr: prop.enum?.join(', ') || '',
      itemsType: (prop.items?.type as 'string' | 'number') || 'string'
    }))
  testResult.value = null
  dialogVisible.value = true
}

const openDetailDialog = (tool: ToolDefinition) => {
  detailTool.value = tool
  detailDialogVisible.value = true
}

const isRequired = (propName: string) => {
  return detailTool.value?.parameters.required?.includes(propName) ?? false
}

const formatSchema = (schema: ToolDefinition['parameters']) => {
  return JSON.stringify(schema, null, 2)
}

const addParam = () => {
  form.parametersList.push({
    name: '',
    type: 'string',
    required: false,
    description: '',
    enumStr: '',
    itemsType: 'string'
  })
}

const removeParam = (index: number) => {
  form.parametersList.splice(index, 1)
}

const testCode = async () => {
  if (!form.executionCode) return

  const testArgs: Record<string, unknown> = {}
  for (const param of form.parametersList) {
    if (param.name) {
      if (param.type === 'string') testArgs[param.name] = 'test'
      else if (param.type === 'number') testArgs[param.name] = 100
      else if (param.type === 'boolean') testArgs[param.name] = true
      else if (param.type === 'array') testArgs[param.name] = ['item1', 'item2']
    }
  }

  try {
    const safeExec = new Function('args', `"use strict"; ${form.executionCode}`)
    const output = await safeExec(testArgs)
    testResult.value = {
      success: true,
      output: JSON.stringify(output, null, 2)
    }
  } catch (error) {
    testResult.value = {
      success: false,
      output: error instanceof Error ? error.message : String(error)
    }
  }
}

const computedSchema = computed(() => {
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

  return JSON.stringify({
    type: 'object',
    properties,
    required: required.length > 0 ? required : undefined
  }, null, 2)
})

const schemaValid = computed(() => {
  const names = form.parametersList.map(p => p.name.trim()).filter(Boolean)
  return names.length === new Set(names).size
})

const canSave = computed(() => {
  return form.name.trim().length >= 2 &&
         form.description.trim().length >= 5 &&
         schemaValid.value &&
         form.executionCode.trim().length > 0
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

  const paramNames = form.parametersList.map(p => p.name).filter(Boolean)
  const uniqueNames = new Set(paramNames)
  if (paramNames.length !== uniqueNames.size) {
    ElMessage.error('Parameter names must be unique')
    return
  }

  submitting.value = true
  try {
    const toolData = {
      name: form.name,
      description: form.description,
      parameters: buildParameters(),
      executionCode: form.executionCode
    }

    if (isEdit.value && selectedTool.value) {
      toolsStore.updateTool(selectedTool.value.id, toolData)
      ElMessage.success('Tool updated')
    } else {
      toolsStore.addTool(toolData)
      ElMessage.success('Tool created')
    }

    dialogVisible.value = false
  } finally {
    submitting.value = false
  }
}

const deleteTool = async (tool: ToolDefinition) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    toolsStore.deleteTool(tool.id)
    ElMessage.success('Tool deleted')
  } catch {
    // User cancelled
  }
}
</script>

<style scoped>
.tools-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #374151;
}

.section-count {
  font-size: 12px;
  padding: 2px 8px;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 12px;
}

.tool-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.tool-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.tool-card.enabled {
  border-color: #22c55e;
  background: #f0fdf4;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.tool-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  font-family: 'SF Mono', Monaco, monospace;
}

.tool-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
  margin-bottom: 12px;
}

.card-footer {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.empty-state {
  text-align: center;
  padding: 32px;
}

/* Form styles */
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-item-name {
  flex: 1;
  min-width: 200px;
}

.form-item-desc {
  flex: 2;
}

.form-hint {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

/* Parameters */
.params-container {
  width: 100%;
}

.params-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.param-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}

.param-main-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.param-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-field label {
  font-size: 11px;
  color: #6b7280;
}

.param-field-name {
  flex: 1;
  min-width: 120px;
}

.param-field-type {
  width: 100px;
}

.param-field-required {
  width: 50px;
  align-items: center;
  padding-top: 20px;
}

.param-field-desc {
  flex: 2;
  min-width: 150px;
}

.param-field-action {
  width: 32px;
  padding-top: 20px;
}

.delete-param-btn {
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

.delete-param-btn:hover {
  background: #fee2e2;
}

.param-extra-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
}

.param-extra-row label {
  font-size: 12px;
  color: #6b7280;
}

.add-param-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  background: transparent;
  color: #667eea;
  border: 1px dashed #667eea;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.add-param-btn:hover {
  background: #eef2ff;
}

/* Code editor */
.code-editor-wrapper {
  width: 100%;
}

.code-editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.code-hint {
  font-size: 12px;
  color: #6b7280;
}

.test-code-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #22c55e;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}

.test-code-btn:hover {
  background: #16a34a;
}

.test-code-btn:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

.code-editor {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  min-height: 180px;
  background: #fff;
  color: #1f2937;
}

.code-editor:focus {
  outline: none;
  border-color: #667eea;
}

.test-result {
  margin-top: 12px;
}

.test-result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}

.test-result-content {
  padding: 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  overflow-x: auto;
  max-height: 150px;
}

/* Schema preview */
.schema-preview-section {
  margin-top: 16px;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}

.schema-preview {
  padding: 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
}

/* Detail dialog */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-section {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
}

.detail-label {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
  display: block;
}

.detail-value {
  font-size: 14px;
  color: #374151;
}

.params-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-detail-item {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
}

.param-detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.param-detail-name {
  font-family: 'SF Mono', Monaco, monospace;
  font-weight: 500;
  color: #374151;
}

.param-detail-desc {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}

.param-detail-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e5e7eb;
}

.extra-label {
  font-size: 11px;
  color: #9ca3af;
}

.extra-value {
  font-size: 12px;
  color: #667eea;
}

.no-params {
  text-align: center;
  color: #9ca3af;
  padding: 16px;
}

.schema-code {
  padding: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  overflow-x: auto;
}

/* Responsive */
@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
  }

  .param-main-row {
    flex-wrap: wrap;
  }

  .param-field-name {
    min-width: 100px;
  }

  .param-field-desc {
    flex: 1 1 100%;
    min-width: 0;
  }
}
</style>
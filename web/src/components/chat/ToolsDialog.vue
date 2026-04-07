<template>
  <el-dialog
    v-model="visible"
    title="工具设置"
    width="900px"
    class="tools-dialog"
    :close-on-click-modal="false"
  >
    <div class="tools-dialog-body">
      <!-- 左侧：工具列表 -->
      <div class="tools-list-panel">
        <!-- 内置工具 -->
        <div class="tools-group">
          <div class="group-header">
            <span>内置工具</span>
            <span class="group-count">{{ toolsStore.builtinTools.length }}</span>
          </div>
          <div class="group-items">
            <div
              v-for="tool in toolsStore.builtinTools"
              :key="tool.id"
              class="tool-item"
              :class="{ selected: selectedTool?.id === tool.id, enabled: tool.enabled }"
              @click="selectTool(tool)"
            >
              <el-checkbox
                :model-value="tool.enabled"
                @change="toggleTool(tool.id)"
                @click.stop
              />
              <span class="tool-name">{{ tool.name }}</span>
              <el-icon class="tool-icon"><View /></el-icon>
            </div>
          </div>
        </div>

        <!-- 自定义工具 -->
        <div class="tools-group">
          <div class="group-header">
            <span>自定义工具</span>
            <span class="group-count">{{ toolsStore.customTools.length }}</span>
            <button class="add-tool-btn" @click="addNewTool" title="添加自定义工具">
              <el-icon><Plus /></el-icon>
            </button>
          </div>
          <div class="group-items">
            <div
              v-for="tool in toolsStore.customTools"
              :key="tool.id"
              class="tool-item"
              :class="{ selected: selectedTool?.id === tool.id, enabled: tool.enabled }"
              @click="selectTool(tool)"
            >
              <el-checkbox
                :model-value="tool.enabled"
                @change="toggleTool(tool.id)"
                @click.stop
              />
              <span class="tool-name">{{ tool.name }}</span>
              <div class="tool-actions-mini">
                <button class="mini-btn" @click.stop="deleteTool(tool)" title="删除">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>
            <div v-if="toolsStore.customTools.length === 0" class="empty-hint">
              <p>暂无自定义工具</p>
              <button class="add-first-btn" @click="addNewTool">
                <el-icon><Plus /></el-icon>
                添加第一个工具
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：编辑面板 -->
      <div class="tools-edit-panel">
        <!-- 未选中状态 -->
        <div v-if="!selectedTool" class="empty-state">
          <el-icon class="empty-icon"><Tools /></el-icon>
          <p>请从左侧选择一个工具查看或编辑</p>
        </div>

        <!-- 内置工具：只读展示 -->
        <div v-else-if="selectedTool.type === 'builtin'" class="tool-view">
          <div class="view-header">
            <h3 class="tool-title">{{ selectedTool.name }}</h3>
            <el-tag type="info" size="small">内置工具</el-tag>
          </div>
          <div class="view-section">
            <label>描述</label>
            <p class="section-content">{{ selectedTool.description }}</p>
          </div>
          <div class="view-section">
            <label>参数定义</label>
            <div v-if="Object.keys(selectedTool.parameters.properties).length > 0" class="params-readonly-list">
              <div v-for="(prop, name) in selectedTool.parameters.properties" :key="name" class="param-readonly-card">
                <div class="param-readonly-main">
                  <div class="param-readonly-name">
                    <span class="label">参数名</span>
                    <span class="value mono">{{ name }}</span>
                  </div>
                  <div class="param-readonly-type">
                    <span class="label">类型</span>
                    <el-tag size="small">{{ prop.type }}</el-tag>
                  </div>
                  <div class="param-readonly-required">
                    <span class="label">必填</span>
                    <el-icon v-if="isRequired(name)" class="required-icon"><CircleCheckFilled /></el-icon>
                    <span v-else class="not-required">-</span>
                  </div>
                  <div class="param-readonly-desc">
                    <span class="label">描述</span>
                    <span class="value">{{ prop.description || '-' }}</span>
                  </div>
                </div>
                <!-- enum 展示 -->
                <div v-if="prop.enum" class="param-readonly-extra">
                  <span class="label">可选值:</span>
                  <span class="enum-values">{{ prop.enum.join(', ') }}</span>
                </div>
                <!-- array items 展示 -->
                <div v-if="prop.type === 'array' && prop.items" class="param-readonly-extra">
                  <span class="label">元素类型:</span>
                  <el-tag size="small">{{ prop.items.type }}</el-tag>
                </div>
              </div>
            </div>
            <div v-else class="no-params">此工具无需参数</div>
          </div>
          <div class="view-section">
            <label>执行代码</label>
            <pre class="code-preview light" v-html="getHighlightedBuiltinCode(selectedTool.name)"></pre>
          </div>
          <div class="view-section">
            <label>JSON Schema</label>
            <pre class="schema-preview light" v-html="highlightCode(formatSchema(selectedTool.parameters), 'json')"></pre>
          </div>
        </div>

        <!-- 自定义工具：可编辑 -->
        <div v-else class="tool-edit">
          <div class="edit-header">
            <h3 class="tool-title">{{ isNewTool ? '新建工具' : selectedTool.name }}</h3>
            <el-tag type="success" size="small">自定义工具</el-tag>
          </div>

          <el-form ref="formRef" :model="editForm" :rules="rules" label-position="top" class="edit-form">
            <div class="form-row">
              <el-form-item label="工具名称" prop="name" class="form-item-name">
                <el-input
                  v-model="editForm.name"
                  placeholder="如: get_weather_info"
                  :disabled="!isNewTool"
                />
                <div class="form-hint">建议使用下划线分隔的命名方式</div>
              </el-form-item>

              <el-form-item label="工具描述" prop="description" class="form-item-desc">
                <el-input
                  v-model="editForm.description"
                  type="textarea"
                  :rows="2"
                  placeholder="描述这个工具的功能和用途..."
                />
              </el-form-item>
            </div>

            <el-form-item label="参数定义">
              <div class="params-container">
                <div v-if="editForm.parametersList.length > 0" class="params-list">
                  <div v-for="(param, index) in editForm.parametersList" :key="index" class="param-card">
                    <div class="param-main-row">
                      <div class="param-field param-field-name">
                        <label>参数名</label>
                        <el-input v-model="param.name" placeholder="如: city" />
                      </div>
                      <div class="param-field param-field-type">
                        <label>类型</label>
                        <el-select v-model="param.type">
                          <el-option label="string" value="string" />
                          <el-option label="number" value="number" />
                          <el-option label="boolean" value="boolean" />
                          <el-option label="array" value="array" />
                        </el-select>
                      </div>
                      <div class="param-field param-field-required">
                        <label>必填</label>
                        <el-checkbox v-model="param.required" />
                      </div>
                      <div class="param-field param-field-desc">
                        <label>描述</label>
                        <el-input v-model="param.description" placeholder="参数说明" />
                      </div>
                      <div class="param-field param-field-action">
                        <button class="delete-param-btn" @click="removeParam(index)" title="删除">
                          <el-icon><Delete /></el-icon>
                        </button>
                      </div>
                    </div>
                    <!-- enum（string类型） -->
                    <div v-if="param.type === 'string'" class="param-extra-row">
                      <label>可选值 (enum):</label>
                      <el-input v-model="param.enumStr" placeholder="option1, option2, ..." />
                    </div>
                    <!-- items（array类型） -->
                    <div v-if="param.type === 'array'" class="param-extra-row">
                      <label>元素类型:</label>
                      <el-select v-model="param.itemsType" style="width: 120px;">
                        <el-option label="string" value="string" />
                        <el-option label="number" value="number" />
                      </el-select>
                    </div>
                  </div>
                </div>
                <button class="add-param-btn" @click="addParam">
                  <el-icon><Plus /></el-icon>
                  添加参数
                </button>
              </div>
            </el-form-item>

            <!-- 执行代码编辑区 -->
            <el-form-item label="执行代码">
              <div class="code-editor-wrapper">
                <div class="code-editor-header">
                  <span class="code-hint">使用 <code>args</code> 访问参数，使用 <code>return</code> 返回结果。支持 async/await。</span>
                  <button class="test-code-btn" @click="testCode" :disabled="!editForm.executionCode">
                    <el-icon><VideoPlay /></el-icon>
                    测试执行
                  </button>
                </div>
                <textarea
                  v-model="editForm.executionCode"
                  class="code-editor light"
                  placeholder="// 示例: 获取天气信息
// args 中包含定义的参数
const city = args.city || '北京';
const response = await fetch(`https://api.example.com/weather?city=${city}`);
const data = await response.json();
return {
  city: city,
  temperature: data.temp,
  weather: data.weather
};"
                  rows="12"
                  spellcheck="false"
                ></textarea>
                <div v-if="testResult" class="test-result">
                  <div class="test-result-header">
                    <span>测试结果</span>
                    <el-tag :type="testResult.success ? 'success' : 'danger'" size="small">
                      {{ testResult.success ? '成功' : '失败' }}
                    </el-tag>
                  </div>
                  <pre class="test-result-content light" v-html="highlightCode(testResult.output, 'json')"></pre>
                </div>
              </div>
            </el-form-item>
          </el-form>

          <!-- JSON Schema 实时预览 -->
          <div class="schema-preview-section">
            <div class="preview-header">
              <span>JSON Schema 预览</span>
              <el-tag v-if="!schemaValid" type="danger" size="small">有错误</el-tag>
            </div>
            <pre class="schema-preview light" v-html="highlightedSchema"></pre>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button v-if="selectedTool?.type === 'custom' || isNewTool" type="primary" @click="saveChanges" :disabled="!canSave">
        {{ isNewTool ? '创建工具' : '保存修改' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, View, Tools, CircleCheckFilled, VideoPlay } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useToolsStore } from '@/stores/tools'
import type { ToolDefinition, SchemaProperty } from '@/types/tool'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'

// 注册语言
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)

interface ParamFormItem {
  name: string
  type: 'string' | 'number' | 'boolean' | 'array'
  required: boolean
  description: string
  enumStr: string
  itemsType: 'string' | 'number'
}

interface TestResult {
  success: boolean
  output: string
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const toolsStore = useToolsStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const selectedTool = ref<ToolDefinition | null>(null)
const isNewTool = ref(false)
const formRef = ref<FormInstance>()
const testResult = ref<TestResult | null>(null)

const editForm = reactive({
  name: '',
  description: '',
  parametersList: [] as ParamFormItem[],
  executionCode: ''
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入工具名称', trigger: 'blur' },
    { min: 2, max: 64, message: '名称长度应在2-64字符之间', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: '名称应以小写字母开头，只能包含小写字母、数字和下划线', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (isNewTool.value && value) {
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

// 内置工具的执行代码
const builtinCodes: Record<string, string> = {
  get_current_time: `// 获取当前时间
function getCurrentTime(timezone) {
  const now = new Date();
  const options = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    weekday: 'long',
    timeZone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
  };
  return {
    iso: now.toISOString(),
    formatted: now.toLocaleString('zh-CN', options),
    timezone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
    timestamp: now.getTime()
  };
}
return getCurrentTime(args.timezone);`,

  get_location: `// 获取当前地理位置
return new Promise((resolve, reject) => {
  if (!navigator.geolocation) {
    reject(new Error('浏览器不支持地理位置功能'));
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (position) => {
      resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        altitude: position.coords.altitude,
        altitudeAccuracy: position.coords.altitudeAccuracy,
        heading: position.coords.heading,
        speed: position.coords.speed,
        timestamp: new Date(position.timestamp).toISOString()
      });
    },
    (error) => {
      const messages = {
        1: '用户拒绝了地理位置请求',
        2: '无法获取位置信息',
        3: '获取位置超时'
      };
      reject(new Error(messages[error.code] || error.message));
    },
    { enableHighAccuracy: args.enableHighAccuracy || false, timeout: 10000 }
  );
});`,

  execute_javascript: `// 执行 JavaScript 代码
const code = args.code;
try {
  const safeEval = new Function(code);
  return safeEval();
} catch (error) {
  return { error: error.message };
}`,

  web_search: `// 网络搜索 (使用 SerpAPI)
const query = args.query;
const location = args.location || 'Austin, Texas, United States';
const hl = args.hl || 'en';
const gl = args.gl || 'us';

const params = new URLSearchParams({
  q: query,
  location: location,
  hl: hl,
  gl: gl,
  google_domain: 'google.com'
});

const url = \`https://serpapi.com/search.json?\${params.toString()}\`;
const response = await fetch(\`https://corsproxy.io/?\${encodeURIComponent(url)}\`);
const data = await response.json();

// 提取搜索结果
const results = (data.organic_results || []).map(item => ({
  title: item.title,
  snippet: item.snippet || '',
  url: item.link
}));

return {
  query,
  location,
  total_results: data.search_information?.total_results || results.length,
  results: results.slice(0, 10)
};`,

  fetch_webpage: `// 获取网页内容
const url = args.url;
const selector = args.selector;

// 使用 CORS 代理
const proxyUrl = \`https://corsproxy.io/?\${encodeURIComponent(url)}\`;
const response = await fetch(proxyUrl);
const html = await response.text();

// 提取页面内容
const parser = new DOMParser();
const doc = parser.parseFromString(html, 'text/html');

if (selector) {
  const elements = doc.querySelectorAll(selector);
  const contents = Array.from(elements).map(el => ({
    text: el.textContent?.trim() || '',
    html: el.innerHTML
  }));
  return { url, selector, matched: contents.length, contents };
}

// 获取标题和文本内容
const title = doc.querySelector('title')?.textContent || '';
const body = doc.body;
body.querySelectorAll('script, style, nav, footer').forEach(el => el.remove());
const textContent = body.textContent?.replace(/\\s+/g, ' ').trim().slice(0, 5000) || '';

return { url, title, textContent, htmlLength: html.length };`
}

const getBuiltinCode = (toolName: string): string => {
  return builtinCodes[toolName] || '// 内置工具执行代码'
}

// 语法高亮函数
const highlightCode = (code: string, language: 'javascript' | 'json' = 'javascript'): string => {
  try {
    return hljs.highlight(code, { language }).value
  } catch {
    return code
  }
}

// 高亮内置工具代码
const getHighlightedBuiltinCode = (toolName: string): string => {
  const code = getBuiltinCode(toolName)
  return highlightCode(code, 'javascript')
}

// 高亮 JSON Schema
const highlightedSchema = computed(() => {
  return highlightCode(computedSchema.value, 'json')
})

// 选中工具时初始化表单
watch(selectedTool, (tool) => {
  if (tool && tool.type === 'custom') {
    editForm.name = tool.name
    editForm.description = tool.description
    editForm.executionCode = tool.executionCode || ''
    editForm.parametersList = Object.entries(tool.parameters.properties)
      .filter(([, prop]) => prop.type !== 'object')
      .map(([name, prop]) => ({
        name,
        type: prop.type as 'string' | 'number' | 'boolean' | 'array',
        required: tool.parameters.required?.includes(name) ?? false,
        description: prop.description || '',
        enumStr: prop.enum?.join(', ') || '',
        itemsType: (prop.items?.type as 'string' | 'number') || 'string'
      }))
  } else {
    resetForm()
  }
})

// 弹窗关闭时重置状态
watch(visible, (isOpen) => {
  if (!isOpen) {
    selectedTool.value = null
    isNewTool.value = false
    testResult.value = null
    resetForm()
  }
})

const resetForm = () => {
  editForm.name = ''
  editForm.description = ''
  editForm.parametersList = []
  editForm.executionCode = ''
}

const selectTool = (tool: ToolDefinition) => {
  selectedTool.value = tool
  isNewTool.value = false
  testResult.value = null
}

const toggleTool = (id: string) => {
  toolsStore.toggleTool(id)
}

const addNewTool = () => {
  selectedTool.value = {
    id: 'new',
    name: '',
    description: '',
    parameters: { type: 'object', properties: {} },
    type: 'custom',
    enabled: true,
    executionCode: ''
  } as ToolDefinition
  isNewTool.value = true
  resetForm()
}

const addParam = () => {
  editForm.parametersList.push({
    name: '',
    type: 'string',
    required: false,
    description: '',
    enumStr: '',
    itemsType: 'string'
  })
}

const removeParam = (index: number) => {
  editForm.parametersList.splice(index, 1)
}

const deleteTool = (tool: ToolDefinition) => {
  ElMessageBox.confirm(
    `确定要删除工具 "${tool.name}" 吗？`,
    '删除工具',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(() => {
    toolsStore.deleteTool(tool.id)
    if (selectedTool.value?.id === tool.id) {
      selectedTool.value = null
    }
    ElMessage.success('工具已删除')
  }).catch(() => {})
}

const isRequired = (propName: string) => {
  return selectedTool.value?.parameters.required?.includes(propName) ?? false
}

const formatSchema = (schema: ToolDefinition['parameters']) => {
  return JSON.stringify(schema, null, 2)
}

// 测试执行代码
const testCode = async () => {
  if (!editForm.executionCode) return

  // 构造测试参数
  const testArgs: Record<string, unknown> = {}
  for (const param of editForm.parametersList) {
    if (param.name) {
      // 根据类型生成测试值
      if (param.type === 'string') testArgs[param.name] = 'test'
      else if (param.type === 'number') testArgs[param.name] = 100
      else if (param.type === 'boolean') testArgs[param.name] = true
      else if (param.type === 'array') testArgs[param.name] = ['item1', 'item2']
    }
  }

  try {
    const safeExec = new Function('args', `
      "use strict";
      ${editForm.executionCode}
    `)
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

// 实时生成 JSON Schema
const computedSchema = computed(() => {
  const properties: Record<string, SchemaProperty> = {}
  const required: string[] = []

  for (const param of editForm.parametersList) {
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
  const names = editForm.parametersList.map(p => p.name.trim()).filter(Boolean)
  return names.length === new Set(names).size
})

const canSave = computed(() => {
  return editForm.name.trim().length >= 2 &&
         editForm.description.trim().length >= 5 &&
         schemaValid.value &&
         editForm.executionCode.trim().length > 0
})

const saveChanges = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  // 验证参数名唯一性
  const paramNames = editForm.parametersList.map(p => p.name).filter(Boolean)
  const uniqueNames = new Set(paramNames)
  if (paramNames.length !== uniqueNames.size) {
    ElMessage.error('参数名称不能重复')
    return
  }

  const toolData = {
    name: editForm.name,
    description: editForm.description,
    parameters: buildParameters(),
    executionCode: editForm.executionCode,
    enabled: true
  }

  if (isNewTool.value) {
    toolsStore.addTool(toolData)
    ElMessage.success('工具已创建')
  } else if (selectedTool.value) {
    toolsStore.updateTool(selectedTool.value.id, toolData)
    ElMessage.success('工具已更新')
  }

  visible.value = false
}

const buildParameters = (): ToolDefinition['parameters'] => {
  const properties: Record<string, SchemaProperty> = {}
  const required: string[] = []

  for (const param of editForm.parametersList) {
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
</script>

<style scoped>
.tools-dialog .el-dialog__body {
  padding: 0;
}

.tools-dialog-body {
  display: flex;
  height: 600px;
  border-top: 1px solid #e5e7eb;
}

/* 左侧列表面板 */
.tools-list-panel {
  width: 240px;
  border-right: 1px solid #e5e7eb;
  background: #f9fafb;
  overflow-y: auto;
  flex-shrink: 0;
}

.tools-group {
  padding: 12px 0;
}

.group-header {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 8px;
}

.group-count {
  font-size: 11px;
  padding: 2px 6px;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 10px;
}

.add-tool-btn {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #667eea;
  border: none;
  color: #fff;
  cursor: pointer;
  border-radius: 4px;
  margin-left: auto;
}

.add-tool-btn:hover {
  background: #5a67d8;
}

.group-items {
  padding: 0 8px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.tool-item:hover {
  background: #e5e7eb;
}

.tool-item.selected {
  background: #eef2ff;
}

.tool-item.enabled {
  background: #f0fdf4;
}

.tool-item.selected.enabled {
  background: #eef2ff;
}

.tool-name {
  flex: 1;
  font-size: 13px;
  font-family: 'SF Mono', 'Monaco', monospace;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-icon {
  color: #6b7280;
  font-size: 14px;
}

.tool-actions-mini {
  display: flex;
  gap: 4px;
}

.mini-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  border-radius: 4px;
}

.mini-btn:hover {
  background: #fee2e2;
  color: #dc2626;
}

.empty-hint {
  padding: 24px 16px;
  text-align: center;
  color: #9ca3af;
}

.empty-hint p {
  margin-bottom: 8px;
  font-size: 13px;
}

.add-first-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}

.add-first-btn:hover {
  background: #5a67d8;
}

/* 右侧编辑面板 */
.tools-edit-panel {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}

/* 工具查看/编辑区 */
.tool-view, .tool-edit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.view-header, .edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tool-title {
  font-size: 18px;
  font-weight: 600;
  color: #374151;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.view-section {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
}

.view-section label {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
  display: block;
}

.section-content {
  font-size: 14px;
  color: #374151;
}

/* 参数定义容器 */
.params-container {
  width: 100%;
}

.params-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

/* 参数卡片 */
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
  font-weight: 500;
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
  white-space: nowrap;
}

.param-extra-row .el-input {
  flex: 1;
}

/* 只读参数列表 */
.params-readonly-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-readonly-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
}

.param-readonly-main {
  display: flex;
  gap: 16px;
  align-items: center;
}

.param-readonly-main > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.param-readonly-main .label {
  font-size: 10px;
  color: #9ca3af;
  text-transform: uppercase;
}

.param-readonly-main .value {
  font-size: 13px;
  color: #374151;
}

.param-readonly-name {
  min-width: 120px;
}

.param-readonly-type {
  width: 80px;
}

.param-readonly-required {
  width: 50px;
  text-align: center;
}

.param-readonly-desc {
  flex: 1;
}

.param-readonly-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5e7eb;
}

.param-readonly-extra .label {
  font-size: 11px;
  color: #6b7280;
}

.enum-values {
  font-size: 12px;
  color: #667eea;
}

.required-icon {
  color: #22c55e;
  font-size: 14px;
}

.not-required {
  color: #d1d5db;
}

.mono {
  font-family: 'SF Mono', 'Monaco', monospace;
}

.no-params {
  text-align: center;
  color: #9ca3af;
  padding: 16px;
  font-size: 13px;
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

/* 表单样式 */
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
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

/* 代码编辑器 */
.code-editor-wrapper {
  width: 100%;
}

.code-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.code-hint {
  font-size: 12px;
  color: #6b7280;
}

.code-hint code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  color: #667eea;
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
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  min-height: 180px;
}

.code-editor.light {
  background: #ffffff;
  color: #1f2937;
}

.code-editor:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
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
  border-radius: 6px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  overflow-x: auto;
  max-height: 150px;
}

.test-result-content.light {
  background: #f9fafb;
  color: #374151;
  border: 1px solid #e5e7eb;
}

/* Schema 预览 - 亮色主题 */
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

.schema-preview,
.code-preview {
  padding: 12px;
  border-radius: 6px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
}

.schema-preview.light,
.code-preview.light,
.test-result-content.light {
  background: #f9fafb;
  color: #374151;
  border: 1px solid #e5e7eb;
}

/* highlight.js 亮色主题样式 */
.code-preview.light :deep(.hljs-keyword),
.schema-preview.light :deep(.hljs-keyword) {
  color: #d73a49;
}

.code-preview.light :deep(.hljs-string),
.schema-preview.light :deep(.hljs-string) {
  color: #032f62;
}

.code-preview.light :deep(.hljs-number),
.schema-preview.light :deep(.hljs-number) {
  color: #005cc5;
}

.code-preview.light :deep(.hljs-function),
.schema-preview.light :deep(.hljs-function) {
  color: #6f42c1;
}

.code-preview.light :deep(.hljs-comment),
.schema-preview.light :deep(.hljs-comment) {
  color: #6a737d;
  font-style: italic;
}

.code-preview.light :deep(.hljs-variable),
.schema-preview.light :deep(.hljs-variable) {
  color: #e36209;
}

.code-preview.light :deep(.hljs-title),
.schema-preview.light :deep(.hljs-title) {
  color: #6f42c1;
}

.code-preview.light :deep(.hljs-built_in),
.schema-preview.light :deep(.hljs-built_in) {
  color: #005cc5;
}

.code-preview.light :deep(.hljs-params),
.schema-preview.light :deep(.hljs-params) {
  color: #24292e;
}

.code-preview.light :deep(.hljs-attr),
.schema-preview.light :deep(.hljs-attr) {
  color: #005cc5;
}

.code-preview.light :deep(.hljs-literal),
.schema-preview.light :deep(.hljs-literal) {
  color: #005cc5;
}

.code-preview.light :deep(.hljs-punctuation),
.schema-preview.light :deep(.hljs-punctuation) {
  color: #24292e;
}

/* 响应式 */
@media (max-width: 768px) {
  .tools-dialog .el-dialog {
    width: 95% !important;
  }

  .tools-dialog-body {
    flex-direction: column;
    height: auto;
    min-height: 400px;
  }

  .tools-list-panel {
    width: 100%;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
  }

  .form-row {
    flex-direction: column;
  }

  .param-main-row {
    flex-wrap: wrap;
  }

  .param-field-name {
    min-width: 100px;
  }

  .param-field-type {
    width: 80px;
  }

  .param-field-desc {
    flex: 1 1 100%;
    min-width: 0;
  }

  .param-readonly-main {
    flex-wrap: wrap;
    gap: 8px;
  }

  .param-readonly-name {
    min-width: 100px;
  }

  .param-readonly-desc {
    flex: 1 1 100%;
  }
}
</style>
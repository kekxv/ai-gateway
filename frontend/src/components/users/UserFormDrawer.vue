<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElInput,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type { UserCreate, UserResponse, UserRole, UserUpdate } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  user: UserResponse | null
  submitting: boolean
  currentUserId: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: UserCreate | UserUpdate]
}>()

const email = ref('')
const password = ref('')
const role = ref<UserRole>('user')
const isActive = ref(true)
const initialBalance = ref('0.00000000')
const emailError = ref('')
const passwordError = ref('')
const initialBalanceError = ref('')

const editing = computed(() => props.user !== null)
const editingSelf = computed(() => props.user?.id === props.currentUserId)
const title = computed(() => (editing.value ? '编辑用户' : '新建用户'))
const unsignedMoneyPattern = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,8})?$/

function clearTransientState(): void {
  password.value = ''
}

function resetForm(): void {
  const user = props.user
  email.value = user?.email ?? ''
  password.value = ''
  role.value = user?.role ?? 'user'
  isActive.value = user?.is_active ?? true
  initialBalance.value = '0.00000000'
  emailError.value = ''
  passwordError.value = ''
  initialBalanceError.value = ''
}

watch(
  () => [props.modelValue, props.user] as const,
  ([open]) => {
    if (open) resetForm()
    else clearTransientState()
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(clearTransientState)

function requestClose(): void {
  if (props.submitting) return
  clearTransientState()
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value && props.submitting) return
  if (!value) clearTransientState()
  emit('update:modelValue', value)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearTransientState()
  done()
}

function validate(): boolean {
  emailError.value = ''
  passwordError.value = ''
  initialBalanceError.value = ''
  if (email.value.trim() === '') emailError.value = '请输入邮箱地址'
  if (!editing.value && password.value.trim() === '') passwordError.value = '请输入初始密码'
  if (!editing.value && !unsignedMoneyPattern.test(initialBalance.value.trim())) {
    initialBalanceError.value = '请输入非负普通小数，最多 12 位整数和 8 位小数'
  }
  return (
    emailError.value === '' &&
    passwordError.value === '' &&
    initialBalanceError.value === ''
  )
}

function submitForm(): void {
  if (props.submitting || !validate()) return
  const user = props.user
  if (user === null) {
    emit('submit', {
      email: email.value.trim(),
      password: password.value,
      role: role.value,
      initial_balance: initialBalance.value.trim(),
    })
    return
  }

  const payload: UserUpdate = {}
  if (email.value.trim() !== user.email) payload.email = email.value.trim()
  if (password.value.trim() !== '') payload.password = password.value
  if (role.value !== user.role) payload.role = role.value
  if (!editingSelf.value && isActive.value !== user.is_active) payload.is_active = isActive.value
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 32rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @closed="clearTransientState"
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ title }}</h2>
        <p class="drawer-description">
          {{ editing ? '更新账号资料与访问状态。密码留空时保持不变。' : '创建账号并设置初始可用余额。' }}
        </p>
      </div>
    </template>

    <ElForm :disabled="submitting" label-position="top" @submit.prevent="submitForm">
      <ElFormItem label="邮箱" :error="emailError">
        <ElInput v-model="email" data-test="user-email" maxlength="320" autocomplete="off" />
      </ElFormItem>
      <ElFormItem :label="editing ? '新密码（可选）' : '初始密码'" :error="passwordError">
        <ElInput
          v-model="password"
          data-test="user-password"
          type="password"
          show-password
          autocomplete="new-password"
        />
      </ElFormItem>
      <ElFormItem label="角色">
        <select v-model="role" data-test="user-role" class="role-select" :disabled="submitting">
          <option value="admin">管理员</option>
          <option value="user">普通用户</option>
        </select>
      </ElFormItem>
      <ElFormItem v-if="!editing" label="初始余额" :error="initialBalanceError">
        <ElInput
          v-model="initialBalance"
          data-test="user-initial-balance"
          inputmode="decimal"
          autocomplete="off"
        />
      </ElFormItem>
      <ElFormItem v-else label="账号启用">
        <fieldset data-test="user-active" class="active-control" :disabled="editingSelf">
          <ElSwitch
            v-model="isActive"
            :disabled="editingSelf"
            active-text="启用"
            inactive-text="停用"
          />
        </fieldset>
        <p v-if="editingSelf" class="self-hint">当前登录管理员不能停用自己。</p>
      </ElFormItem>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton data-test="user-cancel" :disabled="submitting" @click="requestClose">
          取消
        </ElButton>
        <ElButton
          data-test="user-submit"
          type="primary"
          :loading="submitting"
          @click="submitForm"
        >
          {{ editing ? '保存修改' : '创建用户' }}
        </ElButton>
      </div>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading {
  margin: 0;
  color: var(--gateway-text);
  font-size: 1.25rem;
}

.drawer-description,
.self-hint {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.active-control {
  margin: 0;
  padding: 0;
  border: 0;
}

.role-select {
  width: 100%;
  height: 2.5rem;
  padding: 0 0.75rem;
  color: var(--gateway-text);
  background: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.role-select:focus {
  border-color: var(--el-color-primary);
  outline: 0;
}

.role-select:disabled {
  cursor: not-allowed;
  background: var(--el-disabled-bg-color);
}
</style>

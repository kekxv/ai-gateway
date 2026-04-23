<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('user.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Card Grid -->
    <div v-if="loading" class="text-center py-12">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    </div>
    <div v-else-if="users.length === 0" class="text-center py-12 text-gray-500">
      {{ t('common.noData') }}
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <div
        v-for="user in paginatedUsers"
        :key="user.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-3 gap-2">
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold text-gray-800 truncate">{{ user.email }}</h3>
            <p class="text-xs text-gray-400 mt-1">{{ formatDate(user.createdAt) }}</p>
          </div>
          <el-tag :type="user.role === 'ADMIN' ? 'danger' : 'info'" size="small" class="shrink-0">
            {{ user.role }}
          </el-tag>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="bg-amber-50 rounded-lg p-2 text-center">
            <div class="text-xs text-amber-500">{{ t('user.balance') }}</div>
            <div class="text-sm font-semibold text-amber-700">{{ formatCurrency(user.balance) }}</div>
          </div>
          <div class="rounded-lg p-2 text-center" :class="user.disabled ? 'bg-red-50' : 'bg-green-50'">
            <div class="text-xs" :class="user.disabled ? 'text-red-500' : 'text-green-500'">{{ t('common.status') }}</div>
            <div class="text-sm font-semibold" :class="user.disabled ? 'text-red-700' : 'text-green-700'">
              {{ user.disabled ? t('common.disabled') : t('common.enabled') }}
            </div>
          </div>
        </div>

        <!-- TOTP -->
        <div v-if="user.totpEnabled" class="mb-3">
          <el-tag type="success" size="small" effect="plain">
            <el-icon class="mr-1"><Key /></el-icon>
            TOTP {{ t('common.enabled') }}
          </el-tag>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap gap-2 pt-3 border-t border-gray-100">
          <el-button size="small" @click="openEditDialog(user)">
            <el-icon class="mr-1"><Edit /></el-icon>
            {{ t('common.edit') }}
          </el-button>
          <el-button size="small" type="warning" @click="adjustBalance(user)">
            <el-icon class="mr-1"><Wallet /></el-icon>
            {{ t('user.adjustBalance') }}
          </el-button>
          <el-button size="small" :type="user.disabled ? 'success' : 'danger'" @click="toggleDisabled(user)">
            {{ user.disabled ? '启用' : '禁用' }}
          </el-button>
          <el-button size="small" type="danger" @click="deleteUser(user)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="users.length > 0" class="flex justify-center mt-6">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[12, 24, 48, 96]"
        layout="total, sizes, prev, pager, next"
        :size="isMobile ? 'small' : 'default'"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('user.editTitle') : t('user.createTitle')" :width="isMobile ? '90%' : '500px'">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" label-position="top">
        <el-form-item :label="t('user.email')" prop="email">
          <el-input v-model="form.email" :disabled="isEdit" />
        </el-form-item>
        <el-form-item v-if="!isEdit" :label="t('login.password')" prop="password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('user.role')" prop="role">
          <el-select v-model="form.role" class="w-full">
            <el-option label="USER" value="USER" />
            <el-option label="ADMIN" value="ADMIN" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('user.balance')" prop="balance">
          <el-input-number v-model="form.balance" :precision="4" :step="1" class="w-full" />
        </el-form-item>
        <el-form-item :label="t('user.validUntil')" prop="valid_until">
          <el-date-picker v-model="form.valid_until" type="datetime" class="w-full" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Balance Adjust Dialog -->
    <el-dialog v-model="balanceDialogVisible" :title="t('user.adjustBalance')" :width="isMobile ? '90%' : '400px'">
      <el-form :model="balanceForm" label-width="100px" label-position="top">
        <el-form-item label="Current">
          {{ formatCurrency(selectedUser?.balance || 0) }}
        </el-form-item>
        <el-form-item label="Amount">
          <el-input-number v-model="balanceForm.amount" :precision="4" :step="1" class="w-full" />
        </el-form-item>
        <el-form-item label="Action">
          <el-radio-group v-model="balanceForm.action">
            <el-radio value="add">Add</el-radio>
            <el-radio value="subtract">Subtract</el-radio>
            <el-radio value="set">Set</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="balanceDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitBalance" :loading="submitting">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from '@/plugins/element-plus-services'
import { Loading, Edit, Wallet, Delete, Key } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { userApi } from '@/api/auth'
import type { User } from '@/types/user'
import dayjs from 'dayjs'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const users = ref<User[]>([])
const dialogVisible = ref(false)
const balanceDialogVisible = ref(false)
const isEdit = ref(false)
const selectedUser = ref<User | null>(null)
const formRef = ref<FormInstance>()
const isMobile = ref(false)

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  fetchUsers()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0
})

// Frontend pagination slicing
const paginatedUsers = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return users.value.slice(start, end)
})

const form = reactive({
  email: '',
  password: '',
  role: 'USER',
  balance: 0,
  valid_until: null as Date | null
})

const balanceForm = reactive({
  amount: 0,
  action: 'add'
})

const rules: FormRules = {
  email: [
    { required: true, message: t('validation.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('validation.emailInvalid'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('validation.passwordRequired'), trigger: 'blur' },
    { min: 8, message: t('validation.passwordMin'), trigger: 'blur' }
  ],
  role: [{ required: true, message: 'Role is required', trigger: 'change' }]
}

const formatCurrency = (num: number) => '$' + num.toFixed(4)
const formatDate = (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm')

const fetchUsers = async () => {
  loading.value = true
  try {
    const response = await userApi.list()
    users.value = response.data || []
    pagination.total = users.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.email = ''
  form.password = ''
  form.role = 'USER'
  form.balance = 0
  form.valid_until = null
}

const openCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (user: User) => {
  isEdit.value = true
  selectedUser.value = user
  form.email = user.email
  form.role = user.role
  form.balance = user.balance
  form.valid_until = user.validUntil ? new Date(user.validUntil) : null
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    if (isEdit.value && selectedUser.value) {
      await userApi.update(selectedUser.value.id, {
        role: form.role as 'ADMIN' | 'USER',
        balance: form.balance,
        validUntil: form.valid_until ? dayjs(form.valid_until).toISOString() : undefined
      })
    } else {
      await userApi.create({
        email: form.email,
        password: form.password,
        role: form.role as 'ADMIN' | 'USER',
        balance: form.balance,
        validUntil: form.valid_until ? dayjs(form.valid_until).toISOString() : undefined
      })
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchUsers()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const adjustBalance = (user: User) => {
  selectedUser.value = user
  balanceForm.amount = 0
  balanceForm.action = 'add'
  balanceDialogVisible.value = true
}

const submitBalance = async () => {
  if (!selectedUser.value) return
  submitting.value = true
  try {
    await userApi.updateBalance(selectedUser.value.id, {
      amount: balanceForm.amount,
      action: balanceForm.action
    })
    ElMessage.success(t('common.success'))
    balanceDialogVisible.value = false
    fetchUsers()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const toggleDisabled = async (user: User) => {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to ${user.disabled ? 'enable' : 'disable'} this user?`,
      t('common.confirm'),
      { type: 'warning' }
    )
    await userApi.toggleDisabled(user.id)
    ElMessage.success(t('common.success'))
    fetchUsers()
  } catch {
    // User cancelled
  }
}

const deleteUser = async (user: User) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await userApi.delete(user.id)
    ElMessage.success(t('common.success'))
    fetchUsers()
  } catch {
    // User cancelled
  }
}
</script>

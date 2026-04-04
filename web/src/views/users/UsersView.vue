<template>
  <div class="space-y-6">
      <!-- Header -->
      <div class="flex justify-between items-center">
        <h2 class="text-xl font-semibold">{{ t('user.title') }}</h2>
        <el-button type="primary" @click="openCreateDialog">
          {{ t('common.create') }}
        </el-button>
      </div>

      <!-- Table -->
      <el-card>
        <el-table :data="paginatedUsers" stripe v-loading="loading">
          <el-table-column prop="email" :label="t('user.email')" />
          <el-table-column prop="role" :label="t('user.role')" width="100">
            <template #default="{ row }">
              <el-tag :type="row.role === 'ADMIN' ? 'danger' : 'info'">
                {{ row.role }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="balance" :label="t('user.balance')" width="150">
            <template #default="{ row }">
              {{ formatCurrency(row.balance) }}
            </template>
          </el-table-column>
          <el-table-column prop="disabled" :label="t('user.disabled')" width="100">
            <template #default="{ row }">
              <el-tag :type="row.disabled ? 'danger' : 'success'">
                {{ row.disabled ? t('common.yes') : t('common.no') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="totp_enabled" :label="t('user.totpEnabled')" width="120">
            <template #default="{ row }">
              <el-tag :type="row.totp_enabled ? 'success' : 'info'">
                {{ row.totp_enabled ? t('common.yes') : t('common.no') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" :label="t('user.createdAt')" width="180">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column :label="t('common.actions')" width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditDialog(row)">{{ t('common.edit') }}</el-button>
              <el-button size="small" type="warning" @click="adjustBalance(row)">{{ t('user.adjustBalance') }}</el-button>
              <el-button size="small" :type="row.disabled ? 'success' : 'danger'" @click="toggleDisabled(row)">
                {{ row.disabled ? '启用' : '禁用' }}
              </el-button>
              <el-button size="small" type="danger" @click="deleteUser(row)">{{ t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Pagination -->
        <div class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :total="pagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
        />
        </div>
      </el-card>

      <!-- Create/Edit Dialog -->
      <el-dialog v-model="dialogVisible" :title="isEdit ? t('user.editTitle') : t('user.createTitle')" width="500px">
        <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
          <el-form-item :label="t('user.email')" prop="email">
            <el-input v-model="form.email" :disabled="isEdit" />
          </el-form-item>
          <el-form-item v-if="!isEdit" :label="t('login.password')" prop="password">
            <el-input v-model="form.password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('user.role')" prop="role">
            <el-select v-model="form.role">
              <el-option label="USER" value="USER" />
              <el-option label="ADMIN" value="ADMIN" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('user.balance')" prop="balance">
            <el-input-number v-model="form.balance" :precision="4" :step="1" />
          </el-form-item>
          <el-form-item :label="t('user.validUntil')" prop="valid_until">
            <el-date-picker v-model="form.valid_until" type="datetime" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
        </template>
      </el-dialog>

      <!-- Balance Adjust Dialog -->
      <el-dialog v-model="balanceDialogVisible" :title="t('user.adjustBalance')" width="400px">
        <el-form :model="balanceForm" label-width="100px">
          <el-form-item label="Current">
            {{ formatCurrency(selectedUser?.balance || 0) }}
          </el-form-item>
          <el-form-item label="Amount">
            <el-input-number v-model="balanceForm.amount" :precision="4" :step="1" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
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

const pagination = reactive({
  page: 1,
  pageSize: 10,
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

onMounted(fetchUsers)
</script>
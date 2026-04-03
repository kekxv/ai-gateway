<template>
  <div class="min-h-screen bg-gray-100 flex items-center justify-center">
    <div class="text-center">
      <h1 class="text-6xl font-bold text-gray-300 mb-4">404</h1>
      <p class="text-xl text-gray-600 mb-8">Page Not Found</p>
      <el-button type="primary" @click="goHome">
        {{ t('common.back') || 'Back to Dashboard' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const { t } = useI18n()

const goHome = () => {
  router.push('/dashboard')
}
</script>
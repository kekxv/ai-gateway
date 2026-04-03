<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

onMounted(async () => {
  // Try to restore user session on app load
  if (authStore.token && !authStore.user) {
    await authStore.fetchCurrentUser()
  }
})
</script>
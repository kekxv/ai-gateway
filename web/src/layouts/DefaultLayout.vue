<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Sidebar - Fixed -->
    <aside class="fixed left-0 top-0 bottom-0 w-64 bg-gradient-to-b from-slate-800 via-slate-800 to-slate-900 text-white flex flex-col shadow-xl z-50">
      <!-- Logo -->
      <div class="p-5 border-b border-slate-700/50">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center shadow-lg">
            <svg class="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 class="text-xl font-bold tracking-tight">AI Gateway</h1>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 p-4 overflow-y-auto">
        <ul class="space-y-1">
          <li v-for="item in menuItems" :key="item.path">
            <router-link
              :to="item.path"
              class="flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200"
              :class="isActive(item.path)
                ? 'bg-gradient-to-r from-indigo-500/20 to-purple-500/20 text-white border-r-4 border-indigo-400'
                : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'"
            >
              <component :is="item.icon" class="w-5 h-5" />
              <span class="font-medium">{{ item.title }}</span>
            </router-link>
          </li>
        </ul>
      </nav>

      <!-- User Section -->
      <div class="p-4 border-t border-slate-700/50 bg-slate-800/50">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 bg-gradient-to-br from-indigo-400 to-purple-500 rounded-full flex items-center justify-center shadow-lg">
            <span class="text-white font-bold">{{ user?.email?.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium truncate">{{ user?.email }}</p>
            <p class="text-xs text-slate-400">
              <el-tag
                :type="user?.role === 'ADMIN' ? 'danger' : 'info'"
                size="small"
                effect="dark"
              >
                {{ user?.role }}
              </el-tag>
            </p>
          </div>
        </div>
        <button
          @click="logout"
          class="w-full px-4 py-2.5 text-sm bg-slate-700/50 hover:bg-slate-600 rounded-xl transition-all duration-200 flex items-center justify-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          {{ t('common.logout') || '退出登录' }}
        </button>
      </div>
    </aside>

    <!-- Main content - with left margin for sidebar -->
    <main class="ml-64 flex flex-col min-h-screen">
      <!-- Header -->
      <header class="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shadow-sm sticky top-0 z-40">
        <h2 class="text-xl font-semibold text-gray-800">{{ currentTitle }}</h2>
        <div class="flex items-center gap-4">
          <!-- Language Selector -->
          <div class="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5">
            <svg class="w-5 h-5 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="10" stroke-width="2"/>
              <path stroke-width="2" d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            <el-select v-model="locale" size="small" style="width: 90px;">
              <el-option label="中文" value="zh" />
              <el-option label="English" value="en" />
            </el-select>
          </div>
        </div>
      </header>

      <!-- Page content -->
      <div class="flex-1 p-6 overflow-auto bg-gray-50">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { locale, t } = useI18n()

const user = computed(() => authStore.user)

// Persist locale changes to localStorage
watch(locale, (newLocale) => {
  localStorage.setItem('locale', newLocale)
})

const menuItems = computed(() => {
  const items = [
    { path: '/dashboard', title: t('menu.dashboard'), icon: 'Dashboard' },
    { path: '/providers', title: t('menu.providers'), icon: 'Provider' },
    { path: '/channels', title: t('menu.channels'), icon: 'Channel' },
    { path: '/models', title: t('menu.models'), icon: 'Model' },
    { path: '/keys', title: t('menu.keys'), icon: 'Key' },
    { path: '/logs', title: t('menu.logs'), icon: 'Log' },
    { path: '/profile', title: t('menu.profile'), icon: 'Profile' }
  ]

  if (authStore.isAdmin) {
    items.splice(1, 0, { path: '/users', title: t('menu.users'), icon: 'User' })
  }

  return items
})

const currentTitle = computed(() => {
  const item = menuItems.value.find(i => i.path === route.path)
  return item?.title || ''
})

const isActive = (path: string) => {
  return route.path === path || route.path.startsWith(path + '/')
}

const logout = () => {
  authStore.logout()
  router.push('/login')
}
</script>
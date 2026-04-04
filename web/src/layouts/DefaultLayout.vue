<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Mobile Header (only on mobile) -->
    <header class="lg:hidden fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 z-50 shadow-sm">
      <button @click="sidebarOpen = true" class="p-2 rounded-lg hover:bg-gray-100">
        <svg class="w-6 h-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <h1 class="text-lg font-semibold text-gray-800">AI Gateway</h1>
      <div class="flex items-center gap-2">
        <el-select v-model="locale" size="small" style="width: 80px;">
          <el-option label="中文" value="zh" />
          <el-option label="English" value="en" />
        </el-select>
      </div>
    </header>

    <!-- Mobile Sidebar Overlay -->
    <div
      v-if="sidebarOpen"
      class="lg:hidden fixed inset-0 bg-black/50 z-40"
      @click="sidebarOpen = false"
    />

    <!-- Sidebar -->
    <aside
      class="fixed left-0 top-0 bottom-0 w-64 bg-gradient-to-b from-slate-800 via-slate-800 to-slate-900 text-white flex flex-col shadow-xl z-50 transition-transform duration-300"
      :class="isMobile ? (sidebarOpen ? 'translate-x-0' : '-translate-x-full') : 'translate-x-0'"
    >
      <!-- Logo -->
      <div class="p-5 border-b border-slate-700/50">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center shadow-lg">
              <svg class="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h1 class="text-xl font-bold tracking-tight">AI Gateway</h1>
          </div>
          <!-- Close button (mobile only) -->
          <button v-if="isMobile" @click="sidebarOpen = false" class="p-1 rounded-lg hover:bg-slate-700/50">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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
              @click="isMobile && (sidebarOpen = false)"
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

    <!-- Main content -->
    <main class="lg:ml-64 flex flex-col min-h-screen pt-14 lg:pt-0">
      <!-- Header (desktop only) -->
      <header class="hidden lg:flex h-16 bg-white border-b border-gray-200 items-center justify-between px-6 shadow-sm sticky top-0 z-40">
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
      <div class="flex-1 p-4 lg:p-6 overflow-auto bg-gray-50">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { locale, t } = useI18n()

const user = computed(() => authStore.user)
const sidebarOpen = ref(false)
const isMobile = ref(false)

// Check if mobile on mount and resize
const checkMobile = () => {
  isMobile.value = window.innerWidth < 1024
  if (!isMobile.value) {
    sidebarOpen.value = false
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

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
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  ElAside,
  ElButton,
  ElContainer,
  ElDrawer,
  ElHeader,
  ElIcon,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElText,
} from 'element-plus'
import 'element-plus/theme-chalk/el-aside.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-container.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-header.css'
import 'element-plus/theme-chalk/el-main.css'
import 'element-plus/theme-chalk/el-menu.css'
import 'element-plus/theme-chalk/el-menu-item.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-popper.css'
import 'element-plus/theme-chalk/el-text.css'
import 'element-plus/theme-chalk/el-tooltip.css'
import {
  Connection,
  DataAnalysis,
  Document,
  Key,
  Lock,
  Menu as MenuIcon,
  Operation,
  User,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'

interface NavigationItem {
  route: string
  label: string
  icon: typeof DataAnalysis
}

const navigation: NavigationItem[] = [
  { route: '/', label: '控制台概览', icon: DataAnalysis },
  { route: '/providers', label: '供应商管理', icon: Connection },
  { route: '/models', label: '模型管理', icon: Operation },
  { route: '/users', label: '用户管理', icon: User },
  { route: '/api-keys', label: '接口密钥', icon: Key },
  { route: '/request-logs', label: '请求日志', icon: Document },
  { route: '/security', label: '安全设置', icon: Lock },
]

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const viewportWidth = ref(typeof window === 'undefined' ? 1200 : window.innerWidth)
const drawerOpen = ref(false)
const isMobile = computed(() => viewportWidth.value < 768)
const isCollapsed = computed(() => viewportWidth.value < 1200)

function updateViewport(): void {
  viewportWidth.value = window.innerWidth
  if (!isMobile.value) drawerOpen.value = false
}

async function navigate(path: string): Promise<void> {
  drawerOpen.value = false
  await router.push(path)
}

async function logout(): Promise<void> {
  auth.logout()
  await router.replace({ name: 'login' })
}

onMounted(() => {
  window.addEventListener('resize', updateViewport, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
})
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <ElContainer class="admin-shell">
    <ElAside v-if="!isMobile" class="admin-sidebar" :width="isCollapsed ? '64px' : '232px'">
      <div class="brand" :class="{ 'brand--collapsed': isCollapsed }">
        <span class="brand__mark" aria-hidden="true">智</span>
        <span v-if="!isCollapsed" class="brand__name">AI 网关</span>
      </div>
      <ElMenu
        class="admin-menu"
        :default-active="route.path"
        :collapse="isCollapsed"
        :collapse-transition="false"
        @select="navigate"
      >
        <ElMenuItem v-for="item in navigation" :key="item.route" :index="item.route">
          <ElIcon><component :is="item.icon" /></ElIcon>
          <template #title>{{ item.label }}</template>
        </ElMenuItem>
      </ElMenu>
    </ElAside>

    <ElDrawer v-model="drawerOpen" direction="ltr" size="min(82vw, 19rem)" title="控制台导航">
      <ElMenu class="admin-menu admin-menu--drawer" :default-active="route.path" @select="navigate">
        <ElMenuItem v-for="item in navigation" :key="item.route" :index="item.route">
          <ElIcon><component :is="item.icon" /></ElIcon>
          <template #title>{{ item.label }}</template>
        </ElMenuItem>
      </ElMenu>
    </ElDrawer>

    <ElContainer class="admin-workspace">
      <ElHeader class="admin-header">
        <ElButton
          v-if="isMobile"
          class="mobile-menu-button"
          text
          aria-label="打开导航菜单"
          @click="drawerOpen = true"
        >
          <MenuIcon />
        </ElButton>
        <div class="header-actions">
          <ElText class="admin-email" truncated>{{ auth.user?.email }}</ElText>
          <ElButton text @click="navigate('/security')">安全设置</ElButton>
          <ElButton text type="danger" @click="logout">退出登录</ElButton>
        </div>
      </ElHeader>
      <ElMain id="main-content" class="admin-main" tabindex="-1">
        <RouterView />
      </ElMain>
    </ElContainer>
  </ElContainer>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
}

.admin-sidebar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 100vh;
  overflow: hidden;
  background: var(--gateway-panel);
  border-right: 1px solid var(--gateway-border);
  transition: width 180ms ease;
}

.brand {
  display: flex;
  height: 64px;
  gap: 0.75rem;
  align-items: center;
  padding: 0 1rem;
  border-bottom: 1px solid var(--gateway-border);
}

.brand--collapsed {
  justify-content: center;
  padding: 0;
}

.brand__mark {
  display: grid;
  width: 2rem;
  height: 2rem;
  flex: 0 0 auto;
  place-items: center;
  color: #fff;
  font-weight: 700;
  background: var(--gateway-brand);
  border-radius: 0.55rem;
}

.brand__name {
  overflow: hidden;
  font-weight: 700;
  white-space: nowrap;
}

.admin-menu {
  border-right: 0;
}

.admin-menu:not(.el-menu--collapse) {
  width: 100%;
}

.admin-menu--drawer {
  margin: 0 -1.25rem;
}

.admin-workspace {
  min-width: 0;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  background: rgb(255 255 255 / 92%);
  border-bottom: 1px solid var(--gateway-border);
  backdrop-filter: blur(10px);
}

.mobile-menu-button {
  margin-right: auto;
  font-size: 1.25rem;
}

.header-actions {
  display: flex;
  min-width: 0;
  gap: 0.35rem;
  align-items: center;
}

.admin-email {
  max-width: 16rem;
  margin-right: 0.5rem;
  color: var(--gateway-muted);
}

.admin-main {
  padding: 1.5rem;
}

@media (max-width: 767px) {
  .admin-header {
    padding: 0 0.75rem;
  }

  .admin-email {
    max-width: 7rem;
    margin-right: 0;
    font-size: 0.8rem;
  }

  .admin-main {
    padding: 1rem;
  }
}
</style>

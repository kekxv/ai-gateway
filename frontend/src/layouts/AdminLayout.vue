<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
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
  Close,
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
let pendingPageHeadingPath: string | undefined

function updateViewport(): void {
  viewportWidth.value = window.innerWidth
  if (!isMobile.value) drawerOpen.value = false
}

function handleNavigationKeydown(event: KeyboardEvent): void {
  if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return
  const items = Array.from(
    document.querySelectorAll<HTMLElement>('.admin-sidebar [data-navigation-route]'),
  )
  if (items.length === 0) return
  const focusedIndex = items.indexOf(document.activeElement as HTMLElement)
  if (event.key === 'Enter' || event.key === ' ') {
    if (focusedIndex === -1) return
    const path = items[focusedIndex]?.dataset.navigationRoute
    if (path === undefined) return
    event.preventDefault()
    event.stopPropagation()
    void navigate(path)
    return
  }

  event.preventDefault()
  event.stopPropagation()
  const activeIndex = items.findIndex((item) => item.classList.contains('is-active'))
  const startingIndex = focusedIndex === -1 ? activeIndex : focusedIndex
  const direction = event.key === 'ArrowDown' ? 1 : -1
  const nextIndex =
    focusedIndex === -1
      ? Math.max(startingIndex, 0)
      : (startingIndex + direction + items.length) % items.length
  items[nextIndex]?.focus()
}

function focusPendingPageHeading(): void {
  if (pendingPageHeadingPath === undefined || route.path !== pendingPageHeadingPath) return
  const heading = document.querySelector<HTMLElement>('.page-header h1')
  if (heading === null) return
  const expectedTitle = route.meta.title
  if (typeof expectedTitle === 'string' && heading.textContent.trim() !== expectedTitle) return
  heading.focus()
  pendingPageHeadingPath = undefined
}

async function navigate(path: string): Promise<void> {
  drawerOpen.value = false
  pendingPageHeadingPath = path
  await router.push(path)
  await nextTick()
  focusPendingPageHeading()
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
      <nav aria-label="控制台导航" tabindex="0" @keydown="handleNavigationKeydown">
        <ElMenu
          class="admin-menu"
          :default-active="route.path"
          :collapse="isCollapsed"
          :collapse-transition="false"
          @select="navigate"
        >
          <ElMenuItem
            v-for="item in navigation"
            :key="item.route"
            :index="item.route"
            :data-navigation-route="item.route"
          >
            <ElIcon><component :is="item.icon" /></ElIcon>
            <template #title>{{ item.label }}</template>
          </ElMenuItem>
        </ElMenu>
      </nav>
    </ElAside>

    <ElDrawer
      v-model="drawerOpen"
      direction="ltr"
      size="min(82vw, 19rem)"
      :show-close="false"
    >
      <template #header="{ titleId, titleClass }">
        <h2 :id="titleId" :class="[titleClass, 'drawer-title']">控制台导航</h2>
        <ElButton text aria-label="关闭导航菜单" @click="drawerOpen = false">
          <Close />
        </ElButton>
      </template>
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
      <ElMain id="main-content" class="admin-main" tabindex="0">
        <RouterView v-slot="{ Component }">
          <Transition name="page-fade" mode="out-in" @after-enter="focusPendingPageHeading">
            <KeepAlive :max="7">
              <component :is="Component" />
            </KeepAlive>
          </Transition>
        </RouterView>
      </ElMain>
    </ElContainer>
  </ElContainer>
</template>

<style scoped>
.admin-shell {
  height: 100vh;
  overflow: hidden;
}

.admin-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  background: var(--gateway-panel);
  border-right: 1px solid var(--gateway-border);
  transition: width 180ms ease;
}

.brand {
  display: flex;
  height: 64px;
  flex-shrink: 0;
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
  background: linear-gradient(135deg, var(--gateway-brand) 0%, #3b82f6 100%);
  border-radius: 0.55rem;
  box-shadow: 0 2px 8px rgb(37 99 235 / 25%);
}

.brand__name {
  overflow: hidden;
  font-weight: 700;
  white-space: nowrap;
}

.admin-menu {
  flex: 1;
  border-right: 0;
}

.admin-menu:not(.el-menu--collapse) {
  width: 100%;
}

.admin-menu--drawer {
  margin: 0 -1.25rem;
}

.drawer-title {
  margin: 0;
  color: var(--gateway-text);
  font-size: 1.125rem;
  font-weight: 700;
}

.admin-workspace {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.admin-header {
  display: flex;
  flex-shrink: 0;
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
  flex: 1;
  padding: 1.5rem;
  overflow-y: auto;
  background: var(--gateway-bg);
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

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 150ms ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}
</style>

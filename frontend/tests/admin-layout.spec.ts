import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'

const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin' as const,
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
}

const mountedWrappers: VueWrapper[] = []

function setViewport(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  window.dispatchEvent(new Event('resize'))
}

async function mountShell(width = 1200): Promise<{
  auth: ReturnType<typeof useAuthStore>
  router: Router
  wrapper: VueWrapper
}> {
  setViewport(width)
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  vi.spyOn(auth, 'restore').mockImplementation(() => {
    auth.user = adminUser
    auth.ready = true
    return Promise.resolve()
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  }) as unknown as VueWrapper
  mountedWrappers.push(wrapper)
  await flushPromises()
  return { auth, router, wrapper }
}

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
})

beforeEach(() => {
  setViewport(1200)
})

describe('管理控制台外壳', () => {
  it('在 768 与 1200 像素边界切换完整侧栏、折叠侧栏和移动抽屉', async () => {
    const { wrapper } = await mountShell(1200)

    expect(wrapper.get('.admin-sidebar').attributes('style')).toContain('width: 232px')
    expect(wrapper.find('.admin-menu.el-menu--collapse').exists()).toBe(false)

    setViewport(1199)
    await flushPromises()
    expect(wrapper.get('.admin-sidebar').attributes('style')).toContain('width: 64px')
    expect(wrapper.find('.admin-menu.el-menu--collapse').exists()).toBe(true)

    setViewport(768)
    await flushPromises()
    expect(wrapper.find('.admin-sidebar').exists()).toBe(true)
    expect(wrapper.find('[aria-label="打开导航菜单"]').exists()).toBe(false)

    setViewport(767)
    await flushPromises()
    expect(wrapper.find('.admin-sidebar').exists()).toBe(false)
    expect(wrapper.get('[aria-label="打开导航菜单"]').isVisible()).toBe(true)
  })

  it('通过带中文关闭标签的移动抽屉完成导航并自动关闭', async () => {
    const { router, wrapper } = await mountShell(767)
    await wrapper.get('[aria-label="打开导航菜单"]').trigger('click')
    await flushPromises()

    const closeButton = document.querySelector<HTMLButtonElement>(
      '[aria-label="关闭导航菜单"]',
    )
    expect(closeButton).not.toBeNull()
    const layout = wrapper.getComponent(AdminLayout)
    closeButton?.click()
    await flushPromises()
    expect((layout.vm as unknown as { drawerOpen: boolean }).drawerOpen).toBe(false)

    await wrapper.get('[aria-label="打开导航菜单"]').trigger('click')
    await flushPromises()
    const providers = [...document.querySelectorAll<HTMLElement>('.el-drawer .el-menu-item')].find(
      (item) => item.textContent.includes('供应商管理'),
    )
    if (providers === undefined) throw new Error('未找到移动抽屉中的供应商管理入口')
    providers.click()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('providers')
    expect((layout.vm as unknown as { drawerOpen: boolean }).drawerOpen).toBe(false)
  })

  it('提供跳转主内容、可聚焦主区域和路由页面内容', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    const main = wrapper.get('main#main-content')
    expect(main.attributes('tabindex')).toBe('-1')
    expect(main.text()).toContain('控制台概览')
    expect(main.text()).toContain('功能正在建设中。')
  })

  it('支持页头安全设置导航和退出登录', async () => {
    const { auth, router, wrapper } = await mountShell()
    const headerButtons = wrapper.findAll('.admin-header button')
    const security = headerButtons.find((button) => button.text().includes('安全设置'))
    expect(security).toBeDefined()
    await security?.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('security')

    const logout = vi.spyOn(auth, 'logout')
    const logoutButton = wrapper
      .findAll('.admin-header button')
      .find((button) => button.text().includes('退出登录'))
    expect(logoutButton).toBeDefined()
    await logoutButton?.trigger('click')
    await flushPromises()

    expect(logout).toHaveBeenCalledTimes(1)
    expect(auth.authenticated).toBe(false)
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('login')
    })
  })
})

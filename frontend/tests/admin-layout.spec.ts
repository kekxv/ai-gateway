import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import type { CurrentUser } from '@/api/types'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/dashboard', () => ({
  getDashboardSummary: () => Promise.resolve({
    users_total: 0,
    active_api_keys: 0,
    providers: { total: 0, enabled: 0 },
    models: { total: 0, enabled: 0 },
    routes: { total: 0, enabled: 0, unavailable: 0 },
    requests_24h: 0,
    failed_requests_24h: 0,
    prompt_tokens_24h: 0,
    completion_tokens_24h: 0,
    cache_read_tokens_24h: 0,
    cache_write_tokens_24h: 0,
    total_tokens_24h: 0,
    cost_24h: '0',
    cost_amount_24h: '0',
    gross_profit_24h: '0',
    average_latency_ms_24h: null,
    total_requests: 0,
    total_cost: '0',
    total_cost_amount: '0',
    total_gross_profit: '0',
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    daily_usage: [],
    top_models: [],
    provider_stats: [],
  }),
  getUserDashboardSummary: () => Promise.resolve({
    balance: '0',
    total_spent: '0',
    active_api_keys: 0,
    requests_24h: 0,
    failed_requests_24h: 0,
    prompt_tokens_24h: 0,
    completion_tokens_24h: 0,
    cache_read_tokens_24h: 0,
    cache_write_tokens_24h: 0,
    total_tokens_24h: 0,
    cost_24h: '0',
    average_latency_ms_24h: null,
    total_requests: 0,
    total_cost: '0',
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    daily_usage: [],
  }),
}))

vi.mock('@/api/providers', () => ({
  listProviders: () => Promise.resolve([]),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  deleteProvider: vi.fn(),
  syncProviderModels: vi.fn(),
}))

vi.mock('@/api/settings', () => ({
  getRegistrationSetting: () => Promise.resolve({ enabled: true }),
  updateRegistrationSetting: vi.fn(),
}))

const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin' as const,
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
}

const regularUser = {
  ...adminUser,
  id: 2,
  email: 'member@example.com',
  role: 'user' as const,
}

const mountedWrappers: VueWrapper[] = []

function setViewport(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  window.dispatchEvent(new Event('resize'))
}

async function mountShell(
  width = 1200,
  warnings?: string[],
  currentUser: CurrentUser = adminUser,
): Promise<{
  auth: ReturnType<typeof useAuthStore>
  router: Router
  wrapper: VueWrapper
}> {
  setViewport(width)
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  vi.spyOn(auth, 'restore').mockImplementation(() => {
    auth.user = currentUser
    auth.ready = true
    return Promise.resolve()
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      ...(warnings === undefined
        ? {}
        : {
            stubs: { transition: false },
            config: {
              warnHandler(message: string) {
                warnings.push(message)
              },
            },
          }),
    },
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
  it('普通用户看到概览、自助模型、请求日志、接口密钥、安全设置导航和账户入口', async () => {
    const { wrapper } = await mountShell(1200, undefined, regularUser)
    const navigationText = wrapper.get('nav[aria-label="控制台导航"]').text()
    const navigationLabels = wrapper
      .findAll('nav[aria-label="控制台导航"] .el-menu-item')
      .map((item) => item.text())

    expect(navigationLabels.slice(0, 2)).toEqual(['控制台概览', '账单统计'])

    expect(navigationText).toContain('可用模型')
    expect(navigationText).toContain('接口密钥')
    expect(navigationText).toContain('安全设置')
    expect(navigationText).toContain('控制台概览')
    expect(navigationText).not.toContain('供应商管理')
    expect(navigationText).not.toContain('模型管理')
    expect(navigationText).not.toContain('用户管理')
    expect(navigationText).toContain('请求日志')
    expect(navigationText).toContain('账单统计')
    expect(wrapper.get('.admin-email').text()).toBe(regularUser.email)
    expect(wrapper.get('.admin-header').text()).toContain('退出登录')
  })

  it('通过真实过渡渲染缓存页面时不产生 Fragment 根节点警告', async () => {
    const warnings: string[] = []
    const { router, wrapper } = await mountShell(1200, warnings)

    await router.push('/providers')
    await flushPromises()

    await vi.waitFor(() => {
      expect(wrapper.get('.route-page').text()).toContain('供应商列表')
      expect(
        warnings.some((message) =>
          message.includes('Component inside <Transition> renders non-element root node'),
        ),
      ).toBe(false)
    })
  })

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
    const mobileNavigationLabels = [...document.querySelectorAll<HTMLElement>('.el-drawer .el-menu-item')]
      .map((item) => item.textContent.trim())
    expect(mobileNavigationLabels.slice(0, 2)).toEqual(['控制台概览', '账单统计'])

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

    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('providers')
    })
    expect((layout.vm as unknown as { drawerOpen: boolean }).drawerOpen).toBe(false)
    expect(wrapper.get('main#main-content').text()).toContain('供应商列表')
  })

  it('提供跳转主内容、可聚焦主区域和路由页面内容', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    const main = wrapper.get('main#main-content')
    expect(main.attributes('tabindex')).toBe('0')
    expect(main.text()).toContain('控制台概览')
    expect(main.text()).toContain('查看网关运营数据、计费概览与请求趋势')
  })

  it('通过侧栏键盘导航后把焦点移动到新页面标题', async () => {
    const { router, wrapper } = await mountShell()
    const navigation = wrapper.get('nav[aria-label="控制台导航"]')
    const providerItem = wrapper.get('[data-navigation-route="/providers"]')
    ;(providerItem.element as HTMLElement).focus()

    await navigation.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('providers')
      expect(wrapper.get('.page-header h1').text()).toBe('供应商管理')
      expect(document.activeElement).toBe(wrapper.get('.page-header h1').element)
    })
  })

  it('支持页头安全设置导航和退出登录', async () => {
    const { auth, router, wrapper } = await mountShell()
    const headerButtons = wrapper.findAll('.admin-header button')
    const security = headerButtons.find((button) => button.text().includes('安全设置'))
    expect(security).toBeDefined()
    await security?.trigger('click')
    await flushPromises()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('security')
    })

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

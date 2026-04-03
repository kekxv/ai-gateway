import { vi, describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ElementPlus from 'element-plus'
import { createRouter, createWebHashHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import zhLocale from '@/../public/locales/zh/common.json'
import enLocale from '@/../public/locales/en/common.json'

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    user: { email: 'test@example.com', role: 'USER' },
    isAdmin: false,
    logout: vi.fn()
  }))
}))

const i18n = createI18n({
  legacy: false,
  locale: 'zh',
  messages: {
    zh: zhLocale,
    en: enLocale
  }
})

// Create a simple router for testing
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/dashboard', name: 'Dashboard', component: { template: '<div>Dashboard</div>' } },
    { path: '/providers', name: 'Providers', component: { template: '<div>Providers</div>' } },
    { path: '/channels', name: 'Channels', component: { template: '<div>Channels</div>' } },
    { path: '/models', name: 'Models', component: { template: '<div>Models</div>' } },
    { path: '/keys', name: 'Keys', component: { template: '<div>Keys</div>' } },
    { path: '/logs', name: 'Logs', component: { template: '<div>Logs</div>' } },
    { path: '/profile', name: 'Profile', component: { template: '<div>Profile</div>' } }
  ]
})

describe('DefaultLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render sidebar', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    expect(wrapper.find('aside').exists()).toBe(true)
  })

  it('should render main content area', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    expect(wrapper.find('main').exists()).toBe(true)
    // DefaultLayout uses router-view, not slot
    expect(wrapper.find('.flex-1.p-6').exists()).toBe(true)
  })

  it('should show user email in sidebar', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    expect(wrapper.text()).toContain('test@example.com')
  })

  it('should show user role', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    expect(wrapper.text()).toContain('USER')
  })

  it('should show logout button', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    const logoutButton = wrapper.findAll('button').find(b => b.text().includes('退出'))
    expect(logoutButton?.exists()).toBe(true)
  })

  it('should render menu items', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    // Should have navigation items with text
    const sidebar = wrapper.find('aside')
    expect(sidebar.text()).toContain('仪表板')
    expect(sidebar.text()).toContain('提供商管理')
  })

  it('should show language selector', async () => {
    router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DefaultLayout, {
      global: {
        plugins: [i18n, ElementPlus, router]
      },
      slots: {
        default: '<div>Content</div>'
      }
    })

    // Element Plus uses el-select component, not native select
    const select = wrapper.findComponent({ name: 'ElSelect' })
    expect(select.exists()).toBe(true)
    // Check for options via ElOption components
    const options = wrapper.findAllComponents({ name: 'ElOption' })
    expect(options.length).toBeGreaterThanOrEqual(2)
  })
})
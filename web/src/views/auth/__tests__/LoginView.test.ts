import { vi, describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ElementPlus from 'element-plus'
import { createRouter, createWebHashHistory } from 'vue-router'
import LoginView from '@/views/auth/LoginView.vue'
import zhLocale from '@/../public/locales/zh/common.json'
import enLocale from '@/../public/locales/en/common.json'

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    token: null,
    user: null,
    isAuthenticated: false,
    isAdmin: false,
    login: vi.fn(),
    logout: vi.fn(),
    fetchCurrentUser: vi.fn()
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
    { path: '/login', name: 'Login', component: { template: '<div>Login</div>' } },
    { path: '/dashboard', name: 'Dashboard', component: { template: '<div>Dashboard</div>' } }
  ]
})

describe('LoginView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render login form', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    // New layout: h1 is brand title "AI Gateway", h2 is login card title
    expect(wrapper.find('.brand-title').text()).toContain('AI Gateway')
    expect(wrapper.find('.card-header h2').text()).toContain('AI Gateway 登录')
    expect(wrapper.find('.login-form').exists()).toBe(true)
  })

  it('should show username field with placeholder', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThanOrEqual(2) // username and password
  })

  it('should show password field', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    const passwordInput = wrapper.find('input[type="password"]')
    expect(passwordInput.exists()).toBe(true)
  })

  it('should show login button', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    const loginButton = wrapper.find('button')
    expect(loginButton.exists()).toBe(true)
    expect(loginButton.text()).toContain('登录')
  })

  it('should show TOTP field', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    // TOTP field should be visible (showTotp is true by default)
    const totpInputs = wrapper.findAll('input').filter(i => i.attributes('maxlength') === '6')
    expect(totpInputs.length).toBeGreaterThan(0)
  })

  it('should show remember me checkbox', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    const checkbox = wrapper.findComponent({ name: 'ElCheckbox' })
    expect(checkbox.exists()).toBe(true)
  })

  it('should accept non-email username like "root"', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    // Fill in non-email format username
    const textInput = wrapper.find('input[type="text"]')
    await textInput.setValue('root')
    await textInput.trigger('blur')

    // Should not have validation error for email format
    // (previously would show "请输入有效的邮箱地址")
    const formItem = wrapper.find('.el-form-item__error')
    expect(formItem.exists() ? formItem.text() : '').not.toContain('邮箱')
  })

  it('should have brand section with features', async () => {
    router.push('/login')
    await router.isReady()

    const wrapper = mount(LoginView, {
      global: {
        plugins: [i18n, ElementPlus, router]
      }
    })

    expect(wrapper.find('.brand-section').exists()).toBe(true)
    expect(wrapper.find('.brand-features').exists()).toBe(true)
    expect(wrapper.findAll('.feature-item').length).toBe(3)
  })
})
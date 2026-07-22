import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'

describe('应用入口', () => {
  it('将页面交给路由渲染', () => {
    const wrapper = shallowMount(App)

    expect(wrapper.find('router-view-stub').exists()).toBe(true)
    wrapper.unmount()
  })
})

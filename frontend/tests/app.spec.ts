import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'

describe('application scaffold', () => {
  it('mounts a runnable Chinese placeholder before routing is installed', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('AI Gateway 管理控制台')
    expect(wrapper.text()).toContain('控制台界面正在建设中')
    expect(wrapper.find('[data-testid="console-placeholder"]').exists()).toBe(true)

    wrapper.unmount()
  })
})

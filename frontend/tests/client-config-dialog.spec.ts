import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ClientConfigDialog from '@/components/api-keys/ClientConfigDialog.vue'

function mountDialog() {
  return mount(ClientConfigDialog, {
    props: { modelValue: true, baseUrl: 'https://gateway.example' },
    attachTo: document.body,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('客户端配置对话框', () => {
  it('在验证接口密钥前提示先加载模型', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.get('[data-test="client-config-models"]').text()).toContain('请先验证并加载模型')
  })

  it('先验证接口密钥，再为 Claude 的各模型角色分别选择可用模型', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [
        { id: 'claude-primary' },
        { id: 'claude-opus' },
        { id: 'claude-sonnet' },
        { id: 'claude-haiku' },
        { id: 'claude-subagent' },
      ],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()

    const keyInput = wrapper.get('[data-test="client-config-key"]').element
    const modelArea = wrapper.get('[data-test="client-config-models"]').element
    expect(keyInput.compareDocumentPosition(modelArea) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-claude-primary"]').setValue('claude-primary')
    await wrapper.get('[data-test="client-config-claude-opus"]').setValue('claude-opus')
    await wrapper.get('[data-test="client-config-claude-sonnet"]').setValue('claude-sonnet')
    await wrapper.get('[data-test="client-config-claude-haiku"]').setValue('claude-haiku')
    await wrapper.get('[data-test="client-config-claude-subagent"]').setValue('claude-subagent')

    expect(JSON.parse(wrapper.get('[data-test="client-config-preview"]').text())).toMatchObject({
      env: {
        ANTHROPIC_MODEL: 'claude-primary',
        ANTHROPIC_DEFAULT_OPUS_MODEL: 'claude-opus',
        ANTHROPIC_DEFAULT_SONNET_MODEL: 'claude-sonnet',
        ANTHROPIC_DEFAULT_HAIKU_MODEL: 'claude-haiku',
        CLAUDE_CODE_SUBAGENT_MODEL: 'claude-subagent',
      },
    })
  })

  it('为 Codex 的各个角色选择独立的可用模型', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [
        { id: 'codex-primary' },
        { id: 'codex-review' },
        { id: 'codex-subagent' },
      ],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-codex"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith('https://gateway.example/v1/models', {
      headers: { Authorization: 'Bearer sk-gw-real-secret' },
    })
    await wrapper.get('[data-test="client-config-codex-primary"]').setValue('codex-primary')
    await wrapper.get('[data-test="client-config-codex-review"]').setValue('codex-review')
    await wrapper.get('[data-test="client-config-codex-subagent"]').setValue('codex-subagent')

    expect(wrapper.get('[data-test="client-config-preview"]').text()).toContain(
      'model = "codex-primary"',
    )
    expect(wrapper.get('[data-test="client-config-preview"]').text()).toContain(
      'review_model = "codex-review"',
    )
    expect(wrapper.get('[data-test="client-config-preview"]').text()).toContain(
      'default_subagent_model = "codex-subagent"',
    )
    expect(wrapper.get('[data-test="client-config-location"]').text()).toContain(
      '~/.codex/config.toml',
    )
  })

  it('为 OpenCode 的默认、规划、构建和审查角色选择独立模型', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [
        { id: 'opencode-primary' },
        { id: 'opencode-plan' },
        { id: 'opencode-build' },
        { id: 'opencode-review' },
      ],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-opencode"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-opencode-primary"]').setValue('opencode-primary')
    await wrapper.get('[data-test="client-config-opencode-plan"]').setValue('opencode-plan')
    await wrapper.get('[data-test="client-config-opencode-build"]').setValue('opencode-build')
    await wrapper.get('[data-test="client-config-opencode-review"]').setValue('opencode-review')

    expect(JSON.parse(wrapper.get('[data-test="client-config-preview"]').text())).toMatchObject({
      model: 'gateway/opencode-primary',
      agent: {
        plan: { model: 'gateway/opencode-plan' },
        build: { model: 'gateway/opencode-build' },
        review: { model: 'gateway/opencode-review' },
      },
    })
  })

  it('为 Pi 选择多个可切换模型', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [{ id: 'pi-fast' }, { id: 'pi-deep' }],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-pi"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-pi-models"]').setValue(['pi-fast', 'pi-deep'])

    expect(JSON.parse(wrapper.get('[data-test="client-config-preview"]').text())).toMatchObject({
      providers: {
        gateway: {
          api: 'openai-completions',
          models: [
            { id: 'pi-fast', name: 'pi-fast' },
            { id: 'pi-deep', name: 'pi-deep' },
          ],
        },
      },
    })
  })

  it('允许 Pi 选择 OpenAI Responses API', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [{ id: 'pi-responses' }],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-pi"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-pi-models"]').setValue(['pi-responses'])
    await wrapper.get('[data-test="client-config-pi-api"]').setValue('openai-responses')

    expect(JSON.parse(wrapper.get('[data-test="client-config-preview"]').text())).toMatchObject({
      providers: { gateway: { api: 'openai-responses' } },
    })
  })

  it('使用 Claude 认证头加载模型', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [{ id: 'claude-key-scoped' }],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledWith('https://gateway.example/v1/models', {
      headers: {
        'anthropic-version': '2023-06-01',
        'x-api-key': 'sk-gw-real-secret',
      },
    })
  })

  it('下载 Pi 的 models.json，并在关闭时清除输入密钥', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [{ id: 'pi-key-scoped' }],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const createObjectUrl = vi.fn(() => 'blob:client-config')
    const revokeObjectUrl = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-pi"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-pi-models"]').setValue(['pi-key-scoped'])
    await wrapper.get('[data-test="client-config-download"]').trigger('click')
    await flushPromises()

    expect(createObjectUrl).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(document.querySelector('a[download="models.json"]')).toBeNull()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:client-config')

    await wrapper.get('[data-test="client-config-close"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    expect(wrapper.get<HTMLInputElement>('[data-test="client-config-key"]').element.value).toBe('')
  })

  it('提示合并已有配置，并在下载失败时保留可复制的预览', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: [{ id: 'downloadable-model' }],
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: () => { throw new Error('download blocked') },
    })
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
    await wrapper.get('[data-test="client-config-target-pi"]').trigger('click')
    await wrapper.get('[data-test="client-config-verify"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="client-config-pi-models"]').setValue(['downloadable-model'])

    expect(wrapper.text()).toContain('请合并到已有配置，不要直接覆盖')
    await wrapper.get('[data-test="client-config-download"]').trigger('click')
    expect(wrapper.get('[data-test="client-config-status"]').text()).toContain('下载失败')
    expect(wrapper.get('[data-test="client-config-preview"]').text()).toContain('downloadable-model')
  })
})

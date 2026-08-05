# API Key Client Config Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let API-key users generate, copy, and download ready-to-use Claude Code, Codex, OpenCode, and Pi configuration files for a selected gateway model.

**Architecture:** Add a pure frontend configuration generator that accepts an API key, a canonical gateway model ID, and the browser origin. Keep the one-time secret boundary intact: API-key list records only supply names/prefixes, while users must explicitly paste the secret into the generator. Render the generator as a reusable dialog from the API Key page, with client-specific file location, content preview, copy, and download actions.

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus, Vitest, jsdom.

## Global Constraints

- Do not expose, persist, or derive an API key from API-key list data; only use the secret the user enters in the dialog.
- Populate the model selector from `ModelResponse.canonical_name`; do not use the database numeric primary key as the provider model string.
- Generator input is the current browser origin. OpenAI-compatible clients receive `${origin}/v1`; Claude Code receives `${origin}` because it appends `/v1/messages` itself.
- Claude Code output is `~/.claude/settings.json` JSON with Anthropic gateway environment variables.
- Codex output is `~/.codex/config.toml` TOML with a custom Responses API provider and its explicit bearer-token setting; the dialog warns that every generated file contains the entered secret.
- OpenCode output is `opencode.json` JSON with OpenAI-compatible provider options and a selected model.
- Pi output is `~/.pi/agent/models.json` JSON with an OpenAI-compatible provider and selected model.
- All production behavior must be introduced through a failing test first.

---

### Task 1: Pure configuration generator

**Files:**
- Create: `frontend/src/utils/clientConfig.ts`
- Test: `frontend/tests/client-config.spec.ts`

**Interfaces:**
- Produces: `ClientConfigTarget`, `ClientConfigFile`, and `buildClientConfig(target, { apiKey, baseUrl, modelId })`.
- Consumed by: `ClientConfigDialog.vue`.

- [ ] **Step 1: Write the failing test**

```ts
expect(buildClientConfig('codex', {
  apiKey: 'sk-gw-example',
  baseUrl: 'https://gateway.example',
  modelId: 'gateway-model',
})).toEqual({
  filename: 'config.toml',
  location: '~/.codex/config.toml',
  content: expect.stringContaining('model = "gateway-model"'),
})
```

Add literal content assertions for all four targets: Claude uses `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`; Codex uses a custom `model_providers.gateway` provider with an explicit bearer token; OpenCode uses an OpenAI-compatible `baseURL` and `apiKey`; Pi declares an `openai-completions` provider and model ID.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --run tests/client-config.spec.ts`

Expected: FAIL because `@/utils/clientConfig` is missing.

- [ ] **Step 3: Write minimal implementation**

```ts
export function buildClientConfig(target: ClientConfigTarget, input: ClientConfigInput): ClientConfigFile {
  const openAiBaseUrl = withoutTrailingSlash(input.baseUrl)
  // Return a client-specific JSON/TOML document with the literal selected model ID.
}
```

Escape JSON through `JSON.stringify`; use a TOML string escaper for model ID and URL; reject blank API key, base URL, or model ID with an `Error`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --run tests/client-config.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/clientConfig.ts frontend/tests/client-config.spec.ts
git commit -m "feat: generate client config files"
```

### Task 2: Reusable client configuration dialog

**Files:**
- Create: `frontend/src/components/api-keys/ClientConfigDialog.vue`
- Test: `frontend/tests/api-keys.spec.ts`

**Interfaces:**
- Consumes: `ClientConfigTarget`, `buildClientConfig`, `ModelResponse[]`, and a dialog `modelValue`.
- Produces: copy/download actions and the generated document preview.

- [ ] **Step 1: Write the failing test**

```ts
const wrapper = mount(ClientConfigDialog, { props: { modelValue: true, models } })
await wrapper.get('[data-test="client-config-model"]').setValue('claude-opus')
await wrapper.get('[data-test="client-config-key"]').setValue('sk-gw-real-secret')
await wrapper.get('[data-test="client-config-target-codex"]').trigger('click')
expect(wrapper.get('[data-test="client-config-preview"]').text()).toContain('model = "claude-opus"')
```

Add a second test that changes the target to Pi and intercepts `URL.createObjectURL`, asserting the download filename is `models.json` and that the content includes the selected canonical ID. The production change that should make these tests fail is omitting the model ID from the generated content or downloading the wrong client file.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --run tests/api-keys.spec.ts`

Expected: FAIL because `ClientConfigDialog.vue` is missing.

- [ ] **Step 3: Write minimal implementation**

Implement a dialog with:

```vue
<select v-model="selectedModelId" data-test="client-config-model">
  <option v-for="model in models" :key="model.id" :value="model.canonical_name">
    {{ model.display_name }} · {{ model.canonical_name }}
  </option>
</select>
<ElInput v-model="apiKey" data-test="client-config-key" type="password" show-password />
```

Use target buttons for Claude Code, Codex, OpenCode, and Pi. Disable copy/download until both fields are non-empty. Download a UTF-8 text Blob through a temporary anchor and revoke the object URL. Reset the secret whenever the dialog closes.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --run tests/api-keys.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/api-keys/ClientConfigDialog.vue frontend/tests/api-keys.spec.ts
git commit -m "feat: add client config dialog"
```

### Task 3: API Key page integration

**Files:**
- Modify: `frontend/src/views/ApiKeysView.vue`
- Test: `frontend/tests/api-keys.spec.ts`

**Interfaces:**
- Consumes: `ClientConfigDialog` and the page's existing loaded `models` catalog.
- Produces: an accessible “客户端配置” page-header action available to administrators and regular users.

- [ ] **Step 1: Write the failing test**

```ts
const wrapper = await mountKeys()
await wrapper.get('[data-test="open-client-config"]').trigger('click')
expect(wrapper.get('[data-test="client-config-dialog"]').isVisible()).toBe(true)
expect(wrapper.get('[data-test="client-config-model"]').text()).toContain('gpt-4.1')
```

Add a regular-user test that loads only `/user/models` and verifies no administrator catalog endpoint is requested when opening the dialog. The production change that should make these tests fail is wiring the dialog to an empty or unauthorized model list.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --run tests/api-keys.spec.ts`

Expected: FAIL because `open-client-config` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add a `clientConfigOpen` ref, page-header button, and dialog:

```vue
<ElButton data-test="open-client-config" @click="clientConfigOpen = true">
  <Document /> 客户端配置
</ElButton>
<ClientConfigDialog v-model="clientConfigOpen" :models="models" />
```

Place the action before “使用示例”; reuse the loaded model list rather than adding a new API request.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --run tests/api-keys.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ApiKeysView.vue frontend/tests/api-keys.spec.ts
git commit -m "feat: expose client configs from API keys"
```

### Task 4: Verification

**Files:**
- Verify: all modified frontend source and tests

- [ ] **Step 1: Run focused tests**

Run: `npm --prefix frontend test -- --run tests/client-config.spec.ts tests/api-keys.spec.ts`

Expected: PASS.

- [ ] **Step 2: Run frontend quality checks**

Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run build`

Expected: all commands exit 0.

- [ ] **Step 3: Run full frontend regression tests**

Run: `npm --prefix frontend test`

Expected: all tests pass.

- [ ] **Step 4: Review diff**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only feature files changed.

## Review remediation (2026-08-05)

### Task 5: Resolve models against the manually entered API key

**Files:** `frontend/src/components/api-keys/ClientConfigDialog.vue`, `frontend/tests/client-config-dialog.spec.ts`, `frontend/src/views/ApiKeysView.vue`, and `frontend/tests/api-keys.spec.ts`.

- [ ] **Step 1: Write failing dialog tests** for `GET /v1/models`: send `Authorization: Bearer <key>` for Codex, OpenCode, and Pi; send `x-api-key` plus `anthropic-version: 2023-06-01` for Claude. Assert only returned `data[].id` values can be selected and a failed request keeps download disabled.
- [ ] **Step 2: Confirm RED** with `npm --prefix frontend test -- --run tests/client-config-dialog.spec.ts`.
- [ ] **Step 3: Implement minimal key-scoped resolution.** Add `verifyAndLoadModels()` to fetch `${baseUrl}/v1/models`, parse non-empty string IDs only, and clear resolved models when the key or client changes. Remove the catalog-model prop from the dialog so disabled or out-of-scope administrator models cannot be selected.
- [ ] **Step 4: Confirm GREEN** with `npm --prefix frontend test -- --run tests/client-config-dialog.spec.ts tests/api-keys.spec.ts`.

### Task 6: Prevent accidental overwrite and report download failures

**Files:** `frontend/src/components/api-keys/ClientConfigDialog.vue` and `frontend/tests/client-config-dialog.spec.ts`.

- [ ] **Step 1: Write failing tests** for a visible “请合并到已有配置，不要直接覆盖” warning and for a throwing `URL.createObjectURL`, asserting a `client-config-status` failure message.
- [ ] **Step 2: Confirm RED** with `npm --prefix frontend test -- --run tests/client-config-dialog.spec.ts`.
- [ ] **Step 3: Implement minimal handling.** Wrap Blob URL creation and temporary-anchor download in `try/catch/finally`, revoke only a created URL, and show “下载失败，请复制预览内容并合并到已有配置文件。” on failure.
- [ ] **Step 4: Confirm GREEN** with `npm --prefix frontend test -- --run tests/client-config-dialog.spec.ts`.

### Task 7: Final verification

- [ ] Run `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`, and `git diff --check`; all must exit zero.

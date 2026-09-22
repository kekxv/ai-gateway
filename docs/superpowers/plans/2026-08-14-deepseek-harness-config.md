# DeepSeek Harness Configuration Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators generate paired DeepSeek Harness `.dsh/.credentials.yaml` and `.dsh/settings.yaml` files for enabled gateway models.

**Architecture:** The console has the authenticated model catalog, so it will build both YAML files client-side. A pure serializer creates deterministic, safely quoted YAML; the provider page collects provider identity, one OpenAI adapter, the externally reachable gateway URL, API-key environment-variable name and its value, then offers separate copy and download controls. The API key never reaches the ai-gateway backend and is cleared when the dialog closes.

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus, Vitest.

## Global Constraints

- Emit `ui-onboarding`, `llm-pi-ai.providers`, and `agent-default-model` in `settings.yaml`, matching the supplied DeepSeek Harness layout.
- Generate `.credentials.yaml` as one `environment-variable-name: API-key` mapping; never send the API key to the ai-gateway backend or persist it in browser storage.
- Expose `api` as a per-provider single-select control for `openai-responses` (default) or `openai-completions`.
- Use enabled canonical models in deterministic name order.
- Map `image` to `input: [text, image]`; map all other model types to `input: [text]`, the two DeepSeek Harness input modalities documented upstream.

---

### Task 1: Implement the YAML serializer

**Files:**

- Create: `frontend/src/lib/deepseekHarness.ts`
- Create: `frontend/tests/deepseek-harness.spec.ts`

**Interfaces:**

- Produces: `buildDeepSeekHarnessFiles(options: DeepSeekHarnessOptions): { credentialsYaml: string; settingsYaml: string }`.
- Consumes: structural model values with `canonical_name`, `model_type`, and `enabled`.

- [ ] **Step 1: Write a failing serializer test**

```ts
expect(buildDeepSeekHarnessFiles({
  providerId: 'kekxv', displayName: 'ai.kekxv.com',
  baseUrl: 'https://ai.kekxv.com/v1', apiKeyEnv: 'KEKXV_API_KEY',
  apiKey: 'sk-gw-test', api: 'openai-responses', defaultModel: 'chat',
  models: [
    { canonical_name: 'vision', model_type: 'image', enabled: true },
    { canonical_name: 'chat', model_type: 'text', enabled: true },
    { canonical_name: 'disabled', model_type: 'text', enabled: false },
  ],
}).settingsYaml).toContain('api: openai-responses')
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend run test -- tests/deepseek-harness.spec.ts`

Expected: FAIL because the serializer module does not exist.

- [ ] **Step 3: Implement the minimal serializer**

```ts
export function buildDeepSeekHarnessFiles(options: DeepSeekHarnessOptions): DeepSeekHarnessFiles {
  const models = options.models.filter((model) => model.enabled)
  // Sort by canonical_name and emit the documented credentials and settings YAML.
}
```

Use a local YAML scalar-quoting helper. Emit the API key only into `credentialsYaml`; settings references it through `apiKeyEnv`. Output `input: [text, image]` for `image` models and `input: [text]` for all others.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix frontend run test -- tests/deepseek-harness.spec.ts`

Expected: PASS, including model filtering, ordering, input mappings, and scalar quoting.

- [ ] **Step 5: Commit Task 1**

Stage only `frontend/src/lib/deepseekHarness.ts` and `frontend/tests/deepseek-harness.spec.ts` with message `feat: generate DeepSeek Harness configuration files`.

### Task 2: Add the provider-console generator

**Files:**

- Modify: `frontend/src/views/ProvidersView.vue`
- Modify: `frontend/tests/providers.spec.ts`

**Interfaces:**

- Consumes: `listModels()` and `buildDeepSeekHarnessFiles()`.
- Produces: `data-test="generate-deepseek-harness-config"`, a generator dialog, and separate `.credentials.yaml` / `settings.yaml` copy and download controls.

- [ ] **Step 1: Write a failing view test**

```ts
await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
await flushPromises()
expect(wrapper.get('[data-test="deepseek-harness-settings"]').text())
  .toContain('api: openai-responses')
```

Mock `GET /admin/models` with one enabled text model, one enabled image model, and one disabled model. Assert only enabled models are shown and image has `input: [text, image]`.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend run test -- tests/providers.spec.ts`

Expected: FAIL because the action and dialog do not exist.

- [ ] **Step 3: Implement the dialog**

```ts
const harnessProviderId = ref('ai-gateway')
const harnessApi = ref<'openai-responses' | 'openai-completions'>('openai-responses')
const harnessBaseUrl = ref(`${window.location.origin}/v1`)
const harnessApiKeyEnv = ref('AI_GATEWAY_API_KEY')
const harnessApiKey = ref('')
const harnessModels = ref<ModelResponse[]>([])
const harnessFiles = computed(() => buildDeepSeekHarnessFiles({
  providerId: harnessProviderId.value.trim(), api: harnessApi.value,
  baseUrl: harnessBaseUrl.value.trim(), apiKeyEnv: harnessApiKeyEnv.value.trim(),
  apiKey: harnessApiKey.value,
  models: harnessModels.value,
}))
```

Load models when the dialog opens. Render the adapter as a radio group (one adapter per provider), with `openai-responses` selected by default. Require provider ID, display name, base URL, environment-variable name, API key, and default model. Render the API key as a password input; clear it when the dialog closes; add copy and `text/yaml;charset=utf-8` download actions for both files.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix frontend run test -- tests/providers.spec.ts tests/deepseek-harness.spec.ts && npm --prefix frontend run lint && npm --prefix frontend run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Stage only the provider view and its test with message `feat: add DeepSeek Harness config export`.

### Task 3: Verify the complete workflow

**Files:**

- Modify: none

- [ ] **Step 1: Run frontend tests and production build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 2: Run browser acceptance tests**

Run: `CI=true E2E_ADMIN_EMAIL='console-e2e@example.com' E2E_ADMIN_PASSWORD="$(openssl rand -hex 24)" npm --prefix frontend run e2e`

Expected: PASS after `alembic upgrade head` with the CI database environment.

- [ ] **Step 3: Run backend quality checks**

Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run mypy src scripts && uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90`

Expected: PASS.

## Self-Review

- The plan covers the upstream provider schema, no-secret export requirement, model input modality declaration, console interaction, and CI-equivalent validation.
- The serializer interface used by the view is specified in Task 1 and consumed consistently in Task 2.

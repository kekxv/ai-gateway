# Provider And Model Management UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider and model management cards denser and separate enabled resources from disabled resources with clear, accessible color and text cues.

**Architecture:** Add one presentation-only status group component shared by both management pages. Each view derives enabled and disabled results from its existing filtered collection, preserving all API, search, filtering, loading, and card interaction behavior. Compactness remains inside the existing card and grid CSS so no business component interface changes are required.

**Tech Stack:** Vue 3, TypeScript, Element Plus, Vitest, Vue Test Utils, CSS.

**Status:** Implemented and verified in the current worktree on 2026-08-05. No commit was created.

## Global Constraints

- Do not change provider, model, route, search, or API behavior.
- Enabled resources render before disabled resources.
- Status is conveyed by both Chinese text and color; color is never the only cue.
- Search and provider filtering apply before status grouping.
- Regular-user model browsing remains read-only.
- Cards remain usable at mobile widths down to 320px.
- Do not commit unless the user explicitly asks for a commit.

---

### Task 1: Status-separated provider and model results

**Files:**
- Create: `frontend/src/components/common/ResourceStatusGroup.vue`
- Modify: `frontend/src/views/ProvidersView.vue`
- Modify: `frontend/src/views/ModelsView.vue`
- Test: `frontend/tests/providers.spec.ts`
- Test: `frontend/tests/models.spec.ts`

**Interfaces:**
- Produces: `ResourceStatusGroup` with props `status: 'enabled' | 'disabled'`, `title: string`, and `count: number`, plus a default slot for cards.
- Consumes: existing `filteredProviders`, `filteredModels`, `ProviderCard`, and `ModelCard` results.

- [ ] **Step 1: Write failing provider grouping test**

Add a disabled provider fixture and assert that the enabled and disabled groups each contain only their matching provider card:

```ts
it('将启用与停用供应商分区并显示各自数量', async () => {
  const disabledProvider = { ...geminiFixture, enabled: false }
  const wrapper = await mountProviders([providerFixture, disabledProvider])

  const enabledGroup = wrapper.get('[data-test="enabled-provider-group"]')
  const disabledGroup = wrapper.get('[data-test="disabled-provider-group"]')
  expect(enabledGroup.text()).toContain('启用中')
  expect(enabledGroup.text()).toContain('1 个')
  expect(enabledGroup.find('[data-test="provider-card-1"]').exists()).toBe(true)
  expect(enabledGroup.find('[data-test="provider-card-2"]').exists()).toBe(false)
  expect(disabledGroup.text()).toContain('已停用')
  expect(disabledGroup.text()).toContain('1 个')
  expect(disabledGroup.find('[data-test="provider-card-2"]').exists()).toBe(true)
  expect(disabledGroup.find('[data-test="provider-card-1"]').exists()).toBe(false)
})
```

- [ ] **Step 2: Run provider test and verify RED**

Run: `npm --prefix frontend run test -- providers.spec.ts`

Expected: FAIL because neither status group exists.

- [ ] **Step 3: Write failing model grouping test**

Render one enabled and one disabled model, then assert the two status groups have exclusive membership:

```ts
it('将启用与停用模型分区并显示各自数量', async () => {
  const disabledModel = { ...scientificZeroFixture, enabled: false }
  useCatalog([modelFixture, disabledModel], [])
  const wrapper = mount(ModelsView, { attachTo: document.body })
  await flushPromises()

  const enabledGroup = wrapper.get('[data-test="enabled-model-group"]')
  const disabledGroup = wrapper.get('[data-test="disabled-model-group"]')
  expect(enabledGroup.text()).toContain('启用中')
  expect(enabledGroup.find('[data-test="model-card-1"]').exists()).toBe(true)
  expect(enabledGroup.find('[data-test="model-card-2"]').exists()).toBe(false)
  expect(disabledGroup.text()).toContain('已停用')
  expect(disabledGroup.find('[data-test="model-card-2"]').exists()).toBe(true)
  expect(disabledGroup.find('[data-test="model-card-1"]').exists()).toBe(false)
  wrapper.unmount()
})
```

- [ ] **Step 4: Run model test and verify RED**

Run: `npm --prefix frontend run test -- models.spec.ts`

Expected: FAIL because neither status group exists.

- [ ] **Step 5: Implement the shared status group and derived collections**

Create the component with a semantic section, visible status dot, title, count, and default slot. Add computed enabled/disabled result arrays after existing search/filter logic, then render one group per non-empty array. Keep the existing `ElEmpty` branch when both arrays are empty.

```ts
const enabledProviders = computed(() => filteredProviders.value.filter((item) => item.enabled))
const disabledProviders = computed(() => filteredProviders.value.filter((item) => !item.enabled))
```

```vue
<ResourceStatusGroup
  v-if="enabledProviders.length > 0"
  data-test="enabled-provider-group"
  status="enabled"
  title="启用中"
  :count="enabledProviders.length"
>
  <div class="providers-grid">...</div>
</ResourceStatusGroup>
```

Apply the equivalent `enabledModels` and `disabledModels` collections and model group markup.

- [ ] **Step 6: Run both focused test files and verify GREEN**

Run: `npm --prefix frontend run test -- providers.spec.ts models.spec.ts`

Expected: both files pass with exclusive group membership and correct counts.

### Task 2: Compact card density and responsive polish

**Files:**
- Modify: `frontend/src/components/providers/ProviderCard.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/views/ProvidersView.vue`
- Modify: `frontend/src/views/ModelsView.vue`

**Interfaces:**
- Preserves: all existing component props, emits, `data-test` hooks, buttons, and responsive behavior.
- Produces: denser cards with 340px desktop minimum width, 12px radius, 1rem outer padding, tighter action spacing, two-column provider metadata, and two-column base model price metrics.

- [ ] **Step 1: Compact view grids and loading skeletons**

Change both resource grids and loading grids from `minmax(400px, 1fr)` to `minmax(min(100%, 340px), 1fr)`, reduce grid padding to `1rem`, gap to `0.75rem`, and skeleton heights to match the denser cards.

- [ ] **Step 2: Compact provider cards**

Reduce card padding/radius/header/body spacing, use a two-column metadata grid at desktop widths, tighten protocol items, and retain a one-column mobile fallback. Disabled cards use a neutral gray surface and reduced visual contrast while keeping controls readable.

- [ ] **Step 3: Compact model cards**

Reduce card padding/radius/header/body spacing. Mark canonical-name information as full width and arrange the four base prices in a two-column grid. Tighten aliases and route sections without removing any content or action.

- [ ] **Step 4: Run focused tests after the CSS refactor**

Run: `npm --prefix frontend run test -- providers.spec.ts models.spec.ts routes.spec.ts`

Expected: all provider, model, and route interaction tests pass.

### Task 3: Complete frontend verification

**Files:**
- Verify: `frontend/`

**Interfaces:**
- Produces: evidence that the UI refinement compiles, formats, and preserves the full frontend behavior suite.

- [ ] **Step 1: Run frontend lint and type-check**

Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck`

Expected: both commands pass.

- [ ] **Step 2: Run the full frontend test suite**

Run: `npm --prefix frontend run test`

Expected: all frontend tests pass.

- [ ] **Step 3: Build the production frontend**

Run: `npm --prefix frontend run build`

Expected: Vue type compilation and Vite production build pass.

- [ ] **Step 4: Review the final diff**

Run: `git diff --check && git status --short && git diff --stat`

Expected: no whitespace errors, no generated artifacts, and only the planned frontend, test, and plan files are modified.

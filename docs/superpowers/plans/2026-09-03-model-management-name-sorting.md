# Model Management Name Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display models in every Model Management status group in ascending order by model name.

**Architecture:** Keep the API response and stored model state unchanged. Sort a copied filtered result in `ModelsView` by `display_name`, with `canonical_name` as a deterministic tie-breaker, before the existing status-group computed values consume it.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, MSW.

**Spec:** User request: “前端 模型管理 里面排序一下，按照名字排序”.

## Global Constraints

- Preserve existing text search, provider filtering, and status grouping behavior.
- Sort ascending by `display_name`; use `canonical_name` to resolve equal display names.
- Do not mutate the API-loaded `models` array in a computed property.
- Add a behavior-focused regression test before production-code changes.

---

### Task 1: Sort the rendered model catalog by name

**Files:**
- Modify: `frontend/tests/models.spec.ts`
- Modify: `frontend/src/views/ModelsView.vue`

**Interfaces:**
- Consumes: `ModelResponse.display_name` and `ModelResponse.canonical_name` in `models`.
- Produces: `filteredModels`, an ascending, deterministically ordered collection used by `enabledModels` and `disabledModels`.

- [x] **Step 1: Write the failing test**

Add a test beside the existing status-group tests that loads three models in API order `Zulu`, `Alpha`, and `Bravo`, then asserts that the rendered cards in the disabled group expose IDs in `Alpha`, `Bravo`, `Zulu` order:

```ts
it('按名称升序显示模型', async () => {
  const alpha = { ...scientificZeroFixture, id: 3, display_name: 'Alpha', canonical_name: 'alpha', enabled: false }
  const bravo = { ...scientificZeroFixture, id: 4, display_name: 'Bravo', canonical_name: 'bravo', enabled: false }
  const zulu = { ...scientificZeroFixture, id: 2, display_name: 'Zulu', canonical_name: 'zulu', enabled: false }
  useCatalog([zulu, alpha, bravo], [])
  const wrapper = mount(ModelsView, { attachTo: document.body })
  await flushPromises()

  expect(
    wrapper.find('[data-test="disabled-model-group"]').findAll('[data-test^="model-card-"]').map((card) => card.attributes('data-test')),
  ).toEqual(['model-card-3', 'model-card-4', 'model-card-2'])
  wrapper.unmount()
})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- --run tests/models.spec.ts`

Expected: FAIL because cards retain API response order (`Zulu`, `Alpha`, `Bravo`).

- [x] **Step 3: Write the minimal implementation**

At the end of the existing `filteredModels` computed block in `frontend/src/views/ModelsView.vue`, return a copied and sorted list:

```ts
return [...result].sort(
  (left, right) =>
    left.display_name.localeCompare(right.display_name, 'zh-CN') ||
    left.canonical_name.localeCompare(right.canonical_name, 'zh-CN'),
)
```

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- --run tests/models.spec.ts`

Expected: PASS, including the new rendered-order assertion.

- [x] **Step 5: Run frontend verification**

Run: `npm run lint && npm run typecheck && npm test`

Expected: all commands exit with status 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ModelsView.vue frontend/tests/models.spec.ts docs/superpowers/plans/2026-09-03-model-management-name-sorting.md
git commit -m "feat: sort model management list by name"
```

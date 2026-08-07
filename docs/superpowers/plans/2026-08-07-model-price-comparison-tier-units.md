# Model Price Comparison and Tier Units Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators select multiple models and compare their cost/public prices in a dialog, while allowing tier length limits to be edited as raw tokens or `K` units without changing backend billing semantics.

**Architecture:** Move price comparison out of each model card into a page-level dialog whose rows are selected models and their configured tiers. For every model/tier/price bucket, aggregate minimum–maximum cost and public prices across configured eligible routes; keep provider routes as hidden calculation inputs rather than comparison objects. Keep `max_input_tokens` as the canonical API value and convert the form-only `token`/`k` representation at the UI boundary.

**Tech Stack:** Vue 3, TypeScript, Element Plus, Vitest, Vue Test Utils, existing exact-decimal helpers.

## Global Constraints

- Price comparison is administrator-only because platform cost and provider multipliers are private.
- A comparison requires at least two selected models.
- Comparison rows represent models and tiers, never individual provider routes.
- Only enabled routes on enabled providers with at least one enabled protocol contribute to price ranges.
- Each price applies `model.price_multiplier` and the provider's cost/public multiplier using exact decimal arithmetic.
- Existing `price_tiers` ordering and inclusive `max_input_tokens` billing semantics remain unchanged.
- Tier unit selection is presentation-only; API payloads continue sending integer token counts or `null` for the final unbounded tier.
- `K` means exactly 1,000 tokens and may use up to three decimal places so switching units preserves any whole-token threshold.

---

### Task 1: Model Selection and Comparison Dialog

**Files:**
- Create: `frontend/src/components/models/ModelPriceComparisonDialog.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/views/ModelsView.vue`
- Delete: `frontend/src/components/models/PriceComparison.vue`
- Test: `frontend/tests/models.spec.ts`

**Interfaces:**
- `ModelCard` consumes optional `selectable: boolean` and `selected: boolean` props and emits `update:selected(boolean)`.
- `ModelPriceComparisonDialog` consumes `modelValue`, `models`, `routes`, and `providers`, and emits `update:modelValue(boolean)`.
- `ModelsView` owns `selectedModelIds: Set<number>` and opens the dialog only when at least two loaded models are selected.

- [ ] **Step 1: Write failing selection and dialog tests**

Add tests that mount the real `ModelsView`, select two model checkboxes, click `price-comparison-open`, and assert the dialog renders model names as rows without provider names. Use literal fixtures with model A prices `2/8/0.5/2.5`, model B prices `4/12/1/3`, and two eligible provider multipliers so expected cost/public ranges are hand-derived strings. Add a disabled-route fixture with extreme multipliers and assert it does not affect either range.

- [ ] **Step 2: Run tests to verify RED**

Run: `npm --prefix frontend run test -- tests/models.spec.ts`

Expected: FAIL because model selection controls, `price-comparison-open`, and the model comparison dialog do not exist.

- [ ] **Step 3: Implement model selection and model-oriented aggregation**

Add an administrator checkbox to each model card. Add the page action and dialog state to `ModelsView`. In the dialog, convert each model's configured tiers (or legacy base prices) into rows and calculate exact min/max values using `multiplyDecimals(base, modelMultiplier, providerMultiplier)`. Filter calculation routes with:

```ts
route.enabled &&
provider.enabled &&
provider.protocols.some((protocol) => protocol.enabled)
```

Render grouped columns for input, output, cache read, and cache write, with cost and user-price cells for each. Delete the route-oriented component and its per-card toggle.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `npm --prefix frontend run test -- tests/models.spec.ts tests/decimal.spec.ts`

Expected: all model and exact-decimal tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/models frontend/src/views/ModelsView.vue frontend/tests/models.spec.ts
git commit -m "feat: compare prices across selected models"
```

### Task 2: Token/K Tier Limit Editing

**Files:**
- Modify: `frontend/src/components/models/ModelFormDrawer.vue`
- Test: `frontend/tests/models.spec.ts`

**Interfaces:**
- `PriceTierRow` stores `maxInputValue: number | null` and `maxInputUnit: 'token' | 'k'` as form-only state.
- `tierLimitTokens(row: PriceTierRow) -> number | null` produces the canonical integer sent as `max_input_tokens`.
- Existing stored limits divisible by 1,000 open in `k`; other limits open in `token`.

- [ ] **Step 1: Write failing unit conversion tests**

Add tests that open a tier with stored `272000`, assert the UI shows value `272` and unit `K`, submit, and assert `max_input_tokens: 272000`. Switch that row to raw tokens and assert the displayed value becomes `272000` without changing the payload. Add a `272.5K` case and assert it serializes to `272500`, plus an unsafe/non-whole conversion case that displays a validation error and does not submit.

- [ ] **Step 2: Run tests to verify RED**

Run: `npm --prefix frontend run test -- tests/models.spec.ts`

Expected: FAIL because `model-tier-limit-unit-*` does not exist and stored limits are still displayed without a unit.

- [ ] **Step 3: Implement form-only unit conversion**

Render the bounded limit input and `ElSelect` in one compact input group with options `Token` and `K`. Preserve canonical tokens while switching units, convert to integer tokens in `tierPayload()`, validate strict ordering after conversion, and format tier labels as `Length ≤ 272K` when divisible by 1,000.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `npm --prefix frontend run test -- tests/models.spec.ts`

Expected: all model form tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/models/ModelFormDrawer.vue frontend/tests/models.spec.ts
git commit -m "feat: support token and K tier limits"
```

### Task 3: Regression and Quality Verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Test: `frontend/tests/models.spec.ts`

**Interfaces:**
- Documentation describes selected-model comparison and token/K form input without implying that routes are comparison objects.

- [ ] **Step 1: Add regression coverage for role boundaries and stale selections**

Assert ordinary users have no model-selection controls or internal cost dialog. Assert a deleted/reloaded model is removed from `selectedModelIds`, and compare remains disabled until two current models are selected.

- [ ] **Step 2: Run focused regression tests**

Run: `npm --prefix frontend run test -- tests/models.spec.ts tests/decimal.spec.ts tests/admin-layout.spec.ts`

Expected: all focused tests pass.

- [ ] **Step 3: Update README descriptions**

Document that administrators select multiple models and compare cost/public ranges by pricing tier, and that tier upper bounds accept Token or K display units while remaining stored as tokens.

- [ ] **Step 4: Run frontend quality gates**

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
git diff --check
```

Expected: zero lint/type errors, all Vitest files pass, production build succeeds, and no whitespace errors remain.

- [ ] **Step 5: Commit**

```bash
git add README.md README.zh-CN.md frontend/tests/models.spec.ts
git commit -m "docs: explain model price comparison"
```

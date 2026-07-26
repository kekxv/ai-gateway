# Frontend Admin Test Repair Design

## Goal

Repair the 50 failing frontend unit tests without reverting the current card- and checkbox-based admin UI. Restore capabilities lost during the refactor, make asynchronous operation state visible and enforceable, and align stale tests with the intended interaction model.

## Failure Classification

The failures are confined to API keys, providers, models, and routes. They fall into three groups:

1. Stable selectors and test interactions were removed while behavior moved into cards, drawers, collapsible route lists, and checkboxes.
2. Product behavior regressed: API-key owner selection disappeared, provider credentials became limited to one schema, route notices became invisible, and route actions on non-initial model cards silently stopped.
3. Security and concurrency behavior is incomplete: generated examples repeat a one-time secret, and provider/model/route controls look usable while an exclusive mutation is running.

Tests should be updated only where the intended UI changed. Assertions that protect supported product behavior, security, or concurrency remain authoritative.

## Selected Design

### API-key ownership and scopes

`ApiKeyFormDrawer` receives the users list from `ApiKeysView` and restores an explicit owner selector. The selector is required for creation and disabled during editing so ownership cannot be transferred accidentally. The drawer no longer depends on the current authentication store to choose an owner.

The current checkbox UI for provider and model restrictions remains. Stable hooks identify each checkbox and tests interact with those controls instead of the removed multi-select elements.

### One-time secret handling

The newly issued key appears only in the dedicated one-time secret field. cURL examples use a fixed environment-variable reference such as `$AI_GATEWAY_API_KEY`; they never interpolate the raw key. Copying or downloading the secret remains explicit and unchanged.

### Provider actions and credentials

Provider cards restore stable action hooks. Edit, sync, and delete are all disabled while any exclusive provider operation is active; delete also remains disabled for providers that cannot be deleted.

The guided API-key, authentication-scheme, and authentication-header fields remain the primary path. An advanced credential JSON-object editor restores the public `JsonObject` capability for providers with additional or nonstandard credential fields. Its rules are:

- blank input means no credential change on edit and no credential payload on create;
- the value must parse to a JSON object, not an array or scalar;
- guided nonblank fields are merged over the advanced object for their reserved keys;
- sensitive draft values are cleared when the drawer closes or a submission completes;
- malformed advanced JSON produces inline validation and no request.

This preserves the approachable common case without restricting supported provider schemas.

### Model cards and route ownership

Model cards restore stable hooks for edit/delete/status/route count and per-card route creation. Route rows restore hooks for edit/delete/disable/status. The tests expand a card before interacting with its routes, matching the current collapsed card UI; the removed master/detail selection panel is not restored.

Route mutations are keyed by the model and route passed by the card event. They no longer depend on obsolete `selectedModelId` state. Each card receives route-loading state and renders its own routes from the canonical `allRoutes` collection. Stale selection-only route state is removed where it has no remaining consumer.

Route success and conflict notices are rendered. A historical-request deletion conflict exposes the existing “disable instead” action. During an exclusive model or route mutation, conflicting model/card/route controls are visibly disabled as well as protected by handler guards.

## Testing Strategy

Use focused Vitest files during development with one worker. Production changes are introduced behind failing behavioral regressions first, then stale DOM interactions are updated to the selected UI.

Coverage includes:

- explicit API-key owner selection, immutable edit ownership, checkbox scopes, and single secret occurrence;
- generic provider credential objects, invalid JSON, secret draft clearing, stable action hooks, and disabled operation states;
- model card actions and current card-layout empty states;
- expanding different model cards, creating/editing/deleting/disabling their routes, visible notices, historical-route recovery, counts, loading, and exclusive mutation behavior.

After focused suites pass, run the bounded public `npm run test` command, typecheck, lint, and production build. The resource guard supplies the two-worker and 120-second suite limits.

## Scope Boundaries

- Do not restore the removed model master/detail layout.
- Do not replace checkbox restrictions with the former multi-select UI.
- Do not expose stored provider secrets returned only as `has_credential`.
- Do not weaken concurrency guards or delete-conflict recovery assertions.
- Do not change backend API contracts.
- Preserve the existing uncommitted `auth.ready` router-guard change.

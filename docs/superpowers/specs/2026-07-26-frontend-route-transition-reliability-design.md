# Frontend Route Transition Reliability Design

## Goal

Eliminate the unhandled dynamic-import rejection and Vue route-transition warnings introduced by the current admin-shell changes, while preserving lazy-loaded routes, page fade transitions, and a seven-page `KeepAlive` cache.

## Root Causes

`AdminLayout.vue` currently starts duplicate route imports on navigation-item mouseover and discards each returned promise with `void`. A failed Vite HMR request, stale hashed chunk, or non-JavaScript proxy response therefore becomes an unhandled promise rejection before navigation occurs.

The same layout places routed components inside `<Transition>` and `<KeepAlive>`. Every active admin view renders multiple top-level template nodes, so Vue receives a Fragment rather than an element root and cannot attach transition hooks. The warning names `ApiKeysView`, but the structural problem applies to Dashboard, Providers, Models, Users, API Keys, Request Logs, and Security.

## Selected Design

### Route loading

Remove `routeComponentPreloads` and the navigation `mouseover` handler from `AdminLayout.vue`. Vue Router remains the only owner of route lazy imports, using the existing `component: () => import(...)` records. This removes speculative duplicate imports and the unhandled rejection path without changing navigation behavior or route chunking.

This change does not add an automatic page reload for arbitrary chunk failures. The production backend already returns `no-cache` for the SPA entry and does not rewrite missing `/console/assets/*` requests to HTML. A genuine production chunk 404 still indicates a stale/mixed deployment or proxy error and must remain observable rather than being hidden in a reload loop.

### Transition roots

Wrap the complete template content of each of the seven admin route views in one neutral element with a shared `route-page` class:

- `DashboardView.vue`
- `ProvidersView.vue`
- `ModelsView.vue`
- `UsersView.vue`
- `ApiKeysView.vue`
- `RequestLogsView.vue`
- `SecurityView.vue`

Dialogs and drawers remain children of that root; their Element Plus teleport behavior is unchanged. Existing scoped selectors continue to target their current elements. The wrapper supplies the concrete element required by `<Transition>` and the stable component subtree required by `<KeepAlive>`.

The existing fade CSS, `mode="out-in"`, cache size, navigation behavior, and the uncommitted `auth.ready` router-guard correction remain unchanged.

## Error Handling

Removing speculative preload means hover cannot initiate a module request or reject a discarded promise. Actual route-import failures continue through Vue Router's navigation error path, where they remain visible for diagnosis. No errors are swallowed and no infinite reload marker is introduced.

## Testing

Add an admin-layout regression test that mounts the real Transition instead of Vue Test Utils' transition stub, captures Vue warnings, and verifies that rendering and navigating between representative cached admin pages does not emit the `non-element root node` warning.

Existing focused view tests continue to verify the contents and behavior beneath the new neutral roots. Run the complete frontend type check, lint, unit-test command, and production build. The build verifies that all lazy route imports still produce valid chunks; any pre-existing failures caused by unrelated worktree changes are reported separately.

## Scope Boundaries

- Do not change the route table or eager-load route views.
- Do not remove `<Transition>` or `<KeepAlive>`.
- Do not add automatic reload behavior for deployment/proxy failures.
- Do not change Playwright or backend static-file routing.
- Preserve the current uncommitted router guard change exactly.

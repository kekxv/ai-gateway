# Client thinking configuration implementation plan

**Goal:** Expose client-supported thinking settings in generated configuration files and preserve Pi model metadata.

**Architecture:** Keep serialization in the existing client configuration builders. The dialog supplies optional client-specific values; omitted values retain existing behavior. Pi capability metadata comes from the authenticated catalog and permits an explicit per-model override.

**Tech stack:** Vue 3, TypeScript, Vitest.

## Steps

- [x] Add failing serializer and dialog tests for Claude thinking enable/disable and effort, Codex main/subagent effort, OpenCode model effort, Harness default effort, and Pi metadata/overrides.
- [x] Run the targeted tests to confirm missing behavior.
- [x] Extend `frontend/src/utils/clientConfig.ts` and `frontend/src/lib/deepseekHarness.ts` with optional settings using the respective client schemas.
- [x] Add controls and state reset in `frontend/src/components/api-keys/ClientConfigDialog.vue`; forward Pi reasoning, context window and output limit.
- [x] Run configuration and API-key tests, typecheck, lint and inspect the diff.

## Schema sources

- Codex: https://developers.openai.com/codex/config-reference/ (`model_reasoning_effort`, `agents.default_subagent_reasoning_effort`).
- Claude Code: SchemaStore `claude-code-settings.json` (`alwaysThinkingEnabled`, `effortLevel`: low/medium/high/xhigh).
- OpenCode: `anomalyco/opencode` provider transform and config schemas (model `options.reasoningEffort`).
- Harness: `deepseek-ai/deepseek-harness` `packages/core/agent-default-model/src/index.ts` (`reasoningEffort`).
- Pi: existing model catalog capability fields and serializer contract; `models.json` describes capability rather than session thinking level.

**Validation:** 69 targeted configuration/dialog/API-key tests passed. Frontend typecheck, lint, and `git diff --check` passed. Independent code review found no actionable issues.

## Follow-up: explicit enable/disable

User clarified that all targets must expose an explicit thinking mode switch.

- [x] Add optional `thinkingEnabled` to serializers; disabling overrides selected effort and enabling defaults to medium.
- [x] Add mode controls, disable effort controls when off, and reset the mode with the key/client.
- [x] Preserve Pi model capabilities; provide a companion `~/.pi/agent/settings.json` with `defaultThinkingLevel`, including preview and download.
- [x] Verify enable/disable and Pi downloaded file contents; run tests, typecheck and lint; request independent review.

**Follow-up validation:** 84 targeted tests passed; frontend typecheck and lint passed. Pi settings include selected-model overrides to ensure the switch wins over existing per-model settings. Independent review found no remaining blockers.

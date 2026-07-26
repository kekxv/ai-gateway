# Frontend Test Resource Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `npm run test` as the frontend unit-test entry point while limiting Vitest to two workers and enforcing a 120-second whole-suite deadline with worker cleanup.

**Architecture:** Vitest configuration owns concurrency and per-test limits. A TypeScript runner, launched through the existing `jiti` dependency, owns the outer deadline and Vitest process group; it forwards arguments and signals, escalates termination after a grace period, and propagates exit status.

**Tech Stack:** Node.js 22+, TypeScript 5.9, jiti 2.7, Vitest 3.2, npm scripts.

## Global Constraints

- The normal command remains exactly `npm run test`.
- Vitest uses at most two workers and retains file parallelism.
- The suite deadline is 120 seconds; the kill grace period is 10 seconds; timeout exit status is 124.
- Tests continue after individual failures; do not enable `bail`.
- `npm run test -- <arguments>` forwards all arguments to Vitest.
- `npm run test:watch` remains intentionally long-lived.
- Do not modify the user's existing changes in `frontend/src/layouts/AdminLayout.vue` or `frontend/src/router/index.ts`.

---

## File Structure

- Create `frontend/scripts/test-process.ts` for deadline, signal, exit-code, and process-tree logic.
- Create `frontend/scripts/run-tests.ts` as the production Vitest launcher.
- Create `frontend/tests/test-process.spec.ts` for real subprocess tests.
- Create `frontend/tests/test-runtime-config.spec.ts` for the Vitest policy contract.
- Modify `frontend/vite.config.ts`, `frontend/package.json`, and `frontend/tsconfig.json`.
- Modify `README.md` and `README.zh-CN.md` to document run versus watch behavior.

---

### Task 1: Bound Vitest Concurrency and Operation Timeouts

**Files:**
- Create: `frontend/tests/test-runtime-config.spec.ts`
- Modify: `frontend/vite.config.ts:25-30`

**Interfaces:**
- Consumes: the existing default Vite/Vitest configuration export.
- Produces: `maxWorkers: 2`, `testTimeout: 5_000`, `hookTimeout: 10_000`, `teardownTimeout: 10_000`.

- [ ] **Step 1: Write the failing configuration test**

```ts
import { describe, expect, it } from 'vitest'

import viteConfig from '../vite.config'

describe('frontend test runtime policy', () => {
  it('bounds worker concurrency and per-operation timeouts', () => {
    expect(viteConfig).toMatchObject({
      test: {
        maxWorkers: 2,
        testTimeout: 5_000,
        hookTimeout: 10_000,
        teardownTimeout: 10_000,
      },
    })
  })
})
```

This test catches removal or accidental relaxation of the user-visible resource policy.

- [ ] **Step 2: Verify RED**

Run `cd frontend && npm exec vitest -- run tests/test-runtime-config.spec.ts --maxWorkers=1`.

Expected: FAIL because the current configuration omits all four fields.

- [ ] **Step 3: Implement the minimal configuration**

Add to the existing `test` object:

```ts
maxWorkers: 2,
testTimeout: 5_000,
hookTimeout: 10_000,
teardownTimeout: 10_000,
```

Do not add `minWorkers`, `fileParallelism`, or `bail`.

- [ ] **Step 4: Verify GREEN**

Run `npm exec vitest -- run tests/test-runtime-config.spec.ts --maxWorkers=1`.

Expected: one file and one test pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/vite.config.ts frontend/tests/test-runtime-config.spec.ts
git commit -m "test: bound frontend unit test resources"
```

---

### Task 2: Add the Whole-suite Process Guard

**Files:**
- Create: `frontend/scripts/test-process.ts`
- Create: `frontend/scripts/run-tests.ts`
- Create: `frontend/tests/test-process.spec.ts`
- Modify: `frontend/package.json:6-13`
- Modify: `frontend/tsconfig.json:20-34`

**Interfaces:**
- Produces: `runWithDeadline(options: RunWithDeadlineOptions): Promise<number>`.
- Options: `command`, `args`, `timeoutMs`, `killGraceMs`, optional `stdio`, optional `writeError`.
- The launcher passes local `vitest/vitest.mjs`, `run`, all user arguments, 120,000ms timeout, and 10,000ms grace.

- [ ] **Step 1: Write failing real-process tests**

Create `frontend/tests/test-process.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { runWithDeadline } from '../scripts/test-process'

const node = process.execPath

describe('test process deadline', () => {
  it('propagates a normal child exit code', async () => {
    const code = await runWithDeadline({
      command: node,
      args: ['-e', 'process.exit(7)'],
      timeoutMs: 2_000,
      killGraceMs: 100,
      stdio: 'ignore',
    })
    expect(code).toBe(7)
  })

  it('forwards command arguments unchanged', async () => {
    const code = await runWithDeadline({
      command: node,
      args: ['-e', "process.exit(process.argv[1] === 'sentinel' ? 0 : 9)", 'sentinel'],
      timeoutMs: 2_000,
      killGraceMs: 100,
      stdio: 'ignore',
    })
    expect(code).toBe(0)
  })

  it('force-terminates a child that exceeds its deadline', async () => {
    const errors: string[] = []
    const startedAt = Date.now()
    const code = await runWithDeadline({
      command: node,
      args: ['-e', "process.on('SIGTERM', () => {}); setInterval(() => {}, 1_000)"],
      timeoutMs: 100,
      killGraceMs: 100,
      stdio: 'ignore',
      writeError: (message) => errors.push(message),
    })
    expect(code).toBe(124)
    expect(Date.now() - startedAt).toBeLessThan(2_000)
    expect(errors.some((message) => message.includes('timed out'))).toBe(true)
  })

  it('returns nonzero when the child cannot start', async () => {
    const errors: string[] = []
    const code = await runWithDeadline({
      command: '/definitely/missing/frontend-test-command',
      args: [],
      timeoutMs: 2_000,
      killGraceMs: 100,
      stdio: 'ignore',
      writeError: (message) => errors.push(message),
    })
    expect(code).toBe(1)
    expect(errors.length).toBe(1)
  })
})
```

These tests exercise real child processes; do not mock `spawn`.

- [ ] **Step 2: Verify RED**

Run `cd frontend && npm exec vitest -- run tests/test-process.spec.ts --maxWorkers=1`.

Expected: FAIL because `../scripts/test-process` is not implemented. Confirm this is the intended missing feature, not a mistyped path.

- [ ] **Step 3: Implement `runWithDeadline`**

Create `frontend/scripts/test-process.ts` with this public API:

```ts
import { spawn, spawnSync, type StdioOptions } from 'node:child_process'
import { constants } from 'node:os'

export interface RunWithDeadlineOptions {
  command: string
  args: readonly string[]
  timeoutMs: number
  killGraceMs: number
  stdio?: StdioOptions
  writeError?: (message: string) => void
}

const forwardedSignals = ['SIGINT', 'SIGTERM'] as const

function signalExitCode(signal: NodeJS.Signals): number {
  return 128 + (constants.signals[signal] ?? 0)
}

export async function runWithDeadline(options: RunWithDeadlineOptions): Promise<number> {
  const writeError = options.writeError ?? ((message: string) => process.stderr.write(`${message}\n`))
  const child = spawn(options.command, [...options.args], {
    detached: process.platform !== 'win32',
    stdio: options.stdio ?? 'inherit',
  })

  return await new Promise<number>((resolve) => {
    let settled = false
    let timedOut = false
    let forwardedSignal: NodeJS.Signals | undefined
    let forceKillTimer: NodeJS.Timeout | undefined

    const signalTree = (signal: NodeJS.Signals): void => {
      if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return
      try {
        if (process.platform === 'win32' && signal === 'SIGKILL') {
          spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' })
        } else if (process.platform === 'win32') child.kill(signal)
        else process.kill(-child.pid, signal)
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error
      }
    }

    const scheduleForcedKill = (): void => {
      if (forceKillTimer !== undefined) return
      forceKillTimer = setTimeout(() => signalTree('SIGKILL'), options.killGraceMs)
    }

    const handlers = new Map<NodeJS.Signals, () => void>()
    for (const signal of forwardedSignals) {
      const handler = (): void => {
        forwardedSignal = signal
        signalTree(signal)
        scheduleForcedKill()
      }
      handlers.set(signal, handler)
      process.once(signal, handler)
    }

    const deadlineTimer = setTimeout(() => {
      timedOut = true
      writeError(`Frontend test suite timed out after ${options.timeoutMs}ms`)
      signalTree('SIGTERM')
      scheduleForcedKill()
    }, options.timeoutMs)

    const finish = (code: number): void => {
      if (settled) return
      settled = true
      clearTimeout(deadlineTimer)
      if (forceKillTimer !== undefined) clearTimeout(forceKillTimer)
      for (const [signal, handler] of handlers) process.removeListener(signal, handler)
      resolve(code)
    }

    child.once('error', (error) => {
      writeError(`Unable to start frontend tests: ${error.message}`)
      finish(1)
    })
    child.once('close', (code, signal) => {
      if (timedOut) finish(124)
      else if (forwardedSignal !== undefined) finish(signalExitCode(forwardedSignal))
      else if (code !== null) finish(code)
      else if (signal !== null) finish(signalExitCode(signal))
      else finish(1)
    })
  })
}
```

- [ ] **Step 4: Verify GREEN**

Run `npm exec vitest -- run tests/test-process.spec.ts --maxWorkers=1`.

Expected: four tests pass, including SIGTERM-to-SIGKILL escalation.

- [ ] **Step 5: Add the public launcher**

Create `frontend/scripts/run-tests.ts`:

```ts
import { createRequire } from 'node:module'

import { runWithDeadline } from './test-process'

const require = createRequire(import.meta.url)
const vitestCli = require.resolve('vitest/vitest.mjs')

process.exitCode = await runWithDeadline({
  command: process.execPath,
  args: [vitestCli, 'run', ...process.argv.slice(2)],
  timeoutMs: 120_000,
  killGraceMs: 10_000,
})
```

Change `frontend/package.json` to `"test": "jiti scripts/run-tests.ts"`. Add `scripts/**/*.ts` to `frontend/tsconfig.json`'s `include` list.

- [ ] **Step 6: Verify the public command and static checks**

Run:

```bash
npm run test -- --help
npm run typecheck
npm run lint
```

Expected: Vitest help proves argument forwarding; typecheck and lint exit zero unless an exact pre-existing failure is identified in the user's uncommitted files.

- [ ] **Step 7: Commit**

```bash
git add frontend/scripts/test-process.ts frontend/scripts/run-tests.ts frontend/tests/test-process.spec.ts frontend/package.json frontend/tsconfig.json
git commit -m "test: enforce frontend suite deadline"
```

---

### Task 3: Document the Safe Entry Point

**Files:**
- Modify: `README.md:400-425`
- Modify: `README.zh-CN.md:350-375`

**Interfaces:**
- Consumes: the npm command contract implemented above.
- Produces: a clear distinction between bounded run mode and persistent watch mode.

- [ ] **Step 1: Add English documentation**

After the quality-gate command block in `README.md`, add:

```md
`npm --prefix frontend run test` limits Vitest to two workers and terminates the whole unit-test run after 120 seconds. Use `npm --prefix frontend run test:watch` only for an intentionally persistent local watch session; stop it with Ctrl+C.
```

- [ ] **Step 2: Add Chinese documentation**

After the corresponding block in `README.zh-CN.md`, add:

```md
`npm --prefix frontend run test` 将 Vitest 限制为两个 worker，并在前端单元测试整套运行超过 120 秒时终止。仅在需要持续监听本地修改时使用 `npm --prefix frontend run test:watch`，并通过 Ctrl+C 停止。
```

- [ ] **Step 3: Verify and commit**

Run `git diff --check -- README.md README.zh-CN.md`, then:

```bash
git add README.md README.zh-CN.md
git commit -m "docs: document bounded frontend tests"
```

---

### Task 4: End-to-end Verification

**Files:**
- Verify only; do not modify unrelated application files to make checks green.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: fresh evidence for the policy, process guard, public command, and worktree ownership.

- [ ] **Step 1: Run focused regressions**

```bash
cd frontend
npm exec vitest -- run tests/test-runtime-config.spec.ts tests/test-process.spec.ts --maxWorkers=1
```

Expected: two files and five tests pass.

- [ ] **Step 2: Run static checks**

```bash
npm run typecheck
npm run lint
```

Expected: both exit zero, subject only to exact separately reported pre-existing failures.

- [ ] **Step 3: Run the public suite and sample its process bound**

Run `npm run test -- --reporter=dot`. While it runs, sample:

```bash
ps -eo rss=,args= | awk '$2 == "node" && $3 ~ /^\(vitest/ { rss += $1; count++ } END { print "vitest_processes=" count+0, "rss_mib=" int(rss/1024) }'
```

Expected: at most three Vitest-related Node processes: one coordinator and two workers. The command terminates by itself. Report actual suite counts because the current worktree has unrelated frontend changes and known baseline failures.

- [ ] **Step 4: Recheck forced termination without waiting 120 seconds**

Run:

```bash
npm exec vitest -- run tests/test-process.spec.ts -t "force-terminates" --maxWorkers=1
```

Expected: the child ignores SIGTERM, is force-killed after the injected 100ms grace period, and returns 124.

- [ ] **Step 5: Review ownership and final diffs**

```bash
git diff --check HEAD~3..HEAD
git status --short
git log -4 --oneline
```

Expected: implementation commits contain only planned files. The user's `AdminLayout.vue` and router changes remain uncommitted and untouched.

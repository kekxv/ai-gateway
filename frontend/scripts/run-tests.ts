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

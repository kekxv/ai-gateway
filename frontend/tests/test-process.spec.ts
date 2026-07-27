import { spawn, type ChildProcess } from 'node:child_process'
import { access, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { pathToFileURL } from 'node:url'

import { describe, expect, it } from 'vitest'

import { runWithDeadline } from '../scripts/test-process'

const node = process.execPath
const require = createRequire(import.meta.url)
const jitiCli = join(dirname(require.resolve('jiti/package.json')), 'lib', 'jiti-cli.mjs')
const testProcessModule = pathToFileURL(join(process.cwd(), 'scripts/test-process.ts')).href

function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM'
  }
}

async function waitForProcessExit(pid: number): Promise<void> {
  const deadline = Date.now() + 1_000
  while (processExists(pid) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
}

async function waitForFile(path: string): Promise<void> {
  const deadline = Date.now() + 1_000
  while (Date.now() < deadline) {
    try {
      await access(path)
      return
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
  throw new Error(`Timed out waiting for ${path}`)
}

async function waitForChildExit(
  child: ChildProcess,
  timeoutMs = 2_000,
): Promise<{ code: number | null; signal: NodeJS.Signals | null }> {
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('Timed out waiting for child exit'))
    }, timeoutMs)
    child.once('close', (code, signal) => {
      clearTimeout(timer)
      resolve({ code, signal })
    })
  })
}

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

  it.runIf(process.platform !== 'win32')(
    'waits through the grace period before force-terminating a ready child',
    async () => {
      const directory = await mkdtemp(join(tmpdir(), 'frontend-test-force-'))
      const readyFile = join(directory, 'ready')
      const errors: string[] = []
      const timeoutMs = 300
      const killGraceMs = 150
      const startedAt = Date.now()
      const result = runWithDeadline({
        command: node,
        args: [
          '-e',
          `
            const { writeFileSync } = require('node:fs')
            process.on('SIGTERM', () => {})
            writeFileSync(${JSON.stringify(readyFile)}, 'ready')
            setInterval(() => {}, 1_000)
          `,
        ],
        timeoutMs,
        killGraceMs,
        stdio: 'ignore',
        writeError: (message) => errors.push(message),
      })

      try {
        await waitForFile(readyFile)
        await expect(result).resolves.toBe(124)
        expect(Date.now() - startedAt).toBeGreaterThanOrEqual(timeoutMs + killGraceMs - 25)
        expect(errors.some((message) => message.includes('timed out'))).toBe(true)
      } finally {
        await result
        await rm(directory, { recursive: true, force: true })
      }
    },
  )

  it('returns nonzero when the child cannot start', async () => {
    const errors: string[] = []
    const initialSigintListeners = process.listenerCount('SIGINT')
    const initialSigtermListeners = process.listenerCount('SIGTERM')
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
    expect(process.listenerCount('SIGINT')).toBe(initialSigintListeners)
    expect(process.listenerCount('SIGTERM')).toBe(initialSigtermListeners)
  })

  it('removes parent signal listeners after a normal child exit', async () => {
    const initialSigintListeners = process.listenerCount('SIGINT')
    const initialSigtermListeners = process.listenerCount('SIGTERM')

    await runWithDeadline({
      command: node,
      args: ['-e', 'process.exit(0)'],
      timeoutMs: 2_000,
      killGraceMs: 100,
      stdio: 'ignore',
    })

    expect(process.listenerCount('SIGINT')).toBe(initialSigintListeners)
    expect(process.listenerCount('SIGTERM')).toBe(initialSigtermListeners)
  })

  it.runIf(process.platform !== 'win32')(
    'forwards SIGTERM and reports its shell-compatible exit code',
    async () => {
      const directory = await mkdtemp(join(tmpdir(), 'frontend-test-signal-'))
      const readyFile = join(directory, 'ready')
      const signalFile = join(directory, 'signal')
      const initialListeners = process.listenerCount('SIGTERM')
      const result = runWithDeadline({
        command: node,
        args: [
          '-e',
          `
            const { writeFileSync } = require('node:fs')
            process.on('SIGTERM', () => {
              writeFileSync(${JSON.stringify(signalFile)}, 'SIGTERM')
              process.exit(0)
            })
            writeFileSync(${JSON.stringify(readyFile)}, 'ready')
            setInterval(() => {}, 1_000)
          `,
        ],
        timeoutMs: 2_000,
        killGraceMs: 100,
        stdio: 'ignore',
      })

      try {
        await waitForFile(readyFile)
        expect(process.listenerCount('SIGTERM')).toBe(initialListeners + 1)
        process.emit('SIGTERM')

        await expect(result).resolves.toBe(143)
        await expect(readFile(signalFile, 'utf8')).resolves.toBe('SIGTERM')
        expect(process.listenerCount('SIGTERM')).toBe(initialListeners)
      } finally {
        if (process.listenerCount('SIGTERM') > initialListeners) process.emit('SIGTERM')
        await result
        await rm(directory, { recursive: true, force: true })
      }
    },
  )

  it.runIf(process.platform !== 'win32')(
    'force-kills descendants left behind when the process-group leader exits',
    async () => {
      const directory = await mkdtemp(join(tmpdir(), 'frontend-test-process-'))
      const pidFile = join(directory, 'descendant.pid')
      const descendantScript = "process.on('SIGTERM', () => {}); setInterval(() => {}, 1_000)"
      const leaderScript = `
        const { spawn } = require('node:child_process')
        const { writeFileSync } = require('node:fs')
        const descendant = spawn(process.execPath, ['-e', ${JSON.stringify(descendantScript)}], {
          stdio: 'ignore',
        })
        writeFileSync(${JSON.stringify(pidFile)}, String(descendant.pid))
        setInterval(() => {}, 1_000)
      `
      let descendantPid: number | undefined

      try {
        const code = await runWithDeadline({
          command: node,
          args: ['-e', leaderScript],
          timeoutMs: 500,
          killGraceMs: 100,
          stdio: 'ignore',
          writeError: () => undefined,
        })
        descendantPid = Number(await readFile(pidFile, 'utf8'))
        await waitForProcessExit(descendantPid)

        expect(code).toBe(124)
        expect(processExists(descendantPid)).toBe(false)
      } finally {
        if (descendantPid !== undefined && processExists(descendantPid)) {
          process.kill(descendantPid, 'SIGKILL')
        }
        await rm(directory, { recursive: true, force: true })
      }
    },
  )

  it.runIf(process.platform !== 'win32')(
    'keeps intercepting repeated SIGTERM until descendant cleanup completes',
    async () => {
      const directory = await mkdtemp(join(tmpdir(), 'frontend-test-wrapper-'))
      const wrapperFile = join(directory, 'wrapper.ts')
      const readyFile = join(directory, 'descendant.ready')
      const descendantPidFile = join(directory, 'descendant.pid')
      const resultFile = join(directory, 'result')
      const descendantScript = `
        const { writeFileSync } = require('node:fs')
        process.on('SIGTERM', () => {})
        writeFileSync(${JSON.stringify(readyFile)}, 'ready')
        setInterval(() => {}, 1_000)
      `
      const leaderScript = `
        const { spawn } = require('node:child_process')
        const { writeFileSync } = require('node:fs')
        const descendant = spawn(process.execPath, ['-e', ${JSON.stringify(descendantScript)}], {
          stdio: 'ignore',
        })
        writeFileSync(${JSON.stringify(descendantPidFile)}, String(descendant.pid))
        setInterval(() => {}, 1_000)
      `
      const wrapperScript = `
        import { writeFileSync } from 'node:fs'
        import { runWithDeadline } from ${JSON.stringify(testProcessModule)}

        const code = await runWithDeadline({
          command: process.execPath,
          args: ['-e', ${JSON.stringify(leaderScript)}],
          timeoutMs: 10_000,
          killGraceMs: 200,
          stdio: 'ignore',
        })
        writeFileSync(${JSON.stringify(resultFile)}, String(code))
      `
      let descendantPid: number | undefined
      let wrapper: ChildProcess | undefined

      try {
        await writeFile(wrapperFile, wrapperScript)
        wrapper = spawn(node, [jitiCli, wrapperFile], { stdio: 'ignore' })
        const wrapperExit = waitForChildExit(wrapper)
        await waitForFile(readyFile)
        descendantPid = Number(await readFile(descendantPidFile, 'utf8'))

        wrapper.kill('SIGTERM')
        await new Promise((resolve) => setTimeout(resolve, 50))
        wrapper.kill('SIGTERM')

        await expect(wrapperExit).resolves.toEqual({ code: 0, signal: null })
        await expect(readFile(resultFile, 'utf8')).resolves.toBe('143')
        await waitForProcessExit(descendantPid)
        expect(processExists(descendantPid)).toBe(false)
      } finally {
        if (wrapper?.pid !== undefined && processExists(wrapper.pid)) {
          process.kill(wrapper.pid, 'SIGKILL')
        }
        if (descendantPid !== undefined && processExists(descendantPid)) {
          process.kill(descendantPid, 'SIGKILL')
        }
        await rm(directory, { recursive: true, force: true })
      }
    },
  )
})

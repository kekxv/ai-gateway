import { access, mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { runWithDeadline } from '../scripts/test-process'

const node = process.execPath

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

  it('forwards SIGTERM and reports its shell-compatible exit code', async () => {
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
  })

  it('force-kills descendants left behind when the process-group leader exits', async () => {
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
  })
})

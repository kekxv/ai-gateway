import { spawn, spawnSync, type ChildProcess, type StdioOptions } from 'node:child_process'
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
  return 128 + constants.signals[signal]
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export async function runWithDeadline(options: RunWithDeadlineOptions): Promise<number> {
  const writeError =
    options.writeError ?? ((message: string) => process.stderr.write(`${message}\n`))
  let child: ChildProcess

  try {
    child = spawn(options.command, [...options.args], {
      detached: process.platform !== 'win32',
      stdio: options.stdio ?? 'inherit',
    })
  } catch (error) {
    writeError(`Unable to start frontend tests: ${describeError(error)}`)
    return 1
  }

  return await new Promise<number>((resolve) => {
    let settled = false
    let timedOut = false
    let forwardedSignal: NodeJS.Signals | undefined
    let forceKillTimer: NodeJS.Timeout | undefined

    const completionCode = (): number =>
      timedOut ? 124 : signalExitCode(forwardedSignal ?? 'SIGTERM')

    const processGroupExists = (): boolean => {
      if (child.pid === undefined) return false
      if (process.platform === 'win32') {
        return child.exitCode === null && child.signalCode === null
      }
      try {
        process.kill(-child.pid, 0)
        return true
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code
        if (code === 'ESRCH') return false
        return code === 'EPERM'
      }
    }

    const signalTree = (signal: NodeJS.Signals): void => {
      if (child.pid === undefined) return
      try {
        if (process.platform === 'win32' && signal === 'SIGKILL') {
          spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' })
        } else if (process.platform === 'win32') {
          if (child.exitCode === null && child.signalCode === null) child.kill(signal)
        } else {
          process.kill(-child.pid, signal)
        }
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error
      }
    }

    const handlers = new Map<NodeJS.Signals, () => void>()
    const deadlineTimer = setTimeout(() => {
      timedOut = true
      writeError(`Frontend test suite timed out after ${String(options.timeoutMs)}ms`)
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

    const scheduleForcedKill = (): void => {
      if (forceKillTimer !== undefined) return
      forceKillTimer = setTimeout(() => {
        signalTree('SIGKILL')
        finish(completionCode())
      }, options.killGraceMs)
    }

    for (const signal of forwardedSignals) {
      const handler = (): void => {
        if (forwardedSignal === undefined) forwardedSignal = signal
        clearTimeout(deadlineTimer)
        signalTree(signal)
        scheduleForcedKill()
      }
      handlers.set(signal, handler)
      process.once(signal, handler)
    }

    child.once('error', (error) => {
      writeError(`Unable to start frontend tests: ${error.message}`)
      finish(1)
    })
    child.once('close', (code, signal) => {
      if (timedOut || forwardedSignal !== undefined) {
        if (!processGroupExists()) finish(completionCode())
      } else if (code !== null) finish(code)
      else if (signal !== null) finish(signalExitCode(signal))
      else finish(1)
    })
  })
}

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
    let windowsTreeTerminationSucceeded = false

    const completionCode = (): number =>
      timedOut ? 124 : signalExitCode(forwardedSignal ?? 'SIGTERM')

    const posixProcessGroupExists = (): boolean => {
      if (child.pid === undefined) return false
      try {
        process.kill(-child.pid, 0)
        return true
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code
        if (code === 'ESRCH') return false
        return true
      }
    }

    const terminateWindowsTree = (force: boolean): boolean => {
      if (child.pid === undefined) return false
      const args = ['/pid', String(child.pid), '/t']
      if (force) args.push('/f')
      const result = spawnSync('taskkill', args, { stdio: 'ignore' })
      if (result.error !== undefined) {
        writeError(`Unable to terminate frontend test process tree: ${result.error.message}`)
        return false
      }
      if (result.status !== 0) {
        writeError(
          `Unable to terminate frontend test process tree: taskkill exited with status ${String(result.status)}`,
        )
        return false
      }
      return true
    }

    const signalTree = (signal: NodeJS.Signals): boolean => {
      if (child.pid === undefined) return false
      if (process.platform === 'win32') {
        return terminateWindowsTree(signal === 'SIGKILL')
      }
      try {
        process.kill(-child.pid, signal)
        return true
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ESRCH') return false
        throw error
      }
    }

    const handlers = new Map<NodeJS.Signals, () => void>()
    const deadlineTimer = setTimeout(() => {
      timedOut = true
      writeError(`Frontend test suite timed out after ${String(options.timeoutMs)}ms`)
      windowsTreeTerminationSucceeded = signalTree('SIGTERM')
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
        const treeKilled = signalTree('SIGKILL')
        if (
          process.platform === 'win32' &&
          !treeKilled &&
          child.exitCode === null &&
          child.signalCode === null
        ) {
          try {
            if (!child.kill('SIGKILL')) {
              writeError('Unable to force-terminate the frontend test process')
            }
          } catch (error) {
            writeError(`Unable to force-terminate the frontend test process: ${describeError(error)}`)
          }
        }
        finish(completionCode())
      }, options.killGraceMs)
    }

    for (const signal of forwardedSignals) {
      const handler = (): void => {
        if (timedOut || forwardedSignal !== undefined) return
        forwardedSignal = signal
        clearTimeout(deadlineTimer)
        windowsTreeTerminationSucceeded = signalTree(signal)
        scheduleForcedKill()
      }
      handlers.set(signal, handler)
      process.on(signal, handler)
    }

    child.once('error', (error) => {
      writeError(`Unable to start frontend tests: ${error.message}`)
      finish(1)
    })
    child.once('close', (code, signal) => {
      if (timedOut || forwardedSignal !== undefined) {
        if (process.platform === 'win32') {
          if (windowsTreeTerminationSucceeded) finish(completionCode())
        } else if (!posixProcessGroupExists()) finish(completionCode())
      } else if (code !== null) finish(code)
      else if (signal !== null) finish(signalExitCode(signal))
      else finish(1)
    })
  })
}

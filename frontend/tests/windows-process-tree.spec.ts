// @vitest-environment node

import { describe, expect, it } from 'vitest'

import {
  createWindowsProcessTreeController,
  parseWindowsProcessSnapshot,
  selectRetainedForceTargets,
  type WindowsCommandResult,
  type WindowsCommandRunner,
} from '../scripts/windows-process-tree'

Object.defineProperty(globalThis, 'sessionStorage', {
  configurable: true,
  value: { clear: () => undefined },
})

function snapshot(
  rows: ReadonlyArray<readonly [pid: number, parentPid: number, creationId: string]>,
): string {
  return rows.map((row) => row.join(',')).join('\r\n')
}

function createRunner(
  snapshots: string[],
  taskkillStatuses: number[] = [],
): { calls: Array<readonly [string, readonly string[]]>; run: WindowsCommandRunner } {
  const calls: Array<readonly [string, readonly string[]]> = []
  const run = (command: string, args: readonly string[]): WindowsCommandResult => {
    calls.push([command, args])
    if (command === 'powershell.exe') {
      return { status: 0, stdout: snapshots.shift() ?? '' }
    }
    return { status: taskkillStatuses.shift() ?? 0, stdout: '' }
  }
  return { calls, run }
}

const initialSnapshot = snapshot([
  [100, 1, 'root-created'],
  [110, 100, 'child-created'],
  [120, 110, 'grandchild-created'],
  [130, 100, 'sibling-created'],
  [900, 1, 'unrelated-created'],
])

describe('Windows process-tree ownership', () => {
  it('targets surviving retained branches after the original root exits', () => {
    const retained = parseWindowsProcessSnapshot(initialSnapshot)
    const current = parseWindowsProcessSnapshot(
      snapshot([
        [110, 1, 'reused-pid'],
        [120, 4, 'grandchild-created'],
        [130, 4, 'sibling-created'],
        [900, 1, 'unrelated-created'],
      ]),
    )

    expect(selectRetainedForceTargets(retained, current, 100)).toEqual([
      { pid: 120, parentPid: 110, creationId: 'grandchild-created' },
      { pid: 130, parentPid: 100, creationId: 'sibling-created' },
    ])
  })

  it('targets only the highest surviving retained ancestor', () => {
    const retained = parseWindowsProcessSnapshot(initialSnapshot)
    const current = parseWindowsProcessSnapshot(
      snapshot([
        [110, 4, 'child-created'],
        [120, 110, 'grandchild-created'],
      ]),
    )

    expect(selectRetainedForceTargets(retained, current, 100)).toEqual([
      { pid: 110, parentPid: 100, creationId: 'child-created' },
    ])
  })

  it('force-kills retained descendants even after the root PID disappears', () => {
    const currentSnapshot = snapshot([
      [120, 4, 'grandchild-created'],
      [130, 4, 'sibling-created'],
      [900, 1, 'unrelated-created'],
    ])
    const { calls, run } = createRunner(
      [initialSnapshot, currentSnapshot, currentSnapshot],
      [1, 0, 0],
    )
    const errors: string[] = []
    const controller = createWindowsProcessTreeController({
      rootPid: 100,
      runCommand: run,
      writeError: (message) => errors.push(message),
    })

    expect(controller.beginGracefulTermination()).toBe(false)
    expect(controller.hasLiveRetainedProcesses()).toBe(true)
    expect(controller.forceTerminate(false)).toBe(true)
    expect(calls.slice(0, 2).map(([command]) => command)).toEqual([
      'powershell.exe',
      'taskkill',
    ])
    expect(calls.filter(([command]) => command === 'taskkill')).toEqual([
      ['taskkill', ['/pid', '100', '/t']],
      ['taskkill', ['/pid', '120', '/t', '/f']],
      ['taskkill', ['/pid', '130', '/t', '/f']],
    ])
    expect(errors).toEqual([
      'Unable to terminate Windows process tree rooted at PID 100: taskkill exited with status 1',
    ])
  })

  it('does not kill an unverified PID when discovery fails after the root exits', () => {
    const calls: Array<readonly [string, readonly string[]]> = []
    const errors: string[] = []
    const run: WindowsCommandRunner = (command, args) => {
      calls.push([command, args])
      if (command === 'powershell.exe') return { status: 1, stdout: '' }
      return { status: 1, stdout: '' }
    }
    const controller = createWindowsProcessTreeController({
      rootPid: 100,
      runCommand: run,
      writeError: (message) => errors.push(message),
    })

    controller.beginGracefulTermination()
    expect(controller.forceTerminate(false)).toBe(false)
    expect(calls.filter(([command]) => command === 'taskkill')).toEqual([
      ['taskkill', ['/pid', '100', '/t']],
    ])
    expect(errors.some((message) => message.includes('snapshot command exited with status 1'))).toBe(
      true,
    )
    expect(errors.some((message) => message.includes('no verified process remains'))).toBe(true)
  })

  it('falls back to the still-live root when escalation discovery fails', () => {
    const calls: Array<readonly [string, readonly string[]]> = []
    const run: WindowsCommandRunner = (command, args) => {
      calls.push([command, args])
      if (command === 'powershell.exe') return { status: 1, stdout: '' }
      return { status: args.includes('/f') ? 0 : 1, stdout: '' }
    }
    const controller = createWindowsProcessTreeController({
      rootPid: 100,
      runCommand: run,
      writeError: () => undefined,
    })

    controller.beginGracefulTermination()
    expect(controller.forceTerminate(true)).toBe(true)
    expect(calls.filter(([command]) => command === 'taskkill')).toEqual([
      ['taskkill', ['/pid', '100', '/t']],
      ['taskkill', ['/pid', '100', '/t', '/f']],
    ])
  })
})

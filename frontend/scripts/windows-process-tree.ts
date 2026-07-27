import { spawnSync } from 'node:child_process'

export interface WindowsProcessIdentity {
  pid: number
  parentPid: number
  creationId: string
}

export interface WindowsCommandResult {
  status: number | null
  stdout: string
  error?: Error
}

export type WindowsCommandRunner = (
  command: string,
  args: readonly string[],
) => WindowsCommandResult

export interface WindowsProcessTreeController {
  beginGracefulTermination(): boolean
  hasLiveRetainedProcesses(): boolean
  forceTerminate(rootIsAlive: boolean): boolean
}

interface WindowsProcessTreeControllerOptions {
  rootPid: number
  writeError: (message: string) => void
  runCommand?: WindowsCommandRunner
}

const snapshotScript = [
  "$ErrorActionPreference = 'Stop'",
  "Get-CimInstance Win32_Process -ErrorAction Stop | ForEach-Object { if ($null -ne $_.CreationDate) { '{0},{1},{2}' -f $_.ProcessId, $_.ParentProcessId, $_.CreationDate.ToUniversalTime().Ticks } }",
].join('; ')

const defaultCommandRunner: WindowsCommandRunner = (command, args) => {
  const result = spawnSync(command, [...args], {
    encoding: 'utf8',
    windowsHide: true,
  })
  const base = {
    status: result.status,
    stdout: result.stdout,
  }
  return result.error === undefined ? base : { ...base, error: result.error }
}

export function parseWindowsProcessSnapshot(output: string): WindowsProcessIdentity[] {
  const trimmed = output.trim()
  if (trimmed.length === 0) return []

  const processes: WindowsProcessIdentity[] = []
  const seenPids = new Set<number>()
  for (const rawLine of trimmed.split(/\r?\n/u)) {
    const parts = rawLine.trim().split(',')
    if (parts.length !== 3) throw new Error(`Invalid Windows process snapshot row: ${rawLine}`)
    const [pidText, parentPidText, creationId] = parts
    const pid = Number(pidText)
    const parentPid = Number(parentPidText)
    if (
      !Number.isSafeInteger(pid) ||
      pid <= 0 ||
      !Number.isSafeInteger(parentPid) ||
      parentPid < 0 ||
      creationId === undefined ||
      creationId.length === 0 ||
      seenPids.has(pid)
    ) {
      throw new Error(`Invalid Windows process snapshot row: ${rawLine}`)
    }
    seenPids.add(pid)
    processes.push({ pid, parentPid, creationId })
  }
  return processes
}

function selectProcessTree(
  snapshot: readonly WindowsProcessIdentity[],
  rootPid: number,
): WindowsProcessIdentity[] {
  const byPid = new Map(snapshot.map((process) => [process.pid, process]))
  if (!byPid.has(rootPid)) return []

  const children = new Map<number, WindowsProcessIdentity[]>()
  for (const process of snapshot) {
    const siblings = children.get(process.parentPid) ?? []
    siblings.push(process)
    children.set(process.parentPid, siblings)
  }

  const tree: WindowsProcessIdentity[] = []
  const pending = [rootPid]
  const visited = new Set<number>()
  while (pending.length > 0) {
    const pid = pending.shift()
    if (pid === undefined || visited.has(pid)) continue
    visited.add(pid)
    const process = byPid.get(pid)
    if (process === undefined) continue
    tree.push(process)
    for (const child of children.get(pid) ?? []) pending.push(child.pid)
  }
  return tree
}

export function selectRetainedForceTargets(
  retainedSnapshot: readonly WindowsProcessIdentity[],
  currentSnapshot: readonly WindowsProcessIdentity[],
  rootPid: number,
): WindowsProcessIdentity[] {
  const retained = selectProcessTree(retainedSnapshot, rootPid)
  const retainedByPid = new Map(retained.map((process) => [process.pid, process]))
  const currentByPid = new Map(currentSnapshot.map((process) => [process.pid, process]))
  const alive = new Set(
    retained
      .filter(
        (process) => currentByPid.get(process.pid)?.creationId === process.creationId,
      )
      .map((process) => process.pid),
  )

  const targets = retained.filter((process) => {
    if (!alive.has(process.pid)) return false
    const visited = new Set<number>()
    let parentPid = process.parentPid
    while (!visited.has(parentPid)) {
      visited.add(parentPid)
      const parent = retainedByPid.get(parentPid)
      if (parent === undefined) return true
      if (alive.has(parentPid)) return false
      parentPid = parent.parentPid
    }
    return true
  })
  return targets.sort((left, right) => left.pid - right.pid)
}

export function createWindowsProcessTreeController(
  options: WindowsProcessTreeControllerOptions,
): WindowsProcessTreeController {
  const runCommand = options.runCommand ?? defaultCommandRunner
  let retainedSnapshot: WindowsProcessIdentity[] = []

  const discoverProcesses = (): WindowsProcessIdentity[] | undefined => {
    const result = runCommand('powershell.exe', [
      '-NoLogo',
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      snapshotScript,
    ])
    if (result.error !== undefined) {
      options.writeError(`Unable to snapshot Windows process tree: ${result.error.message}`)
      return undefined
    }
    if (result.status !== 0) {
      options.writeError(
        `Unable to snapshot Windows process tree: snapshot command exited with status ${String(result.status)}`,
      )
      return undefined
    }
    try {
      return parseWindowsProcessSnapshot(result.stdout)
    } catch (error) {
      options.writeError(`Unable to snapshot Windows process tree: ${String(error)}`)
      return undefined
    }
  }

  const terminateTree = (pid: number, force: boolean): boolean => {
    const args = ['/pid', String(pid), '/t']
    if (force) args.push('/f')
    const result = runCommand('taskkill', args)
    const prefix = `Unable to terminate Windows process tree rooted at PID ${String(pid)}`
    if (result.error !== undefined) {
      options.writeError(`${prefix}: ${result.error.message}`)
      return false
    }
    if (result.status !== 0) {
      options.writeError(`${prefix}: taskkill exited with status ${String(result.status)}`)
      return false
    }
    return true
  }

  return {
    beginGracefulTermination(): boolean {
      const processes = discoverProcesses()
      if (processes !== undefined) {
        retainedSnapshot = selectProcessTree(processes, options.rootPid)
        if (retainedSnapshot.length === 0) {
          options.writeError(
            `Unable to retain Windows process tree ownership: root PID ${String(options.rootPid)} was absent from the snapshot`,
          )
        }
      }
      return terminateTree(options.rootPid, false)
    },

    hasLiveRetainedProcesses(): boolean {
      if (retainedSnapshot.length === 0) return true
      const processes = discoverProcesses()
      if (processes === undefined) return true
      return selectRetainedForceTargets(retainedSnapshot, processes, options.rootPid).length > 0
    },

    forceTerminate(rootIsAlive: boolean): boolean {
      const processes = discoverProcesses()
      if (processes !== undefined && retainedSnapshot.length > 0) {
        const targets = selectRetainedForceTargets(
          retainedSnapshot,
          processes,
          options.rootPid,
        )
        if (targets.length > 0) {
          let succeeded = true
          for (const target of targets) {
            if (!terminateTree(target.pid, true)) succeeded = false
          }
          return succeeded
        }
        if (!rootIsAlive) return true
      }

      if (rootIsAlive) return terminateTree(options.rootPid, true)
      options.writeError(
        `Unable to force-terminate Windows process tree safely: no verified process remains after root PID ${String(options.rootPid)} exited`,
      )
      return false
    },
  }
}

const CONTEXT_KEY = 'tbs.contextCollapsed'
const SIDE_KEY = 'tbs.sideCollapsed'

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = sessionStorage.getItem(key)
    if (raw === null) return fallback
    return raw === '1'
  } catch {
    return fallback
  }
}

function writeBool(key: string, value: boolean): void {
  try {
    sessionStorage.setItem(key, value ? '1' : '0')
  } catch {
    // private mode — ignore
  }
}

export function readContextCollapsed(): boolean {
  return readBool(CONTEXT_KEY, false)
}

export function writeContextCollapsed(value: boolean): void {
  writeBool(CONTEXT_KEY, value)
}

export function readSideCollapsed(): boolean {
  return readBool(SIDE_KEY, false)
}

export function writeSideCollapsed(value: boolean): void {
  writeBool(SIDE_KEY, value)
}

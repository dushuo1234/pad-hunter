export interface Notice {
  id: number
  text: string
}

const EMPTY: Notice[] = []
let notices: Notice[] = EMPTY
let seq = 0
const listeners = new Set<() => void>()

export function getNotices(): Notice[] {
  return notices
}

export function getServerNotices(): Notice[] {
  return EMPTY
}

export function subscribeNotices(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function pushNotice(text: string): number {
  const id = ++seq
  notices = [...notices, { id, text }].slice(-3)
  for (const listener of listeners) listener()
  return id
}

export function dismissNotice(id: number): void {
  const next = notices.filter((notice) => notice.id !== id)
  if (next.length === notices.length) return
  notices = next.length > 0 ? next : EMPTY
  for (const listener of listeners) listener()
}

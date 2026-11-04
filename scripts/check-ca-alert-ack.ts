/**
 * CA sound alert ("姐姐，微信来啦") per-project acknowledgement:
 * once the user clicks a project's toast (or opens its detail), that
 * project must never alert again — even for brand new addresses —
 * while other projects keep alerting normally.
 */

// Browser shims must exist before the module under test loads.
const store = new Map<string, string>()
;(globalThis as Record<string, unknown>).localStorage = {
  getItem: (k: string) => (store.has(k) ? store.get(k) : null),
  setItem: (k: string, v: string) => void store.set(k, String(v)),
  removeItem: (k: string) => void store.delete(k),
}
;(globalThis as Record<string, unknown>).window = {
  setTimeout: () => 0,
  clearTimeout: () => undefined,
  setInterval: () => 0,
  clearInterval: () => undefined,
  matchMedia: () => ({ matches: false, addEventListener: () => undefined }),
}
;(globalThis as Record<string, unknown>).Audio = class {
  muted = false
  volume = 1
  currentTime = 0
  preload = ''
  play() {
    return Promise.resolve()
  }
  pause() {}
}

function fail(message: string): never {
  throw new Error(message)
}

const {
  ackCaProject,
  ackToast,
  dismissToast,
  getAlertUi,
  isCaProjectAcked,
  observeSightings,
  sightingProjectKey,
} = await import('../src/utils/caAlert.ts')

const addr = (n: number) => `0x${String(n).padStart(40, '0')}`
const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

// Key rules: handle wins; display name is the normalized fallback.
if (sightingProjectKey({ handle: '@ProjX', project: 'Whatever' }) !== 'h:projx') fail('handle key wrong')
if (sightingProjectKey({ project: '  ProjY ' }) !== 'p:projy') fail('name key wrong')

const x1 = { address: addr(1), project: 'ProjX', handle: 'projx' }
const x2 = { address: addr(2), project: 'ProjX', handle: 'projx' }
const x3 = { address: addr(3), project: 'ProjX', handle: 'projx' }
const y1 = { address: addr(11), project: 'ProjY', handle: 'projy' }
const y2 = { address: addr(12), project: 'ProjY', handle: 'projy' }

// First read baselines silently.
observeSightings('ca', [x1])
await tick()
if (getAlertUi().toasts.length !== 0) fail('baseline should stay quiet')

// A new address for X alerts once.
observeSightings('ca', [x1, x2])
await tick()
const toasts = getAlertUi().toasts
if (toasts.length !== 1) fail(`expected 1 toast, got ${toasts.length}`)
if (toasts[0].projectKey !== 'h:projx') fail(`toast key ${toasts[0].projectKey}`)

// Clicking the toast (close button) acknowledges the whole project.
ackToast(toasts[0].id)
if (getAlertUi().toasts.length !== 0) fail('ackToast should dismiss the toast')
if (!isCaProjectAcked(x3)) fail('project X should be acked after toast click')
const persisted = JSON.parse(store.get('pad-hunter.ca-alert.seen.v1') ?? '{}') as { acked?: string[] }
if (!persisted.acked?.includes('h:projx')) fail('ack not persisted to localStorage')

// A brand new address for the acked project stays silent — the bug.
observeSightings('ca', [x1, x2, x3])
await tick()
if (getAlertUi().toasts.length !== 0) fail('acked project alerted again for a new address')

// Other projects still alert.
observeSightings('ca', [y1])
await tick()
if (getAlertUi().toasts.length !== 1) fail('unacked project should still alert')
dismissToast(getAlertUi().toasts[0].id)

// The detail-open path (ackCaProject) silences future addresses too.
ackCaProject('projy', 'ProjY')
observeSightings('ca', [y1, y2])
await tick()
if (getAlertUi().toasts.length !== 0) fail('detail-acked project alerted again')

console.log('check-ca-alert-ack: ok')

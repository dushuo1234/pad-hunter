import {
  FALLBACK_WORKBENCH_API_BASE,
  isRetiredWorkbenchApiBase,
  migratedWorkbenchApiBase,
} from '../src/utils/apiBase.ts'

function fail(message: string): never {
  throw new Error(message)
}

if (FALLBACK_WORKBENCH_API_BASE !== 'https://api.adualpha.win') fail('fallback base')

const retired = [
  'https://dotted-disengage-awoke.ngrok-free.dev',
  'https://dotted-disengage-awoke.ngrok-free.dev/',
  'http://dotted-disengage-awoke.ngrok-free.dev/pad',
  'https://DOTTED-DISENGAGE-AWOKE.ngrok-free.dev',
]
for (const base of retired) {
  if (!isRetiredWorkbenchApiBase(base)) fail(`should retire ${base}`)
  if (migratedWorkbenchApiBase(base) !== FALLBACK_WORKBENCH_API_BASE) fail(`migrate ${base}`)
}

const kept = ['', 'https://api.adualpha.win', 'https://example.com/api', 'not a url']
for (const base of kept) {
  if (isRetiredWorkbenchApiBase(base)) fail(`should keep ${base}`)
  if (migratedWorkbenchApiBase(base) !== base) fail(`unchanged ${base}`)
}

console.log('api base checks ok')

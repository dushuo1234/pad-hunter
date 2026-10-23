/** Built-in workbench API when the settings field and VITE_WORKBENCH_API_BASE are empty. */
export const FALLBACK_WORKBENCH_API_BASE = 'https://api.adualpha.win'

/** Previous tunnel. Bandwidth-capped; saved settings that still point here move to the fallback. */
export const RETIRED_WORKBENCH_API_HOST = 'dotted-disengage-awoke.ngrok-free.dev'

export function isRetiredWorkbenchApiBase(baseUrl: string): boolean {
  const trimmed = baseUrl.trim()
  if (!trimmed) return false
  try {
    return new URL(trimmed).hostname.toLowerCase() === RETIRED_WORKBENCH_API_HOST
  } catch {
    return trimmed.toLowerCase().includes(RETIRED_WORKBENCH_API_HOST)
  }
}

/** Saved ngrok bases become the current fallback. Any other value is returned unchanged. */
export function migratedWorkbenchApiBase(baseUrl: string): string {
  return isRetiredWorkbenchApiBase(baseUrl) ? FALLBACK_WORKBENCH_API_BASE : baseUrl
}

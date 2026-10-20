import { useEffect, useState } from 'react'

export type AppRoute =
  | { name: 'home' }
  | { name: 'today' }
  | { name: 'ca' }
  | { name: 'launched' }
  | { name: 'workbench' }
  | { name: 'monitor'; handle: string }
  | { name: 'notfound' }

export function appPath(subpath = ''): string {
  const base = import.meta.env.BASE_URL || '/'
  const tail = subpath.replace(/^\//, '')
  if (!tail) return base
  return `${base}${tail}`
}

export function monitorPath(handle: string): string {
  return appPath(`monitor/${encodeURIComponent(handle)}`)
}

export function stripBase(pathname: string): string {
  let base = import.meta.env.BASE_URL || '/'
  if (base.endsWith('/')) base = base.slice(0, -1)
  let path = pathname || '/'
  if (base && (path === base || path.startsWith(`${base}/`))) {
    path = path.slice(base.length) || '/'
  }
  if (!path.startsWith('/')) path = `/${path}`
  if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1)
  return path
}

export function parseRoute(pathname: string): AppRoute {
  const path = stripBase(pathname)
  if (path === '/') return { name: 'home' }
  if (path === '/today') return { name: 'today' }
  if (path === '/ca') return { name: 'ca' }
  if (path === '/launched') return { name: 'launched' }
  if (path === '/workbench') return { name: 'workbench' }
  const match = /^\/monitor\/([^/]+)$/.exec(path)
  if (!match) return { name: 'notfound' }
  try {
    return { name: 'monitor', handle: decodeURIComponent(match[1]) }
  } catch {
    return { name: 'monitor', handle: match[1] }
  }
}

function isAppPath(pathname: string): boolean {
  const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '')
  return pathname === base || pathname.startsWith(`${base}/`)
}

export function useRoute(): AppRoute {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute(window.location.pathname))

  useEffect(() => {
    const sync = () => setRoute(parseRoute(window.location.pathname))
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const target = event.target
      if (!(target instanceof Element)) return
      const anchor = target.closest('a')
      if (!anchor) return
      if (anchor.target && anchor.target !== '_self') return
      const href = anchor.getAttribute('href')
      if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return
      let url: URL
      try {
        url = new URL(href, window.location.href)
      } catch {
        return
      }
      if (url.origin !== window.location.origin || !isAppPath(url.pathname)) return
      event.preventDefault()
      const next = `${url.pathname}${url.search}${url.hash}`
      const current = `${window.location.pathname}${window.location.search}${window.location.hash}`
      if (next !== current) window.history.pushState({}, '', next)
      setRoute(parseRoute(url.pathname))
      window.scrollTo(0, 0)
    }
    window.addEventListener('popstate', sync)
    document.addEventListener('click', onClick)
    return () => {
      window.removeEventListener('popstate', sync)
      document.removeEventListener('click', onClick)
    }
  }, [])

  return route
}

import { useEffect, useMemo } from 'react'
import { CaAlertToasts } from './components/CaAlert'
import { Header } from './components/Header'
import { useCaAlertWatcher } from './hooks/useCaAlertWatcher'
import { usePadData } from './hooks/usePadData'
import { useTheme } from './hooks/useTheme'
import { CaPage } from './pages/CaPage'
import { HomePage } from './pages/HomePage'
import { LaunchedPage } from './pages/LaunchedPage'
import { MonitorPage } from './pages/MonitorPage'
import { TodayPage } from './pages/TodayPage'
import { WorkbenchPage } from './pages/WorkbenchPage'
import { setBaseDocumentTitle } from './utils/caAlert'
import { countUpcoming } from './utils/launch'
import { appPath, useRoute } from './router'

export default function App() {
  const { theme, toggle } = useTheme()
  const route = useRoute()
  const data = usePadData()
  useCaAlertWatcher()
  const todayCount = useMemo(
    () =>
      data.loading && data.candidates.length === 0
        ? null
        : countUpcoming(data.candidates, data.events, data.listingTimes),
    [data.candidates, data.events, data.listingTimes, data.loading],
  )

  useEffect(() => {
    const titles: Record<typeof route.name, string> = {
      home: '台子雷达 · 项目推送',
      today: '即将开盘 · 台子雷达',
      ca: '发现CA · 台子雷达',
      launched: '已开盘 · 台子雷达',
      workbench: '工作台 · 台子雷达',
      monitor: '监控详情 · 台子雷达',
      notfound: '未找到 · 台子雷达',
    }
    setBaseDocumentTitle(titles[route.name])
  }, [route.name])

  return (
    <div className="min-h-screen bg-[var(--color-cream)] text-[var(--color-ink)] dark:bg-[var(--color-night)] dark:text-[var(--color-night-ink)]">
      <Header
        theme={theme}
        route={route}
        todayCount={todayCount}
        launchedCount={data.loading && data.launched.items.length === 0 ? null : data.launched.count}
        onToggleTheme={toggle}
        onUpload={(file) => void data.handleUpload(file)}
        onRefresh={() => void data.loadDefault()}
      />

      {route.name === 'home' && (
        <HomePage
          key={data.uploadNote ?? 'site'}
          payload={data.payload}
          candidates={data.candidates}
          loading={data.loading}
          error={data.error}
          uploadNote={data.uploadNote}
          onRetry={() => void data.loadDefault()}
        />
      )}
      {route.name === 'today' && (
        <TodayPage
          candidates={data.candidates}
          events={data.events}
          listingTimes={data.listingTimes}
          loading={data.loading}
        />
      )}
      {route.name === 'ca' && <CaPage candidates={data.candidates} />}
      {route.name === 'launched' && (
        <LaunchedPage items={data.launched.items} generatedAt={data.launched.generatedAt} loading={data.loading} />
      )}
      {route.name === 'workbench' && (
        <WorkbenchPage
          candidates={data.allCandidates}
          events={data.events}
          loading={data.loading}
          eventsAt={data.eventsAt}
          launchedHandles={data.launchedHandles}
        />
      )}
      {route.name === 'monitor' && (
        <MonitorPage
          handle={route.handle}
          candidates={data.allCandidates}
          events={data.events}
          eventsNote={data.eventsNote}
          eventsAt={data.eventsAt}
        />
      )}
      {route.name === 'notfound' && (
        <main className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6">
          <h1 className="text-2xl font-bold">没有这个页面</h1>
          <a href={appPath()} className="mt-4 inline-block text-sm text-[var(--color-orange)] hover:underline">
            返回项目列表
          </a>
        </main>
      )}

      <CaAlertToasts />

      <footer className="border-t border-[var(--color-line)] py-8 text-center dark:border-[var(--color-night-line)]">
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          台子雷达 · Pad Hunter — Telegram「项目推送」与「项目推送监控」
        </p>
      </footer>
    </div>
  )
}

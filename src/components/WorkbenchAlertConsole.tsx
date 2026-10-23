import { useMemo } from 'react'
import { markWorkbenchAlertIdsRead } from '../utils/workbenchAlertStore'
import {
  ALERT_UI,
  consoleLines,
  flashingAlertIds,
  type WorkbenchAlert,
} from '../utils/workbenchAlerts'

export function WorkbenchAlertConsole({
  alerts,
  readIds,
  pinned,
  launched,
}: {
  alerts: readonly WorkbenchAlert[]
  readIds: ReadonlySet<string>
  pinned: ReadonlySet<string>
  launched: ReadonlySet<string>
}) {
  const visible = useMemo(() => ({ pinned, launched }), [pinned, launched])
  const lines = consoleLines(alerts, readIds, visible)
  const flashingIds = flashingAlertIds(alerts, readIds, visible)
  const flashing = flashingIds.length > 0

  const stop = () => {
    if (flashingIds.length === 0) return
    markWorkbenchAlertIdsRead(flashingIds)
  }

  return (
    <section
      className={`wb-console mt-4 ${flashing ? 'cursor-pointer' : ''}`}
      aria-label={flashing ? `${ALERT_UI.consoleTitle}，${ALERT_UI.consoleStop}` : ALERT_UI.consoleTitle}
      onClick={stop}
      onKeyDown={(event) => {
        if (!flashing) return
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        stop()
      }}
      tabIndex={flashing ? 0 : undefined}
    >
      <div className="wb-console-bar">
        <span>工作台:~$ {ALERT_UI.consoleTitle}</span>
        <span>
          {flashing ? (
            <>
              <span className="wb-dot-flash mr-1 inline-block h-2 w-2 rounded-full bg-amber-300 align-middle" aria-hidden="true" />
              {flashingIds.length} {ALERT_UI.consoleCount} · {ALERT_UI.consoleStop}
            </>
          ) : (
            ALERT_UI.consoleReady
          )}
        </span>
      </div>
      <div className="wb-console-log" role="log" aria-live="polite">
        {lines.length === 0 ? (
          <p className="wb-console-quiet">{ALERT_UI.consoleWait}</p>
        ) : (
          lines.map((line) => (
            <p
              key={line.id || `${line.handle}-${line.ts}`}
              className={`wb-console-line${line.flash ? ' wb-line-flash' : ''}`}
              data-alert-tone={line.tone}
            >
              <span className="wb-console-stamp">{line.stamp || '—'}</span>
              <span aria-hidden="true">{line.mark}</span>
              <span className="wb-console-label">{line.label}</span>
              <span className="wb-console-name">{line.name || line.handle}</span>
              {line.text && <span className="wb-console-text">{line.text}</span>}
            </p>
          ))
        )}
      </div>
      <p className="wb-console-prompt">
        <span aria-hidden="true">▸ </span>
        {flashing ? ALERT_UI.consoleStop : ALERT_UI.consoleWait}
        <span className={`wb-console-cursor${flashing ? ' wb-dot-flash' : ''}`} aria-hidden="true" />
      </p>
    </section>
  )
}

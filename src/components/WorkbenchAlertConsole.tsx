import { useMemo } from 'react'
import { handleKey } from '../utils/workbench'
import { markWorkbenchAlertsRead } from '../utils/workbenchAlertStore'
import { ALERT_UI, consoleLines, type WorkbenchAlert } from '../utils/workbenchAlerts'

/** One project's command-line log. A click stops the blink for this project only. */
export function WorkbenchAlertConsole({
  alerts,
  readIds,
  name,
  handle,
}: {
  alerts: readonly WorkbenchAlert[]
  readIds: ReadonlySet<string>
  name: string
  handle: string
}) {
  const key = handleKey(handle)
  const mine = useMemo(
    () => alerts.filter((alert) => handleKey(alert.handle) === key),
    [alerts, key],
  )
  const lines = consoleLines(mine, readIds)
  const flashingCount = lines.filter((line) => line.flash).length
  const flashing = flashingCount > 0
  const title = name.trim() || handle

  const stop = () => {
    if (!key || !flashing) return
    markWorkbenchAlertsRead(handle)
  }

  return (
    <section
      className={`wb-console ${flashing ? 'cursor-pointer' : ''}`}
      aria-label={flashing ? `${title}，${ALERT_UI.consoleStop}` : `${title} ${ALERT_UI.consoleTitle}`}
      onClick={(event) => {
        event.stopPropagation()
        stop()
      }}
      onKeyDown={(event) => {
        if (!flashing) return
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        event.stopPropagation()
        stop()
      }}
      tabIndex={flashing ? 0 : undefined}
    >
      <div className="wb-console-bar">
        <span className="min-w-0 truncate">{title}:~$</span>
        <span className="shrink-0">
          {flashing ? (
            <>
              <span className="wb-dot-flash mr-1 inline-block h-2 w-2 rounded-full bg-amber-300 align-middle" aria-hidden="true" />
              {flashingCount} {ALERT_UI.consoleCount}
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
              key={line.id || `${line.ts}-${line.label}`}
              className={`wb-console-line${line.flash ? ' wb-line-flash' : ''}`}
              data-alert-tone={line.tone}
            >
              <span className="wb-console-stamp">{line.stamp || '—'}</span>
              <span aria-hidden="true">{line.mark}</span>
              <span className="wb-console-label">{line.label}</span>
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

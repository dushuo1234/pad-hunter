import { useMemo } from 'react'
import { markWorkbenchAlertIdsRead } from '../utils/workbenchAlertStore'
import {
  ALERT_UI,
  consoleLines,
  flashingAlertIds,
  type WorkbenchAlert,
} from '../utils/workbenchAlerts'

/**
 * Command-line alert log.
 * Without `handle`, this is the shared 提醒控制台 for every pinned project.
 * With `handle`, it is that project's box and a click acks only those ids.
 */
export function WorkbenchAlertConsole({
  alerts,
  readIds,
  pinned,
  launched,
  name,
  handle,
}: {
  alerts: readonly WorkbenchAlert[]
  readIds: ReadonlySet<string>
  pinned?: ReadonlySet<string>
  launched?: ReadonlySet<string>
  name?: string
  handle?: string
}) {
  const project = Boolean(handle)
  const visible = useMemo(
    () => (project ? { handle } : { pinned, launched }),
    [project, handle, pinned, launched],
  )
  const lines = consoleLines(alerts, readIds, visible)
  const flashingIds = flashingAlertIds(alerts, readIds, visible)
  const flashing = flashingIds.length > 0
  const title = (name ?? '').trim() || handle || ''

  const stop = () => {
    if (flashingIds.length === 0) return
    markWorkbenchAlertIdsRead(flashingIds)
  }

  return (
    <section
      className={`wb-console ${project ? 'wb-console-project' : 'mt-4'} ${flashing ? 'cursor-pointer' : ''}`}
      aria-label={
        project
          ? flashing
            ? `${title}，${ALERT_UI.consoleStop}`
            : `${title} ${ALERT_UI.consoleTitle}`
          : flashing
            ? `${ALERT_UI.consoleTitle}，${ALERT_UI.consoleStop}`
            : ALERT_UI.consoleTitle
      }
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
        <span className="min-w-0 truncate">{project ? `${title}:~$` : `工作台:~$ ${ALERT_UI.consoleTitle}`}</span>
        <span className="shrink-0">
          {flashing ? (
            <>
              <span className="wb-dot-flash mr-1 inline-block h-2 w-2 rounded-full bg-amber-300 align-middle" aria-hidden="true" />
              {flashingIds.length} {ALERT_UI.consoleCount}
              {project ? '' : ` · ${ALERT_UI.consoleStop}`}
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
              {!project && <span className="wb-console-name">{line.name || line.handle}</span>}
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

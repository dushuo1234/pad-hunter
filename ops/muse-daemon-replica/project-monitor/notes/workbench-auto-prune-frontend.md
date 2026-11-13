# Frontend follow-up (needs CloudAgent PR on dushuo1234/pad-hunter)

## Why
Server now strips launched handles from `workbench_active.json` and rejects them on
`POST /v1/workbench/sync` (response includes `dropped_launched`). Browser localStorage
`pad-hunter.workbench.v1` still keeps pins, so the Workbench UI can re-show and re-sync
them until the client also drops them.

## Desired behavior
When `launched.json` / `launchedHandles` includes a workbench pin, auto-remove it from
localStorage (same as manual 移出), then the next sync stays clean.

## Suggested edit
In `src/hooks/useWorkbenchLive.ts` (or `WorkbenchPage.tsx`), after `fetchLaunched()` /
when `launchedHandles` prop updates:

```ts
import { removeWorkbenchItems, handleKey, getWorkbenchItems } from '../utils/workbench'
import { isLaunchedHandle } from '../utils/launched'

// inside an effect depending on launched / launchedHandles:
const dropIds = getWorkbenchItems()
  .filter((item) => isLaunchedHandle(launchedHandles, item.handle))
  .map((item) => item.id)
if (dropIds.length) removeWorkbenchItems(dropIds)
```

Also honor sync response `dropped_launched` from `syncWorkbench` in `src/utils/workbenchApi.ts`:
if the API returns dropped handles, remove matching pins from localStorage.

Optional: when sync returns `dropped_launched`, show toast 「已自动移出已开盘 N 个」.

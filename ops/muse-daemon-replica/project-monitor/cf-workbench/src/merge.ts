/** LWW merge helpers — parity with workbench_api.py v1.5.0 */

export const TOMBSTONE_MAX = 500;
export const TOMBSTONE_DAYS = 30;

export type WBItem = {
  handle: string;
  name?: string | null;
  sites?: string[] | null;
  x_url?: string | null;
  chain?: string | null;
  notes?: string | null;
  push?: boolean | null;
  added_at?: string | null;
  updated_at?: string | null;
};

export type Tombstone = { handle: string; removed_at?: string | null };

export type PinsDoc = {
  synced_at: string;
  timezone: string;
  client_id?: string | null;
  count: number;
  items: WBItem[];
  removed: Tombstone[];
  dropped_launched: { handle?: string | null; name?: string | null }[];
  note?: string;
};

export type ReviewedMark = {
  at?: string | null;
  snapshot?: unknown;
  cleared_at?: string | null;
};

export type ReviewedDoc = {
  synced_at: string;
  timezone: string;
  client_id?: string | null;
  marks: Record<string, ReviewedMark>;
};

export function nowIso(): string {
  // Asia/Shanghai wall clock as +08:00 ISO (seconds)
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(
    fmt.formatToParts(new Date()).map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}+08:00`;
}

export function norm(h: string | null | undefined): string {
  return (h || "").trim().replace(/^@+/, "").trim().toLowerCase();
}

export function epoch(iso: string | null | undefined): number {
  if (!iso) return 0;
  try {
    const t = Date.parse(iso);
    return Number.isFinite(t) ? t / 1000 : 0;
  } catch {
    return 0;
  }
}

function itemEffectiveTs(it: WBItem, defaultIso?: string): number {
  return epoch(it.updated_at || it.added_at || defaultIso || undefined);
}

export function pruneTombstones(removed: Tombstone[]): Tombstone[] {
  const byH = new Map<string, Tombstone>();
  for (const t of removed || []) {
    if (!t || typeof t !== "object") continue;
    const h = norm(t.handle);
    if (!h) continue;
    const ra = t.removed_at || "";
    const prev = byH.get(h);
    if (!prev || ra > (prev.removed_at || "")) {
      byH.set(h, {
        handle: (t.handle || h).trim().replace(/^@+/, ""),
        removed_at: ra,
      });
    }
  }
  const cutoff = Date.now() / 1000 - TOMBSTONE_DAYS * 86400;
  const kept: Tombstone[] = [];
  for (const t of byH.values()) {
    const ts = epoch(t.removed_at);
    if (ts === 0 || ts >= cutoff) kept.push(t);
  }
  kept.sort((a, b) => (b.removed_at || "").localeCompare(a.removed_at || ""));
  return kept.slice(0, TOMBSTONE_MAX);
}

export function pinsPayload(wb: PinsDoc): {
  synced_at: string;
  items: WBItem[];
  removed: Tombstone[];
} {
  return {
    synced_at: wb.synced_at || nowIso(),
    items: [...(wb.items || [])],
    removed: [...(wb.removed || [])],
  };
}

export function mergeWorkbench(
  prev: PinsDoc,
  body: {
    items?: WBItem[];
    client_id?: string | null;
    removed?: Tombstone[] | null;
  },
  blocked: Set<string> = new Set(),
): { doc: PinsDoc; dropped: { handle?: string | null; name?: string | null }[] } {
  const now = nowIso();
  const itemsBy = new Map<string, WBItem>();
  for (const it of prev.items || []) {
    if (!it || typeof it !== "object") continue;
    const h = norm(it.handle);
    if (h) itemsBy.set(h, { ...it });
  }
  const tombsBy = new Map<string, Tombstone>();
  for (const t of prev.removed || []) {
    if (!t || typeof t !== "object") continue;
    const h = norm(t.handle);
    if (h) {
      tombsBy.set(h, {
        handle: (t.handle || h).trim().replace(/^@+/, ""),
        removed_at: t.removed_at || now,
      });
    }
  }

  const dropped: { handle?: string | null; name?: string | null }[] = [];

  for (const it of body.items || []) {
    const h = norm(it.handle);
    if (!h) continue;
    const display = it.handle.trim().replace(/^@+/, "");
    if (blocked.has(h)) {
      dropped.push({ handle: display, name: it.name });
      continue;
    }
    const d: WBItem = { ...it, handle: display };
    d.sites = (it.sites || [])
      .filter((u): u is string => typeof u === "string" && !!u.trim())
      .map((u) => u.trim())
      .slice(0, 20);
    const existing = itemsBy.get(h);
    const incIso = d.updated_at || d.added_at || now;
    if (!d.updated_at) d.updated_at = incIso;
    if (!d.added_at) d.added_at = (existing?.added_at ?? null) || now;
    const incTs = epoch(d.updated_at || d.added_at);

    const tomb = tombsBy.get(h);
    if (tomb && epoch(tomb.removed_at) >= incTs) continue;
    if (tomb && incTs > epoch(tomb.removed_at)) tombsBy.delete(h);

    if (existing) {
      const exTs = itemEffectiveTs(existing);
      if (incTs < exTs) continue;
      if (existing.added_at) {
        if (!d.added_at || epoch(existing.added_at) <= epoch(d.added_at)) {
          d.added_at = existing.added_at;
        }
      }
      for (const fld of ["name", "sites", "x_url", "chain", "notes"] as const) {
        const inv = d[fld];
        const exv = existing[fld];
        if (inv === null || inv === undefined || inv === "" || (Array.isArray(inv) && inv.length === 0)) {
          if (exv !== null && exv !== undefined && exv !== "" && !(Array.isArray(exv) && exv.length === 0)) {
            (d as Record<string, unknown>)[fld] = exv;
          }
        }
      }
    }
    itemsBy.set(h, d);
  }

  if (body.removed !== undefined && body.removed !== null) {
    for (const t of body.removed) {
      const h = norm(t.handle);
      if (!h) continue;
      const display = t.handle.trim().replace(/^@+/, "");
      const ra = t.removed_at || now;
      const raTs = epoch(ra);
      const existing = itemsBy.get(h);
      if (existing) {
        if (raTs > itemEffectiveTs(existing, now)) {
          itemsBy.delete(h);
          tombsBy.set(h, { handle: display, removed_at: ra });
        }
      } else {
        const prevT = tombsBy.get(h);
        if (!prevT || raTs >= epoch(prevT.removed_at)) {
          tombsBy.set(h, { handle: display, removed_at: ra });
        }
      }
    }
  }

  for (const h of [...itemsBy.keys()]) {
    if (blocked.has(h)) {
      const it = itemsBy.get(h)!;
      itemsBy.delete(h);
      dropped.push({ handle: it.handle, name: it.name });
    }
  }

  const itemsList = [...itemsBy.values()].sort((a, b) =>
    (a.added_at || "").localeCompare(b.added_at || ""),
  );
  const removedList = pruneTombstones([...tombsBy.values()]);
  const note =
    prev.note ||
    "Cloudflare Workers sync room. Launched handles should be pruned client-side / by box poller.";

  return {
    doc: {
      synced_at: now,
      timezone: "Asia/Shanghai",
      client_id: body.client_id ?? null,
      count: itemsList.length,
      items: itemsList,
      removed: removedList,
      dropped_launched: dropped,
      note,
    },
    dropped,
  };
}

export function normReviewKey(key: string): string {
  const k = (key || "").trim();
  if (k.toLowerCase().startsWith("name:")) {
    return "name:" + k.split(":", 1)[1];
  }
  return norm(k);
}

function markEffectiveTs(m: ReviewedMark): number {
  return Math.max(epoch(m.at), epoch(m.cleared_at));
}

export function mergeReviewed(
  prev: ReviewedDoc,
  body: { client_id?: string | null; marks?: Record<string, ReviewedMark> },
): ReviewedDoc {
  const now = nowIso();
  const marks: Record<string, ReviewedMark> = {};
  for (const [k, v] of Object.entries(prev.marks || {})) {
    if (v && typeof v === "object") marks[k] = { ...v };
  }
  for (const [rawK, mark] of Object.entries(body.marks || {})) {
    const k = normReviewKey(rawK);
    if (!k) continue;
    const clean: ReviewedMark = {
      at: mark?.at ?? null,
      snapshot: mark?.snapshot,
      cleared_at: mark?.cleared_at ?? null,
    };
    const existing = marks[k];
    if (!existing || markEffectiveTs(clean) >= markEffectiveTs(existing)) {
      marks[k] = clean;
    }
  }
  return {
    synced_at: now,
    timezone: "Asia/Shanghai",
    client_id: body.client_id ?? null,
    marks,
  };
}

export function emptyPins(): PinsDoc {
  return {
    synced_at: nowIso(),
    timezone: "Asia/Shanghai",
    client_id: null,
    count: 0,
    items: [],
    removed: [],
    dropped_launched: [],
    note: "Cloudflare Workers sync room.",
  };
}

export function emptyReviewed(): ReviewedDoc {
  return {
    synced_at: nowIso(),
    timezone: "Asia/Shanghai",
    client_id: null,
    marks: {},
  };
}

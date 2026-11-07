/** Mirror workbench_api.py ORIGIN_RE */
const ORIGIN_RE =
  /^(https:\/\/dushuo1234\.github\.io|https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?|null)$/;

export function originAllowed(origin: string | null): boolean {
  if (origin === null || origin === undefined) return true; // non-browser / curl
  return ORIGIN_RE.test(origin);
}

export function corsHeaders(origin: string | null): HeadersInit {
  const h: Record<string, string> = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers":
      "Content-Type, X-Pad-Hunter-Token, Authorization",
    "Access-Control-Max-Age": "86400",
  };
  if (origin && originAllowed(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Vary"] = "Origin";
  } else if (!origin) {
    // leave unset for curl
  }
  return h;
}

export function withCors(resp: Response, origin: string | null): Response {
  const headers = new Headers(resp.headers);
  const extra = corsHeaders(origin);
  for (const [k, v] of Object.entries(extra)) headers.set(k, v);
  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers,
  });
}

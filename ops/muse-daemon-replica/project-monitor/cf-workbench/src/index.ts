/**
 * Pad Hunter workbench + radar cloud sync — Worker entry.
 * Routes HTTP + WS to a single Durable Object room.
 */
import { WorkbenchRoom, type Env } from "./workbench-do";
import { corsHeaders, originAllowed, withCors } from "./cors";

export { WorkbenchRoom };

function roomStub(env: Env): DurableObjectStub {
  const name = env.ROOM_NAME || "pad-hunter";
  const id = env.WORKBENCH.idFromName(name);
  return env.WORKBENCH.get(id);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");

    if (request.method === "OPTIONS") {
      if (origin && !originAllowed(origin)) {
        return new Response(null, { status: 403 });
      }
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (url.pathname === "/health" || url.pathname === "/") {
      try {
        const stub = roomStub(env);
        const r = await stub.fetch(
          new Request(new URL("/internal/health", request.url), { method: "GET" }),
        );
        return withCors(r, origin);
      } catch (e) {
        return withCors(
          Response.json(
            {
              ok: false,
              version: env.VERSION || "1.7.2-cf",
              backend: "cloudflare-workers-do",
              error: String(e).slice(0, 200),
            },
            { status: 503 },
          ),
          origin,
        );
      }
    }

    if (
      url.pathname.startsWith("/v1/workbench/") ||
      url.pathname === "/v1/workbench/ws" ||
      url.pathname.startsWith("/v1/radar/") ||
      url.pathname.startsWith("/v1/launched/") ||
      url.pathname.startsWith("/v1/today/")
    ) {
      const stub = roomStub(env);
      const fwdHeaders = new Headers(request.headers);
      fwdHeaders.set("X-PH-Build", env.BUILD_ID || "");
      const r = await stub.fetch(new Request(request, { headers: fwdHeaders }));
      if (r.status === 101) return r;
      return withCors(r, origin);
    }

    return withCors(
      Response.json(
        {
          detail: "not found",
          hint: "Pad Hunter cloud: /health, /v1/workbench/*, /v1/radar/*, /v1/launched/*, /v1/today/cas, /v1/workbench/ws",
        },
        { status: 404 },
      ),
      origin,
    );
  },
} satisfies ExportedHandler<Env>;

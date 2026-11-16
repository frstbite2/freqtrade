/**
 * Server-side proxy to the FastAPI backend. The browser calls /api/platform/<path>; this
 * handler checks the path against an allowlist, adds the bearer token from the server's own
 * environment and forwards a GET. The token never reaches the browser: it is not in any client
 * bundle, response or error message.
 */

import { isAllowedPath } from "@/lib/proxy-rules";

export const dynamic = "force-dynamic";

const TIMEOUT_MS = 8000;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  if (!isAllowedPath(path)) {
    return Response.json({ error: "path not allowed" }, { status: 404 });
  }
  const base = (process.env.PLATFORM_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
  const token = process.env.PLATFORM_API_TOKEN;
  const query = new URL(request.url).search;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const upstream = await fetch(`${base}/${path.join("/")}${query}`, {
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
      signal: controller.signal,
    });
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    // Unreachable or too slow. Say so without echoing the URL or anything from the environment.
    return Response.json({ error: "backend unreachable" }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}

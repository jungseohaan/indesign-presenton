import { NextRequest, NextResponse } from "next/server";
import {
  getFastApiAuthHeaders,
  getFastApiBaseUrl,
} from "@/lib/fastapi-internal";

// Proxy outline-refine through a server-side route handler instead of the
// next.config rewrite. The rewrite path (undici) intermittently drops the
// connection ("socket hang up" / ECONNRESET) on the multi-second LLM call;
// a dedicated handler with no client-side timeout is reliable.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const url = `${getFastApiBaseUrl()}/api/v1/ppt/outline-refine/message`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getFastApiAuthHeaders(),
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const bodyText = await response.text();
    return new NextResponse(bodyText, {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error?.message || "Failed to reach outline service" },
      { status: 502 }
    );
  }
}

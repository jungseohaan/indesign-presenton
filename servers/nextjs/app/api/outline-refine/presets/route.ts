import { NextRequest, NextResponse } from "next/server";
import {
  getFastApiAuthHeaders,
  getFastApiBaseUrl,
} from "@/lib/fastapi-internal";

// Saving a preset may auto-summarize rules via an LLM call, so proxy through a
// dedicated handler (not the next.config rewrite) for reliability.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const url = `${getFastApiBaseUrl()}/api/v1/ppt/outline-refine/presets`;
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
      { detail: error?.message || "Failed to reach preset service" },
      { status: 502 }
    );
  }
}

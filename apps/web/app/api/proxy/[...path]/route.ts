import { NextRequest, NextResponse } from "next/server";

const apiUrl = () => (process.env.SPANTRACE_API_URL || process.env.AGENTSCOPE_API_URL || "http://localhost:8070").replace(/\/$/, "");

async function forward(request: NextRequest, path: string[]) {
  const key = process.env.SPANTRACE_API_KEY || process.env.AGENTSCOPE_API_KEY;
  if (!key) return NextResponse.json({ detail: "Dashboard is not configured. Set SPANTRACE_API_KEY in apps/web/.env.local." }, { status: 503 });
  const target = `${apiUrl()}/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ "X-API-Key": key });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const body = request.method === "GET" || request.method === "DELETE" ? undefined : await request.arrayBuffer();
  const response = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
  const text = await response.text();
  return new NextResponse(text, { status: response.status, headers: { "content-type": response.headers.get("content-type") || "application/json" } });
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return forward(request, (await context.params).path); }
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return forward(request, (await context.params).path); }
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return forward(request, (await context.params).path); }

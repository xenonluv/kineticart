import { NextRequest } from "next/server";
import { headFile, serveFile } from "@/lib/generations";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return serveFile((await params).id, "image");
}

export async function HEAD(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return headFile((await params).id, "image");
}

// Container liveness probe. Deliberately not under /api/*, which Nginx routes to FastAPI (ADR-006).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}

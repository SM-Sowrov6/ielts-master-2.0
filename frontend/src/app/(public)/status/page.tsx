import type { Metadata } from "next";

import { PageHeader } from "@/components/patterns/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { components } from "@/lib/api/schema";
import { serverApi } from "@/lib/api/server";
import { ServerEnvError } from "@/lib/server-env";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "System status" };

type Readiness = components["schemas"]["ReadinessResponse"];
type BackendStatus =
  { kind: "reachable"; readiness: Readiness } | { kind: "unreachable"; reason: string };

async function fetchBackendStatus(): Promise<BackendStatus> {
  try {
    // The typed client: /readyz returns ReadinessResponse for both 200 and 503.
    const { data, error } = await serverApi().GET("/readyz", { signal: AbortSignal.timeout(3000) });
    const readiness = data ?? error;
    if (readiness) return { kind: "reachable", readiness };
    return { kind: "unreachable", reason: "Unexpected response from backend" };
  } catch (error) {
    // Never surface internal hostnames or error text to the page.
    if (error instanceof ServerEnvError)
      return { kind: "unreachable", reason: "Backend URL is not configured" };
    return { kind: "unreachable", reason: "Backend did not respond" };
  }
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <Badge variant={ok ? "secondary" : "destructive"}>{ok ? "Operational" : "Unavailable"}</Badge>
  );
}

export default async function StatusPage() {
  const backend = await fetchBackendStatus();
  const rows: { name: string; ok: boolean; nested?: boolean }[] = [
    { name: "Frontend", ok: true },
    { name: "Backend API", ok: backend.kind === "reachable" && backend.readiness.status === "ok" },
    ...(backend.kind === "reachable"
      ? Object.entries(backend.readiness.checks).map(([name, status]) => ({
          name,
          ok: status === "ok",
          nested: true,
        }))
      : []),
  ];
  return (
    <>
      <PageHeader title="System status" description="Live readiness of the platform services." />
      <Card>
        <CardContent>
          <dl className="divide-y">
            {rows.map((row) => (
              <div
                key={row.name}
                className={
                  row.nested
                    ? "flex justify-between py-3 pl-6 text-sm"
                    : "flex justify-between py-3"
                }
              >
                <dt className="capitalize">{row.name}</dt>
                <dd>
                  <StatusBadge ok={row.ok} />
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      {backend.kind === "unreachable" && (
        <p className="mt-4 text-sm text-muted-foreground">{backend.reason}</p>
      )}
    </>
  );
}

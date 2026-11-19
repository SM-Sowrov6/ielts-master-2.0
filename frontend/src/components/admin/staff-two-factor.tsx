"use client";

import { useQuery } from "@tanstack/react-query";
import { CopyIcon, LoaderCircleIcon, ShieldCheckIcon, SmartphoneIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";

import { BrandMark } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  confirmMfaSetup,
  fetchMfaStatus,
  type MfaSetup,
  messageFor,
  startMfaSetup,
  verifyMfa,
} from "@/lib/auth/api";

/**
 * Staff second factor, shown by the admin layout when the backend answers `mfa_required`.
 * Not enrolled: scan a QR code, confirm one code, save the recovery codes. Enrolled: enter the
 * current authenticator code (or a recovery code). Success upgrades the session server-side;
 * the layout is then re-rendered and lets the person in.
 */
export function StaffTwoFactor() {
  const router = useRouter();
  const status = useQuery({ queryKey: ["mfa-status"], queryFn: fetchMfaStatus });
  const [recovery, setRecovery] = useState<string[] | null>(null);

  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-dvh w-full max-w-md flex-col items-center justify-center gap-6 px-4 py-12"
    >
      <BrandMark />
      <section className="w-full space-y-5 rounded-3xl border bg-card p-6 shadow-elevation-1">
        <header className="space-y-1 text-center">
          <ShieldCheckIcon className="mx-auto size-8 text-primary" aria-hidden="true" />
          <h1 className="font-heading text-xl font-semibold">Two-factor authentication</h1>
          <p className="text-sm text-muted-foreground">
            Staff access is protected by a second step using an authenticator app (Google
            Authenticator, Microsoft Authenticator, 1Password, Authy…).
          </p>
        </header>
        {recovery ? (
          <RecoveryCodes codes={recovery} onDone={() => router.refresh()} />
        ) : status.isPending ? (
          <LoaderCircleIcon
            className="mx-auto size-6 animate-spin text-primary"
            aria-label="Loading"
          />
        ) : status.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {messageFor(status.error)}
          </p>
        ) : status.data.enrolled ? (
          <VerifyStep onDone={() => router.refresh()} />
        ) : (
          <SetupStep onEnrolled={setRecovery} />
        )}
      </section>
      <Link href="/dashboard" className="text-sm text-muted-foreground underline">
        Back to your dashboard
      </Link>
    </main>
  );
}

function CodeForm({
  label,
  hint,
  submitLabel,
  allowRecovery,
  onSubmit,
}: {
  label: string;
  hint?: string;
  submitLabel: string;
  allowRecovery?: boolean;
  onSubmit: (code: string) => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [useRecovery, setUseRecovery] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(code.trim());
    } catch (err) {
      setError(messageFor(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="mfa-code">{useRecovery ? "Recovery code" : label}</Label>
        <Input
          id="mfa-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="one-time-code"
          inputMode={useRecovery ? "text" : "numeric"}
          placeholder={useRecovery ? "xxxxx-xxxxx" : "123456"}
          maxLength={useRecovery ? 20 : 7}
          autoFocus
          required
          aria-describedby={hint ? "mfa-hint" : undefined}
          className="text-center font-mono text-lg tracking-widest"
        />
        {hint && !useRecovery && (
          <p id="mfa-hint" className="text-xs text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={busy || code.trim().length < 6}>
        {busy && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
        {submitLabel}
      </Button>
      {allowRecovery && (
        <button
          type="button"
          className="w-full text-center text-xs text-muted-foreground underline"
          onClick={() => {
            setUseRecovery((v) => !v);
            setCode("");
            setError(null);
          }}
        >
          {useRecovery
            ? "Use the authenticator app instead"
            : "Lost your phone? Use a recovery code"}
        </button>
      )}
    </form>
  );
}

function VerifyStep({ onDone }: { onDone: () => void }) {
  return (
    <CodeForm
      label="6-digit code from your authenticator app"
      submitLabel="Verify"
      allowRecovery
      onSubmit={async (code) => {
        await verifyMfa(code);
        onDone();
      }}
    />
  );
}

function SetupStep({ onEnrolled }: { onEnrolled: (codes: string[]) => void }) {
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!setup) return;
    let live = true;
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 220 })
      .then((url) => live && setQr(url))
      .catch(() => live && setQr(null));
    return () => {
      live = false;
    };
  }, [setup]);

  if (!setup) {
    return (
      <div className="space-y-3 text-center">
        <SmartphoneIcon className="mx-auto size-10 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm">
          Your account needs two-factor authentication before it can open the admin console. It
          takes about a minute.
        </p>
        <Button
          className="w-full"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setSetup(await startMfaSetup());
            } catch (err) {
              toast.error(messageFor(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          Set up authenticator
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ol className="list-decimal space-y-1 pl-5 text-sm">
        <li>Open your authenticator app and add a new account.</li>
        <li>Scan this QR code (or enter the key by hand).</li>
        <li>Type the 6-digit code it shows.</li>
      </ol>
      <div className="flex justify-center">
        {qr ? (
          // eslint-disable-next-line @next/next/no-img-element -- local data URL, no optimisation needed
          <img
            src={qr}
            alt="QR code for your authenticator app"
            width={220}
            height={220}
            className="rounded-xl border bg-white p-2"
          />
        ) : (
          <LoaderCircleIcon className="size-6 animate-spin text-primary" aria-hidden="true" />
        )}
      </div>
      <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2">
        <code className="flex-1 break-all text-xs">{setup.secret.match(/.{1,4}/g)?.join(" ")}</code>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Copy key"
          onClick={() =>
            void navigator.clipboard
              ?.writeText(setup.secret)
              .then(() => toast.success("Key copied"))
          }
        >
          <CopyIcon aria-hidden="true" />
        </Button>
      </div>
      <CodeForm
        label="6-digit code"
        submitLabel="Confirm and continue"
        onSubmit={async (code) => onEnrolled(await confirmMfaSetup(code))}
      />
    </div>
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const text = codes.join("\n");
  return (
    <div className="space-y-4">
      <p className="text-sm">
        Two-factor authentication is on. Save these <strong>recovery codes</strong> somewhere safe
        (a password manager or printed). Each one works once if you lose your phone. They will not
        be shown again.
      </p>
      <ul
        className="grid grid-cols-2 gap-2 rounded-xl bg-muted p-3 font-mono text-sm"
        aria-label="Recovery codes"
      >
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          className="flex-1"
          onClick={() =>
            void navigator.clipboard?.writeText(text).then(() => toast.success("Codes copied"))
          }
        >
          <CopyIcon aria-hidden="true" /> Copy
        </Button>
        <Button
          type="button"
          variant="outline"
          className="flex-1"
          onClick={() => {
            const url = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
            const a = Object.assign(document.createElement("a"), {
              href: url,
              download: "ielts-master-recovery-codes.txt",
            });
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Download
        </Button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />I have
        saved my recovery codes
      </label>
      <Button className="w-full" disabled={!saved} onClick={onDone}>
        Open the admin console
      </Button>
    </div>
  );
}

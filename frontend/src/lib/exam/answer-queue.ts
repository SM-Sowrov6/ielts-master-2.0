/**
 * Candidate answer autosave (docs/EXAMINATION_ENGINE_DESIGN.md §5, ADR-013). Not the admin draft
 * save: this one talks to /attempts/{id}/answers under the attempt's writer lease.
 *
 * - Every change gets a monotonically increasing `client_revision`, persisted together with the
 *   lease and the not-yet-acknowledged answers in this browser (localStorage), so a reload or a
 *   crash replays unsaved answers with the same lease, and the server keeps the newest.
 * - Saves are debounced per question (800 ms) and flushed immediately on navigation/submit.
 * - Network/server errors retry with exponential backoff; the UI shows the state.
 * - Fatal responses (submitted, time up, continued elsewhere) stop the queue.
 * The server is the source of truth; local storage is only an outbox.
 */

import { putAnswers, type AnswerItem, type Response } from "@/lib/exam/api";
import { ApiError } from "@/lib/api/errors";

export type SaveState = "idle" | "pending" | "saving" | "saved" | "retrying" | "stopped";
export type FatalCode =
  | "attempt_submitted"
  | "attempt_deadline_passed"
  | "superseded_session"
  | "writer_token_invalid"
  | "attempt_not_found";

type Pending = { response: Response; revision: number; flagged: boolean };
type Stored = {
  epoch: number;
  token: string;
  revision: number;
  pending: Record<string, Pending>;
  submitKey?: string;
};

const PREFIX = "ielts.attempt.";
const DEBOUNCE_MS = 800;
const FATAL = new Set<string>([
  "attempt_submitted",
  "attempt_deadline_passed",
  "superseded_session",
  "writer_token_invalid",
  "attempt_not_found",
]);

function read(attemptId: string): Stored | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + attemptId);
    return raw ? (JSON.parse(raw) as Stored) : null;
  } catch {
    return null;
  }
}

function write(attemptId: string, value: Stored): void {
  try {
    window.localStorage.setItem(PREFIX + attemptId, JSON.stringify(value));
  } catch {
    // Storage full or blocked (private mode): saving continues, only offline replay is lost.
  }
}

export function storedLease(attemptId: string): { epoch: number; token: string } | null {
  const s = read(attemptId);
  return s ? { epoch: s.epoch, token: s.token } : null;
}

/** Remember a lease issued by start/resume. A new epoch starts a fresh revision counter. */
export function rememberLease(attemptId: string, epoch: number, token: string): void {
  const current = read(attemptId);
  if (current && current.epoch === epoch && current.token === token) return;
  write(attemptId, { epoch, token, revision: 0, pending: {}, submitKey: current?.submitKey });
}

export function submitKey(attemptId: string): string {
  const s = read(attemptId);
  if (s?.submitKey) return s.submitKey;
  const key = crypto.randomUUID();
  if (s) write(attemptId, { ...s, submitKey: key });
  return key;
}

export function forgetAttempt(attemptId: string): void {
  try {
    window.localStorage.removeItem(PREFIX + attemptId);
  } catch {
    // ignore
  }
}

export class AnswerQueue {
  private state: Stored;
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private inFlight: Promise<void> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private stopped = false;

  constructor(
    private readonly attemptId: string,
    lease: { epoch: number; token: string },
    private readonly listeners: {
      onState: (state: SaveState, detail?: string) => void;
      onServerTime: (serverNow: string) => void;
      onFatal: (code: FatalCode) => void;
    },
  ) {
    const stored = read(attemptId);
    this.state =
      stored && stored.epoch === lease.epoch && stored.token === lease.token
        ? stored
        : { epoch: lease.epoch, token: lease.token, revision: 0, pending: {} };
    write(attemptId, this.state);
  }

  /** Answers changed in this browser that the server has not acknowledged yet. */
  pendingAnswers(): Record<string, Response> {
    return Object.fromEntries(Object.entries(this.state.pending).map(([q, p]) => [q, p.response]));
  }

  hasPending(): boolean {
    return Object.keys(this.state.pending).length > 0;
  }

  set(questionId: string, response: Response, flagged = false): void {
    if (this.stopped) return;
    this.state.revision += 1;
    this.state.pending[questionId] = { response, revision: this.state.revision, flagged };
    write(this.attemptId, this.state);
    this.listeners.onState("pending");
    const timer = this.timers.get(questionId);
    if (timer) clearTimeout(timer);
    this.timers.set(
      questionId,
      setTimeout(() => {
        this.timers.delete(questionId);
        void this.flush();
      }, DEBOUNCE_MS),
    );
  }

  /** Send everything pending now (navigation, blur, before submit). Resolves when settled. */
  async flush(): Promise<void> {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
    if (this.inFlight) await this.inFlight;
    if (this.stopped || !this.hasPending()) return;
    this.inFlight = this.send().finally(() => {
      this.inFlight = null;
    });
    await this.inFlight;
  }

  finalItems(): AnswerItem[] {
    return Object.entries(this.state.pending).map(([question_id, p]) => ({
      question_id,
      response: p.response as AnswerItem["response"],
      client_revision: p.revision,
      flagged: p.flagged,
    }));
  }

  stop(): void {
    this.stopped = true;
    for (const timer of this.timers.values()) clearTimeout(timer);
    if (this.retryTimer) clearTimeout(this.retryTimer);
  }

  private async send(): Promise<void> {
    let single = false; // after a 422, send one answer at a time to isolate the invalid one
    while (this.hasPending() && !this.stopped) {
      const batch = this.finalItems().slice(0, single ? 1 : 50);
      this.listeners.onState("saving");
      try {
        const result = await putAnswers(
          this.attemptId,
          { epoch: this.state.epoch, token: this.state.token },
          batch,
        );
        this.attempt = 0;
        for (const stored of result.stored) {
          const pending = this.state.pending[stored.question_id];
          // Acknowledged once the server holds this revision (or newer) for our lease.
          if (
            pending &&
            stored.writer_epoch === this.state.epoch &&
            stored.client_revision >= pending.revision
          ) {
            delete this.state.pending[stored.question_id];
          }
        }
        write(this.attemptId, this.state);
        this.listeners.onServerTime(result.server_now);
      } catch (error) {
        if (error instanceof ApiError && FATAL.has(error.code)) {
          this.stop();
          this.listeners.onState("stopped", error.code);
          this.listeners.onFatal(error.code as FatalCode);
          return;
        }
        if (error instanceof ApiError && error.isClientError && error.status !== 429) {
          if (batch.length > 1) {
            single = true;
            continue;
          }
          // This one answer is rejected for good (malformed): drop it, keep saving the rest.
          for (const item of batch) delete this.state.pending[item.question_id];
          write(this.attemptId, this.state);
          continue;
        }
        this.attempt += 1;
        const delay = Math.min(30_000, 1000 * 2 ** (this.attempt - 1));
        this.listeners.onState(
          "retrying",
          `Connection problem. Retrying in ${Math.round(delay / 1000)} s.`,
        );
        this.retryTimer = setTimeout(() => void this.flush(), delay);
        return;
      }
    }
    if (!this.stopped) this.listeners.onState(this.hasPending() ? "pending" : "saved");
  }
}

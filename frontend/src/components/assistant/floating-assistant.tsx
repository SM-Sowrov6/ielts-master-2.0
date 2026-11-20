"use client";

import {
  ArrowUpIcon,
  BotIcon,
  MinusIcon,
  RotateCcwIcon,
  TriangleAlertIcon,
  XIcon,
} from "lucide-react";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { AssistantMarkdown } from "@/components/assistant/assistant-markdown";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import {
  MAX_MESSAGE_CHARS,
  fetchAssistantStatus,
  sendAssistantMessage,
  type ChatMessage,
} from "@/lib/assistant/api";
import { assistantHiddenOn } from "@/lib/assistant/routes";
import { loadConversation, saveConversation } from "@/lib/assistant/session";
import { useCurrentUser } from "@/lib/auth/hooks";
import { cn } from "@/lib/utils";

type Availability = "unknown" | "available" | "unavailable";

const GENERAL_SUGGESTIONS = [
  "How is the IELTS test structured?",
  "Give me a 4-week study plan",
  "How can I improve my vocabulary?",
];

/** One page-aware starter question, by section. */
function pageSuggestion(pathname: string): string | null {
  if (pathname.startsWith("/writing")) return "How do I plan a Task 2 essay?";
  if (pathname.startsWith("/reading")) return "Tips for True / False / Not Given?";
  if (pathname.startsWith("/listening")) return "How do I avoid spelling mistakes in Listening?";
  if (pathname.startsWith("/speaking")) return "How can I speak for 2 minutes in Part 2?";
  if (pathname === "/") return "What can I do on IELTS MASTER?";
  return null;
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "assistant_rate_limited":
        return "You've sent a lot of messages. Please wait a minute and try again.";
      case "assistant_busy":
        return "The assistant is busy right now (free AI capacity is limited). Please try again in a moment.";
      case "assistant_unavailable":
        return "The assistant isn't available right now. Please try again later.";
      case "validation_failed":
        return "That message couldn't be sent. Please shorten it and try again.";
      default:
        return "Something went wrong. Please try again.";
    }
  }
  return "Can't reach IELTS MASTER. Check your connection and try again.";
}

/**
 * Floating site assistant (bottom-right). Opens only when the user asks; never pops up on its
 * own, and is hidden on exam, Writing-editor, Speaking-session and staff pages. The conversation
 * lives in this tab's sessionStorage, scoped to the signed-in user.
 */
export function FloatingAssistant() {
  const pathname = usePathname() ?? "/";
  const { data: user, isPending: userPending } = useCurrentUser();
  const owner = user?.id ?? "guest";

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(false);
  const [availability, setAvailability] = useState<Availability>("unknown");

  const panelId = useId();
  const titleId = useId();
  const launcherRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  // Load this owner's conversation once the user is known; switching account never shows
  // another user's chat (state adjusted during render, React's "derived state" pattern).
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  if (!userPending && loadedFor !== owner) {
    setLoadedFor(owner);
    setMessages(loadConversation(owner));
    setError(null);
    setPending(false);
  }
  useEffect(() => () => abortRef.current?.abort(), [owner]);

  // Availability is checked lazily, the first time the panel opens.
  useEffect(() => {
    if (!open || availability !== "unknown") return;
    let cancelled = false;
    fetchAssistantStatus()
      .then((ok) => !cancelled && setAvailability(ok ? "available" : "unavailable"))
      .catch(() => !cancelled && setAvailability("available")); // let the chat call report it
    return () => {
      cancelled = true;
    };
  }, [open, availability]);

  useEffect(() => {
    if (!open) return;
    // Focus the input when opened (after the panel renders).
    const t = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages, pending, error, open]);

  const update = useCallback(
    (next: ChatMessage[]) => {
      setMessages(next);
      saveConversation(owner, next);
    },
    [owner],
  );

  const send = useCallback(
    async (history: ChatMessage[]) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setPending(true);
      setError(null);
      try {
        const reply = await sendAssistantMessage(history, pathname, controller.signal);
        if (controller.signal.aborted) return;
        update([...history, { role: "assistant", content: reply }]);
        if (!openRef.current) setUnread(true);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.code === "assistant_unavailable") {
          setAvailability("unavailable");
        }
        setError(errorText(err));
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setPending(false);
        }
      }
    },
    [pathname, update],
  );

  const submit = useCallback(
    (text: string) => {
      const content = text.trim().slice(0, MAX_MESSAGE_CHARS);
      if (!content || pending) return;
      const history: ChatMessage[] = [...messages, { role: "user", content }];
      update(history);
      setDraft("");
      void send(history);
    },
    [messages, pending, send, update],
  );

  const retry = useCallback(() => {
    if (messages.at(-1)?.role === "user") void send(messages);
  }, [messages, send]);

  const minimize = useCallback(() => {
    setOpen(false);
    launcherRef.current?.focus();
  }, []);

  const close = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
    setOpen(false);
    launcherRef.current?.focus();
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
    setError(null);
    update([]);
    inputRef.current?.focus();
  }, [update]);

  if (assistantHiddenOn(pathname)) return null;

  const onFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(draft);
  };

  const onInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit(draft);
    }
  };

  const unavailable = availability === "unavailable";
  const firstName = user?.full_name.split(/\s+/)[0];
  const suggestions = [pageSuggestion(pathname), ...GENERAL_SUGGESTIONS]
    .filter((s): s is string => Boolean(s))
    .slice(0, 3);
  const nearLimit = draft.length > MAX_MESSAGE_CHARS - 200;

  return (
    <div className="assistant-root">
      {open && (
        <section
          id={panelId}
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              minimize();
            }
          }}
          className={cn(
            "assistant-panel fixed z-[45] flex flex-col overflow-hidden border border-border bg-background text-foreground shadow-elevation-float",
            // Mobile: full screen. Tablet/desktop: anchored card above the launcher.
            "inset-0 sm:inset-auto sm:right-6 sm:bottom-24 sm:h-[min(640px,calc(100dvh-8rem))] sm:w-[400px] sm:rounded-2xl",
          )}
        >
          <header className="flex items-center gap-3 border-b border-border bg-gradient-to-r from-primary to-[color-mix(in_oklch,var(--primary),var(--brand-accent)_45%)] px-4 py-3 text-primary-foreground">
            <span
              aria-hidden="true"
              className="relative grid size-9 shrink-0 place-items-center rounded-xl bg-white/15 ring-1 ring-white/25"
            >
              <BotIcon className="size-5" />
              <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-primary bg-brand-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="truncate text-sm font-semibold">
                IELTS MASTER Assistant
              </h2>
              <p className="truncate text-xs text-primary-foreground/80">
                {unavailable ? "Currently offline" : "AI help for IELTS and this site"}
              </p>
            </div>
            <div className="flex items-center gap-0.5">
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={reset}
                disabled={messages.length === 0 && !pending}
                aria-label="Start a new conversation"
                title="New conversation"
                className="text-primary-foreground hover:bg-white/15 hover:text-primary-foreground"
              >
                <RotateCcwIcon />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={minimize}
                aria-label="Minimise assistant"
                title="Minimise"
                className="text-primary-foreground hover:bg-white/15 hover:text-primary-foreground"
              >
                <MinusIcon />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={close}
                aria-label="Close assistant"
                title="Close"
                className="text-primary-foreground hover:bg-white/15 hover:text-primary-foreground"
              >
                <XIcon />
              </Button>
            </div>
          </header>

          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="Conversation"
            className="flex-1 space-y-3 overflow-y-auto overscroll-contain bg-surface px-4 py-4 text-sm"
          >
            {messages.length === 0 && (
              <div className="space-y-3">
                <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-3.5 py-3 shadow-elevation-1">
                  <p className="font-medium">
                    Hi{firstName ? ` ${firstName}` : ""}! I&apos;m your IELTS MASTER assistant.
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Ask me about IELTS Listening, Reading, Writing or Speaking, grammar and
                    vocabulary, study plans, or how to use this site.
                  </p>
                </div>
                {!unavailable && (
                  <ul className="flex flex-wrap gap-2" aria-label="Suggested questions">
                    {suggestions.map((s) => (
                      <li key={s}>
                        <button
                          type="button"
                          onClick={() => submit(s)}
                          className="rounded-full border border-primary/25 bg-background px-3 py-1.5 text-left text-xs font-medium text-primary transition-colors hover:bg-primary/10"
                        >
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2.5 whitespace-pre-wrap break-words text-primary-foreground">
                    <span className="sr-only">You: </span>
                    {m.content}
                  </p>
                </div>
              ) : (
                <div key={i} className="flex gap-2">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
                  >
                    <BotIcon className="size-4" />
                  </span>
                  <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-card px-3.5 py-2.5 shadow-elevation-1">
                    <span className="sr-only">Assistant: </span>
                    <AssistantMarkdown text={m.content} onNavigate={minimize} />
                  </div>
                </div>
              ),
            )}

            {pending && (
              <div className="flex gap-2" role="status">
                <span
                  aria-hidden="true"
                  className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
                >
                  <BotIcon className="size-4" />
                </span>
                <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-3.5 py-3 shadow-elevation-1">
                  <span className="sr-only">The assistant is typing…</span>
                  <span aria-hidden="true" className="assistant-typing flex gap-1">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-destructive"
              >
                <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <div className="flex-1">
                  <p>{error}</p>
                  {messages.at(-1)?.role === "user" && !unavailable && (
                    <button
                      type="button"
                      onClick={retry}
                      className="mt-1 font-medium underline underline-offset-2"
                    >
                      Try again
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          <form
            onSubmit={onFormSubmit}
            className="border-t border-border bg-background px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
          >
            {unavailable ? (
              <p className="px-1 pb-1 text-xs text-muted-foreground">
                The assistant is offline right now. You can still use every other part of IELTS
                MASTER.
              </p>
            ) : (
              <>
                <div className="flex items-end gap-2 rounded-xl border border-input bg-background px-3 py-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
                  <label htmlFor={`${panelId}-input`} className="sr-only">
                    Message the assistant
                  </label>
                  <textarea
                    id={`${panelId}-input`}
                    ref={inputRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={onInputKeyDown}
                    maxLength={MAX_MESSAGE_CHARS}
                    rows={1}
                    placeholder="Ask about IELTS…"
                    aria-describedby={`${panelId}-hint`}
                    className="max-h-32 min-h-6 flex-1 resize-none bg-transparent text-sm outline-none [field-sizing:content] placeholder:text-muted-foreground"
                  />
                  <Button
                    type="submit"
                    size="icon-sm"
                    disabled={pending || !draft.trim()}
                    aria-label="Send message"
                    className="rounded-lg"
                  >
                    <ArrowUpIcon />
                  </Button>
                </div>
                <p
                  id={`${panelId}-hint`}
                  className="mt-1.5 flex justify-between gap-2 px-1 text-[11px] text-muted-foreground"
                >
                  <span>AI can make mistakes. It never gives band scores in chat.</span>
                  {nearLimit && (
                    <span aria-live="polite">
                      {draft.length}/{MAX_MESSAGE_CHARS}
                    </span>
                  )}
                </p>
              </>
            )}
          </form>
        </section>
      )}

      <button
        ref={launcherRef}
        type="button"
        onClick={() => {
          if (open) return minimize();
          setUnread(false);
          setOpen(true);
        }}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={open ? "Minimise IELTS MASTER Assistant" : "Open IELTS MASTER Assistant"}
        title="IELTS MASTER Assistant"
        className={cn(
          "assistant-launcher fixed right-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-[45] grid size-14 place-items-center rounded-full text-primary-foreground shadow-elevation-float transition-transform hover:scale-105 focus-visible:ring-4 focus-visible:ring-ring/50 focus-visible:outline-none sm:right-6 sm:bottom-6",
          open && "max-sm:hidden",
        )}
      >
        <span aria-hidden="true" className="assistant-launcher-glow" />
        {open ? (
          <XIcon className="relative size-6" aria-hidden="true" />
        ) : (
          <span className="assistant-bot relative" aria-hidden="true">
            <BotIcon className="size-7" />
          </span>
        )}
        {!open && (unread || pending) && (
          <span className="absolute top-0.5 right-0.5 size-3.5 rounded-full border-2 border-background bg-brand-accent">
            <span className="sr-only">
              {pending ? "The assistant is replying" : "New reply from the assistant"}
            </span>
          </span>
        )}
      </button>
    </div>
  );
}

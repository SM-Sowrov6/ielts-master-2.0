"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  EyeIcon,
  LoaderCircleIcon,
  PlusIcon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { toast } from "sonner";

import { ExaminerAvatar } from "@/components/speaking-room/shared";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createConfig,
  deleteConfig,
  fetchConfig,
  fetchConfigs,
  fetchPreview,
  fetchProfiles,
  fetchSpeakingTestOptions,
  saveConfig,
  setPublished,
  updateProfile,
  type ExaminerConfigBody,
  type ExaminerProfile,
} from "@/lib/admin/examiner-api";
import type { Me } from "@/lib/auth/api";
import { messageFor } from "@/lib/auth/api";
import { cn } from "@/lib/utils";

const BASE = "/admin/speaking/examiner";
const K = {
  configs: ["admin", "examiner", "configs"],
  profiles: ["admin", "examiner", "profiles"],
};

// ------------------------------------------------------------------------------ overview
export function ExaminerOverview({ user }: { user: Me }) {
  const router = useRouter();
  const qc = useQueryClient();
  const canEdit = user.permissions.includes("content.edit");
  const configs = useQuery({ queryKey: K.configs, queryFn: fetchConfigs });
  const tests = useQuery({
    queryKey: ["admin", "examiner", "tests"],
    queryFn: fetchSpeakingTestOptions,
  });
  const [testId, setTestId] = useState("");
  const create = useMutation({
    mutationFn: () => createConfig(testId),
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: K.configs });
      router.push(`${BASE}/${c.id}`);
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-heading text-xl font-semibold">Test configurations</h2>
          {canEdit && (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (testId) create.mutate();
              }}
            >
              <div className="space-y-1">
                <Label htmlFor="ex-test">Published Speaking test</Label>
                <select
                  id="ex-test"
                  className="h-9 w-64 rounded-md border bg-background px-2 text-sm"
                  value={testId}
                  onChange={(e) => setTestId(e.target.value)}
                >
                  <option value="">Choose a test…</option>
                  {(tests.data ?? []).map((t) => (
                    <option key={t.test_id} value={t.test_id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" disabled={!testId || create.isPending}>
                <PlusIcon aria-hidden="true" />
                New configuration
              </Button>
            </form>
          )}
        </div>
        {tests.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Publish a Speaking test in{" "}
            <Link
              href="/admin/speaking"
              className="text-primary underline-offset-4 hover:underline"
            >
              Speaking Management
            </Link>{" "}
            first; configurations reuse its parts, questions and cue card.
          </p>
        )}
        {configs.isPending ? (
          <LoadingState rows={2} />
        ) : configs.isError ? (
          <ErrorState
            title="Configurations could not be loaded"
            description={messageFor(configs.error)}
          />
        ) : configs.data.length === 0 ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            No examiner configurations yet. Candidates can start a room only for a published one.
          </p>
        ) : (
          <ul className="divide-y rounded-xl border bg-card">
            {configs.data.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <Link
                    href={`${BASE}/${c.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {c.title}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {c.test_title} · {c.body.part1_questions?.length ?? 0} Part 1 · cue card ·{" "}
                    {c.body.part3_questions?.length ?? 0} Part 3 · {c.body.difficulty}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {c.issues.length > 0 && (
                    <Badge variant="outline">{c.issues.length} issue(s)</Badge>
                  )}
                  <Badge variant={c.status === "published" ? "default" : "outline"}>
                    {c.status}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <ProfilesEditor canEdit={canEdit} />
    </div>
  );
}

function ProfileCard({ profile, canEdit }: { profile: ExaminerProfile; canEdit: boolean }) {
  const qc = useQueryClient();
  const id = useId();
  const [p, setP] = useState(profile);
  const save = useMutation({
    mutationFn: () =>
      updateProfile(profile.id, {
        name: p.name,
        title: p.title,
        personality: p.personality,
        speaking_style: p.speaking_style,
        accent: p.accent || null,
        difficulty: p.difficulty as "supportive" | "standard" | "challenging",
        avatar_tone: p.avatar_tone as "primary" | "success" | "warning" | "info",
        voice: p.voice as Record<string, string>,
        is_active: p.is_active,
      }),
    onSuccess: () => {
      toast.success("Examiner saved.");
      void qc.invalidateQueries({ queryKey: K.profiles });
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const field = (key: "name" | "title" | "accent", label: string) => (
    <div className="space-y-1">
      <Label htmlFor={`${id}-${key}`}>{label}</Label>
      <Input
        id={`${id}-${key}`}
        value={p[key] ?? ""}
        readOnly={!canEdit}
        onChange={(e) => setP({ ...p, [key]: e.target.value })}
      />
    </div>
  );
  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="flex items-center gap-3">
          <ExaminerAvatar examiner={p} />
          <div>
            <p className="font-semibold">{p.name}</p>
            <p className="text-xs text-muted-foreground">
              {p.code} ·{" "}
              {Object.keys(p.voice).length ? "voice settings stored" : "no voice configured"}
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {field("name", "Name")}
          {field("title", "Title")}
          {field("accent", "Accent / voice note")}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor={`${id}-pers`}>Personality</Label>
            <Textarea
              id={`${id}-pers`}
              rows={2}
              value={p.personality}
              readOnly={!canEdit}
              onChange={(e) => setP({ ...p, personality: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-style`}>Speaking style</Label>
            <Textarea
              id={`${id}-style`}
              rows={2}
              value={p.speaking_style}
              readOnly={!canEdit}
              onChange={(e) => setP({ ...p, speaking_style: e.target.value })}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor={`${id}-diff`}>Difficulty</Label>
            <select
              id={`${id}-diff`}
              disabled={!canEdit}
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={p.difficulty}
              onChange={(e) => setP({ ...p, difficulty: e.target.value })}
            >
              <option value="supportive">Supportive</option>
              <option value="standard">Standard</option>
              <option value="challenging">Challenging</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-tone`}>Avatar colour</Label>
            <select
              id={`${id}-tone`}
              disabled={!canEdit}
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={p.avatar_tone}
              onChange={(e) => setP({ ...p, avatar_tone: e.target.value })}
            >
              {["primary", "success", "warning", "info"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <Label className="flex items-center gap-2 pb-2 font-normal">
            <Checkbox
              checked={p.is_active}
              disabled={!canEdit}
              onCheckedChange={(v) => setP({ ...p, is_active: Boolean(v) })}
            />
            Offered to candidates
          </Label>
          {canEdit && (
            <Button className="ml-auto" onClick={() => save.mutate()} disabled={save.isPending}>
              <SaveIcon aria-hidden="true" />
              Save
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ProfilesEditor({ canEdit }: { canEdit: boolean }) {
  const profiles = useQuery({ queryKey: K.profiles, queryFn: fetchProfiles });
  return (
    <section className="space-y-3">
      <h2 className="font-heading text-xl font-semibold">Examiner profiles</h2>
      <p className="text-sm text-muted-foreground">
        Personas candidates choose from. Voice settings stay empty until the voice provider is
        connected; until then rooms run in guided mode.
      </p>
      {profiles.isPending ? (
        <LoadingState rows={2} />
      ) : profiles.isError ? (
        <ErrorState title="Profiles could not be loaded" description={messageFor(profiles.error)} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          {profiles.data.map((p) => (
            <ProfileCard key={`${p.id}-${p.name}-${p.is_active}`} profile={p} canEdit={canEdit} />
          ))}
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------ editor
type Instructions = NonNullable<ExaminerConfigBody["instructions"]>;
const INSTRUCTIONS: [keyof Instructions, string, string][] = [
  ["role", "Examiner role and personality", "Who the examiner is and how they behave."],
  ["introduction", "Introduction message", "Use {examiner} for the examiner's name."],
  ["tone", "Speaking tone", ""],
  ["question_delivery", "Question delivery", ""],
  ["follow_up_rules", "Follow-up question rules", "Used by the live examiner only."],
  ["irrelevant_answers", "Irrelevant answers", ""],
  ["silence", "Candidate stays silent", ""],
  ["to_part2", "Transition to Part 2", "Spoken before the cue card."],
  ["to_part3", "Transition to Part 3", ""],
  ["completion", "Session completion", "The examiner's closing line."],
  [
    "confidentiality",
    "Confidentiality rules",
    "Never reveal model answers or feedback during the test.",
  ],
];

function QuestionPicker({
  label,
  options,
  picked,
  readOnly,
  onChange,
}: {
  label: string;
  options: string[];
  picked: number[];
  readOnly: boolean;
  onChange: (next: number[]) => void;
}) {
  const move = (i: number, d: -1 | 1) => {
    const next = [...picked];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j]!, next[i]!];
    onChange(next);
  };
  const unused = options.map((_, i) => i).filter((i) => !picked.includes(i));
  return (
    <fieldset className="space-y-2 rounded-xl border p-4">
      <legend className="px-1 text-sm font-semibold">{label}</legend>
      {options.length === 0 && (
        <p className="text-sm text-muted-foreground">The test has no questions here.</p>
      )}
      <ol className="space-y-1">
        {picked.map((q, i) => (
          <li key={q} className="flex items-center gap-2 rounded-md bg-muted/40 px-2 py-1 text-sm">
            <span className="w-5 text-muted-foreground">{i + 1}.</span>
            <span className="flex-1">{options[q] ?? "Missing question"}</span>
            {!readOnly && (
              <>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="Move up"
                  onClick={() => move(i, -1)}
                >
                  <ArrowUpIcon aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="Move down"
                  onClick={() => move(i, 1)}
                >
                  <ArrowDownIcon aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="Remove"
                  onClick={() => onChange(picked.filter((x) => x !== q))}
                >
                  <Trash2Icon aria-hidden="true" />
                </Button>
              </>
            )}
          </li>
        ))}
      </ol>
      {!readOnly && unused.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {unused.map((i) => (
            <Button
              key={i}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onChange([...picked, i])}
            >
              <PlusIcon aria-hidden="true" />
              {options[i]!.length > 50 ? `${options[i]!.slice(0, 50)}…` : options[i]}
            </Button>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function num(v: string, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export function ExaminerConfigEditor({ configId, user }: { configId: string; user: Me }) {
  const router = useRouter();
  const qc = useQueryClient();
  const config = useQuery({
    queryKey: [...K.configs, configId],
    queryFn: () => fetchConfig(configId),
  });
  const preview = useQuery({
    queryKey: [...K.configs, configId, "preview"],
    queryFn: () => fetchPreview(configId),
  });
  const [draft, setDraft] = useState<ExaminerConfigBody | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);
  if (config.data && config.data.revision !== loaded) {
    setDraft(structuredClone(config.data.body));
    setLoaded(config.data.revision);
  }
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: K.configs });
  };
  const save = useMutation({
    mutationFn: () => saveConfig(configId, loaded!, draft!),
    onSuccess: (c) => {
      qc.setQueryData([...K.configs, configId], c);
      refresh();
      toast.success(
        c.issues.length
          ? `Saved. ${c.issues.length} issue(s) block publishing.`
          : "Saved. Ready to publish.",
      );
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const publish = useMutation({
    mutationFn: (on: boolean) => setPublished(configId, on),
    onSuccess: (c) => {
      qc.setQueryData([...K.configs, configId], c);
      refresh();
      toast.success(
        c.status === "published" ? "Published: candidates can now take this test." : "Unpublished.",
      );
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: () => deleteConfig(configId),
    onSuccess: () => {
      refresh();
      router.push(BASE);
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  if (config.isPending || !draft) return <LoadingState label="Loading configuration…" />;
  if (config.isError)
    return <ErrorState title="Configuration not found" description={messageFor(config.error)} />;
  const c = config.data;
  const canEdit = user.permissions.includes("content.edit");
  const canPublish = user.permissions.includes("content.publish");
  const readOnly = !canEdit || c.status === "published";
  const dirty = JSON.stringify(draft) !== JSON.stringify(c.body);
  const avail = (preview.data?.available ?? {}) as {
    part1?: string[];
    part2_rounding?: string[];
    part3?: string[];
    cue_card?: { prompt?: string; points?: string[] } | null;
  };
  const set = (patch: Partial<ExaminerConfigBody>) => setDraft({ ...draft, ...patch });
  const timing = draft.timing!;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href={BASE} className="text-sm text-muted-foreground hover:underline">
            ← AI Examiner Configuration
          </Link>
          <h1 className="font-heading text-2xl font-semibold">{c.title}</h1>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={c.status === "published" ? "default" : "outline"}>{c.status}</Badge>
            Built on “{c.test_title}”
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!readOnly && (
            <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
              {save.isPending ? (
                <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
              ) : (
                <SaveIcon aria-hidden="true" />
              )}
              Save draft
            </Button>
          )}
          {canPublish && c.status !== "published" && (
            <Button
              variant="outline"
              onClick={() => publish.mutate(true)}
              disabled={dirty || c.issues.length > 0 || publish.isPending}
            >
              Publish
            </Button>
          )}
          {canPublish && c.status === "published" && (
            <Button
              variant="outline"
              onClick={() => publish.mutate(false)}
              disabled={publish.isPending}
            >
              Unpublish to edit
            </Button>
          )}
          {canEdit && c.status !== "published" && (
            <Button variant="ghost" onClick={() => remove.mutate()} disabled={remove.isPending}>
              Delete
            </Button>
          )}
        </div>
      </div>
      {c.issues.length > 0 && (
        <ul
          role="alert"
          className="list-disc space-y-1 rounded-xl border border-warning/40 bg-warning/10 p-4 pl-8 text-sm"
        >
          {c.issues.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-6 xl:grid-cols-[1fr_26rem]">
        <div className="space-y-6">
          <Card>
            <CardContent className="grid gap-4 pt-6 md:grid-cols-3">
              <div className="space-y-1 md:col-span-3">
                <Label htmlFor="cfg-title">Configuration title</Label>
                <Input
                  id="cfg-title"
                  value={draft.title}
                  readOnly={readOnly}
                  maxLength={200}
                  onChange={(e) => set({ title: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cfg-diff">Difficulty</Label>
                <select
                  id="cfg-diff"
                  disabled={readOnly}
                  className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                  value={draft.difficulty}
                  onChange={(e) =>
                    set({ difficulty: e.target.value as ExaminerConfigBody["difficulty"] })
                  }
                >
                  <option value="supportive">Supportive</option>
                  <option value="standard">Standard</option>
                  <option value="challenging">Challenging</option>
                </select>
              </div>
              <fieldset className="space-y-1 md:col-span-2">
                <legend className="text-sm font-medium">Evaluation criteria</legend>
                <div className="flex flex-wrap gap-4">
                  {(["FC", "LR", "GRA", "PR"] as const).map((k) => (
                    <Label key={k} className="flex items-center gap-2 font-normal">
                      <Checkbox
                        checked={draft.criteria!.includes(k)}
                        disabled={readOnly}
                        onCheckedChange={(v) =>
                          set({
                            criteria: v
                              ? [...draft.criteria!, k]
                              : draft.criteria!.filter((x) => x !== k),
                          })
                        }
                      />
                      {
                        {
                          FC: "Fluency & coherence",
                          LR: "Lexical resource",
                          GRA: "Grammar",
                          PR: "Pronunciation",
                        }[k]
                      }
                    </Label>
                  ))}
                </div>
              </fieldset>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-4 pt-6">
              <h2 className="font-heading text-lg font-semibold">Timing and follow-ups</h2>
              <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {(
                  [
                    ["part1_answer_seconds", "Part 1 answer (s)"],
                    ["part2_prep_seconds", "Part 2 preparation (s)"],
                    ["part2_speak_seconds", "Part 2 long turn (s)"],
                    ["part3_answer_seconds", "Part 3 answer (s)"],
                    ["max_total_minutes", "Whole test (min)"],
                  ] as const
                ).map(([key, label]) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={`t-${key}`}>{label}</Label>
                    <Input
                      id={`t-${key}`}
                      type="number"
                      value={timing[key]}
                      readOnly={readOnly}
                      onChange={(e) =>
                        set({ timing: { ...timing, [key]: num(e.target.value, timing[key] ?? 0) } })
                      }
                    />
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-end gap-4">
                <Label className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={draft.follow_ups!.enabled}
                    disabled={readOnly}
                    onCheckedChange={(v) =>
                      set({ follow_ups: { ...draft.follow_ups!, enabled: Boolean(v) } })
                    }
                  />
                  Ask follow-up questions
                </Label>
                <Label className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={draft.follow_ups!.use_candidate_answers}
                    disabled={readOnly}
                    onCheckedChange={(v) =>
                      set({
                        follow_ups: { ...draft.follow_ups!, use_candidate_answers: Boolean(v) },
                      })
                    }
                  />
                  Build Part 3 follow-ups on the candidate&apos;s answers
                </Label>
                <div className="space-y-1">
                  <Label htmlFor="fu-max">Max follow-ups per question</Label>
                  <Input
                    id="fu-max"
                    type="number"
                    min={0}
                    max={3}
                    className="w-24"
                    value={draft.follow_ups!.max_per_question}
                    readOnly={readOnly}
                    onChange={(e) =>
                      set({
                        follow_ups: {
                          ...draft.follow_ups!,
                          max_per_question: num(e.target.value, 1),
                        },
                      })
                    }
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Follow-ups are generated by the live AI examiner. In guided mode (no voice provider)
                only the configured questions are asked.
              </p>
            </CardContent>
          </Card>
          <QuestionPicker
            label="Part 1 · introduction and interview"
            options={avail.part1 ?? []}
            picked={draft.part1_questions!}
            readOnly={readOnly}
            onChange={(v) => set({ part1_questions: v })}
          />
          <fieldset className="space-y-2 rounded-xl border p-4">
            <legend className="px-1 text-sm font-semibold">
              Part 2 · cue card (from the test)
            </legend>
            {avail.cue_card?.prompt ? (
              <div className="rounded-lg border-2 border-dashed p-3 text-sm">
                <p className="font-medium">{avail.cue_card.prompt}</p>
                <ul className="list-disc pl-5">
                  {(avail.cue_card.points ?? []).map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-destructive">
                The test has no cue card. Add it in Speaking Management.
              </p>
            )}
          </fieldset>
          <QuestionPicker
            label="Part 2 · rounding-off questions"
            options={avail.part2_rounding ?? []}
            picked={draft.part2_rounding!}
            readOnly={readOnly}
            onChange={(v) => set({ part2_rounding: v })}
          />
          <QuestionPicker
            label="Part 3 · discussion"
            options={avail.part3 ?? []}
            picked={draft.part3_questions!}
            readOnly={readOnly}
            onChange={(v) => set({ part3_questions: v })}
          />
          <Card>
            <CardContent className="space-y-4 pt-6">
              <h2 className="font-heading text-lg font-semibold">Examiner instructions</h2>
              <div className="grid gap-4 md:grid-cols-2">
                {INSTRUCTIONS.map(([key, label, hint]) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={`ins-${key}`}>{label}</Label>
                    <Textarea
                      id={`ins-${key}`}
                      rows={3}
                      value={draft.instructions![key] ?? ""}
                      readOnly={readOnly}
                      maxLength={3000}
                      onChange={(e) =>
                        set({ instructions: { ...draft.instructions!, [key]: e.target.value } })
                      }
                    />
                    {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
        <aside className="space-y-3 xl:sticky xl:top-20 xl:self-start">
          <h2 className="flex items-center gap-2 font-heading text-lg font-semibold">
            <EyeIcon className="size-5" aria-hidden="true" />
            Candidate preview{" "}
            {dirty && (
              <span className="text-xs font-normal text-muted-foreground">(save to refresh)</span>
            )}
          </h2>
          {preview.isPending ? (
            <LoadingState rows={3} />
          ) : preview.isError ? (
            <ErrorState title="Preview unavailable" description={messageFor(preview.error)} />
          ) : (
            <div className="max-h-[70vh] space-y-2 overflow-y-auto rounded-2xl border bg-card p-4 text-sm">
              <ol className="space-y-2">
                {preview.data.plan.map((s) => (
                  <li
                    key={String(s.step)}
                    className={cn(
                      "rounded-lg px-3 py-2",
                      s.role === "examiner"
                        ? "bg-muted"
                        : "ml-6 border border-dashed text-muted-foreground",
                    )}
                  >
                    <p className="text-[0.6875rem] font-semibold tracking-wide uppercase">
                      Part {String(s.part_no)} ·{" "}
                      {s.role === "examiner"
                        ? String(s.kind)
                        : `candidate answers (${String(s.answer_seconds)}s${Number(s.prep_seconds) ? `, ${String(s.prep_seconds)}s prep` : ""})`}
                    </p>
                    {s.role === "examiner" && <p>{String(s.text)}</p>}
                  </li>
                ))}
              </ol>
              <details>
                <summary className="cursor-pointer font-medium">
                  Conversation rules given to the examiner
                </summary>
                <ol className="mt-2 list-decimal pl-5">
                  {preview.data.rules.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ol>
              </details>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

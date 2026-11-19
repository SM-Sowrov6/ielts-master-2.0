"use client";

import { useQuery } from "@tanstack/react-query";
import { useId, type ReactNode } from "react";

import { Input } from "@/components/ui/input";
import {
  fetchImage,
  type ContentGroup,
  type ContentQuestion,
  type Option,
  type Response,
} from "@/lib/exam/api";
import { countWords } from "@/lib/exam/responses";
import { docToText } from "@/lib/admin/richtext";
import { cn } from "@/lib/utils";

/**
 * Candidate renderer for one question group, driven by the handler's student view
 * (`answer_format`): "option" = one label per question, "options" = choose N labels,
 * "text" = typed answer (optionally inside a completion template with numbered blanks).
 * All 13 Listening types map onto these three families (backend question-type registry).
 */
export type GroupProps = {
  group: ContentGroup;
  answers: Readonly<Record<string, Response>>;
  onChange: (questionId: string, response: Response) => void;
  disabled: boolean;
  attemptId: string;
  sectionNo: number;
  groupNo: number;
};

function label(q: ContentQuestion): string {
  return q.number_from === q.number_to ? `${q.number_from}` : `${q.number_from}–${q.number_to}`;
}

function Stem({ stem }: { stem: unknown }) {
  const text = docToText(stem);
  return text ? <p className="whitespace-pre-line">{text}</p> : null;
}

/** TRUE/FALSE/NOT GIVEN style types: the server sends the fixed choices as group options. */
const FIXED_CHOICE = new Set(["tfng", "ynng"]);

function OptionBox({ options, title }: { options: Option[]; title: string }) {
  if (!options.length) return null;
  return (
    <div className="rounded-lg border bg-muted/40 p-3">
      <p className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </p>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {options.map((o) => (
          <div key={o.label} className="flex gap-2">
            <dt className="w-6 shrink-0 font-semibold">{o.label}</dt>
            <dd>{o.text}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function GroupImage({
  attemptId,
  sectionNo,
  groupNo,
}: {
  attemptId: string;
  sectionNo: number;
  groupNo: number;
}) {
  const image = useQuery({
    queryKey: ["attempt-image", attemptId, sectionNo, groupNo],
    queryFn: () => fetchImage(attemptId, sectionNo, groupNo),
    staleTime: 20 * 60_000,
  });
  if (image.isPending)
    return <div className="h-48 animate-pulse rounded-lg bg-muted" aria-hidden="true" />;
  if (image.isError)
    return <p className="text-sm text-destructive">The image could not be loaded.</p>;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
    <img
      src={image.data.url}
      alt="Map, plan or diagram for these questions"
      className="max-h-96 w-full rounded-lg border object-contain"
    />
  );
}

function Question({ q, children, id }: { q: ContentQuestion; children: ReactNode; id: string }) {
  return (
    <li
      id={`question-${q.number_from}`}
      className="scroll-mt-24 rounded-lg border bg-card p-3"
      aria-labelledby={id}
    >
      <div className="flex gap-3">
        <span
          id={id}
          className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/10 text-sm font-semibold text-primary tabular-nums"
        >
          <span className="sr-only">{`Question ${label(q)}`}</span>
          <span aria-hidden="true">{label(q)}</span>
        </span>
        <div className="min-w-0 flex-1 space-y-2 text-sm">{children}</div>
      </div>
    </li>
  );
}

function TextAnswer({
  q,
  value,
  onChange,
  disabled,
  wordLimit,
  labelledBy,
}: {
  q: ContentQuestion;
  value: string;
  onChange: (text: string) => void;
  disabled: boolean;
  wordLimit: number | null;
  labelledBy: string;
}) {
  const over = wordLimit !== null && countWords(value) > wordLimit;
  const hintId = `hint-${q.id}`;
  return (
    <div className="space-y-1">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        maxLength={200}
        autoComplete="off"
        spellCheck={false}
        aria-labelledby={labelledBy}
        aria-describedby={over ? hintId : undefined}
        aria-invalid={over || undefined}
        className="max-w-sm"
        data-question={q.number_from}
      />
      {over && (
        <p id={hintId} className="text-xs text-destructive">
          More than {wordLimit} word{wordLimit === 1 ? "" : "s"}: an answer over the limit scores
          zero.
        </p>
      )}
    </div>
  );
}

type Blank = { type: string; text?: string; attrs?: Record<string, unknown>; content?: Blank[] };

/** Completion template (ProseMirror JSON with numbered `blank` nodes) with inline answer boxes. */
function Template({ doc, render }: { doc: Blank; render: (number: number) => ReactNode }) {
  const walk = (node: Blank, key: string): ReactNode => {
    const kids = (node.content ?? []).map((c, i) => walk(c, `${key}.${i}`));
    switch (node.type) {
      case "doc":
        return (
          <div key={key} className="space-y-2">
            {kids}
          </div>
        );
      case "paragraph":
        return <p key={key}>{kids}</p>;
      case "heading":
        return (
          <p key={key} className="font-semibold">
            {kids}
          </p>
        );
      case "bulletList":
        return (
          <ul key={key} className="list-disc space-y-1 pl-5">
            {kids}
          </ul>
        );
      case "orderedList":
        return (
          <ol key={key} className="list-decimal space-y-1 pl-5">
            {kids}
          </ol>
        );
      case "listItem":
        return <li key={key}>{kids}</li>;
      case "table":
        return (
          <div key={key} className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <tbody>{kids}</tbody>
            </table>
          </div>
        );
      case "tableRow":
        return <tr key={key}>{kids}</tr>;
      case "tableHeader":
        return (
          <th key={key} className="border bg-muted/50 p-2 text-left">
            {kids}
          </th>
        );
      case "tableCell":
        return (
          <td key={key} className="border p-2 align-top">
            {kids}
          </td>
        );
      case "hardBreak":
        return <br key={key} />;
      case "blank":
        return (
          <span key={key} className="mx-1 inline-block align-middle">
            {render(Number(node.attrs?.number))}
          </span>
        );
      case "text":
        return <span key={key}>{node.text}</span>;
      default:
        return <span key={key}>{kids}</span>;
    }
  };
  return <>{walk(doc, "t")}</>;
}

export function QuestionGroup({
  group,
  answers,
  onChange,
  disabled,
  attemptId,
  sectionNo,
  groupNo,
}: GroupProps) {
  const base = useId();
  const config = group.config ?? {};
  const wordLimit = typeof config.word_limit === "number" ? config.word_limit : null;
  const numbers = group.questions.flatMap((q) => [q.number_from, q.number_to]);
  const range = `Questions ${Math.min(...numbers)}–${Math.max(...numbers)}`;
  const groupOptions = group.options ?? [];
  const template = config.template as Blank | null | undefined;
  const byNumber = new Map(group.questions.map((q) => [q.number_from, q]));

  const textOf = (q: ContentQuestion) => {
    const r = answers[q.id];
    return r && "text" in r ? r.text : "";
  };
  const setText = (q: ContentQuestion, text: string) => onChange(q.id, text ? { text } : null);

  let body: ReactNode;
  if (group.answer_format === "text" && template) {
    body = (
      <div className="rounded-lg border bg-card p-4 text-sm">
        <Template
          doc={template}
          render={(n) => {
            const q = byNumber.get(n);
            if (!q) return <span>[{n}]</span>;
            return (
              <span className="inline-flex items-center gap-1">
                <span id={`${base}-${q.number_from}`} className="font-semibold tabular-nums">
                  <span className="sr-only">{`Question ${n}`}</span>
                  <span aria-hidden="true">{n}</span>
                </span>
                <TextAnswer
                  q={q}
                  value={textOf(q)}
                  onChange={(t) => setText(q, t)}
                  disabled={disabled}
                  wordLimit={wordLimit}
                  labelledBy={`${base}-${q.number_from}`}
                />
              </span>
            );
          }}
        />
      </div>
    );
  } else {
    body = (
      <ol className="space-y-3">
        {group.questions.map((q) => {
          const labelId = `${base}-${q.number_from}`;
          const response = answers[q.id];
          if (group.answer_format === "text") {
            return (
              <Question key={q.id} q={q} id={labelId}>
                <Stem stem={q.stem} />
                <TextAnswer
                  q={q}
                  value={textOf(q)}
                  onChange={(t) => setText(q, t)}
                  disabled={disabled}
                  wordLimit={wordLimit}
                  labelledBy={labelId}
                />
              </Question>
            );
          }
          if (group.answer_format === "options") {
            const chosen = response && "choices" in response ? response.choices : [];
            const options = q.options?.length ? q.options : groupOptions;
            return (
              <Question key={q.id} q={q} id={labelId}>
                <Stem stem={q.stem} />
                <fieldset className="space-y-1" aria-labelledby={labelId}>
                  <legend className="text-xs text-muted-foreground">
                    Choose {q.marks} ({chosen.length} selected)
                  </legend>
                  {options.map((o) => {
                    const checked = chosen.includes(o.label);
                    const full = !checked && chosen.length >= q.marks;
                    return (
                      <label
                        key={o.label}
                        className={cn(
                          "flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted",
                          checked && "bg-primary/5",
                          (disabled || full) && "cursor-not-allowed opacity-60",
                        )}
                      >
                        <input
                          type="checkbox"
                          className="mt-0.5 size-4 accent-[var(--primary)]"
                          checked={checked}
                          disabled={disabled || full}
                          data-question={q.number_from}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...chosen, o.label]
                              : chosen.filter((c) => c !== o.label);
                            onChange(q.id, next.length ? { choices: [...next].sort() } : null);
                          }}
                        />
                        <span>
                          <span className="font-semibold">{o.label}</span> {o.text}
                        </span>
                      </label>
                    );
                  })}
                </fieldset>
              </Question>
            );
          }
          // "option": one label per question.
          const choice = response && "choice" in response ? response.choice : "";
          const radios = q.options?.length
            ? q.options
            : FIXED_CHOICE.has(group.question_type)
              ? groupOptions
              : null;
          if (radios) {
            return (
              <Question key={q.id} q={q} id={labelId}>
                <Stem stem={q.stem} />
                <fieldset className="space-y-1" aria-labelledby={labelId}>
                  {radios.map((o) => (
                    <label
                      key={o.label}
                      className={cn(
                        "flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted",
                        choice === o.label && "bg-primary/5",
                        disabled && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <input
                        type="radio"
                        name={`q-${q.id}`}
                        className="mt-0.5 size-4 accent-[var(--primary)]"
                        checked={choice === o.label}
                        disabled={disabled}
                        data-question={q.number_from}
                        onChange={() => onChange(q.id, { choice: o.label })}
                      />
                      <span>
                        <span className="font-semibold">{o.label}</span>
                        {o.text !== o.label && ` ${o.text}`}
                      </span>
                    </label>
                  ))}
                </fieldset>
              </Question>
            );
          }
          return (
            <Question key={q.id} q={q} id={labelId}>
              <Stem stem={q.stem} />
              <select
                className="h-9 w-40 rounded-md border bg-background px-2 text-sm disabled:opacity-60"
                value={choice}
                disabled={disabled}
                aria-labelledby={labelId}
                data-question={q.number_from}
                onChange={(e) => onChange(q.id, e.target.value ? { choice: e.target.value } : null)}
              >
                <option value="">Choose…</option>
                {groupOptions.map((o) => (
                  <option key={o.label} value={o.label}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Question>
          );
        })}
      </ol>
    );
  }

  return (
    <section className="space-y-3" aria-label={range}>
      <div className="space-y-1">
        <h2 className="text-sm font-semibold">{range}</h2>
        {group.instructions && (
          <p className="text-sm text-muted-foreground">{group.instructions}</p>
        )}
      </div>
      {group.has_image && (
        <GroupImage attemptId={attemptId} sectionNo={sectionNo} groupNo={groupNo} />
      )}
      {group.answer_format !== "text" &&
        !FIXED_CHOICE.has(group.question_type) &&
        !group.questions.some((q) => q.options?.length) && (
          <OptionBox options={groupOptions} title="Options" />
        )}
      {group.answer_format === "text" && groupOptions.length > 0 && (
        <OptionBox options={groupOptions} title="Word bank" />
      )}
      {body}
    </section>
  );
}

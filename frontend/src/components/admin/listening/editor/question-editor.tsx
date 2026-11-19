"use client";

import { ArrowDownIcon, ArrowUpIcon, CopyIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useId } from "react";

import {
  explanationFromText,
  multiAnswers,
  nextLabel,
  optionAnswer,
  optionLabels,
  splitAlternatives,
  stemFromText,
  textAnswer,
  usesOptions,
  type AnswerMode,
} from "@/components/admin/listening/editor/model";
import { QUESTION_TYPES } from "@/components/admin/listening/labels";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { GroupDoc, Issue, OptionDoc, QuestionDoc } from "@/lib/admin/listening-api";
import { docToText } from "@/lib/admin/richtext";
import { useModuleInfo } from "@/lib/admin/module";

export function IssueList({ issues }: { issues: readonly Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1 text-sm" aria-label="Validation messages">
      {issues.map((issue, i) => (
        <li
          key={`${issue.code}-${i}`}
          className={issue.severity === "error" ? "text-destructive" : "text-muted-foreground"}
        >
          <span className="font-medium">{issue.severity === "error" ? "Error" : "Warning"}:</span>{" "}
          {issue.message}
        </li>
      ))}
    </ul>
  );
}

export function OptionsEditor({
  legend,
  options,
  readOnly,
  onChange,
}: {
  legend: string;
  options: readonly OptionDoc[];
  readOnly: boolean;
  onChange: (options: OptionDoc[]) => void;
}) {
  const id = useId();
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{legend}</legend>
      <ul className="space-y-2">
        {options.map((option, index) => (
          <li key={index} className="flex items-center gap-2">
            <Label htmlFor={`${id}-l${index}`} className="sr-only">
              Option {index + 1} letter
            </Label>
            <Input
              id={`${id}-l${index}`}
              className="w-16 text-center"
              value={option.label}
              maxLength={20}
              readOnly={readOnly}
              onChange={(e) =>
                onChange(options.map((o, i) => (i === index ? { ...o, label: e.target.value } : o)))
              }
            />
            <Label htmlFor={`${id}-t${index}`} className="sr-only">
              Option {option.label || index + 1} text
            </Label>
            <Input
              id={`${id}-t${index}`}
              value={option.text}
              maxLength={2000}
              readOnly={readOnly}
              placeholder="Option text"
              onChange={(e) =>
                onChange(options.map((o, i) => (i === index ? { ...o, text: e.target.value } : o)))
              }
            />
            {!readOnly && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove option ${option.label}`}
                onClick={() => onChange(options.filter((_, i) => i !== index))}
              >
                <Trash2Icon aria-hidden="true" />
              </Button>
            )}
          </li>
        ))}
      </ul>
      {!readOnly && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...options, { label: nextLabel(options), text: "" }])}
        >
          <PlusIcon aria-hidden="true" />
          Add option
        </Button>
      )}
    </fieldset>
  );
}

function TextAnswerEditor({
  question,
  readOnly,
  onChange,
}: {
  question: QuestionDoc;
  readOnly: boolean;
  onChange: (q: QuestionDoc) => void;
}) {
  const id = useId();
  const answer = question.answers[0];
  const alternatives = answer ? splitAlternatives(answer.value) : [];
  const values = alternatives.length ? alternatives : [""];
  const mode = (answer?.match_mode as AnswerMode | undefined) ?? "text";
  const set = (next: string[], nextMode: AnswerMode = mode) =>
    onChange({ ...question, answers: textAnswer(next, nextMode) });
  return (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-[1fr_10rem]">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-main`}>Correct answer</Label>
          <Input
            id={`${id}-main`}
            value={values[0] ?? ""}
            readOnly={readOnly}
            maxLength={500}
            aria-describedby={`${id}-help`}
            onChange={(e) => set([e.target.value, ...values.slice(1)])}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-mode`}>Answer type</Label>
          <Select
            value={mode}
            onValueChange={(v) => set(values, v as AnswerMode)}
            disabled={readOnly}
          >
            <SelectTrigger id={`${id}-mode`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="text">Words</SelectItem>
              <SelectItem value="numeric">Number</SelectItem>
              <SelectItem value="time">Time</SelectItem>
              <SelectItem value="date">Date</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <p id={`${id}-help`} className="text-xs text-muted-foreground">
        Optional words in brackets, e.g. <code>(the) library</code>; spelling variants with a slash,
        e.g. <code>colour/color</code>. Spelling, case, hyphen and number rules follow the
        type&apos;s normalisation settings.
      </p>
      {values.slice(1).map((value, index) => (
        <div key={index} className="flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={`${id}-alt${index}`}>Accepted alternative {index + 1}</Label>
            <Input
              id={`${id}-alt${index}`}
              value={value}
              readOnly={readOnly}
              maxLength={500}
              onChange={(e) => set(values.map((v, i) => (i === index + 1 ? e.target.value : v)))}
            />
          </div>
          {!readOnly && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Remove alternative ${index + 1}`}
              onClick={() => set(values.filter((_, i) => i !== index + 1))}
            >
              <Trash2Icon aria-hidden="true" />
            </Button>
          )}
        </div>
      ))}
      {!readOnly && (
        <Button type="button" variant="outline" size="sm" onClick={() => set([...values, ""])}>
          <PlusIcon aria-hidden="true" />
          Add accepted alternative
        </Button>
      )}
    </div>
  );
}

export function QuestionEditor({
  group,
  question,
  index,
  count,
  issues,
  readOnly,
  onChange,
  onMove,
  onDuplicate,
  onRemove,
}: {
  group: GroupDoc;
  question: QuestionDoc;
  index: number;
  count: number;
  issues: readonly Issue[];
  readOnly: boolean;
  onChange: (q: QuestionDoc) => void;
  onMove: (delta: -1 | 1) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const id = useId();
  const { passages } = useModuleInfo();
  const meta = QUESTION_TYPES[group.question_type];
  const multi = meta?.family === "multi_option";
  const option = usesOptions(group) && !multi;
  const to = question.number_to ?? question.number_from;
  const marks = to - question.number_from + 1;
  const labels = optionLabels(group, question).filter(Boolean);
  const selected = question.answers.map((a) => a.value);
  const label =
    marks > 1 ? `Questions ${question.number_from}–${to}` : `Question ${question.number_from}`;
  const hasError = issues.some((i) => i.severity === "error");

  return (
    <li
      className={`space-y-3 rounded-lg border p-3 ${hasError ? "border-destructive/50" : ""}`}
      aria-labelledby={`${id}-title`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 id={`${id}-title`} className="text-sm font-semibold">
          {label}
          {multi && <span className="font-normal text-muted-foreground"> · {marks} marks</span>}
        </h4>
        {!readOnly && (
          <div className="flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Move ${label} up`}
              disabled={index === 0}
              onClick={() => onMove(-1)}
            >
              <ArrowUpIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Move ${label} down`}
              disabled={index === count - 1}
              onClick={() => onMove(1)}
            >
              <ArrowDownIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Duplicate ${label}`}
              onClick={onDuplicate}
            >
              <CopyIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Delete ${label}`}
              onClick={onRemove}
              disabled={count === 1}
            >
              <Trash2Icon aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-[8rem_8rem_1fr]">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-from`}>{multi ? "First number" : "Number"}</Label>
          <Input
            id={`${id}-from`}
            type="number"
            min={1}
            max={40}
            value={question.number_from}
            readOnly={readOnly}
            onChange={(e) => {
              const from = Math.max(1, Math.min(40, Number(e.target.value) || 1));
              onChange({
                ...question,
                number_from: from,
                number_to: multi ? Math.min(40, from + marks - 1) : null,
              });
            }}
          />
        </div>
        {multi && (
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-to`}>Last number</Label>
            <Input
              id={`${id}-to`}
              type="number"
              min={question.number_from}
              max={40}
              value={to}
              readOnly={readOnly}
              onChange={(e) =>
                onChange({
                  ...question,
                  number_to: Math.max(
                    question.number_from,
                    Math.min(40, Number(e.target.value) || question.number_from),
                  ),
                })
              }
            />
          </div>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-stem`}>Question prompt</Label>
        <Textarea
          id={`${id}-stem`}
          rows={2}
          value={docToText(question.stem)}
          readOnly={readOnly}
          placeholder={
            meta?.family === "text"
              ? "e.g. Name of the hotel: ________"
              : "e.g. Why did the speaker…?"
          }
          onChange={(e) => onChange({ ...question, stem: stemFromText(e.target.value) })}
        />
      </div>
      {meta?.questionOptions && (
        <OptionsEditor
          legend="Answer options"
          options={question.options ?? []}
          readOnly={readOnly}
          onChange={(options) => onChange({ ...question, options })}
        />
      )}
      {multi ? (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Correct answers (choose {marks})</legend>
          <div className="flex flex-wrap gap-3">
            {labels.map((l) => {
              const checked = selected.includes(l);
              return (
                <Label key={l} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={checked}
                    disabled={readOnly}
                    onCheckedChange={(value) => {
                      const next = value ? [...selected, l] : selected.filter((s) => s !== l);
                      onChange({
                        ...question,
                        answers: multiAnswers(labels.filter((x) => next.includes(x))),
                      });
                    }}
                  />
                  {l}
                </Label>
              );
            })}
          </div>
          {!labels.length && (
            <p className="text-sm text-muted-foreground">Add options to the group first.</p>
          )}
        </fieldset>
      ) : option ? (
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-key`}>Correct answer</Label>
          <Select
            value={selected[0] ?? ""}
            onValueChange={(v) => onChange({ ...question, answers: optionAnswer(v) })}
            disabled={readOnly || !labels.length}
          >
            <SelectTrigger id={`${id}-key`} className="w-40">
              <SelectValue placeholder={labels.length ? "Choose" : "Add options first"} />
            </SelectTrigger>
            <SelectContent>
              {labels.map((l) => (
                <SelectItem key={l} value={l}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <TextAnswerEditor question={question} readOnly={readOnly} onChange={onChange} />
      )}
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-expl`}>Explanation</Label>
        <Textarea
          id={`${id}-expl`}
          rows={2}
          value={docToText(question.explanation?.body)}
          readOnly={readOnly}
          placeholder="Why this is the answer (shown to candidates after review)."
          onChange={(e) =>
            onChange({
              ...question,
              explanation: explanationFromText(e.target.value, question.explanation),
            })
          }
        />
      </div>
      {passages && (
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-evidence`}>Evidence paragraph</Label>
          <Input
            id={`${id}-evidence`}
            className="w-24"
            value={question.explanation?.evidence_paragraph_label ?? ""}
            readOnly={readOnly}
            maxLength={4}
            placeholder="e.g. C"
            onChange={(e) => {
              const label = e.target.value.trim().toUpperCase() || null;
              const body = question.explanation?.body ?? null;
              const hasBody = docToText(body).trim().length > 0;
              onChange({
                ...question,
                explanation:
                  label || hasBody
                    ? {
                        body: body ?? { type: "doc", content: [] },
                        audio_start_ms: question.explanation?.audio_start_ms ?? null,
                        audio_end_ms: question.explanation?.audio_end_ms ?? null,
                        evidence_paragraph_label: label,
                      }
                    : null,
              });
            }}
          />
        </div>
      )}
      <IssueList issues={issues} />
    </li>
  );
}

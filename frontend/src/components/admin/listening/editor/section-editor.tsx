"use client";

import { ArrowDownIcon, ArrowUpIcon, CopyIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";

import { MediaField } from "@/components/admin/listening/editor/media-field";
import {
  cloneGroup,
  cloneQuestion,
  move,
  newGroup,
  swapNumbers,
  newQuestion,
  nextNumber,
  questionNumbers,
  sectionRange,
} from "@/components/admin/listening/editor/model";
import {
  IssueList,
  OptionsEditor,
  QuestionEditor,
} from "@/components/admin/listening/editor/question-editor";
import { QUESTION_TYPES, SECTION_KINDS, typeLabel } from "@/components/admin/listening/labels";
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
import type { Asset, GroupDoc, Issue, SectionDoc } from "@/lib/admin/listening-api";
import { issuesFor } from "@/lib/admin/issues";
import { PassageEditor } from "@/components/admin/listening/editor/passage-editor";
import { useModuleInfo } from "@/lib/admin/module";

type Shared = {
  testId: string;
  assets: ReadonlyMap<string, Asset>;
  readOnly: boolean;
  issues: readonly Issue[];
  allSections: readonly SectionDoc[];
  onAsset: (asset: Asset) => void;
  types: readonly string[];
};

function GroupEditor({
  sectionNo,
  group,
  index,
  count,
  shared,
  onChange,
  onMove,
  onDuplicate,
  onRemove,
}: {
  sectionNo: number;
  group: GroupDoc;
  index: number;
  count: number;
  shared: Shared;
  onChange: (g: GroupDoc) => void;
  onMove: (delta: -1 | 1) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const id = useId();
  const meta = QUESTION_TYPES[group.question_type];
  const config = (group.config ?? {}) as Record<string, unknown>;
  const optionFormat = Boolean(meta?.optionFormat) && config.answer_format === "option";
  const showGroupOptions = Boolean(meta?.groupOptions) || optionFormat;
  const { readOnly } = shared;
  const setConfig = (patch: Record<string, unknown>) => {
    const next: Record<string, unknown> = { ...config, ...patch };
    for (const [k, v] of Object.entries(next)) if (v === undefined || v === null) delete next[k];
    onChange({ ...group, config: next });
  };
  const groupIssues = issuesFor(shared.issues, { section: sectionNo, group: index });
  const numbers = group.questions.flatMap(questionNumbers);
  const range = numbers.length
    ? `Q${Math.min(...numbers)}–${Math.max(...numbers)}`
    : "no questions";

  return (
    <li
      className="space-y-4 rounded-xl border bg-card p-4 shadow-elevation-1"
      aria-labelledby={`${id}-h`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`${id}-h`} className="font-heading text-sm font-semibold">
          Group {index + 1}: {typeLabel(group.question_type)}{" "}
          <span className="font-normal text-muted-foreground">({range})</span>
        </h3>
        {!readOnly && (
          <div className="flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Move group ${index + 1} up`}
              disabled={index === 0}
              onClick={() => onMove(-1)}
            >
              <ArrowUpIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Move group ${index + 1} down`}
              disabled={index === count - 1}
              onClick={() => onMove(1)}
            >
              <ArrowDownIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Duplicate group ${index + 1}`}
              onClick={onDuplicate}
            >
              <CopyIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Delete group ${index + 1}`}
              onClick={onRemove}
            >
              <Trash2Icon aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-type`}>Question type</Label>
          <Select
            value={group.question_type}
            disabled={readOnly}
            onValueChange={(type) =>
              onChange({
                ...newGroup(type, group.questions[0]?.number_from ?? 1),
                instructions: group.instructions,
                questions: group.questions.map((q) => ({
                  ...newQuestion(type, q.number_from),
                  lineage_id: q.lineage_id,
                  stem: q.stem,
                  explanation: q.explanation,
                })),
              })
            }
          >
            <SelectTrigger id={`${id}-type`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {shared.types.map((t) => (
                <SelectItem key={t} value={t}>
                  {typeLabel(t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!readOnly && (
            <p className="text-xs text-muted-foreground">
              Changing the type resets answers and options.
            </p>
          )}
        </div>
        {meta?.family === "text" && !optionFormat && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-limit`}>Word limit</Label>
              <Select
                value={config.word_limit ? String(config.word_limit) : "none"}
                disabled={readOnly}
                onValueChange={(v) =>
                  setConfig({ word_limit: v === "none" ? undefined : Number(v) })
                }
              >
                <SelectTrigger id={`${id}-limit`} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No limit</SelectItem>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n} word{n > 1 ? "s" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Label className="mt-6 flex items-center gap-2 font-normal">
              <Checkbox
                checked={Boolean(config.allow_number)}
                disabled={readOnly}
                onCheckedChange={(v) => setConfig({ allow_number: v ? true : undefined })}
              />
              &ldquo;and/or a number&rdquo;
            </Label>
          </div>
        )}
      </div>
      {meta?.optionFormat && (
        <Label className="flex items-center gap-2 font-normal">
          <Checkbox
            checked={optionFormat}
            disabled={readOnly}
            onCheckedChange={(v) =>
              onChange({
                ...group,
                config: v ? { answer_format: "option" } : { word_limit: 2 },
                options: v
                  ? group.options?.length
                    ? group.options
                    : [{ label: "A", text: "" }]
                  : [],
                questions: group.questions.map((q) => ({ ...q, answers: [] })),
              })
            }
          />
          Candidates choose from a list of options (word bank) instead of writing words
        </Label>
      )}
      {meta?.family === "option" && meta.groupOptions && (
        <Label className="flex items-center gap-2 font-normal">
          <Checkbox
            checked={config.options_reusable !== false}
            disabled={readOnly}
            onCheckedChange={(v) => setConfig({ options_reusable: v ? undefined : false })}
          />
          An option may be the answer to more than one question
        </Label>
      )}
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-instr`}>Instructions</Label>
        <Textarea
          id={`${id}-instr`}
          rows={2}
          value={group.instructions ?? ""}
          readOnly={readOnly}
          maxLength={2000}
          onChange={(e) => onChange({ ...group, instructions: e.target.value || null })}
        />
      </div>
      {meta?.image && (
        <MediaField
          label="Map / plan / diagram image (optional)"
          kind="image"
          testId={shared.testId}
          assetId={group.image_asset_id}
          assets={shared.assets}
          readOnly={readOnly}
          onUploaded={(asset) => {
            shared.onAsset(asset);
            onChange({ ...group, image_asset_id: asset.id });
          }}
          onRemove={() => onChange({ ...group, image_asset_id: null })}
        />
      )}
      {showGroupOptions && (
        <OptionsEditor
          legend={optionFormat ? "Word bank" : "Options shared by these questions"}
          options={group.options ?? []}
          readOnly={readOnly}
          onChange={(options) => onChange({ ...group, options })}
        />
      )}
      <IssueList issues={groupIssues} />
      <ol className="space-y-3">
        {group.questions.map((question, qi) => (
          <QuestionEditor
            key={`${question.lineage_id ?? "new"}-${qi}`}
            group={group}
            question={question}
            index={qi}
            count={group.questions.length}
            issues={issuesFor(shared.issues, {
              section: sectionNo,
              group: index,
              question: question.number_from,
            })}
            readOnly={readOnly}
            onChange={(q) =>
              onChange({ ...group, questions: group.questions.map((x, i) => (i === qi ? q : x)) })
            }
            onMove={(delta) =>
              onChange({ ...group, questions: swapNumbers(group.questions, qi, qi + delta) })
            }
            onDuplicate={() =>
              onChange({
                ...group,
                questions: [
                  ...group.questions,
                  cloneQuestion(question, nextNumber(shared.allSections)),
                ],
              })
            }
            onRemove={() =>
              onChange({ ...group, questions: group.questions.filter((_, i) => i !== qi) })
            }
          />
        ))}
      </ol>
      {!readOnly && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            onChange({
              ...group,
              questions: [
                ...group.questions,
                newQuestion(group.question_type, nextNumber(shared.allSections)),
              ],
            })
          }
        >
          <PlusIcon aria-hidden="true" />
          Add question
        </Button>
      )}
    </li>
  );
}

export function SectionEditor({
  section,
  shared,
  onChange,
}: {
  section: SectionDoc;
  shared: Shared;
  onChange: (s: SectionDoc) => void;
}) {
  const id = useId();
  const info = useModuleInfo();
  const [newType, setNewType] = useState(shared.types[0] ?? "form_completion");
  const { readOnly } = shared;
  const groups = section.groups ?? [];
  const setGroups = (next: GroupDoc[]) => onChange({ ...section, groups: next });
  const sectionIssues = issuesFor(shared.issues, { section: section.section_no });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-heading text-xl font-semibold">
          {info.sectionNoun} {section.section_no}
        </h2>
        <p className="text-sm text-muted-foreground">
          {info.audio && <>Typically: {SECTION_KINDS[section.section_no]} · </>}
          {sectionRange(section)}
        </p>
      </div>
      <IssueList issues={sectionIssues} />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-title`}>{info.sectionNoun} title</Label>
          <Input
            id={`${id}-title`}
            value={section.title ?? ""}
            readOnly={readOnly}
            maxLength={300}
            onChange={(e) => onChange({ ...section, title: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-context`}>Context / description</Label>
          <Input
            id={`${id}-context`}
            value={section.context ?? ""}
            readOnly={readOnly}
            maxLength={2000}
            placeholder={info.audio ? "What the recording is about" : "Topic of the passage"}
            onChange={(e) => onChange({ ...section, context: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor={`${id}-instr`}>{info.sectionNoun} instructions</Label>
          <Textarea
            id={`${id}-instr`}
            rows={2}
            value={section.instructions ?? ""}
            readOnly={readOnly}
            maxLength={5000}
            onChange={(e) => onChange({ ...section, instructions: e.target.value || null })}
          />
        </div>
      </div>
      {info.passages && (
        <PassageEditor
          passage={section.passages?.[0]}
          readOnly={readOnly}
          onChange={(p) => onChange({ ...section, passages: [p] })}
        />
      )}
      {info.audio && (
        <MediaField
          label="Section audio"
          kind="audio"
          testId={shared.testId}
          assetId={section.audio_asset_id}
          assets={shared.assets}
          readOnly={readOnly}
          onUploaded={(asset) => {
            shared.onAsset(asset);
            onChange({ ...section, audio_asset_id: asset.id });
          }}
        />
      )}
      <section aria-labelledby={`${id}-questions`} className="space-y-3">
        <h3 id={`${id}-questions`} className="font-heading text-base font-semibold">
          Question groups
        </h3>
        {groups.length === 0 && (
          <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            No questions in this {info.sectionNoun.toLowerCase()} yet.
          </p>
        )}
        <ol className="space-y-4">
          {groups.map((group, gi) => (
            <GroupEditor
              key={gi}
              sectionNo={section.section_no}
              group={group}
              index={gi}
              count={groups.length}
              shared={shared}
              onChange={(g) => setGroups(groups.map((x, i) => (i === gi ? g : x)))}
              onMove={(delta) => setGroups(move(groups, gi, gi + delta))}
              onDuplicate={() =>
                setGroups([...groups, cloneGroup(group, nextNumber(shared.allSections))])
              }
              onRemove={() => setGroups(groups.filter((_, i) => i !== gi))}
            />
          ))}
        </ol>
        {!readOnly && (
          <div className="flex flex-wrap items-end gap-2 rounded-lg border border-dashed p-3">
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-newtype`}>New group type</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger id={`${id}-newtype`} className="w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {shared.types.map((t) => (
                    <SelectItem key={t} value={t}>
                      {typeLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              type="button"
              onClick={() =>
                setGroups([...groups, newGroup(newType, nextNumber(shared.allSections))])
              }
            >
              <PlusIcon aria-hidden="true" />
              Add question group
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}

export type { Shared as SectionShared };

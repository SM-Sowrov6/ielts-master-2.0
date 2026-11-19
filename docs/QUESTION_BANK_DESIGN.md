# IELTS MASTER 2.0 — Question Bank Design

| Field | Value |
|---|---|
| Status | **Draft v0.2 — revised after Phase 1 audit; awaiting approval** |
| Related | `DATABASE_SCHEMA.md` §4, `EXAMINATION_ENGINE_DESIGN.md`, `CONTENT_MANAGEMENT_ARCHITECTURE.md` |
| Last updated | 2026-11-17 |

---

## 1. Goal

One pipeline (**author → validate → render → capture → normalise → score → explain**) for every objective IELTS question type. Type-specific behaviour is plugged in through a **registry** of handlers on the backend and renderers on the frontend. We never build a separate exam engine per type.

## 2. Core Concepts

| Concept | Meaning |
|---|---|
| **Question group** | A block that shares instructions and context ("Questions 1–6: Complete the notes below. Write ONE WORD ONLY.") and optionally a shared option list, image, table, or note template. It has exactly one `question_type`. |
| **Question** | One numbered scoring unit, or a numbered range for multi-mark items ("Questions 21–22: Choose TWO letters"). It has `number_from`, `number_to`, and `marks`. |
| **Answer key** | One or more slots per question with a canonical value, a match mode, and accepted variants. |
| **Response** | Typed JSON captured from the student, validated by the type's response schema. |
| **Handler** | Backend class implementing the type's contract (schemas, validation, normalisation, scoring). |
| **Renderer** | Frontend component implementing the type's UI for practice, exam, review, and CMS preview. |

## 3. Supported Types

`question_type` codes are stable identifiers stored in DB rows and must never be renamed.

| Code | Module(s) | Response shape | Scoring family |
|---|---|---|---|
| `mcq_single` | L, R | `{choice: "B"}` | option |
| `mcq_multi` | L, R | `{choices: ["A","D"]}` | set (1 mark per correct, no negative) |
| `tfng` | R | `{choice: "TRUE"\|"FALSE"\|"NOT GIVEN"}` (fixed choices, no authored options) | option |
| `ynng` | R | `{choice: "YES"\|"NO"\|"NOT GIVEN"}` (fixed choices) | option |
| `matching_headings` | R | `{choice: "iv"}` per paragraph question | option (shared list) |
| `matching_information` | R | `{choice: "C"}` (paragraph letter) | option, letters reusable |
| `matching_features` | L, R | `{choice: "B"}` | option (shared list) |
| `matching_sentence_endings` | R | `{choice: "E"}` | option (shared list) |
| `sentence_completion` | L, R | `{text: "..."}` | text |
| `summary_completion` | L, R | `{text}` **or** `{choice}` when a word bank is given (`config.word_bank=true`) | text / option |
| `note_completion` | L, R | `{text}` | text |
| `table_completion` | L, R | `{text}` | text |
| `flowchart_completion` | L, R | `{text}` or `{choice}` | text / option |
| `form_completion` | L | `{text}` | text |
| `diagram_labelling` | L, R | `{text}` or `{choice}` | text / option |
| `map_labelling` | L | `{choice: "F"}` (letters on map) | option |
| `plan_labelling` | L | `{choice}` or `{text}` | option / text |
| `short_answer` | L, R | `{text}` | text |

Writing tasks and speaking questions are **not** objective question types. They live in `writing_tasks` / `speaking_parts` and are scored by the AI engine.

New types are added by registering a handler + renderer + JSON schema, with no change to the exam engine. Adding a type requires: (1) a new stable `code`, (2) handler + golden tests, (3) renderer + editor form, (4) a seed migration inserting the code into the `question_types` reference table (`question_groups.question_type` is an FK to `question_types.code`, so no enum/CHECK migration is needed), and (5) an import-schema update. The exam engine, scoring pipeline, and analytics treat `question_type` as opaque.

## 4. Handler Contract (backend)

```python
class QuestionTypeHandler(Protocol):
    code: ClassVar[str]
    version: ClassVar[str]                        # bump when scoring semantics change

    GroupConfig: type[BaseModel]                  # validates question_groups.config
    QuestionConfig: type[BaseModel]               # validates questions.config
    Response: type[BaseModel]                     # validates attempt_answers.response

    def validate_authoring(self, group, questions, keys) -> list[ValidationIssue]: ...
    def normalise(self, response: Response, rules: AnswerRules) -> NormalisedResponse: ...
    def score(self, question, keys, response: NormalisedResponse) -> ScoreOutcome: ...
    def student_view(self, group, questions) -> StudentGroupDTO: ...   # strips keys!
```

- `student_view` is the **only** path that produces content for students. It structurally excludes answer keys, variants, and (in exam mode) explanations. A unit test per handler asserts no key material appears in its output (security requirement).
- `ScoreOutcome = {marks_awarded, marks_available, is_correct, matched_key_id, detail}`.
- `scorer_version` is stored per `question_scores` row so rescoring after a bug fix can be audited and replayed.

## 5. Text Answer Normalisation & Validation

Completion-type answers are where scoring disputes happen, so the rules are explicit and data-driven.

`AnswerRules` (from group config):
```json
{
  "answer_format": "text",
  "word_limit": 2,
  "allow_number": true,
  "number_counts_as_word": false,
  "case_sensitive": false,
  "hyphen_policy": "equivalent",
  "british_american_equivalent": true,
  "numbers_as_digits_or_words": true
}
```

- `answer_format` is `text` or `option`. It drives the response schema for types that support both (summary/flowchart/diagram completion with or without a word bank, plan labelling), so the response shape is never guessed.
- **Instruction mapping (authoring presets):** "ONE WORD ONLY" → `word_limit 1, allow_number false`. "ONE WORD AND/OR A NUMBER" → `word_limit 1, allow_number true, number_counts_as_word false` (the number is additional to the word). "NO MORE THAN THREE WORDS" → `word_limit 3, allow_number false`. "A NUMBER" → `answer_format text, match_mode numeric`. The CMS selects a preset, which generates both the student-visible instruction text and the rule, so they can't drift.

### 5.1 Match modes (per answer key)

| `match_mode` | Use | Normalisation & comparison |
|---|---|---|
| `text` | completion / short answer | text pipeline below, then set membership in {canonical} ∪ variants |
| `option` | single choice / matching | exact option label (A, iv, TRUE) |
| `set_member` | multi-mark choice ("Choose TWO") | each selected label matched against unused key slots, order-independent |
| `numeric` | quantities, prices, years | parse digits/words (`twenty-five` ≡ `25`), strip thousands separators and currency symbols, compare as decimals. **Units are not compared** (implementation 5a): when a unit matters, use `text` mode with explicit variants |
| `time` | listening times | parse `9.30`, `9:30`, `9.30am`, `9 pm`, `noon`/`midday`, `midnight` to minutes since midnight. A key without am/pm matches on the 12-hour clock. **Spoken forms (`half past nine`) are not parsed**: add them as key variants |
| `date` | dates | parse `15 March`, `March 15`, `15th March`, `15/3` (day-first default, configurable) to (day, month[, year]) and compare the fields the key specifies |

### 5.2 Key authoring notation

Answer keys may use the conventional answer-key notation, which the import/CMS **expands into explicit `answer_variants` at authoring time** (the scorer only ever compares concrete strings):
- `(the) library` → optional words: `the library`, `library`.
- `colour/color` → word-level alternatives (slash **without** spaces).
- `car park / parking lot` → phrase-level alternatives (slash **with** spaces).
- Empty alternatives (`a//b`), unbalanced or nested parentheses are authoring errors.
- Combined: `(a) (short) break/rest` → the full cross product, capped at 64 variants (validator error beyond that).
- Expanded variants are shown to the reviewer for approval and checked against `word_limit` (a variant exceeding the limit is an authoring error).

Normalisation pipeline (deterministic, unit-tested with a golden corpus):
1. Unicode NFKC, trim, collapse internal whitespace.
2. Case-fold unless `case_sensitive`.
3. Strip surrounding punctuation; normalise quotes, apostrophes, and dashes.
4. Hyphen policy: `"well-known"` ≡ `"well known"` when `equivalent`.
5. Numbers in `text` mode: `"twenty"` ≡ `"20"` if enabled. Dedicated `numeric`/`time`/`date` keys use the parsers in §5.1.
6. Spelling-variant table (colour/color) when enabled.
7. Word-limit check **after** normalisation. Words are whitespace-separated tokens after hyphen policy, and a hyphenated compound counts as one word. When `number_counts_as_word = false`, one numeric token is excluded from the count. Exceeding the limit = incorrect (matches IELTS rules), and in practice mode the feedback says why.

Matching: normalised response ∈ {normalised canonical} ∪ {normalised variants}. **No fuzzy matching on scoring.** IELTS requires correct spelling. Fuzzy similarity is used only to show "close — check spelling" in practice feedback.

Spelling-variant and number tables are data, versioned with the scorer.

## 6. Shared Options & Reuse Semantics

- Shared option lists (`question_options.group_id`) support matching types. `GroupConfig.options_reusable: bool` controls whether a letter may be used more than once. The UI enforces it in practice and exam, and the scorer doesn't care.
- `matching_headings` may include unused distractor headings and an example (`config.example`) that is displayed but not scored.
- `mcq_multi` "Choose TWO" spanning numbers 21–22: one question row, `marks=2`, two key slots, order-independent. Each correct choice earns 1 mark, and selecting more than the allowed count is blocked in the UI (and validated server-side: excess choices → response rejected with 422).

## 7. Rendering (frontend)

```
components/questions/
  registry.ts                 # code → { Renderer, ReviewRenderer, EditorForm, responseSchema (zod) }
  shared/                     # BlankInput, OptionList, DragDropMatch, InlineTemplate, ImageHotspots
  types/<code>/               # Renderer.tsx, Review.tsx, Editor.tsx
```

- Renderers take `(group, questions, value, onChange, mode)` and are **pure/controlled**. Persistence is handled by the exam shell (autosave queue), never by the renderer.
- Completion types share an `InlineTemplate` that renders authored templates (notes, tables, flowcharts, forms) with numbered blanks embedded, e.g. `"Rent: £{{q:7}} per week"`. Templates are stored as structured JSON (ProseMirror doc with `blank` nodes), not HTML strings, so no raw HTML is ever injected.
- Map/diagram labelling uses an image asset + hotspot coordinates (`config.hotspots[{number, x, y}]`), accessible via a fallback select list.
- Drag-and-drop matching always has a keyboard/select alternative (WCAG).
- Zod response schemas are **generated from the backend Pydantic schemas** (via OpenAPI → codegen) to keep validation in sync.

## 8. Metadata & Tagging

Each question carries `question_type` (from group), `difficulty` (`easy|medium|hard`, editor-assigned, later recalibrated from data), `tags[]` (topic: environment, education…; skill: skimming, inference, detail…), and `lineage_id` (stable across content versions, used for item statistics).

**Item statistics** (computed by analytics from `question_scores`): p-value (proportion correct), discrimination index (top vs bottom quartile), and average time. These flag broken items (p≈0 or negative discrimination) to reviewers automatically.

## 9. Question-type Practice Sets

Generated at attempt creation from published content: filters (`module`, `question_type`, `variant`, `difficulty`, exclude recently seen) → select **whole question groups** (never split a group from its passage/audio) → snapshot into `exam_attempts.config_snapshot`. Selection is reproducible from the stored seed and manifest.

## 9a. Implementation status (Phase 5a, 2026-11-18)

- Code: `backend/app/modules/content/question_types/` (`normalize.py`, `base.py`, `handlers.py`, `catalog.py`, registry in `__init__.py`).
- Three handler families cover all 18 codes: `OptionHandler` (single choice, incl. fixed-choice T/F/NG and Y/N/NG), `MultiOptionHandler` (`mcq_multi`, 1 mark per correct choice, excess choices rejected), `TextHandler` (completion / short answer; `text`, `numeric`, `time`, `date` keys; word-bank `answer_format: "option"` only for `summary_completion`, `flowchart_completion`, `diagram_labelling`, `plan_labelling`).
- Unified option response shape: `{"choice": "<label>"}` for every option type (v0.2 listed `{value}` for T/F/NG; changed for one consistent contract).
- Word count: hyphenated compounds count once, and hyphenated number words (`twenty-five`) count as one number.
- Every handler records `version = "1.0.0"` (`question_types.handler_version`).

## 10. Testing Requirements

- Per handler: authoring validation cases, normalisation golden tests, scoring truth tables, "no key leakage" test.
- Property-based tests (Hypothesis) for the normaliser (idempotence: `normalise(normalise(x)) == normalise(x)`).
- Frontend: component tests per renderer (keyboard operability, controlled value round-trip), Playwright flows for each type family.
- Rescoring safety: changing a handler's `version` requires a migration note and a replay script (dry-run diff of scores) before deployment.

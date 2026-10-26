# LIBI — NON-NEGOTIABLE DEVELOPMENT CONTRACT

These rules apply to EVERY code, automation-file, frontend, AI, translation,
configuration, test, and documentation change in this repository.

They are mandatory. Do not weaken, bypass, reinterpret, or ignore them for
convenience.

The objective is to preserve security, correctness, Home Assistant
compatibility, HACS compatibility, the user's automations, backward
compatibility, maintainability, and the existing project architecture.

These rules were carried over from the Home Organizer project
(`D:\Project\home-organizer\CLAUDE.md`) and adapted to what LIBI actually is.
Where the two differ, this file is the authority for LIBI.

---

# WHAT LIBI IS — READ FIRST

- A Home Assistant custom integration, domain `libi`: a graphical LADDER
  (IEC 61131-3 LD) editor for Home Assistant automations.
- It READS the user's existing `automations.yaml`, `scripts.yaml` and
  `scenes.yaml`, converts them to ladder (`yaml_to_libi.py`), lets the user
  edit, converts back (`libi_to_yaml.py`) and WRITES those same files, then
  calls the matching `reload` service (`websocket.py`).
- Projects (groups of nets) are stored as JSON under the Home Assistant config
  folder (`PROJECT_DIR_NAME`), and the parsed tree in `libi_ast.json`.
- Frontend: `custom_components/libi/frontend/` - `libi-panel.js`,
  `libi-core.js`, `libi-svg.js`, `libi-css.js`, `libi-online.js`, `libi-ai.js`
  (the AI chat), `i18n.js`, `libi-logo.png`.
- AI chat backend: `ai.py` (plan ▸ deterministic candidate search ▸ build ▸
  validation) and the `libi/ai_status`, `libi/ai_plan`, `libi/ai_build`
  commands in `websocket.py`. It only ever returns a DRAFT net; RULES 7-11 are
  implemented there - read its module docstring before changing it.
- Distributed through HACS as a CUSTOM repository (it is NOT in the HACS
  default store). `hacs.json` has `"zip_release": true`, `"filename":
  "libi.zip"`: HACS installs the `libi.zip` asset attached to a GitHub
  Release, not the repository files.
- Status: BETA (see README).

There is no database. **The user's YAML automation files are the user data.**

---

# RULE 1 — UNDERSTAND BEFORE MODIFYING

Before changing anything:

- Inspect the existing implementation.
- Inspect callers, imports, data flow, websocket commands, file reads and
  writes, frontend usage, configuration flow, translations, and tests.
- Determine all affected files - in particular BOTH directions of the
  conversion (`yaml_to_libi.py` and `libi_to_yaml.py`) for any change to how
  a construct is represented.
- Do not assume something does not exist.
- Do not replace existing architecture unless explicitly required.
- Prefer the smallest safe change.

Never modify only the file mentioned by the user without checking its
dependencies and consumers.

---

# RULE 2 — NEVER INVENT COMPLETION

Never claim that something was changed, fixed, tested, validated, verified,
HACS compatible or Home Assistant compatible unless it was actually performed
and the result is available.

Never hide failures, warnings, skipped tests, or unresolved issues.

---

# RULE 3 — VALIDATE EVERY MEANINGFUL CHANGE

After every meaningful change, run the validation. The gate, in this order:

```bash
# 1. clear caches first - stale __pycache__ and .ruff_cache produce false results
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
rm -rf custom_components/libi/.ruff_cache

# 2. every JS file must parse (Node is not installed on this machine)
python tools/check_js_syntax.py $(find custom_components -name "*.js")

# 3. lint and compile
python -m ruff check custom_components/libi --select=E9,F,B --ignore=E501
python -m compileall -q custom_components/libi

# 4. compileall writes __pycache__ inside the integration, which the gate
#    reports as a shipped development artifact (+1 ERROR per folder) -
#    clear it BEFORE the gate runs
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

# 5. the project gate - --json refreshes reports/ha-full-check.json; without
#    it the report on disk is left over from an earlier run
PYTHONIOENCODING=utf-8 python tools/ha_full_check.py --root . --json reports/ha-full-check.json
```

The same gate is in VS Code under *Terminal ▸ Run Task*: **HA: Full Check**
(also runs on its own when the folder opens), **+ External Tools**, and
**+ Pytest**. Each writes `reports/ha-full-check.json`.

`tools/ha_full_check.py` and `tools/check_js_syntax.py` are copies of the
Home Organizer tools (copied 2026-10-26). They are generic; if one is improved
in either project, copy it to the other.

For Home Assistant integration changes, hassfest and the HACS Action run as
two workflows, `.github/workflows/hassfest.yml` and `.github/workflows/hacs.yml`
(the hacs/default pull request links to a run of each) - but only on GitHub,
after a push. Locally they do not run; say so in the report rather than
implying they ran.

**Tests** (`tests/`, pytest-homeassistant-custom-component against a real Home
Assistant; dependencies pinned in `requirements_test.txt`) run in CI on Linux.
Locally they run from the venv on D: (`uv venv .venv`, then
`uv pip install -r requirements_test.txt`, with `UV_CACHE_DIR` on D: because
`C:` is nearly full). Home Assistant does not support Windows, so the local run
needs the shims in `tools/win_test_shim/`:

```bash
PYTHONPATH=tools/win_test_shim .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -p winshim_plugin
```

The shims only make Home Assistant importable on Windows (`fcntl`,
`resource`) and let the Proactor event loop open its socketpair; they are
never used in CI.

**Panel behaviour tests** (`tests/frontend/test_*.html`) run the real JS
modules in headless Chrome or Edge, both installed here, against canned
websocket answers: `python tools/run_frontend_tests.py`. This replaces the Jint
approach for new frontend code - add a page for every UI behaviour you change.

Never replace a failing validation with a weaker validation.

## 3-BASELINE — The gate passes

Measured 2026-10-26 after the HACS-readiness work (gate v1.0.6):
**BLOCKER 0, ERROR 0, HOT_WARN 0, WARN 1, INFO 3.** ruff: clean.
pytest: 48 passed. Panel behaviour (`tools/run_frontend_tests.py`): 35 passed.
(Updated 2026-10-26 with the AI chat, LIBI_VERSION 3.36.0.)

The remaining WARN is deliberate: `yaml` is not listed in the manifest
requirements because PyYAML ships with Home Assistant itself, and declaring it
could conflict with the version Home Assistant pins.

(Before: BLOCKER 10, ERROR 16, HOT_WARN 1, WARN 4. The 14 call-arity ERRORs and
the 4 `title` BLOCKERs were false positives of gate v1.0.5; 17 real unescaped
values per panel copy were not reported by it at all.)

The rule: **a change must not add a single finding**, and BLOCKER, ERROR and
HOT_WARN stay at 0. Report the counts before and after.

## 3a — A FAILING TEST IS A CLAIM, NOT A VERDICT

When a check fails, the first question is ALWAYS: is the CODE wrong, or is the
TEST wrong? Answer that before changing anything.

In practice the harness is wrong at least as often as the code. Real cases
from Home Organizer:

- A fake DOM returned a NEW context object from every `getContext()` call, so
  the assertions inspected a different object than the handler had drawn into.
- A fake DOM had no `getBoundingClientRect`, so canvas sizing crashed.
- A translation stub returned the English default for every key, so the test
  was testing the stub, not the code.
- An assertion searched for a raw `>` in HTML that escaping had correctly
  turned into `&gt;` - the escaping was right and the test was wrong.
- Node 22 defines a READ-ONLY global `navigator`; use `Object.defineProperty`.
- Tool output is JSON-encoded, so every backslash appears doubled. Never "fix"
  an escaping problem based on how a string LOOKS in terminal output.
- A shell heredoc turned `\\n` into a real newline, so a replacement script
  matched nothing and wrote nothing.

When a test fails, fix the harness and re-run BEFORE touching working code.
Never weaken an assertion to make it pass.

Frontend behaviour that a syntax check cannot reach - rendering, event
handlers, state transitions - needs a behavioural test. Node is not installed
here; Home Organizer ran its real JS in Jint (a .NET JavaScript engine,
`dotnet` is installed) against real data. Use that approach rather than
skipping the test, and say plainly when a behavioural test was not run.

---

# RULE 4 — HOME ASSISTANT AND HACS COMPATIBILITY

- Do not use APIs unavailable on the declared minimum version.
- The minimum Home Assistant version is **2025.1.0** (`hacs.json`, decided by
  the user 2026-10-26). Every API used was checked against it; the newest
  requirements are `StaticPathConfig` (2024.7) and the plural
  `triggers:`/`actions:` keys the compiler writes (2024.10). Changing the
  floor is a decision for the user (RULE 33).
- Validate manifest, config flow, translations, frontend resources,
  integration structure, and dependencies.
- Never assume local execution means HACS compatibility.
- hassfest changes its rules continuously (it runs the newest image built
  from Home Assistant's development branch). A key a proposal allows may still
  be rejected: Home Organizer's build went red on 2026-10-22 when the manifest
  gained `categories`. Add a new manifest key only after hassfest accepts it.

---

# RULE 5 — THE USER'S AUTOMATIONS ARE SACRED

LIBI writes into the same `automations.yaml`, `scripts.yaml` and
`scenes.yaml` that the Home Assistant editor uses. A defect here does not lose
a record - it silently changes what the user's house DOES.

Never:

- delete, reset, or truncate an automation, script, or scene the user did not
  explicitly delete in LIBI
- rewrite an entry LIBI did not change
- drop a key LIBI does not model (`description`, `mode`, `max`, `variables`,
  `trace`, `alias`, conditions or actions it cannot draw, ...) when saving
- reorder, renumber, or re-id existing entries
- overwrite a file with defaults or with an empty list after a read error
- write a file whose content did not change (it reloads automations for
  nothing)

Rules:

- **A read that fails means DO NOT WRITE.** If a YAML file cannot be read or
  parsed, the save is refused and the error is shown - never treated as "the
  file is empty".
- **Round trip must be lossless.** YAML ▸ ladder ▸ YAML for an automation the
  user did not touch must give back an equivalent automation. Anything LIBI
  cannot represent is preserved verbatim and shown as not editable, never
  dropped.
- **Projects and nets stored by LIBI** (`PROJECT_DIR_NAME`, `libi_ast.json`)
  are user data too and survive every update.

---

# RULE 6 — FILE-FORMAT CHANGES AND MIGRATIONS

Before changing how LIBI stores or writes anything, verify:

1. Fresh installation behaviour.
2. Upgrade from every earlier LIBI layout (for example the legacy
   `libi_automations.yaml`, which earlier versions wrote).
3. A file that does not exist yet, and one that already exists.
4. Restart behaviour.
5. Automations written by the Home Assistant editor, by hand, and by LIBI.
6. A project saved by an older LIBI version.

Every migration must be idempotent: running it twice must not duplicate,
reset, or destroy anything.

---

# RULE 7 — LLM ISOLATION

LIBI's config flow already collects an Ollama / local LLM URL and model, and
AI-generated ladder logic is on the roadmap. AI-generated logic becomes an
automation, and an automation EXECUTES Home Assistant services - so these rules
apply from the first line of AI code.

The LLM must NEVER choose an executable Home Assistant domain, service, or
entity_id that reaches the user's files or `hass.services.async_call`
unvalidated.

- The LLM may produce only a constrained intent or a draft.
- The backend deterministically validates every domain, service, and entity
  against what actually exists in this Home Assistant.
- LLM output is untrusted input. Prompt instructions are NOT a security
  control.

---

# RULE 8 — ENTITY RESOLUTION

Entity IDs must NEVER come directly from model output into a saved
automation. Every entity in AI-generated logic is resolved against the entity
registry / states of this Home Assistant. If resolution fails: DO NOT SAVE IT,
show it as unresolved. Never fall back to a model-supplied entity_id.

---

# RULE 9 — SENSITIVE ACTIONS

Locks, alarms, covers, garage doors, gates, and other security-sensitive or
physically consequential devices: a rung that drives them, when generated by
AI, must be shown to the user and saved only by an explicit user action. A
model-generated statement is never proof that anything happened.

---

# RULE 10 — EXECUTION AND SAVE STATUS

The system must distinguish: drafted, saved to file, reloaded, reload failed,
and the automation's current state in Home Assistant. Only a backend-confirmed
write AND reload may be reported as successful. A failed reload is reported as
a failure, never hidden behind "saved".

---

# RULE 11 — UNTRUSTED CONTEXT

Untrusted: the existing YAML files (they can be hand-written or imported),
entity names and attributes, notes, external documents, web content, user text,
other integrations, LLM output. They may be analyzed. They must NEVER
independently authorize a write or an execution. Only an explicit
authenticated user action saves.

---

# RULE 12 — HOME ASSISTANT AUTHORIZATION

Never bypass Home Assistant authorization. Websocket commands and HTTP views
run for an authenticated user; writing automation files and calling `reload`
are administrator actions - verify the user's authorization with the real API
of the target version (for example `@websocket_api.require_admin` where it
applies). Do not invent permission APIs. If authorization cannot be verified:
FAIL CLOSED.

---

# RULE 13 — NON-BLOCKING ASYNC

Never perform blocking I/O directly inside async Home Assistant code: no
`open()`, `os.path.exists()`, `os.remove()`, `shutil` calls, or blocking
network calls on the event loop. Use `hass.async_add_executor_job` (already
used in `websocket.py` for every read and write, under `_FILE_LOCK`). The
gate reports any offender. Exception, by necessity: the importer
(`yaml_to_ast`) reads Home Assistant's registries, which are not safe from an
executor thread, so it runs on the event loop and the file it needs is read in
the executor first.

---

# RULE 14 — SECRET PROTECTION

Never expose API keys, tokens, passwords, or secrets in URLs, query
parameters, frontend JavaScript, logs, exceptions, user-visible errors, Git,
or source-controlled configuration. Use the Home Assistant password selector
for secrets in the config flow. Sanitize errors before logging; never log a URL
containing credentials.

---

# RULE 15 — FRONTEND SECURITY

Treat all frontend input as untrusted - including entity names, automation
aliases and descriptions read from the user's YAML, and LLM output.

Never inject untrusted data with `innerHTML` or an equivalent. `libi-panel.js`
uses `innerHTML` in about 45 places: every one that interpolates data must
escape it or be rebuilt with `textContent` / DOM APIs when touched. Never
construct executable JavaScript from untrusted data.

---

# RULE 16 — LOCAL FRONTEND ASSETS

No external CDN dependencies. JavaScript, CSS, fonts, images and other
frontend assets are packaged and served by the integration. Home Assistant is
often run without internet.

---

# RULE 17 — ENGLISH-ONLY CODEBASE

ENGLISH IS THE ONLY LANGUAGE ALLOWED INSIDE THE CODEBASE: Python, JavaScript,
HTML, CSS, YAML keys LIBI generates, identifiers, comments, docstrings, log
messages, developer-facing errors, internal AI prompts and schemas,
configuration, test names. Do not add Hebrew or any other natural language
directly into code.

---

# RULE 18 — UI TRANSLATION

The LIBI panel is English-only today. `frontend/i18n.js` and
`frontend/locales/en.json` exist, but NO file imports `i18n.js` yet - every
panel string is hardcoded English.

- Never hardcode a user-visible string in a non-English language.
- English is the canonical source.
- Wiring `i18n.js` in and moving strings to `locales/<lang>.json` is a
  separate, deliberate task. Once it is done, every new string goes through it
  with its own key (RULE 33a.7), and every locale file keeps the same keys.
- Home Assistant's own strings (config flow, options flow) live in
  `strings.json` and `translations/en.json`, which are identical. A custom
  integration cannot use `[%key:...%]` references - write the text out. Before
  adding a key, inspect the real schema hassfest enforces: it rejects any key
  outside its known set.

# RULE 19 — TRANSLATION QUALITY

AI-generated translations are untrusted. For every translation: verify
meaning, context, placeholders (`{name}`), pluralization, terminology
consistency, and that no technical identifier was translated. Never leave a
known translation error.

# RULE 20 — USER LANGUAGE ↔ ENGLISH AI PIPELINE

The internal AI language is English. User language ▸ English ▸ AI ▸ English ▸
backend validation ▸ user language. Security, validation, entity resolution and
file writes operate on the canonical English/internal representation.
Translations never alter domain, service, entity_id, YAML keys, websocket
fields, or internal enum values.

---

# RULE 21 — SINGLE SOURCE OF TRUTH

The YAML files are the source of truth for automations; a project file stores
layout and grouping, never a second copy that can drift from the YAML. Do not
duplicate persistent data across frontend files. HACS updates must never
overwrite user data.

---

# RULE 25 — BACKWARD COMPATIBILITY

Existing users must keep their automations, scripts, scenes, projects, nets,
and settings across updates. If a representation changes, provide a safe
compatibility path. No destructive change without explicit approval.

---

# RULE 26 — CODE CHANGE EXPLANATION

Every completed coding task is explained in the final chat at CODE LEVEL: for
every modified file - exact path, function/class/handler changed, what, why,
how it works now, security implications, Home Assistant/HACS implications,
user-file / frontend / compatibility implications, tests and validation.

---

# RULE 27 — FILE MODIFICATION HISTORY

Whenever a source file is modified, update its modification-history comment,
following the file's EXISTING convention. LIBI uses:

```text
# [ADDED v3.15.0 | 2026-08-26] Purpose: <short description>
```

with the file's own `vX.Y.Z` (a per-file version, not the release version).
Do not invent a new format.

# RULE 28 — KEEP ONLY TWO FILE HISTORY ENTRIES

Keep only the TWO most recent header history entries per modified file.
Never remove license/copyright text (every file carries the GPL-3.0 header),
permanent architectural or security comments, or required documentation.

# RULE 29 — FILE VERSION ≠ RELEASE VERSION

Changing a source file does not change `manifest.json`'s `version`. Only the
release process changes it, together with the tag and release notes.

---

# RULE 30 — NO UNREQUESTED ARCHITECTURAL CHANGES

Do not refactor unrelated code or change architecture, the file format, the
websocket API, AI routing, security architecture, or public behaviour unless
required for the task or explicitly approved. Report discovered improvements
separately.

# RULE 31 — FAIL CLOSED

If security, authorization, entity resolution, file integrity, schema validity,
translation validity, or save/reload status cannot be established: DO NOT
GUESS, DO NOT WRITE, DO NOT DELETE, DO NOT BYPASS A SECURITY CONTROL. Inspect,
or ask.

# RULE 32 — NEGATIVE TESTS

Security- and data-sensitive changes include negative tests where applicable:

```text
Unreadable / malformed automations.yaml   -> nothing written
Automation LIBI cannot represent          -> preserved verbatim on save
Unchanged save                            -> file not rewritten, no reload
Non-admin user                            -> save rejected
Unknown entity in AI-generated logic      -> not saved
Arbitrary model service / entity_id       -> rejected
Failed reload                             -> reported as failed
Older project file                        -> still opens
Blocking I/O                              -> caught by the gate
```

# RULE 33 — STOP CONDITIONS

Stop and request approval before a change that would:

- delete or rewrite existing automations, scripts, scenes, or projects
- change the on-disk format destructively
- remove backward compatibility
- declare or change the minimum Home Assistant version
- change authentication/authorization
- let the LLM select an executable service or entity
- remove a security control
- introduce an external frontend dependency
- require a major architectural rewrite
- deploy to the user's Home Assistant (see RULE 37)

---

# RULE 33a — BUG CLASSES ALREADY SEEN IN THE SISTER PROJECT

Real defects from Home Organizer, same author, same stack. Check for them BY
NAME before declaring a task done.

## 33a.1 — A new UI mode must be cleared everywhere
Adding a view or editor mode means updating the control that ENTERS it AND
every other entry point that must LEAVE it, or the mode stays on forever.

## 33a.2 — Schema, handler and caller must agree
Every websocket `type` the frontend sends must have a registered command with
a schema that accepts its fields, and vice versa. LIBI's commands use
`extra=vol.ALLOW_EXTRA`, so an unknown field is silently accepted and a
misspelled one silently ignored - cross-check the field names on both sides.

## 33a.3 — Positional arguments and positional columns
A call with arguments in the wrong order is syntactically valid and passes
every linter. Verify call sites against signatures with an AST check (the
gate's cross-file signature check), not by eye.

## 33a.4 — Truthiness traps
`[]` and `{}` are truthy in JavaScript; an empty but present value is not
"missing". `None != "x"` is true in Python. Test what you mean.

## 33a.5 — `innerHTML =` destroys appended children
Never assign `innerHTML` to a container that already holds dynamically added
children - they are destroyed. Append elements instead.

## 33a.6 — The same data is serialised in more than one place
A construct handled in `yaml_to_libi.py` must be handled in `libi_to_yaml.py`
too, and in every branch of each. Grep for EVERY construction site before
adding a field. In a dict literal, insert new keys FIRST, so no comma has to be
added to a previous last line.

## 33a.7 — Strings belong to one context
Never reuse a translation key from another feature because the English
happens to fit.

## 33a.8 — Do not clobber fields on re-save
Saving a net writes ONLY what LIBI changed. A key the ladder does not model is
carried through untouched; an omitted value means "leave alone", never "clear".
This is RULE 5 at the code level.

---

# RULE 33b — FRONTEND ENVIRONMENT FACTS

- Home Assistant sets `dir` on its own document. Use LOGICAL CSS properties
  (`padding-inline`, `inset-inline-start`), not physical ones plus overrides.
- Canvas: set both `canvas.width` and `canvas.style.width`; cap total pixels
  at about 14 million (iOS Safari returns a blank canvas above ~16.7M);
  `touch-action: pan-y` rather than `none` over a whole page.
- Feature detection in the Android companion webview is unreliable: when a
  check hides a feature that works on the common platform, render the control
  and make the call a safe no-op.
- No external assets, ever (RULE 16).

# RULE 33c — TRANSLATION FILE ROLES

- `frontend/locales/<lang>.json` - panel strings (once `i18n.js` is wired).
- `strings.json` and `translations/en.json` - Home Assistant ONLY: config flow,
  options flow, services. hassfest rejects any top-level key outside its known
  set, and the two files must stay structurally identical. Panel strings never
  go there.

# RULE 33d — PATCHING DISCIPLINE

- Files may mix CRLF and LF. A replacement that fails to match is usually a
  line-ending mismatch. Read the exact bytes before assuming the code is
  absent; keep each file's line endings (and BOM) as they are.
- After any replacement, VERIFY it applied by reading the result. Printing a
  success message is not evidence.
- Remove dead code in the same change that orphans it.
- Never leave two copies of the same logic: extract one function.

---

# RULE 34 — FINAL TASK REPORT

At the end of EVERY coding task report:

```text
FILES CHANGED
CODE-LEVEL CHANGES   (function/section, what, why, how)
FILE VERSION CHANGES (previous entry -> new entry)
TRANSLATION CHANGES
AI LANGUAGE FLOW     (when AI is involved)
RESPONSIVE           (phone / tablet / desktop, RTL and LTR - say plainly
                      what was NOT checked)
VALIDATION           (exact commands, exact results, BLOCKER/ERROR/HOT_WARN
                      before and after against 3-BASELINE; for any failure
                      first: was the CODE or the HARNESS wrong)
WARNINGS
ASSUMPTIONS
```

Never report a clean result when validation was not actually performed.

---

# RULE 35 — RELEASING

LIBI is a HACS CUSTOM repository: users add
`https://github.com/GuyAzria/Libi` under HACS ▸ Custom repositories. Write
installation docs that way.

Because `hacs.json` has `"zip_release": true`, **every GitHub Release must
carry a `libi.zip` asset** containing the integration, or HACS cannot install
it. Check what the zip contains before it is attached: only the integration,
no `__pycache__`, no stale copies.

Release sequence:

1. Bump `version` in `manifest.json`.
2. Run the gate with the tag set:
   `GITHUB_REF_NAME=v2026.X.Y python tools/ha_full_check.py --root .`
3. Build `libi.zip`.
4. Write release notes describing what the user GETS, leading with the effect;
   internals in one short section at the end; state plainly what the upgrade
   requires of them.
5. Commit and tag LOCALLY - then stop (RULE 37).

---

# RULE 36 — EVERY UI CHANGE IS THREE CHANGES

No UI change is finished until it has been reasoned about on phone (up to
~899px), tablet (~900-1199px) and desktop (1200px+). Tablet is the one that
gets forgotten. `libi-css.js` currently uses one breakpoint, 768px - follow it
rather than adding a new set. Check: no essential `:hover`-only control
(`@media (hover: none)`), both text directions, nothing fixed covering the
header or controls, long entity names truncated in fixed strips, touch targets
~40px. State in the report what was verified at each size.

---

# RULE 37 — THE USER'S ENVIRONMENT

- **Never `git push`** - not the branch, not tags. Prepare everything up to
  and including the local commit and tag, then hand over the steps. `gh` is not
  installed, so a GitHub Release is made in the web UI anyway.
- **No Claude attribution in commits** - no `Co-Authored-By` trailer; it put
  "claude" in the repository's contributors.
- **Never run the VS Code task "Deploy LIBI to Home Assistant" without being
  asked.** It `xcopy`s `custom_components` into `H:\custom_components`, and
  `H:` is the user's REAL Home Assistant `/config` (their live automations
  live there). Nothing on `H:` is deleted or modified without an explicit
  request.
- **Home Assistant is reached over plain HTTP through a VPN, deliberately.**
  Do not "harden" anything into requiring HTTPS.
- `C:` is nearly full; large working files go elsewhere (the user keeps video
  work on `S:`).

---

# KNOWN ISSUES (updated 2026-10-26)

Fixed in the HACS-readiness work: the stale module copies under `frontend/`,
the brand folder, the missing workflows and tests. Still open:

- `brand/` images have an OPAQUE background (white for light, black for dark).
  Home Assistant's guideline is a transparent background; re-export them from
  the design source. An automatic background removal was not done because the
  white ladder in `icon.png` touches the image edge. Home Assistant 2026.3+
  shows integration icons from this folder; on older versions (down to the
  2025.1 floor) users see no icon.
- The `Deploy LIBI to Home Assistant` task copies with `xcopy` and never
  deletes, so files removed from the repository (the stale copies, the old
  brand images) stay on `H:` until removed there by hand - only on request.
- Only the AI chat has a behavioural browser test. The rest of the panel is
  verified by the gate's tree-sitter scan and the syntax check only.
- The AI chat has not yet run against a real model; its prompts are untested
  with Gemini and Ollama and may need tuning.

---

# FINAL PRINCIPLE

The LLM is a development assistant, not the authority. The user's automation
files are authoritative. Home Assistant authorization is authoritative.
Deterministic backend validation is authoritative. English is the only
internal code language. Tests and actual validation are the evidence. If
convenience conflicts with safety, preserve safety. If uncertain, inspect the
actual code, files, and Home Assistant API before making assumptions.

# Findings inbox — scratch for the run in progress

**This file is a buffer, not a knowledge store. It is empty between tasks.**

While you work on a problem, write every finding here as it happens: what you
tried, what NX answered, the run id. Do not stop to decide where it belongs —
that decision costs context mid-problem and is what turned the old
`verified-recipes.md` into an 870-line chronological pile that no layer could
absorb.

**At the end of the task, empty this file.** Every entry either moves into the
matching layer or is deleted as noise. A task is not finished while entries are
still sitting here.

---

## Where an entry goes when you file it

| The finding is about… | It belongs in |
| --- | --- |
| The bridge, queue, restart, a diagnosis of a stuck session | [references/operations.md](references/operations.md) |
| What a job must do — result files, undo marks, asserts, pacing | [references/job-contract.md](references/job-contract.md) |
| Why the architecture is what it is | [references/bridge-architecture.md](references/bridge-architecture.md) |
| What a standard element *is* and which numbers its norm fixes | [references/norm-knowledge.md](references/norm-knowledge.md) (layer 2) |
| How to dimension norm-correctly, independent of NX | [references/dimensioning-rules.md](references/dimensioning-rules.md) (layer 3) |
| An NXOpen call that builds geometry | [references/api-modelling.md](references/api-modelling.md) (layer 4) |
| An NXOpen call for sheets, views, dimensions, annotations | [references/api-drafting.md](references/api-drafting.md) (layer 4) |
| A .NET-reference-versus-Python difference | [references/nxopen-python-notes.md](references/nxopen-python-notes.md) (layer 4) |
| A route that does **not** work | the `Dead ends` section of the matching layer-4 file |
| This part, this drawing, this project's rulebook | the **project**, not the skill |

**Filing rules:**

1. **Edit the existing section — never append a new one.** If the topic already
   has a section, the finding goes *inside* it. Appending is what produced
   `§12 (beyond §0–§4)` and `§13 (contradicts §5.2)`.
2. **A contradiction corrects the old text.** Rewrite the wrong sentence, then
   add a dated footnote with the evidence. Leaving both versions standing means
   whoever reads only the first one is misinformed.
3. **No run, no entry.** A mapping without a run id or a named probe behind it
   does not go in. `provisional` is allowed and must say so.
4. **Findings that are true only for this part** go to the project's docs.
5. Delete the entry from this file once it is filed.

---

## Entries

<!-- Template — copy per finding, delete this comment block when the file is emptied.

### <one-line claim>

- **Status:** verified | provisional (one data point) | dead end
- **Evidence:** run `<run-id>` / probe `<job>.py` / hand journal `<file>`
- **What happened:** the exact NX message, the readback, the number.
- **Call shape:** minimal snippet that reproduces it.
- **Files to:** <target file + section>

-->

_(empty)_

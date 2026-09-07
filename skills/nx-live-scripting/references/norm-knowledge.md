# Norm knowledge (layer 2: element know-how)

**STATUS: placeholder.** This layer will hold the engineering knowledge of
the standard elements a job needs — one entry per element, filled by the
user as required. Layer 3 ([dimensioning-rules.md](dimensioning-rules.md))
says *how* to dimension; this file says *what* the element is and which
numbers the norm fixes. Layer 4 ([api-modelling.md](api-modelling.md) for
geometry, [api-drafting.md](api-drafting.md) for the drawing) says how each
entry is built with the NX API.

## Entry schema (mandatory fields)

1. **Function** — what the element does in the assembly.
2. **Geometry/sizes** — nominal sizes and how they derive (e.g. key
   cross-section from shaft diameter); valid ranges.
3. **Tolerance/seat selection** — which fit classes for which seat
   (fixed/light/sliding), with the source table.
4. **Representation** — how the element is drawn (views, sections, symbols).
5. **Dimensioning** — pointer to the layer-3 recipe; element-specific
   deviations only.
6. **Source** — norm + year/edition and the handbook page
   (Labisch/Wählisch 7th ed.: B. = book page).
7. **API notes** — pointer to the layer-4 mapping; verified limits only
   (e.g. "t1 not associatively dimensionable, state as note").

## Coverage

| Element | Norm | Status |
| --- | --- | --- |
| Parallel key + keyway, high form | DIN 6885-1 | open (verified geometry/tolerances exist in project evidence) |
| Retaining ring, shaft / bore | DIN 471 / DIN 472 | open |
| Centre hole, forms A/B/R/D | DIN 332 / ISO 6411 | **provisional for Form D + M6 only** (see below; norm original pending) |
| Undercut | DIN 509 | open |
| Metric ISO thread | DIN 13 / DIN ISO 965 | open |
| Rolling-bearing seats | DIN 620 + maker tables | open |
| Locknut + lock washer | DIN 981 / DIN 5406 | open |

## How to add an entry

Write it from the norm original (handbook tables are excerpts), run the
numbers past a real feature once, then fill the schema above and flip the
status. One element per session; a half-filled entry is worse than an open
row because the next agent will trust it.

## Provisional: centre hole Form D coaxial with M6 (ASSUMED — norm original pending)

**Do not trust the numbers below as norm values.** They are an engineering
assumption the user approved to resolve a physical conflict (a plain A/R
centre cannot share the M6 axis — layer 3 flags it; a standard centre cone
would cut away thread starts). Verify against DIN 332 / ISO 6411 original
(Nautos skill) before reuse on another part.

1. **Function** — centre datum for re-chucking the far side, combined with
   a functional M6 thread on the same face.
2. **Geometry/sizes (assumed)** — 60° included lead cone, mouth Ø6.4
   (identical to the thread's start chamfer diameter, so no extra diametral
   cut), thread depth 14 / drilled hole 16 (usable ~12 preserved).
3. **Tolerance/seat selection** — thread 6H-equivalent callout on drawing;
   no separate centre tolerance stated.
4. **Representation** — M6 callout plus `Zentrierform D 60 Grad` note with
   leader; cosmetic thread is not BREP (STEP `THREAD` count 0).
5. **Dimensioning** — layer-3 internal-thread recipe; t1-style depth notes
   where unassociatable.
6. **Source** — user decision 2026-09-07 + assumed proportions; NORM
   ORIGINAL PENDING.
7. **API notes** — `HolePackageBuilder` threaded hole with
   `ThreadedStartChamferAngle '60'` (from face), depths as strings,
   `Tolerance = 0.01`; verification: tap cylinder r≈2.5 present, lead cone
   half-angle 30°±2° from axis via `UF.Modeling.AskFaceData` (kind 17),
   45° end chamfer of the part correctly excluded. Runs
   `20260907T072011Z-706c3de3` (check design wrong twice, geometry right),
   `20260907T072108Z-24b9e214` (9/9 green).

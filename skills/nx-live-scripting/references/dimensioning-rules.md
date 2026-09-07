# Dimensioning rules (layer 3: norms → drawing)

Generic, reusable rules for norm-correct dimensioning of turned/milled
production drawings. No part-specific values here — those live with the
project. Source: Labisch/Wählisch, *Technisches Zeichnen*, 7th ed., ch. 5–11
(B. = book page); norms as named. When a rule and the project's drawing
disagree, the project decides and records it; when a rule turns out wrong,
fix it here.

Worked example on this installation (project-specific values, screenshots):
`../../../../10_Online_Machining/docs/bemaßungs-regelwerk.md`.

**Growth:** this file grows feature by feature from the handbook. When a
project needs a feature not covered here (e.g. spline, locknut, gear),
extract the generic rule plus the book page into this file — values stay
with the project, norm facts go to layer 2, the verified call sequence to
layer 4.

## Pre-flight: what to read per feature

**Read this table before writing any code.** Rules first, API second — reading
API-first optimises mechanism over conformity, which is how content details
(remain markings, short-form wordings, limit deviations) get dropped by a sweep
that looks green.

The project columns below are the shape this takes for the consuming project
(`10_Online_Machining`: `F-…` rules and `s…` figure numbers from
`docs/bemaßungs-regelwerk.md`). Another project fills them with its own.

| Feature | Rules here | Project rules + figures | Layer-4 entry |
| --- | --- | --- | --- |
| Bearing seat (shaft) | §7 seat recipe, §2 order, §5 fits, §6 surface | F-1, R-2.4; s082, s142, s145, s157, s242 | Diameter fallback, fits, surface, trial delete |
| Keyway DIN 6885-A | §7 keyway recipe | F-2, R-2.4; s208, s209 | Width placement (**open**: end view), t1 note, section dead end |
| Retaining groove DIN 471 | §7 groove recipe | F-3; s223, s224 | Width/face-twice, detail view, no-t rule |
| Internal thread | §7 thread recipe | F-4; s170, s171, s172 | Thread standard data, `ThreadBuilder` dead end |
| Centre hole | §7 centre recipe | F-5; s201, s205 | provisional Form D → [norm-knowledge.md](norm-knowledge.md) |
| Chamfers, general sizes | §4 symbols, §1 edges | F-6, R-1.4; s089, s094 | Notes + leaders pattern |
| Fits/deviations | §5 ISO fits | R-4.4; s143 | `LimitsAndFits`, deviations note/table |
| Frame, title, tolerances | §1 frame | R-1.x; s069 | Sheet/template, title cells, notes |

Layer-4 entries live in [api-drafting.md](api-drafting.md) (drawing) and
[api-modelling.md](api-modelling.md) (geometry).

## 1. Frame (once per drawing)

- **End state, complete, singular** (B. 69, DIN EN ISO 129-1): every dimension
  refers to the finished part; each dimension appears exactly once, in exactly
  one view; nothing needed for manufacturing may be missing; self-evident
  geometry (e.g. intersection curves) is not dimensioned.
- **Units**: lengths in mm without unit; angles always with unit (`45°`).
- **Title block** (DIN EN ISO 7200): owner, part number, title, drawn-by,
  approved-by, date, document type. Never leave drawn-by empty.
- **General tolerances** beside the title block, e.g. `ISO 2768-m` (lengths/
  angles, DIN ISO 2768-1) resp. `ISO 2768-mK` (plus form/location, DIN ISO
  2768-2). Do NOT apply to auxiliary dimensions `(…)` or theoretically exact
  boxed dimensions.
- **Tolerancing principle** (B. 132–134, DIN EN ISO 8015): default is the
  **independency principle** — size, form and location tolerances apply
  independently. A `Tolerierung ISO 8015` note is good practice. Envelope
  requires `E` behind the size, maximum-material requires `M`; never assume
  either without the symbol.
- **Edges** (B. 124–127, DIN ISO 13715): defined chamfers/radii are dimensioned
  normally. The edge symbol (+/−/±) is only for *indefinite* edges, plus a
  `Kanten ISO 13715` note at the title block.

## 2. Placement and order (B. 69–71, 93)

- **Nesting, small-inside**: with parallel dimension lines the **shortest chain
  sits closest to the part**, larger ones above — small dimensions are
  "housed" by the large ones, so no long extension line crosses a small
  dimension value. Sort ascending inside→outside; re-stack instead of
  squeezing a dimension in later.
- **Spacing**: first line ~**10 mm** from the parallel body edge, further lines
  at **equal spacing ≥ 7 mm**. The 10/8/8 school rule satisfies the norm
  (8 ≥ 7) and may be used as standard. Uneven spacing is a defect.
- **No crossings**: dimension lines never cross each other, other auxiliary
  lines, or run parallel to hatching; extension lines never span several
  views. Escape order when a crossing threatens: (1) pull the dimension to
  the feature side, (2) move it to a view showing the geometry, (3) use a
  leader — **never** let a line cross a dimension value (interrupt line or
  hatching at the number instead).
- **Feature side**: dimension each feature where it lies or is visible and
  crossings stay minimal — diameters of turned parts in the main view,
  groove widths where the groove is visible (section/end view), thread depths
  at the hole representation, narrow grooves in a detail view. Belonging items
  (nominal + tolerance + depth/length) stay together **in one view**.
- **Numerals**: centred above the line, readable **from below and from the
  right** (two reading directions, never mixed), ≥ 2.5 mm (rule of thumb
  3.5 mm), vertical B script. Foot 6/9/66/99 against rotation if needed.
- **Extension lines**: thin-continuous, perpendicular to the measured distance
  (oblique ~60° only for lack of space), **1–2 mm overshoot** past the
  dimension line, only from visible body edges; **centre/symmetry lines may
  serve as (extended) extension lines** — the normal case for diameters.
- **Short dimensions**: extend the line outward and set arrows from outside
  first, then the number outward (preferably right); only then detach the
  number via leader (thin oblique full line).
- **Leaders onto faces**: from outside = solid body, from inside = hollow body
  (bore). Use for hole callouts and chamfers on short edges.

## 3. Manufacturing-related dimensioning (B. 71–81)

- **Turning**: axial dimensions **from one datum face** (second datum after
  re-chucking); **radial always as diameter** (`Ø…`); chamfers, radii,
  grooves separately with position.
- **Milling (keyways)**: from machined datums so the cutter path is readable;
  centred grooves need no location; pure tool runout is not dimensioned.
- **Drilling/threading**: **only the thread nominal** (`M6` = coarse,
  P from DIN 13, no core diameter); **usable thread length + core-hole depth**,
  both from the datum, together with the nominal **in one view**; drill point
  drawn correctly but not dimensioned; countersink via angle + Ø or depth.

## 4. Symbols and additions (B. 82–91)

`Ø` diameter · `R` radius (arrow only at arc) · `M` metric thread (no pitch =
coarse; fine always with pitch) · `□` square, one side only · chamfers
`length × angle`, 45° combined (`1 × 45°`, included in part length) ·
`(…)` auxiliary · `[…]` raw/pre-machining (explain above title block) ·
**rounded frame = inspection dimension** · **rectangular frame =
theoretically exact** (datum for position tolerances).

## 5. ISO fits (B. 135–163, DIN EN ISO 286)

**Lowercase = shaft, UPPERCASE = bore**; letter = position to nominal, number
= grade (size). `h`/`H`: one deviation is zero. Give limit deviations in
brackets behind the fit or in a table at the title block. Grades 01–5 gauges,
**5–13 machined**, 14–18 as-formed. Letters i, l, o, q, w (I, L, O, Q, W) do
not exist. Fits: clearance (both positive), transition (mixed), interference
(both negative); prefer Einheitsbohrung (unit bore H).

## 6. Surface (B. 107–119, DIN EN ISO 1302 / 21920-1)

`Ra 0,8` = fine-finished (neither visible nor tangible); bearing-seat guide:
shaft Ra ≤ 1.6. Drawings often use Rz instead (e.g. collective Rz 6,3) —
same placement rules. Symbol from outside onto edge or extension line, readable
from below/right, **once per surface** (one generator line on solids of
revolution), in the view where the surface is dimensioned; predominant finish
as collective symbol above the title block, exceptions additionally
singled out. No addition = 16 % rule; write `max` for zero exceedance.

## 7. Feature recipes — what the dimensioning must contain

- **Bearing seat (shaft)**: diameter + fit in main view; axial seat length
  from datum, stacked per §2; finish symbol on the same generator line;
  undercut callout (`DIN 509 – F…`) via leader; limit deviations in
  brackets/table (B. 142–143, 200–201, 242).
- **Keyway DIN 6885-A**: **two views** — length in shaft view, width + depth
  in section/end view; seat diameter beside it so the datum face is visible;
  seats: fixed P9, light N9/JS9, sliding H8/D10. Like a slot, but with a
  defined depth (DIN 6885-1/-2).
  - **Depth reference side** (most common error class): **blind (non-open)
    groove in a shaft → from the groove side** to the floor (B. 209);
    **open groove in a shaft → from the opposite side**; groove in a
    **bore → like an open groove** (opposite side to floor), except with a
    second groove opposite — then from the groove side.
  - **Length is absolute**, never centre-to-centre of the end arcs (unlike a
    slot); do not draw arc centres.
  - **Top-view short form**: depth on a leader with the letter **h**
    (DIN 3898); width by dimension line OR on the leader; fit on the leader.
    This is the norm-correct fallback when the depth cannot be dimensioned
    associatively (see layer 4).
  - Special cases (not covered here, DIN 6885-1/-2 originals apply): Woodruff
    keyways, tapered shaft ends/bores (floor parallel to taper axis vs. to
    generator), keyways with slope, simplified retaining-ring grooves.
- **Retaining-ring groove DIN 471/472**: groove width m + groove-base Ø
  (both toleranced), axial position from datum, narrow widths as detail
  view; depth t = (d1−d2)/2 NOT dimensioned; plan axial clearance
  (groove wider than ring); running/direction tolerances on base and
  shoulder (B. 222–224).
- **Internal thread**: thread symbol + nominal, usable length, core-hole Ø
  and depth, countersink (Ø + angle) — all in **one** view; tolerance class
  only off-medium (6H); runout ≈ 2.5×P drawn, not functionally dimensioned;
  usable-length limit as wide full line (B. 169–173, 180).
- **Centre hole**: short form `ISO 6411 – form size/size` at the end face
  plus remain/remove marking a/b/c; full dimensioning as breakthrough/detail
  otherwise (B. 203–205). Note: plain forms A/B/R do NOT share an axis with
  a thread — that needs form D.
- **Remaining geometry**: overall length as the **outermost, largest**
  dimension line housing all axial singles; 45° chamfers in short form.

## 8. Never list (LLM guardrails)

No envelope without `E`, no max-material without `M`; no core-Ø or drill
point dimensioned; no keyway depth from the shaft axis; no groove depth t
dimensioned; no dimension twice; no general tolerance on `(…)`/boxed
dimensions; no plain centre hole coaxial with a thread; finish symbols only
on functional faces, rest via collective symbol; no line across a numeral;
no extension line across views; lettering never below 2.5 mm.

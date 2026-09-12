# Layer 4 — drawing: verified NXOpen calls

**Everything about sheets, views, dimensions and annotations is in this file.**
For geometry use [api-modelling.md](api-modelling.md). *What* to dimension and
*how it must look* is layer 3, [dimensioning-rules.md](dimensioning-rules.md) —
read that **before** this one; API-first reading optimises mechanism over
conformity.

**Need working code fast, not the story behind it?** [SNIPPETS-drafting.md](SNIPPETS-drafting.md)
has the sheet/view/title-block/PDF calls as plain copy-paste blocks with no
rationale/run-id archaeology (dimensions and surface finish are flagged there
as not yet snippet-stable — read the narrative for those). Come back to this
file when a snippet fails or you need the *why*.

Every call sequence here was executed against **NX 2506.3001** on this VM, in a
visible session unless said otherwise. Run ids are the evidence.

**Nothing here is recalled. Unlisted paths are unverified, not impossible.**

Status per entry: **verified** (ran, with `result.json`) · **provisional**
(one data point / hand journal only) · **dead end** ([§9](#9-dead-ends-do-not-re-investigate)).

---

## Index: layer-3 rule → API → trap

### Sheet and views

| Rule | API path | Trap / evidence |
| --- | --- | --- |
| Sheet, frame, title block | `DrawingSheetBuilder UseTemplate` with full path (no elevation needed); `SetTemplateInstantiationIsComplete(True)`; layer 256 visible | Auto-filled cells (scale, mass) are not settable. [§1](#1-sheet-from-the-company-template) |
| Template sheet as the standard | Company template by default; `CustomSize` sheets are probes and scratch only | KUP A3 probe + drawing runs. [§1](#1-sheet-from-the-company-template) |
| Title attributes → cells | 11/13 cells follow `SetUserAttribute`/`SetTimeUserAttribute` (date via `parameters.json`); the rest via `SetCellValueForLabel(label, value)` + indexed re-read | `Text` read-only; `EditableText` silent no-op; `EditCell` 5-arg deprecated. Runs `20260907T071525Z-ca710b73` … `20260907T073617Z-84f81b7e`. [§2](#2-title-block-cells) |
| Base-view placement point | **IGNORED** on NX2506 visible — position post-creation via `MoveView(Point3d)`, absolute sheet coords | Origins 40/60/100 → pixel-identical PDFs. Runs `20260906T193646Z-070e502a` … `20260907T070546Z-328bba4c`. [§3](#3-view-placement) |
| `view.Scale` / `view.Origin` | Viewport-relative readbacks — **never assert on them** | 2.0 set reads 3.16/6.18; constant within a run incl. across `Fit()`. [§3](#3-view-placement) |
| Fresh views in visible NX | `UpdateViews(All, sheet)` after creation + fresh-gate before dims | Lone `Update()` leaves stale views (1 object). Run `20260906T191513Z-2480b9bc`. [§3](#3-view-placement) |
| Layout acceptance without the API | Host ink-bbox gate: `pdftoppm` + runs > 25 mm; assert left ≥ 10 mm, right ≤ 289 mm | Caught x = 0.0 rules that every in-job assert passed. [§3](#3-view-placement) |
| Old iteration sheets off the navigator | Sheet has **no** `Delete()` — invisible undo mark + `AddToDeleteList([sheet])` + `DoUpdate`; cascades views/dims/notes | Prefix guard + explicit keep-list; model untouched. Run `20260907T062735Z-a68f9276` (12 deleted, 1 kept). [§7](#7-sheet-hygiene-and-framing-the-visible-sheet) |
| Watcher sees the whole sheet | `final.Open()` → `part.Views.WorkView.Fit()` + `UpdateDisplay()` | Without `Fit` the window shows a zoomed section. Same run. [§7](#7-sheet-hygiene-and-framing-the-visible-sheet) |
| Session shows stale annotations | `part.Views.Regenerate()` after annotation work, before export + save | `UpdateViews(All)` refreshes geometry only; `UpdateDisplay` alone healed nothing. [§8](#8-regenerate-the-call-that-refreshes-annotations) |
| Which canned view shows a feature's end (not just "is it fresh") | Fixed table `CANNED_VIEW_X_END`, checked before creating the view | A live check via `AskVisibleObjects()` Tags is a dead end — view-local curves, not model faces. [§3](#3-view-placement) end |
| Export a sheet to PDF | `part.PlotManager.CreatePrintPdfbuilder()` + `SourceBuilder.SetSheets([sheet])` + `Filename` + `Commit()` | `session.PlotManager` does not exist — it's on the part. [PDF export](#pdf-export) |

### Dimensions

| Rule | API path | Trap / evidence |
| --- | --- | --- |
| Any dimension, text centred | `NewDimensionData` + `NewAssociativity` per object + `CreateHorizontalDimension`; `dim.IsOriginCentered = True` | Centred is wrong for a diameter in a longitudinal view ("inside the part"). [§4](#4-dimensions-the-general-shape) |
| Diameter in longitudinal view | Cylindrical **face, twice**, `AssociativityPointOption.OnCurve`, `CreateCylindricalDimension` | Circular edges report the axial distance — a plausible wrong number (29 for 25). [§4](#4-dimensions-the-general-shape) |
| Diameter fallback that verifies | `CreateDiameterDimension` on one circular edge with `OnCurve` in an **end view** | `CreateDiametralDimension`/`CreateRadialDimension` do not exist. Runs `20260906T101016Z-ad1f55e9`, `20260906T101340Z-3497fe52`. [§4](#4-dimensions-the-general-shape) |
| Lengths on turned parts | Circular edges with `ArcCenter`, not planar faces | Planar faces fail with `The planar face cannot be projected`. [§4](#4-dimensions-the-general-shape) |
| Lengths without rim vertices | Station-known rim arcs (`arcs_at`: all vertices share one X) + `ArcCenter`; diameters station-free end-on | Full circles lack vertices; chamfered end rims are Ø23/Ø18. Drawing runs …`84a85e84` … `070e502a`. [§4](#4-dimensions-the-general-shape) |
| ISO fit instead of typed deviations | `dim.ToleranceType = ToleranceType.LimitsAndFits`; `dim.LimitFitDeviation = 'h'` (`'P'` internal); `dim.LimitFitGrade = 6` | On the builder path it is `Style.DimensionStyle.LimitFitDeviation` as a string. [§4](#4-dimensions-the-general-shape) |
| Every dimension asserts itself | Compare `dim.ComputedSize` to the nominal in the job, report both | A wrong association becomes a failed run, not a wrong drawing. [§4](#4-dimensions-the-general-shape) |
| Trial dimensions | Real objects — delete each rejected one via invisible undo mark + `AddToDeleteList` + `DoUpdate` | Otherwise they stay on the sheet. [§4](#4-dimensions-the-general-shape) |
| Text placement that holds in session **and** print | `Dimensions.CreateLinearDimensionBuilder(Null)` + `Drag` associative origin | Direct `dim.AnnotationOrigin = Point3d` writes **NaN** (proven twice). [§5](#5-dimension-text-placement-via-the-builder) |
| Narrow dims placed outside | **Omit** `TextCentered` — `True` forces print-time centring over the explicit origin | Runs `…c886ae1c` vs `…90ef799d`, pixel-verified. [§5](#5-dimension-text-placement-via-the-builder) |
| Linear-dim associativity (dialog path) | View-extracted curves: `view.DraftingBodies.FindObject(…)` → `DraftingCurves.FindObject("(Extracted Edge) …")` + `SnapType.Center` | Model edges do **not** attach on this path; runtime names are view-specific — search, never hardcode. [§5](#5-dimension-text-placement-via-the-builder) |
| Ring groove width (DIN 471, narrow) | Station-extracted drafting curves (journal IDs carry model coords — parse triplets, match station ±0.5) + `CreateLinearDimensionBuilder` + `SnapType.Center` + explicit origin; sweep pairs, assert, delete rejects | Silhouette curves do **not** carry `Center` (`first object associativity type is invalid`). Runs `…604d6ec8`, `…c886ae1c`. [§5](#5-dimension-text-placement-via-the-builder) |
| Keyway width placement | Front view (NX is Z-up: Top overlaps the floor edges → 0.0, correctly rejected); floor edges + `OnCurve`, `CreateVerticalDimension` | Flank faces fail 5–6×. **OPEN:** the end-view association per layer-3 rule F-2 was never swept — Front was expedience. Run `20260906T192021Z-dd5937e4`. |
| Keyway depth `t1` | **No verified path** | State as a note; norm-correct form is the top-view leader with letter **h** (layer 3). [§9](#9-dead-ends-do-not-re-investigate) |
| Keyway length overall (Form A, absolute) | **Unverified**: `Tangent` on the R3 end arcs returns the centre distance (12.0 for an 18 slot), never the outer extremes | State in a note until a working associativity is swept. Run `…bc1ca8a0`. [§9](#9-dead-ends-do-not-re-investigate) |

### Annotations

| Rule | API path | Trap / evidence |
| --- | --- | --- |
| Finish symbol with value | `DraftingSurfaceFinishBuilder`; setter is `Finish`, not `FinishType`; **Modifier** variants only; `SingleRoughnessValue = True`, `A1 = 'Ra 0,8'` | Without a Modifier variant NX draws the tick and silently drops the value, in every spelling. [§6](#6-surface-finish-notes-leaders) |
| Leader onto geometry | `CreateLeaderData`, `FilledArrow`, `StubSide Inferred`, `Leader.SetValue(obj, view, MODEL-Point3d)` | `(0,0,0)` routes to the model origin — a diagonal across the sheet. Pass the edge midpoint from `GetVertices()`. Runs `20260906T193518Z-c13eca35`, `20260906T193646Z-070e502a`. [§6](#6-surface-finish-notes-leaders) |
| Note text / placement | `Text.TextBlock.SetText` takes a **list** of strings; `Origin.OriginPoint = Point3d` directly | A single string fails; an unset origin lands notes in the sheet corner. [§6](#6-surface-finish-notes-leaders) |

---

## 1. Sheet from the company template

The documented route copies the template into
`C:\Program Files\Siemens\NX…\UGII\templates` — that needs elevation. A full
path works just as well. Drawings go on the company template **by default** — the standing rule in
[job-contract.md](job-contract.md). The canonical source is this toolkit's own
`templates/` (see its README), VM-synced to
`C:/Users/hanne/Documents/OnlineMachiningNX/templates/`, which is the path the
jobs hold in their `TEMPLATE` constant. `CustomSize` sheets are probes and
scratch only.

```python
builder = part.DrawingSheets.DrawingSheetBuilder(None)
builder.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
builder.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
builder.MetricSheetTemplateLocation = r'C:\...\KUP_Zeichenvorlage.prt'
sheet = builder.Commit(); builder.Destroy()
sheet.Open()

# Without this the part stays half-instantiated. A part saved in that state
# later refuses to open with "Corrupt data found when loading an OM file".
part.Drafting.SetTemplateInstantiationIsComplete(True)

# Frame and title block arrive on layer 256 in state "visible only" (2).
# Set it visible or both are missing from the PDF.
part.Layers.SetState(256, NXOpen.Layer.State.Visible)
```

Probe: `template_probe.py` inspects a template part before use — sheets, sizes,
tables, title blocks, and the attribute titles its cells read. Attribute titles
are read off the template part itself (job `03_jobs/spark3_template.py`; no
`CloseAll` in visible sessions).

Sheet name and scale come from the template, not from the builder. Change them
afterwards with
`sheet.SetParameters(height, length, numerator, denominator, units, projection_angle)`.

**Two template side effects:**

- Instantiation spawns `SKETCH_<Blatt>_000`. Keep it out of the layer-21 sweep
  ([api-modelling.md §3](api-modelling.md#3-sketches-datums-and-why-loose-curves-are-a-defect))
  or the frame vanishes — observed, then scoped to `SKIZZE_*` + datums only.
- Fresh template sheets are named `Blatt 1`. A purge guard must match the
  project prefix **or** that name.

**The template's scale cell is fixed** (KUP: 1:1). Views follow it, never the
reverse — otherwise the title block lies.
Run `20260907T072323Z-58cc2931` (6/6 green on template, A3 PDF accepted).

---

## 2. Title block cells

Cells are filled from **part attributes**, set before or after the sheet exists:

```python
part.SetUserAttribute('Bezeichnung/Titel', -1, 'Prüfkörper', NXOpen.Update.Option.Now)
part.SetTimeUserAttribute('Datum', -1, '06-Sep-2026 00:00:00', NXOpen.Update.Option.Now)
```

A time attribute wants `DD-Mon-YYYY hh:mm:ss`; ISO-8601 is refused with
`The date value is invalid.` The date comes from `parameters.json`, never from
`os.environ` ([job-contract.md](job-contract.md), hard requirement 5).

**Collection access** (3 dispatches burned): `part.DraftingManager` **is** the
`DraftingApplicationManager`. `part.Annotations.TitleBlocks` and
`session.DraftingApplicationManager` do **not** exist. Read labels at runtime
(`Cells.Length` / `FindItem(i)` → `.Label`; `ObjectList` is not iterable), match
case-insensitively, and write neutrals (`Name`, `Matrikel-Nr.`, …) as `-`.
Runs `…df72d2f7` (accessor dead ends), `…bf811165` (labels), `…ae072278`
(neutrals).

**Correction, 2026-09-08** (run `20260907T222440Z-226cee6d`): the plain
`TitleBlock` object returned by `part.DraftingManager.TitleBlocks` has **no**
`Cells` property (`AttributeError`), and the `EditTitleBlockBuilder` itself
exposes no enumerable cell collection either — only `Get/SetCellValueForLabel`.
There is no verified runtime cell-label scan on this build — though see the
correction below: `mvtp_probe_titleblock.py` (run `20260908T071811Z-35c87b00`)
found `EditTitleBlockBuilder.Cells` after all (`.Length` = 13,
`.FindItem(i).Label`/`.Text`), so a scan is possible; the `try/except` sweep
below remains the simpler path when the labels are already known. Call
`SetCellValueForLabel` directly with the known label string (this section
already lists them: `Allgemeintoleranz`, `Material, wird automatisch
ausgefüllt`, …), each in its own `try/except` so one unmatched label doesn't
lose the rest:

```python
for label, value in (('Allgemeintoleranz', 'ISO 2768-m'),
                      ('Material, wird automatisch ausgefüllt', '1.4301')):
    try:
        etb.SetCellValueForLabel(label, value)
    except Exception:
        ...  # record and continue
```

**`SetCellValueForLabel` does not raise on an unmatched label — it silently
no-ops.** `'Material_manuell'` (a label that does not exist on this template;
the real label is `'Material, wird automatisch ausgefüllt'`, see below) ran
with no exception and reported success, but wrote nothing. A `try/except`
around the call catches a real failure, not this one — after the sweep,
re-read each cell's `.Text` (via `Cells.FindItem(i)`, above) and compare
against what was intended before trusting a "set" report. Found rendering
`mvtp_zeichnung.py`'s PDF to PNG and inspecting it (the Allgemeintoleranz/
Werkstoff cells still showed template defaults), run `20260908T071154Z-82b788dc`.

**Cells that ignore attributes** are edited directly. The verified chain, each
step settled by one run: `TitleBlockCellBuilder.Text` is read-only →
`EditableText` assigns silently without effect → `EditCell(a,b,c,d,e)` needs 5
args (deprecated since NX12.0.1) → **`EditTitleBlockBuilder.SetCellValueForLabel(label, value)`**
+ `Commit`, then indexed re-read.
Runs `20260907T072949Z-7c40caf8` (map: 13 cells with labels),
`20260907T073054Z-a678a6e6` (chain), `20260907T073617Z-84f81b7e`
(`cells_ok: true`, PDF-accepted title block).

On the KUP template exactly two cells need this: cell 8 (`Allgemeintoleranz`)
and cell 11 (`Material, wird automatisch ausgefüllt` — despite the name, this
is the manual-override cell, not an auto-filled one; there is no separate
`Material_manuell` label on this template, confirmed by enumerating all 13
cell labels, run `20260908T071811Z-35c87b00`); the other 11 follow
attributes. KUP defaults that must be **overridden**: `Bezeichnung/Titel`,
`Allgemeintoleranz`, `Material, wird automatisch ausgefüllt`, neutral `-` for
course/personal fields, `Datum` as a time attribute.

**Once a part carries more than one sheet, `DraftingManager.TitleBlocks[0]`
is the OLDEST title block, not the one on the sheet just created.** Editing
cells by a fixed index silently lands on the wrong sheet's title block once a
second sheet exists — the write succeeds, `Commit()` raises nothing, but the
sheet actually being exported still shows template defaults. Diff the tag set
before/after creating the new sheet and edit only the block that is new:

```python
before = {int(b.Tag) for b in part.DraftingManager.TitleBlocks}
sheet = create_sheet(part)            # DrawingSheetBuilder, as above
new_blocks = [b for b in part.DraftingManager.TitleBlocks
              if int(b.Tag) not in before]
assert len(new_blocks) == 1
```

Found the same way as the silent-no-op above: rendering a second sheet's PDF
after a first sheet already existed on the part showed template defaults
despite a reported `'set'`. Fixed and reverified in run
`20260908T072255Z-bf730d30` (`new_blocks: 1`, correct values in the render).

`SCALE`/`WEIGHT`/`CAL_WEIGHT` fill from NX itself and are **not** settable from
the API — leave them. Weight stays empty until a physical material is assigned
(open micro-point, cosmetic).

---

## 3. View placement

`sheet.SheetDraftingViews.CreateBaseView(model_view, Point3d(x, y, 0), scale, False)`
**ignores the placement point** on NX 2506.3001 in a visible session: three
identical drawing runs with origins 40 / 60 / 100
(`20260906T193646Z-070e502a`, `20260907T064416Z-cc0afc93`,
`20260907T064615Z-e10d1bd9`, job `03_jobs/spark3_zeichnung.py`) produce
pixel-identical PDFs. NX auto-arranges base views from the sheet origin. **Do
not steer layout through the creation point.**

The working sequence, watcher-judged stepwise (`03_jobs/spark3_step*.py`):

```python
view = sheet.SheetDraftingViews.CreateBaseView(model_view, Point3d(x, y, 0), scale, False)
part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)   # fills it
view.MoveView(NXOpen.Point3d(x_abs, y_abs, 0.0))       # absolute SHEET coordinates
```

**The enum and the overload above were both wrong in an earlier version of this
note** — corrected 2026-09-08 (run `20260907T222440Z-226cee6d` hit both):
the enum is `NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption`, not
`NXOpen.Drafting.ViewUpdateOption` (`AttributeError`); and of
`DraftingViewCollection`'s three `UpdateViews` overloads
(`(ViewUpdateOption)`, `(ViewUpdateOption, DrawingSheet)`, `(DraftingView[])`),
the two-argument one takes a **single** `DrawingSheet`, not `[sheet]`
(`TypeError`). Confirmed working from run `20260907T222811Z-e120df81` onward.

1. blank sheet shows only the dashed frame (`…070035Z-6a1d4ae8`, empty frame
   flush at the frame edge),
2. `UpdateViews(All)` fills it in place (`…070321Z-7b7afd55`, 0 → 16 objects),
3. `MoveView` relocates it (`…070546Z-328bba4c`: `Front@46` moved visibly right
   with reserve to the frame, origin −39.09 → −35.0, user screenshot).

`Fit()` only frames the *window*; readbacks stay constant across it.

**Do not use, do not assert on:**

- `view.Origin` is read-only and returns model space; `view.SetOrigin(…)`
  answers `View may not be scaled nor translated`. (`SetOrigin` exists as a
  sibling of `MoveView` — unneeded.)
- `CalculateMinMaxBox()` also returns model space.
- `view.Scale` / `view.Origin` readbacks are **viewport-relative**: creation
  scale 2.0 reads back 3.16 / 6.18 across runs with identical code, constant
  within a run including across `Fit()`. They follow the window viewport, not
  the drafting data.

**A lone `view.Update()` is not enough** in a visible session: right after
`CreateBaseView` the view still reports `IsOutOfDate true` with 1 object. Gate
on freshness after the collective `UpdateViews(All)` and proceed only when
fresh. Run `20260906T191513Z-2480b9bc`. (The batch path has a sibling trap —
[operations.md](operations.md), *The batch trap*.)

**The collective `UpdateViews(All)` alone is not always enough either.**
Run `20260907T222712Z-5443070b`: `front.IsOutOfDate` was still `True` right
after `UpdateViews(All)` + `MoveView`. Fixed by retrying, calling **both**
`part.DraftingViews.UpdateViews(All, sheet)` **and** the view's own
`drafting_view.Update()`, gated on `IsOutOfDate is False` and a non-empty
`AskVisibleObjects()`; 1–2 retries with a short pause resolved it every time
(run `20260907T222811Z-e120df81` onward). A short retry loop is cheap and
removes the need to guess how many update calls a given view will need:

```python
for attempt in range(5):
    part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    drafting_view.Update()
    part.Views.WorkView.UpdateDisplay()
    if drafting_view.IsOutOfDate is False and list(drafting_view.AskVisibleObjects()):
        break
    time.sleep(0.5)
```

**Layout acceptance is a host-side gate**, independent of API semantics: render
the PDF (`pdftoppm -png -r 100`), threshold, collect horizontal runs longer than
25 mm, assert left margin ≥ 10 mm and right edge ≤ 289 mm. Text and dust never
form 25 mm runs, so the gate only sees rules (outlines, dimension lines,
borders). It caught content touching x = 0.0 that every in-job assert had
passed. `01_host/nx_check_result.py --gate-pdf` implements it.

**Open (measured, not explained):** long rules touching x = 0.0 even though all
placed content starts far right of it — view-border/centreline class suspected
(they track views, not the sheet), identity not isolated.

**Which canned view shows which end of the part — verified, don't re-derive
per part.** 'Right' exposes the part's **max**-coordinate end along the
model's long axis (its camera looks toward the origin from the positive
side); 'Left' is diametrically opposite and exposes the **min**-coordinate
end. Front/Top/Back/Bottom look along the other two axes and show the
profile, not an axis-end. This is a fixed fact about NX's absolute-WCS named
views (both first- and third-angle drafting convention agree on which axis
each name looks along; only the sheet layout differs) — not part geometry —
so check it once per axis convention and keep it as a table, not a live
per-view query (the natural-seeming live check is a dead end, see below).
Caught a real bug this way: a threaded hole placed at the part's min-X end
was reported as shown by a 'Right' base view purely because the view was
non-stale and had visible objects — neither of which says *which* end. Fixed
by picking 'Left' and asserting the table match **before** creating any
view, zero extra NX calls. Runs `20260907T191233Z-a97821e0` (confirms
Right→max, the bug), `20260907T200346Z-8ea44fb6` (confirms Left→min, the fix).

**Which canned view shows a Y/Z-oriented feature (e.g. a keyway cut with
`Direction = (0, ±1, 0)`, [api-modelling.md §5](api-modelling.md#5-keyway-form-a-as-a-sketch-defined-extrusion)) — the same class of mistake, one axis over.**
A feature cut on the far side of a view's camera does not render at all in
this NX config (neither solid nor dashed — the same silent-drop mechanism as
the occluded-circular-edge case below), so picking the wrong named view for a
Y/Z-directional cut makes it vanish from that view exactly like the wrong
X-end pick above, and the fix is the same shape: decode the camera direction
from `ModelingView.Matrix` **before** creating the view, don't render-and-see.
`Matrix` exposes `Xx,Xy,Xz,Yx,Yy,Yz,Zx,Zy,Zz`; its **Z-row is the direction
from the model toward the viewer** (confirmed against the already-known
Top→looks-along-−Z fact: Top's `Zx,Zy,Zz` = `(0,0,1)`, i.e. `+Z` toward the
viewer, consistent with a camera above looking down):

```python
CANNED_VIEW_TOWARD_VIEWER = {          # (Zx, Zy, Zz) of ModelingView.Matrix
    'Front': (0, -1, 0), 'Back': (0, 1, 0),      # Y axis
    'Top': (0, 0, 1), 'Bottom': (0, 0, -1),      # Z axis
    'Left': (-1, 0, 0), 'Right': (1, 0, 0),      # X axis (matches CANNED_VIEW_X_END)
}
```

A feature cut with `Direction (0, +1, 0)` (material removed toward `+Y`) sits
on the near/visible side of `Back` (toward-viewer `+Y`) and the far/hidden
side of `Front` (toward-viewer `-Y`). Caught the same way as the X-end bug:
a keyway built with `cut_direction=+1.0` did not appear in a `Front` base
view at all, at any render resolution (600 dpi checked) — confirmed by
probing `Front`'s own `Matrix` (`mvtp_probe_viewdir.py`,
run `20260908T071653Z-50d132bb`) and fixed by switching the base view to
`Back`, reverified by re-rendering the PDF (run `20260908T072255Z-bf730d30`).
Verified on `Front`/`Back`/`Top`/`Bottom`/`Left`/`Right` in that same probe;
`Left`/`Right`'s toward-viewer rows agree with the already-established
`CANNED_VIEW_X_END` table above, cross-checking the decode.

**A rotationally symmetric feature (e.g. a DIN 471 groove cut directly into
the revolve profile) is a separate, still-open case — the Front/Back fix
above does not apply to it.** Its radius step should change the true
silhouette on every longitudinal view regardless of near/far side, yet it
still did not render as an outline notch even from the corrected `Back` view
(checked at 600 dpi, tight crop) — only its two boundary edges show, as short
radial lines. Not explained by the near/far mechanism above; grouped with the
occluded-circular-edge case in [Open mappings](#open-mappings-rule-known-api-path-not-verified)
as the same class of unresolved small-feature silhouette gap. Runs
`20260908T070517Z-cfe4ad0e` (groove geometry verified present via face
radius), `20260908T072255Z-bf730d30` (still missing from the render after
the view-side fix).

---

## 4. Dimensions: the general shape

```python
data = part.Annotations.NewDimensionData()
for index, (obj, view, option) in enumerate(objects, 1):
    assoc = part.Annotations.NewAssociativity()
    assoc.FirstObject, assoc.ObjectView, assoc.PointOption = obj, view, option
    data.SetAssociativity(index, [assoc])
dim = part.Dimensions.CreateHorizontalDimension(data, NXOpen.Point3d(x, y, 0.0))
dim.IsOriginCentered = True          # text centred on the dimension line
```

For placement-critical dimensions (narrow, chained) use the builder path in
[§5](#5-dimension-text-placement-via-the-builder) instead.

- **`IsOriginCentered` overrides the placement point.** Right for lengths, wrong
  for a diameter in a longitudinal view, where centred means "inside the part".
- **Diameters on a longitudinal view need the cylindrical *face*, twice**, with
  `AssociativityPointOption.OnCurve`. With the circular edges,
  `CreateCylindricalDimension` measures the axial distance between them and
  reports a plausible wrong number (29 instead of 25).
- **Diameters end-on are the fallback that verifies.** `CreateDiameterDimension`
  exists (`CreateDiametralDimension` and `CreateRadialDimension` do not); one
  circular edge with `OnCurve` in an end view returns the edge's own diameter
  and asserts cleanly. Used when all five point options on the cylindrical face
  in a longitudinal view answer `The orientation of input face object is not
  correct` (runs `20260906T101016Z-ad1f55e9`, `20260906T101340Z-3497fe52`).
  This is an attempt outcome, not an impossibility: diameters in a longitudinal
  view do work elsewhere; the differing mechanism is unknown.
- **Lengths go on circular edges with `ArcCenter`.** Planar faces as length
  references fail with `The planar face cannot be projected`. Where rims have no
  vertices, use station-known rim arcs
  ([api-modelling.md §7](api-modelling.md#7-measuring-the-solid-instead-of-trusting-the-picture)).
- **ISO fits instead of typed deviations:**

```python
dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
dim.LimitFitDeviation = 'h'          # 'P' for an internal feature
dim.LimitFitGrade = 6
```

- **Trial dimensions are real objects.** Searching for the right associativity
  leaves them on the sheet. Remove each rejected one:

```python
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Probemaß')
session.UpdateManager.AddToDeleteList([dim])
session.UpdateManager.DoUpdate(mark)
```

- **Assert every dimension.** `dim.ComputedSize` against the nominal turns a
  wrong association into a failed run instead of a wrong drawing. Record the
  `view` and the layer-3 `rule` per dimension too — a correct number in the
  wrong view still breaks the rule ([job-contract.md](job-contract.md)).

---

## 5. Dimension text placement via the builder

Direct creation (`CreateHorizontal/VerticalDimension` + post-hoc
`IsOriginCentered`) leaves text placement partly uncontrolled: the print path
centres narrow text on its own, the session follows anchors the job never
reliably set — and a direct `dim.AnnotationOrigin = Point3d` write reads back
`NaN` (two runs; the dim then behaves corrupt).

**Provisional — recorded from the user's own hand journal `journal_1_1_hand.py`
(1.1 recreated live in the session), not yet from a dispatched job:**

```python
b = part.Dimensions.CreateLinearDimensionBuilder(NXOpen.Annotations.Dimension.Null)
b.Origin.Anchor = NXOpen.Annotations.OriginBuilder.AlignmentPosition.MidCenter
b.Origin.SetInferRelativeToGeometry(False)
b.Origin.Origin.SetValue(NXOpen.TaggedObject.Null, NXOpen.View.Null, point)  # explicit!
assoc = NXOpen.Annotations.Annotation.AssociativeOriginData()
assoc.OriginType = NXOpen.Annotations.AssociativeOriginType.Drag
# View/ViewOfGeometry/PointOnGeometry Null, alignments TopLeft, the rest default
b.Origin.SetAssociativeOrigin(assoc)
b.Origin.Origin.SetValue(NXOpen.TaggedObject.Null, NXOpen.View.Null, point2)  # final
b.Style.DimensionStyle.TextCentered = True
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Linear Dimension')
obj = b.Commit()
session.DeleteUndoMark(mark, None)
b.Destroy()
```

The Drag origin persists through print — that is what the direct path does not
achieve.

**`TextCentered = True` forces print-time centring on the line, overriding the
explicit origin.** For text that must stay outside (narrow widths), **omit it**:
with a `Drag` origin and default centring the print keeps the hand-placed
outside position (`1,1 +0,14/-0` beside the arrows, run `…90ef799d`,
pixel-verified, versus `…c886ae1c` on the same part). So: `TextCentered = True`
for centred lengths, omit for outside-placed narrow dims. Per-dim narrow
preferences (`DisplayType`, `TextOffset`) are print-ignored in both directions
(`+4.0` / `−4.0` render identically centred; orphan run `…fc7210d2`).

**Associativity on this path goes through view-extracted curves, not model
edges:**

```python
body  = view.DraftingBodies.FindObject(...)
curve = body.DraftingCurves.FindObject("(Extracted Edge) ...")
b.FirstAssociativity.SetValue(NXOpen.Annotations.AssociativityType.SnapType.Center,
                              curve, view, modelPoint, None, None, Point3d(0,0,0))
```

Runtime curve names are view-specific — **search for the curve, never hardcode a
`FindObject` string** in a reusable job. Fits live on the builder here too
(`Style.DimensionStyle.LimitFitDeviation = 'H'` as a string, shaft via
`LimitFitShaftDeviation`).

**Narrow features (ring groove, DIN 471):** journal identifiers of drafting
curves carry model coordinates — parse the triplets and match the station to
±0.5, then sweep candidate pairs, assert `ComputedSize`, and delete the
rejects. Silhouette curves do **not** carry `Center` and answer `first object
associativity type is invalid`. Runs `…604d6ec8`, `…c886ae1c`.

**Trial `SetValue` points are real placements** — the 1.1 needed two recorded
drags (`(115.9, 246.0)` then `(127.0, 246.0)`).

**Open:** whether `AnnotationOrigin` reads back numeric after a builder
`SetValue` (the direct write reads back `NaN` — proven). Note that NaN is what
NX itself records on a text drag, so it means auto-layout, not corruption per
se.

---

## 6. Surface finish, notes, leaders

```python
builder = part.Annotations.DraftingSurfaceFinishSymbols \
    .CreateDraftingSurfaceFinishBuilder(None)
# `FinishType` is read-only; the setter is `Finish`. Only the *Modifier*
# variants carry the extension line that the value sits on — without it NX draws
# the tick and silently drops the roughness value, in every spelling.
builder.Finish = NXOpen.Annotations.DraftingSurfaceFinishBuilderFinishType \
    .ModifierMaterialRemovalRequired
builder.SingleRoughnessValue = True
builder.A1 = 'Ra 0,8'
```

A leader onto a real object survives model changes; a leader onto a free point
does not:

```python
data = part.Annotations.CreateLeaderData()
data.Arrowhead = NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
data.StubSide = NXOpen.Annotations.LeaderSide.Inferred
data.Leader.SetValue(edge, view, midpoint)      # MODEL-space Point3d
builder.Leader.Leaders.Append(data)
```

The same `Leader` block works on `CreateDraftingNoteBuilder`.

**`Leader.SetValue` takes a model-space point.** `(0,0,0)` routes the leader to
the model origin — a diagonal across the whole sheet. Pass the edge midpoint
from `GetVertices()` for a short direct leader. Runs
`20260906T193518Z-c13eca35` (diagonal), `20260906T193646Z-070e502a` (short
leader, accepted PDF).

**Note text** goes through `builder.Text.TextBlock.SetText` with a **list** of
strings (one per line) — a single string fails with `First parameter is
invalid. Expecting List of Unicode str`.

**Placement** goes through `builder.Origin.OriginPoint = Point3d` directly:
`OriginBuilder` has **no** `PlaneReference` (`AttributeError`), and `Plane` is
read-only too. Always set it — for notes *and* symbols — or the annotation
commits fine and lands in the sheet corner with leaders across the whole
drawing. Runs `20260906T101708Z-…` … `20260906T104405Z-b77d74f9` (final:
visually accepted).

**Check content, not just mechanics.** A sweep that optimises associativity and
placement silently drops content details (remain markings, short-form wordings,
limit deviations). Every annotation needs its layer-3 rulebook line verified.

---

## 7. Sheet hygiene and framing the visible sheet

Iterative drawing work leaves one sheet per run on the part (SPARK3: 13 sheets,
2 of them red-X failures). The Part Navigator rots and the watcher loses the
accepted sheet. Cleanup is a drafting-only job — model features are never
touched.

`DraftingDrawingSheet` has **no** `Delete()` (member dump in the run below).
Delete through the trial-dimension path — it works for sheets and cascades
their views, dimensions, notes and symbols:

```python
sheets = list(part.DrawingSheets)   # inventory: name + view count each
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
session.UpdateManager.AddToDeleteList([sheet])
session.UpdateManager.DoUpdate(mark)
```

Guardrails that make this safe: match names by project prefix (`SPARK3_*`) or
the fresh-template name `Blatt 1`, keep an explicit keep-list (the visually
accepted sheet), never touch foreign sheets, one visible undo mark over the
whole cleanup so a wrong deletion is recoverable by hand. **Open the final
sheet first, then delete the rest.**

Run `20260907T062735Z-a68f9276` (`03_jobs/spark3_cleanup.py`): 12 sheets
deleted (incl. both red-X ones), `SPARK3_070e502a` kept with 3 views, model
features (`REVOLVED/BLOCK/SIMPLE HOLE/THREADED HOLE`) verified untouched, part
saved, `failed: []`.

Sheet deletion can crash natively — see the SEHException row in
[operations.md](operations.md), *Failure triage*. Prefer uniquely named sheets
(`SetName`) over purging.

**Framing for the watcher.** After `final.Open()`, `part.Views.WorkView` is a
`View` that **has** a `Fit` member. `Fit()` + `UpdateDisplay()` frames the whole
sheet — without it the drafting window shows a zoomed section and the user
cannot see the drawing (user screenshot 2026-09-07). Put the `Fit` at the end
of every drawing/cleanup job, right after the final `Open()`.
`ModelingViews.WorkView` answers `not a model view` on an open sheet.

**The dashed rectangle in the NX window is the sheet frame itself** — present on
an empty `CustomSize` sheet, aspect equal to the sheet size (297:210). It is not
data (`BordersAndZones` is `None`, no drafting sketches). Content crowding that
frame comes from view placement ([§3](#3-view-placement)), never from the frame.
Run `20260907T065728Z-c457ecb5` (`03_jobs/spark3_reset.py`, blank
`SPARK3_WATCH`).

---

## 8. `Regenerate`: the call that refreshes annotations

`DraftingViews.UpdateViews(All)` refreshes **geometry** (`IsOutOfDate`,
`AskVisibleObjects`) but leaves the interactive session showing stale annotation
layout and missing tolerances — while the print path (full layout) already
renders correctly. Symptom class, 2026-09-07: the session showed no limit
deviations and displaced texts for the same data the PDF rendered correctly.
The gallery action *View → Layout → Regenerate All Views* heals the session.

Recorded calls (user hand journal `journal1`):

```python
# Menu: View->Layout->Update Display
workPart.Views.UpdateDisplay()
# Menu: View->Layout->Regenerate
workPart.Views.Regenerate()
```

**Call `part.Views.Regenerate()` after any annotation work and before export +
save, in every generation job.** `UpdateDisplay` alone healed nothing in the
observed case (user-observed 2026-09-07); keep the pair — it is cheap — but
`Regenerate` is the load-bearing call. This is a standing rule, listed in
[job-contract.md](job-contract.md) and present in
[../assets/job-template.py](../assets/job-template.py).

Same journal's side finding: `AnnotationOrigin = NaN` is what NX itself records
on a text drag ([§5](#5-dimension-text-placement-via-the-builder)) — NaN means
auto-layout, not corruption per se.

---

## PDF export

`part.PlotManager.CreatePrintPdfbuilder()` — **not** `session.PlotManager`
(`AttributeError: 'NXOpen.Session' object has no attribute 'PlotManager'. Did
you mean: 'XYPlotManager'?`). `PlotManager` lives on the `BasePart`. Its
`SourceBuilder` is a `PlotSourceBuilder` with `SetSheets(list)` (there is no
plain `Sheets` property to assign). Verified: probe `03_jobs/pk6_probe_pdf.py`
(run `20260907T222123Z-7115648c`, member dump), used successfully in run
`20260907T223720Z-0b0c669f` (133595-byte PDF, rendered to PNG via `pdftoppm`
and visually inspected — frame, title block, views, dimensions all present).

```python
builder = part.PlotManager.CreatePrintPdfbuilder()
builder.SourceBuilder.SetSheets([sheet])       # the DrawingSheet(s) to export
builder.Filename = str(pdf_path)               # full path, VM-side
builder.Commit()
builder.Destroy()
```

Call this after `part.Views.Regenerate()` and `part.Save(...)`, not before —
same ordering as any other export.

**Gate before `Commit()`: helpers must be invisible, or they print.**
Loose profile curves, sketches and datum planes that are still on a visible
layer are drawn into every drafting view — including the exported PDF — with
no error anywhere. Hiding them is [api-modelling.md
§3](api-modelling.md#3-sketches-datums-and-why-loose-curves-are-a-defect)
(`MoveDisplayableObjects` to 21/61 + `SetState(Hidden)`), but hiding alone is
not the claim: assert the states right here
(`part.Layers.GetState(21) is Hidden`, same for 61) before committing the
PDF, and inspect the render for stray lines before calling the drawing done.
Verified 2026-09-08 (run `20260908T210544Z-3bd57207`: helpers hidden in J1–J3,
render clean, 9/9 dims green).

---

## Open mappings: rule known, API path not verified

Freistich callout as a drafting entity; associative ordinate/chain
dimensioning; weld and edge-symbol builders. Keyway width in the **end** view
(layer-3 rule F-2) — the Front placement that ran was expedience, the end-view
association was never swept.

**Occluded circular edges do not render as hidden (dashed) circles in a base
end view, and the two obvious style toggles do not fix it.** A shaft's
`Diameter20`/`Diameter19` circular edges, behind a `Diameter25` end face in a
`RIGHT` base end view, were confirmed absent by rendering the exported PDF to
PNG and visually inspecting it (only the outer boundary + a through-hole
visible, even though the diametral *dimensions* referencing those edges were
numerically correct via `ComputedSize`). `view.Style.HiddenLines.Hiddenline`
and `.SelfHidden` both already read `True` by default; explicitly setting
either to `True` again left `AskVisibleObjects()` at the same count (6).
Probes `03_jobs/pk6_probe_hiddenline.py`, runs `20260907T223456Z-e4f3989e`,
`20260907T223535Z-8e221985`. Mechanism unidentified — not further
investigated; do not re-try just these two toggles without a new idea. The
longitudinal view is **not** a ready fallback either: its direct
cylindrical-face `CreateCylindricalDimension` route is a documented dead end
on this build ([§4](#4-dimensions-the-general-shape)). Until one of the two is
actually fixed, an end-view diametral dimension with the correct
`ComputedSize` but no matching visible circle is the best verified option —
acceptable because the number and the fit are both still correct and legible,
just not visually anchored to a drawn circle.

**A rotationally symmetric radius step (e.g. a DIN 471 retaining-ring groove
built directly into the revolve profile) does not render as an outline notch
in a longitudinal base view either, even on the near/visible side — likely
the same class of issue as the occluded-circular-edge case above, but distinct
from it: this feature is axisymmetric, so its true silhouette should change
on every viewing angle regardless of near/far, and the [Front/Back
near-far fix](#3-view-placement) that solves a directional (Y/Z) cut's
visibility does not apply.** The groove's two boundary edges DO render (as
short radial lines at each station), and its diametral dimension
(`CreateDiameterDimension`, end view, [§4](#4-dimensions-the-general-shape))
returns the correct `ComputedSize` — only the connecting top/bottom silhouette
line fails to dip to the smaller radius between them. Checked at 600 dpi,
tight crop on the exact station: no notch at any zoom level, so this is not
a resolution artefact. Mechanism unidentified, not further investigated.
Treat the same way as the occluded-circle case: trust the dimension and a
supplementary leader note over the drawn outline, and flag the PDF for human
review before treating it as visually complete. Runs `20260908T070517Z-cfe4ad0e`
(groove geometry confirmed present via face radius measurement),
`20260908T072255Z-bf730d30` (still missing from the render).

A rule without a verified row above is dimensioned by hand after the job, or the
job is extended first — **never by guessing a builder.**

## 9. Dead ends: do not re-investigate

Recorded so the next agent does not spend the same hours. **An attempt outcome
is not an impossibility** — where the mechanism is unknown, that is said.

- **`SectionViewBuilder` cuts along the shaft, not across it.** Parent view,
  `SectionViewType = SimpleStepped`, a `Cut` segment point at the wanted
  station, additional `Arrow` points above and below it, and a horizontal
  placement request all produce the same longitudinal cut.
  `ViewPlacementBuilder.Method` is read-only, so the placement direction cannot
  be forced either. Consequence: keyway width goes to the end view.
- **No associative dimension to a cylinder's crest — keyway depth `t1`.** All
  five point options on a circular edge (`Tangent`, `OnCurve`, `Control`,
  `Defining`, `Anchor`), in an end view and in a section, and with vertical,
  perpendicular and parallel dimension types, return axis-related distances
  (3.0 / 6.5 / 9.54 / 10.0 / 20.0) — never surface-to-feature. State `t1` as a
  note (the norm fixes it for the key size), or find different reference
  geometry.
- **Keyway length overall (Form A, absolute).** `Tangent` on the R3 end arcs
  returns the centre distance (12.0 for an 18 slot), never the outer extremes.
  Unverified, not impossible. Run `…bc1ca8a0`.
- **`DetailViewBuilder.Scale` and `LabelOnParent` are read-only accessors.**
  Write through `Scale.Numerator` / `Scale.Denominator` and the flattened enum
  `DetailViewBuilderLabelOnParentType`. Boundary points must be `NXOpen.Point`
  objects, not `Point3d`.
- **`view.SetOrigin(…)`** answers `View may not be scaled nor translated`; the
  base-view creation point is ignored entirely ([§3](#3-view-placement)).
- **Silhouette drafting curves carry no `Center`** — `first object
  associativity type is invalid` ([§5](#5-dimension-text-placement-via-the-builder)).
- **Auto-filled title-block cells** (`SCALE`, `WEIGHT`, `CAL_WEIGHT`) are not
  settable from the API ([§2](#2-title-block-cells)).
- **`part.Annotations.TitleBlocks`, `session.DraftingApplicationManager`,
  `CreateDiametralDimension`, `CreateRadialDimension`** — none of these exist.
- **Checking "which end does this view show" via `view.AskVisibleObjects()`
  Tag-matched against the model's own `Face` objects (from
  `body.GetFaces()` / `uf.Modeling.AskFaceData`).** A drafting view's
  `AskVisibleObjects()` returns **view-local drafting-curve/body objects**,
  not the originating model `Face`/`Edge` objects — their Tags never
  intersect, so every view answers "shows nothing" for every face, uniformly,
  which looks like a broken view rather than a broken check. Mechanism
  confirmed indirectly (three different views all producing empty
  intersections including ones known-good from PDF render, run
  `20260907T200032Z-6c4b8192`); the real per-view-curve identity is the one
  [§5](#5-dimension-text-placement-via-the-builder) already documents
  (`view.DraftingBodies.FindObject(...)` → `DraftingCurves.FindObject(...)`,
  itself only reachable by searching, not by a direct Tag match to the
  model). Use the verified-table approach above instead of a live check for
  "which end" questions.

Modelling dead ends live in
[api-modelling.md](api-modelling.md#9-dead-ends-do-not-re-investigate).

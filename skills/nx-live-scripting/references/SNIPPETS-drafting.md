# Snippets — drafting (code only)

Copy-paste-ready calls, no rationale/run-id storytelling. Read a section here
first; go to [api-drafting.md](api-drafting.md) (linked per snippet) only when
something fails or you need the *why*. Read [dimensioning-rules.md](dimensioning-rules.md)
before dimensioning anything — this file is mechanism, not norm-correctness.

## Sheet from the company template

```python
sb = part.DrawingSheets.DrawingSheetBuilder(None)
try:
    sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
    sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
    sb.MetricSheetTemplateLocation = TEMPLATE   # full VM path, no elevation needed
    sheet = sb.Commit()
finally:
    sb.Destroy()
sheet.Open()
part.Drafting.SetTemplateInstantiationIsComplete(True)   # skip -> "Corrupt data
# found when loading an OM file" the next time the part is opened
part.Layers.SetState(256, NXOpen.Layer.State.Visible)     # frame+title block layer
```
`CustomSize` sheets are probes/scratch only — no frame, no title block, no
general-tolerance note. Full context: [api-drafting.md §1](api-drafting.md#1-sheet-from-the-company-template).

## Title block: attributes first, then the two cells that ignore them

```python
part.SetUserAttribute('Bezeichnung/Titel', -1, TITLE, NXOpen.Update.Option.Now)
part.SetTimeUserAttribute('Datum', -1, date_str, NXOpen.Update.Option.Now)
# date_str format: 'DD-Mon-YYYY hh:mm:ss' — ISO-8601 is refused

before = {int(b.Tag) for b in part.DraftingManager.TitleBlocks}  # empty on a
# fresh part; capture it BEFORE creating the sheet whenever the part might
# already carry another sheet — TitleBlocks[0] is the OLDEST block once more
# than one exists, not the one on the sheet just created (silent wrong-sheet
# write, no exception). part.Annotations.TitleBlocks and
# session.DraftingApplicationManager do NOT exist.
sheet = create_sheet(part)  # DrawingSheetBuilder, see "Sheet from the company template" above
new_blocks = [b for b in part.DraftingManager.TitleBlocks if int(b.Tag) not in before]
if new_blocks:
    eb = part.DraftingManager.TitleBlocks.CreateEditTitleBlockBuilder([new_blocks[0]])
    try:
        eb.SetCellValueForLabel('Allgemeintoleranz', 'ISO 2768-m')      # KUP
        eb.SetCellValueForLabel('Material, wird automatisch ausgefüllt', '1.4301')  # KUP,
        # manual-override cell despite the name — SetCellValueForLabel does NOT
        # raise on an unmatched label (e.g. a typo'd 'Material_manuell'), it
        # silently no-ops, so a wrong label looks identical to success
        eb.Commit()
    finally:
        eb.Destroy()
```
On the KUP template only these two cells need the direct-edit path (they
ignore the matching attribute); the other ~11 cells follow attributes alone.
`Cell.Text` is read-only, `EditableText` a silent no-op, `EditCell(a,b,c,d,e)`
deprecated — `SetCellValueForLabel` is the one that sticks. Full context:
[api-drafting.md §2](api-drafting.md#2-title-block-cells).

## Base view + placement + freshness gate

```python
mv = part.ModelingViews.FindObject('Front')   # or 'Top', 'Right', 'Left', ...
vw = sheet.SheetDraftingViews.CreateBaseView(mv, NXOpen.Point3d(x, y, 0.0), SCALE, False)
vw.Update()
vw.MoveView(NXOpen.Point3d(x_abs, y_abs, 0.0))   # absolute SHEET coords — the
# CREATION point above is IGNORED on NX 2506.3001 visible; NX auto-arranges
# base views from the sheet origin regardless of what you pass there
vw.Update()
...
part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
# THEN check freshness (a lone view.Update() right after creation is not enough):
assert vw.IsOutOfDate is False and len(vw.AskVisibleObjects()) > 0
```
Do not assert on `view.Scale`/`view.Origin` — both are viewport-relative
readbacks, not the drafting data. Full context: [api-drafting.md §3](api-drafting.md#3-view-placement).

## Which canned view shows which end

```python
# Fixed fact about NX's absolute-WCS named views, not part geometry — verified
# 2026-09-07, do not re-derive with a live check (see dead end below).
CANNED_VIEW_X_END = {'Right': 'max', 'Left': 'min'}   # Front/Top/Back/Bottom
# look along the OTHER two axes and show the profile, not an axis-end.

def assert_view_shows_x_end(model_view_name, expected_end, why):
    shown = CANNED_VIEW_X_END.get(model_view_name)
    assert shown == expected_end, {'wrong canned view for this feature': why,
        'model_view': model_view_name, 'shows_x_end': shown, 'need': expected_end}

assert_view_shows_x_end('Left', 'min', 'M6+Zentrierung liegt bei x=0')

# Same idea for a Y/Z-directional cut (e.g. a keyway with Direction (0,+-1,0)):
# which view is near vs. far decides whether it renders at all (a feature on
# the far side does not draw, not even dashed). (Zx,Zy,Zz) of
# ModelingView.Matrix is the direction FROM the model TOWARD the viewer.
CANNED_VIEW_TOWARD_VIEWER = {
    'Front': (0, -1, 0), 'Back': (0, 1, 0),
    'Top': (0, 0, 1), 'Bottom': (0, 0, -1),
    'Left': (-1, 0, 0), 'Right': (1, 0, 0),
}
```
**Dead end, do not re-attempt:** checking this live via `view.AskVisibleObjects()`
Tags matched against the model's own `Face` objects — a drafting view's
visible objects are view-local drafting-curve/body objects, the Tags never
intersect the model's faces, every view reports "shows nothing" uniformly.
`view.IsOutOfDate is False` + `AskVisibleObjects() > 0` only proves the view
rendered *something*, never *which* end. Full context: [api-drafting.md §3](api-drafting.md#3-view-placement)
(bottom) and [§9 dead ends](api-drafting.md#9-dead-ends-do-not-re-investigate).

## PDF export

```python
part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
pdf = part.PlotManager.CreatePrintPdfbuilder()
try:
    pdf.Filename = pdf_path
    pdf.SourceBuilder.SetSheets([sheet])
    pdf.Colors = NXOpen.PrintPDFBuilder.Color.BlackOnWhite
    pdf.Size = NXOpen.PrintPDFBuilder.SizeOption.FullScale
    pdf.OutputText = NXOpen.PrintPDFBuilder.OutputTextOption.Text
    pdf.Commit()
finally:
    pdf.Destroy()
assert os.path.getsize(pdf_path) > 1000
```
Call `part.Views.Regenerate()` (not just `UpdateDisplay()`) before this in any
job that touched annotations — otherwise the session shows stale tolerances
even though this export already renders correctly. Full context:
[api-drafting.md §8](api-drafting.md#8-regenerate-the-call-that-refreshes-annotations).

## Sheet cleanup (delete via the trial-dimension path — sheets have no `Delete()`)

```python
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
session.UpdateManager.AddToDeleteList([sheet])
session.UpdateManager.DoUpdate(mark)
```
Guard with a name-prefix/keep-list before sweeping — this cascades views,
dimensions, notes. Can crash natively on some sheets after heavy edit/save
cycles (SEHException, `operations.md` failure-triage table); prefer uniquely
named sheets over purging when the choice is available. Full context:
[api-drafting.md §7](api-drafting.md#7-sheet-hygiene-and-framing-the-visible-sheet).

## Dimensions and surface finish — genuinely not a copy-paste snippet yet

Several pieces here have **open, unswept, or dead-end** associativity paths
per part (diameter fallback works; keyway width was only ever proven in one
view; keyway depth `t1` has no verified association at all; DIN471 groove
width needed a per-run curve search). Read
[api-drafting.md §4-§6](api-drafting.md#4-dimensions-the-general-shape) in
full before attempting these rather than trusting a snippet — the narrative
*is* the current state of the art here, not yet reducible to a stable recipe.

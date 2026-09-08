# Layer 4 — NXOpen from Python: lookup and the .NET gap

The language layer under the two call files ([api-modelling.md](api-modelling.md), [api-drafting.md](api-drafting.md)): how to search the reference, and how a .NET signature has to be bent to run in Python.

## The lookup tool

```sh
.venv/bin/python 04_reference/nx_api_lookup.py CreateCylinderBuilder
.venv/bin/python 04_reference/nx_api_lookup.py Dimension Tolerance
```

It parses `04_reference/NXOpen.xml` — the version-matched reference from the
licensed installation — and prints every `<member>` whose name contains **all**
given terms, with the first ~650 characters of its documentation.

Two things in the output matter beyond the signature:

- **License requirements.** The XML carries them per member, e.g.
  `FeatureCollection.CreateCylinderBuilder` requires
  *"solid_modeling OR cam_base OR insp_programming"*. An unlicensed call fails
  at runtime, not at write time.
- **Deprecations.** e.g. `Implicit.…CreateCylinderBuilder` is marked
  *"Deprecated in NX2406.0.0, use …CreateCylinderBuilder1 instead"*.

Its limit: substring match on member names. It answers "what is the exact
signature of X" and cannot answer "how do I make a counterbore" — for that,
guess the family name (`Hole`, `Chamfer`, `Revolve`) and search several terms.

`NXOpen.xml` is licensed vendor documentation. It is gitignored; do not commit,
paste, or upload it.

## The gap that produces plausible non-running code

**The XML documents .NET signatures; jobs are Python.** An agent that reads a
.NET signature and writes Python produces code that looks right and does not
run — and no retrieval method fixes that, because the retrieved text is correct
and the translation is where it breaks.

The reliable move: **a call copied from a job in `03_jobs/` that has actually run
in this NX version beats any translated .NET signature.** `acceptance.py` and
`live_demo.py` are verified Python against NX 2506, and
[api-modelling.md](api-modelling.md) and [api-drafting.md](api-drafting.md)
collect whole working sequences for
modelling, drawing derivation and export — read it before writing a job in
territory it already covers.

### Differences to expect when translating

Confirmed by the working jobs in this toolkit:

- **Properties, not `Get`/`Set`.** `builder.Type = …`, `builder.Origin = …`,
  `dim.ToleranceType = …`, `view.IsOutOfDate` — all plain attributes.
- **Enums live on the declaring class**, spelled out fully:
  `NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight`,
  `NXOpen.Drawings.DrawingSheetBuilder.SheetOption.CustomSize`,
  `NXOpen.Annotations.ToleranceType.BilateralTwoLines`,
  `NXOpen.Part.Units.Millimeters`. **Two different bindings look identical in
  code and are not:** a true .NET sub-namespace (`NXOpen.Features`,
  `NXOpen.GeometricUtilities`, `NXOpen.Layer`, `NXOpen.UF`) needs its own
  `import NXOpen.<Name>` — `import NXOpen` alone does not bring it in, e.g.
  `part.Layers` (a `LayerManager`) works with plain `import NXOpen`, but
  `NXOpen.Layer.State.Hidden` raises `AttributeError: module 'NXOpen' has no
  attribute 'Layer'` without it (run `20260907T184808Z-c65bfc0d`). A class that
  merely *looks* like a namespace because its nested enums print the same way
  (`NXOpen.Sketch.ViewReorient.FalseValue`, `NXOpen.Sketch.UpdateLevel.Model`)
  is **already available via plain `import NXOpen`** — `NXOpen.Sketch` is a
  class (`T:NXOpen.Sketch` in the XML), not a package, so `import NXOpen.Sketch`
  itself fails, and because it is a **module-level** import this crashes before
  the job's own `try/except` ever runs: NX answers the whole dispatch with
  `NXOpen.NXException: Unable to execute python script`, not a catchable
  Python traceback in `result.json`. Before importing a sub-namespace, check the
  XML: `T:NXOpen.<Name>` alone (no child `M:`/`F:` members whose owner is a
  *different* outer type) is a class needing no import; genuine sibling
  namespaces have many unrelated classes under that prefix. Run
  `20260907T190220Z-36005835` (crash), fixed by dropping the import.
- **Expressions take strings, not numbers.** `builder.Diameter.RightHandSide =
  '20'`. A float there is the wrong type, and a literal loses the parametric
  link that later edits depend on.
- **Builders must be destroyed.** `feature = builder.CommitFeature()` then
  `builder.Destroy()`, ideally in a `finally`. Same for
  `DrawingSheetBuilder.Commit()` and `PrintPDFBuilder.Commit()`.
- **Collections iterate.** `for body in part.Bodies`, `len(list(part.Bodies))`,
  `body.GetEdges()` returns a sequence you can sort.
- **Disposable status objects.** `part.Save(...)` returns a status that wants
  `.Dispose()`.

Confirmed later, each one after producing code that looked correct and did not
work:

- **The readable property and the writable one often differ in name.** The XML
  shows one member; Python exposes the getter under that name and refuses to
  assign to it. Seen so far: `ThreadBuilder.Type` reads, `ThreadType` writes;
  `DraftingSurfaceFinishBuilder.FinishType` reads, `Finish` writes;
  `SectionViewBuilder.SectionLineType` reads, `SectionViewType` writes. When an
  assignment answers *"attribute … is not writable"*, look for a sibling with the
  feature's own name in front of it rather than concluding the property is
  unavailable.
- **Nested enums are flattened, and an unset property returns the enum class.**
  `NXOpen.Features.ThreadBuilder.Type` is not reachable; the values live in
  `NXOpen.Features.ThreadBuilderType`. The pattern is
  `<Namespace>.<Builder><EnumName>`, with a trailing `s` sometimes present
  (`DatumAxisBuilderTypes`, `HolePackageBuilderTypes`) and sometimes not
  (`ThreadBuilderInput`). Resolve it instead of guessing:

```python
def enum_value(builder, prop, value):
    for name in (type(builder).__name__ + prop, type(builder).__name__ + prop + 's'):
        holder = getattr(NXOpen.Features, name, None)
        if holder is not None and hasattr(holder, value):
            return getattr(holder, value)
    current = getattr(builder, prop, None)        # an unset property returns the class
    if isinstance(current, type) and hasattr(current, value):
        return getattr(current, value)
    raise AttributeError('%s.%s has no value %s' % (type(builder).__name__, prop, value))
```

- **Reserved words get a suffix.** `NXOpen.Sketch.ViewReorient.False` is not
  valid Python; the member is `FalseValue`, matching the already-used
  `BasePart.CloseAfterSave.FalseValue`.
- **Selections are not lists.** `ThreadBuilder.CylindricalFace` is a
  `SelectObject`: `.Value = face`, not `.Add(face)`.
  `HolePackageBuilder.HolePosition` is a `Section` and takes
  `AddSmartPoint(point, tolerance)`. Title block cells and section-line segments
  are `ObjectList`s — `.Length` and `.FindItem(i)`, not iteration.
- **Some members are simply gone.** `Face.GetDiameter`, `Face.GetBoundingBox`,
  `FeatureCollection.CreateSymbolicThreadBuilder`,
  `FeatureCollection.DeleteFeature`. Deleting runs through
  `UpdateManager.AddToDeleteList` plus `DoUpdate(mark)`. A removed member is a
  plausible reason for a stale "NX cannot do this" conclusion — check the name
  before believing the capability is absent.
- **A method taking one object may still want a list.**
  `TitleBlocks.CreateEditTitleBlockBuilder` refuses a single `TitleBlock` and
  accepts `[title_block]`.
- **A Python-scoping trap, not an NXOpen one, but it fires inside jobs the
  same way: a module-level `import NXOpen.X` used only for a local helper,
  written as a second `import NXOpen.X` statement INSIDE a function, makes
  `NXOpen` a local name for that function's ENTIRE body** — including lines
  before the import. `session = NXOpen.Session.GetSession()` at the top of
  `build()` then fails with `UnboundLocalError: cannot access local variable
  'NXOpen' where it is not associated with a value`, not an import error, at
  the point of *first use*, which reads nothing like the actual cause.
  Standard Python (any assignment or import anywhere in a function scopes the
  name to that whole function) — always list every `import NXOpen.<X>` a job
  needs once, at module level. Run `20260908T070844Z-fc0db083` (crash),
  fixed in `20260908T070913Z-30115304`.
- **`out` parameters come back as tuples, and not every element is a sequence,
  and a "point" is not always a `Point3d`.** `UFSession.Modeling.AskFaceData`
  returns seven values; the second (point) and third (direction) are plain
  3-element **float lists** `[x, y, z]`, not `Point3d`/`Vector3d` objects —
  `point.Y` raises `AttributeError: 'list' object has no attribute 'Y'`, use
  `point[1]`. The fifth is a float radius and the sixth a single float, not a
  list. Run `20260907T185100Z-9f8b4d52` (the failing `.Y` access),
  `20260907T185157Z-9f8b4d52` (fixed, green).

Expected from the .NET/Python binding in general, worth verifying against a real
run before relying on them:

- `out` parameters come back as a **tuple** instead of being assigned in place.
- Overloads resolve by argument count and type; when a call is rejected, count
  the arguments against the XML signature first.
- Methods taking a .NET array take a Python list.

When a translation is uncertain, write a tiny probe job that only calls the
questionable API and reports `dir(obj)` or the exception into `result.json`. One
7-second dispatch cycle settles it; guessing does not.

Two habits make those probes pay for themselves:

- **Dump the whole surface at once.** A helper returning `dir(obj)` plus, for
  every attribute that is itself a type, that type's members answers "what is
  this builder called and what values does its enum take" in one dispatch
  instead of five.
- **Sweep instead of guessing.** When one of a handful of options must be right —
  a point option, a call order, a spelling — build them all in one job and report
  the value each produced. `03_jobs/probes/thread_probe.py` settles 24 combinations in a
  single run. Delete the objects a sweep creates.

## Worth building later

Both are open items in `docs/nx-live-scripting-handoff.md`, section 9.3:

1. Index the **verified Python** from jobs that ran, so the first hit is real
   code rather than a .NET signature. This is the higher-value half.
2. An embedding index over the XML (the public `nxopen-mcp` uses BGE-M3 +
   sqlite-vec) so intent-shaped questions work without knowing the class name.

Order matters: better retrieval over .NET signatures only delivers the
wrongly-shaped answer faster.

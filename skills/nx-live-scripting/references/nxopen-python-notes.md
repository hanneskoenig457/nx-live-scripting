# NXOpen from Python: lookup and the .NET gap

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
`live_demo.py` are verified Python against NX 2506.

### Differences to expect when translating

Confirmed by the working jobs in this toolkit:

- **Properties, not `Get`/`Set`.** `builder.Type = …`, `builder.Origin = …`,
  `dim.ToleranceType = …`, `view.IsOutOfDate` — all plain attributes.
- **Enums live on the declaring class**, spelled out fully:
  `NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight`,
  `NXOpen.Drawings.DrawingSheetBuilder.SheetOption.CustomSize`,
  `NXOpen.Annotations.ToleranceType.BilateralTwoLines`,
  `NXOpen.Part.Units.Millimeters`. Import the sub-namespace
  (`import NXOpen.Features`) — `import NXOpen` alone does not bring it in.
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

Expected from the .NET/Python binding in general, worth verifying against a real
run before relying on them:

- `out` parameters come back as a **tuple** instead of being assigned in place.
- Overloads resolve by argument count and type; when a call is rejected, count
  the arguments against the XML signature first.
- Methods taking a .NET array take a Python list.

When a translation is uncertain, write a tiny probe job that only calls the
questionable API and reports `dir(obj)` or the exception into `result.json`. One
7-second dispatch cycle settles it; guessing does not.

## Worth building later

Both are open items in `docs/nx-live-scripting-handoff.md`, section 9.3:

1. Index the **verified Python** from jobs that ran, so the first hit is real
   code rather than a .NET signature. This is the higher-value half.
2. An embedding index over the XML (the public `nxopen-mcp` uses BGE-M3 +
   sqlite-vec) so intent-shaped questions work without knowing the class name.

Order matters: better retrieval over .NET signatures only delivers the
wrongly-shaped answer faster.

"""Auf welchem Weg landet eine Skizze wirklich auf der gewünschten Ebene?

`SketchInPlaceBuilder2` mit `PlaneOption.ExistingPlane` und `PlaneReference`
committet zwar, nimmt danach aber keine Kurve der XZ-Ebene an ("Object not in
the plane of the sketch") — die Skizze liegt offenbar weiter auf der Vorgabe-
Ebene. Dieser Job probiert vier Rezepte und prüft jedes mit einer Testkurve, die
in der XZ-Ebene liegt.

Zusätzlich: welche Zylinderflächen hat der Prüfkörper und wie kommt man an ihren
Durchmesser? `Face.GetDiameter` gibt es in NX 2506 nicht, weshalb die Suche nach
der Kernlochfläche für das Gewinde ins Leere lief.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.UF

REORIENT = NXOpen.Sketch.ViewReorient.FalseValue
WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False, 'recipes': []}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def xz_matrix():
    matrix = NXOpen.Matrix3x3()
    matrix.Xx, matrix.Xy, matrix.Xz = 1.0, 0.0, 0.0
    matrix.Yx, matrix.Yy, matrix.Yz = 0.0, 0.0, 1.0
    matrix.Zx, matrix.Zy, matrix.Zz = 0.0, -1.0, 0.0
    return matrix


def probe(out, result):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)

    # --- Zylinderflächen des vorhandenen Teils ---------------------------------
    faces = []
    try:
        part_file = out.parent / 'specimen' / 'pruefkoerper.prt'
        specimen = session.Parts.OpenDisplay(str(part_file))[0]
        body = list(specimen.Bodies)[0]
        for face in body.GetFaces():
            entry = {'type': str(face.SolidFaceType)}
            entry['face_members'] = [n for n in members(face) if 'iamet' in n or 'Radius' in n]
            data = safe(lambda f=face: uf.Modeling.AskFaceData(f.Tag))
            if not isinstance(data, str):
                entry['uf_type'] = data[0]
                entry['uf_point'] = [round(v, 4) for v in data[1]]
                entry['uf_dir'] = [round(v, 4) for v in data[2]]
                entry['uf_radius'] = round(data[4], 4)
            else:
                entry['uf_error'] = data
            faces.append(entry)
    except Exception:
        result['face_error'] = traceback.format_exc()[-900:]
    result['cylindrical_faces'] = [f for f in faces if 'Cylind' in f.get('type', '')]
    result['face_count'] = len(faces)
    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))

    # --- Skizzenrezepte --------------------------------------------------------
    scratch = out / 'sketch_plane.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)
    result['simple_builder_members'] = safe(
        lambda: members(part.Sketches.CreateSimpleSketchInPlaceBuilder()))

    builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        datum_feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    datum_plane = [e for e in datum_feature.GetEntities()
                   if isinstance(e, NXOpen.DatumPlane)][0]
    plane_from_feature = part.Planes.CreatePlane(datum_feature)
    fixed_plane = part.Planes.CreateFixedTypePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0), xz_matrix(), WITHIN)
    result['plane_normals'] = {
        'datum': safe(lambda: str(datum_plane.Normal)),
        'from_feature': safe(lambda: str(plane_from_feature.Normal)),
        'fixed': safe(lambda: str(fixed_plane.Normal)),
    }

    def recipe_a():
        b = part.Sketches.CreateSketchInPlaceBuilder2(None)
        b.PlaneOption = NXOpen.Sketch.PlaneOption.ExistingPlane
        b.PlaneReference = plane_from_feature
        return b

    def recipe_b():
        b = part.Sketches.CreateSketchInPlaceBuilder2(None)
        b.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        b.PlaneOrFace.Value = datum_plane
        return b

    def recipe_c():
        b = part.Sketches.CreateSimpleSketchInPlaceBuilder()
        b.PlaneOrFace.Value = datum_plane
        return b

    def recipe_d():
        b = part.Sketches.CreateSketchInPlaceBuilder2(None)
        b.PlaneOption = NXOpen.Sketch.PlaneOption.ExistingPlane
        b.PlaneReference = fixed_plane
        return b

    for label, factory in (('A_existing_plane_from_feature', recipe_a),
                           ('B_inferred_planeorface', recipe_b),
                           ('C_simple_builder', recipe_c),
                           ('D_existing_fixed_plane', recipe_d)):
        entry = {'recipe': label}
        try:
            b = factory()
            try:
                sketch = b.Commit()
            finally:
                b.Destroy()
            entry['sketch'] = sketch.Name
            sketch.Activate(REORIENT)
            # Testkurve in der XZ-Ebene: y = 0, z variabel.
            line = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, 5.0),
                                          NXOpen.Point3d(10.0, 0.0, 5.0))
            try:
                sketch.AddGeometry(
                    line, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
                entry['add_xz_curve'] = 'ok'
            except Exception as error:
                entry['add_xz_curve'] = 'ERROR: ' + str(error)[:200]
            sketch.Update()
            sketch.Deactivate(REORIENT, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            entry['error'] = traceback.format_exc()[-800:]
        result['recipes'].append(entry)

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


if __name__ == '__main__':
    main()

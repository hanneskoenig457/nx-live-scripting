"""Letzter Versuch für ein echtes Gewindefeature: die Bohrung als Hole-Feature.

Der ThreadBuilder nimmt das symbolische Gewinde auf der bereits gedrehten
Ø5-Fläche nicht an (Durchmesser, Steigung, Länge und Startfläche sind gesetzt,
NX bleibt bei "Thread depth must be greater than zero"). HolePackageBuilder geht
den umgekehrten Weg: NX bohrt selbst und legt das Gewinde gleich mit an. Das
liefert zusätzlich die automatische Bohrungsangabe in der Zeichnung.

Arbeitet auf einem Wegwerfzylinder, nicht am Prüfkörper.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def describe(obj):
    return {'type': type(obj).__name__, 'members': members(obj)}


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    scratch = out / 'hole_probe.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    cylinder = part.Features.CreateCylinderBuilder(None)
    cylinder.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
    cylinder.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    cylinder.Direction = NXOpen.Vector3d(1.0, 0.0, 0.0)
    cylinder.Diameter.RightHandSide = '20'
    cylinder.Height.RightHandSide = '70'
    feature = cylinder.CommitFeature()
    cylinder.Destroy()
    body = feature.GetBodies()[0]

    uf = NXOpen.UF.UFSession.GetUFSession()
    end_face = None
    for face in body.GetFaces():
        data = uf.Modeling.AskFaceData(face.Tag)
        if data[0] == 22 and abs(data[1][0] - 70.0) < 0.01:
            end_face = face
            break
    result['end_face'] = end_face is not None

    builder = part.Features.CreateHolePackageBuilder(None)
    try:
        result['hole_position'] = describe(builder.HolePosition)
        result['projection'] = describe(builder.ProjectionDirection)
        result['boolean'] = describe(builder.BooleanOperation)
        builder.Type = getattr(NXOpen.Features, 'HolePackageBuilderTypes').ThreadedHole
        builder.ThreadStandard = 'Metric Coarse'
        builder.ThreadSize = 'M6 x 1.0'
        builder.RadialEngageOption = '0.75'
        # HolePosition ist eine Section; die Bohrmitte kommt als Punkt hinein.
        point = part.Points.CreatePoint(NXOpen.Point3d(70.0, 0.0, 0.0))
        result['placement'] = str(safe(
            lambda: builder.HolePosition.AddSmartPoint(point, 0.01)))
        result['projection_set'] = str(safe(lambda: setattr(
            builder.ProjectionDirection, 'DirectionType',
            NXOpen.GeometricUtilities.ProjectionOptions.DirectionType.FaceNormal)))
        builder.ThreadLengthOption = getattr(
            NXOpen.Features, 'HolePackageBuilderThreadLengthOptions').Custom
        builder.ThreadDepth.RightHandSide = '12'
        builder.ThreadedHoleDepth.RightHandSide = '14'
        builder.BooleanOperation.Type = \
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        builder.BooleanOperation.SetTargetBodies([body])
        result['tolerance_default'] = str(safe(lambda: builder.Tolerance))
        for candidate in (0.01, 0.0254, None):
            attempt = {'tolerance': candidate}
            try:
                if candidate is not None:
                    builder.Tolerance = candidate
                hole = builder.CommitFeature()
                attempt['ok'] = True
                result['hole'] = hole.JournalIdentifier
                result['ok_hole'] = True
                result.setdefault('tolerance_attempts', []).append(attempt)
                break
            except Exception as error:
                attempt['error'] = str(error)[:180]
                result.setdefault('tolerance_attempts', []).append(attempt)
    except Exception:
        result['hole_error'] = traceback.format_exc()[-1500:]
    finally:
        safe(lambda: builder.Destroy())

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


if __name__ == '__main__':
    main()

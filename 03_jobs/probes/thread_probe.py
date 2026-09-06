"""Welche Aufrufreihenfolge nimmt der ThreadBuilder in NX 2506 an?

Das symbolische M6-Gewinde auf der Kernlochfläche scheitert je nach Reihenfolge
mit "Unable to modify tool due to missing target face." oder "Thread depth must
be greater than zero." Dieser Job probiert die plausiblen Kombinationen auf dem
vorhandenen Prüfkörper durch und meldet die erste, die NX annimmt. Das Feature
wird nach jedem Versuch wieder gelöscht, das Teil nicht gespeichert.
"""
import itertools
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.UF

TAP_DIAMETER = 5.0
TOTAL_LENGTH = 70.0
THREAD_DEPTH = 12.0
THREAD_STANDARD = 'Metric Coarse'
THREAD_SIZE = 'M6 x 1.0'
UF_FACE_PLANE = 22
UF_FACE_CONE = 17


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def enum_value(builder, prop, value):
    for name in (type(builder).__name__ + prop, type(builder).__name__ + prop + 's'):
        holder = getattr(NXOpen.Features, name, None)
        if holder is not None and hasattr(holder, value):
            return getattr(holder, value)
    current = getattr(builder, prop, None)
    if isinstance(current, type) and hasattr(current, value):
        return getattr(current, value)
    raise AttributeError('%s.%s hat keinen Wert %s' % (type(builder).__name__, prop, value))


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False, 'attempts': []}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    part = session.Parts.OpenDisplay(str(out.parent / 'specimen' / 'pruefkoerper.prt'))[0]
    body = list(part.Bodies)[0]

    bore_face, start_face = None, None
    for face in body.GetFaces():
        data = uf.Modeling.AskFaceData(face.Tag)
        if bore_face is None and abs(data[4] - TAP_DIAMETER / 2.0) < 0.01:
            bore_face = face
        if start_face is None and data[0] == UF_FACE_PLANE \
                and abs(data[1][0] - TOTAL_LENGTH) < 0.01:
            start_face = face
    result['found'] = {'bore': bore_face is not None, 'start': start_face is not None}

    # Die Ø5-Bohrung beginnt erst hinter der 120°-Senkung; die Stirnfläche
    # berührt sie also nicht, weshalb NX dort Gewindetiefe null rechnet.
    # Kandidaten sind deshalb die Kegelfläche der Senkung und der Kreisrand
    # Ø5 am Übergang.
    cone_face = None
    for face in body.GetFaces():
        data = uf.Modeling.AskFaceData(face.Tag)
        if data[0] == UF_FACE_CONE and data[1][0] > TOTAL_LENGTH - 5.0:
            cone_face = face
            break
    start_edge = None
    for edge in body.GetEdges():
        length = edge.GetLength()
        if abs(length - 3.141592653589793 * TAP_DIAMETER) < 0.2:
            start_edge = edge
            break
    result['found']['cone'] = cone_face is not None
    result['found']['start_edge'] = start_edge is not None

    starts = {'none': None, 'face': start_face, 'cone': cone_face, 'edge': start_edge}
    for order, match, start_key, limit, manual in itertools.product(
            ('face_first',), (False,), ('cone', 'face'), ('Value',), ('exp', 'float')):
        entry = {'order': order, 'match_cylinder': match, 'start': start_key,
                 'limit': limit, 'manual': manual}
        builder = part.Features.CreateThreadBuilder(None)
        try:
            def set_size():
                builder.ThreadStandard = THREAD_STANDARD
                if not match:
                    builder.ThreadSize = THREAD_SIZE
                    builder.RadialEngage = '0.75'

            def set_face():
                builder.CylindricalFace.Value = bore_face
                if starts[start_key] is not None:
                    builder.StartObject.Value = starts[start_key]

            builder.ThreadType = enum_value(builder, 'Type', 'Symbolic')
            builder.MatchThreadSizeToCylinder = match
            if order == 'face_first':
                set_face()
                set_size()
            else:
                set_size()
                set_face()
            builder.ThreadLimit = enum_value(builder, 'LimitOption', limit)
            if limit == 'Value':
                builder.ThreadLength.RightHandSide = str(THREAD_DEPTH)
            entry['size_seen'] = str(safe(lambda: builder.ThreadSize))
            for name in ('ThreadLength', 'MajorDiameterExp', 'MinorDiameterExp',
                         'PitchExp', 'AngleExp', 'TapDrillDiameterExp'):
                entry[name] = str(safe(
                    lambda n=name: getattr(builder, n).RightHandSide))
            if manual == 'exp':
                # Die Normtabelle füllt Steigung und Flankenwinkel, aber nicht
                # die Durchmesser; ohne sie ist die Gewindetiefe null.
                builder.MajorDiameterExp.RightHandSide = '6'
                builder.MinorDiameterExp.RightHandSide = '4.9175'
                builder.TapDrillDiameterExp.RightHandSide = '5'
            elif manual == 'float':
                builder.MajorDiameter = 6.0
                builder.MinorDiameter = 4.9175
                builder.TapDrillDiameter = 5.0
            if manual:
                builder.ThreadLength.RightHandSide = str(THREAD_DEPTH)
                entry['after'] = {
                    'major': str(safe(lambda: builder.MajorDiameterExp.RightHandSide)),
                    'minor': str(safe(lambda: builder.MinorDiameterExp.RightHandSide)),
                    'tap': str(safe(lambda: builder.TapDrillDiameterExp.RightHandSide)),
                    'length': str(safe(lambda: builder.ThreadLength.RightHandSide))}
            feature = builder.CommitFeature()
            entry['ok'] = True
            entry['feature'] = feature.JournalIdentifier
        except Exception as error:
            entry['ok'] = False
            entry['error'] = str(error)[:160]
            feature = None
        finally:
            safe(lambda: builder.Destroy())
        result['attempts'].append(entry)
        if entry.get('ok'):
            mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'weg')
            session.UpdateManager.AddToDeleteList([feature])
            safe(lambda: session.UpdateManager.DoUpdate(mark))

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))


if __name__ == '__main__':
    main()

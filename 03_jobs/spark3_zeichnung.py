"""SPARK3 Zeichnung v1 (Phase 1): Minimal-PDF mit den 4 tolerierten Merkmalen.

Teil: verifiziertes Modell (Run 20260906T153508Z-a28c46ac), per FullPath-Match
wiederverwendet. VOR jedem Commit: DisplayPart-Check (kein Raten, keine
Verschmutzung bei falschem Kontext).
UEBERHOLT: CustomSize-Blaetter sind Probe/Scratch. Zeichnungen entstehen auf
KUP_Zeichenvorlage.prt -- siehe spark3_zeichnungT.py und den Job-Contract.
Dieser Job bleibt als Beleg der Runs stehen, die ihn zitieren.

Blatt CustomSize 297x210 ohne Template (Firmen-Template liegt ausserhalb des
Skills) -- daher keine Template-Completion-, keine Layer-256-Schritte.
Ansichten je SOFORT upgedatet (Batch-Trap), Guards vor PDF-Export.
Masse (alle mit ComputedSize gegen Nominal asserted; falsche Assoziation =
failed Run, keine falsche Zeichnung):
  Front: Gesamtlaenge 70 (Kreis-Kanten ArcCenter, acceptance-Muster),
         Ringnut-Breite 1.1 (Nutwand-Kreise r=10 bei x=57.45/58.55, ArcCenter),
         Nutgrund Oe19 (Zylinderflaeche 2x OnCurve, Fallback Stirn-Kreis),
  Top:   Nutbreite 6 P9 (Flanken-Faces OnCurve, Fallback Flankenkanten-Sweep),
  Right: Oe20 h6 + Oe25 stirnseitig (Kreis-Kante OnCurve, Fallback-Pfad --
         gleichzeitig Orientierungsbeweis der Ansicht).
Fit: LimitsAndFits h6 / P9 / h11. Ra 0,8 Modifier-Symbol mit Leader auf
Sitz-Erzeugende. Notes: Titel/ISO-2768-m/ISO-8015, M6-Callout mit Leader,
t1-Note (associativ unverifiziert, Mapping). Trial-Masse werden einzeln per
unsichtbarer Marke + DeleteList + DoUpdate entfernt.
"""
import json
import math
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Annotations
import NXOpen.Drawings
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer
import NXOpen.UF

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260906T153508Z-a28c46ac/20260906T153508Z-a28c46ac.prt')
PREFIX = 'SPARK3_'
SHEET_W, SHEET_H, SCALE = 297.0, 210.0, 2.0


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'dims': [], 'trials': [],
              'views': {}}
    try:
        run(out, result)
        result['ok'] = (all(d.get('ok', False) for d in result['dims'])
                        and result.get('pdf_ok', False)
                        and all(v.get('fresh') for v in
                                result['views'].values()))
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result, watchable=True):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()

    # --- Kontext prüfen, VOR jedem Commit ---
    result['stage'] = 'context'
    want = None
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        if isinstance(full, str) and full.replace('\\', '/').lower() == \
                BASE_PRT.lower():
            want = p
            break
    assert want is not None, {'verified part not open': BASE_PRT}
    shown = safe(lambda: str(session.Parts.Display.FullPath))
    if not (isinstance(shown, str) and shown.replace('\\', '/').lower()
            == BASE_PRT.lower()):
        setdisplay = safe(lambda: session.Parts.SetDisplay(want))
        result['set_display'] = setdisplay if isinstance(
            setdisplay, str) else 'ok'
        shown = safe(lambda: str(session.Parts.Display.FullPath))
    result['display'] = shown
    assert isinstance(shown, str) and shown.replace('\\', '/').lower() == \
        BASE_PRT.lower(), {'display is not the verified part': shown}
    part = want
    result['part'] = safe(lambda: part.JournalIdentifier)
    body = list(part.Bodies)[0]

    def repaint():
        try:
            part.ModelingViews.WorkView.UpdateDisplay()
        except Exception as error:
            result['repaint'] = 'WARN: ' + str(error)[:200]

    # --- Skizzen/Datums aus den Ansichten (Layer-Import verifiziert) ---
    result['stage'] = 'layers'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Layer Blatt')
    moved = {'sketches': [], 'datums': 0, 'sketch_curves': 0}
    try:
        for sk in part.Sketches:
            geos = []
            try:
                geos = list(sk.GetAllGeometry())
            except Exception:
                pass
            try:
                part.Layers.MoveDisplayableObjects(21, [sk] + list(geos))
                moved['sketches'].append(safe(lambda s=sk: s.Name))
                moved['sketch_curves'] += len(geos)
            except Exception as error:
                moved.setdefault('errors', []).append(str(error)[:150])
    except Exception as error:
        moved['sketch_scan'] = 'ERR: ' + str(error)[:150]
    try:
        for d in part.Datums:
            try:
                part.Layers.MoveDisplayableObjects(61, [d])
                moved['datums'] += 1
            except Exception:
                continue
    except Exception as error:
        moved['datum_scan'] = 'ERR: ' + str(error)[:150]
    result['moved'] = moved
    result['layer_before'] = {
        'l21': safe(lambda: str(part.Layers.GetState(21))),
        'l61': safe(lambda: str(part.Layers.GetState(61)))}
    part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
    result['layer21'] = safe(lambda: str(part.Layers.GetState(21)))
    result['layer61'] = safe(lambda: str(part.Layers.GetState(61)))

    # --- Alt-Bogen weg (selbstreinigend: Prefix Guard, Undo-Klammer) ---
    result['stage'] = 'purge old sheets'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Blatt neu')
    purged = []
    for sh in list(part.DrawingSheets):
        nm = safe(lambda s=sh: str(s.Name))
        if isinstance(nm, str) and nm.startswith(PREFIX):
            try:
                mark = session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
                session.UpdateManager.AddToDeleteList([sh])
                session.UpdateManager.DoUpdate(mark)
                purged.append(nm)
            except Exception as error:
                assert False, 'Purge fehlgeschlagen: ' + nm + ' ' + \
                    str(error)[:200]
    result['purged'] = purged

    # --- Blatt (Reserven: Inhalt 60..286 statt 40..290) ---
    result['stage'] = 'sheet'
    sheet_name = 'SPARK3_' + out.name[-8:]
    sb = part.DrawingSheets.DrawingSheetBuilder(None)
    try:
        sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.CustomSize
        sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        sb.Length = SHEET_W
        sb.Height = SHEET_H
        sb.Name = sheet_name
        sb.ScaleNumerator = 1.0
        sb.ScaleDenominator = 1.0
        sb.ProjectionAngle = NXOpen.Drawings.DrawingSheetBuilder \
            .SheetProjectionAngle.First
        sheet = sb.Commit()
    finally:
        sb.Destroy()
    sheet.Open()
    result['sheet'] = sheet_name
    if watchable:
        time.sleep(1.0)

    # --- Ansichten (Modellursprung -> Blattpunkt), sofort updaten ---
    result['stage'] = 'views'
    views = {}
    for label, model_view, at in (
            ('front', 'Front', NXOpen.Point3d(100.0, 110.0, 0.0)),
            ('top', 'Top', NXOpen.Point3d(100.0, 40.0, 0.0)),
            ('right', 'Right', NXOpen.Point3d(230.0, 110.0, 0.0))):
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 Ansicht ' + label)
        mv = part.ModelingViews.FindObject(model_view)
        vw = sheet.SheetDraftingViews.CreateBaseView(mv, at, SCALE, False)
        vw.Update()  # Batch-Trap: sofort, nicht erst nach den Massen
        views[label] = vw
        result['views'][label] = {
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
        result.setdefault('scale_at_creation', {})[label] = safe(
            lambda v=vw: str(v.Scale))
        if watchable:
            time.sleep(1.0)
    # Kollektiv-Update: erst danach ist Geometrie in allen Ansichten sicher.
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    for label, vw in views.items():
        result['views'][label] = {
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
    assert all(v['fresh'] for v in result['views'].values()), \
        {'views stale after UpdateViews': result['views']}

    # --- Geometrie-Finder (semi-aware: intakte Kreise = Halbkreispaare,
    # L/pi liefert dort den Radius; Rezept S4) ---
    edges = list(body.GetEdges())
    result['n_edges'] = len(edges)

    def edge_len(e):
        try:
            return e.GetLength()
        except Exception:
            return None

    def edge_station_x(e):
        try:
            vs = e.GetVertices()
            if not vs:
                return None
            return sum(v.X for v in vs) / len(vs)
        except Exception:
            return None

    def circles(dia, tol=0.08):
        res = []
        for e in edges:
            L = edge_len(e)
            if L is None:
                continue
            if abs(L / math.pi - dia) <= tol:
                res.append(e)
            elif abs(2 * L / math.pi - dia) <= tol:
                res.append(e)
        return res

    def at_x(e, x, tol=0.6):
        sx = edge_station_x(e)
        return sx is not None and abs(sx - x) <= tol

    def diag():
        hist = {}
        for e in edges:
            L = edge_len(e)
            if L is None:
                continue
            hist[round(L / math.pi, 2)] = hist.get(
                round(L / math.pi, 2), 0) + 1
        return {'n_edges': len(edges),
                'dia_hist_L_over_pi': sorted(hist.items(),
                                             key=lambda kv: -kv[1])}

    def arcs_at(x, tol=0.25):
        # Kreisbogen in einer X-Ebene (alle Vertices ~gleiches X): Station
        # bekannt, Ø egal -- ArcCenter misst die axiale Lage.
        res = []
        for e in edges:
            try:
                vs = e.GetVertices()
            except Exception:
                continue
            if len(vs) < 2:
                continue
            xs = [v.X for v in vs]
            if max(xs) - min(xs) > tol:
                continue
            if abs(sum(xs) / len(xs) - x) <= tol:
                res.append(e)
        return res

    class StageFail(Exception):
        pass

    def stage(label, fn):
        result['stage'] = label
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 ' + label[:30])
        try:
            fn()
        except Exception as error:
            result['dims'].append({'label': label, 'ok': False,
                                   'error': str(error)[:300]})

    def face_edges(face):
        try:
            return list(face.GetEdges())
        except Exception as error:
            result.setdefault('face_edges_err', []).append(str(error)[:150])
            return []

    def match_dia(es, dia, tol=0.08):
        res = []
        for e in es:
            L = edge_len(e)
            if L is None:
                continue
            if abs(L / math.pi - dia) <= tol or \
                    abs(2 * L / math.pi - dia) <= tol:
                res.append(e)
        return res

    def endface(nx, x0, tol=0.1):
        return [f for f, p in planar_faces(0, nx) if abs(p[0] - x0) <= tol]

    def cyl_faces(radius, axis, tol=0.01):
        found = []
        for face in body.GetFaces():
            try:
                kind, point, direction, box, rad, rd, no = \
                    uf.Modeling.AskFaceData(face.Tag)
            except Exception:
                continue
            if kind == 16 and abs(float(rad) - radius) <= tol and \
                    abs(abs(direction[axis]) - 1.0) < 1e-6:
                found.append(face)
        return found

    def planar_faces(naxis, nsign):
        found = []
        for face in body.GetFaces():
            try:
                kind, point, direction, box, rad, rd, no = \
                    uf.Modeling.AskFaceData(face.Tag)
            except Exception:
                continue
            if kind == 22 and abs(abs(direction[naxis]) - 1.0) < 1e-6 and \
                    (direction[naxis] * nsign) > 0:
                found.append((face, [round(v, 3) for v in point]))
        return found

    # --- Mass-Helfer ---
    def assoc(obj, view, option):
        a = part.Annotations.NewAssociativity()
        a.FirstObject = obj
        a.ObjectView = view
        a.PointOption = option
        return a

    ArcCenter = NXOpen.Annotations.AssociativityPointOption.ArcCenter
    OnCurve = NXOpen.Annotations.AssociativityPointOption.OnCurve

    def place(create, view, assocs, point, center=True):
        data = part.Annotations.NewDimensionData()
        for i, a in enumerate(assocs, 1):
            data.SetAssociativity(i, [a])
        dim = create(data, point)
        try:
            dim.IsOriginCentered = center
        except Exception:
            pass
        return dim

    def delete_trial(dim):
        mark = session.SetUndoMark(
            NXOpen.Session.MarkVisibility.Invisible, 'Probemass')
        session.UpdateManager.AddToDeleteList([dim])
        session.UpdateManager.DoUpdate(mark)

    def record(label, nominal, dim, extra=None):
        try:
            got = float(dim.ComputedSize)
        except Exception:
            got = None
        entry = {'label': label, 'nominal': nominal, 'computed': got,
                 'ok': got is not None and abs(got - nominal) < 1e-6}
        if extra:
            entry.update(extra)
        result['dims'].append(entry)
        return entry['ok']

    def apply_fit(dim, dev, grade):
        dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
        dim.LimitFitDeviation = dev
        dim.LimitFitGrade = grade

    H = part.Dimensions.CreateHorizontalDimension
    V = part.Dimensions.CreateVerticalDimension
    DIA = part.Dimensions.CreateDiameterDimension
    CYL = part.Dimensions.CreateCylindricalDimension
    POINT_OPTS = ['OnCurve', 'ArcCenter', 'Tangent', 'Control', 'Defining',
                  'Anchor']

    # --- L70 Front: Bogen an Stirn-Ebenen (Ø egal), Fallback Faces-Sweep ---
    def do_L70():
        a0 = arcs_at(0.0)
        a70 = arcs_at(70.0)
        result['L70_arcs'] = {'x0': len(a0), 'x70': len(a70)}
        if a0 and a70:
            dim = place(H, views['front'],
                        [assoc(a0[0], views['front'], ArcCenter),
                         assoc(a70[0], views['front'], ArcCenter)],
                        NXOpen.Point3d(130.0, 68.0, 0.0))
            if abs(float(dim.ComputedSize) - 70.0) < 1e-6:
                record('Laenge 70', 70.0, dim, {'path': 'rim-arcs'})
                return
            result['trials'].append(
                {'dim': 'L70-arcs', 'computed': float(dim.ComputedSize)})
            delete_trial(dim)
        f0 = endface(-1, 0.0)
        f70 = endface(+1, 70.0)
        if not (f0 and f70):
            raise StageFail('Stirnflächen fehlen: ' + str(diag()))
        for opt_name in POINT_OPTS:
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(H, views['front'],
                            [assoc(f0[0], views['front'], opt),
                             assoc(f70[0], views['front'], opt)],
                            NXOpen.Point3d(110.0, 68.0, 0.0))
                got = float(dim.ComputedSize)
                if abs(got - 70.0) < 1e-6:
                    record('Laenge 70', 70.0, dim,
                           {'path': 'end-faces/' + opt_name})
                    return
                result['trials'].append(
                    {'dim': 'L70-faces/' + opt_name, 'computed': got})
                delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'L70-faces/' + opt_name,
                                         'error': str(error)[:200]})
        raise StageFail('L70-Pfade erschoepft')
    stage('Laenge 70', do_L70)
    if watchable:
        time.sleep(1.0)

    # --- Oe20 h6 + Oe25 stirnseitig (Right; assert = Orientierungsbeweis;
    # stationslos: jeder echte Kreis des Ø misst richtig) ---
    def do_dia():
        e20 = match_dia(edges, 20.0)
        if not e20:
            raise StageFail('Oe20-Kreis fehlt: ' + str(diag()))
        dim = place(DIA, views['right'],
                    [assoc(e20[0], views['right'], OnCurve)],
                    NXOpen.Point3d(230.0, 162.0, 0.0), center=False)
        apply_fit(dim, 'h', 6)
        record('Sitz Oe20 h6', 20.0, dim, {'fit': 'h6'})
        e25 = match_dia(edges, 25.0)
        if not e25:
            raise StageFail('Oe25-Kreis fehlt: ' + str(diag()))
        dim = place(DIA, views['right'],
                    [assoc(e25[0], views['right'], OnCurve)],
                    NXOpen.Point3d(230.0, 58.0, 0.0), center=False)
        record('Welle Oe25', 25.0, dim)
    stage('Durchmesser', do_dia)
    if watchable:
        time.sleep(1.0)

    # --- Ringnut-Breite 1.1 Front: Bogen an Wand-Ebenen, Fallback Faces ---
    def do_groovew():
        g1 = arcs_at(57.45)
        g2 = arcs_at(58.55)
        result['groove_arcs'] = {'x57': len(g1), 'x58': len(g2)}
        if g1 and g2:
            try:
                dim = place(H, views['front'],
                            [assoc(g1[0], views['front'], ArcCenter),
                             assoc(g2[0], views['front'], ArcCenter)],
                            NXOpen.Point3d(176.0, 152.0, 0.0))
                if abs(float(dim.ComputedSize) - 1.1) < 1e-6:
                    dim.ToleranceType = \
                        NXOpen.Annotations.ToleranceType.BilateralTwoLines
                    dim.UpperMetricToleranceValue = 0.14
                    dim.LowerMetricToleranceValue = 0.0
                    dim.ToleranceDecimalPlaces = 2
                    record('Ringnut-Breite 1.1+0.14', 1.1, dim,
                           {'path': 'rim-arcs'})
                    return
                result['trials'].append(
                    {'dim': 'Nut-1.1-arcs', 'computed': float(dim.ComputedSize)})
                delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'Nut-1.1-arcs',
                                         'error': str(error)[:200]})
        w1 = [f for f, p in planar_faces(0, +1) if abs(p[0] - 57.45) < 0.05]
        w2 = [f for f, p in planar_faces(0, -1) if abs(p[0] - 58.55) < 0.05]
        result['groove_walls'] = {'w57': len(w1), 'w58': len(w2)}
        if not (w1 and w2):
            raise StageFail('Nutwand-Faces fehlen')
        for opt_name in POINT_OPTS:
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(H, views['front'],
                            [assoc(w1[0], views['front'], opt),
                             assoc(w2[0], views['front'], opt)],
                            NXOpen.Point3d(176.0, 152.0, 0.0))
                got = float(dim.ComputedSize)
                if abs(got - 1.1) < 1e-6:
                    dim.ToleranceType = \
                        NXOpen.Annotations.ToleranceType.BilateralTwoLines
                    dim.UpperMetricToleranceValue = 0.14
                    dim.LowerMetricToleranceValue = 0.0
                    dim.ToleranceDecimalPlaces = 2
                    record('Ringnut-Breite 1.1+0.14', 1.1, dim,
                           {'path': 'wall-faces/' + opt_name})
                    return
                result['trials'].append(
                    {'dim': 'Nut-1.1/' + opt_name, 'computed': got})
                delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'Nut-1.1/' + opt_name,
                                         'error': str(error)[:200]})
        raise StageFail('Nut-1.1-Pfade erschoepft')
    stage('Ringnut-Breite', do_groovew)
    if watchable:
        time.sleep(1.0)

    # --- Nutgrund Oe19: (a) Front Zylinderflaeche 2x, (b) Stirnkreis ---
    result['stage'] = 'dim groove base'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Nutgrund')
    ok19 = False
    gb = cyl_faces(9.5, 0)
    for opt_name in ('OnCurve', 'Tangent'):
        if ok19 or not gb:
            break
        try:
            opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                          opt_name)
            dim = place(CYL, views['front'],
                        [assoc(gb[0], views['front'], opt),
                         assoc(gb[0], views['front'], opt)],
                        NXOpen.Point3d(196.0, 120.0, 0.0), center=False)
            if abs(float(dim.ComputedSize) - 19.0) < 1e-6:
                apply_fit(dim, 'h', 11)
                ok19 = record('Nutgrund Oe19 h11', 19.0, dim,
                              {'fit': 'h11', 'path': 'face-twice/' + opt_name})
            else:
                result['trials'].append(
                    {'dim': 'Nutgrund-a/' + opt_name,
                     'computed': float(dim.ComputedSize)})
                delete_trial(dim)
        except Exception as error:
            result['trials'].append({'dim': 'Nutgrund-a/' + opt_name,
                                     'error': str(error)[:200]})
    if not ok19:
        gb_e = [e for e in face_edges(gb[0])
                if (lambda x: x is not None and 57.0 <= x <= 59.0)(
                    edge_station_x(e))] if gb else []
        assert gb_e, {'Nutgrund-Kreis fehlt (Pfad b)': diag()}
        dim = place(DIA, views['right'],
                    [assoc(gb_e[0], views['right'], OnCurve)],
                    NXOpen.Point3d(262.0, 110.0, 0.0))
        apply_fit(dim, 'h', 11)
        record('Nutgrund Oe19 h11', 19.0, dim, {'fit': 'h11', 'path': 'end-on'})
    if watchable:
        time.sleep(1.0)

    # --- Nutbreite 6 P9 Top: Faces, Fallback Kanten-Sweep ---
    result['stage'] = 'dim keyway width'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 Nut 6')
    ok6 = False
    flm = [f for f, p in planar_faces(2, +1)
           if abs(p[2] + 3.0) < 0.02]
    flp = [f for f, p in planar_faces(2, -1)
           if abs(p[2] - 3.0) < 0.02]
    if flm and flp:
        for opt_name in POINT_OPTS:
            if ok6:
                break
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(V, views['front'],
                            [assoc(flm[0], views['front'], opt),
                             assoc(flp[0], views['front'], opt)],
                            NXOpen.Point3d(172.0, 150.0, 0.0))
                if abs(float(dim.ComputedSize) - 6.0) < 1e-6:
                    apply_fit(dim, 'P', 9)
                    ok6 = record('Nutbreite 6 P9', 6.0, dim,
                                 {'fit': 'P9',
                                  'path': 'flank-faces/' + opt_name})
                else:
                    result['trials'].append(
                        {'dim': 'Nut-6-faces/' + opt_name,
                         'computed': float(dim.ComputedSize)})
                    delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'Nut-6-faces/' + opt_name,
                                         'error': str(error)[:200]})
    if not ok6:
        floor_edges = []
        for e in edges:
            try:
                vs = e.GetVertices()
                if len(vs) != 2:
                    continue
                L = e.GetLength()
            except Exception:
                continue
            if abs(L - 14.0) > 0.05:
                continue
            ys = sorted(round(v.Y, 3) for v in vs)
            zs = sorted(round(v.Z, 3) for v in vs)
            if ys[0] == ys[1] == 6.5 and zs[0] == zs[1] and \
                    abs(abs(zs[0]) - 3.0) < 0.02:
                floor_edges.append((zs[0], e))
        result['trials'].append(
            {'dim': 'Nut-6-floor-edges', 'found': len(floor_edges)})
        assert len(floor_edges) >= 2, 'Nut-Bodenkanten fehlen'
        e_a = [e for z, e in floor_edges if z < 0][0]
        e_b = [e for z, e in floor_edges if z > 0][0]
        for opt_name in ('OnCurve', 'Tangent'):
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(V, views['front'],
                            [assoc(e_a, views['front'], opt),
                             assoc(e_b, views['front'], opt)],
                            NXOpen.Point3d(138.0, 150.0, 0.0), center=False)
                if abs(float(dim.ComputedSize) - 6.0) < 1e-6:
                    apply_fit(dim, 'P', 9)
                    ok6 = record('Nutbreite 6 P9', 6.0, dim,
                                 {'fit': 'P9', 'path': 'floor-edges/' + opt_name})
                    break
                result['trials'].append(
                    {'dim': 'Nut-6-edges/' + opt_name,
                     'computed': float(dim.ComputedSize)})
                delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'Nut-6-edges/' + opt_name,
                                         'error': str(error)[:200]})
    assert ok6, {'Nutbreite-Assoziation fehlgeschlagen': result['trials']}
    if watchable:
        time.sleep(1.0)

    # --- Ra 0,8 auf Sitz-Erzeugende (Front), Leader auf Kante ---
    result['stage'] = 'surface finish'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 Ra')
    seam, best = None, 0.0
    table = []
    for e in edges:
        try:
            vs = e.GetVertices()
            if len(vs) != 2:
                continue
            (x1, y1, z1), (x2, y2, z2) = \
                ((v.X, v.Y, v.Z) for v in vs)
        except Exception:
            continue
        if abs(y1 - y2) > 1e-6 or abs(z1 - z2) > 1e-6:
            continue  # nicht X-parallel
        ym, zm = (y1 + y2) / 2, (z1 + z2) / 2
        if abs(math.hypot(ym, zm) - 10.0) > 0.03:
            continue  # nicht Sitz-Ø20
        if min(x1, x2) < 44.9 or max(x1, x2) > 70.1:
            continue
        L = abs(x2 - x1)
        if L < 1e-6:
            continue  # degenerierte Punkt-Kante
        table.append({'x': [round(min(x1, x2), 2), round(max(x1, x2), 2)],
                      'y': round(ym, 2), 'z': round(zm, 2), 'L': round(L, 2)})
        if ym < 9.0 or zm < 0:
            continue  # Flanken-Oberkante oben (z=+3): Symbol darüber
        if L > best:
            best, seam = L, e
    result['seam_table'] = table
    assert seam is not None, {'Sitz-Kante fehlt': table}
    result['seam'] = {'len': round(best, 3)}
    fb = part.Annotations.DraftingSurfaceFinishSymbols \
        .CreateDraftingSurfaceFinishBuilder(None)
    try:
        fb.Finish = NXOpen.Annotations.DraftingSurfaceFinishBuilderFinishType \
            .ModifierMaterialRemovalRequired
        fb.SingleRoughnessValue = True
        fb.A1 = 'Ra 0,8'
        fb.Origin.OriginPoint = NXOpen.Point3d(167.0, 132.0, 0.0)
        lead = part.Annotations.CreateLeaderData()
        lead.Arrowhead = NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
        lead.StubSide = NXOpen.Annotations.LeaderSide.Inferred
        vs = seam.GetVertices()
        mid = NXOpen.Point3d(sum(v.X for v in vs) / len(vs),
                             sum(v.Y for v in vs) / len(vs),
                             sum(v.Z for v in vs) / len(vs))
        lead.Leader.SetValue(seam, views['front'], mid)
        fb.Leader.Leaders.Append(lead)
        sym = fb.Commit()
        result['surface_finish'] = safe(lambda: sym.JournalIdentifier)
    finally:
        try:
            fb.Destroy()
        except Exception:
            pass
    if watchable:
        time.sleep(1.0)

    # --- Notes: Titel/ISO, M6 mit Leader, t1 ---
    result['stage'] = 'notes'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 Notes')

    def note(lines, point, edge=None, view=None):
        nb = part.Annotations.CreateDraftingNoteBuilder(None)
        try:
            nb.Text.TextBlock.SetText(list(lines))
            nb.Origin.OriginPoint = point
            if edge is not None:
                lead = part.Annotations.CreateLeaderData()
                lead.Arrowhead = \
                    NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
                lead.StubSide = NXOpen.Annotations.LeaderSide.Inferred
                lead.Leader.SetValue(edge, view,
                                     NXOpen.Point3d(0.0, 0.0, 0.0))
                nb.Leader.Leaders.Append(lead)
            return nb.Commit()
        finally:
            try:
                nb.Destroy()
            except Exception:
                pass

    note(['Pruefkoerper - Wellenstummel Oe25 x 70',
          'ISO 2768-m - Tolerierung ISO 8015'],
         NXOpen.Point3d(18.0, 192.0, 0.0))
    tap_cands = match_dia(edges, 5.0, tol=0.3)
    assert tap_cands, {'M6-Leaderkante fehlt': diag()}
    tap_done, tap_errs = False, []
    for cand in tap_cands[:3]:
        try:
            note(['M6 x 1 (12 tief)',
                  'Kernloch Oe5 (14 tief)'],
                 NXOpen.Point3d(248.0, 100.0, 0.0),
                 edge=cand, view=views['right'])
            result['m6_leader'] = 'ok'
            tap_done = True
            break
        except Exception as error:
            tap_errs.append(str(error)[:150])
    assert tap_done, {'M6-Leader fehlgeschlagen': tap_errs}
    note(['Nut B6 P9, t1 = 3,5 ab Mantel (Hinweis)'],
         NXOpen.Point3d(150.0, 14.0, 0.0))
    if watchable:
        time.sleep(1.0)

    # --- Guards + PDF (Fit erst NACH Export: isoliert Rescaler) ---
    result['stage'] = 'update+export'
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    for label, vw in views.items():
        result['views'][label] = {
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
    result['scale_pre_export'] = {
        label: safe(lambda v=vw: str(v.Scale))
        for label, vw in views.items()}
    assert all(v['fresh'] for v in result['views'].values()), result['views']
    pdf_path = str(out / (out.name + '.pdf'))
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
    import os
    result['pdf'] = pdf_path
    result['pdf_bytes'] = os.path.getsize(pdf_path)
    result['pdf_ok'] = result['pdf_bytes'] > 1000
    assert result['pdf_ok'], result['pdf_bytes']

    result['stage'] = 'frame for watcher'
    try:
        wv = part.Views.WorkView
        if 'Fit' in dir(wv):
            wv.Fit()
            result['fit'] = 'called'
        wv.UpdateDisplay()
    except Exception as error:
        result['fit'] = 'ERR: ' + str(error)[:200]
    result['scale_post_fit'] = {
        label: safe(lambda v=vw: str(v.Scale))
        for label, vw in views.items()}
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'

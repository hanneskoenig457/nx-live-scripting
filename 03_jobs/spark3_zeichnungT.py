"""SPARK3 Template-Blatt v1: KUP A3-Vorlage + 1:1-Ansichten + tolerierte Masse.

Teil: Form-D-Modell (Run 20260907T072108Z-24b9e214), per FullPath-Match +
SetDisplay-Fallback. Frisches Teil -> keine Boegen erwartet (sonst Fail).
Template: C:/.../templates/KUP_Zeichenvorlage.prt (VM-lokal verifiziert).
Attribute VOR Blatt (Titel aus Proben-Tabelle); Allgemeintoleranz 'ISO 2768-m'
statt Template-Default 'mK' (Abstract: keine KMG-Pauschalen); Datum aus
parameters.json; Personen/Kurs neutral '-'; SHEET_NUM/NO_OF_SHEET '1';
SCALE/WEIGHT/Material per NX bzw. Material_manuell='1.4301'.
Blatt: UseTemplate + voller Pfad, Open, SetTemplateInstantiationIsComplete,
Layer 256 sichtbar. Massstab fix 1:1 (Titelzelle) -> Ansichten 1.0.
Masse = bewiesene Finder/Pfade (6x, Fits, Bilateral 1.1): L70, Oe20 h6,
Oe25, Nut 1.1+0.14, Nutgrund Oe19 h11, Nutbreite 6 P9. Notes: M6/Form D,
t1, Ra -- KEINE Titel/ISO-Notes (Schriftfeld-Zellen). MoveView-Muster pro
Ansicht (Platzierung wird ignoriert, §13). UpdateViews-Gate, PDF, Save.
Mark-IDs protokolliert. result.json (UTF-8).
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
            '20260907T072108Z-24b9e214/20260907T072108Z-24b9e214.prt')
TEMPLATE = ('C:/Users/hanne/Documents/OnlineMachiningNX/templates/'
            'KUP_Zeichenvorlage.prt')
PREFIX = 'SPARK3_'
SCALE = 1.0


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'dims': [], 'trials': [],
              'views': {}, 'marks': {}, 'attrs': {}}
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
    params = json.loads((out / 'parameters.json').read_text())

    def mark(key, label):
        mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                                  label)
        result['marks'][key] = safe(lambda: str(mid))
        return mid

    result['stage'] = 'context'
    want = None
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        if isinstance(full, str) and full.replace('\\', '/').lower() == \
                BASE_PRT.lower():
            want = p
            break
    assert want is not None, {'model part not open': BASE_PRT}
    shown = safe(lambda: str(session.Parts.Display.FullPath))
    if not (isinstance(shown, str) and shown.replace('\\', '/').lower()
            == BASE_PRT.lower()):
        session.Parts.SetDisplay(want)
    part = want
    result['part'] = safe(lambda: part.JournalIdentifier)
    body = list(part.Bodies)[0]

    # --- Purge: Selbstreinigung (Prefix + 'Blatt 1' vom Template-Lauf) ---
    result['stage'] = 'purge'
    mark('purge', 'SPARK3 Purge Blatt 1')
    purged = []
    for sh in list(part.DrawingSheets):
        nm = safe(lambda s=sh: str(s.Name))
        if isinstance(nm, str) and (nm.startswith(PREFIX) or nm == 'Blatt 1'):
            m = session.SetUndoMark(
                NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
            session.UpdateManager.AddToDeleteList([sh])
            session.UpdateManager.DoUpdate(m)
            purged.append(nm)
    result['purged'] = purged

    # --- Attribute (Titel aus Template-Probe 20260907T071525Z-ca710b73) ---
    result['stage'] = 'attributes'
    mark('attrs', 'SPARK3 Attribute')
    str_attrs = {
        'Bezeichnung/Titel': 'Prüfkörper',
        'Dokumentenart': 'Fertigungszeichnung',
        'Allgemeintoleranz': 'ISO 2768-m',
        'Material_manuell': '1.4301',
        'Name': '-', 'Matrikelnummer': '-', 'Tutor': '-',
        'Tutoriumstermin': '-', 'Gruppe': '-', 'Semester': '-', 'Kurs': '-',
        'SHEET_NUM': '1', 'NO_OF_SHEET': '1'}

    def set_attrs(tag):
        for title, value in str_attrs.items():
            try:
                part.SetUserAttribute(title, -1, value,
                                      NXOpen.Update.Option.Now)
                result['attrs'][title + '@' + tag] = 'set'
            except Exception as error:
                result['attrs'][title + '@' + tag] = 'ERR: ' + \
                    str(error)[:150]
        try:
            part.SetTimeUserAttribute('Datum', -1, params.get(
                'date', '07-Sep-2026 10:30:00'), NXOpen.Update.Option.Now)
            result['attrs']['Datum@' + tag] = params.get('date', 'default')
        except Exception as error:
            result['attrs']['Datum@' + tag] = 'ERR: ' + str(error)[:150]

    def read_attrs(tag):
        try:
            got = {}
            for a in part.GetUserAttributes():
                try:
                    t = a.Title
                except Exception:
                    continue
                if t in str_attrs or t in ('Datum', 'Werkstoff'):
                    try:
                        got[t] = str(a.StringValue)
                    except Exception:
                        try:
                            got[t] = 'time=' + str(a.TimeValue)
                        except Exception:
                            got[t] = '?'
            result['attr_readback@' + tag] = got
        except Exception as error:
            result['attr_readback@' + tag] = 'ERR: ' + str(error)[:200]

    set_attrs('pre')
    read_attrs('pre')

    # --- Blatt aus Template ---
    result['stage'] = 'sheet from template'
    mark('sheet', 'SPARK3 Template-Blatt')
    sb = part.DrawingSheets.DrawingSheetBuilder(None)
    try:
        sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
        sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        sb.MetricSheetTemplateLocation = TEMPLATE
        sheet = sb.Commit()
    finally:
        sb.Destroy()
    sheet.Open()
    result['sheet'] = {'name': safe(lambda: sheet.Name),
                       'len': safe(lambda: float(sheet.Length)),
                       'h': safe(lambda: float(sheet.Height))}
    try:
        part.Drafting.SetTemplateInstantiationIsComplete(True)
        result['instantiation'] = 'complete'
    except Exception as error:
        result['instantiation'] = 'ERR: ' + str(error)[:200]
    try:
        part.Layers.SetState(256, NXOpen.Layer.State.Visible)
    except Exception as error:
        result['layer256_set'] = 'ERR: ' + str(error)[:150]
    result['layer256'] = safe(lambda: str(part.Layers.GetState(256)))
    try:
        blocks = list(part.DraftingManager.TitleBlocks)
        result['titleblocks'] = [safe(lambda t=t: t.Name) for t in blocks]
        if blocks:
            # Refresh-Hypothese: Attribute NACH Blatt-Erstellung erneut setzen
            set_attrs('post')
            read_attrs('post')
            eb = part.DraftingManager.TitleBlocks \
                .CreateEditTitleBlockBuilder([blocks[0]])
            try:
                cells = []
                n = eb.Cells.Length
                for i in range(n):
                    c = eb.Cells.FindItem(i)
                    info = {'index': i, 'type': type(c).__name__}
                    try:
                        info['members'] = [
                            m for m in members(c)
                            if not m.startswith('Get')][:60]
                    except Exception:
                        pass
                    for m in ('Row', 'Column'):
                        info[m.lower()] = safe(
                            lambda cc=c, mm=m: str(getattr(cc, mm)))
                    for m in ('Text', 'StringValue', 'Value'):
                        v = safe(lambda cc=c, mm=m: getattr(cc, mm))
                        if not (isinstance(v, str) and v.startswith('ERR')):
                            info[m] = str(v)[:120]
                    for m in ('GetText',):
                        v = safe(lambda cc=c, mm=m: str(getattr(cc, mm)()))
                        if not v.startswith('ERR'):
                            info[m] = v[:120]
                    cells.append(info)
                result['title_cells'] = cells
            finally:
                try:
                    eb.Destroy()
                except Exception:
                    pass
    except Exception as error:
        result['titleblocks'] = 'ERR: ' + str(error)[:200]
    if watchable:
        time.sleep(1.0)

    # --- Skizzen/Datums weg (bewiesen) ---
    result['stage'] = 'layers'
    mark('layers', 'SPARK3 Layer Blatt')
    moved = {'sketches': [], 'datums': 0}
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
            except Exception:
                continue
    except Exception:
        pass
    try:
        for d in part.Datums:
            try:
                part.Layers.MoveDisplayableObjects(61, [d])
                moved['datums'] += 1
            except Exception:
                continue
    except Exception:
        pass
    result['moved'] = moved
    part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    part.Layers.SetState(61, NXOpen.Layer.State.Hidden)

    # --- Ansichten 1.0 + MoveView (bewiesenes Muster, §13) ---
    result['stage'] = 'views'
    views = {}
    for label, model_view, at, mv_to in (
            ('front', 'Front', NXOpen.Point3d(160.0, 170.0, 0.0),
             NXOpen.Point3d(160.0, 170.0, 0.0)),
            ('top', 'Top', NXOpen.Point3d(160.0, 70.0, 0.0),
             NXOpen.Point3d(160.0, 70.0, 0.0)),
            ('right', 'Right', NXOpen.Point3d(330.0, 170.0, 0.0),
             NXOpen.Point3d(330.0, 170.0, 0.0))):
        mark('view_' + label, 'SPARK3 Ansicht ' + label)
        mv = part.ModelingViews.FindObject(model_view)
        vw = sheet.SheetDraftingViews.CreateBaseView(mv, at, SCALE, False)
        vw.Update()
        try:
            vw.MoveView(mv_to)
            mv_how = 'MoveView ok'
        except Exception as error:
            mv_how = 'ERR: ' + str(error)[:150]
        vw.Update()
        views[label] = vw
        result['views'][label] = {
            'move': mv_how,
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
        if watchable:
            time.sleep(1.0)
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    for label, vw in views.items():
        result['views'][label] = {
            'move': result['views'][label]['move'],
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
    assert all(v['fresh'] for v in result['views'].values()), \
        {'views stale': result['views']}

    # --- Finder + Mass-Helfer (Modell-Raum, platzierungsunabhaengig) ---
    edges = list(body.GetEdges())

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

    def arcs_at(x, tol=0.25):
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

    def face_edges(face):
        try:
            return list(face.GetEdges())
        except Exception:
            return []

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

    def assoc(obj, view, option):
        a = part.Annotations.NewAssociativity()
        a.FirstObject = obj
        a.ObjectView = view
        a.PointOption = option
        return a

    ArcCenter = NXOpen.Annotations.AssociativityPointOption.ArcCenter
    OnCurve = NXOpen.Annotations.AssociativityPointOption.OnCurve
    POINT_OPTS = ['OnCurve', 'ArcCenter', 'Tangent', 'Control', 'Defining',
                  'Anchor']

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
        m = session.SetUndoMark(
            NXOpen.Session.MarkVisibility.Invisible, 'Probemass')
        session.UpdateManager.AddToDeleteList([dim])
        session.UpdateManager.DoUpdate(m)

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

    def apply_fit(dim, dev, grade):
        dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
        dim.LimitFitDeviation = dev
        dim.LimitFitGrade = grade

    H = part.Dimensions.CreateHorizontalDimension
    V = part.Dimensions.CreateVerticalDimension
    DIA = part.Dimensions.CreateDiameterDimension
    CYL = part.Dimensions.CreateCylindricalDimension

    class StageFail(Exception):
        pass

    def stage(label, fn):
        result['stage'] = label
        mark('dim_' + label[:20], 'SPARK3 ' + label[:30])
        try:
            fn()
        except Exception as error:
            result['dims'].append({'label': label, 'ok': False,
                                   'error': str(error)[:300]})

    # L70
    def do_L70():
        a0, a70 = arcs_at(0.0), arcs_at(70.0)
        if a0 and a70:
            dim = place(H, views['front'],
                        [assoc(a0[0], views['front'], ArcCenter),
                         assoc(a70[0], views['front'], ArcCenter)],
                        NXOpen.Point3d(170.0, 140.0, 0.0))
            if abs(float(dim.ComputedSize) - 70.0) < 1e-6:
                record('Laenge 70', 70.0, dim, {'path': 'rim-arcs'})
                return
            result['trials'].append({'dim': 'L70-arcs',
                                     'computed': float(dim.ComputedSize)})
            delete_trial(dim)
        raise StageFail('L70 ohne Treffer')
    stage('Laenge 70', do_L70)

    # Oe20 h6 + Oe25
    def do_dia():
        e20 = match_dia(edges, 20.0)
        if not e20:
            raise StageFail('Oe20-Kreis fehlt')
        dim = place(DIA, views['right'],
                    [assoc(e20[0], views['right'], OnCurve)],
                    NXOpen.Point3d(330.0, 205.0, 0.0), center=False)
        apply_fit(dim, 'h', 6)
        record('Sitz Oe20 h6', 20.0, dim, {'fit': 'h6'})
        e25 = match_dia(edges, 25.0)
        if not e25:
            raise StageFail('Oe25-Kreis fehlt')
        dim = place(DIA, views['right'],
                    [assoc(e25[0], views['right'], OnCurve)],
                    NXOpen.Point3d(330.0, 140.0, 0.0), center=False)
        record('Welle Oe25', 25.0, dim)
    stage('Durchmesser', do_dia)

    # Nut 1.1 + bilateral
    def do_groovew():
        w1 = [f for f, p in planar_faces(0, +1) if abs(p[0] - 57.45) < 0.05]
        w2 = [f for f, p in planar_faces(0, -1) if abs(p[0] - 58.55) < 0.05]
        if not (w1 and w2):
            raise StageFail('Nutwand-Faces fehlen')
        for opt_name in POINT_OPTS:
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(H, views['front'],
                            [assoc(w1[0], views['front'], opt),
                             assoc(w2[0], views['front'], opt)],
                            NXOpen.Point3d(200.0, 195.0, 0.0))
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

    # Nutgrund Oe19 h11
    def do_gbase():
        gb = cyl_faces(9.5, 0)
        for opt_name in ('OnCurve', 'Tangent'):
            if not gb:
                break
            try:
                opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                              opt_name)
                dim = place(CYL, views['front'],
                            [assoc(gb[0], views['front'], opt),
                             assoc(gb[0], views['front'], opt)],
                            NXOpen.Point3d(200.0, 170.0, 0.0), center=False)
                if abs(float(dim.ComputedSize) - 19.0) < 1e-6:
                    apply_fit(dim, 'h', 11)
                    record('Nutgrund Oe19 h11', 19.0, dim,
                           {'fit': 'h11', 'path': 'face-twice/' + opt_name})
                    return
                result['trials'].append(
                    {'dim': 'Nutgrund/' + opt_name,
                     'computed': float(dim.ComputedSize)})
                delete_trial(dim)
            except Exception as error:
                result['trials'].append({'dim': 'Nutgrund/' + opt_name,
                                         'error': str(error)[:200]})
        raise StageFail('Nutgrund ohne Treffer')
    stage('Nutgrund', do_gbase)

    # Nutbreite 6 P9
    def do_width6():
        flm = [f for f, p in planar_faces(2, +1) if abs(p[2] + 3.0) < 0.02]
        flp = [f for f, p in planar_faces(2, -1) if abs(p[2] - 3.0) < 0.02]
        if flm and flp:
            for opt_name in POINT_OPTS:
                try:
                    opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                                  opt_name)
                    dim = place(V, views['front'],
                                [assoc(flm[0], views['front'], opt),
                                 assoc(flp[0], views['front'], opt)],
                                NXOpen.Point3d(150.0, 195.0, 0.0),
                                center=False)
                    if abs(float(dim.ComputedSize) - 6.0) < 1e-6:
                        apply_fit(dim, 'P', 9)
                        record('Nutbreite 6 P9', 6.0, dim,
                               {'fit': 'P9', 'path': 'flank/' + opt_name})
                        return
                    result['trials'].append(
                        {'dim': 'Nut-6/' + opt_name,
                         'computed': float(dim.ComputedSize)})
                    delete_trial(dim)
                except Exception as error:
                    result['trials'].append({'dim': 'Nut-6/' + opt_name,
                                             'error': str(error)[:200]})
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
        if len(floor_edges) >= 2:
            e_a = [e for z, e in floor_edges if z < 0][0]
            e_b = [e for z, e in floor_edges if z > 0][0]
            for opt_name in ('OnCurve', 'Tangent'):
                try:
                    opt = getattr(NXOpen.Annotations.AssociativityPointOption,
                                  opt_name)
                    dim = place(V, views['front'],
                                [assoc(e_a, views['front'], opt),
                                 assoc(e_b, views['front'], opt)],
                                NXOpen.Point3d(150.0, 195.0, 0.0),
                                center=False)
                    if abs(float(dim.ComputedSize) - 6.0) < 1e-6:
                        apply_fit(dim, 'P', 9)
                        record('Nutbreite 6 P9', 6.0, dim,
                               {'fit': 'P9',
                                'path': 'floor-edges/' + opt_name})
                        return
                    result['trials'].append(
                        {'dim': 'Nut-6e/' + opt_name,
                         'computed': float(dim.ComputedSize)})
                    delete_trial(dim)
                except Exception as error:
                    result['trials'].append({'dim': 'Nut-6e/' + opt_name,
                                             'error': str(error)[:200]})
        raise StageFail('Nutbreite ohne Treffer')
    stage('Nutbreite', do_width6)

    # Ra + Notes (ohne Titel/ISO: Schriftfeld-Zellen)
    def do_finish_notes():
        mark('finish', 'SPARK3 Ra+Notes')
        seam, best = None, 0.0
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
                continue
            ym, zm = (y1 + y2) / 2, (z1 + z2) / 2
            if abs(math.hypot(ym, zm) - 10.0) > 0.03:
                continue
            if min(x1, x2) < 44.9 or max(x1, x2) > 70.1:
                continue
            L = abs(x2 - x1)
            if L < 1e-6 or ym < 9.0 or zm < 0:
                continue
            if L > best:
                best, seam = L, e
        if seam is None:
            raise StageFail('Sitz-Kante fehlt')
        fb = part.Annotations.DraftingSurfaceFinishSymbols \
            .CreateDraftingSurfaceFinishBuilder(None)
        try:
            fb.Finish = NXOpen.Annotations \
                .DraftingSurfaceFinishBuilderFinishType \
                .ModifierMaterialRemovalRequired
            fb.SingleRoughnessValue = True
            fb.A1 = 'Ra 0,8'
            fb.Origin.OriginPoint = NXOpen.Point3d(215.0, 195.0, 0.0)
            lead = part.Annotations.CreateLeaderData()
            lead.Arrowhead = \
                NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
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

        def note(lines, point, edge=None, view=None):
            nb = part.Annotations.CreateDraftingNoteBuilder(None)
            try:
                nb.Text.TextBlock.SetText(list(lines))
                nb.Origin.OriginPoint = point
                if edge is not None:
                    lead = part.Annotations.CreateLeaderData()
                    lead.Arrowhead = NXOpen.Annotations \
                        .LeaderDataArrowheadType.FilledArrow
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

        tap = match_dia(edges, 5.0, tol=0.3)
        if not tap:
            raise StageFail('M6-Leaderkante fehlt')
        done = False
        for cand in tap[:3]:
            try:
                note(['M6 x 1 (12 tief)',
                      'Kernloch Oe5 (16 tief)',
                      'Zentrierform D 60 Grad'],
                     NXOpen.Point3d(352.0, 150.0, 0.0),
                     edge=cand, view=views['right'])
                done = True
                break
            except Exception:
                continue
        if not done:
            raise StageFail('M6-Leader fehlgeschlagen')
        result['m6_leader'] = 'ok'
        note(['Nut B6 P9, t1 = 3,5 ab Mantel (Hinweis)'],
             NXOpen.Point3d(330.0, 250.0, 0.0))
    stage('Finish+Notes', do_finish_notes)

    # Guards + PDF + Fit danach
    result['stage'] = 'update+export'
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    for label, vw in views.items():
        result['views'][label] = {
            'move': result['views'][label]['move'],
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects()),
            'fresh': (vw.IsOutOfDate is False
                      and len(vw.AskVisibleObjects()) > 0)}
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
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'

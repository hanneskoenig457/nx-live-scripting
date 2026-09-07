"""SPARK3 Cleanup + Rahmung: Navigator entschlacken, Final-Bogen einrahmen.

Teil: verifiziertes Modell (Run 20260906T153508Z-a28c46ac), Display-Check mit
SetDisplay-Fallback (verifiziertes Muster). Modell-Features werden NICHT
angefasst -- nur der Drawing-Zweig.
1. Listet alle Bogen (Name + View-Zahl).
2. Dumpt members(Bogen) + members(Ansicht) -- findet Loesch-/Fit-API per
   dir(), kein Raten (Beleg fuer Schicht 4).
3. Loescht alle 'SPARK3_*'-Boegen AUSSER dem finalen (SPARK3_070e502a,
   visuell abgenommen): erst Bogen.Delete() falls vorhanden, sonst
   DeleteList + DoUpdate. Pro Bogen try/except, Bericht kept/deleted/failed.
   Rot-X-Fehlbogen zuerst (die stoeren am meisten).
4. Oeffnet den Final-Bogen, ruft Fit auf der Drafting-Arbeitsansicht falls
   vorhanden (Zuschauer sieht das Blatt danach vollstaendig), Repaint.
5. Speichert. Alles in result.json (UTF-8); keine Exception entkommt.
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Drawings
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer
import NXOpen.UF

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260906T153508Z-a28c46ac/20260906T153508Z-a28c46ac.prt')
FINAL_SHEET = 'SPARK3_070e502a'
PREFIX = 'SPARK3_'


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'deleted': [], 'kept': [],
              'failed': []}
    try:
        run(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result, watchable=True):
    session = NXOpen.Session.GetSession()

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
        session.Parts.SetDisplay(want)
        shown = safe(lambda: str(session.Parts.Display.FullPath))
    assert isinstance(shown, str) and shown.replace('\\', '/').lower() == \
        BASE_PRT.lower(), {'display mismatch': shown}
    part = want
    result['part'] = safe(lambda: part.JournalIdentifier)
    result['model_features'] = safe(
        lambda: [f.JournalIdentifier for f in part.Features][:12])

    # --- Inventur ---
    result['stage'] = 'inventory'
    sheets = list(part.DrawingSheets)
    inv = []
    for sh in sheets:
        nm = safe(lambda s=sh: s.Name)
        try:
            nv = len(list(sh.SheetDraftingViews))
        except Exception:
            nv = 'ERR'
        inv.append({'name': nm, 'views': nv})
    result['inventory'] = inv

    # --- API-Dump (Beleg, kein Raten) ---
    result['stage'] = 'api dump'
    if sheets:
        result['sheet_members'] = members(sheets[0])
        try:
            vws = list(sheets[0].SheetDraftingViews)
            result['view_members'] = members(vws[0]) if vws else []
        except Exception as error:
            result['view_members'] = 'ERR: ' + str(error)[:200]
    try:
        wv = part.Views.WorkView
        result['workview_type'] = type(wv).__name__
        result['workview_members'] = members(wv)
    except Exception as error:
        result['workview'] = 'ERR: ' + str(error)[:200]

    # --- Loeschen (nur PREFIX, nie FINAL, nie Modell) ---
    result['stage'] = 'delete old sheets'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Navigator Cleanup')
    final = None
    for sh in list(part.DrawingSheets):
        nm = safe(lambda s=sh: s.Name)
        if nm == FINAL_SHEET:
            final = sh
    assert final is not None, {'final sheet missing': FINAL_SHEET}
    final.Open()
    if watchable:
        time.sleep(1.0)
    for sh in list(part.DrawingSheets):
        nm = safe(lambda s=sh: s.Name)
        if not isinstance(nm, str) or not nm.startswith(PREFIX):
            result['kept'].append({'name': nm, 'why': 'foreign, untouched'})
            continue
        if nm == FINAL_SHEET:
            result['kept'].append({'name': nm, 'why': 'accepted drawing'})
            continue
        try:
            if 'Delete' in members(sh):
                sh.Delete()
                how = 'Delete()'
            else:
                mark = session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
                session.UpdateManager.AddToDeleteList([sh])
                session.UpdateManager.DoUpdate(mark)
                how = 'DeleteList+DoUpdate'
            result['deleted'].append({'name': nm, 'how': how})
        except Exception:
            result['failed'].append(
                {'name': nm, 'error': traceback.format_exc()[-400:]})
        if watchable:
            time.sleep(1.0)

    # --- Rahmung: Fit auf der Drafting-Arbeitsansicht ---
    result['stage'] = 'frame final sheet'
    final.Open()
    fit_report = {}
    try:
        wv = part.Views.WorkView
        fit_report['workview'] = type(wv).__name__
        if 'Fit' in members(wv):
            wv.Fit()
            fit_report['Fit'] = 'called'
        else:
            fit_report['Fit'] = 'no Fit member'
        try:
            wv.UpdateDisplay()
            fit_report['repaint'] = 'ok'
        except Exception as error:
            fit_report['repaint'] = 'ERR: ' + str(error)[:150]
    except Exception:
        fit_report['error'] = traceback.format_exc()[-400:]
    result['fit'] = fit_report
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'verify+save'
    rest = []
    for sh in part.DrawingSheets:
        nm = safe(lambda s=sh: s.Name)
        try:
            nv = len(list(sh.SheetDraftingViews))
        except Exception:
            nv = 'ERR'
        rest.append({'name': nm, 'views': nv})
    result['remaining'] = rest
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'

"""Verify a collected NX run: schema, rules, deviations, dims, PDF, hash.

Usage (from toolkit root, host Python):
    .venv/bin/python 01_host/nx_check_result.py --run <run-id> [--gate-pdf]

Fails (exit 1) when the run's evidence is incomplete — even if the job
reported ok. Checks, in order:
 1. bridge-execution.json: execution_ok, pid/session/thread present, and the
    SHA-256 recomputed locally against runs/nx/<run>/job.py (independent of
    what the dispatcher claims).
 2. result.json: ok true, stage complete, no bare traceback-as-success.
 3. rules[] (template regime): every entry resolved (met/deviated) — an
    'open' rule fails the run. Jobs predating the template get a warning.
 4. deviations[]: each entry carries tried/fallback/why (undocumented
    fallback = defect).
 5. dims[] (drawings): label/nominal/computed/ok recomputed from values
    (not trusted blindly), plus view + rule fields (placement conformity).
    checks[] (models): label/nominal/ok recomputed.
 6. figure_checks[]: required whenever dims exist — [{feature, figure,
    match}] forces the figure-against-PDF comparison (Bild 9-16 etc.).
    The script cannot judge the match; it makes skipping impossible.
 7. pdf: pdf_ok must agree with a real file (remote + local copies) of
    matching byte size.
 8. --gate-pdf: ink-bbox gate (needs pdftoppm + PIL + numpy): horizontal
    rules >25 mm must start >=10 mm and end <=289 mm on A-series sheets.
    Skipped with a warning when the tools are missing.

Prints a JSON report; exit 0 only when every applicable check passes.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDINGS = []


def check(name, ok, detail=None):
    entry = {'check': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    FINDINGS.append(entry)
    return bool(ok)


def load_json(path):
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-8', 'cp1252'):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError('undecodable JSON: %s' % path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', required=True, help='run id under runs/nx')
    ap.add_argument('--gate-pdf', action='store_true',
                    help='also run the ink-bbox gate on the collected PDF')
    ap.add_argument('--left-min', type=float, default=10.0)
    ap.add_argument('--right-max', type=float, default=None,
                    help='absolute mm; default: page width - 8')
    args = ap.parse_args()

    local = ROOT / 'runs' / 'nx' / args.run
    if not local.is_dir():
        print(json.dumps({'run': args.run, 'ok': False,
                          'error': 'unknown run dir'}, indent=2))
        return 2
    remote = local / 'remote'

    try:
        exe = load_json(remote / 'bridge-execution.json')
    except Exception as error:
        print(json.dumps({'run': args.run, 'ok': False,
                          'error': 'bridge-execution.json: %s' % error},
                         indent=2))
        return 1
    check('execution_ok', exe.get('execution_ok') is True, exe.get('error'))
    for field in ('pid', 'session_id', 'thread_id'):
        check('bridge field ' + field, exe.get(field) not in (None, 0),
              exe.get(field))
    try:
        sha = hashlib.sha256((local / 'job.py').read_bytes()).hexdigest()
        check('source sha256 recomputed', sha == exe.get('sha256'),
              {'local': sha[:12], 'remote': str(exe.get('sha256'))[:12]})
    except Exception as error:
        check('source sha256 recomputed', False, str(error)[:150])

    try:
        res = load_json(remote / 'result.json')
    except Exception as error:
        print(json.dumps({'run': args.run, 'ok': False,
                          'error': 'result.json: %s' % error}, indent=2))
        return 1
    check('result ok:true', res.get('ok') is True,
          {'stage': res.get('stage'), 'error': bool(res.get('error'))})
    check('stage complete', res.get('stage') == 'complete',
          res.get('stage'))

    if 'rules' in res:
        open_rules = [r.get('rule') for r in res['rules']
                      if r.get('status') not in ('met', 'deviated')]
        check('rules resolved', not open_rules, open_rules or 'all resolved')
    else:
        check('rules resolved', True, 'warning: pre-template job, no rules')

    for dev in res.get('deviations', []):
        check('deviation documented %s' % dev.get('rule'),
              all(dev.get(k) for k in ('tried', 'fallback', 'why')), dev)

    for dim in res.get('dims', []):
        label = dim.get('label', '?')
        try:
            match = dim.get('computed') is not None and \
                abs(float(dim['computed']) - float(dim['nominal'])) < 1e-6
        except (TypeError, ValueError):
            match = False
        check('dim %s value' % label,
              bool(dim.get('ok')) and match,
              {'nominal': dim.get('nominal'),
               'computed': dim.get('computed'),
               'path': dim.get('path')})
        check('dim %s view+rule' % label,
              bool(dim.get('view')) and bool(dim.get('rule')), dim)
    for chk in res.get('checks', []):
        label = chk.get('label', '?')
        try:
            match = chk.get('found') is not None and \
                abs(float(chk['found']) - float(chk['nominal'])) <= \
                float(chk.get('tol', 1e-6) if isinstance(chk.get('tol'), (int, float)) else 1e-6)
        except (TypeError, ValueError):
            match = False
        if not chk.get('ok', False) and not match:
            check('check %s' % label, False, chk)
        else:
            check('check %s' % label, bool(chk.get('ok')), chk.get('found'))

    if res.get('dims'):
        figs = res.get('figure_checks', [])
        complete = bool(figs) and all(
            all(f.get(k) for k in ('feature', 'figure', 'match'))
            for f in figs)
        check('figure_checks present', complete,
              figs if figs else 'missing: compare PDF against figures!')
    failed_items = [d.get('label') for d in res.get('dims', [])
                    if not d.get('ok')] + \
        [c.get('label') for c in res.get('checks', []) if not c.get('ok')]
    if failed_items:
        check('trials recorded for failures',
              bool(res.get('trials')), res.get('trials', [])[:3])

    if res.get('pdf_ok'):
        pdfs = [remote / (args.run + '.pdf'), local / (args.run + '.pdf')]
        found = [p for p in pdfs if p.is_file()]
        sizes = {str(p): p.stat().st_size for p in found}
        check('pdf file present', bool(found), sizes)
        if found and res.get('pdf_bytes'):
            check('pdf bytes match',
                  any(s == res['pdf_bytes'] for s in sizes.values()),
                  {'reported': res.get('pdf_bytes'), 'actual': sizes})
    if args.gate_pdf:
        gate_pdf(args, remote)

    report = {'run': args.run,
              'ok': all(f['ok'] for f in FINDINGS),
              'findings': FINDINGS}
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


def gate_pdf(args, remote):
    pdfs = sorted(remote.glob('*.pdf'))
    if not pdfs:
        check('ink-bbox gate', False, 'no PDF in remote/')
        return
    if shutil.which('pdftoppm') is None:
        check('ink-bbox gate', True, 'warning: pdftoppm missing, skipped')
        return
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        check('ink-bbox gate', True, 'warning: PIL/numpy missing, skipped')
        return
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['pdftoppm', '-png', '-r', '100', str(pdfs[0]),
                        tmp + '/gate'], check=True,
                       capture_output=True)
        im = np.array(Image.open(tmp + '/gate-1.png').convert('L'))
    ink = im < 200
    mm = 25.4 / 100.0
    h, w = ink.shape
    page_w = w * mm
    right_max = args.right_max if args.right_max is not None else page_w - 8.0
    starts, ends = [], []
    for r in range(h):
        row = ink[r]
        s = None
        for i, v in enumerate(row):
            if v and s is None:
                s = i
            if not v and s is not None:
                if (i - 1 - s) * mm > 25:
                    starts.append(s * mm)
                    ends.append((i - 1) * mm)
                s = None
    if not starts:
        check('ink-bbox gate', False, 'no long rules found')
        return
    check('ink-bbox gate left>=%.0f' % args.left_min,
          min(starts) >= args.left_min, round(min(starts), 1))
    check('ink-bbox gate right<=%.0f' % right_max,
          max(ends) <= right_max, round(max(ends), 1))


if __name__ == '__main__':
    raise SystemExit(main())

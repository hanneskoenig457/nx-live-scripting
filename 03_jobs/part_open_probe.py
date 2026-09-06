"""Why does this part not open? Reports NX' load status in plain text.

`Parts.OpenDisplay` does not raise when a part is unusable — it returns `None`
for the part and puts the reason in the load status, which is easy to miss. This
job asks for that reason. It is how "Corrupt data found when loading an OM file"
was identified on a part that had been saved successfully minutes earlier.

Pass the part with `--parameters`:

    echo '{"part": "C:/…/pruefkoerper.prt"}' > /tmp/p.json
    .venv/bin/python 01_host/nx_remote.py part_open_probe.py --parameters /tmp/p.json

Opens read-only paths only, changes nothing, saves nothing.
"""
import json
import traceback
from pathlib import Path
import NXOpen


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def parameters(out):
    source = out / 'parameters.json'
    if source.exists():
        try:
            return json.loads(source.read_text(encoding='utf-8-sig'))
        except Exception:
            return {}
    return {}


def main(job_dir):
    out = Path(job_dir)
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

    given = parameters(out).get('part')
    if not given:
        raise RuntimeError('No part given; pass {"part": "<full path>"} via --parameters')
    path = Path(given)
    result['part'] = str(path)
    result['exists'] = path.exists()
    result['bytes'] = path.stat().st_size if path.exists() else 0

    for label, call in (('OpenDisplay', lambda: session.Parts.OpenDisplay(str(path))),
                        ('Open', lambda: session.Parts.Open(str(path)))):
        entry = {}
        try:
            opened = call()
            entry['part_returned'] = opened[0] is not None
            status = opened[1]
            count = safe(lambda s=status: s.NumberUnloadedParts)
            entry['unloaded'] = count
            if isinstance(count, int):
                entry['messages'] = [
                    {'part': str(safe(lambda i=i: status.GetPartName(i))),
                     'status': str(safe(lambda i=i: status.GetStatus(i))),
                     'text': str(safe(lambda i=i: status.GetStatusDescription(i)))}
                    for i in range(count)]
        except Exception:
            entry['error'] = traceback.format_exc()[-900:]
        result[label] = entry
        safe(lambda: session.Parts.CloseAll(
            NXOpen.BasePart.CloseModified.CloseModified, None))


if __name__ == '__main__':
    main(Path(__file__).resolve().parent)

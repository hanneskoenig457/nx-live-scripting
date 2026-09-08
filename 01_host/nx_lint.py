"""Static pre-flight checks for a job.py, run before it ever reaches the VM.

Catches the two import mistakes that have each already burned a full dispatch
cycle (SSH + NX + collect, ~10-60s and a context-costly failure to diagnose):
a genuine NXOpen sub-namespace referenced without its own `import NXOpen.X`,
and the mirror mistake of importing a name that is actually a *class* in the
root NXOpen namespace — that import itself raises and crashes script load
before the job's own try/except ever runs, so NX answers with a bare
"Unable to execute python script" instead of a traceback in result.json.

Classification of NXOpen.X as namespace-vs-class comes from the installed
NXOpen.xml itself (same source nx_api_lookup.py reads), not a hand-maintained
list — a namespace carries a `T:NXOpen.X.NamespaceDoc` member, a class does
not. This can't go stale the way a hardcoded list would, and it extends
itself to every namespace/class in the installed NX version, not just the
ones a past session happened to hit.

Usage: 01_host/nx_lint.py <job.py>
Exit 0 = no errors (warnings still print, non-blocking). Exit 1 = errors found.
See references/nxopen-python-notes.md in the skill for the incidents this
was written to catch — extend the CHECKS below when a new dispatch-cycle
mistake turns out to be statically detectable, don't just note it in prose.

Text-based, not AST-based: a name mentioned only in a comment or docstring
(e.g. explaining "we deliberately don't use os.environ here") can trigger a
warning on its own text. Accepted tradeoff for staying a fast, dependency-free
regex pass — kept to WARNING level (never ERROR) for exactly this reason.
The `def main(job_dir):` check is ERROR-level because it is unambiguous and
matters only for jobs meant for the visible dispatcher path (nx_dispatch.py
submit); an intentionally batch-only probe (bare `def main():`, run directly
via `nx_remote.py <job>.py` without --prepare-only) will correctly fail it —
that reflects a real incompatibility with the dispatcher's
`Session.Execute(path, "", "main", [runDirectory])` call, not a false
positive.
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / '04_reference/NXOpen.xml'


def load_namespaces_and_classes():
    """(namespaces, classes): top-level NXOpen.<Name> types from the XML.
    NamespaceDoc is the authoritative namespace signal; a name is a class
    otherwise (module-level NXOpen.<Name> constructs, e.g. NXOpen.Sketch,
    NXOpen.Update, NXOpen.PrintPDFBuilder — all reachable via plain
    `import NXOpen`, none importable as `NXOpen.<Name>` themselves)."""
    namespaces, classes = set(), set()
    for member in ET.parse(XML).iter('member'):
        name = member.attrib.get('name', '')
        if not name.startswith('T:NXOpen.'):
            continue
        parts = name[len('T:NXOpen.'):].split('.')
        if len(parts) == 1:
            classes.add(parts[0])
        elif len(parts) == 2 and parts[1] == 'NamespaceDoc':
            namespaces.add(parts[0])
    classes -= namespaces  # NamespaceDoc wins if a name has both signals
    return namespaces, classes


def check(source):
    namespaces, classes = load_namespaces_and_classes()
    imported = set(re.findall(r'^\s*import NXOpen\.(\w+)', source, re.MULTILINE))
    used = set(re.findall(r'NXOpen\.(\w+)[.(]', source))

    errors, warnings = [], []

    for name in sorted(used & namespaces - imported):
        errors.append(
            f"NXOpen.{name} is a namespace (has NamespaceDoc in NXOpen.xml) but is used "
            f"without 'import NXOpen.{name}' — AttributeError at the point of use, or "
            f"worse if it's assigned inside a builder chain other code depends on.")

    for name in sorted(imported & classes):
        errors.append(
            f"'import NXOpen.{name}' — {name} is a CLASS in the root NXOpen namespace "
            f"(no NamespaceDoc), not an importable sub-package. This import itself raises "
            f"ModuleNotFoundError, which happens at script LOAD time, before main()'s own "
            f"try/except can catch it — NX answers the whole dispatch with "
            f"'NXException: Unable to execute python script', not a traceback in "
            f"result.json. Remove the import; NXOpen.{name}.X already works via plain "
            f"'import NXOpen'.")

    for name in sorted(used - namespaces - classes):
        warnings.append(
            f"NXOpen.{name} not found in NXOpen.xml as a namespace or a class — check "
            f"spelling, or confirm with: 04_reference/nx_api_lookup.py {name}")

    for builder_call in ('CreateRevolveBuilder', 'CreateHolePackageBuilder'):
        # Only a NEW builder (called with None) defaults Tolerance to 0.0; a
        # re-edit call (CreateRevolveBuilder(existing_feature), the pattern
        # feature_reedit_probe.py uses to re-open features for diagnosis)
        # inherits whatever tolerance the feature already committed with.
        if re.search(re.escape(builder_call) + r'\(\s*None\s*\)', source) \
                and not re.search(r'\.Tolerance\s*=', source):
            warnings.append(
                f"{builder_call}(None) is used but no '.Tolerance = ...' assignment found "
                f"in the file — defaults to 0.0, commits without complaint, fails later on "
                f"re-open or with an unrelated-looking error (api-modelling.md Paragraph 1).")

    if not re.search(r'^def main\(job_dir\)', source, re.MULTILINE):
        errors.append(
            "No top-level 'def main(job_dir):' found (job-contract.md hard requirement 1) "
            "— Session.Execute calls main(job_dir) by name; an if __name__ guard is never "
            "reached inside NX's embedded interpreter.")

    if re.search(r'\bos\.environ\b', source):
        warnings.append(
            "os.environ referenced — NX freezes the environment when it starts its "
            "embedded interpreter (job-contract.md hard requirement 5); read config from "
            "a parameters.json beside the job instead.")

    return errors, warnings


def main():
    if len(sys.argv) != 2:
        print('usage: nx_lint.py <job.py>', file=sys.stderr)
        return 2
    job_path = Path(sys.argv[1])
    errors, warnings = check(job_path.read_text(encoding='utf-8'))
    for w in warnings:
        print('WARNING:', w)
    for e in errors:
        print('ERROR:', e)
    if errors:
        print(f'\n{len(errors)} error(s), {len(warnings)} warning(s) '
              '— fix errors before dispatching.')
        return 1
    print(f'0 errors, {len(warnings)} warning(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

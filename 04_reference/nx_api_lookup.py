"""Search the private, version-matched NX .NET XML documentation (signatures may
differ in Python).

LAST RESORT. Check, in this order, before running this:
  1. references/SNIPPETS-modelling.md / SNIPPETS-drafting.md — verified, copy-paste
     code from calls that have actually run against this NX version.
  2. references/api-modelling.md / api-drafting.md — the narrative layer-4 files,
     for the *why* behind a trap, or a task the snippets don't cover yet.
  3. Community sources (NXJournaling, GitHub, Stack Overflow) for genuinely new
     territory nothing above covers — still needs translating to Python and a
     cheap probe-verified dispatch before being trusted; never copy it in as-is.
  Only once none of those answer the question does the raw .NET XML belong here.

This tool substring-matches the ENTIRE NXOpen API, not just your area: "Limits"
alone matches ~150 members / ~32,000 characters (~8,000 tokens) in one call,
most of them nothing to do with what you're building. Pass several narrowing
terms together in ONE call (they combine as OR) rather than making several
separate broad single-term calls hunting for the same answer — that pattern has
burned 40,000+ tokens in one exploration for something already sitting solved
in a SNIPPETS file.
"""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKILL_REFS = Path.home() / '.claude/skills/nx-live-scripting/references'
DEFAULT_CAP = 20


def already_covered(terms):
    """Which of the skill's own faster-to-read files already mention any of
    these terms — checked before spending tokens on the raw XML."""
    hits = []
    for filename in ('SNIPPETS-modelling.md', 'SNIPPETS-drafting.md',
                      'api-modelling.md', 'api-drafting.md'):
        path = SKILL_REFS / filename
        try:
            text = path.read_text(encoding='utf-8', errors='replace').lower()
        except OSError:
            continue
        if any(term.lower() in text for term in terms):
            hits.append(filename)
    return hits


def main():
    args = sys.argv[1:]
    show_all = '--all' in args
    terms = [a for a in args if a != '--all']
    if not terms:
        print('usage: nx_api_lookup.py [--all] <term> [<term> ...]', file=sys.stderr)
        return 2

    covered = already_covered(terms)
    if covered:
        print(f"NOTE: {', '.join(terms)!r} already appears in {', '.join(covered)} "
              f"in this skill's own references — that may already be a verified, "
              f"Python-correct answer; this XML gives only the raw .NET signature.")
        print()

    matches = [item for item in ET.parse(ROOT / '04_reference/NXOpen.xml').iter('member')
               if any(key in item.attrib['name'] for key in terms)]
    # Type declarations and shorter names are more likely to be the class itself
    # (what you're usually actually looking for) than a deeply nested member.
    matches.sort(key=lambda m: (not m.attrib['name'].startswith('T:'), len(m.attrib['name'])))

    total = len(matches)
    if total > DEFAULT_CAP and not show_all:
        print(f"WARNING: {total} members matched — this term is broad, matching "
              f"across the whole NXOpen API, not just your area. Showing the "
              f"{DEFAULT_CAP} most likely (type declarations and shorter names first); "
              f"pass --all for the rest, or add a narrower term instead.")
        print()
        matches = matches[:DEFAULT_CAP]

    for item in matches:
        print(item.attrib['name'])
        print(' '.join(''.join(item.itertext()).split())[:650])


if __name__ == '__main__':
    raise SystemExit(main())

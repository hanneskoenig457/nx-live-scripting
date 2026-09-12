#!/usr/bin/env python3
"""Repair malformed Doxygen enum tables in the local NXOpen Python Guide.

Siemens' 2506 Guide occasionally emits an enum's value table in a form that is
missing or cannot be reliably read as one ``Enumerator`` table.  The local
2506.3001 stubs contain those value names.  This tool compares every matching
stub enum with its local Guide page and, only where no structured Doxygen table
matches, injects a clearly labelled replacement table.  It never changes a
correct vendor table or guesses a value.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from html import escape, unescape
import json
from pathlib import Path
import re
import sys
from typing import Iterable


REFERENCE_DIR = Path(__file__).resolve().parent
GUIDE_DIR = REFERENCE_DIR / "nxopen_python_ref"
STUB_DIR = REFERENCE_DIR / "nxopen_python_stubs"
MANIFEST = GUIDE_DIR / ".enum-table-repairs.json"
MARKER_START = "<!-- nxopen-enum-repair:start -->"
MARKER_END = "<!-- nxopen-enum-repair:end -->"
CLASS = re.compile(
    r"^(?P<indent> *)class\s+(?P<name>[A-Za-z_]\w*)\s*\((?P<bases>[^)]*)\)\s*:\s*$"
)
VALUE = re.compile(r"^(?P<indent> *)(?P<name>[A-Za-z_]\w*)\s*:\s*int\b")
TITLE = re.compile(
    r"<title>NXOpen Python Reference Guide:\s*(?P<name>.*?)\s+Class Reference</title>",
    re.DOTALL,
)
TABLE = re.compile(r'<table\s+class="doxtable">(?P<body>.*?)</table>', re.DOTALL)
ROW = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.DOTALL)
CELL = re.compile(r"<t[dh]\b[^>]*>(?P<body>.*?)</t[dh]>", re.DOTALL)
TAGS = re.compile(r"<[^>]+>")
REPAIR_BLOCK = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\s*", re.DOTALL
)


@dataclass(frozen=True)
class EnumDefinition:
    qualified_name: str
    values: tuple[str, ...]
    stub_file: str


@dataclass(frozen=True)
class Repair:
    qualified_name: str
    page: str
    values: tuple[str, ...]
    stub_file: str
    doxygen_tables: int


@dataclass(frozen=True)
class Audit:
    enum_definitions: int
    enum_values: int
    matched_pages: int
    structured_pages: int
    repaired_pages: int
    unmatched_or_alias_enums: int


def module_name(path: Path) -> str:
    relative = path.relative_to(STUB_DIR).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def parse_stub_enums(path: Path) -> Iterable[EnumDefinition]:
    """Read generated ``.pyi`` text without parsing its invalid docstrings."""
    classes: list[tuple[int, str, bool]] = []
    base = module_name(path)
    enum_values: dict[str, list[str]] = {}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        class_match = CLASS.match(line)
        indent = len(line) - len(line.lstrip(" "))
        if line.strip():
            while classes and indent <= classes[-1][0]:
                classes.pop()
        if class_match is not None:
            parent = ".".join(item[1] for item in classes)
            qualified = ".".join(part for part in (base, parent, class_match["name"]) if part)
            is_enum = any(base_name.strip().split(".")[-1] == "Enum" for base_name in class_match["bases"].split(","))
            classes.append((indent, class_match["name"], is_enum))
            if is_enum:
                enum_values[qualified] = []
            continue

        value_match = VALUE.match(line)
        if value_match is None or not classes or not classes[-1][2]:
            continue
        enum_indent, _, _ = classes[-1]
        if len(value_match["indent"]) == enum_indent + 4:
            enum_values[".".join(part for part in (base, ".".join(item[1] for item in classes)) if part)].append(
                value_match["name"]
            )

    for qualified, values in enum_values.items():
        if values:
            yield EnumDefinition(
                qualified_name=qualified,
                values=tuple(values),
                stub_file=path.relative_to(STUB_DIR).as_posix(),
            )


def load_enums() -> list[EnumDefinition]:
    if not STUB_DIR.is_dir():
        raise FileNotFoundError(f"Python stubs unavailable: {STUB_DIR}")
    enums = [enum for path in sorted(STUB_DIR.rglob("*.pyi")) for enum in parse_stub_enums(path)]
    return sorted(enums, key=lambda enum: enum.qualified_name)


def guide_pages() -> dict[str, Path]:
    if not GUIDE_DIR.is_dir():
        raise FileNotFoundError(f"Python Reference Guide unavailable: {GUIDE_DIR}")
    pages: dict[str, Path] = {}
    for page in GUIDE_DIR.glob("a*.html"):
        with page.open(encoding="utf-8", errors="replace") as handle:
            header = handle.read(4096)
        title = TITLE.search(header)
        if title is not None:
            pages[unescape(TAGS.sub("", title["name"]))] = page
    return pages


def text(fragment: str) -> str:
    return " ".join(unescape(TAGS.sub("", fragment)).split())


def doxygen_enumerator_tables(source: str) -> list[tuple[str, ...]]:
    """Return every normal Doxygen ``Enumerator | Comment`` table on a page."""
    tables: list[tuple[str, ...]] = []
    for table_match in TABLE.finditer(source):
        rows = [
            [text(cell) for cell in CELL.findall(row_match["body"])]
            for row_match in ROW.finditer(table_match["body"])
        ]
        if not rows or len(rows[0]) < 2 or rows[0][0] != "Enumerator":
            continue
        values = tuple(row[0] for row in rows[1:] if row)
        tables.append(values)
    return tables


def table_matches(expected: tuple[str, ...], tables: list[tuple[str, ...]]) -> bool:
    expected_values = Counter(expected)
    return any(Counter(table) == expected_values for table in tables)


def is_own_enum_page(source: str, qualified_name: str) -> bool:
    """Reject a flat stub alias that collides with an ordinary class page.

    For example, the stub's old ``NXOpen.Axis`` enum is documented by the
    Guide as ``NXOpen.Axis.Types``.  The normal ``NXOpen.Axis`` class page must
    not receive an enum table merely because both names begin with ``Axis``.
    Every genuine Doxygen enum page exposes its generated ``ValueOf`` method.
    """
    return f"{qualified_name}.ValueOf" in source


def audit() -> tuple[Audit, list[Repair]]:
    enums = load_enums()
    pages = guide_pages()
    repairs: list[Repair] = []
    matched = structured = 0
    for enum in enums:
        page = pages.get(enum.qualified_name)
        if page is None:
            continue
        source = page.read_text(encoding="utf-8", errors="replace")
        vendor_source = REPAIR_BLOCK.sub("", source)
        if not is_own_enum_page(vendor_source, enum.qualified_name):
            continue
        matched += 1
        # Inspect the original Doxygen markup, not a table injected by a prior
        # local repair.  This keeps ``--apply`` repeatable and preserves an
        # accurate manifest after a subsequent mirror refresh.
        tables = doxygen_enumerator_tables(vendor_source)
        if table_matches(enum.values, tables):
            structured += 1
            continue
        repairs.append(
            Repair(
                qualified_name=enum.qualified_name,
                page=page.name,
                values=enum.values,
                stub_file=enum.stub_file,
                doxygen_tables=len(tables),
            )
        )
    report = Audit(
        enum_definitions=len(enums),
        enum_values=sum(len(enum.values) for enum in enums),
        matched_pages=matched,
        structured_pages=structured,
        repaired_pages=len(repairs),
        unmatched_or_alias_enums=len(enums) - matched,
    )
    return report, repairs


def replacement_table(repair: Repair) -> str:
    rows = "".join(f"<tr><td>{escape(value)}</td></tr>" for value in repair.values)
    return (
        f"{MARKER_START}\n"
        '<section class="nxopen-enum-repair">\n'
        '<h2 class="groupheader">Verified enum values</h2>\n'
        '<p>This table repairs an unstructured Doxygen enum table. Values are '
        'taken verbatim from the local NXOpen Python 2506.3001 stubs.</p>\n'
        '<table class="doxtable nxopen-enum-repair-table">\n'
        '<tr><th>Enumerator</th></tr>\n'
        f"{rows}\n</table>\n</section>\n{MARKER_END}\n"
    )


def apply_repairs(repairs: list[Repair]) -> int:
    changed = 0
    for repair in repairs:
        page = GUIDE_DIR / repair.page
        source = page.read_text(encoding="utf-8", errors="replace")
        cleaned = REPAIR_BLOCK.sub("", source)
        marker = '<div class="contents">'
        if marker not in cleaned:
            raise ValueError(f"cannot place repair table in {page}")
        repaired = cleaned.replace(marker, marker + "\n" + replacement_table(repair), 1)
        if repaired != source:
            temporary = page.with_name(f".{page.name}.part")
            temporary.write_text(repaired, encoding="utf-8")
            temporary.replace(page)
            changed += 1
    manifest = {
        "source": "NXOpen Python 2506 Guide + local 2506.3001 stubs",
        "repairs": [asdict(repair) for repair in repairs],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write replacement tables into affected local pages")
    parser.add_argument("--list", action="store_true", help="print every affected enum page")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        report, repairs = audit()
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Enum-table audit unavailable: {error}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), indent=2))
    if arguments.list:
        for repair in repairs:
            print(f"{repair.qualified_name}\t{repair.page}\t{len(repair.values)} values")
    if arguments.apply:
        changed = apply_repairs(repairs)
        print(f"Applied {changed} local enum-table repair(s); manifest: {MANIFEST}")
    else:
        print("Dry run only; pass --apply to write the local repairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

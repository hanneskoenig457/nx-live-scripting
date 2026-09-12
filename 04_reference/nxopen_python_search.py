#!/usr/bin/env python3
"""Query the local Doxygen index of Siemens' NXOpen Python Reference Guide.

This intentionally reads Doxygen's ``search/*.js`` index instead of scanning
the mirrored HTML tree.  It gives an agent the same prefix search that the
Guide's search field provides, without needing a browser or ``rg``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


REFERENCE_ROOT = Path(__file__).resolve().parent / "nxopen_python_ref"
SEARCH_DIR = REFERENCE_ROOT / "search"
SECTIONS = {"all", "classes", "namespaces", "functions", "variables", "pages"}


class ParseError(ValueError):
    """Doxygen search JavaScript was not in its expected data-only format."""


class JavaScriptArrayParser:
    """Small parser for the data literals emitted by Doxygen search indexes."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.position = 0

    def parse(self) -> Any:
        value = self._value()
        self._space()
        return value

    def _space(self) -> None:
        while self.position < len(self.source) and self.source[self.position].isspace():
            self.position += 1

    def _value(self) -> Any:
        self._space()
        if self.position >= len(self.source):
            raise ParseError("unexpected end of index")
        character = self.source[self.position]
        if character == "[":
            return self._array()
        if character in "\"'":
            return self._string(character)
        if character in "-0123456789":
            return self._number()
        return self._word()

    def _array(self) -> list[Any]:
        self.position += 1
        values: list[Any] = []
        self._space()
        if self._accept("]"):
            return values
        while True:
            values.append(self._value())
            self._space()
            if self._accept("]"):
                return values
            if not self._accept(","):
                raise ParseError(f"expected ',' or ']' at {self.position}")

    def _string(self, quote: str) -> str:
        self.position += 1
        characters: list[str] = []
        while self.position < len(self.source):
            character = self.source[self.position]
            self.position += 1
            if character == quote:
                return "".join(characters)
            if character != "\\":
                characters.append(character)
                continue
            if self.position >= len(self.source):
                raise ParseError("unfinished string escape")
            escaped = self.source[self.position]
            self.position += 1
            escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
            if escaped == "x":
                characters.append(chr(int(self._take(2), 16)))
            elif escaped == "u":
                characters.append(chr(int(self._take(4), 16)))
            else:
                characters.append(escapes.get(escaped, escaped))
        raise ParseError("unterminated string")

    def _take(self, count: int) -> str:
        result = self.source[self.position : self.position + count]
        if len(result) != count:
            raise ParseError("unfinished hexadecimal escape")
        self.position += count
        return result

    def _number(self) -> int | float:
        match = re.match(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", self.source[self.position :])
        if match is None:
            raise ParseError(f"invalid number at {self.position}")
        self.position += len(match.group(0))
        number = match.group(0)
        return float(number) if any(marker in number for marker in ".eE") else int(number)

    def _word(self) -> Any:
        match = re.match(r"[A-Za-z_]+", self.source[self.position :])
        if match is None:
            raise ParseError(f"unexpected character at {self.position}")
        self.position += len(match.group(0))
        values = {"true": True, "false": False, "null": None}
        word = match.group(0)
        if word not in values:
            raise ParseError(f"unsupported JavaScript token {word!r}")
        return values[word]

    def _accept(self, character: str) -> bool:
        if self.position < len(self.source) and self.source[self.position] == character:
            self.position += 1
            return True
        return False


def _search_id(term: str) -> str:
    """Apply Doxygen's ASCII punctuation escaping to a search term."""
    encoded: list[str] = []
    for character in term.lower():
        if character.isalnum() or ord(character) >= 128:
            encoded.append(character)
        else:
            encoded.append(f"_{ord(character):02x}")
    return "".join(encoded)


def _section_content(section: str) -> str:
    searchdata = SEARCH_DIR / "searchdata.js"
    if not searchdata.is_file():
        raise FileNotFoundError(f"Doxygen search index missing: {searchdata}")
    source = searchdata.read_text(encoding="utf-8")
    def index_map(variable: str) -> dict[int, str]:
        match = re.search(
            rf"var\s+{variable}\s*=\s*\{{(?P<body>.*?)\}};",
            source,
            flags=re.DOTALL,
        )
        if match is None:
            raise ParseError(f"Doxygen index has no {variable}")
        return {
            int(number): value
            for number, value in re.findall(
                r"(\d+)\s*:\s*['\"]([^'\"]+)['\"]", match.group("body")
            )
        }

    names = index_map("indexSectionNames")
    section_index = next((number for number, name in names.items() if name == section), None)
    if section_index is None:
        raise ParseError(f"Doxygen index has no {section!r} section")
    content = index_map("indexSectionsWithContent").get(section_index)
    if content is None:
        raise ParseError(f"Doxygen index has no character map for {section!r}")
    return content


def _load_chunk(section: str, term: str) -> list[Any]:
    term_id = _search_id(term)
    if not term_id:
        return []
    character_index = _section_content(section).find(term_id[0])
    if character_index < 0:
        return []
    chunk = SEARCH_DIR / f"{section}_{character_index:x}.js"
    if not chunk.is_file():
        raise FileNotFoundError(f"Doxygen index chunk missing: {chunk}")
    source = chunk.read_text(encoding="utf-8")
    assignment = re.search(r"var\s+searchData\s*=\s*", source)
    if assignment is None:
        raise ParseError(f"no searchData literal in {chunk}")
    return JavaScriptArrayParser(source[assignment.end() :]).parse()


def _display_target(href: str) -> str:
    page, anchor, = (href.split("#", 1) + [""])[:2]
    resolved = (SEARCH_DIR / page).resolve()
    try:
        displayed = resolved.relative_to(REFERENCE_ROOT.resolve()).as_posix()
    except ValueError:
        displayed = href
    return f"{displayed}#{anchor}" if anchor else displayed


def search(term: str, section: str, limit: int) -> list[tuple[str, str, str]]:
    term_id = _search_id(term)
    matches: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in _load_chunk(section, term):
        if not isinstance(entry, list) or len(entry) < 2 or not isinstance(entry[0], str):
            continue
        if not entry[0].startswith(term_id):
            continue
        payload = entry[1]
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], str):
            continue
        label = payload[0]
        for target in payload[1:]:
            if not isinstance(target, list) or not target or not isinstance(target[0], str):
                continue
            scope = target[2] if len(target) > 2 and isinstance(target[2], str) else ""
            result = (label, scope, _display_target(target[0]))
            if result not in seen:
                seen.add(result)
                matches.append(result)
            if len(matches) >= limit:
                return matches
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("term", help="Prefix to look up, as in the Doxygen search field")
    parser.add_argument("--section", choices=sorted(SECTIONS), default="all")
    parser.add_argument("--limit", type=int, default=20, help="Maximum results (default: 20)")
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be positive")
    try:
        matches = search(arguments.term, arguments.section, arguments.limit)
    except (FileNotFoundError, ParseError, UnicodeError) as error:
        print(f"Doxygen search unavailable: {error}", file=sys.stderr)
        return 2
    if not matches:
        print(f"No Doxygen hit for {arguments.term!r} in {arguments.section}.")
        return 1
    for label, scope, target in matches:
        qualifier = f" — {scope}" if scope else ""
        print(f"{label}{qualifier}\n  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

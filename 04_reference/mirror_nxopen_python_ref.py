#!/usr/bin/env python3
"""Mirror Siemens' public NXOpen Python Doxygen reference for local browsing.

Only resources below BASE_URL are followed.  The destination is gitignored
because it contains third-party vendor documentation.  The script intentionally
uses only the Python standard library so it remains usable in the project venv
without a package installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import ssl
import sys
import threading
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


BASE_URL = (
    "https://docs.sw.siemens.com/documentation/external/"
    "PL20241101461013487/en-US/custom_api/nxopen_python_ref/"
)
DEFAULT_DESTINATION = Path(__file__).resolve().parent / "nxopen_python_ref"
USER_AGENT = "08-NX-API-local-documentation-mirror/1.0"
SYSTEM_CA_BUNDLES = (
    Path("/etc/ssl/cert.pem"),
    Path("/etc/ssl/certs/ca-certificates.crt"),
)
TEXT_SUFFIXES = {".css", ".htm", ".html", ".js"}
RESOURCE_SUFFIXES = {
    ".css", ".gif", ".htm", ".html", ".ico", ".jpeg", ".jpg", ".js",
    ".map", ".png", ".svg", ".ttf", ".webp", ".woff", ".woff2",
}
ATTRIBUTE_URL = re.compile(
    r"(?P<prefix>\b(?:href|src)\s*=\s*[\"'])(?P<url>[^\"']+)(?P<suffix>[\"'])",
    re.IGNORECASE,
)
CSS_URL = re.compile(
    r"(?P<prefix>url\(\s*[\"']?)(?P<url>[^\"')\s]+)(?P<suffix>[\"']?\s*\))",
    re.IGNORECASE,
)
QUOTED_RESOURCE = re.compile(
    r"[\"'](?P<url>[^\"']+?\.(?:css|gif|html?|ico|jpe?g|js|map|png|svg|ttf|webp|woff2?))(?:\?[^\"']*)?[\"']",
    re.IGNORECASE,
)
SEARCH_SECTION = re.compile(r'^\s*(?P<id>\d+):\s*"(?P<value>[^"]*)"', re.MULTILINE)

BASE_PARTS = urlsplit(BASE_URL)
BASE_PATH = PurePosixPath(unquote(BASE_PARTS.path))


@dataclass(frozen=True)
class DownloadedResource:
    url: str
    content: bytes
    content_type: str


class RateLimiter:
    """Serialize request starts without serializing file parsing and writing."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._next_request = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_request - now)
            self._next_request = max(now, self._next_request) + self.interval
        if wait_seconds:
            time.sleep(wait_seconds)


def canonical_url(candidate: str, page_url: str = BASE_URL) -> str | None:
    """Return an allowed, fragment-free URL or ``None`` for external links."""
    if not candidate or candidate.startswith(("data:", "javascript:", "mailto:")):
        return None

    parsed = urlsplit(urljoin(page_url, candidate))
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc != BASE_PARTS.netloc:
        return None

    path = PurePosixPath(unquote(parsed.path))
    try:
        path.relative_to(BASE_PATH)
    except ValueError:
        return None
    if ".." in path.parts:
        return None

    # Doxygen uses static filenames, and query strings only create duplicate
    # local files.  Fragments stay useful in the browser but require no fetch.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def local_path(url: str, destination: Path) -> Path:
    path = PurePosixPath(unquote(urlsplit(url).path))
    relative = path.relative_to(BASE_PATH)
    if str(relative) in {"", "."}:
        relative = PurePosixPath("index.html")
    if ".." in relative.parts:
        raise ValueError(f"Refusing path outside mirror: {url}")
    return destination.joinpath(*relative.parts)


def extract_links(text: str, page_url: str) -> Iterable[str]:
    """Find normal HTML/CSS URLs plus Doxygen's quoted navtree filenames."""
    for pattern in (ATTRIBUTE_URL, CSS_URL, QUOTED_RESOURCE):
        for match in pattern.finditer(text):
            link = canonical_url(match.group("url"), page_url)
            if link is not None:
                yield link
    yield from dynamic_search_links(text, page_url)


def dynamic_search_links(text: str, page_url: str) -> Iterable[str]:
    """Expand Doxygen's dynamically constructed per-letter search indexes.

    ``search.js`` builds names such as ``search/classes_0.js`` from the two
    maps in ``searchdata.js``.  As those filenames never occur literally in
    the HTML or JavaScript, a conventional static crawler cannot find them.
    """
    page_path = PurePosixPath(unquote(urlsplit(page_url).path))
    if page_path != BASE_PATH / "search" / "searchdata.js":
        return

    maps = re.findall(r"var\s+(indexSectionsWithContent|indexSectionNames)\s*=\s*\{(.*?)\};", text, re.DOTALL)
    sections = {
        name: {int(match.group("id")): match.group("value") for match in SEARCH_SECTION.finditer(body)}
        for name, body in maps
    }
    contents = sections.get("indexSectionsWithContent", {})
    names = sections.get("indexSectionNames", {})
    for section_id, characters in contents.items():
        section_name = names.get(section_id)
        if section_name is None:
            continue
        for index, _ in enumerate(characters):
            link = canonical_url(f"{section_name}_{index:x}.js", page_url)
            if link is not None:
                yield link


def rewrite_absolute_urls(text: str, page_url: str, page_path: Path, destination: Path) -> str:
    """Make absolute in-tree URLs usable when ``index.html`` is opened locally."""
    def replacement(match: re.Match[str]) -> str:
        original = match.group("url")
        parsed = urlsplit(original)
        if not (original.startswith("/") or parsed.scheme in {"http", "https"}):
            return match.group(0)
        target = canonical_url(original, page_url)
        if target is None:
            return match.group(0)
        relative = os.path.relpath(local_path(target, destination), page_path.parent)
        if parsed.fragment:
            relative += f"#{parsed.fragment}"
        return f"{match.group('prefix')}{Path(relative).as_posix()}{match.group('suffix')}"

    return ATTRIBUTE_URL.sub(replacement, CSS_URL.sub(replacement, text))


def certificate_context() -> ssl.SSLContext:
    """Use macOS' CA bundle when the framework Python has none configured."""
    for bundle in SYSTEM_CA_BUNDLES:
        if bundle.is_file():
            return ssl.create_default_context(cafile=str(bundle))
    return ssl.create_default_context()


def fetch(
    url: str, timeout: float, context: ssl.SSLContext, rate_limiter: RateLimiter
) -> DownloadedResource:
    rate_limiter.wait()
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310 - URL is allowlisted above.
        return DownloadedResource(
            url=url,
            content=response.read(),
            content_type=response.headers.get_content_type(),
        )


def write_resource(resource: DownloadedResource, destination: Path) -> list[str]:
    target = local_path(resource.url, destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    is_text = suffix in TEXT_SUFFIXES or resource.content_type.startswith("text/")
    if not is_text:
        write_bytes_atomically(target, resource.content)
        return []

    text = resource.content.decode("utf-8", errors="replace")
    text = rewrite_absolute_urls(text, resource.url, target, destination)
    write_text_atomically(target, text)
    return list(extract_links(text, resource.url))


def write_bytes_atomically(target: Path, content: bytes) -> None:
    temporary = target.with_name(f".{target.name}.part")
    temporary.write_bytes(content)
    temporary.replace(target)


def write_text_atomically(target: Path, content: str) -> None:
    write_bytes_atomically(target, content.encode("utf-8"))


def existing_links(url: str, destination: Path) -> list[str] | None:
    """Reuse complete local pages when continuing an interrupted mirror."""
    target = local_path(url, destination)
    if not target.is_file():
        return None
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return []
    return list(extract_links(target.read_text(encoding="utf-8", errors="replace"), url))


def mirror(
    destination: Path, workers: int, timeout: float, refresh: bool, request_interval: float
) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    pending: deque[str] = deque([BASE_URL + "index.html"])
    scheduled = set(pending)
    downloaded = 0
    reused = 0
    failures: list[str] = []
    context = certificate_context()
    rate_limiter = RateLimiter(request_interval)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while pending:
            batch = [pending.popleft() for _ in range(min(workers, len(pending)))]
            local_results: list[tuple[str, list[str]]] = []
            fetch_urls: list[str] = []
            for url in batch:
                # Starting with a fresh index request makes a resumed crawl obey
                # any session/cookie policy the public host may use.
                links = None if refresh or url == BASE_URL + "index.html" else existing_links(url, destination)
                if links is None:
                    fetch_urls.append(url)
                else:
                    local_results.append((url, links))
                    reused += 1
            futures = {
                pool.submit(fetch, url, timeout, context, rate_limiter): url
                for url in fetch_urls
            }
            for url, discovered in local_results:
                for link in discovered:
                    if link not in scheduled:
                        scheduled.add(link)
                        pending.append(link)
            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                try:
                    discovered = write_resource(future.result(), destination)
                except (HTTPError, TimeoutError, URLError, OSError, ValueError) as error:
                    failures.append(f"{url}: {error}")
                    continue
                downloaded += 1
                for link in discovered:
                    if link not in scheduled:
                        scheduled.add(link)
                        pending.append(link)
                if downloaded % 100 == 0:
                    print(f"{downloaded} Dateien geladen; {len(pending)} noch in der Warteschlange")

    (destination / ".mirror-source.txt").write_text(
        f"Source: {BASE_URL}\nFiles discovered: {len(scheduled)}\n"
        f"Files downloaded in this run: {downloaded}\nFiles reused in this run: {reused}\n",
        encoding="utf-8",
    )
    print(f"Fertig: {len(scheduled)} Ressourcen unter {destination} "
          f"({downloaded} geladen, {reused} wiederverwendet).")
    if failures:
        print(f"WARNUNG: {len(failures)} Datei(en) konnten nicht geladen werden:", file=sys.stderr)
        print("\n".join(failures[:20]), file=sys.stderr)
        if len(failures) > 20:
            print(f"... und {len(failures) - 20} weitere", file=sys.stderr)
        return 1
    return 0


def verify(destination: Path) -> int:
    """Report local Doxygen resource links whose target is not in the mirror."""
    missing: list[tuple[Path, Path]] = []
    checked = 0
    for source in destination.rglob("*"):
        if not source.is_file() or source.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative_source = source.relative_to(destination).as_posix()
        page_url = BASE_URL + relative_source
        text = source.read_text(encoding="utf-8", errors="replace")
        for url in extract_links(text, page_url):
            target = local_path(url, destination)
            checked += 1
            if not target.is_file():
                missing.append((source.relative_to(destination), target.relative_to(destination)))

    print(f"{checked} lokale Doxygen-Referenzen in {destination} geprüft.")
    if not missing:
        print("OK: Alle geprüften lokalen Ressourcen sind vorhanden.")
        return 0
    print(f"FEHLER: {len(missing)} lokale Referenz(en) fehlen:", file=sys.stderr)
    for source, target in missing[:30]:
        print(f"  {source} -> {target}", file=sys.stderr)
    if len(missing) > 30:
        print(f"  ... und {len(missing) - 30} weitere", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=0.1,
        help="Mindestabstand zwischen HTTP-Abrufen in Sekunden (Vorgabe: 0,1)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="auch bereits lokal vorhandene Ressourcen erneut herunterladen",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="nur bereits vorhandene lokale Doxygen-Referenzen pruefen",
    )
    parser.add_argument(
        "--no-enum-repair",
        action="store_true",
        help="nach einem erfolgreichen Standard-Spiegel keine lokalen Enum-Tabellen reparieren",
    )
    return parser.parse_args()


def repair_enum_tables(destination: Path) -> None:
    """Reapply labelled local enum fixes after a vendor-page refresh."""
    if destination != DEFAULT_DESTINATION.resolve():
        print("Enum-Reparatur uebersprungen: benutzerdefiniertes Spiegelziel.")
        return
    try:
        from repair_nxopen_python_enum_tables import apply_repairs, audit

        report, repairs = audit()
        changed = apply_repairs(repairs)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"WARNUNG: lokale Enum-Reparatur nicht ausgefuehrt: {error}", file=sys.stderr)
        return
    print(
        f"Lokale Enum-Reparatur: {changed} Seite(n) aktualisiert "
        f"({report.repaired_pages} unstrukturierte Vendor-Tabellen)."
    )


def main() -> int:
    args = parse_args()
    if args.workers < 1 or args.request_interval < 0:
        print("--workers muss mindestens 1 und --request-interval mindestens 0 sein.", file=sys.stderr)
        return 2
    if args.verify:
        return verify(args.destination.resolve())
    result = mirror(
        args.destination.resolve(),
        args.workers,
        args.timeout,
        args.refresh,
        args.request_interval,
    )
    if result == 0 and not args.no_enum_repair:
        repair_enum_tables(args.destination.resolve())
    return result


if __name__ == "__main__":
    raise SystemExit(main())

"""Doc↔code coverage tripwire — the portable enforcement helper.

A living doc that mirrors an enumerable code surface (MCP tools, CLI verbs, a public
API) rots *silently*: you add a command and forget the doc, and nothing complains. This
turns that silent drift into a failing test. It checks **coverage, never prose
correctness** — both sides are sets of names, so there is no semantics involved and
nothing here is intractable.

The doc declares what it covers with **anchors**: any name in backticks inside a markdown
heading (``### `search` ``), or an explicit ``<!-- surface: NAME -->`` marker for an item
without its own heading. Scope a check to one ``## Section`` so several surfaces can share
one doc without colliding.

The ``waived`` set is the pressure valve: a surface item you have *consciously* chosen not
to document yet is acknowledged, not silently missing — the test forces the choice instead
of letting omission pass. This single function is the reusable artifact; everything
project-specific is the enumerator that produces ``surface`` and the wiring test.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CapabilityCheck:
    """One code↔doc coverage assertion, declared per-project in ``config.py``.

    ``surface`` is a zero-arg callable returning the live set of names (introspected from
    code — MCP tools, CLI verbs, a public API), so nothing here is a transcription. The
    invariant tripwire (``test_capabilities_coverage``) parametrizes over a tuple of these;
    everything project-specific is the enumerator, not the check.
    """

    name: str  # test id, e.g. "MCP tools"
    surface: Callable[[], Iterable[str]]  # live code surface enumerator
    section: str | None = None  # ``## Section`` of the doc scoping this check
    label: str = "surface item"  # noun used in the failure message
    waived: tuple[str, ...] = field(default_factory=tuple)


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BACKTICK = re.compile(r"`([^`]+)`")
_MARKER = re.compile(r"<!--\s*surface:\s*(.+?)\s*-->")


def _slice_section(text: str, section: str | None) -> str:
    """Return the body under the heading whose text equals ``section`` (backticks and case
    ignored), up to the next heading of the same or higher level. ``None`` = whole doc."""
    if section is None:
        return text
    target = section.strip().lower()
    lines = text.splitlines()
    start: int | None = None
    level = 0
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if not m:
            continue
        htext = _BACKTICK.sub(r"\1", m.group(2)).strip().lower()
        if start is None:
            if htext == target:
                start, level = i + 1, len(m.group(1))
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    if start is None:
        raise AssertionError(f"section {section!r} not found in doc")
    return "\n".join(lines[start:])


def documented_names(doc: str | Path, *, section: str | None = None) -> set[str]:
    """Every name the doc anchors — backticked tokens in headings plus ``surface:`` markers,
    within ``section`` if given. This is the deterministic parse the tripwire compares
    against; it never reads prose."""
    text = _slice_section(Path(doc).read_text(encoding="utf-8"), section)
    names: set[str] = set()
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            names.update(t.strip() for t in _BACKTICK.findall(m.group(2)))
    names.update(m.strip() for m in _MARKER.findall(text))
    return names


def assert_documented(
    surface: Iterable[str],
    doc: str | Path,
    *,
    section: str | None = None,
    label: str = "surface item",
    waived: Iterable[str] = (),
    bidirectional: bool = True,
) -> None:
    """Fail if the code ``surface`` and the doc disagree.

    - **missing**: a name in ``surface`` is neither documented nor waived (you shipped it
      and forgot the doc — the silent rot this exists to catch).
    - **stale** (when ``bidirectional``): the doc anchors a name no longer in ``surface``
      (you removed it but the doc still claims it).
    """
    surface_set = set(surface)
    waived_set = set(waived)
    documented = documented_names(doc, section=section)
    where = f"section {section!r} of {doc}" if section else str(doc)

    missing = surface_set - documented - waived_set
    assert not missing, (
        f"{len(missing)} undocumented {label}(s) in {where}: {sorted(missing)} — "
        f"document each (an anchored heading like ``### `name` ``) or add it to `waived`"
    )
    if bidirectional:
        stale = documented - surface_set - waived_set
        assert not stale, (
            f"{len(stale)} stale {label}(s) in {where}: {sorted(stale)} — "
            f"the code surface no longer has these; remove or rename them in the doc"
        )

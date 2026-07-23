"""The keystone tripwire: the capability doc must enumerate the real consumer surface.

This is the one doc whose content is a *function of code* (here: the MCP tools and the CLI
grammar), so it is the one doc that earns an automated forcing function — every other durable
doc (ADRs, the glossary, the roadmap) is human-judged, not testable, and is left alone (see
`docs/spec/README.md`).

Updating the capability doc when the surface changes is therefore part of "done": add the
tool/command as an anchored heading and this test stays green; forget, and it goes red. That
is the whole point — silent doc rot becomes a loud test failure.

**Invariant.** This file is copied verbatim between repos; the surface enumerators + the doc
path are the per-project parameters, declared in `config.CAPABILITY_ENUMERATORS` /
`config.CAPABILITY_DOC`.
"""

from __future__ import annotations

import config
import pytest
from doc_tripwire import CapabilityCheck, assert_documented

CAPABILITIES = config.REPO_ROOT / config.CAPABILITY_DOC


@pytest.mark.parametrize(
    "check", config.CAPABILITY_ENUMERATORS, ids=lambda c: c.name
)
def test_capability_doc_covers_surface(check: CapabilityCheck) -> None:
    assert_documented(
        check.surface(),
        CAPABILITIES,
        section=check.section,
        label=check.label,
        waived=check.waived,
    )

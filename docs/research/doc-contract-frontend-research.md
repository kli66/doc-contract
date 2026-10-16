# Research: Front end for reading doc-contract change items

Saved at `docs/research/doc-contract-frontend-research.md`, alongside
`docs/research/search-provider-comparison.md`. This directory is outside the change graph: the
`doc-contract` resolver only mints nodes for `docs/changes/**/*.md`, `docs/adr/NNNN-*.md`,
`docs/spec/*.md`, `docs/archive/**`, and the root nodes declared in `.doc-contract.toml`, so research
notes are not managed documents and cannot affect preflight.

Research date: 2026-10 (dates below are as observed from GitHub release Atom feeds, PyPI/npm/crates.io
registry JSON during this session; no search-engine snippets were trusted for any decision-relevant
claim — every finding links a primary source). Note: the search-tool providers available in this
session were mostly unavailable (API key/rate-limit failures), so verification was done by directly
fetching release feeds, package registries, LICENSE files, and official doc pages. Claims I could not
verify are flagged in the last section.

## Summary

**Nothing surveyed can be used directly as a doc-contract viewer.** No mature project renders
doc-contract's front matter (`id`/`persistence`/`status`/`depends_on`/`files_owned`/`self_hash`) as
structured UI, none understands one-folder-per-change discovery (`docs/changes/<id>/change.md` +
companion files), and — the hard part — none validates bare backticked code references like
`src/doc_contract/resolver.py:1102` or `files_owned` paths that do not exist yet. Link checkers
(lychee, mdbook-linkcheck) only check *links*, not backticked inline-code refs; doc-site generators
render front matter as invisible metadata at best.

**Best bootstrap candidate (dev-time lane): Material for MkDocs.** It is the only surveyed generator
with a first-class offline story — a built-in `offline` plugin that produces a `site/` directory you
open via `file://`, and a `privacy` plugin that vendors external assets (its docs explicitly say the
result "can work without connectivity to the internet") — plus native Mermaid rendering for the
roadmap DAG and the biggest plugin ecosystem for customizing how front matter and code refs are
rendered. The build is a separate process/venv (`uv`-managed, dev-only), so it does not touch the
stdlib-only `pyproject.toml`. Starlight (Astro) is the strongest Node-side alternative: its content
collections give typed, *validated* front matter schemas (zod), which maps naturally onto
doc-contract's strict front matter, but its offline story is less turnkey.

**Recommendation in one line:** build a thin, project-local static-site generator (~300–600 lines,
dev-time, any runtime) that emits a MkDocs Material project — front matter rendered as structured
tables, `depends_on` and relative links normalized, code refs emitted as `vscode://file/<abs>:<line>`
deep links (documented VS Code URL scheme) — and ship nothing at runtime; the sanctioned extension
seam stays a binary live-pass check. Reuse the renderer/offline/mermaid machinery from Material;
build the doc-contract-specific indexing, code-ref linking, and staleness checks yourself. Separately,
`jmfederico/pi-web` (currently under evaluation, not adopted) is a viable conditional *host* for the
same viewer as a plugin — see the pi-web section below; the standalone path above remains the default.

## Findings

### Material for MkDocs — best offline bootstrap candidate

1. **Claim:** Material for MkDocs is mature and actively maintained: latest release `mkdocs-material-9.7.7` (release feed `updated` 2026-07-28), PyPI classifies it `Development Status :: 5 - Production/Stable`, license MIT.
   [Source: GitHub releases Atom feed](https://github.com/squidfunk/mkdocs-material/releases.atom),
   [Source: PyPI JSON metadata](https://pypi.org/pypi/mkdocs-material/json). **Support:** direct evidence. **Confidence:** high.

2. **Claim:** Material for MkDocs ships a built-in `offline` plugin: after `mkdocs build`, the `site/`
   directory can be opened directly via `file://` with no server; the plugin moves the search index to
   a JS file and disables `use_directory_urls` so the site works from the local filesystem (some
   Fetch-API features like instant loading must be disabled).
   [Source: Built-in offline plugin docs](https://squidfunk.github.io/mkdocs-material/plugins/offline/). **Support:** direct evidence. **Confidence:** high.

3. **Claim:** Material's built-in `privacy` plugin downloads external assets at build time so the
   documentation "can work without connectivity to the internet"; the offline docs present
   offline+privacy as the combination for "truly offline-capable documentation".
   [Source: Built-in offline plugin docs (privacy section)](https://squidfunk.github.io/mkdocs-material/plugins/offline/). **Support:** direct evidence. **Confidence:** high (see contradiction on Mermaid, Finding 4).

4. **Claim (with contradiction):** Material has native Mermaid support since 8.2.0 via
   `pymdownx.superfences` custom fences — the JS runtime auto-initializes on ` ```mermaid ` blocks —
   which covers the `docs/roadmap.md` DAG block. However, a project issue reports Mermaid not
   rendering when the network is unavailable, so whether Mermaid renders fully offline (bundled asset
   vs CDN fetch) must be settled by a 10-minute spike before committing.
   [Source: Diagrams reference](https://squidfunk.github.io/mkdocs-material/reference/diagrams/),
   [Source: Issue #3781 "Mermaid doesn't render when network is not available"](https://github.com/squidfunk/mkdocs-material/issues/3781). **Support:** direct evidence + unresolved contradiction. **Confidence:** high that Mermaid is supported; low that offline Mermaid works without the privacy plugin / build-time vendoring.

5. **Claim:** MkDocs/Material treat front matter as page *metadata* (title, description, tags,
   template), and the built-in `meta` plugin sets/merges folder-level `.meta.yml` metadata — but no
   surveyed feature renders arbitrary YAML front matter (e.g. `depends_on`, `self_hash`) as visible
   structured UI. That must be generated (e.g. the generator emits a metadata table into each page).
   [Source: Material reference (front matter)](https://squidfunk.github.io/mkdocs-material/reference/),
   [Source: Built-in meta plugin](https://squidfunk.github.io/mkdocs-material/plugins/meta/). **Support:** direct evidence for what exists; "no structured-UI for arbitrary YAML" is researcher inference from the documented feature set. **Confidence:** medium-high.

### Astro Starlight — best structured-front-matter candidate (Node lane)

6. **Claim:** `@astrojs/starlight` is actively maintained: latest release `@astrojs/starlight@0.42.6`
   dated 2026-10-08 on its release feed; license MIT (npm registry metadata).
   [Source: GitHub releases Atom feed](https://github.com/withastro/starlight/releases.atom),
   [Source: npm registry JSON](https://registry.npmjs.org/@astrojs/starlight). **Support:** direct evidence. **Confidence:** high.

7. **Claim:** Starlight loads docs through Astro content collections with a zod schema
   (`docsSchema()` in `src/content.config.ts`): front matter is typed, validated, and produces build
   errors for invalid entries — the closest surveyed analogue to doc-contract's strict front matter
   and frozen `self_hash`.
   [Source: Starlight frontmatter reference](https://starlight.astro.build/reference/frontmatter/),
   [Source: Content collections guide](https://docs.astro.build/en/guides/content-collections/),
   [Source: Starlight schema source](https://github.com/withastro/starlight/blob/main/packages/starlight/schema.ts). **Support:** direct evidence. **Confidence:** high.

8. **Claim:** Starlight is a full Astro/Node build with no equivalent of Material's `file://` offline
   plugin documented on its site; offline use would mean serving the built site from localhost.
   [Source: Starlight docs (manual setup / configuration)](https://starlight.astro.build/manual-setup/). **Support:** direct evidence of the build model; absence-of-offline-plugin is interpretation from the documented feature set. **Confidence:** medium.

### Sphinx/MyST — best cross-reference system, worst shape fit

9. **Claim:** Sphinx is `Production/Stable` on PyPI, supports Python 3.12–3.15, and is BSD-2-licensed
   (LICENSE.rst: "two clause BSD licence", copyright 2007–2026).
   [Source: PyPI JSON](https://pypi.org/pypi/Sphinx/json),
   [Source: Sphinx LICENSE.rst](https://github.com/sphinx-doc/sphinx/blob/master/LICENSE.rst). **Support:** direct evidence. **Confidence:** high.

10. **Claim:** Sphinx's genuine code-link machinery (`sphinx.ext.viewcode` — generates highlighted
    source pages and links them from object descriptions; `sphinx.ext.linkcode` — adds external links
    via a user-supplied `linkcode_resolve`) operates on *documented Python objects* (autodoc domains),
    not on arbitrary `path:line` strings inside prose. It does not solve doc-contract's bare-backtick
    code-ref problem, and MyST means converting the repo's Markdown idioms to Sphinx's model.
    [Source: sphinx.ext.viewcode docs](https://www.sphinx-doc.org/en/master/usage/extensions/viewcode.html),
    [Source: sphinx.ext.linkcode docs](https://www.sphinx-doc.org/en/master/usage/extensions/linkcode.html). **Support:** direct evidence; the "doesn't solve our problem" conclusion is researcher inference. **Confidence:** high on mechanism, medium on fit verdict.

### mdBook ecosystem — Rust single binaries, but link checker is stale

11. **Claim:** `mdbook-linkcheck` is effectively unmaintained: latest release v0.7.7 on 2022-10-03
    (release feed), latest crate 0.7.7 with `updated_at` 2022-10-03; MIT license.
    [Source: GitHub releases Atom feed](https://github.com/Michael-F-Bryan/mdbook-linkcheck/releases.atom),
    [Source: crates.io API](https://crates.io/api/v1/crates/mdbook-linkcheck),
    [Source: LICENSE](https://raw.githubusercontent.com/Michael-F-Bryan/mdbook-linkcheck/master/LICENSE). **Support:** direct evidence. **Confidence:** high.

12. **Claim:** `mdbook-mermaid` (Mermaid preprocessor for mdBook) is actively maintained — v0.17.1
    released 2026-08-14 — so a Rust-lane offline mdBook viewer for the DAG is plausible, but it still
    needs a bespoke front-matter/code-ref layer, and mdBook's own license was not verified this
    session (its `COPYRIGHT`/LICENSE raw fetch did not resolve).
    [Source: GitHub releases Atom feed](https://github.com/badboy/mdbook-mermaid/releases.atom). **Support:** direct evidence for maintenance; license unverified. **Confidence:** high (maintenance), low (licensing).

### ADR viewers — closest in artifact shape, too thin and too quiet

13. **Claim:** log4brains (ADR knowledge base with web UI and static-site export; Apache-2.0) is
    stale: latest npm dist-tag `latest` is 1.1.0 and its last GitHub release v1.1.0 was 2024-12-17 —
    roughly two years before the observed date. It assumes an `adr-tools`-style `docs/adr/` layout and
    its own ADR front matter, not one-folder-per-change with `depends_on`/`files_owned`. Judge: reject
    as a base; at most a UI reference.
    [Source: npm registry JSON](https://registry.npmjs.org/log4brains),
    [Source: GitHub releases Atom feed](https://github.com/thomvaill/log4brains/releases.atom),
    [Source: repo layout](https://github.com/thomvaill/log4brains). **Support:** direct evidence; the fit verdict is researcher inference. **Confidence:** high.

14. **Claim:** `adr-viewer` (PyPI, MIT) generates static HTML or serves a local web page from a
    directory of ADRs and renders Mermaid blocks in them; latest stable 1.4.0 uploaded 2024-04-21 with
    1.5.0rc1 on 2024-07-07 — slow, single-maintainer cadence. Built around adr-tools format (`--adr-path
    doc/adr/`), no graph view of dependencies. Judge: reject as a base.
    [Source: PyPI JSON](https://pypi.org/pypi/adr-viewer/json). **Support:** direct evidence; verdict is researcher inference. **Confidence:** high.

### Code references — the hard part, only partial coverage exists

15. **Claim:** lychee (Rust, single binary) is an actively maintained link checker: crate 0.24.2
    published 2026-05-01, license `Apache-2.0 OR MIT`, nightly builds running. It validates links
    (including local files) in Markdown — but doc-contract's second reference kind is bare backticked
    `path:line` *inline code*, which is not a Markdown link, so link checkers structurally do not
    cover it, and nothing surveyed validates line-number drift or not-yet-existing `files_owned` paths.
    [Source: crates.io API](https://crates.io/api/v1/crates/lychee),
    [Source: GitHub releases Atom feed](https://github.com/lycheeverse/lychee/releases.atom). **Support:** direct evidence for lychee's facts; the "backticked refs are out of scope" claim is researcher inference from lychee's description as a link checker and would need a small spike to confirm. **Confidence:** high (facts), medium (scope claim).

16. **Claim:** `vscode://file/{full path to file}:line:column` is a documented VS Code URL scheme for
    opening a file at a specific line/column (Insiders: `vscode-insiders://`); it expects an absolute
    path. This is the practical mechanism for a generated viewer to turn `src/doc_contract/resolver.py:1102`
    into a one-click jump in the developer's editor without shipping a code viewer.
    [Source: VS Code CLI docs, "Opening VS Code with URLs"](https://code.visualstudio.com/docs/editor/command-line). **Support:** direct evidence. **Confidence:** high.

17. **Claim:** Markdown LSPs are alive and useful for *editing* but are not front ends: Marksman
    (single Rust binary; release dated 2026-02-08) and markdown-oxide (v0.25.12, 2026-06-29) provide
    wiki-link/reference intelligence inside editors; note the crate named `marksman` on crates.io is
    an unrelated 2015 name-squatter (v0.0.1 "Reserved name for HTML builder") and `markdown-oxide` is
    not published on crates.io under that name — both distribute via GitHub releases.
    [Source: Marksman releases](https://github.com/artempyanykh/marksman/releases.atom),
    [Source: markdown-oxide releases](https://github.com/Feel-ix-343/markdown-oxide/releases.atom),
    [Source: crates.io API (marksman)](https://crates.io/api/v1/crates/marksman),
    [Source: crates.io API (markdown-oxide)](https://crates.io/api/v1/crates/markdown-oxide). **Support:** direct evidence. **Confidence:** high.

### Other candidates — weighed and mostly rejected

18. **Claim:** Docusaurus supports Mermaid via the separate `@docusaurus/theme-mermaid` package plus
    `markdown.mermaid: true`, and is MIT-licensed — but it is a heavy Node build with no `file://`
    offline mode; reject for this use.
    [Source: Docusaurus diagrams docs](https://docusaurus.io/docs/markdown-features/diagrams),
    [Source: LICENSE](https://raw.githubusercontent.com/facebook/docusaurus/main/LICENSE). **Support:** direct evidence; verdict is inference. **Confidence:** high.

19. **Claim:** VitePress is mature (npm latest 1.6.4, MIT, with a `2.0.0-alpha` line in progress) but
    like Docusaurus is a dev-server/SSG with no documented offline `file://` mode; reject in favor of
    Material unless the team prefers Node.
    [Source: npm registry JSON](https://registry.npmjs.org/vitepress),
    [Source: LICENSE](https://raw.githubusercontent.com/vuejs/vitepress/main/LICENSE). **Support:** direct evidence; verdict is inference. **Confidence:** high.

20. **Claim:** Docsify is a zero-build client-side SPA whose docs' own starter template loads core
    assets from the jsDelivr CDN and is previewed via `docsify serve` — i.e., runtime fetching plus a
    local server, contradicting this repo's offline-first constraint; reject.
    [Source: Docsify quickstart docs](https://docsifyjs.github.io/docsify/#/quickstart) (fetched as repo source: docsifyjs/docsify `docs/quickstart.md`). **Support:** direct evidence; verdict is inference. **Confidence:** high.

21. **Claim:** Quarto has native Mermaid and Graphviz support, but print-format rendering depends on
    Chrome/Edge, and whether Mermaid renders offline in HTML output after install was not verified;
    its pandoc-based weight is out of proportion for a change-item viewer. Reject pending a spike.
    [Source: Quarto diagrams docs](https://quarto.org/docs/authoring/diagrams.html). **Support:** direct evidence for mermaid support; offline behavior unverified. **Confidence:** medium.

22. **Claim:** Zensical (from the Material team's org) exists but is pre-alpha: its own site is
    generated by `zensical-0.0.70` (0.0.x) per the page's generator meta tag. Not adoptable now; worth
    re-checking in a year.
    [Source: zensical.org (generator meta tag)](https://zensical.org/). **Support:** direct evidence of version; "pre-alpha" is interpretation of the 0.0.x version. **Confidence:** medium.

23. **Claim (gap, cross-cutting):** No surveyed project's selling point is "browse a
    change/decision-record graph with dependency edges from front matter." log4brains renders ADR
    links/status, adr-viewer renders pages, MkDocs/Starlight render trees; the `depends_on` DAG view
    must be generated (the roadmap's Mermaid DAG already encodes it, so the cheapest path is rendering
    that, not building a new graph model).
    [Source: researcher inference across the sources above]. **Support:** researcher inference (negative claim — absence). **Confidence:** medium-high.

## pi-web as host (candidate — not yet adopted)

The user is **evaluating** `jmfederico/pi-web` (a local agent-session web UI, TypeScript/Vite/Node)
and is not committed to it. This section therefore answers one question conditionally: *if* pi-web is
adopted, what does it already give a doc-contract viewer, and what must still be built? All claims
below were verified by reading the cited source files on `main` this session. The standalone MkDocs
recommendation above is unchanged by this section.

24. **Claim:** pi-web is MIT-licensed (LICENSE: "Copyright (c) 2026 Federico Jaramillo Martinez").
    Its maturity is hard to certify: I found no release feed/version evidence this session (see open
    questions); treat it as a personal project under active development.
    [Source: LICENSE](https://github.com/jmfederico/pi-web/blob/main/LICENSE). **Support:** direct evidence for license; maturity is researcher assessment. **Confidence:** high (license), low (maturity).

25. **Claim:** Two pi-web surfaces render repo Markdown with workspace-aware link rewriting today:
    (a) chat messages, via the app renderer in `src/client/src/formatting/markdown.ts` — marked
    (`gfm: true, breaks: true`), then a sanitizer that, for every anchor whose `href` resolves via
    `workspaceMarkdownFilePath(href, workspace)`, rewrites it to `workspaceFilePreviewUrl(...)` with a
    `data-workspace-file` attribute and `target="_self"` (other links get `target="_blank"`); and
    (b) the Files viewer — the plugin capability table documents "Preview diagrams or other text
    formats in chat and Files → Browser content renderers".
    [Source: src/client/src/formatting/markdown.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/markdown.ts),
    [Source: docs/plugins.md capability table](https://github.com/jmfederico/pi-web/blob/main/docs/plugins.md). **Support:** direct evidence. **Confidence:** high.

26. **Claim:** Link rewriting covers doc-contract's inter-doc Markdown links but not its bare
    backticked paths, and directory links are rewritten without a file-existence check:
    `workspaceMarkdownFilePath` accepts any relative href and any workspace-root-absolute path,
    normalizes dot segments, rejects schemes/`#`/`?`/`//`/backslashes, and explicitly says
    "Classification only: filesystem containment and symlink checks belong to the server" — so a
    directory link like `docs/changes/<id>/` **is** rewritten to a preview URL, but whether the Files
    preview degrades gracefully on a directory (vs erroring) is unverified. Bare backticked
    `` `docs/roadmap.md` `` produces no `<a>` at all, so it is never rewritten and does not navigate.
    [Source: src/client/src/formatting/workspaceLinks.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/workspaceLinks.ts). **Support:** direct evidence for the rewrite rules; directory-preview behavior unverified. **Confidence:** high (rules), low (directory behavior).

27. **Claim:** Nothing in pi-web resolves or links code references: reading
    `markdown.ts`, `contentRendering.ts`, and `workspaceLinks.ts` end-to-end found no line-number
    handling (no `#L`, `:line`, `lineNumber`, or reveal logic) — this **confirms** the steering
    observation. Code *blocks* (fences) go through plugin content renderers matched by language or
    file extension (`contentRenderers.ts`), capped at `MAX_CONTENT_RENDERER_LENGTH = 100_000`, but a
    content renderer only receives code-block text — it cannot see document position, so it cannot
    turn inline backtick refs into links. To support `src/doc_contract/resolver.py:1102` a doc-contract
    plugin would need a workspace panel that parses refs from the rendered document and opens files
    through host file helpers; whether those helpers expose an "open at line" behavior (vs plain read)
    was not verifiable from the files fetched this session (spike).
    [Source: src/client/src/formatting/markdown.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/markdown.ts),
    [Source: src/client/src/formatting/contentRendering.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/contentRendering.ts),
    [Source: src/client/src/plugins/contentRenderers.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/plugins/contentRenderers.ts). **Support:** direct evidence (absence verified by full read); the plugin design conclusion is researcher inference. **Confidence:** high (absence of line handling), medium (plugin design).

28. **Claim:** The `relay` system is a poor fit for doc-contract and would need a new workspace panel
    instead: relays discover documents under `.pi-web/relays` with anchor docs `["status.md",
    "charter.md", "operations.md", "log.md"]`, caps `MAX_RELAY_DOCUMENTS = 200` / depth 5, and their
    document viewer (`markdownDocument.ts`) renders `.md` through a **vendored**
    `vendor/marked.esm.js` with safety rules explicitly duplicated from the app renderer ("the plugin
    cannot import that module, so the rules are duplicated here") — and unlike the app renderer, it
    performs **no workspace link rewriting** (relative hrefs would not navigate to workspace files).
    So a thin relay adapter could list change folders, but rendered change items would have dead
    inter-doc links, no front-matter UI, and no `depends_on` graph. The honest answer is a
    doc-contract workspace panel using host file helpers plus the app-style renderer behavior.
    [Source: pi-packages/relays/relayDiscovery.ts](https://github.com/jmfederico/pi-web/blob/main/pi-packages/relays/relayDiscovery.ts),
    [Source: pi-packages/relays/markdownDocument.ts](https://github.com/jmfederico/pi-web/blob/main/pi-packages/relays/markdownDocument.ts),
    [Source: pi-packages/relays/relaysPanelElement.ts](https://github.com/jmfederico/pi-web/blob/main/pi-packages/relays/relaysPanelElement.ts). **Support:** direct evidence; fit verdict is researcher inference. **Confidence:** high.

29. **Claim:** Nothing in the fetched pi-web sources parses YAML front matter or builds a dependency
    graph: the app renderer escapes raw HTML and does no front-matter special-casing (marked would
    render `---`-delimited YAML as visible body text — a change item rendered as-is would show its
    `self_hash` blob as junk), and no fetched module models `depends_on`. Front matter as structured
    UI and any DAG view are build items for a plugin.
    [Source: src/client/src/formatting/markdown.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/markdown.ts),
    [Source: pi-packages/relays/markdownDocument.ts](https://github.com/jmfederico/pi-web/blob/main/pi-packages/relays/markdownDocument.ts). **Support:** direct evidence of absence in fetched sources (negative claim). **Confidence:** medium-high.

30. **Claim:** The roadmap DAG is already covered offline if pi-web is adopted: a bundled
    `pi-web-plugins/mermaid` plugin exists whose engine imports `mermaid` and `dompurify` as bundled
    dependencies ("Built as one IIFE, executed only inside an opaque-origin sandbox frame"), runs
    `mermaid.render` with `securityLevel: "strict"`, `maxTextSize: 100_000`, `maxEdges: 500`, and
    sanitizes the SVG — no CDN, so offline-capable once installed. `maxEdges: 500` is comfortably
    above a change-graph scale but worth knowing.
    [Source: pi-web-plugins/mermaid/mermaid-engine.ts](https://github.com/jmfederico/pi-web/blob/main/pi-web-plugins/mermaid/mermaid-engine.ts),
    [Source: pi-web-plugins/mermaid/package.json](https://github.com/jmfederico/pi-web/blob/main/pi-web-plugins/mermaid/package.json). **Support:** direct evidence. **Confidence:** high.

31. **Claim:** External plugins are a supported extension point (no fork), with an explicit
    stability/versioning story: plugins are declared in `package.json` under `piWeb.plugins`
    (browser/server entries), installed and enabled via Settings, with recovery via
    `pi-web plugins safe-start` modes; the docs say to "Use only the public package entrypoints.
    Internal routes, services, and `dist/**` imports are not supported APIs"; capability contracts are
    versioned (`content-rendering` capability is `version: 1` in `contentRendering.ts`; docs state
    "Browser API v4 remains unchanged" and describe server API v3/v5 lineages); bundled plugin
    contributions are exercised in `pi-web-plugins/pluginPublicApi.test.ts`. Unknown: whether a
    browser plugin can invoke the host's `content-rendering` capability (which exposes
    `renderMarkdown` with workspace link rewriting) from a panel — that would avoid duplicating the
    renderer, and needs a spike.
    [Source: docs/plugins.md](https://github.com/jmfederico/pi-web/blob/main/docs/plugins.md),
    [Source: src/client/src/formatting/contentRendering.ts](https://github.com/jmfederico/pi-web/blob/main/src/client/src/formatting/contentRendering.ts),
    [Source: pi-web-plugins/pluginPublicApi.test.ts](https://github.com/jmfederico/pi-web/blob/main/pi-web-plugins/pluginPublicApi.test.ts). **Support:** direct evidence; the open capability question is flagged, not resolved. **Confidence:** high.

**If pi-web is adopted — built in vs to build:**
- Built in: Markdown rendering with GFM (chat + Files), workspace-relative Markdown link rewriting
  and navigation (Findings 25–26), offline Mermaid diagram rendering (Finding 30), file
  listing/reading helpers, external plugin installation and safe-start recovery (Finding 31).
- To build (doc-contract plugin): change-folder discovery (`docs/changes/**` + archive), YAML
  front-matter parsing and structured UI, `depends_on` graph view, backticked `path:line` →
  navigable/open-at-line behavior (host helper support unverified), `files_owned` existence markers,
  handling of the generated `docs/roadmap.md` DAG block, and possibly its own renderer if the host
  content-rendering capability is not callable from panels (the relay precedent shows the duplication
  cost is real — Finding 28).
- Adoption does **not** change doc-contract's shipped-runtime invariants: pi-web is a Node/browser
  dev-time host; a doc-contract plugin lives in pi-web's plugin/package world, not in
  `pyproject.toml`. `dependencies = []`, the stdlib-only resolver, offline CLI mode, `sync` vendoring,
  and the optional-project-check seam are all untouched — the plugin is dev-time tooling, exactly like
  the MkDocs lane. (The plugin's *server entry* runs in pi-web's session daemon with full
  filesystem/process permissions per the trust docs — irrelevant to the Python package, but do not
  put anything there that must be stdlib-pure.)

## Comparison

| Candidate | Maturity / maintenance (observed) | Runtime needed | Offline-capable? | Inter-doc links | Code references | Front matter as structured UI | License | How consumed here |
|---|---|---|---|---|---|---|---|---|
| Material for MkDocs 9.7.7 | Production/Stable, release 2026-07-28 | Python (build-time, venv/uv) | Yes — built-in `offline` (+`privacy`) plugins, `file://` | Rewrites/validates relative links at build | None for backtick `path:line`; plugins exist for external repos | No (metadata only) — generate tables | MIT | **Bootstrap** (dev-time lane) |
| Astro Starlight 0.42.6 | Very active, release 2026-10-08 | Node/Astro (build-time) | Not turnkey; serve built site locally | Relative link validation in build | No backtick-path handling | **Yes** — validated zod schema per collection | MIT | **Bootstrap** (Node lane alternative) |
| Sphinx + MyST | Production/Stable; Py 3.12–3.15 | Python (build-time) | Yes (static output); offline story fine | `:doc:`/`:ref:`/intersphinx (needs MyST conversion) | `viewcode`/`linkcode` for documented objects only | No | BSD-2 | Reject (idiom mismatch, conversion cost) |
| mdBook (+mdbook-linkcheck, mdbook-mermaid) | mermaid preprocessor active (2026-08); linkcheck dead since 2022 | Rust toolchain | Yes (static HTML) | linkcheck validates links (stale) | No backtick-path handling | No | linkcheck MIT; mdBook unverified | Reject (linkcheck stale; thin ecosystem) |
| Docusaurus v3 | Active (Meta) | Node | No `file://` mode | Build-time link checking exists | No | No | MIT | Reject (weight) |
| VitePress 1.6.4 | Active | Node | No `file://` mode documented | Vue-router relative links | No | No | MIT | Reject (weight) |
| Docsify 5 | Active | Any (client SPA) | No — runtime fetch + CDN + `serve` | Runtime fetch | No | No | (not verified this session) | Reject (offline constraint) |
| Quarto | Active (Posit) | Quarto/pandoc | Unverified for mermaid HTML | Pandoc crossrefs | No | No | GPL-2 (pandoc bundling; not re-verified) | Reject pending spike |
| Zensical | Pre-alpha (0.0.70 generator) | Python/Node (unclear) | Unknown | Unknown | Unknown | Unknown | Unknown | Reject now, re-check later |
| log4brains 1.1.0 | Stale: last release 2024-12-17 | Node | Static export yes | ADR link resolver (adr-tools format) | No | ADR status/supersedes only | Apache-2.0 | Reject as base; UI reference |
| adr-viewer 1.4.0/1.5.0rc1 | Slow, single maintainer (2024) | Python | Static HTML yes | None (flat list) | No | adr-tools status only | MIT | Reject |
| lychee 0.24.2 | Active (2026-05, nightlies) | None (Rust binary) | Yes (CLI) | Validates *links* incl. local files | No (backtick refs not links — verify via spike) | n/a | Apache-2.0 OR MIT | **Use as checker** alongside generator |
| Marksman / markdown-oxide | Active (2026 releases) | Editor + LSP | n/a (editor-side) | Wiki/ref resolution | Editor-grade, not viewer | n/a | (not verified) | Reject for viewer; useful while editing |
| pi-web (jmfederico) | Under evaluation by user; no release evidence verified this session | Node/TS app + browser | Yes (local app; mermaid bundled in plugin, no CDN) | Chat/Files rewrite workspace-relative links (`_self` nav); relay docs do NOT rewrite; backtick refs not links | None — no line-number handling; no path:line resolution | No — build item for a plugin | MIT | **Conditional host** — plugin if adopted; standalone path unaffected |

## Recommendation

**Two explicit lanes (this is the key architectural decision, driven by repo constraints a–d):**

**Default lane — standalone dev-time viewer (recommended regardless of pi-web).** A separate
`uv`-managed venv/Node build that never appears in `pyproject.toml` (`dependencies = []` stays
frozen), never runs under `check --offline`, and is never vendored by `sync` into `.doc-contract/`.
Concretely:

1. **Reuse Material for MkDocs** for rendering, search, theming, Mermaid, and the offline `file://`
   build (Findings 1–4). Run `mkdocs build` with `offline` + `privacy` plugins; commit-free output
   goes to a git-ignored `.doc-contract-site/` (or `site/`) and opens via `index.html`.
2. **Build thin doc-contract glue** (the part nothing provides): a generator script (stdlib-only is
   *not* required for this lane — it runs in the dev venv) that walks
   `docs/changes/**/change.md` + companion files, parses the YAML front matter with PyYAML (dev-time
   dep, fine), injects a metadata panel (status, track, persistence, `depends_on` links,
   `files_owned` list with existence check) into each page; converts bare backticked `path[:line]`
   refs into links — inter-doc refs to real files become relative MkDocs links; code refs become
   `vscode://file/<abs>:<line>` deep links (Finding 16); missing `files_owned` targets render as a
   visible "not yet created" marker; copies/renders the roadmap DAG block as Mermaid with
   `DAG_BEGIN/DAG_END` sentinels stripped.
3. **Add lychee** (single Rust binary, Finding 15) in CI/dev to catch broken inter-doc links; accept
   that backtick code-ref validation must be part of the generator (and may later justify a
   doc-contract CLI check, since `self_hash`/`files_owned` semantics already live there).

**Reuse vs build split:** reuse ~everything presentation-related from Material (renderer, offline
story, mermaid, search — the 80% you should never write); build ~all doc-contract semantics
(folder discovery, front-matter UI, code-ref linking, staleness — the 20% no project covers).

**Conditional lane — pi-web host (only if the user adopts pi-web):** the same thin doc-contract glue
is re-expressed as a pi-web plugin (workspace panel) instead of a generated static site. What changes:
link navigation and Mermaid come from the host instead of Material (Findings 25, 30); what does not
change: front-matter UI, code-ref resolution, and graph views are still built by us (Findings 27, 29),
and doc-contract's shipped-runtime invariants (`dependencies = []`, stdlib-only, offline CLI, `sync`
vendoring, live-pass-only extension seam) are untouched either way. Decision guidance: pi-web gives a
live, watchable viewer (panels refresh when workspace files change — per its plugin docs) but requires
buying into its plugin model and its renderer-duplication constraints; the MkDocs lane gives a
zero-server `file://` artifact that works even if pi-web evaluation ends in "no". The two are not
mutually exclusive; do not block the standalone lane on the pi-web evaluation.

## Open questions and residual uncertainty

- **pi-web is still being tested by the user** — this section is conditional by design. Hands-on
  spikes needed before counting on it: (a) does clicking a *directory* link
  (`docs/changes/<id>/`) in chat/Files preview open something sensible or error (Finding 26)?
  (b) can a browser plugin panel invoke the host `content-rendering` capability to get workspace-link
  rewriting without duplicating the renderer (relay's duplicated safety rules show the cost)?
  (c) do host file helpers support "open at line" semantics for `path:line` refs, or must the plugin
  render code itself (Finding 27)? (d) pi-web release/version and maintenance cadence were not
  verifiable this session — establish them before treating it as a stable host.
- **Mermaid offline under Material (blocking for the DAG view):** docs claim offline+privacy yields a
  site that "can work without connectivity", but issue #3781 reports Mermaid failing with no network.
  Needs a 10-minute spike: build a Material site with a Mermaid block, `offline`+`privacy` plugins,
  and load it with networking disabled. (By contrast, pi-web's mermaid plugin is verified bundled/offline.)
- **lychee vs backticked refs:** my claim that inline-code `path:line` refs are out of scope for
  lychee is inference from its being a link checker; a spike with a sample file would confirm or
  falsify it.
- **Unverified licenses/versions:** mdBook's license, Docsify's license/version date, Quarto's offline
  Mermaid behavior. None change the recommendation (all reject-lane), but don't cite without re-checking.
- **Zensical:** confirmed to exist (zensical.org, generator `0.0.70`) but its docs/repository could
  not be fetched this session; capabilities unknown. Re-evaluate later.
- **Could not confirm any "doc-graph viewer":** no project found (and existence not ruled out) that
  renders front-matter dependency graphs generically; the MkDocs plugin ecosystem was not exhaustively
  enumerated. If a `depends_on`-graph MkDocs plugin exists, it would reduce Lane-1 glue further.
- **Observed dates use this session's clock**, which reads as late 2026 in the fetched feeds; treat
  relative staleness rather than absolute dates as the signal.

## Sources

Kept (primary, verified this session):
- Material for MkDocs: offline plugin docs, diagrams reference, meta plugin, reference/front matter, releases Atom feed, PyPI JSON
- Astro Starlight: frontmatter/config/manual-setup docs, content collections guide, schema.ts, releases Atom feed, npm JSON
- Sphinx: viewcode/linkcode docs, LICENSE.rst, PyPI JSON
- lychee, mdbook-linkcheck, mdbook-mermaid, marksman, markdown-oxide, log4brains: releases Atom feeds + crates.io/npm/PyPI registry JSON
- adr-viewer: PyPI JSON (description incl. Mermaid/serve usage)
- Docusaurus diagrams docs + LICENSE; VitePress npm JSON + LICENSE; Docsify quickstart (repo source); Quarto diagrams docs; VS Code `vscode://file` CLI docs
- pi-web: `docs/plugins.md`, `src/client/src/formatting/{markdown,workspaceLinks,contentRendering}.ts`, `src/client/src/plugins/contentRenderers.ts`, `pi-packages/relays/{markdownDocument,relayDiscovery}.ts`, `pi-web-plugins/mermaid/{mermaid-engine.ts,package.json}`, LICENSE (all on `main`, fetched this session)

Rejected/deprioritized:
- Search-engine summaries and blog posts (unavailable/untrusted this session)
- GitHub REST API (rate-limited) — replaced by releases.atom feeds and registry JSON
- Structurizr, GitHub Projects/wiki — judged not applicable to repo-local offline change-item viewing (interpretation; not individually verified)

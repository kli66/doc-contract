# Research: AST-aware change tickets (chunk-level scope and verification)

Deliverable: `docs/research/ast-aware-change-tickets-research.md`. This directory is outside the
change graph (`doc-contract` mints nodes only for `docs/changes/**/*.md`, `docs/adr/NNNN-*.md`,
`docs/spec/*.md`, `docs/archive/**`, and the root nodes in `.doc-contract.toml`), so this file is not
a managed document and cannot affect preflight.

Research date: 2026-10 (session clock; the newest primary-source timestamps observed in this session
are 2026-10-16, e.g. the tree-sitter nightly feed). **Evidence rule used:** every capability claim
below links a primary source — protocol/spec pages, repository source files, LICENSE text, release
Atom feeds, registry JSON, tool manuals, or the paper's own DOI/abstract page. Search-engine snippets
were used only to locate primary URLs and are never the support for a decision-relevant claim. Where
I could not reach a primary source, the claim is in **§9 Unverified / needs a spike**, not in the
findings.

**Search-tool caveat (disclosed):** most configured search providers were unavailable this session
(Brave/Tavily/Exa rejected with missing-key/rate-limit errors; a keyless provider plus one working
provider carried the discovery work). Following the precedent of
`docs/research/doc-contract-frontend-research.md`, verification was therefore done by **fetching raw
primary sources directly** (GitHub `releases.atom`, `raw.githubusercontent.com` files, PyPI JSON,
tool manual pages, vendor protocol docs). Quotes below are from those fetches.

## Summary

**Nothing surveyed can be adopted unmodified as a chunk-scope verifier, and no system anywhere was
found that verifies either direction (every declared chunk was touched / every changed chunk was
declared).** The mature infrastructure that exists serves *other* problems: symbol-identity protocols
(SCIP/LSIF/Kythe/LSP monikers) are explicitly read-only navigation formats — SCIP's own design doc
lists "support use cases involving code modifications" as a **non-goal** — and AST-diff tools
(GumTree, RefactoringMiner, difftastic, ast-grep) compute *what changed*, not *what was allowed to
change* or *what was supposed to change*.

**What is adoptable unmodified is components, not a solution:** Python's stdlib `ast` (+ `tokenize`,
`difflib`) for a zero-dependency Python-first extractor; `git` plumbing for the baseline; a dev-time
structural differ (ast-grep or difftastic) for human-facing summaries; and the *design conventions* of
SCIP's qualified-symbol grammar and of CI "new code / baseline ref / new findings only" semantics.
The verify logic itself is small and must be in-house.

**Recommendation in one line:** adopt nothing as a runtime dependency; build a ~200–400 line
stdlib-only, advisory-first chunk-scope check (declared chunks as `path::qualified.name` strings in
front matter, re-resolved per revision) that answers coverage by *per-chunk before/after AST equality*
rather than by full AST-diffing, with recorded-revision baseline and a mandatory tool-written-file
exemption list; keep a dev-time structural differ purely for the human diff summary. The runner-up —
keep file-level scope plus a machine-checked diff summary and stop there — wins if declared chunk
names turn out to drift faster than they inform.

**Addendum (2026-10-16):** one further design — edit-time provenance — is recorded in the final
section. It does not change the recommendation.

## Findings

1. **Claim:** No surveyed system verifies declared-vs-actual chunk scope in either direction. SCIP's
   design doc puts code modification out of scope; LSIF is deprecated and removed at Sourcegraph; LSP
   `textDocument/documentSymbol` returns names and ranges but no identity; CODEOWNERS in GitHub and
   GitLab is path-pattern-only; `diff-cover`/Codecov patch coverage, SonarQube new-code gates, and
   Semgrep diff-aware scans all quantify over *lines/files/new-findings*, never over *declared
   symbols*. [Source: SCIP DESIGN.md](https://raw.githubusercontent.com/sourcegraph/scip/main/docs/DESIGN.md),
   [Source: LSP 3.17 documentSymbol](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/language/documentSymbol.md),
   [Source: GitHub CODEOWNERS docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners),
   [Source: GitLab CODEOWNERS syntax](https://docs.gitlab.com/user/project/codeowners/reference/),
   [Source: diff-cover README](https://raw.githubusercontent.com/Bachmann1234/diff_cover/master/README.rst),
   [Source: SonarQube new code](https://docs.sonarsource.com/sonarqube-server/9.8/user-guide/clean-as-you-code),
   [Source: Semgrep diff-aware scans](https://docs.semgrep.dev/kb/semgrep-ci/trigger-diff-scans-env-var).
   **Support:** interpretation (a negative claim assembled from the documented feature sets above; this
   is not a proof of absence — see §9). **Confidence:** medium-high.

2. **Claim:** Python's stdlib is sufficient for a Python-first extractor at zero dependency cost:
   `ast.expr`/`ast.stmt` subclasses carry `lineno`, `col_offset`, `end_lineno`, `end_col_offset`, and
   `ast.get_source_segment()` returns a node's source text; the docs also warn that "the end positions
   are not required by the compiler and are therefore optional". [Source: Python `ast` docs](https://docs.python.org/3/library/ast.html).
   **Support:** direct evidence. **Confidence:** high. **Inference (researcher):** because end
   positions are optional and there is no public "node at position" API, any implementation must walk
   the tree and decide its own containment rule rather than relying on a stdlib range lookup.

3. **Claim:** Declaration-level chunks (qualified names) are the only chunk unit an *authoring agent*
   can name durably: LSP's `DocumentSymbol` offers exactly one name-like field (`name`, must be
   non-empty) plus two ranges, and the spec says the `SymbolInformation` range "doesn't have to denote
   a node range in the sense of an abstract syntax tree" and "can't be used to re-infer a hierarchy".
   [Source: LSP 3.17 documentSymbol](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/language/documentSymbol.md).
   **Support:** direct evidence for the spec text; the "only writable unit" conclusion is researcher
   inference. **Confidence:** high (quotes), medium (inference).

4. **Claim:** Qualified names are the identity scheme with the smallest practical drift surface, but
   no protocol guarantees stability: Kythe states a VName `signature` "should be consistently generated
   given the same input to the indexer, but that does not necessarily need to be stable across
   different versions of the input"; LSIF's moniker `identifier` "is opaque in LSIF" and its
   `UniquenessLevel` describes *uniqueness* (`document`…`global`), never stability across revisions;
   LSP's moniker request only says servers "should ensure that the moniker calculation matches to those
   used in the corresponding LSIF implementation". [Source: Kythe schema reference](https://www.kythe.io/docs/schema/),
   [Source: LSIF protocol.ts](https://raw.githubusercontent.com/microsoft/lsif-node/main/protocol/src/protocol.ts),
   [Source: LSP 3.17 moniker](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/language/moniker.md).
   **Support:** direct evidence. **Confidence:** high.

5. **Claim:** Two opposite identity designs bound the trade-off. Content addressing (Unison: "Each
   Unison definition is identified by a hash of its syntax tree… names are just separately stored
   metadata that don't affect the function's hash") is perfectly rename/move-proof but *breaks on every
   edit* — useless as "this chunk changed" identity. A recorded revision with a stable logical id
   (Jujutsu: "Rewriting a commit results in a new commit, and thus a new commit ID, but the change ID
   generally remains the same") is the closest analogue to `change.md`'s id mapping onto a revision.
   [Source: Unison "the big idea"](https://www.unison-lang.org/docs/the-big-idea/),
   [Source: jj glossary](https://jj-vcs.github.io/jj/latest/glossary/). **Support:** direct evidence;
   the "analogue to change.md" mapping is researcher inference. **Confidence:** high.

6. **Claim (anchor drift is the top risk):** Yes — three independent primary docs remove the
   guarantees a span/index-based chunk name would need. Python AST end positions are optional (Finding
   2); LSP symbol ranges need not be AST node ranges and there is no symbol id (Finding 3); Kythe
   explicitly refuses stability for signatures across versions (Finding 4). So a chunk declared as a
   line span or node index must be re-resolved against every revision, and silent drift is the default
   failure mode. [Sources as above.] **Support:** interpretation over direct evidence. **Confidence:**
   medium-high.

7. **Claim:** In comparable systems the baseline is always a *recorded commit or commit pair*, never a
   date or the dirty worktree. `diff-cover` "compares the current branch to `origin/main`" and uses
   "the `...` git diff range notation by default (changes on the current branch since it diverged from
   the compare branch)"; Semgrep diff-aware scans require `SEMGREP_PR_ID` + `SEMGREP_BASELINE_REF` and
   "only report findings newly introduced in the commits after that baseline"; Codecov compares a base
   and head commit and can require both reports; SonarQube's "new code" is defined by releases, a
   number of days, or "For pull requests, all new or changed lines are considered new code".
   [Source: diff-cover README](https://raw.githubusercontent.com/Bachmann1234/diff_cover/master/README.rst),
   [Source: Semgrep diff-aware](https://docs.semgrep.dev/kb/semgrep-ci/trigger-diff-scans-env-var),
   [Source: Codecov PR comments](https://docs.codecov.com/docs/pull-request-comments),
   [Source: SonarQube new code](https://docs.sonarsource.com/sonarqube-server/9.8/user-guide/clean-as-you-code).
   **Support:** direct evidence. **Confidence:** high.
   **Inference (researcher):** because `doc-contract` records only a date at accept/begin, **no
   comparable baseline is currently available**; a chunk check therefore has three honest choices —
   record a revision at accept/begin (new lifecycle field), use merge-base against the default branch
   as an *implicit* baseline (accepting unrelated in-flight edits in the verdict), or refuse to run and
   emit an advisory "no baseline" instead of a verdict.

8. **Claim:** Moves, renames and formatting are exactly where AST-diff engines earn their cost, and
   they are mature: GumTree's README states its two advantages are that "edit actions are always
   aligned with the syntax" and that "it can detect moved or renamed elements in addition of deleted
   and inserted code" (supported languages: C, Java, JavaScript, Python, R, Ruby; LGPL-3.0; nightly
   distribution updated 2026-10-12); RefactoringMiner (MIT, v3.1.6, 2026-09-16) reports refactoring
   types at method/field/class granularity including Rename/Move/Merge and now ships AST diff for Java,
   Python, Kotlin, JS/TS and C/C++.
   [Source: GumTree README](https://raw.githubusercontent.com/GumTreeDiff/gumtree/master/README.md),
   [Source: GumTree releases feed](https://github.com/GumTreeDiff/gumtree/releases.atom),
   [Source: GumTree LICENSE](https://raw.githubusercontent.com/GumTreeDiff/gumtree/master/LICENSE),
   [Source: RefactoringMiner README](https://raw.githubusercontent.com/tsantalis/RefactoringMiner/master/README.md),
   [Source: RefactoringMiner releases feed](https://github.com/tsantalis/RefactoringMiner/releases.atom),
   [Source: RefactoringMiner LICENSE](https://raw.githubusercontent.com/tsantalis/RefactoringMiner/master/LICENSE).
   **Support:** direct evidence. **Confidence:** high. **Adoption delta:** both are JVM tools invoked as
   a separate process; neither knows our ticket model, so we would still build the declaration parsing,
   the name mapping, the baseline, the exemption list and the two verdicts.

9. **Claim:** AST-editing platforms exist but are language-JVM-shaped and forbid a stdlib lane:
   OpenRewrite's LST is "type-attributed" and "format-preserving" yet "must fit into memory" and is
   regenerated per run (nothing stored between runs); LibCST is MIT and parses "Python 3.0 -> 3.15"
   keeping "all formatting details", but ships a native extension (Rust toolchain needed when no wheel
   matches) and lists "Advanced full repository facts providers like fully qualified name and call
   graph" under **Future** — i.e. it has no qualified names today.
   [Source: OpenRewrite LST docs](https://docs.openrewrite.org/concepts-and-explanations/lossless-semantic-trees),
   [Source: LibCST README](https://raw.githubusercontent.com/Instagram/LibCST/main/README.rst).
   **Support:** direct evidence. **Confidence:** high. **Adoption delta:** dev-lane only; LibCST would
   be the right tool if we later want format-preserving *rewrites*, not for verification.

10. **Claim:** A dev-time structural-search CLI is the cheapest way to (a) let the authoring agent
    enumerate candidate chunks and (b) give humans a syntax-aware diff. ast-grep is MIT (v0.51.0,
    2026-10-15), offline, single-binary, supports 27 languages with Python among them, and its rules are
    YAML with `pattern`/`has`/`stopBy` primitives plus `--inline-rules` for one-shot queries.
    [Source: ast-grep rule essentials](https://ast-grep.github.io/guide/rule-config.html),
    [Source: ast-grep languages](https://ast-grep.github.io/reference/languages.html),
    [Source: ast-grep LICENSE](https://raw.githubusercontent.com/ast-grep/ast-grep/main/LICENSE),
    [Source: ast-grep releases feed](https://github.com/ast-grep/ast-grep/releases.atom).
    **Support:** direct evidence. **Confidence:** high. **Adoption delta:** it answers "where does this
    pattern occur", so it can validate *that a chunk name resolves*, not *that it was the only thing
    changed*; the two verdicts remain ours.

11. **Claim:** difftastic is a human-display tool by design, not a checker: it "will ignore whitespace
    that isn't syntactically significant", its output "is intended for human consumption, and it does
    not generate patches that you can apply later", and it is MIT with vendored tree-sitter parsers.
    [Source: difftastic README](https://raw.githubusercontent.com/Wilfred/difftastic/master/README.md),
    [Source: difftastic releases feed](https://github.com/Wilfred/difftastic/releases.atom) (0.71.0,
    2026-09-18). **Support:** direct evidence. **Confidence:** high.

12. **Claim (whitespace/comments — comparable behaviour differs):** difftastic suppresses
    non-syntactic whitespace changes (Finding 11); `diff-cover` counts diff lines by default and offers
    `--ignore-whitespace` as an opt-in; Coccinelle hides spacing-only changes unless `--force-diffshow`
    ("diff even if only spacing changes") is given, and offers `--partial-match` to report partial
    matches. [Sources: difftastic README](https://raw.githubusercontent.com/Wilfred/difftastic/master/README.md),
    [diff-cover README](https://raw.githubusercontent.com/Bachmann1234/diff_cover/master/README.rst),
    [spatch(1) manual](https://manpages.debian.org/experimental/coccinelle/spatch.1.en.html).
    **Support:** direct evidence for each tool's documented behaviour; the conclusion is researcher
    inference. **Confidence:** high (docs), medium (conclusion). **Inference:** an AST-based check
    should treat "declared chunk's AST unchanged, text changed" as *touched but semantically unchanged*
    — a distinct third state that keeps docstring/comment work from producing a coverage warning while
    still being visible in the advisory text.

13. **Claim (closest existing analogue to the coverage check):** Coccinelle semantic patches are the
    only surveyed artefact that declares a *syntactic change* and then verifies it found a match —
    `spatch` "describes the code to match and the transformation to perform as a semantic patch, which
    looks like a standard patch, but can transform multiple files at any number of code sites", emits a
    patch "showing the effect of the application, if any", and flags `--defined`/`--undefined`.
    [Source: spatch(1) manual](https://manpages.debian.org/experimental/coccinelle/spatch.1.en.html).
    **Support:** direct evidence. **Confidence:** high. **Adoption delta / counter-note:** it is C-only
    (experimental C++), an external OCaml binary, and it *applies* a transformation rather than auditing
    a diff — so it is design evidence for "a declared change that must match", not an adoption candidate.

14. **Claim (enforcement ladder — advisory before blocking is the established pattern):** Google's
    static-analysis team defines an "effective false positive" as an issue where "developers did not
    take positive action after seeing the issue", lists non-actionable/non-trustworthy/expensive fixes
    among the reasons engineers ignore warnings, and only enables a check as error or warning "after
    vetting it"; SonarQube warns that adding conditions "may lead to bottlenecks… frequent failures may
    cause a debate on which conditions to prioritize"; GitLab supports optional CODEOWNERS sections
    (`^[Section]`) that do not require approval.
    [Source: CACM, Lessons from Building Static Analysis Tools at Google](https://cacm.acm.org/research/lessons-from-building-static-analysis-tools-at-google/),
    [Source: SonarQube Clean as You Code](https://docs.sonarsource.com/sonarqube-server/9.8/user-guide/clean-as-you-code),
    [Source: GitLab CODEOWNERS syntax](https://docs.gitlab.com/user/project/codeowners/reference/).
    **Support:** direct evidence. **Confidence:** high.

15. **Claim (containment prior art is file/path-shaped):** GitHub's CODEOWNERS uses gitignore-style
    patterns with documented limitations (negation `!` does not work, a >3 MB file is ignored entirely,
    an invalid line is skipped) and no symbol granularity; GitLab's CODEOWNERS adds `[Section]` groups
    and per-section exclusion patterns but is likewise path-based; no chunk- or symbol-level ownership
    mechanism was found in either product's docs.
    [Source: GitHub CODEOWNERS docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners),
    [Source: GitLab CODEOWNERS syntax](https://docs.gitlab.com/user/project/codeowners/reference/).
    **Support:** direct evidence (docs) + negative finding (absence) which is search-bounded, not
    exhaustive; see §9. **Confidence:** high (documented mechanism), medium (absence claim).

16. **Claim (line-level "coverage of the change" already exists — but it measures tests, not scope):**
    `diff-cover` computes "the percentage of new or modified lines that are covered by tests… If you
    touch a line of code, that line should be covered", requires git and a coverage XML/LCov report, and
    pulls third-party dependencies (current release 10.6.0 declares `chardet`, `jinja2`, `pluggy`,
    `pygments` and `requires_python >=3.10`); Codecov's analogous "patch coverage" works from uploaded
    base/head reports. [Source: diff-cover README](https://raw.githubusercontent.com/Bachmann1234/diff_cover/master/README.rst),
    [Source: PyPI diff_cover JSON](https://pypi.org/pypi/diff-cover/json),
    [Source: Codecov PR comments](https://docs.codecov.com/docs/pull-request-comments).
    **Support:** direct evidence. **Confidence:** high. **Inference:** this is the *coverage-shaped*
    precedent most tickets would accept, but it needs a CI commit pair and a coverage report, and it
    cannot tell whether the touched line was the intended one.

17. **Claim (Counter-evidence, mixed):** a controlled experiment with 28 developers found change
    decomposition "leads to fewer wrongly reported issues… yet impacts neither understanding the change
    rationale nor the number of found defects" — scoping helps reviewer noise, not defect detection;
    and an October 2026 preprint on agent-generated patches reports that agents "produce large, tangled
    patches", that untangling them while staying runnable improved a follow-up agent's regression-repair
    pass@1 by 5.2% absolute, and that baseline untanglers left 20.6%–37.4% of commit histories
    unrunnable. [Source: The effects of change decomposition on code review (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7924728/),
    [Source: Runnable Commit Untangling for Coding Agents (arXiv 2610.11593, preprint)](https://arxiv.org/abs/2610.11593).
    **Support:** direct evidence (both are the authors' own abstracts/reported results; the second is a
    non-peer-reviewed preprint). **Confidence:** high for the controlled experiment, low-medium for the
    preprint.

18. **Claim (indexer protocols are read-only and partly abandoned):** SCIP "is meant to be a
    _transmission_ format… not meant as a _storage_ format for querying", lists "Support use cases
    involving code modifications" under non-goals, and records that "LSIF support has since been fully
    deprecated and removed" at Sourcegraph; GitHub's stack-graphs repository states "This repository is
    no longer supported or updated by GitHub"; Kythe keeps revisions and timestamps out of names on
    purpose ("a name should say 'what' something is, not 'when'").
    [Source: SCIP DESIGN.md](https://raw.githubusercontent.com/sourcegraph/scip/main/docs/DESIGN.md),
    [Source: SCIP README](https://raw.githubusercontent.com/sourcegraph/scip/main/README.md) (CLI v0.10.0, 2026-09-03),
    [Source: github/stack-graphs README](https://github.com/github/stack-graphs),
    [Source: Kythe schema](https://www.kythe.io/docs/schema/). **Support:** direct evidence; these are
    design evidence (§3.6), not adoption candidates. **Confidence:** high.

## Answers to the decision questions

1. **Chunk unit.** Declaration-level qualified names (module/class/function/method) are the unit worth
   having: they are stable under reformatting, survivable under intra-file moves, human-writable by the
   authoring agent, and directly expressible in the fixed front-matter grammar (Findings 2, 3, 5).
   Statement/node spans and byte ranges have better precision but no durable name and optional end
   positions (Findings 2, 6); hunks are baseline-relative and evaporate on rebase (Finding 7).
   *Sub-question:* a declared **parent** chunk should satisfy coverage when a child changed **only if
   containment is defined over the declaration's subtree** — that is the researcher's recommendation
   (inference, not a sourced guarantee), and the check should say so in its advisory text, because the
   opposite choice (exact span) makes "I touched the method" fail whenever a line in the module
   docstring moved.

2. **Chunk identity and stability.** Ranked by survival: recorded revision + qualified name (survives
   reformat/reorder/intra-file move; breaks on rename/move across files) > qualified name with
   structural anchoring on the enclosing declarations > line/span pins (drift silently; Findings 2, 6) >
   content hash (breaks on *any* edit — Unison's model, Finding 5). Index-backed monikers (LSIF/SCIP)
   give cross-version linkage but no stability guarantee and no modification support (Findings 4, 18).
   **Anchor drift is the top risk — confirmed with evidence:** every mechanism that could pin a chunk to
   a position has an explicit primary-source disclaimer (Findings 2, 3, 4, 6).

3. **The baseline.** Comparable systems always diff against recorded commits: merge-base/`...` by
   default (`diff-cover`), an explicit `SEMGREP_BASELINE_REF` (Semgrep), base+head commits (Codecov),
   releases/days/PR-lines (SonarQube) — Finding 7. Consequences for us: a date-only lifecycle has no
   baseline; the dirty worktree is unusable because tool output is always in flight; merge-base is
   available without any schema change but includes unrelated in-flight edits in both verdicts; a
   recorded revision (a new front-matter/lifecycle field, or the archive record on landing) gives the
   cleanest semantics. Which one is "actually available" is a repo decision, not a research finding:
   **what must be recorded is a revision id** (inference, Finding 7).

4. **Deriving the changed set.** For *our* question the cheapest reliable method is not a full AST diff
   but **per-declared-chunk before/after equality**: re-resolve each declared name in the baseline
   revision and the current tree, compare normalized dumps/segments, and only then map the residual
   text diff onto nodes for the containment direction (inference; costed by Findings 2, 8, 9). Full AST
   diffing (GumTree/RefactoringMiner/difftastic) buys move/rename awareness at the price of a second
   runtime and a mapping layer (Findings 8, 10, 11). Known error modes to expect and document: moves
   and rename detection, decorators/annotations above a declaration, generated code, multi-statement
   hunks straddling two chunks, deleted files, and parse failure on syntax-invalid worktrees.
   *Sub-question:* "touched" must be defined twice — **byte-touched** (text diff) for containment, and
   **semantically touched** (AST equality) for coverage; difftastic/diff-cover/Coccinelle all show that
   whitespace-only change is a caller-configurable judgement, not a universal rule (Finding 12).

5. **Coverage and containment checks.** No system does either direction (Finding 1). Adjacent systems
   and what they would miss: CODEOWNERS (file/path ownership → no chunk coverage, no containment inside
   a file; Finding 15); `diff-cover`/Codecov patch coverage (line coverage of new lines, needs a CI
   commit pair and a coverage report; Finding 16); SonarQube new-code gate (lines + rules; Finding 7);
   Semgrep diff-aware (new *findings* only; Finding 7); Coccinelle SmPL (a declared syntactic change
   that must match, but it applies rather than audits; Finding 13). Composition with `files_owned`: the
   honest design is **narrow, not replace** — `files_owned` remains the ownership/overlap primitive, and
   the chunk set is validated to be a subset of the owned files, with a chunk outside `files_owned`
   being a separate advisory (inference). **Exemptions are mandatory:** every ticket declares its own
   `change.md`, its status line, the `docs/roadmap.md` entry, and the archive record created on landing —
   without a fixed exempt set (the ticket's own artefact paths, and the generated roadmap region) the
   containment verdict is a permanent false positive (inference from §2's given repo facts).

6. **Chunks that appear or disappear.** Protocols give no vocabulary for this (SCIP/LSIF/Kythe are
   revision-less; Finding 18); the closest mechanism is a refactoring detector that names *Rename/Move
   Method* between two revisions (RefactoringMiner; Finding 8). For a declared-chunk checker the
   distinguishable states are computed, not declared: **present in baseline and absent now = removed
   (intended)**; **absent in both = unresolved (typo or not-yet-created)**; **absent in baseline and
   present now = created (intended)**, which is why a declaration syntax should carry an explicit
   marker for "new" (e.g. a `new::` name prefix) rather than relying on absence. Fail behaviour
   should be: unresolved → advisory (fail-open) at introduction, with duplication/ambiguity (two
   declarations resolving to the same node, or one name matching several nodes) → advisory naming the
   ambiguity and never a silent pick (inference).

7. **Opt-in, degradation, and authoring workflow.** Precedents: a check is enabled as warning only
   after vetting and is measured by "effective false positives" (Google, Finding 14); sections can be
   marked optional (GitLab, Finding 14); gates are represented as statuses that can be required or not
   (SonarQube/Codecov/Semgrep, Finding 7). Recommended ladder for us: absent front-matter key = check
   inert (existing tickets unaffected); key present = advisory findings only; a repo-level flag may
   later promote one verdict to error, per verdict, never both at once. Degradation must be explicit,
   never silent: no extractor for the language, unresolvable chunk, missing baseline, or unparseable
   file → a WARN that says which of those happened, and no verdict; `--offline` and the stdlib-only lane
   mean the Python extractor always exists, so this is mostly an other-language concern (Findings 2, 10).
   The authoring agent can enumerate candidates with **stdlib `ast`** (`ast.walk` over the after-tree of
   `files_owned`, printing `path::qualname`) — a ~20-line command matching an authoring surface that
   already reads code; the dev lane may additionally use `ast-grep --inline-rules` for pattern-shaped
   enumeration and `--debug-query` workflows (Finding 10).

8. **Language-agnostic seam.** The language-neutral core is: declaration syntax, baseline resolution,
   exemption policy, verdict framing, and reporting. The per-language part is *extraction only*, behind
   one interface: `extract(path, source) -> [(qualname, span, parent, fingerprint)]`. Three real
   providers: (a) stdlib `ast` for Python (in-runtime); (b) tree-sitter + per-grammar `queries/tags.scm`
   for the rest — the tags vocabulary is a documented convention but "new applications may extend (or
   only recognize a subset)", the query file lives in each grammar repo, and `py-tree-sitter` is a
   third-party dependency, so this is the dev lane; (c) an LSP server per language — but LSP gives no
   symbol id, and monikers are optional and only required to "match… the corresponding LSIF
   implementation" (Findings 2, 4, 10 and tree-sitter Code Navigation docs:
   https://tree-sitter.github.io/tree-sitter/4-code-navigation.html). **Implication:** every added
   language costs a per-language extractor regardless of the seam chosen; neither tree-sitter tags nor
   LSP is a trustworthy *identity* source (names are not unique, no stability contract).

9. **Concurrency (short).** Chunk-level ownership as a true isolation boundary has no prior art found
   in this session: the ownership mechanisms in products are path-based, and their enforcement point is
   review/approval, not write-time locks (Finding 15). So chunk scope should be treated as a
   coordination and detection aid for parallel agents — it can flag "two in-progress tickets declare an
   overlapping chunk" the way `ownership-overlap` flags files, but it cannot prevent interleaved edits,
   and a verifier that runs after the fact will attribute the union of both tickets' edits to each
   ticket's diff unless the baseline is per-ticket (Finding 7). One paragraph, per brief.

10. **Counter-evidence.** Decomposition reduces *wrongly reported issues* but not found defects
    (controlled experiment, N=28), and its cost is authoring ceremony (Finding 17). Agent-authored
    patches are measurably tangled and untangling them helped a downstream agent repair regressions
    (+5.2% absolute pass@1) — evidence that scoping aids *agent* consumers, from a preprint (Finding
    17). Policy gates fail by becoming ignored when they fire often (SonarQube's own warning) or by
    "effective false positives" (Google) — Finding 14. The honest alternative (keep file-level scope
    plus a machine-checked diff summary) is therefore a legitimate landing point, and is the runner-up
    in §6.

11. **Cost of the deliverable** — folded into the matrix's *Delta* column below.

## Options matrix

| #   | Family (candidate)                                                                      | Granularity                                  | Identity scheme                                      | Changed-set derivation                                                  | Strictness                                   | Offline story                                                                                     | Cost to adopt        | Delta we still build                                                                |
| --- | --------------------------------------------------------------------------------------- | -------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------- |
| 1   | **stdlib `ast` + `difflib` (in-house, in-runtime)**                                     | declaration (qualname)                       | `path::qualname` string, re-resolved per revision    | per-chunk before/after AST equality + residual text-diff→node mapping   | advisory first; opt-in key                   | fully offline, stdlib-only, no new dependency                                                     | ~200–400 LOC         | everything: declaration grammar, baseline, exemptions, both verdicts, messages      |
| 2   | File-level scope + machine-checked diff summary (`git diff` counts + tree-ish baseline) | file                                         | existing paths                                       | `git diff` text/numstat                                                 | advisory only                                | offline (git plumbing already used)                                                               | ~50–100 LOC          | nothing external; delivers no chunk verdicts                                        |
| 3   | ast-grep (dev lane)                                                                     | syntactic pattern                            | `kind`/`pattern` query, not an identity              | pattern hits, not a diff                                                | rule severity (reported)                     | offline single binary, MIT, 27 langs                                                              | install + config     | name→pattern mapping, baseline, both verdicts; not a verifier by itself             |
| 4   | difftastic (dev lane)                                                                   | syntax nodes for display                     | none (no identity)                                   | AST-aware diff, move/rename-aware-ish; ignores non-syntactic whitespace | display only (no exit-code policy)           | offline single binary, MIT                                                                        | install              | all verdict logic; no machine-readable scope output                                 |
| 5   | GumTree (dev lane)                                                                      | AST node matching + edit script              | tool-internal node ids, per run                      | full AST diff (add/del/move/update)                                     | none built in                                | offline (JVM + jars), LGPL-3.0                                                                    | dev venv/JVM install | mapping edit script → declared names; baseline; verdicts; exception handling        |
| 6   | RefactoringMiner (dev lane)                                                             | method/field/class + sub-method refactorings | names per revision, refactoring types                | AST diff + refactoring detection, multi-language                        | none built in                                | offline (JVM), MIT                                                                                | dev venv/JVM install | same as #5, plus precision caveats per language                                     |
| 7   | LibCST (dev lane)                                                                       | CST nodes, formatting-preserving             | none yet (FQN listed as *Future*)                    | tree comparison you write                                               | none                                         | offline (needs Rust toolchain when no wheel)                                                      | pip install          | qualified-name provider, diffing, verdicts                                          |
| 8   | OpenRewrite LST (dev lane)                                                              | typed LST (Java-first)                       | type-attributed nodes                                | recipe matches / LST diff                                               | recipe/CI driven                             | offline JVM, Apache-2.0 (per docs/repo)                                                           | JVM + project build  | not applicable to our Python-first target without a second stack                    |
| 9   | SCIP / LSIF / Kythe indexers                                                            | symbols + spans                              | monikers / VNames (opaque, unstable across versions) | per-revision index dump; diffing is *ours*                              | none (read-only, modification is a non-goal) | indexers are local but require per-language toolchains; no service needed for `scip-python` alone | high                 | everything: no scope model, no diff, no verdicts; plus a per-language indexer       |
| 10  | CI services (Codecov / SonarQube / Semgrep platform)                                    | line / new-code / new-finding                | n/a                                                  | base-vs-head commits                                                    | required status checks                       | **not on-prem without self-hosting** (last resort per brief)                                      | service + tokens     | mirrors none of the chunk semantics; rejected as services, kept as design precedent |

## Recommended bootstrap path

**Recommended (ranked first): option 1 — build a small stdlib-only, advisory-first chunk-scope check
in-house; adopt nothing as a runtime dependency.** It is the only row that satisfies the stdlib-only
invariant *and* answers both questions (Findings 2, 4, 6, 7). Concretely: declare chunks in front
matter, resolve them against a recorded baseline revision (else merge-base, else skip with an advisory),
compute coverage by per-chunk AST equality and containment by mapping the text diff onto nodes,
exempt the ticket's own artefacts, and emit WARN-class findings only.

**Runner-up, and the condition under which it wins: option 2 (keep file-level scope plus a
machine-checked diff summary).** It wins if, after a soak period of real tickets, either (a) declared
chunk names drift or fail to resolve in more than a small fraction of tickets, (b) tickets opt in so
rarely that the check's signal is negligible, or (c) no baseline revision is ever recorded, leaving both
verdicts dominated by unrelated in-flight edits (Findings 6, 7, 17). It is a legitimate permanent
landing point, not a failure.

**What we build ourselves (unavoidable in every option incl. the runner-up):** the declaration
grammar in the existing front-matter grammar; the baseline resolver; the exemption policy for
tool-written files; the two verdicts and their advisory wording; the diagnostics discipline (ids/paths/
counts, never bodies); and the authoring-time chunk enumerator.

**Explicitly not adopted:** GumTree/RefactoringMiner/OpenRewrite/LibCST as runtime components (second
toolchain, large delta, no scope model); SCIP/LSIF/Kythe as an identity source (read-only by design,
per-language indexers, no stability contract); any self-hosted or hosted service (Codecov/SonarQube/
Semgrep platform) — they are the design precedent for baselines and gating, not dependencies.

## Design sketch (non-binding)

**Sketch only — a decision to be taken later, not a decision taken here.**

Front matter (fits the fixed grammar: a list of strings, or a map of string→string, 2-space indent):

```yaml
# v1 — list form (simplest; parsers, order-insensitive)
chunks_owned:
  - src/doc_contract/resolver.py::Resolver.resolve
  - src/doc_contract/resolver.py::new::_baseline_rev

# v2 — map form (lets a chunk carry one status token without a nested structure)
chunks_owned:
  resolver.resolve: src/doc_contract/resolver.py::Resolver.resolve
  baseline.rev.new: src/doc_contract/resolver.py::new::_baseline_rev
```

Grammar notes: `path::qualname` (`::` cannot occur in either component); `new::` marks "created by this
change"; a bare `path::` with no qualname means "any chunk in this file" (escape hatch that degrades to
today's file-level behaviour). Absent key ⇒ check inert ⇒ existing tickets unchanged (backward
compatible by construction).

Verify algorithm (advisory-first):

1. If `chunks_owned` absent → exit clean (no findings). If present but no baseline revision is
   available → `WARN chunk-baseline-missing`, no verdicts.
2. Resolve baseline tree (recorded revision → else merge-base with the default branch → else stop at
   step 1) and current tree.
3. For each declared chunk: resolve the qualname in both trees. Present-both → compare normalized AST
   dumps (positions excluded) → *changed* / *unchanged-but-text-differing* / *unchanged*. `new::`
   chunks must be absent in baseline and present now. Absent in both → `WARN chunk-unresolved`
   (typo or not-yet-created, indistinguishable by construction — say so in the message).
4. **Coverage verdict:** any declared chunk resolving to *unchanged* (and not marked `new::`) →
   `WARN chunk-not-touched` (this is the gap the ticket exists to close).
5. **Containment verdict:** for each owned file, map the text diff hunks onto enclosing nodes; any
   changed node that is not inside a declared chunk's subtree, after subtracting the exempt set, →
   `WARN change-outside-chunks` listing path + qualname + hunk count. Declared parent chunks cover
   their subtree (Answer 1's sub-question); `path::` (file-level) chunks suppress this verdict for that
   file.
6. Exempt set (fixed, always): the change's own `docs/changes/<id>/` files, the ticket's status line,
   `docs/roadmap.md` (or its generated region), and the archive record written on landing.
7. Exit codes: 0 always at introduction; a repo-level capability flag may promote one verdict to a
   non-zero exit later. Diagnostics carry ids/paths/qualnames/counts only.

## Risks, false positives, and what would falsify the recommendation

- **Anchor/drift false positives (highest):** a chunk name that no longer resolves because of a rename
  or a move across files produces a coverage warning that is a lie (Findings 4, 6). Mitigation: report
  *unresolved* and *not-touched* as distinct codes; never conflate them with containment.
- **Permanent false positives from tool-written files:** if the exemption set is incomplete, every
  ticket warns. This is the single most likely reason the check gets ignored (Finding 14).
- **Ceremony:** authoring agents must emit chunk names; a wrong-but-plausible name is worse than no
  name (it produces a containment advisory for the intended edit). Falsifier: measure resolution rate
  and false-advisory rate over ~20 real tickets; if unresolved ≥ ~10% or the false rate dominates,
  fall back to the runner-up.
- **Whitespace/comment edits:** treating them as "not touched" for coverage while treating them as
  "touched" for containment is a deliberate asymmetry that must be documented, or it will be read as a
  bug (Finding 12).
- **Multi-chunk hunks and moves** are the classic AST-diff failure modes (Findings 8, 11); the
  per-chunk-equality trick avoids most of them for coverage, but the containment direction still uses a
  text diff and will mis-attribute moved code — acceptable while advisory.
- **What would falsify the whole recommendation:** evidence that declared chunk names cannot be
  produced reliably by the authoring skill (resolution rate collapses), or that the measured
  false-positive burden exceeds the review-noise benefit the decomposition experiment reports
  (Finding 17) — in either case, keep file-level scope plus a diff summary and stop.

## Unverified / needs a spike

1. **Tangled-change statistics (Herzig & Zeller, MSR 2013).** Search snippets quote "up to 15% of all
   bug fixes… multiple tangled changes" and "16.6% of all source changes", but the primary PDF/abstract
   pages I could reach this session were blocked (IEEE CSDL renders in JavaScript; Semantic Scholar HTML
   did not extract). **Cheapest experiment:** read the MSR'13 PDF (DOI 10.1109/MSR.2013.6624006) or the
   authors' copy, and record the exact figure with page/table. Until then the *only* verified
   decomposition evidence in this report is the PMC controlled experiment (Finding 17).
2. **`git merge-base` under shallow clones** — I did not confirm a primary statement from the git
   documentation that merge-base fails or degrades in a shallow clone (the git-merge-base page fetched
   here contains no "shallow" text). **Spike:** `git clone --depth=1` a fixture, run
   `git merge-base HEAD origin/main`, record the failure mode; check `git fetch --unshallow` as the
   remedy.
3. **Whether any LSP server we would realistically run (e.g. ruff's server, pyright) implements
   `textDocument/documentSymbol` and `textDocument/moniker`** — not verified this session; the spec
   makes both optional. Spike: run against this repo and record what is returned.
4. **Semgrep OSS local diff-aware behaviour without the Semgrep platform/App token** — the fetched page
   is written around the platform (`SEMGREP_APP_TOKEN`), so the OSS-only baseline story is unverified.
   Spike: run OSS semgrep with a baseline ref and no token.
5. **Offline packaging of the dev-lane binaries** (ast-grep, difftastic, GumTree, RefactoringMiner,
   `scip-python`): each releases prebuilt artefacts, but whether they run on the target on-prem images
   without network, and their size/licence notices, was not exercised. Spike: install each into a
   throwaway dev venv on the deployment image with networking disabled.
6. **Spec/plan-driven tooling that attaches implementation intent to artifacts** (the brief's seed
   lead: Kiro-style specs, spec-kit-style plans): no primary source was fetched this session, so I make
   **no claim** about their file or chunk declaration or verification behaviour. Spike: fetch their docs;
   the question is whether any of them *machine-checks* declared scope (my expectation is no, but that
   is an inference, not a finding).
7. **Negative claim in Finding 1/15 (no chunk-scope verifier exists)** is search-bounded: provider
   outages mean the space was probed via direct fetches of the obvious primary sources, not exhaustively.
   Spike: one targeted sweep of GitHub code search for terms like `chunks_owned`, `declared symbols`,
   `scope enforcement AST diff` before treating the absence as settled.
8. **RefactoringMiner Python-precision** is claimed by its README benchmark links, which I did not open;
   the multi-language support table itself is primary and was read (Finding 8).
9. **LibCST's metadata/position providers** (useful for span-based anchoring) were not read; only the
   README's feature list and its "future FQN" statement were verified.
10. **Coccinelle on Python** — nothing in the manual suggests it; the SmPL design is cited as design
    evidence only, and its C-only scope is from the manual's own description ("a program matching and
    transformation tool for C").

## Sources

**Kept (primary, fetched this session):**
- SCIP: `scip.proto` (symbol grammar), `README.md`, `docs/DESIGN.md` (non-goals, LSIF removal), releases feed (v0.10.0, 2026-09-03).
- LSIF: `microsoft/lsif-node` `protocol.ts` (moniker vertex, `UniquenessLevel`, opaque identifier).
- LSP 3.17: `language/documentSymbol.md`, `language/moniker.md`.
- Kythe: schema reference (VName fields, signature non-stability, no revision in names), storage model.
- tree-sitter: Queries/Basic Syntax, Code Navigation (tags, `queries/tags.scm` convention), releases feed; `github/stack-graphs` README (unsupported/not updated by GitHub).
- Python standard library `ast` documentation (position attributes, `get_source_segment`).
- ast-grep: rule essentials, language list, LICENSE (MIT), releases feed (0.51.0, 2026-10-15).
- difftastic: README (MIT; whitespace behaviour; non-goal: no patches), releases feed (0.71.0, 2026-09-18).
- GumTree: README (move/rename detection; languages), LICENSE (LGPL-3.0), releases feed (nightly 2026-10-12); ChangeDistiller paper (IEEE TSE 2007, DOI 10.1109/TSE.2007.70731) and its 2025 retrospective (DOI 10.1109/TSE.2025.3538326) as AST-diff design evidence.
- RefactoringMiner: README (language table, refactoring types, AST diff), LICENSE (MIT), releases feed (3.1.6, 2026-09-16).
- OpenRewrite LST docs; LibCST README (MIT, formatting-preserving, "future" FQN).
- Coccinelle: `spatch(1)` manual (Debian manpages mirror of the upstream man page).
- diff-cover: README (baseline `origin/main`, `...` notation, `--ignore-whitespace`), PyPI JSON (10.6.0, deps); PyPI JSON for semgrep (1.181.0) and its LICENSE (LGPL-2.1).
- Semgrep docs: diff-aware scans / `SEMGREP_BASELINE_REF`.
- Codecov: Pull Request Comments (base/head, patch coverage).
- SonarQube: Clean as You Code / new code definition (releases, days, PR lines; gating drawbacks).
- CODEOWNERS: GitHub "About code owners", GitLab "Syntax of CODEOWNERS file".
- Policy-gate evidence: CACM "Lessons from Building Static Analysis Tools at Google" (effective false positive; vetting before enabling as warning/error).
- Change-scope evidence: "The effects of change decomposition on code review—a controlled experiment" (PMC); "Runnable Commit Untangling for Coding Agents" (arXiv 2610.11593, **preprint**).
- Baseline/identity design evidence: git-merge-base and git-diff manuals; Jujutsu glossary (change ID stable across rewrites); Unison "the big idea" (content-addressed definitions); Pijul manual (change commutation).

**Rejected / deprioritized:**
- Search-engine result snippets and vendor blogs (SmartBear "400 lines" guidance, AI-code-review vendor posts, Harness/Aviator CODEOWNERS guides): secondary, unverifiable detail, not used for any claim.
- Semantic Scholar / IEEE CSDL / ResearchGate pages for Herzig & Zeller: unreachable as primary text this session (see §9.1).
- log4brains/mdBook/Docusaurus-style viewer material from the sibling frontend note: out of scope here.
- stack-graphs, Darcs, Coccinelle-as-adoption: recorded as abandoned-or-adjacent *design* evidence only (§3.6 of the brief), not adoption candidates.

## Next steps

1. Spike the baseline question first (it gates both verdicts): can `accept`/`begin` record a revision id,
   and what does merge-base return in this repo's actual clone shape (§9.2)?
2. Prototype the Python extractor + per-chunk equality in ~150 lines against three real past tickets
   reconstructed from git history, and measure resolution and false-advisory rates (the falsifier in
   §Risks).
3. Only if the prototype's numbers hold: decide the front-matter key and exemption set; keep the dev-time
   structural differ (ast-grep) for authoring and human summaries, not for the gate.

## Addendum (2026-10-16) — edit-time provenance: a second verification point

Appended after the main run, while reviewing `pydantic/pydantic-ai` issue #9123 ("AST-Aware Code
Editing capability") and the implementation it cites. It answers a question §4.4/§4.7 left open —
whether the changed-chunk set can be *produced* rather than *inferred* — and records one design the
main pass did not survey. Evidence rule unchanged: primary sources only, fetched 2026-10-16.

A1. **Claim:** #9123 is an unimplemented request, not a readable implementation: it is OPEN with zero
comments, cross-referenced only by #9124 (LSP diagnostics) and #9138 (edit-format abstraction), and no
pull request closes it. Its harness sibling `pydantic-ai-harness#728` was CLOSED by moving `edit_file`
to *unified-diff patches* — a text-granularity fix, not an AST one — and a code search of that
repository for `ast_grep`/`tree_sitter` returns nothing.
[Source: issue #9123](https://github.com/pydantic/pydantic-ai/issues/9123),
[Source: pydantic-ai-harness#728](https://github.com/pydantic/pydantic-ai-harness/issues/728),
[Source: GitHub code search over the harness repo](https://github.com/pydantic/pydantic-ai-harness).
**Support:** direct evidence. **Confidence:** high. **Relevance:** no adoption candidate; only the
mechanism below.

A2. **Claim:** the real implementation the issue points at is Mastra's `ast_edit` tool
(`packages/core/src/workspace/tools/ast-edit.ts`, 564 lines, Apache-2.0), built on `@ast-grep/napi`
loaded through a cached dynamic import that returns `null` on failure, whereupon the tool degrades to
the message `@ast-grep/napi is not available. Install it to use AST editing.` Its schema is
`pattern`/`replacement` plus `transform: add-import | remove-import | rename`, and its `outputSchema`
is `z.string()` (line 407).
[Source: ast-edit.ts](https://github.com/mastra-ai/mastra/blob/main/packages/core/src/workspace/tools/ast-edit.ts),
[Source: packages/core/package.json](https://github.com/mastra-ai/mastra/blob/main/packages/core/package.json)
(license Apache-2.0). **Support:** direct evidence. **Confidence:** high. **Adoption delta:** nothing
adoptable (TypeScript/napi, no contact with our front-matter or verdict layers). **Borrow:** the
degradation shape — the ladder §4.7 recommends, independently implemented in a production agent
framework.

A3. **Claim (the borrowable mechanism):** an AST-aware *editor* already computes the datum the
containment verdict needs — the matched node ranges — and discards it at the tool boundary.
`patternReplace` iterates `root.findAll({ rule: { pattern } })` (line 347), takes `match.range()` per
hit (line 354) and `match.getMatch(varName)` (line 359) to build the replacement text; the rename path
surfaces only an occurrence *count*, as prose: `Renamed 'x' to 'y' (N occurrences)` (line 518). The
result is assembled as a string (line 555) and the declared output is `z.string()` (line 407), so no
range ever reaches the caller and a checker must re-derive the changed set from a text diff (Answer
4's method). **Support:** direct evidence (source read). **Confidence:** high. **Inference:** if the
editing path emitted `[(path, span, pattern)]` as structured metadata, containment would be *observed*
rather than *inferred*, removing the residual mis-attribution of moved code that §Risks currently
accepts — at the cost of covering only edits made through that tool, and saying nothing about human or
unmediated-agent edits. No surveyed system does this, which extends Finding 1's negative result from
"no verifier" to "no producer either".

A4. **Claim:** the adjacent pattern is verify-after-edit rather than verify-at-`check`: Mastra appends
`getEditDiagnosticsText(...)` to the edit result, and ships a separate `lsp-inspect` tool declaring
`{hover, diagnostics, definition, implementation}`.
[Source: ast-edit.ts (return path, lines 549-560)](https://github.com/mastra-ai/mastra/blob/main/packages/core/src/workspace/tools/ast-edit.ts),
[Source: lsp-inspect.ts](https://github.com/mastra-ai/mastra/blob/main/packages/core/src/workspace/tools/lsp-inspect.ts).
**Support:** direct evidence. **Confidence:** high. **Relevance:** a third option for *when* the chunk
verdict runs (edit time, `check` time, or both). It changes no decision answer, but belongs beside
§4.7's ladder.

**Caveats.** The issue's "Who has this" table is not citable: it paraphrases Mastra's source rather
than quoting it (its `SgNode` interface is not the real napi API shape), and its "Claude Code — LSP
tool" row could not be verified against any primary source. Treat the table as a lead list only.

**Effect on the recommendation: none.** Option 1 (stdlib-only in-house check) stands and its coverage
direction is unchanged. The one idea worth carrying into a prototype is A3: record what the *editor*
touched where an editor exists, fall back to diff-derived inference where it does not, and report the
two as different provenance classes — the observed class is strictly stronger, and conflating them
would overstate the weaker one.

# Research: Search API providers for an indie developer

Saved at `docs/research/search-provider-comparison.md`, alongside
`docs/research/doc-contract-frontend-research.md`. (`doc-contract-complexity-review.md` remains a
root-level analysis note.) The directory is deliberately outside the change graph:
`doc-contract` discovery only mints nodes for `docs/changes/**/*.md`, `docs/adr/NNNN-*.md`,
`docs/spec/*.md`, `docs/archive/**`, and the root nodes declared in `.doc-contract.toml`, so notes
here are not managed documents and cannot break preflight.

Research date: **2026-10-15**. Every price below was read from the vendor's own pricing page during
this session; none is from memory or a secondary summary. Rows where the vendor's page is
JavaScript-rendered, gated, or absent say so explicitly. Prices in this market move — re-check the
linked page before committing budget.

## Summary

For an indie developer the choice splits on three axes that the price column alone hides: whether a
free tier is usable **without a credit card**, what a billable **unit** actually is (request, credit,
10-result page, or call-plus-tokens), and whether the free path survives real load.

- **Keyless prototyping:** You.com's free MCP tier is the only offering here that needs no API key, no
  account, and no card — 100 queries/day. TinyFish and Parallel give unusually generous free volume
  otherwise.
- **Cheapest at volume:** Parallel's Search API ($0.001–$0.005 per 10 results), TinyFish ($0.00 per
  search request in the free tier), Search1API (≈$0.66–0.76 per 1,000 credits), and Bright Data
  ($1.50/1k successful requests).
- **Best agent ergonomics:** Tavily (1,000 credits/month, no card) and Exa ($10 in credits on signup,
  resetting monthly, no payment method).
- **Zero-cost but self-owned:** SearXNG is the only genuinely free option, because you run it.
- **Grounding with Google Search is not a free-tier feature.** It requires the Gemini API Paid Tier
  (linked Cloud Billing account plus a ≥$5 prepay); Google AI Pro/Ultra subscriptions raise quota in
  *AI Studio*, not for API keys. Details in its own section below.

The comparison table below is the primary artifact; the sections after it record what could not be
verified and where free tiers mislead.

## Provider comparison

| Provider | Free tier (as published) | Paid entry | Unit | Key / card | Indie note | Source |
|---|---|---|---|---|---|---|
| **You.com** | **100 queries/day, no API key, no account, no card** (MCP) | $5.00 / 1k calls (≤100 results/call) + $10 free credit | call | none for free tier | Lowest-friction start of anything here — genuinely keyless | [you.com/pricing](https://you.com/pricing) |
| **TinyFish** | Search **$0.00/request**: 30 req/min, 500 req/hour; Fetch free 1,000 URLs/day | Agent $0.016/step, Browser $0.002/min | request | key for paid | Generous free search volume; agent/browser steps are the paid part | [tinyfish.ai/pricing](https://www.tinyfish.ai/pricing) |
| **Parallel** | Up to **5,000 requests/month free** | Search API $0.001–$0.005 **per 10 results**; Task API $0.005–$2.4/req | 10-result page | key | Cheapest per-result at the low end; Search API 600 req/min | [parallel.ai/pricing](https://parallel.ai/pricing) |
| **Tavily** | 1,000 credits/mo, **no card** | PAYG $0.008/credit; Project $30 = 4,000 credits ($0.0075/cr); Bootstrap $100 = 15,000 ($0.0067) | credit | no card for free | Agent-oriented; free student accounts | [tavily.com/pricing](https://tavily.com/pricing), [credits doc](https://docs.tavily.com/documentation/api-credits) |
| **Exa** | **$10 credits on signup, resets to $10 monthly, no payment method** (≈2,500 instant searches) | instant $4/1k, fast/auto $7/1k, deep $12–15/1k, contents $1/1k pages, answer $5/1k | request (≤10 results) | none for free tier | Pay-as-you-go, no subscription; the free MCP path rate-limits under load | [exa.ai/pricing](https://exa.ai/pricing) |
| **Gemini (Google grounding)** | **Not available on the API free tier** — see grounding section | 5,000 free search requests/month (Gemini 3+), then **$14 / 1k**; older models 1,500 RPD free then $35 / 1k grounded prompts | query the model executes | Cloud Billing linked + ≥$5 prepay | Not a free-tier feature; testable in AI Studio | [ai.google.dev pricing](https://ai.google.dev/gemini-api/docs/pricing), [grounding](https://ai.google.dev/gemini-api/docs/google-search) |
| **Bright Data** | 5K requests/month free | PAYG **$1.5/1k** successful requests; $499/mo = 380K included, $1.3/1k beyond | successful request | card | Failed requests are not billed; SERP scraping rather than an index | [product](https://brightdata.com/products/serp-api), [pricing/serp](https://brightdata.com/pricing/serp) |
| **Search1API** | 100 credits | Basic $19 = 25,000 credits (≈$0.76/1k); Pro $99 = 150,000 (≈$0.66/1k); Ent $499 = 1M | credit — search = 1, agentic = 5, deepcrawl = 20 | key | Cheap at volume; multi-engine routing; MCP/CLI/skills interfaces | [search1api.com/pricing](https://www.search1api.com/pricing) |
| **Firecrawl** | 1,000 credits/mo, no card | Hobby $19/mo = 5,000 credits/mo (2,500 searches or 5,000 scrapes) | credit — search = 2 credits per 10 results | no card for free | Scrape-first product; search is a bolt-on | [firecrawl.dev/pricing](https://firecrawl.dev/pricing) |
| **Brave** | **$5 free credits every month** | Answers $4 / 1k requests + $5 per 1M tokens; Search plan 50 QPS | query | **card required even for the free plan** (anti-fraud, not charged) | Independent index; per-1k Search rate sits in a JS-rendered card and was not extractable | [brave.com/search/api](https://brave.com/search/api/) |
| **Perplexity** | not stated | Agent tool `web_search` **$0.0025 per invocation** (web) / $0.001 (fast) + model tokens | invocation + tokens | key | Cheap tool call; Sonar token rates dominate real cost | [docs.perplexity.ai](https://docs.perplexity.ai/getting-started/pricing) |
| **OpenAI** | not stated | Web search **$10 / 1k calls** + search content tokens at model rates; non-reasoning preview $25 / 1k with free tokens | call + tokens | API key or Codex login | Token cost dominates at scale | [developers.openai.com](https://developers.openai.com/api/docs/pricing) |
| **SerpApi** | 250 searches/mo (50/hr) | Starter $25/mo = 1,000 searches (200/hr) → **$25 / 1k** at entry | search | card | Best result-shape fidelity, worst entry price | [serpapi.com/pricing](https://serpapi.com/pricing) |
| **Valyu** | not stated | DeepResearch per task: Fast $0.10, Standard $0.50, Heavy $2.50, Max $15; screenshots $0.05/URL, code exec $0.10/run | task / retrieval | key | Search API is priced per retrieval *by data source* — no flat rate | [valyu.ai/pricing](https://www.valyu.ai/pricing) |
| **Kagi** | none for API | **$12 / 1k requests**; Extract $4 / 1k pages; invoiced every 30 days or at $100 | request | paid Kagi account | Premium index, premium price, no free tier | [kagi.com/api/pricing](https://kagi.com/api/pricing) |
| **Jina** | Reader free, rate-limited | API key raises limits; limits are RPM and TPM per IP or key | request | optional key | Fetching/reading utility rather than a general search vendor; the numeric rate table did not extract | [reader](https://jina.ai/reader/), [api pricing](https://jina.ai/api-dashboard/pricing/) |
| **SearXNG** | **Free, self-hosted** | n/a — your own instance | — | none | JSON output must be enabled in `settings.yml` or the request returns 403; many public instances disable it | [docs.searxng.org](https://docs.searxng.org/dev/search_api.html) |
| **Serper** | **not retrievable** — the homepage is JavaScript-only and `/pricing` returns 404 | *secondary source only:* $1.00 / 1k at the $50 pack, $0.30 / 1k at $3,750; prepaid credits expire after 6 months | query | card | Cheap headline price, but credits dying after six months is a real trap. Treat as unverified | [serper.dev](https://serper.dev/) (fetched; contains no pricing text) |
| **Serply** | not stated | *vendor's own chart:* $49/mo ($0.98 / 1k); $5 Micro pack; it claims Bright Data $1.50/1k, Firecrawl $1.66/1k, SerpApi $7.25/1k | query | card | Self-published comparison against named competitors — self-serving, though the Bright Data figure matches that vendor's own page | [serply.io/pricing](https://serply.io/pricing) |

## Providers with no verifiable public pricing

Named so the table's edge is explicit, not hidden: **Searchinfinity**, **Querit** (page
unextractable), **SERPdive**, **Anysearch**, **XCrawl**, **Baizhi**, **Keenable**, **SerpBase** (fetch
failed), **Z.ai** (page carries model token pricing but no search-tool price), **Bocha** (no pricing
text found on site), **Kimi / Moonshot** (model token pricing only), **Mistral** (documentation URL
404s), **xAI** (documents the `web_search` tool but publishes no price on the pages fetched),
**Ollama** (local runtime, not a search vendor), **degoog** and **DuckDuckGo** (no official commercial
API; these are scrapers or self-hosted frontends), **Parallel MCP** (same vendor as Parallel).

## Three caveats that matter more than the price column

1. **Units are not comparable across rows.** "1 credit", "1 request", "1 call", and "per 10 results"
   are different quantities, and several vendors bill calls *plus* model tokens. Any per-1k ranking
   across rows would be this note's arithmetic rather than the vendors' published price, so it is not
   given here.
2. **Free tiers are for evaluation, not production.** You.com and Exa need no key at all; Brave
   demands a card even for its free plan; and a free path that carried real research work in this
   session (Exa's free MCP endpoint) still returned `429` under load — see the appendix.
3. **Shortlist by profile.** Keyless prototype → You.com. Cheapest at volume → Parallel or TinyFish.
   Best agent ergonomics with no card → Tavily. Already on Gemini → grounding on the paid tier.
   True zero-cost → SearXNG, accepting the ops burden. Quality-and-pay-accordingly → Kagi or SerpApi.

## Grounding with Google Search: subscription vs API tier

Grounding is not sold as an add-on subscription. It requires the Gemini API **Paid Tier**, and a
consumer **Google AI Pro / Ultra subscription does not unlock it for API keys**. Google's own plans
document is explicit that Pro and Ultra exist to raise limits in AI Studio:

> "Google AI Pro and Ultra subscription plans provide greater model access and increased rate limits
> for prototyping and development in AI Studio compared to the free tier." … "When daily baseline
> subscription quotas are exhausted in AI Studio, you can continue your workflows using a Gemini API
> key with Cloud Billing enabled for pay-per-request usage of the Gemini API directly."
> — [Google AI plans](https://ai.google.dev/gemini-api/docs/google-ai-plans)

| Surface | Grounding with Google Search | Cost | Requirement |
|---|---|---|---|
| Gemini API — Free Tier (active project, no billing) | **Not available** — the pricing tables read "Not available" in the Free Tier column for both Gemini 3.x and 2.5 models | — | API key only; grounding excluded |
| Google AI Studio (web Playground / Build) | **Testable** — pricing footnote: "Can be tested in Google AI Studio" | Within the AI Studio plan quota | Google account; AI Pro/Ultra raise that quota |
| Gemini API — Paid Tier | Available | 5,000 free search requests/month (Gemini 3+), then **$14 / 1k requests**; older models 1,500 RPD free, then **$35 / 1k grounded prompts** | Link an active billing account and prepay **≥ $5** |
| Vertex AI | Available | First 5,000/month **$0.00** per account/month, then **$14 / 1k** | GCP billing |

Sources: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) (tier tables and
footnotes), [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
(per-query billing model), [Billing](https://ai.google.dev/gemini-api/docs/billing) (Free/Tier 1–3
qualification and the ≥$5 prepay), [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing).

One consolation for subscribers: "Subscribers with Google Cloud Platform (GCP) projects and Cloud
Billing enabled are eligible to receive monthly Cloud credits from the Google Developer Program for
Cloud services, including the Gemini API" — those credits apply once billing is enabled, and eligible
credits are consumed first ([Google AI plans](https://ai.google.dev/gemini-api/docs/google-ai-plans)).

## Appendix: what this harness could actually call on 2026-10-15

Recorded because it is the practical counterweight to the free-tier column. During research run
`05b335c0-8337-4b11-9737-05e2e267d1c6` (68 `web_search` invocations) the observed provider outcomes were:

| Provider | Outcome | Queries affected |
|---|---|---|
| Tavily | `Tavily API key not found` | 8 |
| Brave | `Brave Search API key not found` | 8 |
| OpenAI | `OpenAI web search unavailable` (no Codex login, no `OPENAI_API_KEY`) | 3 |
| Exa | `Exa MCP rate limit reached (429)` on the free endpoint | 5 |
| Exa | succeeded | 3 |
| — | provider reported as `unknown` (no results) | 5 |

No `/var/home/kai/.pi/agent/web-search.json` existed and no provider API-key environment variables
were set, which is why the one working path was Exa's keyless free MCP endpoint — itself rate-limited.
Tavily, Brave, OpenAI, and Exa are all eligible providers in this harness; the failures were
credentials and quota, not policy. The practical fix for a later pass is a single key in
`/var/home/kai/.pi/agent/web-search.json` (for example `{ "exaApiKey": "…" }`), which lifts the free
MCP limit.

## Sources

Kept (primary, fetched this session): vendor pricing pages linked in each row above
(`you.com/pricing`, `tinyfish.ai/pricing`, `parallel.ai/pricing`, `tavily.com/pricing`,
`docs.tavily.com/documentation/api-credits`, `exa.ai/pricing`, `firecrawl.dev/pricing`,
`brave.com/search/api/`, `serpapi.com/pricing`, `kagi.com/api/pricing`, `jina.ai` reader and API
pricing, `you.com/pricing`, `brightdata.com` product and `/pricing/serp`, `search1api.com/pricing`,
`valyu.ai/pricing`, `docs.searxng.org/dev/search_api.html`, `docs.perplexity.ai/getting-started/pricing`,
`developers.openai.com/api/docs/pricing`, `ai.google.dev` pricing / grounding / billing / plans,
`cloud.google.com/vertex-ai/generative-ai/pricing`), plus the harness run log for the appendix.

Rejected as evidence: search-engine snippets, the Serply competitor chart (used only as a labelled
vendor claim), and a third-party Serper price summary (labelled secondary; Serper's own site publishes
no machine-readable pricing).

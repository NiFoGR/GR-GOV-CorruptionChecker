# GR-GOV-CorruptionChecker — Plan

A public-spending analysis site for Greek government publications: ingest what the
state is legally required to publish, reduce it to structured spending records, run
deterministic red-flag rules over it, and publish the findings with links back to the
primary source.

---

## 0. The reframe (read this first)

The instinct is "point an AI at every government publication and let it find the
corruption." That does not work, for three reasons:

1. **Volume.** Diavgeia takes in thousands of acts *per day*. An LLM pass over every
   document is expensive, slow, and mostly wasted — the overwhelming majority of acts
   are routine and unremarkable.
2. **The signal is already structured.** Spending acts carry machine-readable metadata:
   amount, VAT, the awarding body, the contractor's tax ID (ΑΦΜ), CPV code, procedure
   type. The strongest corruption signals are **SQL queries over that table**, not
   reading comprehension. Contract splitting is a `GROUP BY buyer, supplier, cpv`. An
   LLM adds nothing and hallucinates.
3. **"Is this corrupt?" is not a question a model may answer in public.** It is a
   defamation claim about named people and companies. See §6.

So the shape is: **cheap deterministic rules over structured data at full scale → LLM
only on the narrow slice where free text actually matters → human review before
anything is published as a claim.**

The product is not an AI. The product is a clean spending database plus a well-tuned
rule set.

---

## 1. Data sources, ranked by value per unit of effort

| # | Source | What it gives | Access | Priority |
|---|--------|---------------|--------|----------|
| 1 | **Διαύγεια (Diavgeia)** | Every act by every public body, incl. expenditure approvals, commitments, awards, payment finalisations. Structured metadata + PDF. CC-BY licensed. | Open REST API, no auth for reads | **Core** |
| 2 | **ΚΗΜΔΗΣ (KIMDIS)** | Central registry of public contracts: tender notices, awards, contracts, amendments. Aligned to **OCDS** + EU eForms. Daily refresh. | Open Data REST API, no credentials needed | **Core** |
| 3 | **ΓΕΜΗ (GEMI)** business registry | Company incorporation date, directors, registered address, share capital. This is what turns a supplier ΑΦΜ into a *story*. | Partly open, partly paid/scraped | High |
| 4 | **data.gov.gr** | Assorted government datasets, incl. budget and Diavgeia-derived sets | API token, free | Medium |
| 5 | **TED / EU Tenders** | EU-threshold tenders, cross-check against KIMDIS | Open API | Medium |
| 6 | **Ελεγκτικό Συνέδριο / ΕΑΔ reports** | Confirmed past findings — your **ground truth for tuning** | PDFs, manual | High (small) |
| 7 | Municipal budget/balance sheets | Denominator for concentration metrics | Scattered | Later |

> **Environment note:** the sandbox this plan was written in has an outbound network
> policy that blocks `diavgeia.gov.gr`, so the endpoints below have **not been live
> tested from here**. First implementation task is to confirm response shapes and paging
> limits from an unrestricted machine.

---

## 2. Simplest architecture that actually works

Deliberately boring. No Kafka, no Elasticsearch, no vector DB, no graph DB at MVP.

```
  Diavgeia API ─┐
  KIMDIS API   ─┼─→ [ Python ingest workers ] ─→ Postgres (raw tables)
  GEMI         ─┘         (httpx + pydantic)          │
                                                      ▼
                                          [ normalise → spending_facts ]
                                                      │
                                                      ▼
                                          [ rule SQL views → flags ]
                                                      │
                                     ┌────────────────┴────────────────┐
                                     ▼                                 ▼
                          [ LLM enrichment ]                  [ Next.js site ]
                       (only on flagged rows)              org pages, supplier
                        PDF extract, justification          pages, flag feed
                        classification, plain-language
                        summaries → human review queue
```

- **Ingest:** Python, `httpx`, `pydantic`. One worker per source. Idempotent upserts
  keyed on ΑΔΑ (Diavgeia) / KIMDIS ID. Incremental by publication date.
- **Store:** a single Postgres (Neon or Supabase free tier is plenty to start).
  `raw_*` tables keep the untouched API payload as `jsonb`; never re-fetch to re-parse.
- **Transform:** plain SQL views/materialised views. Add dbt only if it hurts without it.
- **Rules:** each rule is one SQL view emitting `(entity, rule_id, severity, evidence_json)`.
- **Serve:** Next.js reading Postgres directly. Static-generate the heavy pages.
- **Schedule:** GitHub Actions cron for daily ingest. No orchestrator needed at this size.
- **Cost:** effectively €0 except LLM calls on the flagged slice and eventually a domain.

---

## 3. The red-flag rules — this is the actual product

Each is cheap, deterministic, explainable, and cites its evidence. Ordered roughly by
signal strength.

**Threshold games**
- **Bunching below the direct-award ceiling.** Under art. 118 N.4412/2016 (as amended by
  N.4782/2021) direct award is capped at **€30,000 excl. VAT** for supplies/services,
  with a higher ceiling for certain ICT contracts. *Verify the current figure before
  coding — it has moved and will move again; store it as a dated config, not a
  constant.* Build a histogram of award values per buyer; a spike in the last few
  percent below the ceiling is the single most reliable indicator in the dataset.
- **Contract splitting (κατάτμηση).** Explicitly prohibited. Same buyer + same supplier +
  same/adjacent CPV within a rolling window (30/90/365 days), summing above the ceiling
  while each part sits below it.

**Competition failures**
- Single-bidder outcomes on procedures that should have drawn several.
- Repeat direct awards: supplier X wins ≥ N direct awards from buyer Y in a year.
- Supplier concentration: one supplier takes >X% of a buyer's addressable spend.
- Emergency/negotiated-without-publication procedure used far above the peer-group rate.

**Entity signals** (requires the GEMI join — highest journalistic value)
- Company incorporated < 12 months before winning a substantial contract.
- Suppliers sharing a registered address, phone, or director with a competing bidder
  (collusion signal) — or with an official of the awarding body (conflict of interest).
- Dormant company suddenly winning at scale.

**Price and timing**
- Unit price outliers vs the national median for the same CPV.
- Award granted implausibly soon after the notice was published.
- Contract value creeping upward through post-award amendments/extensions.
- Suspiciously round figures clustering at a ceiling.

**Hygiene / compliance**
- Contracts in KIMDIS with no corresponding Diavgeia act, or vice versa.
- Payments exceeding the committed amount.
- Late publication beyond the statutory deadline.

Every rule ships with: a plain-language description, the legal or statistical basis, a
false-positive rate measured against §7 ground truth, and a link to every source
document.

---

## 4. Where the LLM belongs (and where it does not)

**Yes:**
- **PDF/text extraction** where metadata is thin — many acts carry the real number only
  in the document body. Extraction to a strict schema, with confidence scores.
- **Classifying stated justifications** for emergency procedures against the statutory
  criteria — "does the stated reason match a permitted ground, yes/no/unclear."
- **Normalising** messy free-text supplier names to ΑΦΜ.
- **Plain-language summaries** of flagged clusters, for the human reviewer — labelled as
  draft, never auto-published.

**No:**
- "Is this corrupt?" / "Did someone take a bribe?"
- Any output about a named person or company published without human sign-off.
- Scoring officials for trustworthiness.
- Replacing a rule that SQL can express exactly.

Rule of thumb: **the LLM extracts and describes; it never accuses.**

---

## 5. Scope the MVP hard

Do not try to cover the whole Greek state in v1. The highest-yield tractable slice:

> **All municipalities (δήμοι), direct awards only, most recent complete year.**

Clear legal thresholds, comparable peer entities (a municipality can be benchmarked
against similar-sized municipalities), high base rate of problems, and manageable
volume. Prove the rules there, then widen to ministries, hospitals (ΥΠΕ — historically
rich territory), and regions.

---

## 6. Legal and ethical guardrails — non-negotiable

This is the part that decides whether the project survives contact with reality.

- **An anomaly is not a crime.** Never publish "X is corrupt." Publish the fact and the
  statistic: *"This buyer's awards cluster in the top 1% for threshold proximity
  nationally,"* with links to every source act. Let the reader draw the conclusion.
- **Defamation exposure is real.** Συκοφαντική δυσφήμηση is a criminal matter in Greece,
  and companies do sue. Neutral language, statistical framing, primary-source links,
  and a documented methodology page are your defence.
- **Right of reply.** A published contact address, a stated correction policy, and a
  visible response turnaround. Publish rebuttals alongside the flags.
- **GDPR.** The data being public does not make republishing it at scale for a new
  purpose automatically lawful. Working rule: **legal persons in, natural persons out.**
  Exclude or aggregate individual grant recipients, salaries, and benefit payments;
  keep companies. Named public officials only in their official capacity.
- **Human in the loop before publication.** No rule output goes live unreviewed in v1.
- **Publish the methodology and the false-positive rate.** Credibility is the whole
  asset; one loud wrong accusation ends the project.

Get a Greek lawyer to read the methodology page and the publication policy *before*
launch, not after the first letter arrives.

---

## 7. Phases

**Phase 0 — Verify (a few days)**
Confirm Diavgeia and KIMDIS endpoints, auth, paging limits, rate limits, and actual
response shapes from an unrestricted machine. Pull one day of data by hand. Confirm
which fields are reliably populated vs usually empty — this determines everything
downstream. Register for a data.gov.gr token.

**Phase 1 — Ingest**
Diavgeia + KIMDIS ingest workers, raw `jsonb` tables, incremental daily backfill for the
target year. Success test: the row count reconciles against the portals' own published
totals.

**Phase 2 — Normalise**
One `spending_facts` table: buyer, supplier ΑΦΜ, amount excl./incl. VAT, CPV, procedure
type, dates, source IDs. Entity resolution on suppliers. This is the hard, unglamorous
step and the one everything else depends on.

**Phase 3 — Rules**
Implement §3 starting with threshold bunching and splitting. Tune against §7 ground
truth: take known confirmed cases from Ελεγκτικό Συνέδριο / ΕΑΔ reports and check the
rules actually fire on them, and measure how often they fire on clean cases.

**Phase 4 — Site**
Org pages, supplier pages, a flag feed, and a methodology page. Every number links to
its source act. Ship read-only and boring.

**Phase 5 — LLM enrichment**
PDF extraction for thin-metadata acts; justification classification; reviewer summaries.

**Phase 6 — Entity graph**
GEMI join: incorporation dates, directors, shared addresses. Where the real stories are.

---

## 8. What I need from you

**Decisions**
1. **Scope** — confirm the MVP slice (municipalities / direct awards / which year), or
   name a different one.
2. **Public or private?** A public site and a personal analysis tool have very different
   legal footprints. This changes §6 materially.
3. **Language** — Greek, English, or both. Affects the UI and the LLM prompts.
4. **Name and domain.**
5. **Are you the publisher personally, or behind a legal entity?** Matters for liability.

**Accounts and keys**
6. Postgres — Neon or Supabase, free tier (or tell me you'd rather self-host).
7. Anthropic API key — for Phase 5 only, not needed before then.
8. data.gov.gr API token — free, self-service registration.
9. Hosting — Vercel for the site, GitHub Actions for cron. Both free at this size.
10. Confirm this GitHub repo is where it all lives.

**Inputs only you can supply**
11. **Ground truth cases** — any known confirmed findings (Ελεγκτικό Συνέδριο, ΕΑΔ,
    press investigations) with the buyer and year. Even 10–20 cases transform rule
    tuning from guesswork into measurement. Highest-value thing on this list.
12. **Current legal thresholds** — the direct-award ceilings in force for each year you
    cover. They have changed; the analysis is wrong if these are wrong.
13. **Do you read Greek legal/administrative text fluently?** Determines how much human
    review is realistic and how much the pipeline must carry.
14. **Time budget** — hours per week, solo or with others. Phase 2 and human review are
    the parts that consume real time.
15. **Any prior art you already know of** — several Greek transparency projects exist;
    worth not rebuilding what works.

**Recommended, not required**
16. A Greek lawyer's read on the methodology and publication policy before going public.
17. A contact address for right-of-reply.

---

## 9. Honest risks

- **Data quality is the real enemy, not scale.** Free-text supplier names, missing ΑΦΜ,
  amounts only inside PDFs, inconsistent CPV coding. Phase 2 will take longer than
  Phases 1, 3, and 4 combined. Budget for it.
- **False positives are existential.** Most threshold bunching is lazy administration,
  not theft. The rules find *questions*, not answers.
- **KIMDIS↔Diavgeia reconciliation is genuinely hard** — the same contract appears in
  both with different identifiers and different values.
- **Legal pressure is a question of when, not if,** if the site is public and any good.
  Methodology page, neutral language, and right of reply are the armour.
- **Scope creep kills this.** "All Greek government publications" is not a v1. One
  slice, done properly, beats full coverage done badly.

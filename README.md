# Greek Public Spending Watch

Reads every award decision published by Greek public bodies on
[Διαύγεια](https://diavgeia.gov.gr), applies red-flag rules, and publishes the
results as a static site.

**No servers, no database, no accounts, no cost.** GitHub Actions does the
scraping on a schedule, commits the results as JSON, and GitHub Pages serves the
page. Everything lives in this repository.

```
GitHub Actions (daily cron)
  └─ scripts/fetch.py    → Diavgeia OpenData API → data/raw/awards.json
  └─ scripts/analyze.py  → red-flag rules        → docs/data/flags.json
        └─ GitHub Pages serves docs/  (plain HTML, no build step)
```

## Turning it on

One click, once: **Settings → Pages → Source → GitHub Actions**.
Then the daily scan publishes to `https://nifogr.github.io/GR-GOV-CorruptionChecker/`.

That's the only setup step. Diavgeia's API needs no key.

## Running it locally

Standard library only, no dependencies:

```bash
python scripts/fetch.py      # writes data/raw/awards.json
python scripts/analyze.py    # writes docs/data/flags.json
python -m http.server -d docs
```

`SCAN_DAYS` controls the look-back window (default 120).

## The rules

| Rule | What it looks for |
|---|---|
| `threshold_proximity` | Awards priced in the top 10% below the €30,000 direct-award ceiling |
| `contract_splitting` | Same buyer + supplier + CPV class within 90 days, each below the ceiling but together above it (*κατάτμηση*, explicitly prohibited) |
| `supplier_concentration` | One supplier holding ≥5 awards and ≥50% of a buyer's award value |
| `round_number` | Exact multiples of €1,000 — corroborating only, reported solely on awards another rule already flagged, since public budgets are routinely round |

Each is a plain function in [`scripts/analyze.py`](scripts/analyze.py). Adding a
rule means adding a function to the `RULES` list (or `CORROBORATING_RULES` for
signals too common to stand alone).

## What this is not

A flag is a **question**, not an accusation. These rules find patterns that
*can* indicate a problem and frequently don't — routine purchasing, urgent
repairs, or a small local market with one real supplier all produce the same
statistical shape as misconduct.

The site publishes facts and statistics with links to the source document, and
never a claim that anyone did something wrong. That framing is not decoration:
defamation is a criminal matter in Greece, and the project's credibility is its
only real asset. See [`docs/methodology.html`](docs/methodology.html) for the
limitations, including an unresolved VAT ambiguity that affects the threshold rule.

## Known gaps

- **Awards only** — not payments, amendments, or tender notices.
- **Recent window only** — the API's default six-month submission window blocks
  simple historical backfill. See [`PROBE-NOTES.md`](PROBE-NOTES.md).
- **No supplier ownership data** — the ΓΕΜΗ business registry join (incorporation
  dates, directors, shared addresses) is where the strongest signals are, and it
  isn't wired up yet.
- **Rules are untuned** — thresholds are reasoned, not calibrated against
  confirmed cases. Expect false positives.

## API notes

[`PROBE-NOTES.md`](PROBE-NOTES.md) records what was verified against the live API,
including two traps: malformed filters are silently ignored rather than rejected,
and a hidden six-month window is ANDed onto every date query.

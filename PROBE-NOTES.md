# Diavgeia OpenData API — verified notes

Established by running `scripts/probe.py` against the live API from GitHub Actions
on 2026-07-27. Recorded because several of these are not obvious and one is a trap.

## Basics

- Base: `https://diavgeia.gov.gr/opendata`
- **No authentication** for reads. Data is CC-BY.
- `GET /search.json` returns `{"info": {...}, "decisions": [...]}`
- `info` = `{query, page, size, actualSize, total, order}`; `page` is 0-indexed
- `size` up to **500** confirmed working
- `GET /types.json` — 43 decision types
- `GET /organizations.json` — full registry, ~2.1 MB; the `size` param is **ignored**

## Traps

**A malformed filter is silently ignored.** `?q=decisionTypeUid:"Δ.2.3"` returned
all 3.1 M decisions with HTTP 200 rather than erroring. Any filter must be verified
by checking the returned records actually carry the value you asked for —
`scripts/fetch.py` aborts if they don't.

**A default ~6-month submission window is ANDed with your date filter.** The
generated query is:

```
submissionTimestamp:[DT(<6 months ago>) TO DT(<now>)]
  AND issueDate:[DT(<6 months ago>) TO DT(<now>)]
  AND status:"Αναρτημένη"
```

Passing `from_issue_date`/`to_issue_date` overrides only the `issueDate` half.
Asking for a single day more than six months back returns near-nothing (one test
day in 2025 returned 8 awards nationally — those are late submissions, not the
real total). Historical backfill needs the submission-window params too; this has
not been solved yet.

## Filters

| Param | Works | Note |
|---|---|---|
| `?type=Δ.1` | **yes** | verified: all returned records carry that type |
| `?q=decisionTypeId:Δ.1` | no | silently ignored |
| `?from_issue_date=` / `?to_issue_date=` | **yes** | `YYYY-MM-DD` |
| `?from_date=` / `?to_date=` | no | returns `total: 0` |

## Decision types that carry money

| ID | Greek | English | Money fields |
|---|---|---|---|
| `Δ.1` | ΑΝΑΘΕΣΗ ΕΡΓΩΝ / ΠΡΟΜΗΘΕΙΩΝ / ΥΠΗΡΕΣΙΩΝ / ΜΕΛΕΤΩΝ | Award | `awardAmount`, `person[]`, `cpv[]` |
| `Β.2.1` | ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ | Expenditure approval | `sponsor[].expenseAmount`, `org` |
| `Β.2.2` | ΟΡΙΣΤΙΚΟΠΟΙΗΣΗ ΠΛΗΡΩΜΗΣ | Payment finalisation | `org`, `sponsor` |
| `Β.1.3` | ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ | Commitment | not yet probed |
| `Δ.2.2` | ΚΑΤΑΚΥΡΩΣΗ | Contract award confirmation | not yet probed |
| `Γ.3.4` | ΣΥΜΒΑΣΗ | Contract | not yet probed |

Note `Δ.2.3` does **not** exist — the award type is `Δ.1`.

## Δ.1 record shape

```json
{
  "ada": "Ρ2Γ6469Β7Δ-ΤΛ4",
  "decisionTypeId": "Δ.1",
  "organizationId": "99206924",
  "issueDate": 1785110400000,
  "subject": "...",
  "documentUrl": "https://diavgeia.gov.gr/doc/Ρ2Γ6469Β7Δ-ΤΛ4",
  "extraFieldValues": {
    "person": [{"afm": "084065149", "name": "ΘΩΜΟΠΟΥΛΟΣ ΑΛΕΒΙΖΟΣ ΟΕ", "afmType": "EL"}],
    "awardAmount": {"amount": 1854.56, "currency": "EUR"},
    "assignmentType": "Προμήθειες",
    "cpv": ["33790000-4"]
  }
}
```

Dates are epoch milliseconds. `organizationId` joins to `organizations.json`
(`uid` → `label`, `vatNumber`, `supervisorLabel` = parent body).

**Unresolved:** whether `awardAmount` includes VAT. The €30,000 direct-award
ceiling is defined excluding VAT, so this materially affects the threshold rule.
`analyze.py` currently tests both bands and labels which matched.

## Scale

~3.1 M decisions per rolling six months, all types.
`Β.2.2` ≈ 1.2 M, `Β.2.1` ≈ 192 k over the same window.

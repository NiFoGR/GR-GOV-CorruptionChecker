"""Apply red-flag rules to fetched award decisions.

Every rule is deterministic and explainable. A flag is a QUESTION worth asking,
never an allegation — see docs/methodology.html.

Reads:  data/raw/awards.json
Writes: docs/data/flags.json
"""

import json
import pathlib
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "awards.json"
OUT = ROOT / "docs" / "data" / "flags.json"

# Direct-award ceiling, art. 118 N.4412/2016 as amended by N.4782/2021.
# Stated exclusive of VAT. Diavgeia's awardAmount does not reliably say whether
# the figure it carries includes VAT, so we test both bands and label which one
# matched — see methodology. Revisit if the statutory figure changes.
THRESHOLD = 30_000.0
VAT_RATE = 0.24
THRESHOLD_INC_VAT = THRESHOLD * (1 + VAT_RATE)

NEAR_BAND = 0.90          # flag awards in [90%, 100%] of a ceiling
SPLIT_WINDOW_DAYS = 90    # look-back for aggregating related awards
CONCENTRATION_MIN = 5     # awards to one supplier from one buyer before flagging
CONCENTRATION_SHARE = 0.5 # ...or this share of the buyer's total value
MAX_PUBLISHED_FLAGS = 2000  # keep the static JSON small; stats report the true total


def ts_to_date(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def load():
    if not RAW.exists():
        raise SystemExit(f"No raw data at {RAW}. Run scripts/fetch.py first.")
    return json.loads(RAW.read_text(encoding="utf-8"))


def normalise(payload):
    """Flatten API decisions into plain award records."""
    orgs = payload.get("organizations") or {}
    records = []
    for d in payload.get("decisions") or []:
        efv = d.get("extraFieldValues") or {}
        amount_obj = efv.get("awardAmount") or {}
        amount = amount_obj.get("amount")
        if amount is None or amount_obj.get("currency") not in (None, "EUR"):
            continue  # no comparable money figure

        people = efv.get("person") or []
        supplier = people[0] if people else {}
        org_id = d.get("organizationId")
        org = orgs.get(org_id) or {}

        records.append({
            "ada": d.get("ada"),
            "date": (ts_to_date(d.get("issueDate")) or ts_to_date(d.get("publishTimestamp"))),
            "amount": float(amount),
            "buyer_id": org_id,
            "buyer": org.get("name") or f"Organisation {org_id}",
            "buyer_parent": org.get("parent"),
            "supplier": supplier.get("name"),
            "supplier_afm": supplier.get("afm"),
            "cpv": (efv.get("cpv") or [None])[0],
            "kind": efv.get("assignmentType"),
            "subject": d.get("subject"),
        })
    return records


# ---------------------------------------------------------------- rules

def rule_threshold_proximity(records):
    """Awards priced just under a direct-award ceiling.

    Bunching immediately below a legal ceiling is the strongest single
    indicator in this dataset: it suggests the price was chosen to stay
    inside the direct-award regime rather than derived from the work.
    """
    flags = []
    for r in records:
        for ceiling, label in ((THRESHOLD, "excl. VAT"), (THRESHOLD_INC_VAT, "incl. VAT")):
            if ceiling * NEAR_BAND <= r["amount"] <= ceiling:
                pct = r["amount"] / ceiling
                flags.append({
                    **base_flag(r),
                    "rule": "threshold_proximity",
                    "rule_label": "Priced just under the direct-award limit",
                    "severity": "high" if pct >= 0.97 else "medium",
                    "detail": (f"€{r['amount']:,.0f} is {pct:.1%} of the €{ceiling:,.0f} "
                               f"direct-award ceiling ({label})."),
                })
                break
    return flags


def rule_contract_splitting(records):
    """One requirement broken into several sub-ceiling awards (κατάτμηση).

    Same buyer, same supplier, same CPV class, inside a rolling window:
    each award sits below the ceiling but together they exceed it.
    Splitting a contract to avoid a tender is explicitly prohibited.
    """
    groups = defaultdict(list)
    for r in records:
        if r["supplier_afm"] and r["cpv"] and r["amount"] < THRESHOLD and r["date"]:
            groups[(r["buyer_id"], r["supplier_afm"], r["cpv"][:5])].append(r)

    flags = []
    for (_, _, cpv5), items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: x["date"])
        for i, anchor in enumerate(items):
            window = [x for x in items[i:] if x["date"] - anchor["date"] <= timedelta(days=SPLIT_WINDOW_DAYS)]
            total = sum(x["amount"] for x in window)
            if len(window) >= 2 and total > THRESHOLD:
                flags.append({
                    **base_flag(anchor),
                    "rule": "contract_splitting",
                    "rule_label": "Repeat awards that together pass the limit",
                    "severity": "high",
                    "amount": round(total, 2),
                    "detail": (f"{len(window)} awards to the same supplier for CPV {cpv5}x "
                               f"within {SPLIT_WINDOW_DAYS} days total €{total:,.0f}, above the "
                               f"€{THRESHOLD:,.0f} ceiling, while each stays below it. "
                               f"Related: {', '.join(x['ada'] for x in window[:6])}"),
                })
                break  # one flag per group
    return flags


def rule_supplier_concentration(records):
    """One supplier taking an outsized share of a single buyer's awards."""
    by_buyer = defaultdict(list)
    for r in records:
        if r["supplier_afm"]:
            by_buyer[r["buyer_id"]].append(r)

    flags = []
    for _, items in by_buyer.items():
        buyer_total = sum(x["amount"] for x in items)
        if buyer_total <= 0:
            continue
        per_supplier = defaultdict(list)
        for x in items:
            per_supplier[x["supplier_afm"]].append(x)

        for _, sup_items in per_supplier.items():
            sup_total = sum(x["amount"] for x in sup_items)
            share = sup_total / buyer_total
            if len(sup_items) >= CONCENTRATION_MIN and share >= CONCENTRATION_SHARE and len(per_supplier) > 1:
                latest = max(sup_items, key=lambda x: x["date"] or datetime.min.date())
                flags.append({
                    **base_flag(latest),
                    "rule": "supplier_concentration",
                    "rule_label": "One supplier dominates this buyer's awards",
                    "severity": "medium",
                    "amount": round(sup_total, 2),
                    "detail": (f"{len(sup_items)} awards worth €{sup_total:,.0f} — {share:.0%} of "
                               f"this body's €{buyer_total:,.0f} in awards over the period."),
                })
    return flags


def rule_round_number(records, flagged_adas):
    """Suspiciously round pricing — only where something else already fired.

    Genuine costed quotes rarely land on an exact thousand, but public budgets
    are written in round figures, so on its own this matches a large share of
    all awards and drowns out the real signal. It is only informative as a
    corroborating detail, so it is scoped to awards another rule already flagged.
    """
    flags = []
    for r in records:
        if r["ada"] in flagged_adas and r["amount"] >= 10_000 and r["amount"] % 1000 == 0:
            flags.append({
                **base_flag(r),
                "rule": "round_number",
                "rule_label": "Also an exactly round amount",
                "severity": "low",
                "detail": f"€{r['amount']:,.0f} is an exact multiple of €1,000.",
            })
    return flags


def base_flag(r):
    return {
        "ada": r["ada"],
        "date": r["date"].isoformat() if r["date"] else None,
        "amount": r["amount"],
        "buyer": r["buyer"],
        "supplier": r["supplier"],
        "supplier_afm": r["supplier_afm"],
        "cpv": r["cpv"],
        "subject": r["subject"],
    }


# Primary rules stand alone. Corroborating rules only fire on awards a primary
# rule already flagged, so they add detail instead of noise.
RULES = [
    rule_threshold_proximity,
    rule_contract_splitting,
    rule_supplier_concentration,
]
CORROBORATING_RULES = [
    rule_round_number,
]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def main():
    payload = load()
    records = normalise(payload)
    print(f"Normalised {len(records)} awards with a usable amount "
          f"(from {len(payload.get('decisions') or [])} decisions)")

    flags = []
    for rule in RULES:
        found = rule(records)
        print(f"  {rule.__name__}: {len(found)} flags")
        flags.extend(found)

    flagged_adas = {f["ada"] for f in flags}
    for rule in CORROBORATING_RULES:
        found = rule(records, flagged_adas)
        print(f"  {rule.__name__}: {len(found)} flags (corroborating)")
        flags.extend(found)

    flags.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), -(f.get("amount") or 0)))

    # The site is a static page, so every visitor downloads this file whole.
    # Publish the most serious flags and report the true total in stats.
    published = flags[:MAX_PUBLISHED_FLAGS]
    if len(flags) > len(published):
        print(f"  publishing top {len(published)} of {len(flags)} flags to keep the page light")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": payload.get("window"),
        "stats": {
            "decisions": len(records),
            "flags": len(flags),
            "flags_published": len(published),
            "total_amount": round(sum(r["amount"] for r in records), 2),
            "organisations": len({r["buyer_id"] for r in records}),
            "suppliers": len({r["supplier_afm"] for r in records if r["supplier_afm"]}),
        },
        "flags": published,
    }, ensure_ascii=False), encoding="utf-8")

    size_kb = OUT.stat().st_size / 1024
    print(f"\nWrote {len(published)} flags to {OUT.relative_to(ROOT)} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()

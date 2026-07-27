"""Fetch award decisions (Δ.1) from the Diavgeia OpenData API.

Verified against the live API (see PROBE-NOTES.md):
  - https://diavgeia.gov.gr/opendata/search.json, no authentication
  - ?type=<decisionTypeId> is the working type filter
  - ?from_issue_date / ?to_issue_date are the date params (NOT from_date)
  - size up to 500, page is 0-indexed
  - Δ.1 decisions carry awardAmount, person[].afm, and cpv[] in extraFieldValues

GOTCHA: the API applies a default ~6-month submissionTimestamp window that is
ANDed with whatever issue-date filter you pass. Asking for a single day more
than 6 months back returns almost nothing. This script only scans recent days,
which stays inside that window.

Writes: data/raw/awards.json
"""

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://diavgeia.gov.gr/opendata"
UA = "GR-GOV-CorruptionChecker/0.1 (+https://github.com/NiFoGR/GR-GOV-CorruptionChecker)"

AWARD_TYPE = "Δ.1"       # ΑΝΑΘΕΣΗ ΕΡΓΩΝ / ΠΡΟΜΗΘΕΙΩΝ / ΥΠΗΡΕΣΙΩΝ / ΜΕΛΕΤΩΝ
PAGE_SIZE = 500

# 30 days keeps a nightly run to a few minutes. A 120-day window took over
# 15 minutes against the live API, which is wasteful to repeat every night.
# Raise SCAN_DAYS for a one-off deeper pass; note the splitting rule's 90-day
# look-back can only see as far back as the window actually fetched.
DAYS = int(os.environ.get("SCAN_DAYS", "30"))
MAX_RECORDS = int(os.environ.get("SCAN_MAX_RECORDS", "60000"))

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def api(path, params, retries=4):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            wait = 2 ** attempt
            print(f"    retry {attempt + 1}/{retries} after {type(e).__name__}: {e} (waiting {wait}s)", flush=True)
            if attempt == retries - 1:
                raise
            time.sleep(wait)


def fetch_awards(from_date, to_date):
    """Page through every Δ.1 decision in the window."""
    out, page = [], 0
    while True:
        params = {
            "type": AWARD_TYPE,
            "from_issue_date": from_date.isoformat(),
            "to_issue_date": to_date.isoformat(),
            "size": PAGE_SIZE,
            "page": page,
        }
        data = api("/search.json", params)
        info = data.get("info") or {}
        decisions = data.get("decisions") or []
        total = info.get("total", 0)

        # A malformed filter is silently ignored by this API and returns
        # everything, so verify the server honoured the type filter.
        wrong = {d.get("decisionTypeId") for d in decisions} - {AWARD_TYPE}
        if wrong:
            sys.exit(f"ABORT: type filter ignored, got types {wrong}. Refusing to ingest.")

        out.extend(decisions)
        if page % 10 == 0 or len(decisions) < PAGE_SIZE:
            print(f"  page {page}: {len(out)}/{total} decisions", flush=True)

        page += 1
        if not decisions or len(out) >= total:
            break
        if len(out) >= MAX_RECORDS:
            print(f"  stopping at {len(out)} records (SCAN_MAX_RECORDS); "
                  f"{total} exist in this window", flush=True)
            break
        time.sleep(0.2)
    return out


def fetch_organizations():
    """uid -> {name, vat, parent}. One big payload; the size param is ignored."""
    print("Fetching organization registry…", flush=True)
    data = api("/organizations.json", {})
    orgs = {}
    for o in data.get("organizations") or []:
        orgs[o.get("uid")] = {
            "name": o.get("label"),
            "vat": o.get("vatNumber"),
            "parent": o.get("supervisorLabel"),
            "category": o.get("category"),
        }
    print(f"  {len(orgs)} organizations", flush=True)
    return orgs


def main():
    to_date = date.today()
    from_date = to_date - timedelta(days=DAYS)
    print(f"Scanning {AWARD_TYPE} awards from {from_date} to {to_date}\n", flush=True)

    awards = fetch_awards(from_date, to_date)
    orgs = fetch_organizations()

    RAW.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "decision_type": AWARD_TYPE,
        "organizations": orgs,
        "decisions": awards,
    }
    path = RAW / "awards.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    mb = path.stat().st_size / 1e6
    print(f"\nWrote {len(awards)} decisions to {path.relative_to(ROOT)} ({mb:.1f} MB)")

    with_amount = sum(1 for d in awards
                      if ((d.get("extraFieldValues") or {}).get("awardAmount") or {}).get("amount") is not None)
    with_afm = sum(1 for d in awards if (d.get("extraFieldValues") or {}).get("person"))
    if awards:
        print(f"Coverage: {with_amount}/{len(awards)} have an amount "
              f"({100 * with_amount / len(awards):.0f}%), "
              f"{with_afm}/{len(awards)} have a supplier ({100 * with_afm / len(awards):.0f}%)")


if __name__ == "__main__":
    main()

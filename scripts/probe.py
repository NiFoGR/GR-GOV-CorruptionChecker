"""Probe the Diavgeia OpenData API to learn its real response shape.

Run from GitHub Actions (GitHub's network can reach diavgeia.gov.gr).
Prints everything we need to write the real fetcher against facts
instead of guesses.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "https://diavgeia.gov.gr/opendata"
UA = "GR-GOV-CorruptionChecker/0.1 (+https://github.com/NiFoGR/GR-GOV-CorruptionChecker)"


def get(path, label):
    url = f"{BASE}{path}"
    print(f"\n{'=' * 70}\n{label}\n  GET {url}\n{'=' * 70}")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            print(f"  HTTP {r.status}  {len(raw)} bytes  content-type={r.headers.get('content-type')}")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                print(f"  NOT JSON. First 600 chars:\n{raw[:600]}")
                return None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        print(f"  HTTP ERROR {e.code}: {e.reason}\n{body}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
    return None


def outline(obj, prefix="", depth=0):
    """Print the key structure of a JSON object, truncating values."""
    if depth > 3:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                n = len(v)
                print(f"  {prefix}{k}: {type(v).__name__}[{n}]")
                outline(v, prefix + "  ", depth + 1)
            else:
                s = repr(v)
                print(f"  {prefix}{k}: {s[:120]}")
    elif isinstance(obj, list) and obj:
        outline(obj[0], prefix + "[0].", depth + 1)


# 1. Decision types — we need the ID for awards (ΑΝΑΘΕΣΗ) and expenditure approvals.
types = get("/types.json", "1. DECISION TYPES")
if types:
    items = types.get("decisionTypes") or types.get("types") or types
    if isinstance(items, list):
        print(f"\n  {len(items)} decision types:")
        for t in items:
            if isinstance(t, dict):
                uid = t.get("uid") or t.get("id") or ""
                label = t.get("label") or t.get("name") or ""
                print(f"    {uid:<12} {label}")

# 2. Plain search — confirm the endpoint, paging keys, and total count.
search = get("/search.json?size=3", "2. BASIC SEARCH (size=3)")
if search:
    print("\n  TOP-LEVEL STRUCTURE:")
    for k, v in search.items():
        print(f"    {k}: {type(v).__name__}" + (f"[{len(v)}]" if isinstance(v, (list, dict)) else f" = {v!r}"))
    info = search.get("info") or {}
    print(f"\n  INFO BLOCK: {json.dumps(info, ensure_ascii=False)}")

    decisions = search.get("decisions") or []
    if decisions:
        print(f"\n  SAMPLE DECISION (full field outline):")
        outline(decisions[0])
        print(f"\n  RAW SAMPLE:\n{json.dumps(decisions[0], ensure_ascii=False, indent=2)[:3000]}")

# 3. Filtered search — does Lucene-style q work, and does an award type carry money fields?
for q, label in [
    ("decisionTypeUid:%22%CE%94.2.3%22", "3a. SEARCH decisionTypeUid = Δ.2.3 (ΑΝΑΘΕΣΗ/award)"),
    ("decisionTypeUid:%22%CE%92.2.1%22", "3b. SEARCH decisionTypeUid = Β.2.1 (ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ)"),
]:
    r = get(f"/search.json?q={q}&size=2", label)
    if r:
        info = r.get("info") or {}
        print(f"  total={info.get('total')}")
        for d in (r.get("decisions") or [])[:1]:
            efv = d.get("extraFieldValues") or {}
            print(f"  ada={d.get('ada')}")
            print(f"  subject={str(d.get('subject'))[:150]}")
            print(f"  extraFieldValues keys: {list(efv.keys())}")
            print(f"  extraFieldValues:\n{json.dumps(efv, ensure_ascii=False, indent=2)[:2500]}")

# 4. Date filtering — essential for incremental daily ingest.
for params, label in [
    ("from_date=2025-01-01&to_date=2025-01-02&size=2", "4a. DATE FILTER from_date/to_date"),
    ("from_issue_date=2025-01-01&to_issue_date=2025-01-02&size=2", "4b. DATE FILTER from_issue_date/to_issue_date"),
]:
    r = get(f"/search.json?{params}", label)
    if r:
        print(f"  total={(r.get('info') or {}).get('total')}")

# 5. Paging — confirm max page size.
for size in (100, 500):
    r = get(f"/search.json?size={size}", f"5. PAGE SIZE {size}")
    if r:
        print(f"  requested {size}, got {len(r.get('decisions') or [])}")

print("\n\nPROBE COMPLETE")

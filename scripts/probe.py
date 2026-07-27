"""Probe 2: find the correct type filter and confirm award decisions carry money fields.

Probe 1 established:
  - https://diavgeia.gov.gr/opendata/search.json works, no auth
  - date filter params are from_issue_date / to_issue_date
  - size=500 works
  - Real award type is Δ.1 (ΑΝΑΘΕΣΗ ΕΡΓΩΝ/ΠΡΟΜΗΘΕΙΩΝ/ΥΠΗΡΕΣΙΩΝ/ΜΕΛΕΤΩΝ)
  - A malformed q= filter is SILENTLY IGNORED and returns everything, so every
    filter below is validated by checking the decisionTypeId actually came back.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://diavgeia.gov.gr/opendata"
UA = "GR-GOV-CorruptionChecker/0.1 (+https://github.com/NiFoGR/GR-GOV-CorruptionChecker)"

AWARD = "Δ.1"        # ΑΝΑΘΕΣΗ ΕΡΓΩΝ / ΠΡΟΜΗΘΕΙΩΝ / ΥΠΗΡΕΣΙΩΝ / ΜΕΛΕΤΩΝ
PAYMENT = "Β.2.2"    # ΟΡΙΣΤΙΚΟΠΟΙΗΣΗ ΠΛΗΡΩΜΗΣ
EXPENSE = "Β.2.1"    # ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ


def get(url, label):
    print(f"\n{'=' * 70}\n{label}\n  GET {url}\n{'=' * 70}")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            print(f"  HTTP {r.status}  {len(raw)} bytes")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                print(f"  NOT JSON: {raw[:400]}")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.reason}\n  {e.read().decode('utf-8', 'replace')[:400]}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
    return None


def check_filter(url, want_type, label):
    """A filter only 'works' if every returned decision has the type we asked for."""
    r = get(url, label)
    if not r:
        return None
    decisions = r.get("decisions") or []
    total = (r.get("info") or {}).get("total")
    types = {d.get("decisionTypeId") for d in decisions}
    ok = types == {want_type} if decisions else False
    print(f"  total={total}  returned_types={types}")
    print(f"  >>> {'WORKS' if ok else 'IGNORED / WRONG — do not use'}")
    return r if ok else None


print("\n\n########## PART 1: which type-filter syntax actually works? ##########")

enc = urllib.parse.quote(AWARD)
candidates = [
    (f"{BASE}/search.json?type={enc}&size=3", "A. ?type=Δ.1"),
    (f"{BASE}/search.json?q=type:{enc}&size=3", "B. ?q=type:Δ.1"),
    (f"{BASE}/search.json?q=decisionTypeId:{enc}&size=3", "C. ?q=decisionTypeId:Δ.1"),
    (f"{BASE}/search.json?q={urllib.parse.quote(f'decisionTypeId:\"{AWARD}\"')}&size=3", "D. ?q=decisionTypeId:\"Δ.1\""),
    (f"{BASE}/search.json?decisionTypeId={enc}&size=3", "E. ?decisionTypeId=Δ.1"),
]

working = None
for url, label in candidates:
    r = check_filter(url, AWARD, label)
    if r and not working:
        working = (url, label, r)

print(f"\n\n>>>>>> WORKING TYPE FILTER: {working[1] if working else 'NONE FOUND'}")


print("\n\n########## PART 2: do award decisions carry money + supplier? ##########")

if working:
    _, _, r = working
    for d in (r.get("decisions") or [])[:2]:
        print(f"\n--- ADA {d.get('ada')} (type {d.get('decisionTypeId')}) ---")
        print(f"  subject: {str(d.get('subject'))[:200]}")
        print(f"  org: {d.get('organizationId')}")
        efv = d.get("extraFieldValues") or {}
        print(f"  extraFieldValues ({len(efv)} keys):")
        print(json.dumps(efv, ensure_ascii=False, indent=4)[:4000])

# Also pull one full single-decision record — the search payload may be trimmed.
if working:
    _, _, r = working
    decisions = r.get("decisions") or []
    if decisions:
        ada = decisions[0].get("ada")
        full = get(f"{BASE}/decisions/{urllib.parse.quote(ada)}.json", f"FULL RECORD for {ada}")
        if full:
            print(json.dumps(full, ensure_ascii=False, indent=2)[:6000])


print("\n\n########## PART 3: payment + expense types (money lives here too) ##########")

for t, name in [(PAYMENT, "Β.2.2 ΟΡΙΣΤΙΚΟΠΟΙΗΣΗ ΠΛΗΡΩΜΗΣ"), (EXPENSE, "Β.2.1 ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ")]:
    if not working:
        break
    tmpl = working[0]
    url = tmpl.replace(enc, urllib.parse.quote(t))
    r = check_filter(url, t, f"TYPE {name}")
    if r:
        for d in (r.get("decisions") or [])[:1]:
            efv = d.get("extraFieldValues") or {}
            print(f"  ada={d.get('ada')}  subject={str(d.get('subject'))[:150]}")
            print(f"  extraFieldValues:\n{json.dumps(efv, ensure_ascii=False, indent=4)[:3000]}")


print("\n\n########## PART 4: organizations lookup (id -> name) ##########")

orgs = get(f"{BASE}/organizations.json?size=3", "ORGANIZATIONS")
if orgs:
    print(json.dumps(orgs, ensure_ascii=False, indent=2)[:2000])


print("\n\n########## PART 5: type + date filter combined (the real ingest query) ##########")

if working:
    url = working[0].replace("&size=3", "&from_issue_date=2025-06-02&to_issue_date=2025-06-02&size=3")
    r = check_filter(url, AWARD, "TYPE + DATE combined")
    if r:
        print(f"  >>> one day of {AWARD} awards: total={(r.get('info') or {}).get('total')}")

print("\n\nPROBE 2 COMPLETE")

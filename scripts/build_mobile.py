"""Build a single self-contained mobile page from the latest scan.

The published site fetches docs/data/flags.json at runtime. This produces one
standalone HTML file with the data inlined, so it opens anywhere — including
from a phone with no hosting set up.

Writes: build/mobile.html
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "data" / "flags.json"
OUT = ROOT / "build" / "mobile.html"

MAX_FLAGS = 450   # keep the page light enough to open over mobile data
SUBJECT_CHARS = 130

RULE_ORDER = {
    "threshold_bunching": 0,
    "contract_splitting": 1,
    "supplier_concentration": 2,
    "threshold_proximity": 3,
    "round_number": 4,
}


def trim(payload):
    """Keep every strong flag, then fill with the largest weak ones."""
    flags = sorted(
        payload["flags"],
        key=lambda f: (RULE_ORDER.get(f["rule"], 9), -(f.get("amount") or 0)),
    )
    kept = flags[:MAX_FLAGS]
    return [{
        "r": f["rule"],
        "l": f.get("rule_label") or f["rule"],
        "s": f["severity"],
        "b": f.get("buyer"),
        "p": f.get("supplier"),
        "a": f.get("amount"),
        "d": f.get("date"),
        "k": f.get("ada"),
        "w": f.get("detail"),
        "j": (f.get("subject") or "")[:SUBJECT_CHARS],
    } for f in kept]


PAGE = r"""<title>Greek Public Spending Watch</title>
<style>
  :root {
    --paper:#faf9f7; --panel:#ffffff; --line:#e4e2dd; --line-soft:#efede8;
    --ink:#12161d; --muted:#5f6874;
    --accent:#1e4d8c; --accent-soft:#eaf0f9;
    --crit:#9d2f33; --crit-bg:#fbeceb;
    --warn:#8a5510; --warn-bg:#fdf3e3;
    --info:#2a5f8f; --info-bg:#ebf2f9;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --paper:#0e1216; --panel:#161b21; --line:#252c35; --line-soft:#1d232a;
      --ink:#e7eaee; --muted:#939dab;
      --accent:#7fa9e6; --accent-soft:#15202e;
      --crit:#f08a80; --crit-bg:#2a1414;
      --warn:#e8b45f; --warn-bg:#2a1f0d;
      --info:#84b4e8; --info-bg:#111e2c;
    }
  }
  :root[data-theme="dark"] {
    --paper:#0e1216; --panel:#161b21; --line:#252c35; --line-soft:#1d232a;
    --ink:#e7eaee; --muted:#939dab;
    --accent:#7fa9e6; --accent-soft:#15202e;
    --crit:#f08a80; --crit-bg:#2a1414;
    --warn:#e8b45f; --warn-bg:#2a1f0d;
    --info:#84b4e8; --info-bg:#111e2c;
  }
  :root[data-theme="light"] {
    --paper:#faf9f7; --panel:#ffffff; --line:#e4e2dd; --line-soft:#efede8;
    --ink:#12161d; --muted:#5f6874;
    --accent:#1e4d8c; --accent-soft:#eaf0f9;
    --crit:#9d2f33; --crit-bg:#fbeceb;
    --warn:#8a5510; --warn-bg:#fdf3e3;
    --info:#2a5f8f; --info-bg:#ebf2f9;
  }

  * { box-sizing:border-box; -webkit-text-size-adjust:100%; }
  body {
    margin:0; background:var(--paper); color:var(--ink);
    font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width:660px; margin:0 auto; padding:0 16px; }

  header { padding:26px 0 18px; border-bottom:1px solid var(--line); }
  .eyebrow {
    font-size:11px; letter-spacing:.13em; text-transform:uppercase;
    color:var(--accent); font-weight:600; margin:0 0 7px;
  }
  h1 {
    margin:0; font-family:Georgia,"Iowan Old Style","Times New Roman",serif;
    font-size:27px; line-height:1.15; font-weight:600; letter-spacing:-.01em;
    text-wrap:balance;
  }
  .dek { margin:9px 0 0; color:var(--muted); font-size:14.5px; }
  .stamp { margin:12px 0 0; color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }

  .figures { display:grid; grid-template-columns:repeat(2,1fr); gap:1px;
             background:var(--line); border:1px solid var(--line);
             border-radius:10px; overflow:hidden; margin:20px 0; }
  .fig { background:var(--panel); padding:13px 14px; }
  .fig b { display:block; font-family:Georgia,"Times New Roman",serif;
           font-size:22px; font-weight:600; letter-spacing:-.02em;
           font-variant-numeric:tabular-nums; }
  .fig span { display:block; color:var(--muted); font-size:11.5px; margin-top:2px; }

  .caveat { background:var(--accent-soft); border:1px solid var(--line);
            border-left:3px solid var(--accent); border-radius:8px;
            padding:13px 15px; font-size:13.5px; color:var(--muted); }
  .caveat b { color:var(--ink); }

  .bar { position:sticky; top:0; z-index:5; background:var(--paper);
         padding:14px 0 12px; border-bottom:1px solid var(--line);
         display:flex; flex-wrap:wrap; gap:8px; }
  input, select {
    font:inherit; font-size:15px; color:var(--ink); background:var(--panel);
    border:1px solid var(--line); border-radius:8px; padding:10px 12px;
    min-height:44px; /* comfortable tap target */
  }
  input { flex:1 1 100%; }
  select { flex:1 1 auto; min-width:0; }
  input:focus-visible, select:focus-visible, a:focus-visible {
    outline:2px solid var(--accent); outline-offset:2px;
  }

  .tally { color:var(--muted); font-size:12.5px; margin:12px 0 0;
           font-variant-numeric:tabular-nums; }

  ul.records { list-style:none; margin:12px 0 0; padding:0;
               display:flex; flex-direction:column; gap:10px; }
  .rec { background:var(--panel); border:1px solid var(--line);
         border-left:3px solid var(--muted); border-radius:8px; padding:13px 15px; }
  .rec.high { border-left-color:var(--crit); }
  .rec.medium { border-left-color:var(--warn); }
  .rec.low { border-left-color:var(--info); }

  .tag { display:inline-block; font-size:10.5px; font-weight:700;
         letter-spacing:.07em; text-transform:uppercase; padding:3px 7px;
         border-radius:4px; }
  .high .tag { color:var(--crit); background:var(--crit-bg); }
  .medium .tag { color:var(--warn); background:var(--warn-bg); }
  .low .tag { color:var(--info); background:var(--info-bg); }
  .kind { font-size:12.5px; color:var(--muted); margin-left:7px; }

  /* Registry names arrive as long comma-run strings with no spaces to wrap at
     (e.g. SURNAME,,FORENAME,PATRONYMIC in Greek capitals), which pushes the page sideways. */
  .who, .vendor, .why { overflow-wrap:anywhere; }
  .who { font-weight:600; margin:9px 0 0; font-size:15.5px; line-height:1.35; }
  .vendor { color:var(--muted); font-size:13.5px; margin:3px 0 0; }
  .why { margin:9px 0 0; font-size:13.5px; color:var(--muted); }

  .foot { display:flex; flex-wrap:wrap; align-items:baseline; gap:10px;
          margin:11px 0 0; padding-top:10px; border-top:1px solid var(--line-soft); }
  .money { font-family:Georgia,"Times New Roman",serif; font-size:17px;
           font-weight:600; font-variant-numeric:tabular-nums; }
  .when { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
  .src { margin-left:auto; font-size:12.5px; }
  a { color:var(--accent); }
  .none { text-align:center; color:var(--muted); padding:34px 0; }

  footer { border-top:1px solid var(--line); margin-top:30px;
           padding:18px 0 44px; color:var(--muted); font-size:12.5px; }
  footer p { margin:0 0 7px; }

  @media (min-width:560px) { .figures { grid-template-columns:repeat(4,1fr); } }
</style>

<header>
  <div class="wrap">
    <p class="eyebrow">&#916;&#953;&#945;&#973;&#947;&#949;&#953;&#945; &#183; automated screening</p>
    <h1>Greek Public Spending Watch</h1>
    <p class="dek">Award decisions published by Greek public bodies, screened for
       patterns worth a second look.</p>
    <p class="stamp" id="stamp"></p>
  </div>
</header>

<div class="wrap">
  <div class="figures" id="figures"></div>

  <p class="caveat"><b>These are statistical flags, not accusations.</b>
     Each record below fits a pattern that <em>can</em> indicate a problem and
     often does not &#8212; routine purchasing, an urgent repair, or a small local
     market with one real supplier all look the same in the data. Nothing here
     is evidence of wrongdoing by anyone. Every record links to the original
     public document.</p>

  <div class="bar">
    <input type="search" id="q" placeholder="Search body or supplier&#8230;" aria-label="Search">
    <select id="rule" aria-label="Filter by pattern"><option value="">All patterns</option></select>
    <select id="sev" aria-label="Filter by severity">
      <option value="">All levels</option>
      <option value="high">High</option>
      <option value="medium">Medium</option>
      <option value="low">Low</option>
    </select>
  </div>

  <p class="tally" id="tally"></p>
  <ul class="records" id="records"></ul>
</div>

<footer>
  <div class="wrap">
    <p>Source: <a href="https://diavgeia.gov.gr">&#916;&#953;&#945;&#973;&#947;&#949;&#953;&#945;</a>, published under CC-BY.
       Independent and non-commercial; not affiliated with the Greek State.</p>
    <p>Snapshot of the __SHOWN__ strongest flags from __TOTAL__ found. Rules and their
       limitations &#8212; including an unresolved VAT ambiguity &#8212; are documented in the
       <a href="https://github.com/NiFoGR/GR-GOV-CorruptionChecker">project repository</a>.</p>
  </div>
</footer>

<script>
const DATA = __DATA__;

const eur = n => n == null ? '\u2014' : '\u20ac' + Math.round(n).toLocaleString('en-GB');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const S = DATA.stats, W = DATA.window, F = DATA.flags;

document.getElementById('stamp').textContent =
  `${W.from} to ${W.to} \u00b7 scanned ${new Date(DATA.generated_at)
    .toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' })}`;

document.getElementById('figures').innerHTML = [
  [S.decisions.toLocaleString('en-GB'), 'awards screened'],
  ['\u20ac' + (S.total_amount / 1e9).toFixed(2) + 'bn', 'total value'],
  [S.flags.toLocaleString('en-GB'), 'flags raised'],
  [S.organisations.toLocaleString('en-GB'), 'public bodies'],
].map(([n, l]) => `<div class="fig"><b>${n}</b><span>${l}</span></div>`).join('');

const sel = document.getElementById('rule');
const seen = new Map();
F.forEach(f => seen.has(f.r) || seen.set(f.r, f.l));
for (const [id, label] of seen) {
  sel.insertAdjacentHTML('beforeend', `<option value="${esc(id)}">${esc(label)}</option>`);
}

function draw() {
  const q = document.getElementById('q').value.toLowerCase().trim();
  const rule = sel.value, sev = document.getElementById('sev').value;

  const hits = F.filter(f =>
    (!rule || f.r === rule) && (!sev || f.s === sev) &&
    (!q || `${f.b} ${f.p ?? ''}`.toLowerCase().includes(q)));

  document.getElementById('tally').textContent =
    `${hits.length.toLocaleString('en-GB')} of ${F.length.toLocaleString('en-GB')} records`;

  document.getElementById('records').innerHTML = hits.length ? hits.map(f => `
    <li class="rec ${esc(f.s)}">
      <span class="tag">${esc(f.s)}</span><span class="kind">${esc(f.l)}</span>
      <p class="who">${esc(f.b)}</p>
      ${f.p ? `<p class="vendor">Supplier: ${esc(f.p)}</p>` : ''}
      <p class="why">${esc(f.w)}</p>
      <div class="foot">
        <span class="money">${eur(f.a)}</span>
        <span class="when">${esc(f.d || '')}</span>
        <span class="src">${f.k ? `<a href="https://diavgeia.gov.gr/doc/${
          encodeURIComponent(f.k)}" target="_blank" rel="noopener">View document \u2197</a>` : ''}</span>
      </div>
    </li>`).join('') : '<li class="none">Nothing matches these filters.</li>';
}

['q', 'rule', 'sev'].forEach(id =>
  document.getElementById(id).addEventListener('input', draw));
draw();
</script>
"""


def main():
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    flags = trim(payload)
    data = {
        "generated_at": payload["generated_at"],
        "window": payload["window"],
        "stats": payload["stats"],
        "flags": flags,
    }
    html = (PAGE
            .replace("__DATA__", json.dumps(data, ensure_ascii=True, separators=(",", ":")))
            .replace("__SHOWN__", f"{len(flags):,}")
            .replace("__TOTAL__", f"{payload['stats']['flags']:,}"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} — {len(flags)} flags, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

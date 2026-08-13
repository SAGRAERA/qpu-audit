"""HTML report generation.

Self-contained single file — no CDN, no external stylesheet, nothing fetched at view
time. It opens offline and can be handed to an administrator as one attachment.
Light and dark themes are both supported.

Reports get read by people who did not generate them, so every string ships in all
supported languages and the reader picks one from a selector. Only the active
language is displayed; the rest sit hidden in the same file. See i18n.py.
"""

from __future__ import annotations

import csv
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import i18n, report_sections
from .queueimpact import QueueImpact, analyze_queue
from .rules import Analysis, UserReport
from .similarity import FamilyDiff, user_families
from .store import Store
from .usage import (
    UsageLedger,
    compute_monthly,
    compute_monthly_by_backend,
    compute_monthly_by_instance,
    load_breakdown,
    load_ledger,
    persist,
    persist_by_backend,
    persist_by_instance,
)

CSS = """
:root{
  --bg:#fbfbfa; --panel:#ffffff; --ink:#1a1a18; --muted:#6b6b66; --line:#e4e2dd;
  --accent:#0f62fe; --abuse:#c21e2b; --gray:#b07d17; --benign:#1f7a4d;
  --abuse-bg:#fdeced; --gray-bg:#fdf5e3; --benign-bg:#e9f6ef;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#16161a; --panel:#1e1e24; --ink:#ececeb; --muted:#9a9a95; --line:#33333c;
    --accent:#78a9ff; --abuse:#ff8389; --gray:#f1c21b; --benign:#42be65;
    --abuse-bg:#3a1d20; --gray-bg:#3a3218; --benign-bg:#12301f;
  }
}
:root[data-theme="dark"]{
  --bg:#16161a; --panel:#1e1e24; --ink:#ececeb; --muted:#9a9a95; --line:#33333c;
  --accent:#78a9ff; --abuse:#ff8389; --gray:#f1c21b; --benign:#42be65;
  --abuse-bg:#3a1d20; --gray-bg:#3a3218; --benign-bg:#12301f;
}
:root[data-theme="light"]{
  --bg:#fbfbfa; --panel:#ffffff; --ink:#1a1a18; --muted:#6b6b66; --line:#e4e2dd;
  --accent:#0f62fe; --abuse:#c21e2b; --gray:#b07d17; --benign:#1f7a4d;
  --abuse-bg:#fdeced; --gray-bg:#fdf5e3; --benign-bg:#e9f6ef;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
  "Noto Sans KR","Noto Sans JP",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:19px;margin:38px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:0 0 6px}
.sub{color:var(--muted);font-size:13px;margin:0 0 24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:20px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.card .v{font-size:24px;font-weight:600;margin-top:2px;font-variant-numeric:tabular-nums}
.card .n{color:var(--muted);font-size:12px}
.note{background:var(--gray-bg);border-left:3px solid var(--gray);padding:10px 14px;
  border-radius:0 6px 6px 0;margin:8px 0;font-size:13.5px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:color-mix(in srgb,var(--panel) 80%,var(--line));font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
tbody tr:last-child td{border-bottom:none}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:600}
.b-abuse{background:var(--abuse-bg);color:var(--abuse)}
.b-gray{background:var(--gray-bg);color:var(--gray)}
.b-benign{background:var(--benign-bg);color:var(--benign)}
.user{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:18px 20px;margin:14px 0}
.user.flagged{border-color:var(--abuse)}
.uhead{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;margin-bottom:2px}
.uid{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:var(--muted)}
.score{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
ul.findings{margin:10px 0 0;padding-left:20px}
ul.findings li{margin:3px 0}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;min-width:90px}
.bar>i{display:block;height:100%;background:var(--accent)}
details{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
summary{cursor:pointer;color:var(--accent);font-size:13.5px;font-weight:500}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;
  overflow-x:auto;font-size:12px;line-height:1.5;margin:8px 0}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.hash{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11.5px;color:var(--muted)}
.tl{display:block;margin:6px 0}
footer{margin-top:50px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin:6px 0 0}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
.chip{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:6px;
  font-size:12px;border:1px solid var(--line);background:var(--bg)}
.chip-waste{border-color:var(--abuse);background:var(--abuse-bg);color:var(--abuse)}
.chip-queue{border-color:var(--gray);background:var(--gray-bg);color:var(--gray)}
.chip-context{border-style:dashed;opacity:.8}
.chip-total{font-weight:600;background:var(--panel)}
.chip-sep{width:1px;background:var(--line);margin:2px 4px}
tfoot th{background:color-mix(in srgb,var(--panel) 80%,var(--line));font-size:12.5px;
  text-align:left;border-top:1px solid var(--line)}
tfoot th.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--abuse);font-weight:600}
.down{color:var(--benign)}

/* Language switching. Every translatable string ships in all languages; only the
   active one is displayed. No network access, no rebuild needed. */
i.tr{display:none;font-style:normal}
:root[data-lang="en"] i.tr[lang="en"],
:root[data-lang="ko"] i.tr[lang="ko"],
:root[data-lang="ja"] i.tr[lang="ja"],
:root[data-lang="es"] i.tr[lang="es"]{display:inline}
:root:not([data-lang]) i.tr[lang="en"]{display:inline}
.langbar{display:flex;align-items:center;gap:8px;justify-content:flex-end;
  margin:-8px 0 8px;font-size:13px;color:var(--muted)}
.langbar select{font:inherit;color:var(--ink);background:var(--panel);
  border:1px solid var(--line);border-radius:6px;padding:3px 8px}

/* Sortable tables. Ranking depends on which column you care about — time, job
   count, user count — so the ordering is the reader's choice, not a fixed one. */
th.sortable-th{cursor:pointer;user-select:none;white-space:nowrap}
th.sortable-th:hover{color:var(--accent)}
th.sortable-th::after{content:"";opacity:.35;font-size:10px}
th.sortable-th:hover::after{content:" ⇅";opacity:.6}
th.sortable-th[data-dir="desc"]::after{content:" ▼";opacity:1;color:var(--accent)}
th.sortable-th[data-dir="asc"]::after{content:" ▲";opacity:1;color:var(--accent)}
.sorthint{color:var(--muted);font-size:12px;margin:6px 0 0}
"""

SORT_SCRIPT = """
(function(){
  // Sort on data-sort, never on the rendered text: cells carry units, thousands
  // separators and four languages at once, none of which sort meaningfully.
  function val(row, i){
    var td = row.children[i];
    if(!td) return '';
    var d = td.getAttribute('data-sort');
    return d !== null ? d : td.textContent.trim();
  }
  function cmp(a, b){
    var na = parseFloat(a), nb = parseFloat(b);
    var aN = a !== '' && !isNaN(na), bN = b !== '' && !isNaN(nb);
    if(aN && bN) return na - nb;
    if(aN) return 1;
    if(bN) return -1;
    return String(a).localeCompare(String(b));
  }
  function renumber(tbody){
    var n = 1;
    Array.prototype.forEach.call(tbody.rows, function(r){
      var c = r.querySelector('.rownum');
      if(c) c.textContent = n++;
    });
  }
  function attach(table){
    if(!table.tHead || !table.tBodies.length) return;
    var ths = table.tHead.rows[table.tHead.rows.length - 1].cells;
    Array.prototype.forEach.call(ths, function(th, i){
      th.classList.add('sortable-th');
      th.addEventListener('click', function(){
        var tbody = table.tBodies[0];
        var desc = th.getAttribute('data-dir') !== 'desc';
        Array.prototype.forEach.call(ths, function(o){ o.removeAttribute('data-dir'); });
        th.setAttribute('data-dir', desc ? 'desc' : 'asc');
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function(x, y){
          var r = cmp(val(x, i), val(y, i));
          return desc ? -r : r;
        });
        rows.forEach(function(r){ tbody.appendChild(r); });
        renumber(tbody);
      });
    });
  }
  document.addEventListener('DOMContentLoaded', function(){
    Array.prototype.forEach.call(document.querySelectorAll('table.sortable'), attach);
  });
})();
"""

LANG_SCRIPT = """
(function(){
  var KEY='qpu-audit-lang';
  var supported=%(codes)s;
  function pick(){
    var saved=null;
    try{saved=localStorage.getItem(KEY);}catch(e){}
    if(saved&&supported.indexOf(saved)>=0)return saved;
    var nav=(navigator.language||'en').slice(0,2).toLowerCase();
    return supported.indexOf(nav)>=0?nav:'en';
  }
  window.setLang=function(l){
    document.documentElement.setAttribute('data-lang',l);
    try{localStorage.setItem(KEY,l);}catch(e){}
    var s=document.getElementById('lang');
    if(s)s.value=l;
  };
  var initial=pick();
  document.documentElement.setAttribute('data-lang',initial);
  document.addEventListener('DOMContentLoaded',function(){
    var s=document.getElementById('lang');
    if(s)s.value=initial;
  });
})();
"""


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def tr(key: str, **params: Any) -> str:
    """A static UI string, emitted once per language.

    Parameter values are escaped; the templates may carry simple inline HTML and are
    inserted as-is, since they come from i18n.py rather than from collected data.
    """
    safe = {k: esc(v) for k, v in params.items()}
    return "".join(
        f'<i class="tr" lang="{code}">{i18n.ui(key, code, **safe)}</i>'
        for code in i18n.LANG_CODES
    )


def trm(msg: Any) -> str:
    """A generated sentence (an i18n.Msg), emitted once per language."""
    if msg is None:
        return ""
    if not isinstance(msg, i18n.Msg):
        return esc(msg)
    return "".join(
        f'<i class="tr" lang="{code}">{esc(msg.text(code))}</i>' for code in i18n.LANG_CODES
    )


def _fmt_seconds(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.1f}s"


def _lang_selector() -> str:
    options = "".join(
        f'<option value="{code}">{esc(label)}'
        + (f" ({esc(i18n.ui('unreviewed_tag', code))})" if code in i18n.UNREVIEWED else "")
        + "</option>"
        for code, label in i18n.LANGUAGES.items()
    )
    return (
        '<div class="langbar">'
        f'<label for="lang">{tr("lang_label")}</label>'
        f'<select id="lang" onchange="setLang(this.value)">{options}</select>'
        "</div>"
    )


def render(
    analysis: Analysis,
    store: Store,
    settings_report: dict[str, Any],
    queue_impacts: list[QueueImpact] | None = None,
    families: dict[str, list[FamilyDiff]] | None = None,
    ledger: UsageLedger | None = None,
    breakdown: Any = None,
    backends: Any = None,
) -> str:
    sections = report_sections.build(esc, tr, trm)
    top_users = int(settings_report.get("top_users", 20))
    users = analysis.users[:top_users]
    families = families or {}
    labels = {u.user_id: u.label for u in analysis.users}

    flagged = [u for u in analysis.users if u.abuse_groups]
    total_wasted = sum(u.flagged_waste_seconds for u in analysis.users)
    waste_pct = (
        f"{total_wasted / analysis.total_seconds * 100:.1f}" if analysis.total_seconds else "0"
    )

    cards = [
        ("card_window", analysis.period_label, tr("card_window_note", jobs=f"{analysis.total_jobs:,}")),
        ("card_qpu", _fmt_seconds(analysis.total_seconds), tr("card_qpu_note", runs=f"{analysis.total_runs:,}")),
        ("card_waste", _fmt_seconds(total_wasted), tr("card_waste_note", pct=waste_pct)),
        ("card_users", f"{len(analysis.users)}", tr("card_users_note", n=len(flagged))),
        ("card_cov", f"{analysis.coverage * 100:.0f}%", tr("card_cov_note")),
    ]
    card_html = "".join(
        f'<div class="card"><div class="k">{tr(k)}</div><div class="v">{esc(v)}</div>'
        f'<div class="n">{n}</div></div>'
        for k, v, n in cards
    )

    ranking = "".join(sections["ranking_row"](i, u) for i, u in enumerate(users, start=1))

    notes = "".join(f'<div class="note">{trm(n)}</div>' for n in analysis.notes)
    if analysis.unmapped_users:
        notes += f'<div class="note">{tr("note_unmapped", n=len(analysis.unmapped_users))}</div>'

    generated = analysis.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    script = LANG_SCRIPT % {"codes": str(i18n.LANG_CODES).replace("'", '"')}

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>qpu-audit</title>
<style>{CSS}</style>
<script>{script}</script>
<script>{SORT_SCRIPT}</script>
</head><body><div class="wrap">
{_lang_selector()}
<h1>{tr('title')}</h1>
<p class="sub">{tr('generated', when=generated, days=analysis.window_days)} · {esc(analysis.period_label)}</p>

<div class="cards">{card_html}</div>
{notes}

<h2>{tr('h_ranking')}</h2>
<p class="sub">{tr('p_ranking')}</p>
<div class="scroll"><table class="sortable">
<thead><tr>
  <th>{tr('th_num')}</th><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>
  <th>{tr('th_score')}</th><th>{tr('th_jobs')}</th><th>{tr('th_qpu')}</th>
  <th>{tr('th_share_all')}</th><th>{tr('th_share_top')}</th>
  <th>{tr('th_unexplained')}</th><th>{tr('th_of_total')}</th>
  <th>{tr('th_unique')}</th><th>{tr('th_top_circuit')}</th><th>{tr('th_cv')}</th>
</tr></thead><tbody>{ranking}</tbody>
</table></div>
<div class="legend">
  <span>{tr('lg_share')}</span><span>{tr('lg_unexplained')}</span>
  <span>{tr('lg_unique')}</span><span>{tr('lg_cv')}</span>
</div>
<p class="sorthint">{tr('sort_hint')}</p>

{sections["compare_section"](analysis.comparison)}

{sections["usage_section"](ledger)}

{sections["instance_section"](breakdown)}

{sections["backend_ranking"](backends)}

{sections["backend_section"](backends)}

{sections["queue_section"](queue_impacts or [], labels)}

<h2>{tr('h_detail')}</h2>
{"".join(sections["user_block"](store, u, settings_report, families.get(u.user_id)) for u in users)
 or f"<p>{tr('p_no_users')}</p>"}

<footer>{tr('footer')}</footer>
</div></body></html>"""


def write_report(
    analysis: Analysis,
    store: Store,
    out_path: Path,
    report_cfg: dict[str, Any],
    with_extras: bool = True,
) -> Path:
    """Write the report.

    ``with_extras`` controls the queue analysis and circuit-family comparison, both of
    which decode stored payloads and therefore take time.
    """
    queue_impacts: list[QueueImpact] = []
    families: dict[str, list[FamilyDiff]] = {}
    ledger: UsageLedger | None = None
    breakdown = None
    backends = None

    # The monthly ledgers are always refreshed and included — they are the long-term
    # value, and they survive IBM dropping the underlying workloads.
    try:
        persist(store, compute_monthly(store))
        persist_by_instance(store, compute_monthly_by_instance(store))
        persist_by_backend(store, compute_monthly_by_backend(store))
        labels = {u.user_id: u.label for u in analysis.users}
        ledger = load_ledger(store, months=12)
        ledger.labels = labels
        breakdown = load_breakdown(store, months=12, names=analysis.instance_names)
        breakdown.labels = labels
        backends = load_breakdown(store, months=12, dimension="backend")
        backends.labels = labels
    except Exception:  # noqa: BLE001
        ledger = None

    if with_extras:
        queue_impacts = analyze_queue(store, analysis.window_days)
        for user in analysis.users[: int(report_cfg.get("top_users", 20))]:
            try:
                families[user.user_id] = user_families(store, user.user_id)
            except Exception:  # noqa: BLE001 - supplementary info must not break the report
                families[user.user_id] = []

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render(
            analysis, store, report_cfg, queue_impacts, families, ledger, breakdown, backends
        ),
        encoding="utf-8",
    )
    return out_path


def write_csv(analysis: Analysis, out_path: Path, lang: str = i18n.DEFAULT_LANG) -> Path:
    """Per-user summary for spreadsheets. Findings render in one language."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "user_id", "label", "score", "waste_points", "queue_points", "context_points",
            "jobs", "runs", "qpu_seconds", "instance_share", "top_instance",
            "top_instance_share", "repeat_seconds_total", "flagged_waste_seconds",
            "unique_circuits", "unique_ratio", "top_flagged_circuit_share",
            "flagged_trivial_seconds", "interval_cv", "max_burst", "flagged_groups",
            "findings",
        ])
        for user in analysis.users:
            writer.writerow([
                user.user_id, user.label, user.score,
                user.waste_points, user.queue_points, user.context_points,
                user.jobs, user.runs, round(user.seconds, 2),
                round(user.instance_share, 4), user.top_instance,
                round(user.top_instance_share, 4),
                round(user.wasted_seconds, 2), round(user.flagged_waste_seconds, 2),
                user.unique_exact, round(user.unique_ratio, 4),
                round(user.top_circuit_share, 4), round(user.flagged_trivial_seconds, 2),
                "" if user.interval_cv is None else round(user.interval_cv, 4),
                user.max_burst, user.abuse_groups,
                " | ".join(f.text(lang) for f in user.findings),
            ])
    return out_path


def default_report_path(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return root / "reports" / f"qpu-audit-{stamp}.html"


def _user_summary(user: UserReport) -> str:  # kept for API compatibility
    return f"{user.label}: {user.score:.0f}"

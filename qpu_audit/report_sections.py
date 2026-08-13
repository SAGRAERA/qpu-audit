"""Report body sections.

Split out of report.py so the HTML shell, CSS and language machinery stay readable.
Every visible string goes through ``tr`` (static) or ``trm`` (generated sentence),
which emit the text once per language; CSS shows only the active one.
"""

from __future__ import annotations

import json
from typing import Any

from . import i18n
from .queueimpact import QueueImpact
from .rules import CLASS_LABEL, CircuitGroup, RiskSignal, UserReport
from .similarity import FamilyDiff
from .store import Store
from .usage import UsageLedger


def _fmt_seconds(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.1f}s"


def num(display: Any, sort: Any, extra: str = "") -> str:
    """A numeric cell that sorts on its underlying value.

    The rendered text carries units, thousands separators and, for some cells, four
    languages at once — none of which sort correctly. ``data-sort`` keeps the
    ordering tied to the number.
    """
    return f'<td class="num" data-sort="{sort}"{extra}>{display}</td>'


def build(esc, tr, trm):
    """Return the section renderers bound to the escaping/translation helpers."""

    def badge(verdict: str) -> str:
        cls = {"abuse": "b-abuse", "gray": "b-gray", "benign": "b-benign"}.get(
            verdict, "b-benign"
        )
        return f'<span class="badge {cls}">{tr("verdict_" + verdict)}</span>'

    def timeline_svg(group: CircuitGroup, width: int = 320, height: int = 26) -> str:
        stamps = sorted(group.timestamps)
        if len(stamps) < 2:
            return ""
        start, end = stamps[0].timestamp(), stamps[-1].timestamp()
        span = max(end - start, 1.0)
        dots = "".join(
            f'<circle cx="{4 + (ts.timestamp() - start) / span * (width - 8):.1f}" '
            f'cy="{height / 2:.0f}" r="2.5" fill="currentColor" opacity="0.75"/>'
            for ts in stamps
        )
        return (
            f'<svg class="tl" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" style="color:var(--accent)">'
            f'<line x1="4" y1="{height / 2:.0f}" x2="{width - 4}" y2="{height / 2:.0f}" '
            f'stroke="currentColor" stroke-opacity="0.25"/>{dots}</svg>'
        )

    def circuit_evidence(store: Store, exact_hash: str, max_lines: int) -> str:
        rows = store.query(
            """SELECT qasm, name, metadata, source, n_qubits, n_clbits, n_ops, n_2q_ops,
                      depth, has_measure, gate_histogram
               FROM circuits WHERE exact_hash = ?""",
            (exact_hash,),
        )
        if not rows:
            return f"<p class='sub'>{tr('ev_no_details')}</p>"
        row = rows[0]

        if row["qasm"]:
            lines = str(row["qasm"]).splitlines()
            trailer = ""
            if len(lines) > max_lines:
                trailer = tr("ev_lines_shown", shown=max_lines, total=len(lines))
                lines = lines[:max_lines]
            return (
                f"<pre><code>{esc(chr(10).join(lines))}</code></pre>"
                + (f"<p class='sub'>{trailer}</p>" if trailer else "")
            )

        if not row["name"] and not row["n_ops"]:
            return f"<p class='sub'>{tr('ev_undecodable')}</p>"

        gates = ""
        try:
            histogram = json.loads(row["gate_histogram"] or "{}")
            top = sorted(histogram.items(), key=lambda kv: -kv[1])[:10]
            gates = ", ".join(f"{name}x{count}" for name, count in top)
        except (TypeError, ValueError):
            pass

        parts = [
            f"<b>{tr('ev_name')}</b> <code>"
            + (esc(row["name"]) if row["name"] else tr("ev_unnamed"))
            + "</code>",
            f"<b>{tr('ev_size')}</b> "
            + tr(
                "ev_size_v",
                q=row["n_qubits"], c=row["n_clbits"], ops=row["n_ops"],
                depth=row["depth"], tq=row["n_2q_ops"],
            )
            + " "
            + (tr("meas_present") if row["has_measure"] else tr("meas_absent")),
        ]
        if gates:
            parts.append(f"<b>{tr('ev_gates')}</b> {esc(gates)}")
        if row["metadata"] and row["metadata"] not in ("{}", "null"):
            parts.append(
                f"<b>{tr('ev_metadata')}</b> <code>{esc(str(row['metadata'])[:400])}</code>"
            )
        parts.append(
            f"<span class='sub'>{tr('ev_decoded_via', src=row['source'] or '?')}</span>"
        )
        return "<p class='sub' style='margin:8px 0'>" + "<br>".join(parts) + "</p>"

    def signal_chips(user: UserReport) -> str:
        if not user.signals:
            return ""
        totals = (
            f'<span class="chip chip-total">{tr("cls_waste")} '
            f"<b>{user.waste_points:.0f}</b></span>"
            f'<span class="chip chip-total">{tr("cls_queue")} '
            f"<b>{user.queue_points:.0f}</b></span>"
            f'<span class="chip chip-total chip-context">{tr("cls_context")} '
            f"<b>{user.context_points:.0f}</b></span>"
        )
        chips = "".join(
            f'<span class="chip chip-{s.klass}">{tr(s.label_key)} '
            f"<b>+{s.points:.0f}</b></span>"
            for s in user.signals
        )
        return f'<div class="chips">{totals}<span class="chip-sep"></span>{chips}</div>'

    def signal_table(signals: list[RiskSignal]) -> str:
        if not signals:
            return ""
        rows = "".join(
            "<tr>"
            f"<td>{tr(s.label_key)}</td>"
            f'<td class="num">{s.points:.1f}</td>'
            f'<td>{tr("cls_" + s.klass)}</td>'
            f"<td>{trm(s.detail)}</td>"
            "</tr>"
            for s in signals
        )
        return (
            f"<details><summary>{tr('sig_summary')}</summary>"
            "<div class='scroll' style='margin-top:8px'><table><thead><tr>"
            f"<th>{tr('sig_th_signal')}</th><th>{tr('sig_th_points')}</th>"
            f"<th>{tr('sig_th_class')}</th><th>{tr('sig_th_basis')}</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table></div>"
            f"<p class='sub' style='margin-top:8px'>{tr('sig_note')}</p></details>"
        )

    def usage_section(ledger: UsageLedger | None) -> str:
        if not ledger or not ledger.months or not ledger.users:
            return ""
        partial_tag = f"<br><span class='sub' style='font-size:11px'>{tr('tag_in_progress')}</span>"
        head = ""
        for month in ledger.months:
            is_partial = ledger.latest_is_partial and month == ledger.months[-1]
            head += f"<th>{esc(month)}{partial_tag if is_partial else ''}</th>"

        rows = []
        for user in ledger.users:
            cells = ""
            for month in ledger.months:
                seconds = ledger.seconds(month, user)
                cells += (
                    f'<td class="num">{seconds / 3600:.2f}</td>' if seconds
                    else '<td class="num" style="opacity:.35">—</td>'
                )
            change = ledger.change(user)
            if change and (change.ratio >= 1.5 or change.ratio <= 0.67):
                arrow = "▲" if change.ratio > 1 else "▼"
                cls = "up" if change.ratio > 1 else "down"
                if change.is_new:
                    label = tr("chg_new")
                else:
                    label = f"{change.ratio:.1f}x"
                    if change.prorated:
                        label += f" ({tr('chg_est')})"
                delta = f'<span class="{cls}">{arrow} {label}</span>'
            else:
                delta = '<span style="opacity:.35">—</span>'
            rows.append(
                "<tr>"
                f"<td>{esc(ledger.labels.get(user) or user)}</td>"
                f'<td class="hash">{esc(user)}</td>'
                f"{cells}"
                f'<td class="num"><b>{ledger.user_total(user) / 3600:.2f}</b></td>'
                f"<td>{delta}</td>"
                "</tr>"
            )

        totals = "".join(
            f'<td class="num">{ledger.month_total(m) / 3600:.2f}</td>' for m in ledger.months
        )
        return f"""
<h2>{tr('h_usage')}</h2>
<p class="sub">{tr('p_usage')}</p>
<div class="scroll"><table>
<thead><tr><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>{head}
  <th>{tr('th_total')}</th><th>{tr('th_vs_prev')}</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
<tfoot><tr><th colspan="2">{tr('th_month_total')}</th>{totals}
  <th class="num">{ledger.grand_total() / 3600:.2f}</th><th></th></tr></tfoot>
</table></div>"""

    def compare_section(comparison: Any) -> str:
        """Two periods side by side."""
        if not comparison or not comparison.users:
            return ""

        def change_cell(ratio: float | None, only_a: bool, only_b: bool) -> str:
            if ratio == float("inf") or only_a:
                return f'<td><span class="up">{tr("cmp_only_a")}</span></td>'
            if ratio is None:
                return '<td><span style="opacity:.35">—</span></td>'
            if only_b:
                return f'<td><span class="down">{tr("cmp_only_b")}</span></td>'
            cls = "up" if ratio > 1 else ("down" if ratio < 1 else "")
            arrow = "▲" if ratio > 1 else ("▼" if ratio < 1 else "")
            return f'<td><span class="{cls}">{arrow} {ratio:.2f}x</span></td>'

        rows = []
        for d in comparison.users[:25]:
            rows.append(
                "<tr>"
                f"<td>{esc(d.label)}</td>"
                f'<td class="hash">{esc(d.user_id)}</td>'
                f'<td class="num">{_fmt_seconds(d.seconds_a)}</td>'
                f'<td class="num">{_fmt_seconds(d.seconds_b)}</td>'
                + change_cell(d.seconds_ratio, d.seconds_b <= 0 < d.seconds_a,
                              d.seconds_a <= 0 < d.seconds_b)
                + f'<td class="num">{_fmt_seconds(d.waste_a)}</td>'
                f'<td class="num">{_fmt_seconds(d.waste_b)}</td>'
                f'<td class="num">{d.jobs_a}</td>'
                f'<td class="num">{d.jobs_b}</td>'
                "</tr>"
            )

        total_ratio = comparison.total_ratio
        if total_ratio is None:
            total_change = "—"
        elif total_ratio == float("inf"):
            total_change = "—"
        else:
            total_change = f"{total_ratio:.2f}x"

        a = f"{comparison.a_start:%Y-%m-%d} → {comparison.a_end:%Y-%m-%d}"
        b = f"{comparison.b_start:%Y-%m-%d} → {comparison.b_end:%Y-%m-%d}"
        return f"""
<h2>{tr('h_compare')}</h2>
<p class="sub">{tr('cmp_periods', a=a, b=b)}<br>{tr('p_compare')}</p>
<div class="scroll"><table>
<thead><tr><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>
  <th>{tr('th_qpu_a')}</th><th>{tr('th_qpu_b')}</th><th>{tr('th_change')}</th>
  <th>{tr('th_waste_a')}</th><th>{tr('th_waste_b')}</th>
  <th>{tr('th_jobs_a')}</th><th>{tr('th_jobs_b')}</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
<tfoot><tr><th colspan="2">{tr('cmp_total')}</th>
  <th class="num">{_fmt_seconds(comparison.total_a)}</th>
  <th class="num">{_fmt_seconds(comparison.total_b)}</th>
  <th>{esc(total_change)}</th><th colspan="4"></th></tr></tfoot>
</table></div>"""

    def _matrix(breakdown: Any, heading_key: str, intro_key: str, total_key: str) -> str:
        """User x key matrix. Shared by the instance and backend sections."""
        if not breakdown or not breakdown.keys:
            return ""
        head = "".join(f"<th>{esc(breakdown.key_label(k))}</th>" for k in breakdown.keys)
        rows = []
        grand = breakdown.grand_total()
        for user in breakdown.users[:25]:
            cells = ""
            for key in breakdown.keys:
                seconds = breakdown.seconds(user, key)
                if seconds:
                    share = breakdown.user_share_of(user, key)
                    emphasis = ' style="font-weight:600"' if share >= 0.5 else ""
                    cells += num(
                        f'{seconds / 3600:.2f}<span class="sub" style="font-size:11px"> '
                        f"{share * 100:.0f}%</span>",
                        f"{seconds:.3f}",
                        emphasis,
                    )
                else:
                    cells += '<td class="num" data-sort="0" style="opacity:.35">—</td>'
            total = breakdown.user_total(user)
            rows.append(
                "<tr>"
                f'<td data-sort="{esc(breakdown.labels.get(user) or user)}">'
                f"{esc(breakdown.labels.get(user) or user)}</td>"
                f'<td class="hash">{esc(user)}</td>'
                f"{cells}"
                + num(
                    f"<b>{total / 3600:.2f}</b>"
                    f'<span class="sub" style="font-size:11px"> '
                    f"{total / grand * 100 if grand else 0:.0f}%</span>",
                    f"{total:.3f}",
                )
                + "</tr>"
            )
        totals = "".join(
            f'<td class="num">{breakdown.key_total(k) / 3600:.2f}</td>' for k in breakdown.keys
        )
        return f"""
<h2>{tr(heading_key)}</h2>
<p class="sub">{tr(intro_key)}</p>
<div class="scroll"><table class="sortable">
<thead><tr><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>{head}
  <th>{tr('th_total')}</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
<tfoot><tr><th colspan="2">{tr(total_key)}</th>{totals}
  <th class="num">{grand / 3600:.2f}</th></tr></tfoot>
</table></div>
<p class="sorthint">{tr('sort_hint')}</p>"""

    def instance_section(breakdown: Any) -> str:
        return _matrix(breakdown, "h_instance", "p_instance", "th_instance_total")

    def backend_ranking(breakdown: Any) -> str:
        """Which QPU absorbed the most time, and who took it."""
        if not breakdown or not breakdown.keys:
            return ""
        rows = []
        for i, key in enumerate(breakdown.keys, start=1):
            total = breakdown.key_total(key)
            users = breakdown.key_users(key)
            top = breakdown.top_user_of(key)
            if top:
                top_id, top_share = top
                top_cell = (
                    f'<td data-sort="{top_share:.6f}">'
                    f"{esc(breakdown.labels.get(top_id) or top_id)}"
                    f'<span class="sub" style="font-size:11px"> {top_share * 100:.0f}%</span></td>'
                )
            else:
                top_cell = '<td data-sort="-1">—</td>'
            jobs = sum(breakdown.jobs.get((u, key), 0) for u in users)
            rows.append(
                "<tr>"
                f'<td class="rownum">{i}</td>'
                f'<td data-sort="{esc(breakdown.key_label(key))}">'
                f"<b>{esc(breakdown.key_label(key))}</b></td>"
                + num(f"{total / 3600:.2f}", f"{total:.3f}")
                + num(f"{breakdown.key_share(key) * 100:.1f}%", f"{breakdown.key_share(key):.6f}")
                + num(f"{jobs:,}", jobs)
                + num(len(users), len(users))
                + top_cell
                + "</tr>"
            )
        return f"""
<h2>{tr('h_backend_rank')}</h2>
<p class="sub">{tr('p_backend_rank')}</p>
<div class="scroll"><table class="sortable">
<thead><tr><th>{tr('th_num')}</th><th>{tr('th_backend')}</th><th>{tr('th_qpu_hours')}</th>
  <th>{tr('th_share')}</th><th>{tr('th_jobs')}</th><th>{tr('th_users_on')}</th>
  <th>{tr('th_top_user')}</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>
<p class="sorthint">{tr('sort_hint')}</p>"""

    def backend_section(breakdown: Any) -> str:
        return _matrix(breakdown, "h_backend", "p_backend", "th_backend_total")

    def queue_section(impacts: list[QueueImpact], labels: dict[str, str]) -> str:
        if not impacts:
            return ""
        rows = "".join(
            "<tr>"
            f'<td class="rownum">{i + 1}</td>'
            f'<td data-sort="{esc(labels.get(q.user_id) or q.user_id)}">'
            f"{esc(labels.get(q.user_id) or q.user_id)}</td>"
            f'<td class="hash">{esc(q.user_id)}</td>'
            + num(f"{q.jobs:,}", q.jobs)
            + num(f"{q.qpu_hours:.2f}h", f"{q.qpu_hours:.4f}")
            + num(
                f"<b>{q.others_wait_overlap_hours:.1f}h</b>",
                f"{q.others_wait_overlap_hours:.4f}",
            )
            + num(f"{q.blocking_share * 100:.1f}%", f"{q.blocking_share:.6f}")
            + num(f"{q.others_jobs_affected:,}", q.others_jobs_affected)
            + num(q.others_users_affected, q.others_users_affected)
            + num(q.max_concurrent, q.max_concurrent)
            + num(q.max_burst, q.max_burst)
            + num(
                "—" if q.median_gap_seconds is None else f"{q.median_gap_seconds:.1f}s",
                -1 if q.median_gap_seconds is None else f"{q.median_gap_seconds:.3f}",
            )
            + num(q.containers, q.containers)
            + "</tr>"
            for i, q in enumerate(impacts[:15])
        )
        return f"""
<h2>{tr('h_queue')}</h2>
<p class="sub">{tr('p_queue')}</p>
<div class="scroll"><table class="sortable">
<thead><tr>
  <th>{tr('th_num')}</th><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>
  <th>{tr('th_jobs')}</th><th>{tr('th_qpu_held')}</th><th>{tr('th_delay')}</th>
  <th>{tr('th_share')}</th><th>{tr('th_jobs_aff')}</th><th>{tr('th_users_aff')}</th>
  <th>{tr('th_max_conc')}</th><th>{tr('th_max_burst')}</th><th>{tr('th_median_gap')}</th>
  <th>{tr('th_containers')}</th>
</tr></thead><tbody>{rows}</tbody>
</table></div>
<div class="legend">
  <span>{tr('lg_delay')}</span><span>{tr('lg_burst')}</span><span>{tr('lg_containers')}</span>
</div>
<p class="sorthint">{tr('sort_hint')}</p>"""

    def family_block(families: list[FamilyDiff]) -> str:
        usable = [f for f in families if f.circuits_compared >= 2]
        if not usable:
            return ""
        verdict_keys = {
            "identical circuit": "fam_v_identical",
            "nearly identical (measurement basis or similar)": "fam_v_near",
            "genuinely different circuits": "fam_v_different",
            "not comparable": "fam_v_na",
        }
        rows = "".join(
            "<tr>"
            f"<td>{tr(verdict_keys.get(f.verdict, 'fam_v_na'))}</td>"
            f'<td class="num">{f.runs}</td>'
            f'<td class="num">{f.circuits_compared}</td>'
            f'<td class="num">{f.total_ops}</td>'
            f'<td class="num">{f.common_prefix}</td>'
            f'<td class="num">{f.common_suffix}</td>'
            f'<td class="num">{f.differing_ops} ({f.diff_ratio * 100:.1f}%)</td>'
            f"<td>{esc(', '.join(dict.fromkeys(f.sample_names))[:60] or '—')}</td>"
            "</tr>"
            for f in usable
        )
        return (
            f"<details><summary>{tr('fam_summary')}</summary>"
            f"<p class='sub' style='margin:8px 0'>{tr('fam_p')}</p>"
            "<div class='scroll'><table><thead><tr>"
            f"<th>{tr('th_verdict')}</th><th>{tr('th_runs')}</th>"
            f"<th>{tr('fam_th_compared')}</th><th>{tr('fam_th_total_ops')}</th>"
            f"<th>{tr('fam_th_head')}</th><th>{tr('fam_th_tail')}</th>"
            f"<th>{tr('fam_th_diff')}</th><th>{tr('fam_th_names')}</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table></div></details>"
        )

    def user_block(
        store: Store,
        user: UserReport,
        cfg: dict[str, Any],
        families: list[FamilyDiff] | None = None,
    ) -> str:
        top_n = int(cfg.get("top_circuits_per_user", 5))
        snippet_lines = int(cfg.get("qasm_snippet_lines", 40))
        flagged = any(g.verdict == "abuse" for g in user.groups)

        def group_label(group: CircuitGroup) -> str:
            if group.kind == "intent" and group.name:
                return esc(group.name)
            name = esc(group.name) if group.name else tr("ev_unnamed")
            return f"{name} · {esc(group.identity[:8])}"

        rows = []
        for group in user.groups[:top_n]:
            interval = group.median_interval_min
            if group.identical_payload:
                payloads = tr("pay_identical")
            elif group.runs > 1:
                payloads = tr("pay_variants", n=group.distinct_exact)
            else:
                payloads = "—"
            rows.append(
                "<tr>"
                f"<td>{badge(group.verdict)}</td>"
                f'<td title="{esc(group.identity)}">{group_label(group)}</td>'
                f'<td class="num">{group.runs}</td>'
                f'<td class="num">{payloads}</td>'
                f'<td class="num">{_fmt_seconds(group.seconds)}</td>'
                f'<td class="num">{_fmt_seconds(group.repeat_seconds)}</td>'
                f'<td class="num">{f"{interval:.1f}m" if interval is not None else "—"}</td>'
                f"<td>{esc(', '.join(sorted(group.backends)) or '—')}</td>"
                f"<td>{esc(', '.join(str(s) for s in sorted(group.shots)) or '—')}</td>"
                f'<td class="num">{group.n_qubits}q / {group.n_ops}op / 2q {group.n_2q_ops}</td>'
                "</tr>"
            )

        evidence = []
        for group in user.groups[:top_n]:
            if group.verdict == "benign":
                continue
            reasons = "".join(f"<li>{trm(r)}</li>" for r in group.reasons)
            jobs = ", ".join(group.job_ids[:12])
            more = tr("ev_more", n=group.runs - 12) if group.runs > 12 else ""
            evidence.append(
                "<details>"
                f"<summary>{badge(group.verdict)} {group_label(group)} — "
                f"{tr('ev_show', runs=group.runs, qpu=_fmt_seconds(group.seconds))}</summary>"
                f"<ul class='findings'>{reasons}</ul>"
                f"{timeline_svg(group)}"
                f"<p class='sub' style='margin:6px 0'>{tr('ev_jobids')}: "
                f"<code>{esc(jobs)}</code> {more}</p>"
                + circuit_evidence(store, group.exact_hash, snippet_lines)
                + "</details>"
            )

        breakdown = "".join(
            f'<tr><td>{tr("sig_" + key)}</td>'
            f'<td class="num">{value:.1f}</td>'
            f'<td style="width:140px"><div class="bar">'
            f'<i style="width:{min(value / 30 * 100, 100):.0f}%"></i></div></td></tr>'
            for key, value in sorted(user.breakdown.items(), key=lambda kv: -kv[1])
            if value > 0
        )
        findings = (
            "<ul class='findings'>"
            + "".join(f"<li>{trm(f)}</li>" for f in user.findings)
            + "</ul>"
            if user.findings else ""
        )
        score_block = (
            f"<details><summary>{tr('score_summary')}</summary>"
            "<div class='scroll' style='margin-top:8px'><table><thead><tr>"
            f"<th>{tr('score_th_component')}</th><th>{tr('sig_th_points')}</th><th></th>"
            "</tr></thead><tbody>" + breakdown + "</tbody></table></div></details>"
            if breakdown else ""
        )

        return f"""
<div class="user{' flagged' if flagged else ''}">
  <div class="uhead">
    <h3>{esc(user.label)}</h3>
    <span class="uid">{esc(user.user_id)}</span>
    <span style="flex:1"></span>
    <span class="score">{user.score:.0f}</span><span class="sub" style="margin:0">/100</span>
  </div>
  <p class="sub" style="margin:2px 0 0">{tr(
      'u_summary', jobs=user.jobs, runs=user.runs, qpu=_fmt_seconds(user.seconds),
      share=f"{user.instance_share * 100:.1f}", distinct=user.unique_exact,
      ratio=f"{user.unique_ratio * 100:.0f}", payloads=user.unique_payloads,
      cov=f"{user.coverage * 100:.0f}")}</p>
  {signal_chips(user)}
  {findings}
  <div class="scroll" style="margin-top:12px">
    <table>
      <thead><tr>
        <th>{tr('th_verdict')}</th><th>{tr('th_circuit')}</th><th>{tr('th_runs')}</th>
        <th>{tr('th_payloads')}</th><th>{tr('th_qpu')}</th><th>{tr('th_repeat_cost')}</th>
        <th>{tr('th_median_gap')}</th><th>{tr('th_backend')}</th><th>{tr('th_shots')}</th>
        <th>{tr('th_size')}</th>
      </tr></thead>
      <tbody>{"".join(rows) or f'<tr><td colspan="10">{tr("no_circuit_data")}</td></tr>'}</tbody>
    </table>
  </div>
  {"".join(evidence)}
  {signal_table(user.signals)}
  {family_block(families or [])}
  {score_block}
</div>"""

    def ranking_row(index: int, u: UserReport) -> str:
        if u.top_instance:
            top_cell = num(
                f'{u.top_instance_share * 100:.0f}%'
                f'<span class="sub" style="font-size:11px"> {esc(u.top_instance)}</span>',
                f"{u.top_instance_share:.6f}",
            )
        else:
            top_cell = '<td class="num" data-sort="-1" style="opacity:.35">—</td>'
        return (
            "<tr>"
            f'<td class="rownum">{index}</td>'
            f'<td data-sort="{esc(u.label)}">{esc(u.label)}</td>'
            f'<td class="hash">{esc(u.user_id)}</td>'
            + num(f"<b>{u.score:.0f}</b>", f"{u.score:.2f}")
            + num(u.jobs, u.jobs)
            + num(_fmt_seconds(u.seconds), f"{u.seconds:.3f}")
            + num(f"{u.instance_share * 100:.1f}%", f"{u.instance_share:.6f}")
            + top_cell
            + num(
                f"<b>{_fmt_seconds(u.flagged_waste_seconds)}</b>",
                f"{u.flagged_waste_seconds:.3f}",
            )
            + num(f"{u.waste_share * 100:.1f}%", f"{u.waste_share:.6f}")
            + num(f"{u.unique_ratio * 100:.0f}%", f"{u.unique_ratio:.6f}")
            + num(f"{u.top_circuit_share * 100:.0f}%", f"{u.top_circuit_share:.6f}")
            + num(
                f"{u.interval_cv:.2f}" if u.interval_cv is not None else "—",
                -1 if u.interval_cv is None else f"{u.interval_cv:.4f}",
            )
            + "</tr>"
        )

    return {
        "badge": badge,
        "compare_section": compare_section,
        "backend_ranking": backend_ranking,
        "backend_section": backend_section,
        "usage_section": usage_section,
        "instance_section": instance_section,
        "queue_section": queue_section,
        "user_block": user_block,
        "ranking_row": ranking_row,
    }

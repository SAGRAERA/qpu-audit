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

    def instance_section(breakdown: Any) -> str:
        if not breakdown or not breakdown.instances:
            return ""
        head = "".join(
            f"<th>{esc(breakdown.instance_name(crn))}</th>" for crn in breakdown.instances
        )
        rows = []
        grand = breakdown.grand_total()
        for user in breakdown.users[:25]:
            cells = ""
            for crn in breakdown.instances:
                seconds = breakdown.seconds(user, crn)
                if seconds:
                    share = breakdown.user_share_of(user, crn)
                    emphasis = ' style="font-weight:600"' if share >= 0.5 else ""
                    cells += (
                        f'<td class="num"{emphasis}>{seconds / 3600:.2f}'
                        f'<span class="sub" style="font-size:11px"> {share * 100:.0f}%</span></td>'
                    )
                else:
                    cells += '<td class="num" style="opacity:.35">—</td>'
            total = breakdown.user_total(user)
            rows.append(
                "<tr>"
                f"<td>{esc(breakdown.labels.get(user) or user)}</td>"
                f'<td class="hash">{esc(user)}</td>'
                f"{cells}"
                f'<td class="num"><b>{total / 3600:.2f}</b>'
                f'<span class="sub" style="font-size:11px"> '
                f'{total / grand * 100 if grand else 0:.0f}%</span></td>'
                "</tr>"
            )
        totals = "".join(
            f'<td class="num">{breakdown.instance_total(crn) / 3600:.2f}</td>'
            for crn in breakdown.instances
        )
        return f"""
<h2>{tr('h_instance')}</h2>
<p class="sub">{tr('p_instance')}</p>
<div class="scroll"><table>
<thead><tr><th>{tr('th_user')}</th><th>{tr('th_userid')}</th>{head}
  <th>{tr('th_total')}</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
<tfoot><tr><th colspan="2">{tr('th_instance_total')}</th>{totals}
  <th class="num">{grand / 3600:.2f}</th></tr></tfoot>
</table></div>"""

    def queue_section(impacts: list[QueueImpact], labels: dict[str, str]) -> str:
        if not impacts:
            return ""
        rows = "".join(
            "<tr>"
            f"<td>{i + 1}</td>"
            f"<td>{esc(labels.get(q.user_id) or q.user_id)}</td>"
            f'<td class="hash">{esc(q.user_id)}</td>'
            f'<td class="num">{q.jobs:,}</td>'
            f'<td class="num">{q.qpu_hours:.2f}h</td>'
            f'<td class="num"><b>{q.others_wait_overlap_hours:.1f}h</b></td>'
            f'<td class="num">{q.blocking_share * 100:.1f}%</td>'
            f'<td class="num">{q.others_jobs_affected:,}</td>'
            f'<td class="num">{q.others_users_affected}</td>'
            f'<td class="num">{q.max_concurrent}</td>'
            f'<td class="num">{q.max_burst}</td>'
            f'<td class="num">'
            f'{"—" if q.median_gap_seconds is None else f"{q.median_gap_seconds:.1f}s"}</td>'
            f'<td class="num">{q.containers}</td>'
            "</tr>"
            for i, q in enumerate(impacts[:15])
        )
        return f"""
<h2>{tr('h_queue')}</h2>
<p class="sub">{tr('p_queue')}</p>
<div class="scroll"><table>
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
</div>"""

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
            top_cell = (
                f'<td class="num">{u.top_instance_share * 100:.0f}%'
                f'<span class="sub" style="font-size:11px"> {esc(u.top_instance)}</span></td>'
            )
        else:
            top_cell = '<td class="num" style="opacity:.35">—</td>'
        return (
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{esc(u.label)}</td>"
            f'<td class="hash">{esc(u.user_id)}</td>'
            f'<td class="num"><b>{u.score:.0f}</b></td>'
            f'<td class="num">{u.jobs}</td>'
            f'<td class="num">{_fmt_seconds(u.seconds)}</td>'
            f'<td class="num">{u.instance_share * 100:.1f}%</td>'
            f"{top_cell}"
            f'<td class="num"><b>{_fmt_seconds(u.flagged_waste_seconds)}</b></td>'
            f'<td class="num">{u.waste_share * 100:.1f}%</td>'
            f'<td class="num">{u.unique_ratio * 100:.0f}%</td>'
            f'<td class="num">{u.top_circuit_share * 100:.0f}%</td>'
            f'<td class="num">'
            f'{f"{u.interval_cv:.2f}" if u.interval_cv is not None else "—"}</td>'
            "</tr>"
        )

    return {
        "badge": badge,
        "usage_section": usage_section,
        "instance_section": instance_section,
        "queue_section": queue_section,
        "user_block": user_block,
        "ranking_row": ranking_row,
    }

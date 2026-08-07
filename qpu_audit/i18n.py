"""Translations for the HTML report.

Reports get handed to other people, so the reader picks the language rather than the
person generating it. Every string lives here, keyed message-first so that adding a
language means filling one column down the file rather than hunting through the code.

Two kinds of string:

  STRINGS    static chrome — headings, table headers, legends, labels
  MESSAGES   sentences with numbers in them, formatted server-side per language

Adding a language:
  1. add the code to LANGUAGES
  2. add that key to every entry below (missing keys fall back to English)
  3. `python -m qpu_audit selftest -o docs/sample-report.html` and check it renders

Translations are contributed, not authoritative. If a term reads wrong in your
language, a pull request fixing it is welcome.
"""

from __future__ import annotations

from typing import Any

# code -> label shown in the report's language selector
LANGUAGES: dict[str, str] = {
    "en": "English",
    "ko": "한국어",
    "ja": "日本語",
    "es": "Español",
}
LANG_CODES = list(LANGUAGES)
DEFAULT_LANG = "en"

# Languages whose translations have not been reviewed by a native speaker.
# Shown with a marker in the selector so readers know what they are getting.
UNREVIEWED = {"ja", "es"}


STRINGS: dict[str, dict[str, str]] = {
    # -- page chrome ------------------------------------------------------
    "title": {
        "en": "QPU usage audit",
        "ko": "QPU 사용 감사 리포트",
        "ja": "QPU 使用状況の監査",
        "es": "Auditoría de uso de QPU",
    },
    "generated": {
        "en": "Generated {when} · last {days} days · qpu-audit",
        "ko": "생성 {when} · 최근 {days}일 · qpu-audit",
        "ja": "生成 {when} · 直近 {days} 日 · qpu-audit",
        "es": "Generado {when} · últimos {days} días · qpu-audit",
    },
    "lang_label": {
        "en": "Language", "ko": "언어", "ja": "言語", "es": "Idioma",
    },
    "unreviewed_tag": {
        "en": "unreviewed", "ko": "미검수", "ja": "未校閲", "es": "sin revisar",
    },
    # -- summary cards -----------------------------------------------------
    "card_window": {"en": "Window", "ko": "분석 기간", "ja": "対象期間", "es": "Periodo"},
    "card_window_note": {
        "en": "{jobs} jobs", "ko": "job {jobs}건", "ja": "ジョブ {jobs} 件", "es": "{jobs} trabajos",
    },
    "card_qpu": {"en": "Total QPU", "ko": "총 QPU 시간", "ja": "QPU 合計", "es": "QPU total"},
    "card_qpu_note": {
        "en": "{runs} executions", "ko": "실행 {runs}회",
        "ja": "実行 {runs} 回", "es": "{runs} ejecuciones",
    },
    "card_waste": {
        "en": "Unexplained repeats", "ko": "설명불가 중복",
        "ja": "説明のつかない反復", "es": "Repeticiones sin explicar",
    },
    "card_waste_note": {
        "en": "{pct}% of total", "ko": "전체의 {pct}%",
        "ja": "全体の {pct}%", "es": "{pct}% del total",
    },
    "card_users": {"en": "Users", "ko": "사용자", "ja": "ユーザー", "es": "Usuarios"},
    "card_users_note": {
        "en": "{n} flagged", "ko": "{n}명 지목", "ja": "{n} 名を検出", "es": "{n} señalados",
    },
    "card_cov": {
        "en": "Circuits retrieved", "ko": "회로 확보율",
        "ja": "回路の取得率", "es": "Circuitos obtenidos",
    },
    "card_cov_note": {
        "en": "run collect again if low", "ko": "낮으면 collect 를 더 돌리세요",
        "ja": "低い場合は collect を再実行", "es": "vuelve a ejecutar collect si es bajo",
    },
    # -- ranking -----------------------------------------------------------
    "h_ranking": {
        "en": "User ranking", "ko": "사용자 랭킹",
        "ja": "ユーザー順位", "es": "Clasificación de usuarios",
    },
    "p_ranking": {
        "en": "Sorted by <b>absolute unexplained repeat time</b>, because a small user with a "
              "bad ratio should not outrank someone burning real hours. The score is a weighted "
              "sum of <b>nine risk signals</b> (max 100) in three classes, and is not evidence "
              "in itself: <b>wasted QPU</b> (60) questions the work, <b>queue impact</b> (20) "
              "harms others whether or not the work is legitimate, and <b>context</b> (20) is "
              "information only. A large but perfectly valid experiment lights up context "
              "signals — always read the per-user evidence below.",
        "ko": "<b>설명불가 중복 시간의 절대량</b> 기준으로 정렬했습니다. 비율만 나쁜 소규모 "
              "사용자가 실제로 시간을 태운 사람보다 위에 오면 안 되기 때문입니다. 점수는 "
              "<b>위험 신호 9종</b>을 세 분류로 가중합한 값(최대 100)이며 그 자체가 증거는 "
              "아닙니다. <b>낭비된 QPU</b>(60)는 작업 자체를 문제 삼고, <b>큐 영향</b>(20)은 "
              "작업이 정당하든 아니든 남에게 해가 되며, <b>맥락</b>(20)은 정보일 뿐입니다. "
              "크지만 완전히 정당한 실험도 맥락 신호는 켭니다 — 아래 사용자별 근거를 반드시 "
              "확인하세요.",
        "ja": "<b>説明のつかない反復時間の絶対量</b>で並べています。比率だけ悪い小規模利用者が、"
              "実際に多くの時間を消費した利用者より上に来ないようにするためです。スコアは"
              "<b>9 種類のリスク信号</b>を 3 分類で加重した値（最大 100）であり、それ自体は"
              "証拠ではありません。<b>無駄な QPU</b>（60）は作業自体を問い、<b>キュー影響</b>"
              "（20）は作業が正当かどうかに関わらず他者に害を与え、<b>文脈</b>（20）は情報に"
              "すぎません。規模が大きいだけの正当な実験も文脈信号を点灯させます — 必ず下記の"
              "利用者別の根拠を確認してください。",
        "es": "Ordenado por el <b>tiempo absoluto de repetición sin explicar</b>, porque un "
              "usuario pequeño con mala proporción no debería superar a quien consume horas "
              "reales. La puntuación es una suma ponderada de <b>nueve señales de riesgo</b> "
              "(máx. 100) en tres clases, y no constituye prueba por sí misma: <b>QPU "
              "desperdiciada</b> (60) cuestiona el trabajo, <b>impacto en la cola</b> (20) "
              "perjudica a otros sea legítimo o no, y <b>contexto</b> (20) es solo información. "
              "Un experimento grande pero perfectamente válido enciende las señales de "
              "contexto — lee siempre las pruebas por usuario más abajo.",
    },
    "th_num": {"en": "#", "ko": "#", "ja": "#", "es": "#"},
    "th_user": {"en": "User", "ko": "사용자", "ja": "ユーザー", "es": "Usuario"},
    "th_userid": {"en": "user_id", "ko": "user_id", "ja": "user_id", "es": "user_id"},
    "th_score": {"en": "Score", "ko": "점수", "ja": "スコア", "es": "Puntuación"},
    "th_jobs": {"en": "Jobs", "ko": "jobs", "ja": "ジョブ", "es": "Trabajos"},
    "th_qpu": {"en": "QPU", "ko": "QPU", "ja": "QPU", "es": "QPU"},
    "th_share_all": {
        "en": "Share (all)", "ko": "점유율(전체)", "ja": "占有率（全体）", "es": "Cuota (total)",
    },
    "th_share_top": {
        "en": "Share (top inst.)", "ko": "점유율(최대 인스턴스)",
        "ja": "占有率（最大インスタンス）", "es": "Cuota (instancia máx.)",
    },
    "th_unexplained": {
        "en": "Unexplained repeats", "ko": "설명불가 중복",
        "ja": "説明のつかない反復", "es": "Repeticiones sin explicar",
    },
    "th_of_total": {"en": "Of total", "ko": "전체 대비", "ja": "全体比", "es": "Del total"},
    "th_unique": {
        "en": "Unique ratio", "ko": "고유회로율", "ja": "固有回路率", "es": "Ratio único",
    },
    "th_top_circuit": {
        "en": "Top circuit", "ko": "최다 회로", "ja": "最多回路", "es": "Circuito principal",
    },
    "th_cv": {"en": "Interval CV", "ko": "간격 CV", "ja": "間隔 CV", "es": "CV de intervalo"},
    "lg_share": {
        "en": "Share (all) = fraction of QPU time across every instance; Share (top inst.) = "
              "the largest fraction held inside any single instance",
        "ko": "점유율(전체) = 모든 인스턴스를 합친 QPU 시간 비중 · 점유율(최대 인스턴스) = "
              "단일 인스턴스 안에서 차지한 최대 비중",
        "ja": "占有率（全体）＝全インスタンス合計の QPU 時間比 · 占有率（最大インスタンス）＝"
              "単一インスタンス内で占めた最大比率",
        "es": "Cuota (total) = fracción del tiempo de QPU en todas las instancias; Cuota "
              "(instancia máx.) = mayor fracción dentro de una sola instancia",
    },
    "lg_unexplained": {
        "en": "Unexplained repeats = QPU time from repetition not judged normal "
              "(grey counts half)",
        "ko": "설명불가 중복 = 정상으로 판정되지 않은 반복이 태운 QPU 시간 (회색은 절반 반영)",
        "ja": "説明のつかない反復＝正常と判定されなかった反復が消費した QPU 時間（灰色は半分）",
        "es": "Repeticiones sin explicar = tiempo de QPU por repetición no considerada normal "
              "(gris cuenta la mitad)",
    },
    "lg_unique": {
        "en": "Unique ratio = distinct circuits / total executions",
        "ko": "고유회로율 = 고유 회로 종수 / 총 실행 횟수",
        "ja": "固有回路率＝固有回路数 / 総実行回数",
        "es": "Ratio único = circuitos distintos / ejecuciones totales",
    },
    "lg_cv": {
        "en": "Interval CV = coefficient of variation of submission gaps (lower is more "
              "mechanical)",
        "ko": "간격 CV = 제출 간격의 변동계수 (낮을수록 기계적)",
        "ja": "間隔 CV＝投入間隔の変動係数（低いほど機械的）",
        "es": "CV de intervalo = coeficiente de variación de los intervalos de envío "
              "(menor = más mecánico)",
    },
    # -- monthly usage -----------------------------------------------------
    "h_usage": {
        "en": "Monthly usage", "ko": "월별 사용량",
        "ja": "月別使用量", "es": "Uso mensual",
    },
    "p_usage": {
        "en": "QPU hours per user. This table accumulates in a local ledger, so <b>it survives "
              "IBM deleting the underlying workload records</b>. It is refreshed on every "
              "<code>collect</code>. A month still in progress is scaled to a full-month "
              "estimate before comparison, otherwise everyone appears to collapse during the "
              "first days of a month.",
        "ko": "사용자별 QPU 시간입니다. 로컬 원장에 누적되므로 <b>IBM 이 원본 워크로드를 지운 "
              "뒤에도 남습니다</b>. <code>collect</code> 를 돌릴 때마다 갱신됩니다. 진행 중인 "
              "달은 비교 전에 월말 기준으로 환산합니다 — 안 그러면 매달 초에 전원이 급감한 것처럼 "
              "보입니다.",
        "ja": "ユーザー別の QPU 時間です。ローカル台帳に蓄積されるため、<b>IBM が元のワークロード"
              "記録を削除した後も残ります</b>。<code>collect</code> のたびに更新されます。進行中の"
              "月は比較前に月末換算します。そうしないと月初に全員が急減したように見えます。",
        "es": "Horas de QPU por usuario. Esta tabla se acumula en un registro local, así que "
              "<b>sobrevive a que IBM elimine los registros de trabajo originales</b>. Se "
              "actualiza en cada <code>collect</code>. Un mes en curso se escala a una "
              "estimación de mes completo antes de comparar; de lo contrario todos parecen "
              "desplomarse los primeros días del mes.",
    },
    "th_total": {"en": "Total", "ko": "합계", "ja": "合計", "es": "Total"},
    "th_vs_prev": {
        "en": "vs prev.", "ko": "전월 대비", "ja": "前月比", "es": "vs ant.",
    },
    "th_month_total": {
        "en": "Month total", "ko": "월 합계", "ja": "月合計", "es": "Total del mes",
    },
    "tag_in_progress": {
        "en": "in progress", "ko": "진행 중", "ja": "進行中", "es": "en curso",
    },
    "chg_new": {"en": "new", "ko": "신규", "ja": "新規", "es": "nuevo"},
    "chg_est": {"en": "est.", "ko": "예상", "ja": "推定", "es": "est."},
    # -- per instance ------------------------------------------------------
    "h_instance": {
        "en": "Usage by instance", "ko": "인스턴스별 사용량",
        "ja": "インスタンス別使用量", "es": "Uso por instancia",
    },
    "p_instance": {
        "en": "QPU hours per user per instance, with the percentage of that instance in small "
              "type. Both views matter: the per-instance columns expose someone monopolising a "
              "single instance, while the <b>total</b> column exposes someone spread across all "
              "of them who nevertheless dominates the account. Neither is visible from the other.",
        "ko": "사용자별·인스턴스별 QPU 시간이고, 작은 글씨는 해당 인스턴스 내 점유율입니다. "
              "두 관점이 모두 필요합니다. 인스턴스별 열은 한 인스턴스를 독점하는 사람을 드러내고, "
              "<b>합계</b> 열은 여러 인스턴스에 나눠 쓰면서도 계정 전체를 지배하는 사람을 "
              "드러냅니다. 한쪽만 봐서는 다른 쪽이 보이지 않습니다.",
        "ja": "ユーザー別・インスタンス別の QPU 時間で、小さい文字は当該インスタンス内の占有率です。"
              "両方の視点が必要です。インスタンス別の列は単一インスタンスを独占する利用者を、"
              "<b>合計</b>列は複数に分散しつつアカウント全体を支配する利用者を明らかにします。"
              "片方だけでは他方は見えません。",
        "es": "Horas de QPU por usuario y por instancia, con el porcentaje de esa instancia en "
              "letra pequeña. Ambas vistas importan: las columnas por instancia revelan a quien "
              "monopoliza una sola instancia, mientras que la columna <b>total</b> revela a quien "
              "se reparte entre todas y aun así domina la cuenta. Ninguna se ve desde la otra.",
    },
    "th_instance_total": {
        "en": "Instance total", "ko": "인스턴스 합계",
        "ja": "インスタンス合計", "es": "Total de instancia",
    },
    # -- queue impact ------------------------------------------------------
    "h_queue": {
        "en": "Queue impact", "ko": "큐 점유 영향",
        "ja": "キューへの影響", "es": "Impacto en la cola",
    },
    "p_queue": {
        "en": "Consuming QPU time and delaying other people are different quantities. A serial "
              "QPU is blocked by <b>occupancy</b>, not by queue presence, so this measures time "
              "spent executing while another user's job was waiting on the same backend. "
              "Intervals are approximated as <code>[ended − qpu_seconds, ended]</code> and jobs "
              "without an end timestamp are excluded — use these figures to compare your own "
              "users, not as an absolute account of delay. Most queue time on shared backends "
              "comes from organizations this tool cannot see.",
        "ko": "QPU 시간을 쓰는 것과 남을 기다리게 하는 것은 다른 양입니다. 직렬 QPU 를 막는 것은 "
              "큐에 있는 것이 아니라 <b>점유</b>이므로, 다른 사용자의 job 이 같은 backend 에서 "
              "대기하는 동안 실제로 실행 중이던 시간을 잽니다. 구간은 "
              "<code>[ended − qpu_seconds, ended]</code> 로 근사했고 종료 시각이 없는 job 은 "
              "제외했습니다 — 절대적인 지연량이 아니라 내부 사용자 간 비교로 쓰세요. 공유 "
              "backend 대기의 대부분은 이 도구가 볼 수 없는 다른 조직에서 옵니다.",
        "ja": "QPU 時間を使うことと他者を待たせることは別の量です。直列の QPU を塞ぐのはキューに"
              "並んでいることではなく<b>占有</b>なので、他の利用者のジョブが同じバックエンドで"
              "待機している間に実際に実行していた時間を測ります。区間は "
              "<code>[ended − qpu_seconds, ended]</code> で近似し、終了時刻のないジョブは除外して"
              "います — 絶対的な遅延量ではなく、内部利用者どうしの比較に使ってください。共有"
              "バックエンドの待ち時間の大半は、このツールから見えない他組織に由来します。",
        "es": "Consumir tiempo de QPU y retrasar a otros son magnitudes distintas. Una QPU serie "
              "se bloquea por <b>ocupación</b>, no por presencia en la cola, así que esto mide el "
              "tiempo ejecutando mientras el trabajo de otro usuario esperaba en el mismo "
              "backend. Los intervalos se aproximan como "
              "<code>[ended − qpu_seconds, ended]</code> y se excluyen los trabajos sin marca de "
              "fin — usa estas cifras para comparar entre tus usuarios, no como cuenta absoluta "
              "del retraso. La mayor parte de la espera en backends compartidos proviene de "
              "organizaciones que esta herramienta no puede ver.",
    },
    "th_qpu_held": {
        "en": "QPU held", "ko": "QPU 점유", "ja": "QPU 占有", "es": "QPU ocupada",
    },
    "th_delay": {
        "en": "Delay caused", "ko": "타인 대기 유발",
        "ja": "他者の待機を誘発", "es": "Retraso causado",
    },
    "th_share": {"en": "Share", "ko": "비중", "ja": "比率", "es": "Cuota"},
    "th_jobs_aff": {
        "en": "Jobs affected", "ko": "영향받은 job",
        "ja": "影響ジョブ", "es": "Trabajos afectados",
    },
    "th_users_aff": {
        "en": "Users affected", "ko": "영향받은 사람",
        "ja": "影響ユーザー", "es": "Usuarios afectados",
    },
    "th_max_conc": {
        "en": "Max concurrent", "ko": "최대 동시 대기",
        "ja": "最大同時待機", "es": "Máx. simultáneos",
    },
    "th_max_burst": {
        "en": "Max burst", "ko": "최대 버스트", "ja": "最大バースト", "es": "Ráfaga máx.",
    },
    "th_median_gap": {
        "en": "Median gap", "ko": "제출간격 중앙값",
        "ja": "投入間隔の中央値", "es": "Intervalo mediano",
    },
    "th_containers": {
        "en": "session/batch", "ko": "session/batch",
        "ja": "session/batch", "es": "session/batch",
    },
    "lg_delay": {
        "en": "Delay caused = time occupying the QPU while others were queued on that backend",
        "ko": "타인 대기 유발 = 다른 사용자가 그 backend 에서 대기하는 동안 QPU 를 점유한 시간",
        "ja": "他者の待機を誘発＝他の利用者が当該バックエンドで待機中に QPU を占有した時間",
        "es": "Retraso causado = tiempo ocupando la QPU mientras otros esperaban en ese backend",
    },
    "lg_burst": {
        "en": "Max burst = most jobs submitted within any 60-second window",
        "ko": "최대 버스트 = 60초 안에 연속 제출된 job 최대 개수",
        "ja": "最大バースト＝60 秒以内に投入されたジョブの最大数",
        "es": "Ráfaga máx. = mayor número de trabajos enviados en 60 segundos",
    },
    "lg_containers": {
        "en": "session/batch = containers created (0 means every job was submitted individually)",
        "ko": "session/batch = 생성한 컨테이너 수 (0 이면 모든 job 을 개별 제출)",
        "ja": "session/batch＝作成したコンテナ数（0 は全ジョブを個別投入）",
        "es": "session/batch = contenedores creados (0 significa que cada trabajo se envió "
              "individualmente)",
    },
    # -- per-user detail ---------------------------------------------------
    "h_detail": {
        "en": "Per-user detail", "ko": "사용자별 상세",
        "ja": "ユーザー別の詳細", "es": "Detalle por usuario",
    },
    "p_no_users": {
        "en": "No users to show.", "ko": "표시할 사용자가 없습니다.",
        "ja": "表示するユーザーがいません。", "es": "No hay usuarios que mostrar.",
    },
    "u_summary": {
        "en": "{jobs} jobs · {runs} executions · {qpu} QPU ({share}% of instance) · "
              "{distinct} distinct circuits ({ratio}%) · {payloads} payloads · "
              "{cov}% circuits retrieved",
        "ko": "job {jobs}건 · 실행 {runs}회 · QPU {qpu} (인스턴스의 {share}%) · "
              "고유회로 {distinct}종 ({ratio}%) · 페이로드 {payloads}종 · 회로 확보율 {cov}%",
        "ja": "ジョブ {jobs} 件 · 実行 {runs} 回 · QPU {qpu}（インスタンスの {share}%） · "
              "固有回路 {distinct} 種（{ratio}%） · ペイロード {payloads} 種 · 回路取得率 {cov}%",
        "es": "{jobs} trabajos · {runs} ejecuciones · {qpu} QPU ({share}% de la instancia) · "
              "{distinct} circuitos distintos ({ratio}%) · {payloads} cargas · "
              "{cov}% circuitos obtenidos",
    },
    "th_verdict": {"en": "Verdict", "ko": "판정", "ja": "判定", "es": "Veredicto"},
    "th_circuit": {"en": "Circuit", "ko": "회로", "ja": "回路", "es": "Circuito"},
    "th_runs": {"en": "Runs", "ko": "실행", "ja": "実行", "es": "Ejecuciones"},
    "th_payloads": {"en": "Payloads", "ko": "페이로드", "ja": "ペイロード", "es": "Cargas"},
    "th_repeat_cost": {
        "en": "Repeat cost", "ko": "중복 소모", "ja": "反復コスト", "es": "Coste repetición",
    },
    "th_backend": {"en": "Backend", "ko": "backend", "ja": "バックエンド", "es": "Backend"},
    "th_shots": {"en": "Shots", "ko": "shots", "ja": "ショット", "es": "Shots"},
    "th_size": {"en": "Size", "ko": "규모", "ja": "規模", "es": "Tamaño"},
    "pay_identical": {
        "en": "identical", "ko": "동일", "ja": "同一", "es": "idénticas",
    },
    "pay_variants": {
        "en": "{n} variants", "ko": "{n}종", "ja": "{n} 種", "es": "{n} variantes",
    },
    "no_circuit_data": {
        "en": "No circuit data", "ko": "회로 데이터 없음",
        "ja": "回路データなし", "es": "Sin datos de circuito",
    },
    "verdict_abuse": {
        "en": "flagged", "ko": "남용 의심", "ja": "要確認", "es": "señalado",
    },
    "verdict_gray": {
        "en": "unexplained", "ko": "설명 안 됨", "ja": "説明なし", "es": "sin explicar",
    },
    "verdict_benign": {
        "en": "normal", "ko": "정상", "ja": "正常", "es": "normal",
    },
    # -- evidence ----------------------------------------------------------
    "ev_show": {
        "en": "{runs} runs / {qpu} — show evidence",
        "ko": "{runs}회 / {qpu} — 근거 보기",
        "ja": "{runs} 回 / {qpu} — 根拠を表示",
        "es": "{runs} ejecuciones / {qpu} — ver pruebas",
    },
    "ev_jobids": {"en": "Job IDs", "ko": "job ID", "ja": "ジョブ ID", "es": "IDs de trabajo"},
    "ev_more": {
        "en": "and {n} more", "ko": "외 {n}건", "ja": "他 {n} 件", "es": "y {n} más",
    },
    "ev_no_details": {
        "en": "No details were retrieved for this circuit.",
        "ko": "이 회로의 상세 정보를 확보하지 못했습니다.",
        "ja": "この回路の詳細は取得できませんでした。",
        "es": "No se obtuvieron detalles de este circuito.",
    },
    "ev_undecodable": {
        "en": "The circuit could not be decoded (private job, or an unrecognised "
              "serialisation format).",
        "ko": "회로를 디코딩하지 못했습니다 (private job 이거나 알 수 없는 직렬화 포맷).",
        "ja": "回路をデコードできませんでした（private ジョブ、または未知の直列化形式）。",
        "es": "No se pudo decodificar el circuito (trabajo privado o formato de serialización "
              "desconocido).",
    },
    "ev_name": {"en": "Name", "ko": "회로명", "ja": "回路名", "es": "Nombre"},
    "ev_unnamed": {"en": "(unnamed)", "ko": "(이름 없음)", "ja": "（名前なし）", "es": "(sin nombre)"},
    "ev_size": {"en": "Size", "ko": "규모", "ja": "規模", "es": "Tamaño"},
    "ev_size_v": {
        "en": "{q} qubits / {c} clbits · {ops} operations · depth {depth} · "
              "{tq} two-qubit gates · measurement",
        "ko": "{q}큐빗 / {c}클래식비트 · 명령 {ops}개 · depth {depth} · "
              "2큐빗 게이트 {tq}개 · 측정",
        "ja": "{q} 量子ビット / {c} 古典ビット · 命令 {ops} 個 · depth {depth} · "
              "2 量子ビットゲート {tq} 個 · 測定",
        "es": "{q} cúbits / {c} bits clásicos · {ops} operaciones · profundidad {depth} · "
              "{tq} puertas de dos cúbits · medición",
    },
    "meas_present": {"en": "present", "ko": "있음", "ja": "あり", "es": "presente"},
    "meas_absent": {"en": "absent", "ko": "없음", "ja": "なし", "es": "ausente"},
    "ev_gates": {"en": "Gates", "ko": "게이트", "ja": "ゲート", "es": "Puertas"},
    "ev_metadata": {"en": "Metadata", "ko": "metadata", "ja": "メタデータ", "es": "Metadatos"},
    "ev_decoded_via": {
        "en": "decoded via: {src}", "ko": "디코딩 경로: {src}",
        "ja": "デコード経路: {src}", "es": "decodificado vía: {src}",
    },
    "ev_lines_shown": {
        "en": "... ({shown} of {total} lines shown)",
        "ko": "... (총 {total}줄 중 {shown}줄 표시)",
        "ja": "... （全 {total} 行中 {shown} 行を表示）",
        "es": "... ({shown} de {total} líneas mostradas)",
    },
    # -- signal table ------------------------------------------------------
    "sig_summary": {
        "en": "Risk signal detail", "ko": "위험 신호 상세",
        "ja": "リスク信号の詳細", "es": "Detalle de señales de riesgo",
    },
    "sig_th_signal": {"en": "Signal", "ko": "신호", "ja": "信号", "es": "Señal"},
    "sig_th_points": {"en": "Points", "ko": "점수", "ja": "点数", "es": "Puntos"},
    "sig_th_class": {"en": "Class", "ko": "분류", "ja": "分類", "es": "Clase"},
    "sig_th_basis": {"en": "Basis", "ko": "근거", "ja": "根拠", "es": "Base"},
    "sig_note": {
        "en": "<b>Wasted QPU</b> questions the work itself. <b>Queue impact</b> harms other "
              "users whether or not the work is legitimate — the remedy is usually batching, "
              "which does not question the science. <b>Context</b> is information only: it "
              "fires on ordinary situations such as a new user or a large but perfectly valid "
              "experiment, and justifies nothing by itself.",
        "ko": "<b>낭비된 QPU</b>는 작업 자체를 문제 삼습니다. <b>큐 영향</b>은 작업이 정당하든 "
              "아니든 다른 사용자에게 해가 되며, 해결책은 대개 batch 사용이라 연구 내용을 "
              "문제 삼지 않습니다. <b>맥락</b>은 정보일 뿐입니다 — 신규 사용자나 규모가 큰 "
              "정당한 실험처럼 평범한 상황에서도 켜지고, 그 자체로는 아무것도 정당화하지 "
              "않습니다.",
        "ja": "<b>無駄な QPU</b>は作業自体を問います。<b>キュー影響</b>は作業が正当かどうかに"
              "関わらず他の利用者に害を与えますが、対処は通常バッチ化であり、研究内容を問う"
              "ものではありません。<b>文脈</b>は情報にすぎません — 新規利用者や規模の大きい"
              "正当な実験など、ごく普通の状況でも点灯し、それ自体は何も正当化しません。",
        "es": "<b>QPU desperdiciada</b> cuestiona el trabajo en sí. <b>Impacto en la cola</b> "
              "perjudica a otros usuarios sea o no legítimo el trabajo — el remedio suele ser "
              "agrupar en lotes, lo que no cuestiona la ciencia. <b>Contexto</b> es solo "
              "información: se activa en situaciones corrientes como un usuario nuevo o un "
              "experimento grande pero válido, y no justifica nada por sí mismo.",
    },
    "cls_waste": {
        "en": "wasted QPU", "ko": "낭비된 QPU", "ja": "無駄な QPU", "es": "QPU desperdiciada",
    },
    "cls_queue": {
        "en": "queue impact", "ko": "큐 영향", "ja": "キュー影響", "es": "impacto en la cola",
    },
    "cls_context": {"en": "context", "ko": "맥락", "ja": "文脈", "es": "contexto"},
    # -- signal labels -----------------------------------------------------
    "sig_duplicate_waste": {
        "en": "repeated identical execution", "ko": "동일 실행 반복",
        "ja": "同一実行の反復", "es": "ejecución idéntica repetida",
    },
    "sig_top_circuit_share": {
        "en": "single-circuit concentration", "ko": "단일 회로 편중",
        "ja": "単一回路への偏り", "es": "concentración en un circuito",
    },
    "sig_trivial_circuit": {
        "en": "non-entangling circuits", "ko": "얽힘 없는 회로",
        "ja": "もつれのない回路", "es": "circuitos sin entrelazamiento",
    },
    "sig_failure_resubmit": {
        "en": "failed-payload resubmission", "ko": "실패 재제출",
        "ja": "失敗ペイロードの再投入", "es": "reenvío de carga fallida",
    },
    "sig_burst_submission": {
        "en": "burst submission", "ko": "버스트 제출",
        "ja": "バースト投入", "es": "envío en ráfaga",
    },
    "sig_no_session": {
        "en": "no session/batch grouping", "ko": "session/batch 미사용",
        "ja": "session/batch 未使用", "es": "sin agrupar en session/batch",
    },
    "sig_overuse": {
        "en": "suspected overuse", "ko": "과사용 의심",
        "ja": "過剰使用の疑い", "es": "sospecha de uso excesivo",
    },
    "sig_regular_interval": {
        "en": "mechanical submission interval", "ko": "기계적 제출 간격",
        "ja": "機械的な投入間隔", "es": "intervalo de envío mecánico",
    },
    "sig_usage_spike": {
        "en": "usage spike", "ko": "사용량 급증",
        "ja": "使用量の急増", "es": "pico de uso",
    },
    # -- circuit family ----------------------------------------------------
    "fam_summary": {
        "en": "How different are these circuits really?",
        "ko": "이 회로들이 실제로 얼마나 다른가",
        "ja": "これらの回路は実際どれだけ違うか",
        "es": "¿Cuán distintos son realmente estos circuitos?",
    },
    "fam_p": {
        "en": "Gate sequences within a family are lined up and the shared head and tail "
              "counted. Experiments like state tomography, where only the measurement basis "
              "changes, are identified here rather than mistaken for repetition.",
        "ko": "같은 계열 회로들의 게이트 열을 맞대어 앞뒤 공통 구간을 셉니다. 측정 기저만 "
              "바뀌는 상태 단층촬영 같은 실험이 반복으로 오인되지 않고 여기서 구분됩니다.",
        "ja": "同一系統の回路のゲート列を突き合わせ、先頭と末尾の共通部分を数えます。測定基底"
              "だけが変わる状態トモグラフィのような実験は、反復と誤認されずここで識別されます。",
        "es": "Se alinean las secuencias de puertas de una familia y se cuenta la cabeza y la "
              "cola compartidas. Experimentos como la tomografía de estado, donde solo cambia "
              "la base de medida, se identifican aquí en lugar de confundirse con repetición.",
    },
    "fam_th_compared": {
        "en": "Compared", "ko": "비교한 회로", "ja": "比較回路数", "es": "Comparados",
    },
    "fam_th_total_ops": {
        "en": "Total ops", "ko": "총 연산", "ja": "総命令数", "es": "Ops totales",
    },
    "fam_th_head": {
        "en": "Shared head", "ko": "앞 공통", "ja": "先頭共通", "es": "Cabeza común",
    },
    "fam_th_tail": {
        "en": "Shared tail", "ko": "뒤 공통", "ja": "末尾共通", "es": "Cola común",
    },
    "fam_th_diff": {
        "en": "Differing", "ko": "상이 구간", "ja": "相違部分", "es": "Diferentes",
    },
    "fam_th_names": {
        "en": "Example names", "ko": "회로명 예시", "ja": "回路名の例", "es": "Nombres de ejemplo",
    },
    "fam_v_identical": {
        "en": "identical circuit", "ko": "완전히 같은 회로",
        "ja": "完全に同一の回路", "es": "circuito idéntico",
    },
    "fam_v_near": {
        "en": "nearly identical (measurement basis or similar)",
        "ko": "거의 같음 (측정 기저 등 일부만 상이)",
        "ja": "ほぼ同一（測定基底など一部のみ相違）",
        "es": "casi idéntico (base de medida o similar)",
    },
    "fam_v_different": {
        "en": "genuinely different circuits", "ko": "서로 다른 회로",
        "ja": "実際に異なる回路", "es": "circuitos realmente distintos",
    },
    "fam_v_na": {
        "en": "not comparable", "ko": "판별 불가", "ja": "判定不可", "es": "no comparable",
    },
    # -- score breakdown ---------------------------------------------------
    "score_summary": {
        "en": "Score breakdown", "ko": "점수 구성", "ja": "スコア内訳", "es": "Desglose de puntuación",
    },
    "score_th_component": {
        "en": "Component", "ko": "항목", "ja": "項目", "es": "Componente",
    },
    # -- footer ------------------------------------------------------------
    "footer": {
        "en": "Verdicts: <b>flagged</b> = identical circuit, shots and backend repeated at "
              "short intervals. <b>normal</b> = a converging optimizer loop, or a benchmark "
              "spread over time and backends. <b>unexplained</b> = repetition that fits neither "
              "— a human needs to look.<br>These are automated heuristics and false positives "
              "are possible. Read the evidence, the circuit contents and the submission "
              "timeline before acting on anything.",
        "ko": "판정 기준: <b>남용 의심</b> = 동일 회로·shots·backend 를 짧은 간격으로 반복. "
              "<b>정상</b> = 수렴하는 최적화 루프이거나 기간·backend 에 분산된 벤치마크. "
              "<b>설명 안 됨</b> = 둘 중 어디에도 맞지 않는 반복 — 사람이 봐야 합니다.<br>"
              "자동 휴리스틱이므로 오탐이 있을 수 있습니다. 조치 전에 근거와 회로 내용, "
              "제출 타임라인을 직접 확인하세요.",
        "ja": "判定基準: <b>要確認</b>＝同一の回路・ショット・バックエンドを短い間隔で反復。"
              "<b>正常</b>＝収束する最適化ループ、または期間とバックエンドに分散したベンチマーク。"
              "<b>説明なし</b>＝どちらにも当てはまらない反復 — 人が確認する必要があります。<br>"
              "自動ヒューリスティクスであり誤検出の可能性があります。対応の前に根拠・回路内容・"
              "投入タイムラインを必ず確認してください。",
        "es": "Veredictos: <b>señalado</b> = circuito, shots y backend idénticos repetidos a "
              "intervalos cortos. <b>normal</b> = un bucle de optimización convergente, o un "
              "benchmark repartido en el tiempo y entre backends. <b>sin explicar</b> = "
              "repetición que no encaja en ninguno — hace falta que lo mire una persona.<br>"
              "Son heurísticas automáticas y puede haber falsos positivos. Lee las pruebas, el "
              "contenido del circuito y la cronología de envíos antes de actuar.",
    },
    "note_unmapped": {
        "en": "{n} user IDs have no name mapping. Run "
              "<code>python -m qpu_audit users --sync</code> to resolve them automatically, "
              "or see docs/user-mapping.md.",
        "ko": "실명 매핑이 없는 user_id 가 {n}명 있습니다. "
              "<code>python -m qpu_audit users --sync</code> 로 자동 조회하거나 "
              "docs/user-mapping.md 를 참고하세요.",
        "ja": "名前が未対応の user_id が {n} 件あります。"
              "<code>python -m qpu_audit users --sync</code> で自動解決するか、"
              "docs/user-mapping.md を参照してください。",
        "es": "{n} IDs de usuario no tienen nombre asignado. Ejecuta "
              "<code>python -m qpu_audit users --sync</code> para resolverlos automáticamente, "
              "o consulta docs/user-mapping.md.",
    },
}


# Sentences containing numbers. Formatted per language, server-side, where the values
# are known. Parameters are pre-escaped by the caller.
MESSAGES: dict[str, dict[str, str]] = {
    # -- findings ----------------------------------------------------------
    "f_waste": {
        "en": "{amount} of QPU spent on unexplained re-execution ({pct}% of this user's total)",
        "ko": "설명되지 않는 재실행에 QPU {amount} 소모 (이 사용자 총 사용량의 {pct}%)",
        "ja": "説明のつかない再実行に QPU を {amount} 消費（この利用者の総使用量の {pct}%）",
        "es": "{amount} de QPU en re-ejecución sin explicar ({pct}% del total de este usuario)",
    },
    "f_top_circuit": {
        "en": "a single flagged circuit accounts for {pct}% of this user's QPU time",
        "ko": "지목된 단일 회로가 이 사용자 QPU 시간의 {pct}%를 차지",
        "ja": "検出された単一の回路がこの利用者の QPU 時間の {pct}% を占める",
        "es": "un solo circuito señalado supone el {pct}% del tiempo de QPU de este usuario",
    },
    "f_unique": {
        "en": "unique circuit ratio {pct}% ({distinct} distinct / {runs} runs)",
        "ko": "고유 회로 비율 {pct}% ({distinct}종 / {runs}회 실행)",
        "ja": "固有回路率 {pct}%（{distinct} 種 / {runs} 回実行）",
        "es": "ratio de circuitos únicos {pct}% ({distinct} distintos / {runs} ejecuciones)",
    },
    "f_unique_rt": {
        "en": "unique circuit ratio {pct}% ({distinct} distinct / {runs} runs, "
              "{payloads} payloads re-transpiled each time)",
        "ko": "고유 회로 비율 {pct}% ({distinct}종 / {runs}회 실행, "
              "페이로드 {payloads}종 — 매번 재트랜스파일)",
        "ja": "固有回路率 {pct}%（{distinct} 種 / {runs} 回実行、ペイロード {payloads} 種 — "
              "毎回再トランスパイル）",
        "es": "ratio de circuitos únicos {pct}% ({distinct} distintos / {runs} ejecuciones, "
              "{payloads} cargas re-transpiladas cada vez)",
    },
    "f_mechanical": {
        "en": "submission intervals are mechanically regular (CV {cv}) — script or bot pattern",
        "ko": "제출 간격이 기계적으로 일정함 (변동계수 {cv}) — 스크립트/봇 패턴",
        "ja": "投入間隔が機械的に一定（変動係数 {cv}） — スクリプト／ボットのパターン",
        "es": "los intervalos de envío son mecánicamente regulares (CV {cv}) — patrón de "
              "script o bot",
    },
    "f_trivial": {
        "en": "repeated execution of trivial circuits (no entanglement or no measurement): "
              "{amount} of QPU",
        "ko": "자명한 회로(얽힘 없음 또는 측정 없음) 반복 실행: QPU {amount}",
        "ja": "自明な回路（もつれなし、または測定なし）の反復実行: QPU {amount}",
        "es": "ejecución repetida de circuitos triviales (sin entrelazamiento o sin medición): "
              "{amount} de QPU",
    },
    "f_failure": {
        "en": "a failed payload was resubmitted {n} times — possibly an unattended script",
        "ko": "실패한 payload 를 {n}회 재제출 — 방치된 스크립트 가능성",
        "ja": "失敗したペイロードを {n} 回再投入 — 放置されたスクリプトの可能性",
        "es": "una carga fallida se reenvió {n} veces — posible script desatendido",
    },
    "f_no_session": {
        "en": "{n} repeated runs submitted individually without session/batch — the queue is "
              "re-entered each time",
        "ko": "반복 실행 {n}건을 session/batch 없이 개별 제출 — 매번 큐를 새로 잡음",
        "ja": "反復実行 {n} 件を session/batch なしで個別投入 — 毎回キューに入り直している",
        "es": "{n} ejecuciones repetidas enviadas individualmente sin session/batch — se vuelve "
              "a entrar en la cola cada vez",
    },
    "f_private": {
        "en": "{n} private jobs expose no circuit and are excluded from judgement",
        "ko": "private job {n}건은 회로를 볼 수 없어 판정에서 제외",
        "ja": "private ジョブ {n} 件は回路が見えないため判定から除外",
        "es": "{n} trabajos privados no exponen circuito y quedan fuera del juicio",
    },
    "f_coverage": {
        "en": "only {pct}% of circuits were retrieved — low confidence, run collect again",
        "ko": "회로 확보율 {pct}% — 판정 신뢰도가 낮습니다, collect 를 더 돌리세요",
        "ja": "回路取得率 {pct}% — 判定の信頼度が低いため collect を再実行してください",
        "es": "solo se obtuvo el {pct}% de los circuitos — poca confianza, ejecuta collect de nuevo",
    },
    # -- signal details ----------------------------------------------------
    "d_duplicate_waste": {
        "en": "{amount} of QPU on unexplained re-execution ({pct}% of this user's usage)",
        "ko": "설명되지 않는 재실행에 QPU {amount} (이 사용자 사용량의 {pct}%)",
        "ja": "説明のつかない再実行に QPU {amount}（この利用者の使用量の {pct}%）",
        "es": "{amount} de QPU en re-ejecución sin explicar ({pct}% del uso de este usuario)",
    },
    "d_top_circuit_share": {
        "en": "a single circuit accounts for {pct}% of this user's QPU time",
        "ko": "단일 회로가 이 사용자 QPU 시간의 {pct}%를 차지",
        "ja": "単一の回路がこの利用者の QPU 時間の {pct}% を占める",
        "es": "un solo circuito supone el {pct}% del tiempo de QPU de este usuario",
    },
    "d_trivial_circuit": {
        "en": "{amount} of QPU on non-entangling circuits",
        "ko": "얽힘 없는 회로에 QPU {amount}",
        "ja": "もつれのない回路に QPU {amount}",
        "es": "{amount} de QPU en circuitos sin entrelazamiento",
    },
    "d_failure_resubmit": {
        "en": "a failed payload was resubmitted {n} times",
        "ko": "실패한 payload 를 {n}회 재제출",
        "ja": "失敗したペイロードを {n} 回再投入",
        "es": "una carga fallida se reenvió {n} veces",
    },
    "d_no_session": {
        "en": "{n} repeated runs submitted individually, without session or batch",
        "ko": "반복 실행 {n}건을 session/batch 없이 개별 제출",
        "ja": "反復実行 {n} 件を session/batch なしで個別投入",
        "es": "{n} ejecuciones repetidas enviadas individualmente, sin session ni batch",
    },
    "d_regular_interval": {
        "en": "submission gap coefficient of variation {cv} — script/bot pattern",
        "ko": "제출 간격 변동계수 {cv} — 스크립트/봇 패턴",
        "ja": "投入間隔の変動係数 {cv} — スクリプト／ボットのパターン",
        "es": "coeficiente de variación de los intervalos {cv} — patrón de script/bot",
    },
    "d_overuse_global": {
        "en": "{pct}% of QPU time across all instances ({amount} over {jobs} jobs)",
        "ko": "전체 인스턴스 QPU 시간의 {pct}% (job {jobs}건, {amount})",
        "ja": "全インスタンスの QPU 時間の {pct}%（ジョブ {jobs} 件、{amount}）",
        "es": "{pct}% del tiempo de QPU en todas las instancias ({amount} en {jobs} trabajos)",
    },
    "d_overuse_instance": {
        "en": "{pct}% of QPU time on '{instance}' ({global_pct}% across all instances, "
              "{amount} over {jobs} jobs)",
        "ko": "'{instance}' 인스턴스 QPU 시간의 {pct}% (전체 인스턴스 기준 {global_pct}%, "
              "job {jobs}건, {amount})",
        "ja": "'{instance}' の QPU 時間の {pct}%（全インスタンス基準 {global_pct}%、"
              "ジョブ {jobs} 件、{amount}）",
        "es": "{pct}% del tiempo de QPU en '{instance}' ({global_pct}% en todas las instancias, "
              "{amount} en {jobs} trabajos)",
    },
    "d_usage_spike": {
        "en": "usage {ratio}x versus the previous month",
        "ko": "직전 달 대비 사용량 {ratio}배",
        "ja": "前月比で使用量 {ratio} 倍",
        "es": "uso {ratio}x respecto al mes anterior",
    },
    "d_usage_spike_new": {
        "en": "new this month versus the previous month",
        "ko": "직전 달 대비 이번 달 신규",
        "ja": "前月比で今月から新規",
        "es": "nuevo este mes respecto al mes anterior",
    },
    "d_burst": {
        "en": "up to {n} jobs submitted within 60 seconds — the queue is taken in one go",
        "ko": "60초 안에 최대 {n}건 연속 제출 — 큐를 한 번에 점유",
        "ja": "60 秒以内に最大 {n} 件を連続投入 — キューを一度に占有",
        "es": "hasta {n} trabajos enviados en 60 segundos — la cola se toma de una vez",
    },
    # -- group reasons -----------------------------------------------------
    "r_converging": {
        "en": "parameters converging across the group — optimizer loop",
        "ko": "그룹 전체에서 파라미터가 수렴 중 — 최적화 루프",
        "ja": "グループ全体でパラメータが収束 — 最適化ループ",
        "es": "parámetros convergiendo en el grupo — bucle de optimización",
    },
    "r_flagged": {
        "en": "{label} repeated {runs} times with identical shots and backend, median gap "
              "{gap} min (span {span} h)",
        "ko": "{label}를 동일 shots·backend 로 {runs}회 반복, 중앙값 간격 {gap}분 "
              "(기간 {span}시간)",
        "ja": "{label} を同一のショット・バックエンドで {runs} 回反復、間隔の中央値 {gap} 分"
              "（期間 {span} 時間）",
        "es": "{label} repetido {runs} veces con shots y backend idénticos, intervalo mediano "
              "{gap} min (lapso {span} h)",
    },
    "r_gray_backends": {
        "en": "{label} repeated {runs} times at a median gap of {gap} min but across "
              "{n} backends — possibly a cross-backend comparison",
        "ko": "{label}를 중앙값 {gap}분 간격으로 {runs}회 반복했으나 backend {n}개에 분산 — "
              "교차 비교 가능성",
        "ja": "{label} を中央値 {gap} 分間隔で {runs} 回反復したが {n} 個のバックエンドに分散 — "
              "バックエンド間比較の可能性",
        "es": "{label} repetido {runs} veces con intervalo mediano de {gap} min pero en "
              "{n} backends — posible comparación entre backends",
    },
    "r_identical": {
        "en": "payload byte-identical — nothing was changed between runs",
        "ko": "페이로드가 바이트 단위로 동일 — 실행 사이에 아무것도 바뀌지 않음",
        "ja": "ペイロードがバイト単位で同一 — 実行間で何も変更されていない",
        "es": "carga idéntica byte a byte — nada cambió entre ejecuciones",
    },
    "r_retranspiled": {
        "en": "re-transpiled every run ({n} distinct payloads) but the experiment identity is "
              "unchanged — no reason for a different result",
        "ko": "매 실행마다 재트랜스파일됨 (고유 페이로드 {n}개) 이지만 실험 정체는 동일 — "
              "결과가 달라질 이유가 없음",
        "ja": "毎回再トランスパイルされている（固有ペイロード {n} 個）が実験の同一性は不変 — "
              "結果が変わる理由がない",
        "es": "re-transpilado en cada ejecución ({n} cargas distintas) pero la identidad del "
              "experimento no cambia — no hay motivo para un resultado distinto",
    },
    "r_nosession": {
        "en": "no session/batch, so the queue is re-entered every time",
        "ko": "session/batch 미사용이라 매번 큐를 새로 잡음",
        "ja": "session/batch 未使用のため毎回キューに入り直している",
        "es": "sin session/batch, así que se vuelve a entrar en la cola cada vez",
    },
    "r_trivial": {
        "en": "circuit itself is trivial: {reason}",
        "ko": "회로 자체가 자명함: {reason}",
        "ja": "回路自体が自明: {reason}",
        "es": "el circuito en sí es trivial: {reason}",
    },
    "r_clifford": {
        "en": "note: Clifford-only circuit (classically simulable, but also normal for "
              "randomized benchmarking or calibration)",
        "ko": "참고: Clifford 전용 회로 (고전 시뮬 가능하나 랜덤 벤치마킹·캘리브레이션에서는 정상)",
        "ja": "参考: Clifford のみの回路（古典シミュレーション可能だが、ランダム化ベンチマークや"
              "校正では正常）",
        "es": "nota: circuito solo Clifford (simulable clásicamente, pero también normal en "
              "benchmarking aleatorizado o calibración)",
    },
    "r_benign_spread": {
        "en": "widely spaced and spread over time or backends — drift / benchmark pattern",
        "ko": "간격이 넓고 기간·backend 에 분산 — 드리프트/벤치마크 패턴",
        "ja": "間隔が広く期間やバックエンドに分散 — ドリフト／ベンチマークのパターン",
        "es": "muy espaciado y repartido en el tiempo o entre backends — patrón de deriva / "
              "benchmark",
    },
    "r_gray_repeat": {
        "en": "same circuit repeated {runs} times{detail}",
        "ko": "동일 회로 {runs}회 반복{detail}",
        "ja": "同一回路を {runs} 回反復{detail}",
        "es": "mismo circuito repetido {runs} veces{detail}",
    },
    "r_detail_gap": {
        "en": "median gap {gap} min", "ko": "중앙값 간격 {gap}분",
        "ja": "間隔の中央値 {gap} 分", "es": "intervalo mediano {gap} min",
    },
    "r_detail_shots": {
        "en": "shots varied", "ko": "shots 가 변함",
        "ja": "ショット数が変動", "es": "shots variaron",
    },
    "trivial_no_2q": {
        "en": "no two-qubit gates (nothing entangled)",
        "ko": "2큐빗 게이트 없음 (얽힘 없음)",
        "ja": "2 量子ビットゲートなし（もつれなし）",
        "es": "sin puertas de dos cúbits (nada entrelazado)",
    },
    "trivial_no_measure": {
        "en": "no measurement gates", "ko": "측정 게이트 없음",
        "ja": "測定ゲートなし", "es": "sin puertas de medición",
    },
    # -- analysis notes ----------------------------------------------------
    "n_denied": {
        "en": "{n} job details were refused for lack of permission and are excluded from "
              "circuit analysis.",
        "ko": "job 상세 {n}건이 권한 부족으로 거부되어 회로 분석에서 제외됐습니다.",
        "ja": "ジョブ詳細 {n} 件が権限不足で拒否され、回路解析から除外されています。",
        "es": "{n} detalles de trabajo fueron rechazados por falta de permisos y se excluyen "
              "del análisis de circuitos.",
    },
    "n_missing": {
        "en": "{n} jobs could not be retrieved, possibly past their retention window.",
        "ko": "job {n}건을 조회하지 못했습니다 — 보관 기간이 지났을 수 있습니다.",
        "ja": "ジョブ {n} 件を取得できませんでした。保持期間を過ぎている可能性があります。",
        "es": "{n} trabajos no pudieron recuperarse, posiblemente fuera de su ventana de "
              "retención.",
    },
    "n_session_unknown": {
        "en": "{n} user(s) created session/batch containers, but job-level session_id is empty "
              "so membership is unknown. Session judgement is suspended for those users only; "
              "for everyone else 'no session' is certain because they created no containers.",
        "ko": "session/batch 컨테이너를 만든 사용자가 {n}명 있으나 job 의 session_id 가 비어 있어 "
              "소속을 알 수 없습니다. 해당 사용자에 한해 session 판정을 보류했고, 나머지는 "
              "컨테이너가 없으므로 'session 미사용'이 확정입니다.",
        "ja": "session/batch コンテナを作成した利用者が {n} 名いますが、ジョブの session_id が空"
              "のため所属が不明です。該当利用者のみ session 判定を保留し、他は コンテナが無いため"
              "「session 未使用」が確定です。",
        "es": "{n} usuario(s) crearon contenedores session/batch, pero session_id a nivel de "
              "trabajo está vacío, así que se desconoce la pertenencia. El juicio sobre session "
              "queda suspendido solo para ellos; para el resto, 'sin session' es seguro porque "
              "no crearon contenedores.",
    },
    "n_synthetic": {
        "en": "This report was generated by selftest from synthetic data. It does not reflect "
              "any real instance.",
        "ko": "이 리포트는 selftest 가 합성 데이터로 만든 것입니다. 실제 인스턴스가 아닙니다.",
        "ja": "このレポートは selftest が合成データから生成したものです。実在のインスタンスでは"
              "ありません。",
        "es": "Este informe fue generado por selftest a partir de datos sintéticos. No refleja "
              "ninguna instancia real.",
    },
}


class Msg:
    """A translatable sentence plus the values to substitute into it.

    Kept as data rather than a formatted string so the same finding can be rendered
    in every language from one analysis pass.
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params

    def text(self, lang: str = DEFAULT_LANG) -> str:
        return message(self.key, lang, **self.params)

    def __str__(self) -> str:
        return self.text()

    def __repr__(self) -> str:
        return f"Msg({self.key!r}, {self.params!r})"


def _lookup(table: dict[str, dict[str, str]], key: str, lang: str) -> str:
    entry = table.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


def ui(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    """A static UI string. May contain simple inline HTML."""
    text = _lookup(STRINGS, key, lang)
    return text.format(**params) if params else text


def message(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    """A sentence with values substituted in.

    A parameter may itself be a ``Msg``; it is resolved in the same language, so
    nested phrases such as "circuit itself is trivial: no two-qubit gates" translate
    as a whole.
    """
    text = _lookup(MESSAGES, key, lang)
    resolved = {
        name: (value.text(lang) if isinstance(value, Msg) else value)
        for name, value in params.items()
    }
    try:
        return text.format(**resolved) if resolved else text
    except (KeyError, IndexError):
        # A translation missing a placeholder must not break the report.
        return _lookup(MESSAGES, key, DEFAULT_LANG).format(**resolved)


def missing_keys(lang: str) -> list[str]:
    """Keys a language has not translated yet. Used by tests and contributors."""
    out = [k for k, v in STRINGS.items() if lang not in v]
    out += [k for k, v in MESSAGES.items() if lang not in v]
    return sorted(out)

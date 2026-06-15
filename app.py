"""
BANKING DATA MIGRATION SYSTEM
Enterprise Streamlit UI. No emojis. Clean information hierarchy.
"""

import json
import os
import queue
import threading
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from config.schema_mapping import get_default_mapping, validate_mapping
from db_config import get_source_connection, get_target_connection

# -- Page config ---------------------------------------------------------------
st.set_page_config(
    page_title="Core Banking Migration",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -- CSS -----------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* -- Sidebar -- */
section[data-testid="stSidebar"] {
    background: #111827;
    border-right: 1px solid #1f2937;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #f9fafb !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.4rem;
}
section[data-testid="stSidebar"] label {
    color: #9ca3af !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
section[data-testid="stSidebar"] input {
    background: #1f2937 !important;
    border: 1px solid #374151 !important;
    color: #f3f4f6 !important;
    border-radius: 2px !important;
    font-size: 0.83rem !important;
}
section[data-testid="stSidebar"] p {
    color: #d1d5db !important;
    font-size: 0.8rem !important;
}

/* -- Main content -- */
.stApp {
    background: #f8fafc;
}

/* -- Page title -- */
.page-title {
    font-size: 1.45rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.01em;
    margin-bottom: 0;
}
.page-subtitle {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.15rem;
    font-family: 'JetBrains Mono', monospace;
}

/* -- Status pill -- */
.pill {
    display: inline-block;
    padding: 0.22rem 0.75rem;
    border-radius: 2px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.pill-idle     { background:#e2e8f0; color:#475569; border:1px solid #cbd5e1; }
.pill-running  { background:#fef3c7; color:#92400e; border:1px solid #f59e0b; }
.pill-complete { background:#dcfce7; color:#166534; border:1px solid #22c55e; }
.pill-failed   { background:#fee2e2; color:#991b1b; border:1px solid #ef4444; }

/* -- Metric cards -- */
div[data-testid="metric-container"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-top: 3px solid #2563eb;
    padding: 1rem 1.1rem 0.9rem;
    border-radius: 2px;
}
div[data-testid="metric-container"] label {
    font-size: 0.68rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b !important;
    font-weight: 600 !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

/* -- Section label -- */
.section-label {
    font-size: 0.67rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin-bottom: 0.6rem;
    margin-top: 1.4rem;
}

/* -- Log terminal -- */
.log-terminal {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 2px;
    padding: 0.9rem 1rem;
    height: 360px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    line-height: 1.7;
}
.log-terminal .lg  { color: #8b949e; }
.log-terminal .ls  { color: #3fb950; }
.log-terminal .lw  { color: #d29922; }
.log-terminal .le  { color: #f85149; }
.log-terminal .lh  { color: #79c0ff; font-weight: 600; }

/* -- Result table -- */
.stDataFrame {
    border: 1px solid #e2e8f0 !important;
    border-radius: 2px !important;
}

/* -- Expander -- */
details > summary {
    font-weight: 600 !important;
    font-size: 0.83rem !important;
    color: #1e293b !important;
}

/* -- Buttons -- */
.stButton > button[kind="primary"] {
    background: #2563eb;
    color: #fff;
    border: none;
    border-radius: 2px;
    font-weight: 600;
    font-size: 0.82rem;
    letter-spacing: 0.02em;
    padding: 0.5rem 1.1rem;
    width: 100%;
}
.stButton > button[kind="primary"]:hover { background: #1d4ed8; }
.stButton > button:not([kind="primary"]) {
    background: #1f2937;
    color: #d1d5db;
    border: 1px solid #374151;
    border-radius: 2px;
    font-size: 0.8rem;
    width: 100%;
}
.stButton > button:not([kind="primary"]):hover { background: #374151; }

/* -- Divider -- */
hr { border-top: 1px solid #e2e8f0; margin: 1rem 0; }

/* -- Progress bar -- */
div[data-testid="stProgressBar"] > div > div {
    background: #2563eb !important;
    border-radius: 1px !important;
}
</style>
""", unsafe_allow_html=True)

# -- Session state init --------------------------------------------------------
_DEFAULTS = {
    "logs": [],
    "running": False,
    "status": "idle",
    "progress": 0,
    "results": None,
    "current_step": "Idle",
    "event_queue": None,
    "_mapping_json": json.dumps(get_default_mapping()),
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# -- Mapping helpers -----------------------------------------------------------


def _get_mapping() -> dict:
    return json.loads(st.session_state._mapping_json)


def _set_mapping(m: dict):
    st.session_state._mapping_json = json.dumps(m)


# -- Sidebar -------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Configuration")

    st.markdown("### Source Database")
    src_host = st.text_input("Host", "localhost", key="src_host")
    src_port = st.text_input("Port", "5432", key="src_port")
    src_db = st.text_input("Database", "legacy_bank_db", key="src_db")
    src_user = st.text_input("User", "postgres", key="src_user")
    src_pass = st.text_input("Password", type="password", key="src_pass")

    st.markdown("---")
    st.markdown("### Target Database")
    tgt_host = st.text_input("Host", "localhost", key="tgt_host")
    tgt_port = st.text_input("Port", "5432", key="tgt_port")
    tgt_db = st.text_input("Database", "target_bank_db", key="tgt_db")
    tgt_user = st.text_input("User", "postgres", key="tgt_user")
    tgt_pass = st.text_input("Password", type="password", key="tgt_pass")

    st.markdown("---")
    st.markdown("### Schema Mapping")

    uploaded = st.file_uploader(
        "Upload schema_mapping.json", type="json", key="schema_up")
    if uploaded:
        try:
            loaded_map = json.load(uploaded)
            validate_mapping(loaded_map)
            _set_mapping(loaded_map)
            st.success("Schema loaded")
        except Exception as _e:
            st.error(f"Schema error: {_e}")

    default_map = get_default_mapping()
    st.download_button(
        "Download schema template",
        data=json.dumps(default_map, indent=2),
        file_name="schema_mapping_template.json",
        mime="application/json",
    )

    st.markdown("---")
    st.markdown("### Performance")
    batch_size = st.number_input(
        "Batch size (rows)",
        min_value=1_000, max_value=200_000,
        value=50_000, step=10_000,
        key="batch_sz",
    )
    run_dq = st.checkbox("Pre-migration data quality scan",
                         value=True, key="dq")
    auto_fix = st.checkbox("Auto-repair detected issues",
                           value=True, key="ar")

    st.markdown("---")
    col_s, col_r = st.columns(2)
    with col_s:
        start_btn = st.button("Run Migration", type="primary", key="start")
    with col_r:
        reset_btn = st.button("Reset", key="reset")

    if reset_btn:
        for _k in list(st.session_state.keys()):
            del st.session_state[_k]
        st.rerun()

# -- Header --------------------------------------------------------------------
left_h, right_h = st.columns([5, 1])
with left_h:
    st.markdown('<p class="page-title">Core Banking Data Migration</p>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="page-subtitle">Multi-Agent ETL Pipeline &nbsp;|&nbsp; '
        'LangChain &nbsp;+&nbsp; CrewAI &nbsp;+&nbsp; LangGraph &nbsp;|&nbsp; '
        'Data Quality Agent &nbsp;|&nbsp; PostgreSQL</p>',
        unsafe_allow_html=True,
    )
with right_h:
    _pill = {
        "idle": "pill-idle",
        "running": "pill-running",
        "complete": "pill-complete",
        "failed": "pill-failed",
    }.get(st.session_state.status, "pill-idle")
    st.markdown(
        f'<div style="text-align:right;padding-top:0.6rem">'
        f'<span class="pill {_pill}">{st.session_state.status.upper()}</span></div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# -- Metrics -------------------------------------------------------------------
res = st.session_state.results or {}
_ext = sum(res.get("extracted", {}).values()) if res else 0
_ld = sum(res.get("loaded", {}).values()) if res else 0
_anom = len([k for k in res.get("anomalies", {})
             if k != "ai_risk_narrative"]) if res else 0
_tbl = len(_get_mapping().get("tables", {}))
_rate = f"{int(_ld / _ext * 100)}%" if _ext else "—"

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.metric("Tables", str(_tbl))
with c2:
    st.metric("Batch Size", f"{batch_size:,}")
with c3:
    st.metric("Extracted", f"{_ext:,}" if _ext else "—")
with c4:
    st.metric("Loaded", f"{_ld:,}" if _ld else "—")
with c5:
    st.metric("Load Rate", _rate)
with c6:
    st.metric("Anomaly Types", str(_anom) if res else "—")

st.markdown('<p class="section-label">Migration Progress</p>',
            unsafe_allow_html=True)
progress_bar = st.progress(st.session_state.progress)
st.markdown(
    f'<p style="font-size:0.75rem;color:#64748b;margin-top:0.2rem">'
    f'Current step: <strong>{st.session_state.current_step}</strong></p>',
    unsafe_allow_html=True,
)

# -- Log terminal --------------------------------------------------------------
st.markdown('<p class="section-label">Event Log</p>', unsafe_allow_html=True)
log_slot = st.empty()


def _render_log():
    lines = st.session_state.logs[-150:]
    parts = []
    for ln in lines:
        u = ln.upper()
        if "ERROR" in u or "FAILED" in u or "FATAL" in u:
            cls = "le"
        elif "SUCCESS" in u or "COMPLETED" in u or "PASSED" in u or "LOADED" in u:
            cls = "ls"
        elif "WARNING" in u or "WARN" in u or "FILTERED" in u:
            cls = "lw"
        elif "===" in ln or any(x in u for x in (
                "AGENT", "CREWAI", "LANGGRAPH", "LANGCHAIN", "MIGRATION STARTED")):
            cls = "lh"
        else:
            cls = "lg"
        safe = ln.replace("&", "&amp;").replace(
            "<", "&lt;").replace(">", "&gt;")
        parts.append(f'<div class="{cls}">{safe}</div>')
    log_slot.markdown(
        f'<div class="log-terminal">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


_render_log()


# -- Log helper (main thread only) --------------------------------------------
def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{ts}]  {msg}")
    u = msg.upper()
    if "EXTRACTING" in u:
        st.session_state.current_step = "Extracting"
    elif "TRANSFORMING" in u:
        st.session_state.current_step = "Transforming"
    elif "LOAD AGENT" in u or ("LOADING" in u and "%" in msg):
        st.session_state.current_step = "Loading"
    elif "VALIDAT" in u:
        st.session_state.current_step = "Validating"
    elif "ANOMALY" in u:
        st.session_state.current_step = "Anomaly Detection"
    elif "DATA QUALITY" in u:
        st.session_state.current_step = "Data Quality Scan"
    elif "REPAIR" in u:
        st.session_state.current_step = "Auto-Repair"
    elif "LANGCHAIN" in u:
        st.session_state.current_step = "LangChain Planning"
    elif "CREWAI" in u:
        st.session_state.current_step = "CrewAI Collaboration"
    elif "LANGGRAPH" in u:
        st.session_state.current_step = "LangGraph Workflow"
    elif "COMPLETED" in u:
        st.session_state.current_step = "Complete"
    elif "FAILED" in u:
        st.session_state.current_step = "Failed"


# -- Background migration thread -----------------------------------------------
# CRITICAL: the background thread has no Streamlit ScriptRunContext.
# It must NEVER read or write st.session_state.
# All communication back to the UI goes through the queue only.

def _run_migration(q: queue.Queue, env: dict, mapping_json: str, run_dq: bool):
    for k, v in env.items():
        os.environ[k] = v

    import io
    import sys as _sys

    # Redirect stdout so every print() in the agents arrives as a log event.
    class _Capture(io.TextIOBase):
        def write(self, s):
            s = s.rstrip()
            if s:
                q.put(("log", s))
            return len(s)

        def flush(self):
            pass

    old_stdout = _sys.stdout
    _sys.stdout = _Capture()

    # Queue-safe progress callback.
    # This closure only puts tuples onto the queue; it never touches session_state.
    def _progress_cb(step: str, table: str, current: int, total: int = None):
        if step == "extraction" and total:
            pct = min(int(current / total * 25), 25)
            q.put(
                ("log", f"Extracting {table}: {current:,} of {total:,}"))
            q.put(("progress", pct))
        elif step == "transformation":
            q.put(("log", f"Transforming {table}"))
            q.put(("progress", 30))
        elif step == "load" and total:
            pct_load = int(current / total * 100)
            q.put(
                ("log", f"Loading {table}: {pct_load}%  ({current:,} of {total:,})"))
            q.put(("progress", min(50 + int(current / total * 50), 100)))

    try:
        import json as _json
        from agents.data_mismatch_logger import reset_mismatch_logger
        from orchestrator import Orchestrator

        reset_mismatch_logger()
        mapping = _json.loads(mapping_json)
        mapping["batch_size"] = int(env.get("BATCH_SIZE", 50_000))

        orch = Orchestrator(
            schema_mapping=mapping,
            progress_callback=_progress_cb,
            estimated_rows=1_000_000,
            run_data_quality=run_dq,
        )
        success = orch.run()
        q.put(("results", orch.results))
        q.put(("done", "success" if success else "failed"))

    except Exception as exc:
        import traceback
        q.put(("log", f"FATAL ERROR: {exc}"))
        q.put(("log", traceback.format_exc()))
        q.put(("done", "failed"))
    finally:
        _sys.stdout = old_stdout


# -- Start migration -----------------------------------------------------------
if start_btn and not st.session_state.running:
    if not src_pass:
        st.error("Source database password is required.")
        st.stop()

    with st.spinner("Testing database connections..."):
        try:
            for k, v in {
                "SOURCE_DB_HOST": src_host, "SOURCE_DB_PORT": src_port,
                "SOURCE_DB_NAME": src_db, "SOURCE_DB_USER": src_user,
                "SOURCE_DB_PASS": src_pass,
                "TARGET_DB_HOST": tgt_host, "TARGET_DB_PORT": tgt_port,
                "TARGET_DB_NAME": tgt_db, "TARGET_DB_USER": tgt_user,
                "TARGET_DB_PASS": tgt_pass,
            }.items():
                os.environ[k] = v
            c = get_source_connection()
            c.close()
            c = get_target_connection()
            c.close()
        except Exception as exc:
            st.error(f"Connection failed: {exc}")
            st.stop()

    st.session_state.logs = []
    st.session_state.results = None
    st.session_state.progress = 0
    st.session_state.running = True
    st.session_state.status = "running"
    st.session_state.current_step = "Initialising"

    _m = _get_mapping()
    _m["batch_size"] = batch_size
    _set_mapping(_m)

    _log("=" * 60)
    _log("MIGRATION STARTED")
    _log(f"Source  : {src_db} @ {src_host}:{src_port}")
    _log(f"Target  : {tgt_db} @ {tgt_host}:{tgt_port}")
    _log(f"Batch   : {batch_size:,} rows")
    _log("=" * 60)

    env_dict = {
        "SOURCE_DB_HOST": src_host, "SOURCE_DB_PORT": src_port,
        "SOURCE_DB_NAME": src_db, "SOURCE_DB_USER": src_user,
        "SOURCE_DB_PASS": src_pass,
        "TARGET_DB_HOST": tgt_host, "TARGET_DB_PORT": tgt_port,
        "TARGET_DB_NAME": tgt_db, "TARGET_DB_USER": tgt_user,
        "TARGET_DB_PASS": tgt_pass,
        "BATCH_SIZE": str(batch_size),
    }

    q = queue.Queue()
    st.session_state.event_queue = q

    threading.Thread(
        target=_run_migration,
        args=(q, env_dict, st.session_state._mapping_json, run_dq),
        daemon=True,
    ).start()


# -- Drain event queue ---------------------------------------------------------
if st.session_state.running and st.session_state.event_queue:
    _q = st.session_state.event_queue
    _done = False

    while True:
        try:
            _kind, _payload = _q.get_nowait()
            if _kind == "log":
                _log(_payload)
            elif _kind == "progress":
                st.session_state.progress = _payload
            elif _kind == "results":
                st.session_state.results = _payload
            elif _kind == "done":
                st.session_state.running = False
                st.session_state.status = (
                    "complete" if _payload == "success" else "failed"
                )
                if _payload == "success":
                    st.session_state.progress = 100
                _done = True
        except queue.Empty:
            break

    progress_bar.progress(st.session_state.progress)
    _render_log()

    if not _done:
        time.sleep(0.35)
        st.rerun()
    else:
        st.rerun()


# -- Results section -----------------------------------------------------------
if st.session_state.results:
    res = st.session_state.results
    st.markdown("---")
    st.markdown('<p class="section-label">Results</p>', unsafe_allow_html=True)

    _ext2 = sum(res.get("extracted", {}).values())
    _ld2 = sum(res.get("loaded", {}).values())
    _skip2 = _ext2 - _ld2
    _rate2 = f"{int(_ld2 / _ext2 * 100)}%" if _ext2 else "—"
    _val = res.get("validation_passed", False)
    _anom2 = len([k for k in res.get("anomalies", {})
                  if k != "ai_risk_narrative"])

    from agents.data_mismatch_logger import get_mismatch_logger
    _mm = get_mismatch_logger().get_summary()

    sr1, sr2, sr3, sr4, sr5 = st.columns(5)
    with sr1:
        st.metric("Extracted", f"{_ext2:,}")
    with sr2:
        st.metric("Loaded", f"{_ld2:,}")
    with sr3:
        st.metric("Skipped", f"{_skip2:,}")
    with sr4:
        st.metric("Load Rate", _rate2)
    with sr5:
        st.metric("Validation", "Passed" if _val else "Failed")

    # Per-table breakdown
    st.markdown('<p class="section-label">Per-Table Breakdown</p>',
                unsafe_allow_html=True)
    _ext_d = res.get("extracted", {})
    _load_d = res.get("loaded", {})
    _rows = []
    for _t in _ext_d:
        _e = _ext_d.get(_t, 0)
        _l = _load_d.get(_t, 0)
        _s = _e - _l
        _r = f"{int(_l / _e * 100)}%" if _e else "—"
        _rows.append({
            "Table": _t.capitalize(),
            "Extracted": f"{_e:,}",
            "Loaded": f"{_l:,}",
            "Skipped": f"{_s:,}" if _s > 0 else "0",
            "Load Rate": _r,
        })
    st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True)

    # Data integrity
    st.markdown('<p class="section-label">Data Integrity</p>',
                unsafe_allow_html=True)
    di1, di2, di3, di4 = st.columns(4)
    with di1:
        st.metric("Orphaned Records", _mm["orphaned_records"])
    with di2:
        st.metric("FK Violations", _mm["foreign_key_violations"])
    with di3:
        st.metric("Null Value Issues", _mm["null_values"])
    with di4:
        st.metric("Schema Mismatches", _mm["schema_mismatches"])

    from agents.data_mismatch_logger import get_mismatch_logger as _gml
    _logger = _gml()
    _rp = _logger.save_report()
    if os.path.exists(_rp):
        with open(_rp) as _fh:
            st.download_button(
                "Download integrity report (JSON)",
                data=_fh.read(),
                file_name=os.path.basename(_rp),
                mime="application/json",
            )

    # Anomalies
    _anomalies = res.get("anomalies", {})
    if _anomalies:
        with st.expander("Anomaly Detection Report", expanded=True):
            for _key, _val in _anomalies.items():
                if _key == "ai_risk_narrative":
                    continue
                _items = _val if isinstance(_val, list) else [_val]
                st.markdown(f"**{_key.capitalize()}**")
                for _item in _items:
                    st.markdown(f"- {_item}")
            if "ai_risk_narrative" in _anomalies:
                st.markdown("---")
                st.markdown("**AI Risk Assessment**")
                st.info(_anomalies["ai_risk_narrative"])

    # AI agent decisions
    with st.expander("LangChain -- AI Agent Planning Decisions"):
        _lc = res.get("langchain_decisions", {})
        if _lc:
            st.caption(
                f"Timestamp: {_lc.get('timestamp', '—')}  |  "
                f"Tools used: {', '.join(_lc.get('tools_used', []))}"
            )
            st.code(_lc.get("agent_plan", ""), language="json")
        else:
            st.caption("No LangChain decisions recorded.")

    with st.expander("CrewAI -- Multi-Agent Collaboration", expanded=True):
        _cr = res.get("crewai_result")
        _ce = res.get("crewai_error")
        if _cr and str(_cr).strip():
            st.markdown("**Collaboration Output**")
            st.markdown("---")
            st.write(str(_cr))
            st.caption(f"Output length: {len(str(_cr))} characters")
        elif _ce:
            st.error(f"CrewAI error: {_ce}")
            st.caption(
                "Most common cause: GROQ_API_KEY not set in .env, "
                "or the cache_breakpoint fix in crew_collaboration.py was not applied."
            )
        else:
            st.caption("CrewAI result not available.")

    with st.expander("LangGraph -- Workflow State"):
        _lg = res.get("langgraph_state")
        if _lg:
            st.json(_lg)
        else:
            st.caption("LangGraph state not recorded.")

    with st.expander("Complete Migration Log (JSON)"):
        st.json(res)

# -- Footer --------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Banking Data Migration System  |  "
    "DataQualityAgent · LangChain · CrewAI · LangGraph  |  PostgreSQL"
)

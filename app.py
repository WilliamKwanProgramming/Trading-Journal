"""Local Streamlit cycle-analysis workbench.

Run with: streamlit run app.py
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from cycle_engine import (
    AnalysisError,
    AnalysisSettings,
    CSVValidationError,
    InsufficientHistoryError,
    load_tradingview_csv,
    run_cycle_analysis,
    run_locked_analysis,
)
from cycle_engine.composite import phase_description, projected_turns_table
from cycle_engine.backtest_plotting import backtest_equity_figure, cycle_selection_heatmap
from cycle_engine.exports import (
    composite_csv,
    figure_png,
    markdown_report,
    pine_ready_settings,
    selected_cycles_csv,
    settings_json,
)
from cycle_engine.plotting import composite_figure, spectrum_figure, validation_figure
from cycle_engine.rolling_backtest import (
    BacktestSettings,
    earliest_backtest_date,
    minimum_backtest_bars,
    run_rolling_backtest,
)
from cycle_engine.validation import walk_forward_validate
from cycle_engine.csv_store import CSVStore, StoredCSV


st.set_page_config(page_title="Trade Ledger · Cycle Analysis", page_icon="↗", layout="wide")
st.markdown(
    """
    <style>
    :root { color-scheme:light; --green:#1e694f; --lime:#c8ee78; --ink:#15211d; --muted:#53665c; --line:#dfe7df; --paper:#f6f8f3; --card:#ffffff; }
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background:var(--paper) !important; color:var(--ink) !important; color-scheme:light !important; }
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] { background:var(--card) !important; color:var(--ink) !important; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] * { color:var(--ink); }
    h1, h2, h3, h4, h5, h6, p, li, label, [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] { color:var(--ink) !important; }
    [data-testid="stCaptionContainer"], .small-muted { color:var(--muted) !important; }
    div[data-testid="stMetric"] { background:var(--card) !important; border:1px solid var(--line); border-radius:14px; padding:14px; }
    [data-testid="stMetricLabel"], [data-testid="stMetricDelta"] { color:var(--muted) !important; }
    [data-testid="stMetricValue"] { color:var(--ink) !important; }
    input, textarea, [data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-testid="stFileUploader"] section { background:#ffffff !important; color:var(--ink) !important; border-color:#b9c9bf !important; }
    input::placeholder, textarea::placeholder { color:#708178 !important; opacity:1 !important; }
    [data-baseweb="select"] *, [data-baseweb="input"] *, [role="listbox"] *, [role="option"] { color:var(--ink) !important; }
    [data-baseweb="popover"] { background:#ffffff !important; }
    button, [data-testid="stDownloadButton"] button { color:var(--ink) !important; background:#ffffff !important; border:1px solid #b9c9bf !important; }
    button[kind="primary"], [data-testid="stButton"] button[kind="primary"] { color:#ffffff !important; background:var(--green) !important; border-color:var(--green) !important; }
    [data-baseweb="tab"] { color:var(--muted) !important; }
    [data-baseweb="tab"][aria-selected="true"] { color:var(--green) !important; }
    [data-testid="stDataFrame"] { background:#ffffff !important; color:var(--ink) !important; }
    [data-testid="stAlert"] { color:var(--ink) !important; }
    .cycle-note { border-left:4px solid var(--lime); padding:12px 16px; background:#eef5e6; color:#30483b !important; border-radius:4px; }
    .cycle-note * { color:#30483b !important; }
    .small-muted { color:var(--muted); font-size:.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_load(raw: bytes, file_name: str, source: str):
    return load_tradingview_csv(raw, file_name=file_name, price_source=source)


@st.cache_data(show_spinner=False)
def cached_analysis(raw: bytes, file_name: str, settings_payload: str, as_of: str | None):
    settings = AnalysisSettings(**json.loads(settings_payload))
    frame, metadata = load_tradingview_csv(raw, file_name=file_name, price_source=settings.source)
    if as_of is None:
        return run_cycle_analysis(frame, metadata, settings)
    return run_locked_analysis(frame, metadata, settings, pd.Timestamp(as_of))


@st.cache_data(show_spinner=False)
def cached_validation(
    raw: bytes,
    file_name: str,
    settings_payload: str,
    tolerance: int,
    max_splits: int,
):
    settings = AnalysisSettings(**json.loads(settings_payload))
    frame, metadata = load_tradingview_csv(raw, file_name=file_name, price_source=settings.source)
    return walk_forward_validate(frame, metadata, settings, tolerance=tolerance, max_splits=max_splits)


@st.cache_data(show_spinner=False)
def cached_rolling_backtest(
    raw: bytes,
    file_name: str,
    settings_payload: str,
    backtest_payload: str,
    start_date: str,
):
    analysis_settings = AnalysisSettings(**json.loads(settings_payload))
    backtest_settings = BacktestSettings(**json.loads(backtest_payload))
    backtest_frame, backtest_metadata = load_tradingview_csv(
        raw, file_name=file_name, price_source=analysis_settings.source
    )
    return run_rolling_backtest(
        backtest_frame,
        backtest_metadata,
        analysis_settings,
        backtest_settings,
        pd.Timestamp(start_date),
    )


def settings_signature(settings: AnalysisSettings) -> str:
    return hashlib.sha256(json.dumps(asdict(settings), sort_keys=True).encode()).hexdigest()


def display_error(error: Exception) -> None:
    st.error(str(error))
    if isinstance(error, InsufficientHistoryError):
        st.info("Tip: the engine requires two observations of the longest requested cycle before it will scan.")


CSV_STORE = CSVStore()
ANALYSIS_SESSION_KEYS = (
    "live_result", "locked_result", "validation_result", "live_file_signature",
    "live_settings_signature", "locked_settings_signature",
    "rolling_backtest_result", "rolling_backtest_signature",
)


def clear_analysis_state() -> None:
    for key in ANALYSIS_SESSION_KEYS:
        st.session_state.pop(key, None)


def csv_label(csv: StoredCSV) -> str:
    size_kb = max(1, round(csv.size_bytes / 1024))
    return f"{csv.file_name} · {size_kb:,} KB"


st.title("Cycle Analysis Workbench")
st.markdown(
    '<div class="cycle-note"><strong>Independent analysis tab.</strong> This workbench only reads the uploaded TradingView CSV. '
    "It does not read the journal database, call Yahoo Finance, or alter any journal data.</div>",
    unsafe_allow_html=True,
)

DEFAULT_WIDGET_VALUES = {
    "source": "close",
    "min_period": 30.0,
    "max_period": 200.0,
    "detection_window": 750,
    "detrending_method": "EMA",
    "num_cycles": 3,
    "phase_window": 250,
    "min_fit": 0.10,
    "min_stability": 0.35,
    "min_separation": 10.0,
    "bartels_enabled": False,
    "bartels_threshold": 49.0,
    "forecast_horizon": 120,
    "detrend_length": 400,
    "spectrum_method": "Harmonic DFT (baseline)",
    "fractional_periods": False,
    "fractional_step": 0.5,
    "mode": "Live recalculation",
    "bt_initial_capital": 100_000.0,
    "bt_position_size_pct": 100.0,
    "bt_allow_shorting": True,
    "bt_commission": 0.0,
    "bt_slippage_pct": 0.0,
    "bt_leverage": 1.0,
    "bt_execution_timing": "Next bar open",
    "bt_signal_mode": "Bullish / bearish projected state",
    "bt_one_bar_confirmation": False,
    "bt_turn_tolerance": 3,
}
for _key, _value in DEFAULT_WIDGET_VALUES.items():
    st.session_state.setdefault(_key, _value)

with st.sidebar:
    st.header("Cycle scanner")
    uploader_key = f"csv_uploader_{st.session_state.get('csv_uploader_version', 0)}"
    uploaded = st.file_uploader(
        "Upload a TradingView CSV",
        type=["csv"],
        key=uploader_key,
        help="The uploaded file is saved locally and remains available after restarting the app.",
    )
    if uploaded is not None:
        uploaded_raw = uploaded.getvalue()
        upload_signature = hashlib.sha256(uploaded_raw + uploaded.name.encode("utf-8")).hexdigest()
        if st.session_state.get("last_upload_signature") != upload_signature:
            saved_csv = CSV_STORE.save(uploaded_raw, uploaded.name)
            st.session_state["last_upload_signature"] = upload_signature
            st.session_state["selected_csv_id"] = saved_csv.file_id
            clear_analysis_state()
            st.rerun()

    saved_csvs = CSV_STORE.list()
    saved_by_id = {csv.file_id: csv for csv in saved_csvs}
    if saved_csvs:
        if st.session_state.get("selected_csv_id") not in saved_by_id:
            st.session_state["selected_csv_id"] = saved_csvs[0].file_id
        selected_csv_id = st.selectbox(
            "Saved CSVs",
            options=[csv.file_id for csv in saved_csvs],
            format_func=lambda file_id: csv_label(saved_by_id[file_id]),
            key="selected_csv_id",
        )
        active_csv: StoredCSV | None = saved_by_id[selected_csv_id]
        st.caption(f"{len(saved_csvs)} saved CSV{'' if len(saved_csvs) == 1 else 's'} · stored in data/csvs")
    else:
        st.session_state.pop("selected_csv_id", None)
        active_csv = None
        st.caption("No saved CSVs yet. Upload one above to add it to your local library.")

    with st.expander("Manage saved CSVs", expanded=False):
        if not saved_csvs:
            st.caption("Your saved CSVs will appear here.")
        else:
            for saved_csv in saved_csvs:
                row = st.columns([3, 1])
                row[0].caption(csv_label(saved_csv))
                if row[1].button("Delete", key=f"request_delete_csv_{saved_csv.file_id}"):
                    st.session_state["confirm_delete_csv_id"] = saved_csv.file_id
                    st.rerun()
            confirm_delete_id = st.session_state.get("confirm_delete_csv_id")
            if confirm_delete_id in saved_by_id:
                st.warning(f"Delete **{saved_by_id[confirm_delete_id].file_name}** from the saved CSV library?")
                confirm_columns = st.columns(2)
                if confirm_columns[0].button("Delete permanently", key="confirm_delete_csv", type="primary"):
                    CSV_STORE.delete(confirm_delete_id)
                    clear_analysis_state()
                    st.session_state.pop("confirm_delete_csv_id", None)
                    st.session_state.pop("selected_csv_id", None)
                    st.session_state.pop("active_csv_id", None)
                    st.session_state.pop("last_upload_signature", None)
                    st.session_state["csv_uploader_version"] = st.session_state.get("csv_uploader_version", 0) + 1
                    st.rerun()
                if confirm_columns[1].button("Cancel", key="cancel_delete_csv"):
                    st.session_state.pop("confirm_delete_csv_id", None)
                    st.rerun()
    if st.button("Reset to default settings", use_container_width=True):
        for key, value in DEFAULT_WIDGET_VALUES.items():
            st.session_state[key] = value
        clear_analysis_state()
        st.rerun()
    source = st.selectbox("Price source", ["close", "open", "high", "low"], key="source")

if active_csv is not None:
    previous_active_id = st.session_state.get("active_csv_id")
    if previous_active_id != active_csv.file_id:
        clear_analysis_state()
        st.session_state["active_csv_id"] = active_csv.file_id

raw: bytes | None = None
active_file_name: str | None = None
if active_csv is not None:
    try:
        raw, active_file_name = CSV_STORE.read(active_csv.file_id)
    except FileNotFoundError:
        st.error("The selected saved CSV is no longer available. Choose another file or upload it again.")
frame = None
metadata = None
parse_error: Exception | None = None
if raw is not None and active_file_name is not None:
    try:
        frame, metadata = cached_load(raw, active_file_name, source)
    except (CSVValidationError, ValueError) as exc:
        parse_error = exc

with st.sidebar:
    if metadata is not None:
        st.caption(f"{metadata.bars:,} bars · {metadata.timeframe} · {metadata.start.date()} → {metadata.end.date()}")
    min_period = st.number_input("Minimum period (bars)", min_value=4.0, max_value=5000.0, step=1.0, key="min_period")
    max_period = st.number_input("Maximum period (bars)", min_value=5.0, max_value=10000.0, step=1.0, key="max_period")
    detection_window = st.number_input("Detection-window length", min_value=32, max_value=100000, step=10, key="detection_window")
    detrending_method = st.selectbox("Detrending method", ["EMA", "HP"], key="detrending_method")
    num_cycles = st.number_input("Number of composite cycles", min_value=1, max_value=10, step=1, key="num_cycles")
    phase_window = st.number_input("Phase-estimation window", min_value=16, max_value=100000, step=10, key="phase_window")
    min_fit = st.slider("Minimum fit / correlation", 0.0, 1.0, step=0.01, key="min_fit")
    min_stability = st.slider("Minimum stability", 0.0, 1.0, step=0.01, key="min_stability")
    min_separation = st.number_input("Minimum cycle separation (bars)", min_value=0.0, max_value=1000.0, step=1.0, key="min_separation")
    bartels_enabled = st.checkbox("Enable Bartels-style genuineness filter", help="Transparent phase/amplitude persistence approximation; not the proprietary FSC implementation.", key="bartels_enabled")
    bartels_threshold = st.slider("Bartels/genuineness threshold (%)", 0.0, 100.0, step=1.0, disabled=not bartels_enabled, key="bartels_threshold")
    forecast_horizon = st.number_input("Forecast horizon (bars)", min_value=1, max_value=5000, step=5, key="forecast_horizon")
    mode = st.radio("Forecast mode", ["Live recalculation", "Locked as-of date"], key="mode")
    locked_date = None
    if mode == "Locked as-of date" and metadata is not None:
        locked_date = st.date_input(
            "Locked as-of date",
            value=metadata.end.date(),
            min_value=metadata.start.date(),
            max_value=metadata.end.date(),
        )
    with st.expander("Method details"):
        detrend_length = st.number_input("Detrending length / HP cutoff", min_value=3, max_value=100000, step=10, key="detrend_length")
        spectrum_method = st.selectbox(
            "Spectrum method",
            ["Harmonic DFT (baseline)", "Goertzel DFT scan (alternative)"],
            key="spectrum_method",
        )
        fractional_periods = st.checkbox("Allow fractional periods", key="fractional_periods")
        fractional_step = st.number_input(
            "Fractional step (bars)", min_value=0.05, max_value=1.0, step=0.05,
            disabled=not fractional_periods,
            key="fractional_step",
        )
        st.caption("The Goertzel path and fractional grid are separate alternatives; the baseline is never changed silently.")
    run_requested = st.button("Run analysis", type="primary", use_container_width=True)

settings = AnalysisSettings(
    source=source,
    min_period=float(min_period),
    max_period=float(max_period),
    detection_window=int(detection_window),
    detrending_method=detrending_method,
    detrend_length=int(detrend_length),
    spectrum_method=spectrum_method,
    fractional_periods=bool(fractional_periods),
    fractional_step=float(fractional_step),
    num_cycles=int(num_cycles),
    phase_window=int(phase_window),
    min_fit=float(min_fit),
    min_stability=float(min_stability),
    min_separation=float(min_separation),
    bartels_enabled=bool(bartels_enabled),
    bartels_threshold=float(bartels_threshold),
    forecast_horizon=int(forecast_horizon),
)
settings_payload = json.dumps(settings.to_dict(), sort_keys=True)

result = None
if parse_error is not None:
    display_error(parse_error)
elif raw is not None and active_file_name is not None and metadata is not None:
    file_signature = hashlib.sha256(raw + active_file_name.encode("utf-8")).hexdigest()
    should_auto_run = mode == "Live recalculation" and st.session_state.get("live_file_signature") != file_signature
    if mode == "Live recalculation":
        if run_requested or should_auto_run:
            try:
                with st.spinner("Scanning candidate cycles…"):
                    result = cached_analysis(raw, active_file_name, settings_payload, None)
                st.session_state["live_result"] = result
                st.session_state["live_file_signature"] = file_signature
                st.session_state["live_settings_signature"] = settings_signature(settings)
            except (CSVValidationError, InsufficientHistoryError, AnalysisError, ValueError) as exc:
                display_error(exc)
        else:
            result = st.session_state.get("live_result")
        if result is not None and st.session_state.get("live_settings_signature") != settings_signature(settings):
            st.info("Controls changed. Click **Run analysis** to apply the new settings; the chart below still shows the last completed run.")
    else:
        if run_requested:
            try:
                with st.spinner("Fitting and freezing the locked model…"):
                    # A date lock includes every intraday bar on that calendar date.
                    lock_end = pd.Timestamp(locked_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
                    result = cached_analysis(raw, active_file_name, settings_payload, lock_end.isoformat())
                st.session_state["locked_result"] = result
                st.session_state["locked_settings_signature"] = settings_signature(settings)
            except (CSVValidationError, InsufficientHistoryError, AnalysisError, ValueError) as exc:
                display_error(exc)
        else:
            result = st.session_state.get("locked_result")
        if result is not None:
            st.caption(f"Locked model frozen at {result.as_of.date()}. Uploading later rows only adds observed context; it does not refit this model.")

if raw is None:
    st.info("Upload a TradingView CSV in the sidebar, or select one from your saved CSV library. No market-data API is used.")

if result is not None:
    overview_tab, composite_tab, spectrum_tab, table_tab, validation_tab, export_tab, rolling_backtest_tab = st.tabs(
        ["Overview", "Composite chart", "Spectrum", "Cycle table", "Validation", "Export", "Rolling Trade Backtest"]
    )

    with overview_tab:
        columns = st.columns(4)
        last_close = float(result.raw_data["close"].iloc[-1])
        columns[0].metric("Symbol / file", result.metadata.symbol, result.metadata.file_name)
        columns[1].metric("Data range", f"{result.metadata.start.date()} → {result.metadata.end.date()}")
        columns[2].metric("Bars / timeframe", f"{result.metadata.bars:,}", result.metadata.timeframe)
        columns[3].metric("Last close at model as-of", f"{last_close:,.4f}")
        second = st.columns(4)
        periods = ", ".join(f"{period:g}" for period in result.selected_cycles["period"])
        next_peak = "Not in horizon" if result.composite.peaks.empty else str(result.composite.peaks["timestamp"].iloc[0].date())
        next_trough = "Not in horizon" if result.composite.troughs.empty else str(result.composite.troughs["timestamp"].iloc[0].date())
        second[0].metric("Selected cycles", periods)
        second[1].metric("Composite phase", f"{result.composite.current_phase_deg:.1f}°", phase_description(result.composite.current_phase_deg))
        second[2].metric("Next projected peak", next_peak)
        second[3].metric("Next projected trough", next_trough)
        if result.metadata.warnings:
            for warning in result.metadata.warnings:
                st.warning(warning)
        st.markdown("#### Inspectable method notes")
        for note in result.methodology_notes:
            st.write(f"- {note}")
        st.caption("Inspired by the public FSC Cycle Scanner whitepaper. This is a transparent approximation, not Cycles.org software and not an identical implementation.")

    with composite_tab:
        st.info("The lower panel is a detrended oscillator/scenario. Its vertical scale is not a price target.")
        composite_chart = composite_figure(result, actual_data=frame if mode == "Locked as-of date" else None)
        st.pyplot(composite_chart, use_container_width=True)
        plt.close(composite_chart)
        st.markdown("#### Next projected peaks and troughs")
        projected_turns = projected_turns_table(result.composite, len(result.raw_data))
        if projected_turns.empty:
            st.caption("No projected turning points fall inside the selected forecast horizon.")
        else:
            st.dataframe(
                projected_turns,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "date": st.column_config.DatetimeColumn("Projected date", format="YYYY-MM-DD HH:mm"),
                    "turn": st.column_config.TextColumn("Turn"),
                    "bars_ahead": st.column_config.NumberColumn("Bars ahead", format="%d"),
                    "composite": st.column_config.NumberColumn("Composite value", format="%.4f"),
                },
            )
            st.caption("Green dashed lines mark projected peaks; red dashed lines mark projected troughs. Each line spans both panels so it can be compared directly with the stock chart.")

    with spectrum_tab:
        spectrum_chart = spectrum_figure(result)
        st.pyplot(spectrum_chart, use_container_width=True)
        plt.close(spectrum_chart)
        st.caption("Amplitude and strength are normalized only for the chart; the table and exports retain their calculated units.")

    with table_tab:
        display_columns = [
            "rank", "period", "amplitude", "spectral_amplitude", "fit", "stability",
            "bartels_genuineness", "strength", "current_phase_deg", "eligible", "selected",
        ]
        cycle_table = result.spectrum.sort_values("rank")[display_columns].rename(
            columns={
                "rank": "Rank", "period": "Period", "amplitude": "Recent amplitude",
                "spectral_amplitude": "Spectral amplitude", "fit": "Fit / correlation",
                "stability": "Stability", "bartels_genuineness": "Bartels-style genuineness %",
                "strength": "Strength", "current_phase_deg": "Current phase °",
                "eligible": "Eligible", "selected": "Selected",
            }
        )
        st.dataframe(
            cycle_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fit / correlation": st.column_config.NumberColumn(format="%.3f"),
                "Stability": st.column_config.NumberColumn(format="%.3f"),
                "Bartels-style genuineness %": st.column_config.NumberColumn(format="%.1f"),
                "Current phase °": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    with validation_tab:
        st.write("Each split fits on a historical prefix, freezes the model, and scores only the next unseen horizon.")
        validation_controls = st.columns(3)
        turn_tolerance = validation_controls[0].number_input("Turn tolerance (bars)", min_value=1, max_value=50, value=5, step=1)
        validation_splits = validation_controls[1].number_input("Maximum splits", min_value=2, max_value=20, value=8, step=1)
        run_validation = validation_controls[2].button("Run walk-forward testing", type="primary", use_container_width=True)
        validation_result = st.session_state.get("validation_result")
        if run_validation:
            try:
                with st.spinner("Running leakage-controlled historical fits…"):
                    validation_result = cached_validation(
                        raw, active_file_name, settings_payload, int(turn_tolerance), int(validation_splits)
                    )
                st.session_state["validation_result"] = validation_result
            except ValueError as exc:
                st.error(str(exc))
        if validation_result is not None:
            st.dataframe(validation_result.summary, use_container_width=True, hide_index=True)
            validation_chart = validation_figure(validation_result)
            st.pyplot(validation_chart, use_container_width=True)
            plt.close(validation_chart)
            with st.expander("Performance by historical segment"):
                st.dataframe(validation_result.segments, use_container_width=True, hide_index=True)
        else:
            st.caption("Validation is deliberately opt-in because it runs many independent historical scans.")

    with export_tab:
        st.write("Every export is generated from the completed model currently displayed above.")
        composite_export_chart = composite_figure(result, actual_data=frame if mode == "Locked as-of date" else None)
        spectrum_export_chart = spectrum_figure(result)
        composite_png = figure_png(composite_export_chart)
        spectrum_png = figure_png(spectrum_export_chart)
        plt.close(composite_export_chart)
        plt.close(spectrum_export_chart)
        downloads = st.columns(2)
        downloads[0].download_button("Selected cycles · CSV", selected_cycles_csv(result), "selected_cycles.csv", "text/csv", use_container_width=True)
        downloads[1].download_button("Composite values · CSV", composite_csv(result), "composite_values.csv", "text/csv", use_container_width=True)
        downloads[0].download_button("Settings · JSON", settings_json(result), "cycle_settings.json", "application/json", use_container_width=True)
        downloads[1].download_button("Pine-ready settings · TXT", pine_ready_settings(result), "pine_ready_settings.txt", "text/plain", use_container_width=True)
        downloads[0].download_button("Composite chart · PNG", composite_png, "composite_chart.png", "image/png", use_container_width=True)
        downloads[1].download_button("Spectrum chart · PNG", spectrum_png, "spectrum_chart.png", "image/png", use_container_width=True)
        downloads[0].download_button("Complete report · Markdown", markdown_report(result), "cycle_analysis_report.md", "text/markdown", use_container_width=True)

    with rolling_backtest_tab:
        st.subheader("Rolling Trade Backtest")
        st.info(
            "This is a rolling historical simulation. Each day’s cycle model is recalculated using only "
            "information available up to that date. Signals are executed on the next bar by default. "
            "Results are historical simulations and do not guarantee future performance."
        )
        st.caption(
            "The backtest uses the current cycle-analysis controls exactly as shown in the main sidebar. "
            "It does not optimize or replace those settings."
        )
        with st.expander("Exact signal and execution logic"):
            st.markdown(
                """
                - **Bullish state (default):** next projected composite > current composite. Target position is long.
                - **Bearish state (default):** next projected composite < current composite. Target position is short when shorting is enabled.
                - A position reverses whenever that projected state changes. This does not require the recalculated composite to place an exact three-point peak or trough on one particular day.
                - The legacy exact-turn rule remains separately selectable for comparison.
                - Every composite value comes from the model fitted on that date's prefix only.
                - The backtest starts flat. The first valid state may schedule an order for the following bar, never the current bar.
                - By default, a signal formed at today's close executes at the next bar's open. A missing next open falls back to that bar's close and is counted in the results.
                - Duplicate same-direction states are ignored.
                - Any final open position is closed at the last CSV close.
                """
            )
        try:
            earliest_date = earliest_backtest_date(frame, settings)
            required_bars = minimum_backtest_bars(settings)
        except ValueError as exc:
            st.warning(str(exc))
            earliest_date = None

        if earliest_date is not None:
            current_start = st.session_state.get("rolling_start_date", earliest_date.date())
            if current_start < earliest_date.date() or current_start > metadata.end.date():
                st.session_state["rolling_start_date"] = earliest_date.date()

            with st.container(border=True):
                st.markdown("#### Backtest controls")
                date_columns = st.columns([1, 1, 1])
                selected_start_date = date_columns[0].date_input(
                    "Start date",
                    min_value=earliest_date.date(),
                    max_value=metadata.end.date(),
                    key="rolling_start_date",
                )
                date_columns[1].metric("Earliest valid start", str(earliest_date.date()), f"{required_bars:,} required bars")
                date_columns[2].metric("Final CSV date", str(metadata.end.date()), f"{metadata.bars:,} total bars")

                capital_columns = st.columns(3)
                initial_capital = capital_columns[0].number_input(
                    "Initial capital", min_value=1.0, step=1_000.0, key="bt_initial_capital"
                )
                position_size_pct = capital_columns[1].number_input(
                    "Position size (% of equity)", min_value=1.0, max_value=100.0, step=5.0,
                    key="bt_position_size_pct",
                )
                leverage = capital_columns[2].number_input(
                    "Leverage", min_value=1.0, max_value=10.0, step=0.25, key="bt_leverage"
                )

                cost_columns = st.columns(3)
                commission = cost_columns[0].number_input(
                    "Commission per order", min_value=0.0, step=1.0, key="bt_commission"
                )
                slippage_pct = cost_columns[1].number_input(
                    "Slippage (%)", min_value=0.0, max_value=10.0, step=0.01, key="bt_slippage_pct"
                )
                execution_timing = cost_columns[2].selectbox(
                    "Execution price", ["Next bar open", "Next bar close"], key="bt_execution_timing"
                )

                option_columns = st.columns(3)
                signal_mode = option_columns[0].selectbox(
                    "Signal mode",
                    ["Bullish / bearish projected state", "Exact projected turn (legacy)"],
                    key="bt_signal_mode",
                )
                allow_shorting = option_columns[1].checkbox("Allow shorting", key="bt_allow_shorting")
                one_bar_confirmation = option_columns[2].checkbox(
                    "Require one-bar confirmation", key="bt_one_bar_confirmation",
                    help="State mode requires the same new bullish/bearish state on two consecutive prefix-only fits before reversing.",
                )
                diagnostic_columns = st.columns(3)
                turn_tolerance = diagnostic_columns[0].number_input(
                    "Oracle turn tolerance (bars)", min_value=0, max_value=30, step=1,
                    key="bt_turn_tolerance",
                    help="Used only for the hindsight diagnostic, never for strategy signals or returns.",
                )
                run_backtest = st.button("Run rolling trade backtest", type="primary", use_container_width=True)

            backtest_settings = BacktestSettings(
                initial_capital=float(initial_capital),
                position_size_pct=float(position_size_pct),
                allow_shorting=bool(allow_shorting),
                commission_per_order=float(commission),
                slippage_pct=float(slippage_pct),
                leverage=float(leverage),
                execution_timing=str(execution_timing),
                signal_mode=str(signal_mode),
                one_bar_confirmation=bool(one_bar_confirmation),
                turn_tolerance_bars=int(turn_tolerance),
            )
            backtest_payload = json.dumps(asdict(backtest_settings), sort_keys=True)
            backtest_signature = hashlib.sha256(
                raw + settings_payload.encode() + backtest_payload.encode() + str(selected_start_date).encode()
            ).hexdigest()
            backtest_result = st.session_state.get("rolling_backtest_result")
            if run_backtest:
                try:
                    with st.spinner("Recalculating one prefix-only cycle model for every backtest date…"):
                        backtest_result = cached_rolling_backtest(
                            raw,
                            active_file_name,
                            settings_payload,
                            backtest_payload,
                            str(selected_start_date),
                        )
                    st.session_state["rolling_backtest_result"] = backtest_result
                    st.session_state["rolling_backtest_signature"] = backtest_signature
                except ValueError as exc:
                    st.error(str(exc))
                    backtest_result = None

            if backtest_result is not None and st.session_state.get("rolling_backtest_signature") != backtest_signature:
                st.warning("Backtest controls or cycle settings changed. Click **Run rolling trade backtest** to refresh the results below.")

            if backtest_result is not None:
                summary = backtest_result.summary

                def summary_value(key: str, kind: str) -> str:
                    value = summary[key]
                    if pd.isna(value):
                        return "—"
                    if kind == "money":
                        return f"${value:,.2f}"
                    if kind == "percent":
                        return f"{value:,.2f}%"
                    if kind == "ratio":
                        return "∞" if value == float("inf") else f"{value:,.2f}"
                    return f"{int(value):,}"

                metric_specs = [
                    ("Initial capital", "initial_capital", "money"),
                    ("Final equity", "final_equity", "money"),
                    ("Net profit", "net_profit", "money"),
                    ("Total return", "total_return_pct", "percent"),
                    ("Annualized return", "annualized_return_pct", "percent"),
                    ("Maximum drawdown", "maximum_drawdown_pct", "percent"),
                    ("Completed trades", "completed_trades", "integer"),
                    ("Win rate", "win_rate_pct", "percent"),
                    ("Long trades", "long_trades", "integer"),
                    ("Short trades", "short_trades", "integer"),
                    ("Average winner", "average_winner", "money"),
                    ("Average loser", "average_loser", "money"),
                    ("Profit factor", "profit_factor", "ratio"),
                    ("Expectancy / trade", "expectancy_per_trade", "money"),
                    ("Long-only net P&L", "long_only_net_pnl", "money"),
                    ("Short-only net P&L", "short_only_net_pnl", "money"),
                    ("Buy-and-hold return", "buy_and_hold_return_pct", "percent"),
                    ("Time in market", "time_in_market_pct", "percent"),
                    ("Longest winning streak", "longest_winning_streak", "integer"),
                    ("Longest losing streak", "longest_losing_streak", "integer"),
                ]
                st.markdown("#### Summary metrics")
                for offset in range(0, len(metric_specs), 4):
                    metric_columns = st.columns(4)
                    for column, (label, key, kind) in zip(metric_columns, metric_specs[offset : offset + 4]):
                        column.metric(label, summary_value(key, kind))
                if summary["open_to_close_fallbacks"]:
                    st.warning(
                        f"Next-bar open was missing on {summary['open_to_close_fallbacks']} execution event(s); "
                        "the simulator used that bar’s close as the documented fallback."
                    )

                st.markdown("#### Equity, cash, and drawdown")
                equity_chart = backtest_equity_figure(backtest_result)
                st.pyplot(equity_chart, use_container_width=True)
                plt.close(equity_chart)

                st.markdown("#### Trade log")
                if backtest_result.trades.empty:
                    st.caption("No completed trades were generated by the rolling signals.")
                else:
                    trade_display = backtest_result.trades.copy()
                    for cycle_column in ("selected_cycles_at_entry", "selected_cycles_at_exit"):
                        trade_display[cycle_column] = trade_display[cycle_column].map(
                            lambda values: ", ".join(f"{value:g}" for value in values)
                        )
                    st.dataframe(trade_display, use_container_width=True, hide_index=True)
                    st.download_button(
                        "Download trade log · CSV",
                        trade_display.to_csv(index=False).encode(),
                        "rolling_backtest_trades.csv",
                        "text/csv",
                    )

                st.markdown("#### Daily rolling signals")
                signal_display = backtest_result.signals.copy()
                for cycle_column in (
                    "selected_cycle_periods", "cycle_amplitudes", "fit_correlations", "stabilities"
                ):
                    signal_display[cycle_column] = signal_display[cycle_column].map(
                        lambda values: ", ".join(f"{value:.4g}" for value in values)
                    )
                daily_columns = [
                    "date", "close", "composite", "previous_composite", "next_projected_composite",
                    "projected_slope", "cycle_state", "signal", "position_after_signal",
                    "selected_cycle_periods", "cycle_amplitudes",
                    "fit_correlations", "stabilities", "equity", "drawdown", "model_valid",
                ]
                st.dataframe(signal_display[daily_columns], use_container_width=True, hide_index=True)
                st.download_button(
                    "Download daily signals · CSV",
                    signal_display.to_csv(index=False).encode(),
                    "rolling_backtest_daily_signals.csv",
                    "text/csv",
                )

                st.markdown("#### Cycle diagnostics")
                diagnostic_columns = st.columns(6)
                diagnostics = backtest_result.cycle_diagnostics
                diagnostic_columns[0].metric("Selection changed", f"{diagnostics['selection_change_pct']:.1f}% of dates")
                diagnostic_columns[1].metric("Consecutive overlap", f"{diagnostics['mean_consecutive_overlap_pct']:.1f}%")
                diagnostic_columns[2].metric("Unique combinations", f"{diagnostics['unique_cycle_combinations']:,}")
                diagnostic_columns[3].metric("Valid rolling models", f"{diagnostics['dates_with_valid_model_pct']:.1f}%")
                diagnostic_columns[4].metric("Bullish state", f"{diagnostics['bullish_state_pct']:.1f}%")
                diagnostic_columns[5].metric("Bearish state", f"{diagnostics['bearish_state_pct']:.1f}%")
                heatmap = cycle_selection_heatmap(backtest_result)
                st.pyplot(heatmap, use_container_width=True)
                plt.close(heatmap)

                st.markdown("#### Hindsight turn correspondence — diagnostic only")
                st.warning(
                    "This comparison uses actual future price turns after the simulation. It is an oracle diagnostic only "
                    "and is never used to generate trades, position sizes, or performance."
                )
                st.dataframe(backtest_result.turn_diagnostics, use_container_width=True, hide_index=True)

                failed_models = backtest_result.signals[~backtest_result.signals["model_valid"]]
                if not failed_models.empty:
                    with st.expander(f"Rolling model failures ({len(failed_models)})"):
                        st.dataframe(
                            failed_models[["date", "model_message"]], use_container_width=True, hide_index=True
                        )

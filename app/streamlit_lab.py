"""Phase 6 analytical lab — Phase 4 metrics, Phase 5 figures, station/hour explorer.

Run from the project root:
    streamlit run app/streamlit_lab.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
PHASE4 = REPORTS / "phase4"
PHASE5 = REPORTS / "phase5"
PREDS = DATA / "app_hourly_preds_2024_09.parquet"
STATIONS = DATA / "stations_geo.parquet"


st.set_page_config(
    page_title="Toronto Bike Share lab",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Toronto Bike Share — analytical lab")
st.caption(
    "September 2024 holdout. The map app is the friendly surface; this lab is for "
    "checking metrics, interpretation figures, and individual station series."
)


@st.cache_data(show_spinner=False)
def load_preds() -> pd.DataFrame:
    frame = pd.read_parquet(PREDS)
    frame["hour_ts"] = pd.to_datetime(frame["hour_ts"])
    return frame


@st.cache_data(show_spinner=False)
def load_stations() -> pd.DataFrame:
    return pd.read_parquet(STATIONS)


@st.cache_data(show_spinner=False)
def load_test_results() -> pd.DataFrame:
    return pd.read_csv(PHASE4 / "test_results.csv")


tab_metrics, tab_interp, tab_explore = st.tabs(
    ["Phase 4 metrics", "Phase 5 interpretation", "Station explorer"]
)

with tab_metrics:
    st.subheader("September test metrics")
    if not (PHASE4 / "test_results.csv").exists():
        st.error("Missing reports/phase4/test_results.csv — run Phase 4 first.")
    else:
        results = load_test_results()
        st.dataframe(results, use_container_width=True, hide_index=True)
        best = results.loc[results["mae"].idxmin()]
        st.success(
            f"Best MAE: **{best['model']}** at {best['mae']:.3f} "
            f"({best['mae_vs_weekly_pct']:.1f}% better than weekly naive)."
        )
        walkthrough = PHASE4 / "walkthrough.md"
        if walkthrough.exists():
            with st.expander("Phase 4 walkthrough"):
                st.markdown(walkthrough.read_text(encoding="utf-8"))

with tab_interp:
    st.subheader("What the models look at")
    figs = [
        ("SHAP summary (GBM)", PHASE5 / "figures" / "shap_summary.png"),
        ("Poisson station coefficients", PHASE5 / "figures" / "poisson_station_coefs.png"),
        ("Poisson shared coefficients", PHASE5 / "figures" / "poisson_shared_coefs.png"),
    ]
    cols = st.columns(len(figs))
    for col, (title, path) in zip(cols, figs):
        with col:
            st.markdown(f"**{title}**")
            if path.exists():
                st.image(str(path), use_container_width=True)
            else:
                st.info(f"Missing {path.name}")
    narrative = PHASE5 / "narrative.md"
    if narrative.exists():
        with st.expander("Phase 5 narrative"):
            st.markdown(narrative.read_text(encoding="utf-8"))

with tab_explore:
    if not PREDS.exists():
        st.error("Missing app predictions. Run `python -m src.phase6_prep` first.")
    else:
        preds = load_preds()
        stations = load_stations() if STATIONS.exists() else pd.DataFrame()
        names = (
            stations.set_index("station_id")["name"].to_dict()
            if not stations.empty
            else {}
        )
        station_ids = sorted(preds["station_id"].unique().tolist())
        labels = {sid: f"{sid} — {names.get(sid, 'unknown')}" for sid in station_ids}

        c1, c2 = st.columns(2)
        with c1:
            station_id = st.selectbox(
                "Station",
                station_ids,
                index=station_ids.index(7006) if 7006 in station_ids else 0,
                format_func=lambda s: labels[s],
            )
        with c2:
            hours = sorted(preds["hour_ts"].unique())
            default = pd.Timestamp("2024-09-23 08:00")
            hour = st.select_slider(
                "Hour",
                options=hours,
                value=default if default in hours else hours[len(hours) // 2],
                format_func=lambda t: pd.Timestamp(t).strftime("%a %Y-%m-%d %H:00"),
            )

        row = preds[(preds["station_id"] == station_id) & (preds["hour_ts"] == hour)]
        if row.empty:
            st.warning("No scored row for that station and hour.")
        else:
            r = row.iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Actual", f"{r['actual']:.0f}")
            m2.metric("GBM (1h)", f"{r['gbm_pred']:.2f}", f"{r['gbm_pred'] - r['actual']:+.2f}")
            m3.metric("Weekly naive", f"{r['weekly_naive']:.0f}", f"{r['weekly_naive'] - r['actual']:+.0f}")
            m4.metric("Poisson", f"{r['poisson_pred']:.2f}", f"{r['poisson_pred'] - r['actual']:+.2f}")

            st.markdown(
                f"Weather that hour: **{r['temp_c']:.1f}°C**, "
                f"**{r['precip_mm']:.1f} mm** rain, **{r['wind_speed_kmh']:.1f} km/h** wind · "
                f"{'weekend' if r['is_weekend'] else 'weekday'}"
                f"{' · holiday' if r['is_holiday'] else ''}."
            )

            hist = preds[preds["station_id"] == station_id].sort_values("hour_ts")
            start = pd.Timestamp(hour) - pd.Timedelta(hours=47)
            window = hist[(hist["hour_ts"] >= start) & (hist["hour_ts"] <= hour)].set_index("hour_ts")
            st.line_chart(window[["actual", "gbm_pred", "weekly_naive"]])
            with st.expander("Raw row"):
                st.dataframe(row.T, use_container_width=True)

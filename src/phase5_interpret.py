"""Phase 5 — interpretation: Poisson coefficients, GBM SHAP, interview narrative.

Reads the Phase 4 finalist artifacts (models/*.joblib) and September test rows.
Does not refit models.

Run from project root:
    python -m src.phase5_interpret
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from src.db import PROJECT_ROOT, get_connection
from src.interpretation import (
    case_shap_rows,
    highlight_signed,
    humanize_poisson_feature,
    rank_mean_abs_shap,
    tidy_poisson_coefficients,
)
from src.modeling import GBM_FEATURES, POISSON_FEATURES, TARGET, load_features

REPORT_DIR = PROJECT_ROOT / "reports" / "phase5"
MODELS_DIR = PROJECT_ROOT / "models"
FIG_DIR = REPORT_DIR / "figures"

# SHAP on the full September matrix is too slow; a fixed sample is enough for
# global ranking and still reproducible.
SHAP_SAMPLE_N = 4_000
SHAP_RANDOM_SEED = 0

# Interview walkthrough cases (same station as Phase 4 walkthrough.md)
CASE_SPECS = [
    {
        "story": "Bay/College — Monday 8am commute peak",
        "start_station_id": 7006,
        "hour_ts": "2024-09-23 08:00:00",
    },
    {
        "story": "Bay/College — quiet Tuesday 2am",
        "start_station_id": 7006,
        "hour_ts": "2024-09-24 02:00:00",
    },
    {
        "story": "Quieter park station — rainy midday",
        "start_station_id": 7629,
        "hour_ts": "2024-09-09 12:00:00",
    },
]


def _station_names() -> dict[int, str]:
    con = get_connection(read_only=True)
    try:
        df = con.execute(
            """
            SELECT start_station_id, any_value(start_station_name) AS name
            FROM trips_clean
            GROUP BY start_station_id
            """
        ).fetchdf()
    finally:
        con.close()
    return {int(r.start_station_id): str(r.name) for r in df.itertuples(index=False)}


def _load_test_scored(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["split"] == "test") & df["lag_168h"].notna()].reset_index(drop=True)


def _poisson_feature_names(pre) -> np.ndarray:
    """Build ColumnTransformer output names without get_feature_names_out.

    The offday_hour branch starts with a FunctionTransformer that doesn't
    implement get_feature_names_out, so sklearn can't name the whole pipeline.
    """
    names: list[str] = []
    for name, trans, cols in pre.transformers_:
        if name == "remainder" or trans == "drop":
            continue
        if name == "offday_hour":
            for cat in trans.named_steps["oh"].categories_[0]:
                names.append(f"offday_hour__offday_hour_{int(cat)}")
        elif name == "dow":
            for cat in trans.categories_[0]:
                names.append(f"dow__day_of_week_{int(cat)}")
        elif name == "lag":
            names.append("lag__lag_168h")
        elif name == "num":
            for col in cols:
                names.append(f"num__{col}")
        elif name == "station":
            for cat in trans.categories_[0]:
                names.append(f"station__start_station_id_{cat}")
        else:
            raise ValueError(f"unexpected Poisson transformer: {name}")
    return np.asarray(names, dtype=object)


def interpret_poisson(model, station_names: dict[int, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    pre = model.named_steps["pre"]
    glm = model.named_steps["glm"]
    names = _poisson_feature_names(pre)
    if len(names) != len(glm.coef_):
        raise ValueError(f"name/coef length mismatch: {len(names)} vs {len(glm.coef_)}")
    coef = tidy_poisson_coefficients(names, glm.coef_)
    coef["label"] = coef["feature"].map(humanize_poisson_feature)
    # Attach station display names where applicable
    coef["station_name"] = None
    station_mask = coef["group"] == "station"
    if station_mask.any():
        ids = coef.loc[station_mask, "feature"].str.extract(r"station__start_station_id_(.+)$")[0]
        coef.loc[station_mask, "station_name"] = ids.map(
            lambda x: station_names.get(int(x), None) if str(x).isdigit() else None
        )
        coef.loc[station_mask, "label"] = coef.loc[station_mask].apply(
            lambda r: f"{r['label']}"
            + (f" ({r['station_name']})" if r["station_name"] else ""),
            axis=1,
        )

    shared = coef[coef["group"] != "station"].copy()
    stations = coef[coef["group"] == "station"].copy()
    return shared, stations


def plot_poisson_shared(shared: pd.DataFrame, path: Path) -> None:
    top = shared.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#1b7f4e" if c > 0 else "#a33b2b" for c in top["coefficient"]]
    ax.barh(top["label"], top["coefficient"], color=colors)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("Poisson coefficient (log expected departures)")
    ax.set_title("Poisson (station model) — non-station drivers")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_poisson_stations(stations: pd.DataFrame, path: Path) -> None:
    named = stations[stations["station_name"].notna() & (stations["station_name"] != "nan")]
    top = (
        pd.concat([named.nlargest(8, "coefficient"), named.nsmallest(8, "coefficient")])
        .drop_duplicates("feature")
        .sort_values("coefficient")
    )
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#1b7f4e" if c > 0 else "#a33b2b" for c in top["coefficient"]]
    labels = top["label"].str.replace(r"^station ", "", regex=True)
    ax.barh(labels, top["coefficient"], color=colors)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("Poisson coefficient (log expected departures)")
    ax.set_title("Poisson — busiest vs quietest station effects")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def compute_shap(model, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """TreeExplainer on a sample; returns (shap_values, sample_index)."""
    rng = np.random.default_rng(SHAP_RANDOM_SEED)
    n = min(SHAP_SAMPLE_N, len(X))
    idx = rng.choice(len(X), size=n, replace=False)
    Xs = X.iloc[idx]
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(Xs)
    return np.asarray(values, dtype="float64"), idx


def plot_shap_importance(importance: pd.DataFrame, path: Path) -> None:
    top = importance.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(top["feature"], top["mean_abs_shap"], color="#2c5f8a")
    ax.set_xlabel("mean |SHAP| (log expected departures)")
    ax.set_title(f"GBM full — global importance (n={SHAP_SAMPLE_N:,} Sep sample)")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_shap_beeswarm(shap_values: np.ndarray, X_sample: pd.DataFrame, path: Path) -> None:
    plt.figure(figsize=(9, 6))
    shap.summary_plot(shap_values, X_sample, show=False, max_display=12)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()


def explain_cases(
    gbm,
    poisson,
    test: pd.DataFrame,
    shap_background: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Local SHAP for the interview cases; also store Poisson/GBM predictions."""
    rows = []
    explainer = shap.TreeExplainer(gbm)
    poisson_cols = [*POISSON_FEATURES, "start_station_id"]
    for spec in CASE_SPECS:
        ts = pd.Timestamp(spec["hour_ts"])
        mask = (test["start_station_id"] == spec["start_station_id"]) & (test["hour_ts"] == ts)
        if not mask.any():
            raise ValueError(f"case not in scored September rows: {spec}")
        row = test.loc[mask].iloc[0]
        Xg = row[GBM_FEATURES].to_frame().T
        Xp = row[poisson_cols].to_frame().T
        gbm_pred = float(gbm.predict(Xg)[0])
        poi_pred = float(poisson.predict(Xp)[0])
        shap_row = np.asarray(explainer.shap_values(Xg), dtype="float64").reshape(-1)
        local = case_shap_rows(
            shap_row, GBM_FEATURES, Xg.to_numpy(dtype="float64").reshape(-1), top_n=8
        )
        local.insert(0, "story", spec["story"])
        local.insert(1, "start_station_id", spec["start_station_id"])
        local.insert(2, "hour_ts", ts)
        local["actual"] = float(row[TARGET])
        local["weekly_naive"] = float(row["lag_168h"])
        local["poisson_pred"] = poi_pred
        local["gbm_pred"] = gbm_pred
        local["base_value"] = float(np.asarray(explainer.expected_value).reshape(-1)[0])
        rows.append(local)
        _ = shap_background  # reserved if we later switch to KernelExplainer
    return pd.concat(rows, ignore_index=True)


def plot_case_waterfall(case_df: pd.DataFrame, story: str, path: Path) -> None:
    sub = case_df[case_df["story"] == story].copy()
    if sub.empty:
        return
    sub = sub.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#1b7f4e" if v > 0 else "#a33b2b" for v in sub["shap"]]
    labels = [f"{f}={v:g}" for f, v in zip(sub["feature"], sub["feature_value"])]
    ax.barh(labels, sub["shap"], color=colors)
    ax.axvline(0, color="#333", linewidth=0.8)
    actual = sub["actual"].iloc[0]
    gbm_pred = sub["gbm_pred"].iloc[0]
    ax.set_xlabel("SHAP contribution (log space)")
    ax.set_title(f"{story}\nactual={actual:g} · GBM={gbm_pred:.2f}")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_narrative(
    shared: pd.DataFrame,
    stations: pd.DataFrame,
    importance: pd.DataFrame,
    cases: pd.DataFrame,
    station_names: dict[int, str],
    path: Path,
) -> None:
    highlighted = highlight_signed(shared, n=3)
    top_imp = importance.head(5)
    peak = cases[cases["story"].str.contains("Monday 8am")].drop_duplicates("feature")
    bay = station_names.get(7006, "station 7006")
    named_stations = stations[stations["station_name"].notna() & (stations["station_name"] != "nan")]
    busy = named_stations.nlargest(1, "coefficient").iloc[0]
    quiet = named_stations.nsmallest(1, "coefficient").iloc[0]
    weather_lag = shared[shared["group"].isin(["weekly_lag", "weather", "calendar"])].copy()
    weather_lag = weather_lag.sort_values("coefficient", key=np.abs, ascending=False)

    lines = [
        "# Phase 5 — why the models predict what they predict",
        "",
        "Interview-ready interpretation of the Phase 4 finalists "
        "(`poisson_station` and `gbm_full_poisson`). Numbers come from the "
        "Jan–Aug refit artifacts and a September holdout sample.",
        "",
        "## The three drivers (say this first)",
        "",
        "1. **Time of day sets the floor and the peak.** SHAP ranks "
        "`hour_of_day` first globally; Poisson’s largest coefficients are "
        "overnight drops (~0.13× at 3am) and commute lifts (~2.4–2.7× at "
        "8am / 5–6pm weekdays).",
        "2. **Recent station activity beats a single weekly copy.** After "
        "hour-of-day, GBM importance is `roll_mean_168h`, `roll_mean_24h`, "
        "and `lag_1h` — what this dock has been doing lately. `lag_168h` "
        "still helps, but it is not the whole story (and weekly naive uses "
        "only that).",
        "3. **Which station you are at is huge for the GLM.** Poisson without "
        "station identity leaned too hard on one weekly lag; with station "
        "one-hots, waterfront/downtown docks get a permanent lift and "
        "low-demand docks stay low.",
        "",
        "## Poisson coefficients (official `poisson_station`)",
        "",
        "Poisson uses a log link: a coefficient of `c` multiplies expected "
        "departures by `exp(c)` when that feature turns on / increases "
        "(after scaling / one-hot).",
        "",
        "### Shared (non-station) drivers — strongest up and down",
        "",
        "| Feature | Coef | × multiplier | Plain reading |",
        "|---------|-----:|-------------:|---------------|",
    ]
    for r in highlighted.itertuples(index=False):
        direction = "up" if r.coefficient > 0 else "down"
        lines.append(
            f"| {r.label} | {r.coefficient:.3f} | {r.multiplier:.3f} | pulls prediction {direction} |"
        )
    lines += [
        "",
        "Weather / weekly lag (scaled):",
        "",
        "| Feature | Coef | × multiplier |",
        "|---------|-----:|-------------:|",
    ]
    for r in weather_lag.itertuples(index=False):
        lines.append(f"| {r.label} | {r.coefficient:.3f} | {r.multiplier:.3f} |")
    lines += [
        "",
        f"Top busy station effect: **{busy['label']}** (coef {busy['coefficient']:.2f}).",
        f"Top quiet station effect: **{quiet['label']}** (coef {quiet['coefficient']:.2f}).",
        "",
        "Plots: `figures/poisson_shared_coefs.png`, `figures/poisson_station_coefs.png`.",
        "",
        "## GBM SHAP (app default `gbm_full_poisson`)",
        "",
        f"Global importance from TreeExplainer on a fixed sample of "
        f"{SHAP_SAMPLE_N:,} September station-hours:",
        "",
        "| Feature | mean \\|SHAP\\| |",
        "|---------|-------------:|",
    ]
    for r in top_imp.itertuples(index=False):
        lines.append(f"| {r.feature} | {r.mean_abs_shap:.4f} |")
    lines += [
        "",
        "Plots: `figures/gbm_shap_importance.png`, `figures/gbm_shap_beeswarm.png`.",
        "",
        f"## Case study — {bay}, Monday 2024-09-23 08:00",
        "",
    ]
    if not peak.empty:
        actual = peak["actual"].iloc[0]
        weekly = peak["weekly_naive"].iloc[0]
        gbm_pred = peak["gbm_pred"].iloc[0]
        poi = peak["poisson_pred"].iloc[0]
        lines += [
            f"Actual departures: **{actual:g}**. Weekly naive copied last Monday "
            f"({weekly:g}). Poisson predicted **{poi:.1f}**; GBM **{gbm_pred:.1f}**.",
            "",
            "Largest SHAP pushes for the GBM on this hour:",
            "",
            "| Feature | Value | SHAP |",
            "|---------|------:|-----:|",
        ]
        for r in peak.head(6).itertuples(index=False):
            lines.append(f"| {r.feature} | {r.feature_value:g} | {r.shap:.3f} |")
        lines += [
            "",
            "Verbal line: *weekly naive pasted 16. Poisson (busy station + big "
            "weekly lag) climbed to ~13. The GBM also saw last week’s spike, but "
            "balanced it with last-hour activity (5), a moderate 24h level (~6), "
            "8am commute lift, and light rain pulling down — landing at ~7.3 "
            "next to the actual 7.*",
            "",
        ]
    lines += [
        "More cases (quiet night + rainy quieter station) are in "
        "`case_shap.csv` and `figures/case_*.png`.",
        "",
        "## How to reproduce",
        "",
        "```bash",
        "python -m src.phase5_interpret",
        "```",
        "",
        "Artifacts: this folder’s CSVs + figures. Models are loaded from "
        "`models/` (Phase 4 final fit); nothing is refit here.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_walkthrough(cases: pd.DataFrame, station_names: dict[int, str], path: Path) -> None:
    bay = station_names.get(7006, "7006")
    peak = cases[cases["story"].str.contains("Monday 8am")]
    quiet = cases[cases["story"].str.contains("quiet Tuesday")]
    lines = [
        "# Phase 5 walkthrough — say it out loud",
        "",
        "Use this as a 90-second interview answer. Details and plots live in "
        "`narrative.md` / `figures/`.",
        "",
        "## Hook (10s)",
        f"“On a Monday 8am at {bay}, seven bikes left. Copying last week said "
        "sixteen; Poisson said ~13; our 1-hour-ahead GBM said ~7.3 — by "
        "balancing last week with that morning’s activity and light rain.”",
        "",
        "## Setup (20s)",
        "Target is hourly departures per station. Baseline = same station, "
        "same hour last week. Official Poisson adds calendar, weather, weekly "
        "lag, and station identity. App default GBM adds last-hour and rolling "
        "activity (so it’s explicitly 1-hour-ahead).",
        "",
        "## Conflict (30s)",
        "Weekly naive is brittle at peaks. Poisson without station ID blew up "
        "on raw weekly lags until we used log1p and one-hots. Even then, "
        "station identity was the big GLM fix. Day-ahead GBM (no last hour) "
        "loses to a simple station×hour-of-week average on MAE — horizon matters.",
        "",
        "## Resolution (20s)",
        "Three drivers: (1) hour-of-day / commute shape, (2) recent local "
        "activity (rolling means + lag_1h), (3) which station (Poisson). "
        "SHAP ranks hour and rolling activity above a lone weekly lag.",
        "",
    ]
    if not peak.empty:
        r = peak.iloc[0]
        lines += [
            "## One number to remember",
            f"Bay/College Mon 8am: actual {r['actual']:g}, weekly {r['weekly_naive']:g}, "
            f"Poisson {r['poisson_pred']:.1f}, GBM {r['gbm_pred']:.1f}.",
            "",
        ]
    if not quiet.empty:
        r = quiet.iloc[0]
        lines += [
            "Quiet night check: everyone roughly agrees near zero "
            f"(actual {r['actual']:g}, GBM {r['gbm_pred']:.1f}). Disagreements live at peaks.",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("loading features + models…")
    station_names = _station_names()
    df = load_features()
    test = _load_test_scored(df)
    del df

    poisson = joblib.load(MODELS_DIR / "poisson_station.joblib")
    gbm = joblib.load(MODELS_DIR / "gbm_full_poisson.joblib")

    print("Poisson coefficients…")
    shared, stations = interpret_poisson(poisson, station_names)
    shared.to_csv(REPORT_DIR / "poisson_shared_coefs.csv", index=False)
    stations.to_csv(REPORT_DIR / "poisson_station_coefs.csv", index=False)
    plot_poisson_shared(shared, FIG_DIR / "poisson_shared_coefs.png")
    plot_poisson_stations(stations, FIG_DIR / "poisson_station_coefs.png")

    print(f"GBM SHAP on {SHAP_SAMPLE_N:,}-row sample…")
    X = test[GBM_FEATURES]
    shap_values, idx = compute_shap(gbm, X)
    X_sample = X.iloc[idx].reset_index(drop=True)
    importance = rank_mean_abs_shap(shap_values, GBM_FEATURES)
    importance.to_csv(REPORT_DIR / "gbm_shap_importance.csv", index=False)
    plot_shap_importance(importance, FIG_DIR / "gbm_shap_importance.png")
    plot_shap_beeswarm(shap_values, X_sample, FIG_DIR / "gbm_shap_beeswarm.png")

    print("case explanations…")
    cases = explain_cases(gbm, poisson, test)
    cases.to_csv(REPORT_DIR / "case_shap.csv", index=False)
    for spec in CASE_SPECS:
        slug = (
            spec["story"]
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("—", "-")
            .replace(",", "")
        )
        plot_case_waterfall(cases, spec["story"], FIG_DIR / f"case_{slug}.png")

    write_narrative(shared, stations, importance, cases, station_names, REPORT_DIR / "narrative.md")
    write_walkthrough(cases, station_names, REPORT_DIR / "walkthrough.md")

    meta = {
        "shap_sample_n": SHAP_SAMPLE_N,
        "shap_random_seed": SHAP_RANDOM_SEED,
        "models": {
            "poisson": "poisson_station.joblib",
            "gbm": "gbm_full_poisson.joblib",
        },
        "cases": CASE_SPECS,
        "top_gbm_features": importance.head(5).to_dict(orient="records"),
        "top_poisson_shared": shared.head(5)[["label", "coefficient", "multiplier"]].to_dict(
            orient="records"
        ),
    }
    with open(REPORT_DIR / "phase5_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\nTop GBM features:\n{importance.head(8).to_string(index=False)}")
    print(f"\nTop Poisson shared:\n{shared.head(8).to_string(index=False)}")
    print(f"\nwrote reports under {REPORT_DIR}")


if __name__ == "__main__":
    main()

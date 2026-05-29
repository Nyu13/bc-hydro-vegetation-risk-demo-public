"""Data provenance tags, map colors, and Streamlit table styling."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Table row backgrounds (light theme; readable on white dataframe chrome)
SYNTHETIC_TABLE_BG = "#fff3cd"
SYNTHETIC_TABLE_BG_ALT = "#ffe0e0"

# Pydeck RGBA — live public outage markers vs synthetic/demo
MAP_OUTAGE_LIVE_RGBA = [255, 140, 0, 210]
MAP_OUTAGE_SYNTHETIC_RGBA = [110, 110, 120, 175]
MAP_CORRIDOR_SYNTHETIC_RGBA = [128, 90, 180, 220]

PROVENANCE_LIVE = "live"
PROVENANCE_SYNTHETIC = "synthetic"

WEATHER_DISPLAY_METRIC_COLUMNS = (
    "wind_gust_kmh",
    "precipitation_mm",
    "temperature_c",
    "weather_severity_score",
)


@dataclass(frozen=True)
class DatasetProvenance:
    """Session-level provenance for one loaded dataset."""

    label: str
    is_synthetic: bool
    source: str
    detail: str = ""

    @property
    def badge(self) -> str:
        unavailable = not self.is_synthetic and "No rows loaded" in self.detail and "Live public only" in self.detail
        return provenance_badge(self.is_synthetic, unavailable=unavailable)

    @property
    def caption(self) -> str:
        base = f"{self.badge} — **{self.label}**"
        if self.source:
            base += f" (`{self.source}`)"
        if self.detail:
            base += f"  \n{self.detail}"
        return base


def provenance_badge(is_synthetic: bool, *, unavailable: bool = False) -> str:
    if unavailable:
        return "🔴 Unavailable"
    return "🟡 Demo/synthetic" if is_synthetic else "🟢 Live"


def fallback_reason_from_source(source: str) -> str:
    """Extract human-readable fallback / fetch error text from the source column."""
    text = str(source or "").strip()
    if not text:
        return ""
    marker = "fallback:"
    if marker in text.lower():
        idx = text.lower().index(marker)
        return text[idx + len(marker) :].strip()
    if "offline mode" in text.lower():
        return text
    return ""


def tag_dataframe(
    df: pd.DataFrame,
    *,
    is_synthetic: bool,
    source: str,
    data_provenance: str | None = None,
) -> pd.DataFrame:
    """Add provenance columns without mutating the caller's frame."""
    if df.empty:
        tagged = df.copy()
    else:
        tagged = df.copy()
    tagged["is_synthetic"] = is_synthetic
    tagged["data_provenance"] = data_provenance or (
        PROVENANCE_SYNTHETIC if is_synthetic else PROVENANCE_LIVE
    )
    tagged["source"] = source
    return tagged


def provenance_from_frame(
    df: pd.DataFrame,
    *,
    default_label: str,
    default_source: str,
    live_public_only: bool = False,
) -> DatasetProvenance:
    if df.empty:
        if live_public_only:
            return DatasetProvenance(
                label=default_label,
                is_synthetic=False,
                source=default_source,
                detail=(
                    "No rows loaded (Live public only is on). Check network/TLS, use **Refresh live data**, "
                    "or disable the toggle for demo CSV fallback."
                ),
            )
        return DatasetProvenance(
            label=default_label,
            is_synthetic=True,
            source=default_source,
            detail="No rows loaded.",
        )
    is_syn = bool(df["is_synthetic"].iloc[0]) if "is_synthetic" in df.columns else True
    src = str(df["source"].iloc[0]) if "source" in df.columns else default_source
    prov = (
        str(df["data_provenance"].iloc[0])
        if "data_provenance" in df.columns
        else (PROVENANCE_SYNTHETIC if is_syn else PROVENANCE_LIVE)
    )
    detail = f"data_provenance={prov}, rows={len(df)}"
    reason = fallback_reason_from_source(src)
    if is_syn and reason:
        detail = f"**Using demo fallback because live fetch failed:** {reason}  \n{detail}"
    elif not is_syn and "TLS verify relaxed" in src:
        detail = (
            "**Note:** Python could not verify BC Hydro TLS; this session used a one-time "
            "unverified retry. Set `BC_HYDRO_SSL_VERIFY=0` before `streamlit run` to skip that attempt.  \n"
            + detail
        )
    return DatasetProvenance(
        label=default_label,
        is_synthetic=is_syn,
        source=src,
        detail=detail,
    )


def display_table_columns(df: pd.DataFrame, *, show_provenance: bool = True) -> list[str]:
    """Column order for UI tables; provenance columns last when shown (never is_synthetic)."""
    hidden = {"is_synthetic"}
    if not show_provenance:
        hidden |= {"data_provenance", "source"}
    base = [c for c in df.columns if c not in hidden]
    extra = [c for c in ("data_provenance", "source") if c in df.columns and c not in base]
    if show_provenance:
        return base + [c for c in extra if c not in base]
    return base


def round_weather_display(df: pd.DataFrame) -> pd.DataFrame:
    """Round weather metrics for table display (wind/temp/score/precip to 1 decimal)."""
    out = df.copy()
    for col in WEATHER_DISPLAY_METRIC_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(1)
    return out


def _weather_styler_format_map(df: pd.DataFrame) -> dict[str, str]:
    """Pandas Styler format strings; Streamlit ignores column_config on Styler."""
    return {col: "{:.1f}" for col in WEATHER_DISPLAY_METRIC_COLUMNS if col in df.columns}


def style_synthetic_rows(
    df: pd.DataFrame,
    *,
    alt: bool = False,
    columns: list[str] | None = None,
) -> pd.io.formats.style.Styler:
    """Highlight synthetic rows for st.dataframe(Styler); is_synthetic used only for styling."""
    bg = SYNTHETIC_TABLE_BG_ALT if alt else SYNTHETIC_TABLE_BG
    if columns is not None:
        display_cols = [c for c in columns if c in df.columns and c != "is_synthetic"]
    else:
        display_cols = display_table_columns(df, show_provenance=True)

    def _row_style(row: pd.Series) -> list[str]:
        idx = row.name
        if "is_synthetic" in df.columns and bool(df.loc[idx, "is_synthetic"]):
            return [f"background-color: {bg}"] * len(row)
        return [""] * len(row)

    subset = df[display_cols] if display_cols else df.drop(columns=["is_synthetic"], errors="ignore")
    styler = subset.style.apply(_row_style, axis=1)
    weather_formats = _weather_styler_format_map(subset)
    if weather_formats:
        styler = styler.format(weather_formats, na_rep="")
    return styler


def synthetic_risk_fill(risk_level: str) -> list[int]:
    """Demo corridor markers: purple-tinted risk fills (always synthetic geometry)."""
    from src.visualization import risk_color

    base = risk_color(risk_level)
    # Blend toward MAP_CORRIDOR_SYNTHETIC_RGBA purple
    purple = MAP_CORRIDOR_SYNTHETIC_RGBA
    alpha = base[3] if len(base) > 3 else 220
    return [
        int((base[0] + purple[0]) / 2),
        int((base[1] + purple[1]) / 2),
        int((base[2] + purple[2]) / 2),
        alpha,
    ]


def outage_marker_color(is_synthetic: bool) -> list[int]:
    return MAP_OUTAGE_SYNTHETIC_RGBA if is_synthetic else MAP_OUTAGE_LIVE_RGBA

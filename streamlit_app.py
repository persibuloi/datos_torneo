import os
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from plotly import colors
import io

# Estilo por defecto de Plotly (se puede cambiar desde la UI)
px.defaults.template = "plotly_white"
# Paleta moderna (Plotly cualitativa)
COLORWAY = colors.qualitative.Vivid

# =============================
# Configuración básica
# =============================
st.set_page_config(
    page_title="Analítica de Bowling 2025",
    page_icon="🎳",
    layout="wide",
)

# CSS sutil para mejorar apariencia
st.markdown(
    """
    <style>
    /* Contenedor principal más aireado */
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    /* Subheaders con separación */
    h2 {margin-top: 0.25rem;}
    /* DataFrame con bordes suaves */
    .stDataFrame {border-radius: 10px; overflow: hidden;}
    /* Separadores más visibles */
    hr {margin: 1.5rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_FILE = os.path.join(
    os.path.expanduser("~"),
    "OneDrive - Sevasa",
    "Escritorio",
    "TORNEO APP",
    "JuegosMerge2025.xlsx",
)


@st.cache_data(show_spinner=False)
def load_excel(file_path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")
    try:
        if sheet is None:
            # Leer primera hoja por defecto
            return pd.read_excel(file_path)
        return pd.read_excel(file_path, sheet_name=sheet)
    except Exception as e:
        raise RuntimeError(f"Error leyendo Excel: {e}")


def guess_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    # Normalización para comparar
    norm = {c: c.strip().lower() for c in columns}

    def find_one(candidates: List[str]) -> Optional[str]:
        for col, low in norm.items():
            for cand in candidates:
                if cand in low:
                    return col
        return None

    guessed = {
        "jugador": find_one(["jugador", "player", "name", "nombre"]),
        "equipo": find_one(["equipo", "team"]),
        "jornada": find_one(["jornada", "fecha", "round", "week", "matchday"]),
        "linea": find_one(["linea", "línea", "game", "partida"]),
        "puntos": find_one(["ptos_gan", "puntos", "pts", "points"]),
        # Intento de encontrar puntuación de línea (score) si existiera
        "score": find_one(["score", "pinfall", "pines", "puntaje", "line score", "l1", "l2", "l3", "l4", "puntos"]),
        # Handicap (HANDI/HDC/handicap)
        "handicap": find_one(["handi", "hdc", "handicap"]),
        # Oponente (VS/Rival/Oponente/Adversario)
        "oponente": find_one(["vs", "rival", "oponente", "adversario"]),
    }
    return guessed


def kpi_card(label: str, value, help_text: Optional[str] = None, cols=None):
    c = cols if cols is not None else st.columns(1)[0]
    with c:
        st.metric(label, value, help=help_text)


def _sparkline_from_series(s: pd.Series, title: str, color: str = "#2563eb"):
    try:
        s = pd.to_numeric(s, errors='coerce')
        s = s.dropna()
        if s.empty:
            return None
        fig = px.line(x=list(range(len(s))), y=s.values, markers=False)
        fig.update_traces(line=dict(color=color, width=2), hovertemplate="%{y:.2f}<extra></extra>")
        fig.update_layout(
            title=title,
            height=120,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        return fig
    except Exception:
        return None


def compute_highlights(df: pd.DataFrame,
                       col_jugador: Optional[str],
                       col_jornada: Optional[str],
                       metric_col: Optional[str]) -> Dict[str, Optional[object]]:
    out: Dict[str, Optional[object]] = {
        "best_avg_player": None,
        "best_avg_value": None,
        "best_avg_spark": None,
        "most_consistent_player": None,
        "most_consistent_cv": None,
        "most_consistent_spark": None,
        "most_200_player": None,
        "most_200_count": 0,
        "score_distribution": None,
    }
    if df is None or df.empty or not col_jugador or not metric_col:
        return out
    data = df.copy()
    data[metric_col] = pd.to_numeric(data[metric_col], errors='coerce')

    # Best average
    try:
        by_p = data.groupby(col_jugador)[metric_col].mean().sort_values(ascending=False)
        if not by_p.empty:
            best_player = by_p.index[0]
            out["best_avg_player"] = best_player
            out["best_avg_value"] = float(by_p.iloc[0])
            # Sparkline por jornada para el jugador
            if col_jornada and col_jornada in data.columns:
                tmp = (
                    data.loc[data[col_jugador] == best_player]
                    .assign(_j=pd.to_numeric(data.loc[data[col_jugador] == best_player, col_jornada], errors='coerce'))
                    .dropna(subset=["_j"]) 
                    .groupby("_j")[metric_col]
                    .mean()
                    .sort_index()
                )
                out["best_avg_spark"] = _sparkline_from_series(tmp, title=f"{best_player}")
    except Exception:
        pass

    # Most consistent (lowest CV) with >=6 games
    try:
        g = data.groupby(col_jugador)[metric_col]
        stats = g.agg(["mean", "std", "count"]).reset_index()
        stats["cv"] = stats["std"] / stats["mean"]
        stats = stats[stats["count"] >= 6]
        stats = stats.replace([np.inf, -np.inf], np.nan).dropna(subset=["cv"])  # evitar div/0
        if not stats.empty:
            row = stats.sort_values("cv").iloc[0]
            out["most_consistent_player"] = row[col_jugador]
            out["most_consistent_cv"] = float(row["cv"])
            # Sparkline de consistencia por jornada
            if col_jornada and col_jornada in data.columns:
                tmp = (
                    data.loc[data[col_jugador] == row[col_jugador]]
                    .assign(_j=pd.to_numeric(data.loc[data[col_jugador] == row[col_jugador], col_jornada], errors='coerce'))
                    .dropna(subset=["_j"]) 
                    .groupby("_j")[metric_col]
                    .std()
                    .sort_index()
                )
                out["most_consistent_spark"] = _sparkline_from_series(tmp, title=f"{row[col_jugador]} - Desv.", color="#10b981")
    except Exception:
        pass

    # Most 200+ games
    try:
        hi = data[data[metric_col] >= 200]
        if col_jugador in hi.columns and not hi.empty:
            counts = hi.groupby(col_jugador).size().sort_values(ascending=False)
            if not counts.empty:
                out["most_200_player"] = counts.index[0]
                out["most_200_count"] = int(counts.iloc[0])
    except Exception:
        pass

    return out

def generate_insights(df: pd.DataFrame,
                      col_jugador: Optional[str],
                      col_equipo: Optional[str],
                      col_jornada: Optional[str],
                      col_linea: Optional[str],
                      col_score: Optional[str],
                      col_handicap: Optional[str],
                      use_hcp: bool = False) -> List[str]:
    insights: List[str] = []
    if df is None or df.empty or not col_score:
        return ["Sin datos suficientes para generar insights."]

    # Copias seguras y numéricas
    data = df.copy()
    data[col_score] = pd.to_numeric(data[col_score], errors='coerce')
    if col_handicap and col_handicap in data.columns:
        data[col_handicap] = pd.to_numeric(data[col_handicap], errors='coerce')
        data["__PINES_HCP__"] = data[col_score].fillna(0) + data[col_handicap].fillna(0)
    # Columna objetivo según toggle
    target_col = "__PINES_HCP__" if (use_hcp and "__PINES_HCP__" in data.columns) else col_score

    # 1) Estado general
    n_rows = len(data)
    n_jug = data[col_jugador].nunique() if col_jugador and col_jugador in data.columns else None
    jornada_txt = ""
    if col_jornada and col_jornada in data.columns:
        jj = pd.to_numeric(data[col_jornada], errors='coerce')
        jj = jj[~jj.isna()]
        if not jj.empty:
            jornada_txt = f" | Jornadas: {int(jj.min())}–{int(jj.max())}"
    if n_jug is not None:
        insights.append(f"📊 Conjunto filtrado: {n_rows} juegos | {n_jug} jugadores{jornada_txt}.")
    else:
        insights.append(f"📊 Conjunto filtrado: {n_rows} juegos{jornada_txt}.")

    # 2) Tendencia por jornada (Score)
    try:
        if col_jornada and col_jornada in data.columns:
            tmp = (
                data.assign(_j=pd.to_numeric(data[col_jornada], errors='coerce'))
                    .dropna(subset=["_j"]) 
                    .groupby("_j")[target_col].mean().reset_index()
            )
            if len(tmp) >= 2:
                coeffs = np.polyfit(tmp["_j"], tmp[target_col], 1)
                slope = coeffs[0]
                trend = "estable"
                if slope > 0.5:
                    trend = "mejorando"
                elif slope < -0.5:
                    trend = "a la baja"
                label_t = "Score+HCP" if target_col == "__PINES_HCP__" else "Score"
                insights.append(f"📈 Tendencia del promedio por jornada ({label_t}): {trend} (pendiente {slope:.2f} pines/jornada).")
    except Exception:
        pass

    # 3) Consistencia (CV) por jugador
    try:
        MIN_JUEGOS = 6
        if col_jugador and col_jugador in data.columns:
            g = data.groupby(col_jugador)[target_col]
            stats = g.agg(["mean", "std", "count"]).reset_index()
            stats["cv"] = stats["std"] / stats["mean"]
            stats = stats[stats["count"] >= MIN_JUEGOS]
            stats = stats.replace([np.inf, -np.inf], np.nan).dropna(subset=["cv"])  # evitar div/0
            if not stats.empty:
                top_cons = stats.sort_values("cv").head(3)
                names = ", ".join([f"{r[col_jugador]} (CV {r['cv']:.2f})" for _, r in top_cons.iterrows()])
                insights.append(f"🧩 Jugadores más consistentes (≥{MIN_JUEGOS} juegos): {names}.")
    except Exception:
        pass

    # 4) Juegos altos >=200 (según métrica activa)
    try:
        base_series = pd.to_numeric(data[target_col], errors='coerce')
        high = data[base_series >= 200]
        c_high = len(high)
        if c_high > 0:
            if col_jugador and col_jugador in data.columns:
                by_j = high.groupby(col_jugador).size().sort_values(ascending=False).head(3)
                top200 = ", ".join([f"{idx}: {val}" for idx, val in by_j.items()])
                insights.append(f"💯 Juegos de 200+: {c_high} en total. Top por jugadores → {top200}.")
            else:
                insights.append(f"💯 Juegos de 200+: {c_high} en total.")
    except Exception:
        pass

    # 5) Mejores líneas con/sin handicap
    try:
        if col_jugador and col_jugador in data.columns:
            best = data[[col_jugador, col_score]].dropna().sort_values(col_score, ascending=False).head(3)
            if not best.empty:
                top_s = ", ".join([f"{r[col_jugador]}: {r[col_score]:.2f}" for _, r in best.iterrows()])
                insights.append(f"🥇 Mejores líneas (Score): {top_s}.")
            if "__PINES_HCP__" in data.columns:
                best_h = data[[col_jugador, "__PINES_HCP__"]].dropna().sort_values("__PINES_HCP__", ascending=False).head(3)
                if not best_h.empty:
                    top_h = ", ".join([f"{r[col_jugador]}: {r['__PINES_HCP__']:.2f}" for _, r in best_h.iterrows()])
                    insights.append(f"🎯 Mejores líneas (con Handicap): {top_h}.")
    except Exception:
        pass

    # 6) Promedios por equipo (Score solamente)
    try:
        if col_equipo and col_equipo in data.columns:
            by_e = (
                data.dropna(subset=[col_equipo])
                    .groupby(col_equipo)[col_score]
                    .mean()
                    .sort_values(ascending=False)
                    .head(3)
            )
            if not by_e.empty:
                top_e = ", ".join([f"{idx}: {val:.2f}" for idx, val in by_e.items()])
                insights.append(f"🏆 Mejores promedios por equipo (Score): {top_e}.")
    except Exception:
        pass

    return insights

def main():
    st.title("🎳 Analítica Dinámica - Torneo XII Empresarial 2025")

    # Sidebar minimal (sin selección de archivo)
    with st.sidebar:
        theme = st.selectbox("Tema de gráficos", options=["Claro", "Oscuro"], index=0)
        palette = st.selectbox("Paleta", options=["Vivid", "Pastel", "Bold", "D3", "Dark24"], index=0)
        use_hcp = False

    # Aplicar tema de gráficos
    # Configurar plantilla y paletas
    if theme == "Oscuro":
        px.defaults.template = "plotly_dark"
    else:
        px.defaults.template = "plotly_white"

    # Paletas de Plotly
    palette_map = {
        "Vivid": colors.qualitative.Vivid,
        "Pastel": colors.qualitative.Pastel,
        "Bold": colors.qualitative.Bold,
        "D3": colors.qualitative.D3,
        "Dark24": colors.qualitative.Dark24,
    }
    COLORWAY = palette_map.get(palette, colors.qualitative.Vivid)
    ACCENT_COLOR = COLORWAY[0] if COLORWAY else "#3b82f6"

    # Cargar archivo por defecto en silencio
    file_path = DEFAULT_FILE

    try:
        df = load_excel(file_path)
    except Exception as e:
        st.error(str(e))
        st.stop()

    if df.empty:
        st.warning("El archivo está vacío o no contiene datos.")
        st.stop()

    # Detección automática de columnas (sin mapeo manual en la UI)
    guesses = guess_columns(df.columns.tolist())
    col_jugador = guesses.get("jugador") if guesses.get("jugador") in df.columns else None
    col_equipo = guesses.get("equipo") if guesses.get("equipo") in df.columns else None
    col_jornada = guesses.get("jornada") if guesses.get("jornada") in df.columns else None
    col_linea = guesses.get("linea") if guesses.get("linea") in df.columns else None
    col_puntos = guesses.get("puntos") if guesses.get("puntos") in df.columns else None
    # Score prioriza 'PUNTOS' si existe
    default_score = "PUNTOS" if "PUNTOS" in df.columns else guesses.get("score")
    col_score = default_score if default_score in df.columns else None
    # Handicap (HANDI/HDC)
    default_handi = None
    for cand in ["HANDI", "HDC", "HANDICAP", guesses.get("handicap")]:
        if cand and cand in df.columns:
            default_handi = cand
            break
    col_handicap = default_handi
    # Oponente (VS/Rival/Oponente/Adversario)
    default_vs = None
    for cand in ["VS", "RIVAL", "OPONENTE", "ADVERSARIO", guesses.get("oponente")]:
        if cand and cand in df.columns:
            default_vs = cand
            break
    col_oponente = default_vs

    # Coerción de tipos básicos
    for c in [col_jornada, col_linea, col_puntos, col_score, col_handicap]:
        if c and c in df.columns:
            # Intentar convertir a numérico cuando tenga sentido
            if df[c].dtype == object:
                df[c] = pd.to_numeric(df[c], errors='ignore')

    # Resumen de columnas oculto (se removió el expander de UI)

    # Filtros avanzados
    st.sidebar.header("Filtros")
    filtered = df.copy()
    
    # Filtro por rendimiento
    if col_score and col_score in df.columns:
        avg_global = pd.to_numeric(df[col_score], errors='coerce').mean()
        perf_filter = st.sidebar.selectbox(
            "Rendimiento", 
            options=["Todos", "Por encima del promedio", "Por debajo del promedio"],
            index=0
        )
        if perf_filter == "Por encima del promedio":
            filtered = filtered[pd.to_numeric(filtered[col_score], errors='coerce') > avg_global]
        elif perf_filter == "Por debajo del promedio":
            filtered = filtered[pd.to_numeric(filtered[col_score], errors='coerce') < avg_global]

    if col_equipo and col_equipo in df.columns:
        equipos = sorted([e for e in filtered[col_equipo].dropna().unique().tolist()])
        sel_equipo = st.sidebar.multiselect("Equipo(s)", options=equipos)
        if sel_equipo:
            filtered = filtered[filtered[col_equipo].isin(sel_equipo)]

    if col_jugador and col_jugador in df.columns:
        jugadores = sorted([j for j in filtered[col_jugador].dropna().unique().tolist()])
        sel_jugador = st.sidebar.multiselect("Jugador(es)", options=jugadores)
        if sel_jugador:
            filtered = filtered[filtered[col_jugador].isin(sel_jugador)]

    if col_jornada and col_jornada in df.columns:
        try:
            min_j, max_j = int(pd.to_numeric(filtered[col_jornada], errors='coerce').min()), int(pd.to_numeric(filtered[col_jornada], errors='coerce').max())
            r = st.sidebar.slider("Rango de Jornadas", min_value=min_j, max_value=max_j, value=(min_j, max_j))
            filtered = filtered[(pd.to_numeric(filtered[col_jornada], errors='coerce') >= r[0]) & (pd.to_numeric(filtered[col_jornada], errors='coerce') <= r[1])]
        except Exception:
            pass

    if col_linea and col_linea in df.columns:
        try:
            min_l, max_l = int(pd.to_numeric(filtered[col_linea], errors='coerce').min()), int(pd.to_numeric(filtered[col_linea], errors='coerce').max())
            r2 = st.sidebar.slider("Rango de Líneas", min_value=min_l, max_value=max_l, value=(min_l, max_l))
            filtered = filtered[(pd.to_numeric(filtered[col_linea], errors='coerce') >= r2[0]) & (pd.to_numeric(filtered[col_linea], errors='coerce') <= r2[1])]
        except Exception:
            pass

    st.divider()
    # KPIs
    st.subheader("📌 Indicadores Clave (KPI)")
    c1, c2, c3, c4, c5 = st.columns(5)

    total_rows = len(filtered)
    kpi_card("Registros", f"{total_rows:,}", "Filas después de filtros", c1)

    if col_puntos and col_puntos in filtered.columns:
        puntos_total = pd.to_numeric(filtered[col_puntos], errors='coerce').fillna(0).sum()
        kpi_card("Puntos totales", f"{puntos_total:,.0f}", cols=c2)
        juegos = filtered.shape[0]
        kpi_card("Puntos por juego", f"{(puntos_total / juegos) if juegos else 0:,.2f}", cols=c3)
    else:
        kpi_card("Puntos totales", "—", cols=c2)
        kpi_card("Puntos por juego", "—", cols=c3)

    # Pines con Handicap (si existen Score y Handicap)
    col_pines_hcp = None
    if col_score and col_score in filtered.columns and col_handicap and col_handicap in filtered.columns:
        tmp_h = filtered[[col_score, col_handicap]].copy()
        tmp_h[col_score] = pd.to_numeric(tmp_h[col_score], errors='coerce').fillna(0)
        tmp_h[col_handicap] = pd.to_numeric(tmp_h[col_handicap], errors='coerce').fillna(0)
        pines_hcp_series = tmp_h[col_score] + tmp_h[col_handicap]
        col_pines_hcp = "__PINES_HCP__"
        filtered[col_pines_hcp] = pines_hcp_series
        kpi_card("Promedio con handicap", f"{pines_hcp_series.mean():,.2f}")
        kpi_card("Mejor con handicap", f"{pines_hcp_series.max():,.2f}")
        # Toggle solo si existe handicap
        with st.sidebar:
            use_hcp = st.toggle("Usar Handicap (global)", value=False, help="Aplica Handicap a estadísticas, rankings y tendencias por jugador/equipo.")

    if col_jugador and col_jugador in filtered.columns:
        kpi_card("Jugadores únicos", f"{filtered[col_jugador].nunique():,}", cols=c4)
    else:
        kpi_card("Jugadores únicos", "—", cols=c4)

    if col_equipo and col_equipo in filtered.columns:
        kpi_card("Equipos únicos", f"{filtered[col_equipo].nunique():,}", cols=c5)
    else:
        kpi_card("Equipos únicos", "—", cols=c5)

    # KPIs adicionales: juegos altos (>=200/225/250) según métrica activa
    if col_score and col_score in filtered.columns:
        base_col = col_pines_hcp if ("__PINES_HCP__" in filtered.columns and 'use_hcp' in locals() and use_hcp) else col_score
        base_vals = pd.to_numeric(filtered[base_col], errors='coerce')
        c6, c7, c8 = st.columns(3)
        k200 = int((base_vals >= 200).sum())
        k225 = int((base_vals >= 225).sum())
        k250 = int((base_vals >= 250).sum())
        kpi_card("Líneas ≥200", f"{k200:,}", cols=c6)
        kpi_card("Líneas ≥225", f"{k225:,}", cols=c7)
        kpi_card("Líneas ≥250", f"{k250:,}", cols=c8)
        
        # Percentiles y estadísticas avanzadas
        st.subheader("📊 Estadísticas Avanzadas")
        p_cols = st.columns(4)
        p25, p50, p75, p90 = base_vals.quantile([0.25, 0.50, 0.75, 0.90])
        std_val = base_vals.std()
        kpi_card("P25", f"{p25:.2f}", cols=p_cols[0])
        kpi_card("P50 (Mediana)", f"{p50:.2f}", cols=p_cols[1])
        kpi_card("P75", f"{p75:.2f}", cols=p_cols[2])
        kpi_card("P90", f"{p90:.2f}", cols=p_cols[3])
        
        # Desviación estándar y outliers
        iqr = p75 - p25
        outliers_low = base_vals < (p25 - 1.5 * iqr)
        outliers_high = base_vals > (p75 + 1.5 * iqr)
        total_outliers = outliers_low.sum() + outliers_high.sum()
        
        o_cols = st.columns(2)
        kpi_card("Desv. Estándar", f"{std_val:.2f}", cols=o_cols[0])
        kpi_card("Outliers (IQR)", f"{total_outliers:,}", cols=o_cols[1])

    # Alertas dinámicas
    st.subheader("🚨 Alertas y Rachas")
    if col_jugador and col_score and col_score in filtered.columns:
        # Detectar rachas de mejora
        if col_jornada and col_jornada in filtered.columns:
            recent_data = (
                filtered.assign(_j=pd.to_numeric(filtered[col_jornada], errors='coerce'))
                .dropna(subset=["_j"])
                .sort_values([col_jugador, "_j"])
            )
            alerts = []
            for jugador in recent_data[col_jugador].unique():
                player_data = recent_data[recent_data[col_jugador] == jugador]
                if len(player_data) >= 3:
                    last_3 = player_data.tail(3)[col_score].astype(float)
                    if last_3.is_monotonic_increasing:
                        alerts.append(f"📈 {jugador}: Racha ascendente (últimas 3 jornadas)")
                    elif (last_3 >= 200).sum() >= 2:
                        alerts.append(f"🔥 {jugador}: 2+ juegos de 200+ en últimas 3 jornadas")
            
            if alerts:
                for alert in alerts[:5]:  # Mostrar máximo 5
                    st.success(alert)
            else:
                st.info("No hay alertas de rachas detectadas")
    
    st.divider()
    # Insights automáticos
    st.subheader("🧠 Insights automáticos")
    insights = generate_insights(
        filtered,
        col_jugador=col_jugador,
        col_equipo=col_equipo,
        col_jornada=col_jornada,
        col_linea=col_linea,
        col_score=col_score,
        col_handicap=col_handicap,
        use_hcp=use_hcp,
    )
    for txt in insights:
        st.markdown(f"- {txt}")

    # Destacados con mini-gráficos
    metric_col = col_pines_hcp if (use_hcp and col_pines_hcp in filtered.columns) else col_score
    st.subheader("🌟 Destacados")
    h = compute_highlights(filtered, col_jugador=col_jugador, col_jornada=col_jornada, metric_col=metric_col)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown("**🏆 Mejor promedio**")
        if h["best_avg_player"] is not None:
            st.metric(h["best_avg_player"], f"{h['best_avg_value']:.2f}")
            if h["best_avg_spark"] is not None:
                st.plotly_chart(h["best_avg_spark"])
        else:
            st.caption("Sin datos")
    with d2:
        st.markdown("**🧩 Más consistente (CV)**")
        if h["most_consistent_player"] is not None:
            st.metric(h["most_consistent_player"], f"CV {h['most_consistent_cv']:.2f}")
            if h["most_consistent_spark"] is not None:
                st.plotly_chart(h["most_consistent_spark"])
        else:
            st.caption("Sin datos")
    with d3:
        st.markdown("**💯 Más juegos ≥200**")
        if h["most_200_player"] is not None:
            st.metric(h["most_200_player"], f"{h['most_200_count']}")
        else:
            st.caption("Sin datos")
    
    # Distribución de scores
    if h["score_distribution"] is not None:
        st.markdown("**📈 Distribución de Scores**")
        st.plotly_chart(h["score_distribution"])

    st.divider()
    # Métricas aprobadas: usar PUNTOS (score) para promedio, desviación, min, max
    st.subheader("👤 Estadísticas por jugador")
    metric_name = "Score" if not use_hcp or not col_pines_hcp else "Score + Handicap"
    st.caption(f"Se calculan sobre: {metric_name}. Si hay Handicap, también se muestra comparativa.")

    if col_score and col_score in filtered.columns:
        kpi_card("Mejor línea", f"{filtered[col_score].max():,.2f}", cols=c3)
        kpi_card("Promedio total", f"{filtered[col_score].mean():,.2f}", cols=c4)

    if col_jugador and col_jugador in filtered.columns:
        target_col = col_pines_hcp if (use_hcp and col_pines_hcp in filtered.columns) else col_score
        tmp_sc = filtered[[col_jugador, target_col]].copy()
        tmp_sc[target_col] = pd.to_numeric(tmp_sc[target_col], errors='coerce')
        stats_jugador = (
            tmp_sc.groupby(col_jugador)[target_col]
            .agg(Promedio="mean", Desviacion=lambda s: s.std(ddof=0), Min="min", Max="max", Juegos="count")
            .reset_index()
            .sort_values("Promedio", ascending=False)
        )
    st.divider()
    # Rankings (solo Promedios)
    st.subheader("📊 Rankings")
    agg_options = []
    if col_puntos and col_puntos in filtered.columns:
        agg_options.append(("Promedio de Puntos", col_puntos, "mean"))
    if col_score and col_score in filtered.columns:
        agg_options.append(("Promedio Score", col_score, "mean"))
    if col_pines_hcp and col_pines_hcp in filtered.columns:
        agg_options.append(("Promedio con Handicap", col_pines_hcp, "mean"))

    # Dimensión de ranking: restringido a Jugador (no hacer rankings por Equipo con PTOS_GAN)
    rank_dimension = col_jugador if col_jugador else None

    if rank_dimension and agg_options:
        label, coln, func = st.selectbox(
            "Métrica de ranking",
            options=agg_options,
            format_func=lambda x: x[0],
        )
        topn = st.slider("Top N", 5, 50, 10)
        min_games = st.slider("Mín. juegos", 1, 30, 6)
        desc = st.checkbox("Orden descendente", value=True)
        # Promedio + conteo de juegos por jugador
        agg_series = filtered.groupby(rank_dimension)[coln].agg(func).rename("Valor")
        counts = filtered.groupby(rank_dimension).size().rename("Juegos")
        rank_df = (
            pd.concat([agg_series, counts], axis=1)
            .dropna(subset=["Valor"])  # por seguridad
        )
        # Filtrar por mínimo de juegos
        rank_df = rank_df[rank_df["Juegos"] >= min_games]
        # Ordenar y recortar
        rank_df = rank_df.sort_values("Valor", ascending=not desc).head(topn).reset_index()
        # Barras coloreadas por valor con escala agradable
        scale = "Turbo" if theme == "Oscuro" else "Blues"
        fig = px.bar(
            rank_df,
            x=rank_dimension,
            y="Valor",
            title=f"Top {topn} por {label}",
            color="Valor",
            color_continuous_scale=scale,
            text_auto=True,
        )
        fig.update_layout(xaxis_title=rank_dimension.title(), yaxis_title=label)
        fig.update_traces(hovertemplate="<b>%{x}</b><br>Valor: %{y:.2f}<extra></extra>", texttemplate="%{y:.2f}")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig)
        with st.expander("Ver tabla de ranking", expanded=False):
            df_rank_disp = rank_df[[rank_dimension, "Valor", "Juegos"]].copy()
            df_rank_disp["Valor"] = pd.to_numeric(df_rank_disp["Valor"], errors='coerce').round(2)
            st.dataframe(df_rank_disp, height=400)
    else:
        st.info("Seleccione al menos una dimensión (Jugador/Equipo) y una métrica para generar ranking.")

    st.divider()
    # Tendencias
    st.subheader("📈 Tendencias")
    if col_jornada and (col_score and col_score in filtered.columns):
        # Tendencias: usar Score o Score+HCP según toggle; NO usar PTOS_GAN
        metric_col = col_pines_hcp if (use_hcp and col_pines_hcp in filtered.columns) else col_score
        dim = st.radio("Agrupar por", options=[opt for opt in [col_equipo, col_jugador] if opt], horizontal=True)
        tmp = (
            filtered
            .assign(_j=pd.to_numeric(filtered[col_jornada], errors='coerce'))
            .dropna(subset=["_j"])
            .groupby(["_j", dim])[metric_col]
            .mean()
            .reset_index()
        )
        fig2 = px.line(
            tmp,
            x="_j",
            y=metric_col,
            color=dim,
            markers=True,
            title=f"Promedio por Jornada ({'Score+HCP' if metric_col==col_pines_hcp else 'Score'})",
            color_discrete_sequence=COLORWAY,
        )
        fig2.update_layout(xaxis_title="Jornada", yaxis_title="Promedio")
        fig2.update_traces(hovertemplate="Jornada %{x}<br>Promedio: %{y:.2f}<br>%{fullData.name}<extra></extra>")
        st.plotly_chart(fig2)
        with st.expander("Ver datos de tendencia", expanded=False):
            tmp_display = tmp.sort_values([dim, "_j"]).copy()
            tmp_display[metric_col] = pd.to_numeric(tmp_display[metric_col], errors='coerce').round(2)
            st.dataframe(tmp_display, height=400)
    else:
        st.info("Para tendencias se requiere 'Jornada' y columna de Score (no se usan Puntos Ganados por equipo).")

    st.divider()
    # Mapa de calor (Equipo vs Jornada)
    st.subheader("🔥 Mapa de calor (Equipo x Jornada)")
    if col_equipo and col_jornada and (col_score and col_score in filtered.columns):
        # Usar Score o Score+HCP según toggle; NO usar PTOS_GAN
        metric_col = col_pines_hcp if (use_hcp and col_pines_hcp in filtered.columns) else col_score
        pivot = (
            filtered.assign(_j=pd.to_numeric(filtered[col_jornada], errors='coerce'))
            .dropna(subset=["_j"]) 
            .pivot_table(index=col_equipo, columns="_j", values=metric_col, aggfunc="mean")
        )
        pivot = pivot.sort_index(axis=1)
        # Heatmap moderno con imshow (con valores en celdas)
        try:
            z = pivot.values.astype(float)
            text_vals = np.round(z, 2)
            fig_hm = px.imshow(
                z,
                x=pivot.columns.astype(str),
                y=pivot.index.astype(str),
                color_continuous_scale="Viridis",
                aspect="auto",
                labels=dict(x="Jornada", y="Equipo", color="Promedio"),
                title=f"Mapa de calor ({'Score+HCP' if metric_col==col_pines_hcp else 'Score'}) por Equipo y Jornada",
            )
            fig_hm.update_traces(text=text_vals, texttemplate="%{text}", textfont_size=12)
            fig_hm.update_coloraxes(showscale=True)
            st.plotly_chart(fig_hm)
        except Exception:
            with st.expander("Ver matriz (tabla)", expanded=False):
                pivot_display = pivot.round(2)
                st.dataframe(pivot_display, height=400)
    else:
        st.info("Requiere 'Equipo', 'Jornada' y columna de Score (no se usan Puntos Ganados por equipo).")

    # Se elimina sección de "Puntos ganados por equipo" para acatar la restricción del usuario.

    st.divider()
    # Comparativa de jugadores
    st.subheader("⚖️ Comparativa de Jugadores")
    if col_jugador and col_score and col_score in filtered.columns:
        # Usar métrica activa según toggle
        comp_metric_col = col_pines_hcp if (use_hcp and col_pines_hcp in filtered.columns) else col_score
        comp_metric_name = "Score+HCP" if comp_metric_col == col_pines_hcp else "Score"
        st.caption(f"Comparando por: {comp_metric_name}")
        
        jugadores_disp = sorted([j for j in filtered[col_jugador].dropna().unique().tolist()])
        if len(jugadores_disp) >= 2:
            comp_cols = st.columns(2)
            with comp_cols[0]:
                j1 = st.selectbox("Jugador 1", options=jugadores_disp, index=0, key="comp1")
            with comp_cols[1]:
                j2 = st.selectbox("Jugador 2", options=jugadores_disp, index=1 if len(jugadores_disp) > 1 else 0, key="comp2")
            
            if j1 != j2:
                data1 = filtered[filtered[col_jugador] == j1][comp_metric_col].astype(float)
                data2 = filtered[filtered[col_jugador] == j2][comp_metric_col].astype(float)
                
                comp_metrics = st.columns(4)
                with comp_metrics[0]:
                    st.metric(f"{j1} - Promedio", f"{data1.mean():.2f}")
                    st.metric(f"{j2} - Promedio", f"{data2.mean():.2f}")
                with comp_metrics[1]:
                    st.metric(f"{j1} - Mejor", f"{data1.max():.2f}")
                    st.metric(f"{j2} - Mejor", f"{data2.max():.2f}")
                with comp_metrics[2]:
                    st.metric(f"{j1} - Juegos", f"{len(data1)}")
                    st.metric(f"{j2} - Juegos", f"{len(data2)}")
                with comp_metrics[3]:
                    st.metric(f"{j1} - ≥200", f"{(data1 >= 200).sum()}")
                    st.metric(f"{j2} - ≥200", f"{(data2 >= 200).sum()}")
                
                # Gráfico comparativo
                if col_jornada and col_jornada in filtered.columns:
                    comp_data = []
                    for j, label in [(j1, "Jugador 1"), (j2, "Jugador 2")]:
                        tmp = (
                            filtered[filtered[col_jugador] == j]
                            .assign(_j=pd.to_numeric(filtered[filtered[col_jugador] == j][col_jornada], errors='coerce'))
                            .dropna(subset=["_j"])
                            .groupby("_j")[comp_metric_col]
                            .mean()
                            .reset_index()
                        )
                        tmp["Jugador"] = j
                        comp_data.append(tmp)
                    
                    if comp_data:
                        comp_df = pd.concat(comp_data, ignore_index=True)
                        fig_comp = px.line(
                            comp_df, x="_j", y=comp_metric_col, color="Jugador",
                            title=f"Comparativa ({comp_metric_name}): {j1} vs {j2}",
                            markers=True,
                            color_discrete_sequence=COLORWAY[:2]
                        )
                        fig_comp.update_layout(xaxis_title="Jornada", yaxis_title=f"Promedio ({comp_metric_name})")
                        st.plotly_chart(fig_comp)
        else:
            st.info("Se necesitan al menos 2 jugadores para comparar")
    
    # Se eliminó la sección "Enfrentamientos del jugador" ya que el archivo no contiene columnas de oponente.
    # Se eliminó la exportación de datos (CSV/XLSX) por solicitud del usuario.


if __name__ == "__main__":
    main()

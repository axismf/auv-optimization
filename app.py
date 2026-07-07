"""Interfaz web del planificador de rutas (RF-06, RF-07, RF-08, RF-09).

Capa de presentación construida con Streamlit. Solo orquesta los módulos del
núcleo (no contiene lógica de algoritmos), de modo que la UI pueda cambiarse
sin tocar el core.

Ejecutar con:
    streamlit run app.py
"""
from __future__ import annotations

import json
import re

from dependencias import *

from src.config import ParametrosModelo
from src.datos import CampoCorrientes, cargar_corrientes, _ALIAS
from src.grafo import construir_grafo
from src.zonas import (
    divergencia,
    seleccionar_waypoints,
    seleccionar_centinelas,
    celda_mas_cercana,
    agregar_puntos_fijos,
)
from src.algoritmos import (
    matriz_costos,
    matriz_costos_sin_corrientes,
    atsp_fuerza_bruta,
    ensamblar_ruta,
    bellman_ford,
    hay_ciclo_negativo,
)
from src.metricas import resumen_mision, estado_bateria, exportar_csv
from src.visualizacion import (
    plot_campo, plot_divergencia, plot_zonas, plot_ruta, plot_3d, plot_bateria,
    plot_grafo_costos, plot_tours_atsp, plot_comparativa_algoritmos, plot_grafo_3d,
)


# ── Constantes ────────────────────────────────────────────────────────────────
_LAT_CALLAO    = -12.05
_LON_CALLAO    = -77.15
_LAT_CHANCAY   = -11.5903   # 11°35′25″S
_LON_CHANCAY   = -77.2761   # 77°16′34″O
_DATA_DIR      = pathlib.Path(__file__).parent / "data"

_FASES_NOMBRES = ["Datos", "Corrientes", "Zonas", "Grafo", "ATSP", "Misión"]

# ── Bases predefinidas en zonas costeras del Perú ──────────────────────────────
_BASES_PREDEFINIDAS: list[dict] = [
    {
        "nombre":    "Callao (Lima)",
        "lat":       -12.05,
        "lon":       -77.15,
        "desc":      "Principal puerto del Perú. 4to más importante de Latinoamérica.",
        "region":    "Costa Centro",
    },
    {
        "nombre":    "Chancay",
        "lat":       -11.57,
        "lon":       -77.27,
        "desc":      "Puerto en expansión. Nuevo hub logístico para Asia-Pacífico.",
        "region":    "Costa Centro-Norte",
    },
    {
        "nombre":    "Paita (Piura)",
        "lat":       -5.09,
        "lon":       -81.12,
        "desc":      "2do puerto en contenedores. Exportaciones agrícolas e hidrobiológicos.",
        "region":    "Costa Norte",
    },
    {
        "nombre":    "Chimbote (Áncash)",
        "lat":       -9.08,
        "lon":       -78.61,
        "desc":      "Puerto pesquero. Principal centro de producción de harina de pescado.",
        "region":    "Costa Centro-Norte",
    },
    {
        "nombre":    "Salaverry (La Libertad)",
        "lat":       -8.22,
        "lon":       -78.97,
        "desc":      "Puerto comercial y pesquero. Cerca de Trujillo.",
        "region":    "Costa Norte-Centro",
    },
    {
        "nombre":    "Pisco (Ica)",
        "lat":       -13.70,
        "lon":       -76.17,
        "desc":      "Puerto LNG Melchorita. Exportaciones de gas natural licuado.",
        "region":    "Costa Sur-Centro",
    },
    {
        "nombre":    "Ilo (Moquegua)",
        "lat":       -17.64,
        "lon":       -71.33,
        "desc":      "Puerto del sur. Conecta con Chile y Bolivia.",
        "region":    "Costa Sur",
    },
    {
        "nombre":    "Matarani (Arequipa)",
        "lat":       -17.00,
        "lon":       -72.11,
        "desc":      "Puerto minero. Exportaciones de minerales y fertilizantes.",
        "region":    "Costa Sur",
    },
]

# ── Presets de drones predefinidos ─────────────────────────────────────────────
# Basados en especificaciones reales de la industria
_DRONE_PRESETS: list[dict] = [
    {
        "nombre":  "REMUS 100",
        "s":       1.0,        # m/s — velocidad típica de trabajo
        "eta":     0.30,
        "k_p":     18.0,       # calibrado con REMUS 100 real (~18 kJ/km)
        "k_r":     1.0,
        "e_max":   3_600_000,  # 1 kWh = 3.6 MJ
        "pct_ini": 100,
        "m":       37.0,       # kg
        "C_d":     1.24,       # efectivo (incluye fricción + apéndices)
        "desc":    "AUV estándar de la industria. Ø19cm, 37kg, batería 1kWh. Autonomía ~200km.",
    },
    {
        "nombre":  "REMUS 600",
        "s":       1.5,        # m/s
        "eta":     0.30,
        "k_p":     77.5,       # Ø33cm, calibrado
        "k_r":     1.0,
        "e_max":   10_800_000, # 3 kWh
        "pct_ini": 100,
        "m":       240.0,      # kg
        "C_d":     1.09,       # efectivo
        "desc":    "AUV mediano. Ø33cm, 240kg, batería 3kWh, autonomía 24h.",
    },
    {
        "nombre":  "REMUS 620",
        "s":       0.5,
        "eta":     0.30,
        "k_p":     0.4,
        "k_r":     18.0,
        "e_max":   10_800_000, # 3 kWh
        "pct_ini": 100,
        "m":       240.0,      # kg
        "C_d":     1.09,       # efectivo
        "desc":    "AUV mediano. Ø33cm, 240kg, batería 3kWh, autonomía 24h.",
    },
    {
        "nombre":  "Bluefin-9",
        "s":       1.0,
        "eta":     0.30,
        "k_p":     37.2,       # Ø23cm, calibrado
        "k_r":     1.0,
        "e_max":   5_400_000,  # 1.5 kWh
        "pct_ini": 100,
        "m":       120.0,      # kg
        "C_d":     1.18,       # efectivo
        "desc":    "AUV militar. Ø23cm, 120kg, batería 1.5kWh.",
    },
    {
        "nombre":  "AUV Genérico (20cm)",
        "s":       0.5,
        "eta":     0.30,
        "k_p":     24.8,       # calibrado
        "k_r":     1.0,
        "e_max":   1_000_000,  # 1 MJ
        "pct_ini": 100,
        "m":       100.0,
        "C_d":     1.55,       # efectivo
        "desc":    "Configuración genérica para prototipos.",
    },
    {
        "nombre":  "Drone Prueba",
        "s":       0.25,       # m/s — casi igual a la corriente → vr pequeño → arrastre mínimo
        "eta":     0.85,       # alta eficiencia para maximizar regeneración
        "k_p":     2.0,        # arrastre bajo → e_drag pequeño
        "k_r":     5.0,        # regeneración alta → e_regen > e_drag → pesos negativos
        "e_max":   500_000,    # 0.5 MJ
        "pct_ini": 100,
        "m":       5.0,
        "C_d":     0.80,
        "desc":    "Preset de prueba para forzar aristas con peso negativo (regeneración > arrastre).",
    },
]

_SVG_AUV = (
    '<svg viewBox="0 0 220 80" xmlns="http://www.w3.org/2000/svg">'
    '<ellipse cx="108" cy="40" rx="88" ry="20" fill="#2E8B9E"/>'
    '<path d="M196,40 Q220,28 217,40 Q220,52 196,40" fill="#1a6b7e"/>'
    '<ellipse cx="22" cy="40" rx="12" ry="20" fill="#1a6b7e"/>'
    '<path d="M26,34 L6,18 L18,34" fill="#1a6b7e"/>'
    '<path d="M26,46 L6,62 L18,46" fill="#1a6b7e"/>'
    '<path d="M80,21 L90,5 L100,21" fill="#1a6b7e"/>'
    '<circle cx="155" cy="34" r="7" fill="#7ec8e3" stroke="#1a6b7e" stroke-width="1.5"/>'
    '<ellipse cx="10" cy="40" rx="3" ry="12" fill="none" stroke="#d0d0d0" stroke-width="1.8"/>'
    '<line x1="10" y1="28" x2="10" y2="52" stroke="#d0d0d0" stroke-width="1.8"/>'
    '<line x1="2" y1="40" x2="18" y2="40" stroke="#d0d0d0" stroke-width="1.5"/>'
    '<rect x="95" y="16" width="3" height="8" fill="#b0b0b0" rx="1"/>'
    '</svg>'
)

_ASSETS_DRONES = pathlib.Path(__file__).parent / "assets" / "drones"
_ASSETS_DRONES.mkdir(parents=True, exist_ok=True)

_IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "svg": "image/svg+xml", "webp": "image/webp"}


def _drone_img_path(nombre: str) -> pathlib.Path | None:
    slug = re.sub(r"[^\w\-]", "_", nombre.strip().lower())
    for ext in _IMG_MIME:
        p = _ASSETS_DRONES / f"{slug}.{ext}"
        if p.exists():
            return p
    return None


_ESTILOS = """
<style>
/* ═══════════════════════════════════════════════════════════════
   INDUSTRIAL MARITIME — DEEP NAVY THEME
   Palette: #040C18 / #081426 / #0A1830 (navy bg layers)
            #FFB000 (industrial amber), #2A7F9F (maritime teal)
            #C5D5E8 (steel white), #7A94B0 (muted steel)
            #1A3050 (border navy)
   ═══════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

html, body, .stApp {
    background-color: #040C18 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
}

* { font-size: 13px !important; }

.stMarkdown, .stText, .stCaption, .stMetric,
.stAlert, .stInfo, .stSuccess, .stWarning, .stError,
p, span, label, div[data-testid="stMetricValue"],
div[data-testid="stMetricLabel"], .stDataFrame,
section[data-testid="stSidebar"] * {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
}

/* ─── Sidebar ───────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background-color: #040C18 !important;
    padding: 4px 0 4px 4px !important;
}
section[data-testid="stSidebar"] > div:first-child {
    background-color: #060F1E !important;
    border-radius: 8px !important;
    border-right: 1px solid #1A3050 !important;
    box-shadow: 0 10px 15px -3px rgba(0,0,0,.6),
                0 4px  6px -4px rgba(0,0,0,.4) !important;
    min-height: calc(100vh - 8px) !important;
    overflow: hidden;
}

/* ─── Main area ─────────────────────────────────────────────── */
section[data-testid="stMain"] {
    background-color: #040C18 !important;
    padding: 4px 4px 4px 0 !important;
}
.main .block-container {
    background-color: #0A1830 !important;
    border-radius: 8px !important;
    border: 1px solid #1A3050 !important;
    box-shadow: 0 10px 25px rgba(0,0,0,.5),
                inset 0 1px 0 rgba(42,127,159,.08) !important;
    padding: 1.5rem 2rem 2.5rem !important;
    max-width: 1400px !important;
    margin: 0 auto !important;
    min-height: calc(100vh - 8px) !important;
}

header[data-testid="stHeader"] { background-color: transparent !important; }

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR NAV
   ═══════════════════════════════════════════════════════════════ */
.nav-terminal-active {
    display:        flex;
    align-items:    center;
    gap:            6px;
    padding:        .38rem .65rem;
    border-left:    2px solid #FFB000;
    color:          #FFB000;
    font-family:    'JetBrains Mono', monospace;
    font-size:      13px;
    font-weight:    700;
    letter-spacing: .08em;
    margin:         2px 0;
}
.nav-terminal-done {
    display:     flex;
    align-items: center;
    padding:     .38rem .65rem;
    border-left: 2px solid #1A3050;
    color:       #3A5878;
    font-family: 'JetBrains Mono', monospace;
    font-size:   13px;
    margin:      2px 0;
}
.nav-terminal-locked {
    display:     flex;
    align-items: center;
    padding:     .38rem .65rem;
    border-left: 2px solid transparent;
    color:       #3A5878;
    font-family: 'JetBrains Mono', monospace;
    font-size:   13px;
    margin:      2px 0;
}

/* ═══════════════════════════════════════════════════════════════
   TERMINAL HEADER + STATUS BAR
   ═══════════════════════════════════════════════════════════════ */
.terminal-header {
    font-family:    'JetBrains Mono', monospace;
    color:          #FFB000;
    font-size:      13px;
    font-weight:    700;
    letter-spacing: .05em;
    padding:        .4rem 0 .8rem;
    border-bottom:  1px solid #1A3050;
    margin-bottom:  1rem;
    white-space:    pre;
}
.status-bar {
    display:     flex;
    align-items: center;
    gap:         .6rem;
    padding:     .35rem 0 .9rem;
    font-family: 'JetBrains Mono', monospace;
    font-size:   13px;
    color:       #7A94B0;
}
.status-dot {
    width:         8px;
    height:        8px;
    border-radius: 50%;
    background:    #FFB000;
    flex-shrink:   0;
    animation:     blink 1.2s step-start infinite;
}
@keyframes blink {
    0%,100% { opacity: 1; }
    50%     { opacity: 0; }
}

/* ═══════════════════════════════════════════════════════════════
   STEPPER
   ═══════════════════════════════════════════════════════════════ */
.stepper-wrap {
    display:     flex;
    align-items: flex-start;
    margin:      0 0 1.4rem;
    padding:     .8rem 0 .4rem;
    overflow:    hidden;
}
.step-item {
    display:        flex;
    flex-direction: column;
    align-items:    center;
    flex-shrink:    0;
    min-width:      54px;
}
.step-connector {
    flex:       1;
    height:     2px;
    background: rgba(26,48,80,.8);
    align-self: flex-start;
    margin-top: 12px;
    min-width:  6px;
}
.step-circle {
    width:           26px;
    height:          26px;
    border-radius:   50%;
    display:         flex;
    align-items:     center;
    justify-content: center;
    font-weight:     700;
    font-size:       12px;
    flex-shrink:     0;
}
.step-done   .step-circle { background: #FFB000; color: #040C18; }
.step-active .step-circle {
    background: #FFB000; color: #040C18;
    box-shadow: 0 0 0 4px rgba(255,176,0,.25);
}
.step-locked .step-circle {
    background: rgba(26,48,80,.6);
    color:      #3A5878;
    border:     1px solid #1A3050;
}
.step-label {
    margin-top:  .3rem;
    font-size:   11px;
    text-align:  center;
    max-width:   54px;
    line-height: 1.2;
}
.step-done   .step-label { color: #3A5878; }
.step-active .step-label { color: #FFB000; font-weight: 700; }
.step-locked .step-label { color: #3A5878; }

/* ═══════════════════════════════════════════════════════════════
   FASE BADGE
   ═══════════════════════════════════════════════════════════════ */
.fase-badge {
    font-size:     .7rem;
    font-weight:   600;
    background:    rgba(255,176,0,.08);
    color:         #FFB000;
    border:        1px solid rgba(255,176,0,.3);
    padding:       .18rem .55rem;
    border-radius: 999px;
    white-space:   nowrap;
}

/* ═══════════════════════════════════════════════════════════════
   CARDS / CONTAINERS (islands)
   ═══════════════════════════════════════════════════════════════ */
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-color:     #1E3A5C !important;
    background-color: rgba(8, 18, 36, 0.78) !important;
    border-radius:    8px !important;
    border-width:     1px !important;
    box-shadow:       0 4px 16px rgba(0,0,0,.35),
                      inset 0 1px 0 rgba(42,127,159,.06) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div > div:first-child .stMarkdown p strong {
    color:          #FFB000 !important;
    letter-spacing: 0.07em;
    font-size:      11px !important;
}
div[data-testid="stMetric"] {
    padding-left: 1rem !important;
}

/* ─── Metric boxes ──────────────────────────────────────────── */
.stMetric {
    border:     1px solid #1A3050 !important;
    border-radius: 8px !important;
    background: rgba(6, 14, 28, 0.7) !important;
}
.stMetric [data-testid="stMetricValue"] {
    color:     #FFB000 !important;
    font-size: 14px !important;
}
.stMetric [data-testid="stMetricLabel"] {
    color:     #7A94B0 !important;
    font-size: 12px !important;
}

/* ═══════════════════════════════════════════════════════════════
   TEXT
   ═══════════════════════════════════════════════════════════════ */
.stMarkdown p, .stMarkdown div, .stMarkdown span {
    color: #C5D5E8 !important;
}
.stMarkdown strong, .stMarkdown b {
    color: #FFB000 !important;
}
.stMarkdown code {
    background:    rgba(26,48,80,.35) !important;
    border:        1px solid #1A3050 !important;
    border-radius: 4px !important;
    padding:       2px 6px !important;
    color:         #A8C4E0 !important;
}

.stCaption {
    color:     #4A6A8A !important;
    font-size: 11px !important;
}

/* ═══════════════════════════════════════════════════════════════
   INPUTS
   ═══════════════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div > select {
    background: #060E1C !important;
    color:      #C5D5E8 !important;
    border:     1px solid #1A3050 !important;
    font-size:  13px !important;
}
.stSlider > div > div > div > div {
    background: #060E1C !important;
    border:     1px solid #1A3050 !important;
}
.stSlider [data-testid="stSliderValue"] {
    font-size: 13px !important;
    color:     #C5D5E8 !important;
}

/* ═══════════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════════ */
.stButton > button, .stDownloadButton > button {
    border-radius:    8px !important;
    font-family:      'JetBrains Mono', monospace !important;
    font-size:        13px !important;
    font-weight:      600 !important;
    letter-spacing:   .2px !important;
    padding:          .5rem 1.1rem !important;
    transition:       all .15s ease !important;
    background-color: rgba(26,48,80,.5) !important;
    color:            #C5D5E8 !important;
    border:           1px solid #1E3A5C !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background-color: rgba(42,127,159,.18) !important;
    border-color:     #2A7F9F !important;
    color:            #FFB000 !important;
    transform:        translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: rgba(255,176,0,.12) !important;
    color:      #FFB000 !important;
    border:     1px solid rgba(255,176,0,.4) !important;
}
.stButton > button[kind="primary"]:hover {
    background:   rgba(255,176,0,.22) !important;
    border-color: #FFB000 !important;
    color:        #FFD060 !important;
}

/* ═══════════════════════════════════════════════════════════════
   ALERTS / INFO BOXES
   ═══════════════════════════════════════════════════════════════ */
.stAlert {
    border:        1px solid #1A3050 !important;
    border-radius: 8px !important;
    background:    rgba(6,14,28,.6) !important;
    font-size:     13px !important;
}

/* ═══════════════════════════════════════════════════════════════
   EXPANDER
   ═══════════════════════════════════════════════════════════════ */
.stExpander {
    border:        1px solid #1A3050 !important;
    border-radius: 8px !important;
    background:    rgba(6,14,28,.4) !important;
}
.stExpander header { font-size: 13px !important; }

/* ═══════════════════════════════════════════════════════════════
   DATAFRAME
   ═══════════════════════════════════════════════════════════════ */
.stDataFrame {
    color:     #C5D5E8 !important;
    border:    1px solid #1A3050 !important;
    font-size: 12px !important;
}
.stDataFrame th {
    background: rgba(26,48,80,.5) !important;
    color:      #FFB000 !important;
    border:     1px solid #1A3050 !important;
    font-size:  12px !important;
}
.stDataFrame td {
    border:    1px solid #0E2040 !important;
    color:     #C5D5E8 !important;
    font-size: 12px !important;
}

/* ═══════════════════════════════════════════════════════════════
   MISC
   ═══════════════════════════════════════════════════════════════ */
.capa-label {
    text-align:    center;
    padding:       .35rem .5rem;
    background:    rgba(26,48,80,.4);
    border:        1px solid #1A3050;
    border-radius: 6px;
    font-size:     .9rem;
}
hr { border-color: #1A3050 !important; }

/* ═══════════════════════════════════════════════════════════════
   IMAGES / PLOTS
   ═══════════════════════════════════════════════════════════════ */
.stImage > img, div[data-testid="stImage"] > img, .main img {
    max-width: 900px !important;
    width:     auto !important;
    height:    auto !important;
    margin:    0 auto !important;
    display:   block !important;
}
div[data-testid="stImage"] {
    max-width: 900px !important;
    margin:    0 auto !important;
}

/* ═══════════════════════════════════════════════════════════════
   ANIMATIONS
   ═══════════════════════════════════════════════════════════════ */
@keyframes slideRight {
    from { opacity: 0; transform: translateX(30px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideLeft {
    from { opacity: 0; transform: translateX(-30px); }
    to   { opacity: 1; transform: translateX(0); }
}
</style>
"""


# ════════════════════════════════════════════════════════════════
#  DECLARACIONES
# ════════════════════════════════════════════════════════════════

# ── Session state ─────────────────────────────────────────────────────────────
# (declared inline below)

# ── Helpers de renderizado ────────────────────────────────────────────────────
# (declared inline below)
# ── Shared helpers ────────────────────────────────────────────────────────────
def _build_etiquetas(todos, wps, cent, base_nodo) -> dict:
    """Build a label dict mapping each zone node to a short string ID."""
    etiq: dict = {}
    for nodo in todos:
        if nodo == base_nodo:
            etiq[nodo] = "BASE"
        elif nodo in wps:
            etiq[nodo] = f"C{wps.index(nodo)+1:02d}"
        elif nodo in cent:
            etiq[nodo] = f"S{cent.index(nodo)+1:02d}"
        else:
            etiq[nodo] = f"Z{todos.index(nodo)}"
    return etiq


def _build_etiquetas_list(todos, etiq_dict) -> list:
    """Return labels in todos order as a flat list."""
    return [etiq_dict[n] for n in todos]


def _calcular_tramos(orden, caminos, etiq_list, M, speed_ms) -> list:
    """Return list of dicts per tramo: De, →, Dist (km), Tiempo (h), Costo (J).

    etiq_list: list[str] indexed by zone int (same order as todos).
    """
    campo   = st.session_state.campo
    lat_rad = math.radians(float(campo.lat.mean()))
    tramos  = []
    for k in range(len(orden) - 1):
        i, j = orden[k], orden[k + 1]
        path  = caminos.get((i, j), [])
        dist_m = 0.0
        for (_, i0, j0), (_, i1, j1) in zip(path, path[1:]):
            dist_m += math.hypot(
                (campo.lon[j1] - campo.lon[j0]) * GRADOS_A_METROS * math.cos(lat_rad),
                (campo.lat[i1] - campo.lat[i0]) * GRADOS_A_METROS,
            )
        tramos.append({
            "De":         etiq_list[i] if i < len(etiq_list) else f"N{i}",
            "→":          etiq_list[j] if j < len(etiq_list) else f"N{j}",
            "Dist (km)":  f"{dist_m / 1000:.1f}",
            "Tiempo (h)": f"{dist_m / max(speed_ms, 0.01) / 3600:.1f}",
            "Costo (J)":  f"{float(M[i, j]):.1f}",
        })
    return tramos


def _render_volver(fase_destino: int, key: str) -> None:
    """Botón para retroceder a una fase anterior sin perder el progreso ya calculado."""
    if st.button(f"◀  Volver a Fase {fase_destino}", key=key, use_container_width=True):
        st.session_state.nav_direction = "left"
        st.session_state.fase_actual   = fase_destino
        st.rerun()


def _render_status_bar(estado: str) -> None:
    """Render an amber blinking status bar with the given text."""
    st.markdown(
        f'<div class="status-bar">'
        f'<span class="status-dot"></span>'
        f'<span>{estado}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════
#  IMPLEMENTACIONES
# ════════════════════════════════════════════════════════════════

# ── Session state ─────────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict = {
        "fase_actual":   1,
        "campo":         None,
        "nc_path":       None,
        "capa_preview":  0,
        # Fase 2
        "div":           None,
        "dx":            None,
        "dy":            None,
        # Fase 3 — parámetros
        "k_zonas_f3":           6,
        "k_cent_f3":            2,
        "dist_min_f3":          3,
        "bases_personalizadas": [],
        "base_key":             "callao",
        # Fase 3 — resultados
        "wps":        None,
        "cent":       None,
        "base_celda": None,
        "todos":      None,
        "base_nodo":  None,
        "base_idx":   None,
        "firma_zonas_f3": None,
        # Fase 4 — drones (por defecto: REMUS 100 + REMUS 620)
        "drones": [
            {
                "nombre":  _DRONE_PRESETS[0]["nombre"],
                "s":       _DRONE_PRESETS[0]["s"],
                "eta":     _DRONE_PRESETS[0]["eta"],
                "k_p":     _DRONE_PRESETS[0]["k_p"],
                "k_r":     _DRONE_PRESETS[0]["k_r"],
                "e_max":   _DRONE_PRESETS[0]["e_max"],
                "pct_ini": _DRONE_PRESETS[0]["pct_ini"],
            },
            {
                "nombre":  _DRONE_PRESETS[2]["nombre"],
                "s":       _DRONE_PRESETS[2]["s"],
                "eta":     _DRONE_PRESETS[2]["eta"],
                "k_p":     _DRONE_PRESETS[2]["k_p"],
                "k_r":     _DRONE_PRESETS[2]["k_r"],
                "e_max":   _DRONE_PRESETS[2]["e_max"],
                "pct_ini": _DRONE_PRESETS[2]["pct_ini"],
            },
        ],
        "drone_key":       0,
        "abrir_drone_idx": None,
        # Fase 4 — resultados
        "grafo":        None,
        "params_f4":    None,
        "bat_ini_j":    None,
        "hay_ciclo_f4": None,
        # Fase 5 — resultados
        "ruta":      None,
        "orden_f5":  None,
        "costo_f5":  None,
        "M_f5":      None,
        "caminos_f5": None,
        "costo_sin_f5": None,
        # navegación
        "nav_direction": "right",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Helpers de renderizado ────────────────────────────────────────────────────

def _fig_a_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf.read()


def _mostrar_figura(fig: plt.Figure, modo: str = "medio") -> None:
    st.pyplot(fig, use_container_width=True)


@st.cache_data(show_spinner=False)
def _calcular_div(nc_path: str) -> tuple:
    """Calcula divergencia superficial; cacheado por ruta de archivo."""
    campo   = cargar_corrientes(nc_path)
    capa    = 0
    lat_med = math.radians(float(campo.lat.mean()))
    dy      = abs(float(campo.lat[1] - campo.lat[0])) * GRADOS_A_METROS
    dx      = abs(float(campo.lon[1] - campo.lon[0])) * GRADOS_A_METROS * math.cos(lat_med)
    div     = divergencia(campo.uo[capa], campo.vo[capa], dx, dy)
    return div, dx, dy


@st.cache_data(show_spinner=False)
def _cargar_campo(ruta: str) -> CampoCorrientes:
    return cargar_corrientes(ruta)


@st.cache_data(show_spinner=False)
def _leer_metadata_nc(ruta: str) -> dict | None:
    """Lee solo coordenadas del .nc para mostrar en la tarjeta de dataset."""
    try:
        with xr.open_dataset(ruta) as ds:
            disponibles = set(ds.variables) | set(ds.coords)

            def _alias(clave: str) -> str | None:
                for a in _ALIAS[clave]:
                    if a in disponibles:
                        return a
                return None

            n_lat  = _alias("lat")
            n_lon  = _alias("lon")
            n_prof = _alias("prof")
            n_uo   = _alias("uo")
            n_vo   = _alias("vo")
            n_time = _alias("time")

            if not all([n_lat, n_lon, n_prof, n_uo, n_vo]):
                return None

            lat  = ds[n_lat].values.astype(float)
            lon  = ds[n_lon].values.astype(float)
            prof = ds[n_prof].values.astype(float)

            paso_lat_km = abs(float(lat[1] - lat[0])) * 111.32 if len(lat) > 1 else 0.0
            paso_lon_km = (
                abs(float(lon[1] - lon[0])) * 111.32
                * math.cos(math.radians(float(lat.mean())))
                if len(lon) > 1 else 0.0
            )
            paso_km = (paso_lat_km + paso_lon_km) / 2

            fecha_str = ""
            if n_time and n_time in ds:
                try:
                    fecha_str = str(pd.Timestamp(ds[n_time].values[0]).date())
                except Exception:
                    fecha_str = str(ds[n_time].values[0])[:10]

            return {
                "lat_min": float(lat.min()),
                "lat_max": float(lat.max()),
                "lon_min": float(lon.min()),
                "lon_max": float(lon.max()),
                "n_lat":   len(lat),
                "n_lon":   len(lon),
                "n_prof":  len(prof),
                "paso_km": paso_km,
                "fecha":   fecha_str,
                "vars":    [v for v in [n_uo, n_vo] if v],
            }
    except Exception:
        return None


# ── Layout global ─────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    fase = st.session_state.fase_actual
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'JetBrains Mono\',monospace;font-size:.95rem;'
            'font-weight:700;color:#FFB000;letter-spacing:.12em;padding:.5rem 0 .3rem;">'
            '[ AUV-CMD ]</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<hr style="border:none;border-top:1px solid #2A3A3A;margin:.3rem 0 .6rem;"/>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:.68rem;font-weight:600;color:#3A4A4A;'
            'letter-spacing:.1em;font-family:\'JetBrains Mono\',monospace;'
            'margin-bottom:.4rem;">◆ NAV</div>',
            unsafe_allow_html=True,
        )
        for i, nombre in enumerate(_FASES_NOMBRES, start=1):
            label = f"{i:02d} {nombre.upper()}"
            if i < fase:
                st.markdown(
                    f'<div class="nav-terminal-done">✓  {label}</div>',
                    unsafe_allow_html=True,
                )
            elif i == fase:
                st.markdown(
                    f'<div class="nav-terminal-active">●  {label}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="nav-terminal-locked">   {label}</div>',
                    unsafe_allow_html=True,
                )
        st.markdown(
            '<hr style="border:none;border-top:1px solid #2A3A3A;margin:.6rem 0 .4rem;"/>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:.65rem;color:#2A3A3A;font-family:\'JetBrains Mono\',monospace;">'
            'SYS: ONLINE<br/>OP: MANUAL</div>',
            unsafe_allow_html=True,
        )


def _render_stepper() -> None:
    fase   = st.session_state.fase_actual
    partes: list[str] = []
    for i, nombre in enumerate(_FASES_NOMBRES, start=1):
        if i < fase:
            cls, icono = "step-done",   "✓"
        elif i == fase:
            cls, icono = "step-active", str(i)
        else:
            cls, icono = "step-locked", str(i)
        partes.append(
            f'<div class="step-item {cls}">'
            f'  <div class="step-circle">{icono}</div>'
            f'  <div class="step-label">{nombre}</div>'
            f'</div>'
        )
    html = '<div class="step-connector"></div>'.join(partes)
    st.markdown(
        f'<div class="stepper-wrap">{html}</div>',
        unsafe_allow_html=True,
    )


def _carousel_js() -> None:
    direction = st.session_state.get("nav_direction", "right")
    anim      = "slideRight" if direction == "right" else "slideLeft"
    st.markdown(
        f"""
        <script>
        (function(){{
            var c = window.parent.document.querySelector(
                'section[data-testid="stMain"] .block-container');
            if (c) {{
                c.style.animation = 'none';
                void c.offsetHeight;
                c.style.animation = '{anim} 0.32s cubic-bezier(0.22,1,0.36,1)';
            }}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )


def _render_fase_actual() -> None:
    fase   = st.session_state.fase_actual
    nombre = _FASES_NOMBRES[fase - 1] if 1 <= fase <= len(_FASES_NOMBRES) else ""
    ascii_line = "─" * 52
    st.markdown(
        f'<div class="terminal-header">┌─── FASE {fase:02d} ─── {nombre.upper()} {ascii_line}┐</div>',
        unsafe_allow_html=True,
    )
    _carousel_js()
    dispatch = {
        1: _render_contenido_fase1,
        2: _render_contenido_fase2,
        3: _render_contenido_fase3,
        4: _render_contenido_fase4,
        5: _render_contenido_fase5,
        6: _render_contenido_fase6,
    }
    dispatch.get(fase, lambda: st.info("Fase no disponible."))()


# ── Fase 1 — Fuente de datos ──────────────────────────────────────────────────

def _render_contenido_fase1() -> None:
    if st.session_state.nc_path:
        _render_status_bar("DATASET CARGADO  ·  LISTO PARA CONTINUAR")
    else:
        _render_status_bar("EN ESPERA  ·  SELECCIONE UN DATASET")

    st.markdown("`> SELECT DATASET`")

    archivos_nc = sorted(_DATA_DIR.glob("*.nc"))
    n_datasets  = len(archivos_nc)
    n_cols      = min(n_datasets, 3) + 1
    cols        = st.columns(n_cols)

    for idx, nc_path in enumerate(archivos_nc[:3]):
        meta       = _leer_metadata_nc(str(nc_path))
        seleccion  = st.session_state.nc_path == str(nc_path)
        nombre_leg = nc_path.stem.replace("_", " ").title()

        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"**{nombre_leg}**")
                if meta:
                    st.markdown(
                        f"Lat `{meta['lat_min']:.1f}°` → `{meta['lat_max']:.1f}°`  \n"
                        f"Lon `{meta['lon_min']:.1f}°` → `{meta['lon_max']:.1f}°`  \n"
                        f"Grilla **{meta['n_lat']} × {meta['n_lon']}** celdas  \n"
                        f"Paso ≈ **{meta['paso_km']:.1f} km**/celda  \n"
                        f"Capas **{meta['n_prof']}** profundidades  \n"
                        f"Variables {' · '.join(meta['vars'])}"
                        + (f"  \nFecha **{meta['fecha']}**" if meta["fecha"] else "")
                    )
                else:
                    st.caption("No se pudo leer la metadata.")

                btn_label = "Seleccionado" if seleccion else "Seleccionar"
                btn_type  = "primary" if seleccion else "secondary"
                if st.button(
                    btn_label,
                    key=f"sel_{nc_path.stem}",
                    type=btn_type,
                    use_container_width=True,
                ):
                    st.session_state.nc_path      = str(nc_path)
                    st.session_state.campo        = None
                    st.session_state.capa_preview = 0
                    st.rerun()

    with cols[-1]:
        with st.container(border=True):
            st.markdown("**Cargar archivo**")
            uploaded = st.file_uploader(
                "Upload .nc file",
                type=["nc"],
                key="nc_uploader",
                label_visibility="collapsed",
            )
            if uploaded is not None:
                if st.session_state.get("nc_uploaded_name") != uploaded.name:
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".nc", delete=False, prefix="auv_upload_"
                    )
                    tmp.write(uploaded.read())
                    tmp.flush()
                    tmp.close()
                    st.session_state.nc_uploaded_name = uploaded.name
                    st.session_state.nc_path          = tmp.name
                    st.session_state.campo            = None
                    st.session_state.capa_preview     = 0
                    st.rerun()
            st.caption("CMEMS GLOBAL_ANALYSISFORECAST")

    if st.session_state.nc_path:
        _render_dataset_cargado()


def _render_dataset_cargado() -> None:
    nc_path = st.session_state.nc_path

    with st.spinner("Cargando campo de corrientes…"):
        try:
            if st.session_state.campo is None:
                st.session_state.campo = _cargar_campo(nc_path)
            campo = st.session_state.campo
        except Exception as e:
            st.error(f"Error al cargar el archivo: {e}")
            return

    n_prof, n_lat, n_lon = campo.uo.shape
    total   = campo.navegable.size
    agua    = int(campo.navegable.sum())
    lat_med = math.radians(float(campo.lat.mean()))
    paso_lat_km = abs(float(campo.lat[1] - campo.lat[0])) * 111.32 if n_lat > 1 else 0.0
    paso_lon_km = (
        abs(float(campo.lon[1] - campo.lon[0])) * 111.32 * math.cos(lat_med)
        if n_lon > 1 else 0.0
    )
    paso_km = (paso_lat_km + paso_lon_km) / 2

    st.markdown("---")

    col_info, col_mapa = st.columns([1, 1])

    with col_info:
        st.markdown(f"**Dataset cargado:** `{pathlib.Path(nc_path).name}`")
        st.markdown("")

        st.markdown("**Información del dataset**")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Grilla", f"{n_lat} × {n_lon}")
        col2.metric("Paso", f"≈ {paso_km:.1f} km")
        col3.metric("Capas", str(n_prof))
        col4.metric("Navegable", f"{100*agua/total:.0f}%")

        st.markdown("")
        st.markdown(
            f"**Cobertura:**  \n"
            f"Lat `{campo.lat.min():.2f}°` → `{campo.lat.max():.2f}°`  \n"
            f"Lon `{campo.lon.min():.2f}°` → `{campo.lon.max():.2f}°`"
        )

        mag_sup = np.sqrt(campo.uo[0] ** 2 + campo.vo[0] ** 2)
        mag_nav = mag_sup[campo.navegable[0]]
        if len(mag_nav):
            st.markdown(
                f"**Corriente superficial:**  \n"
                f"media `{float(np.nanmean(mag_nav)):.3f} m/s`  \n"
                f"máx `{float(np.nanmax(mag_nav)):.3f} m/s`"
            )

        metadata = _leer_metadata_nc(nc_path)
        if metadata and metadata.get("fecha"):
            st.markdown(f"**Fecha:** {metadata['fecha']}")

        st.markdown("")
        if st.session_state.fase_actual == 1:
            if st.button(
                "▶  Continuar → Fase 2",
                type="primary",
                key="btn_continuar_f1",
                use_container_width=True,
            ):
                st.session_state.nav_direction = "right"
                st.session_state.fase_actual   = 2
                st.rerun()

    with col_mapa:
        st.markdown("`> CAMPO DE CORRIENTES`")

        capa_actual = st.session_state.capa_preview
        n_capas     = len(campo.prof)
        prof_m     = campo.prof[capa_actual]
        nombre_cap = "superficie" if capa_actual == 0 else f"{prof_m:.1f} m"

        nav1, nav2, nav3, nav4 = st.columns([1, 4, 1, 3])

        with nav1:
            if st.button("◀", key="capa_prev", disabled=(capa_actual == 0)):
                st.session_state.capa_preview = capa_actual - 1
                st.rerun()

        with nav2:
            st.markdown(
                f"<div class='capa-label'>"
                f"<b>CAPA {capa_actual}</b> · {nombre_cap.upper()}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with nav3:
            if st.button("▶", key="capa_next", disabled=(capa_actual == n_capas - 1)):
                st.session_state.capa_preview = capa_actual + 1
                st.rerun()

        with nav4:
            opciones   = [f"Capa {i}  ·  {campo.prof[i]:.1f} m" for i in range(n_capas)]
            nueva_capa = st.selectbox(
                "Saltar a capa",
                options=opciones,
                index=capa_actual,
                key="sel_capa_drop",
                label_visibility="collapsed",
            )
            idx_nueva = opciones.index(nueva_capa)
            if idx_nueva != capa_actual:
                st.session_state.capa_preview = idx_nueva
                st.rerun()

        with st.spinner("Renderizando..."):
            fig, ax = plt.subplots(figsize=(8, 6))
            plot_campo(campo, capa=capa_actual, ax=ax)
            _mostrar_figura(fig, "medio")
            plt.close(fig)


# ── Fase 2 — Análisis del campo de corrientes ─────────────────────────────────

def _render_contenido_fase2() -> None:
    _render_status_bar("PROCESANDO  ·  ANÁLISIS DE DIVERGENCIA ACTIVO")

    campo   = st.session_state.campo
    nc_path = st.session_state.nc_path
    capa    = 0

    lat_med = math.radians(float(campo.lat.mean()))
    dy_km   = abs(float(campo.lat[1] - campo.lat[0])) * 111.32
    dx_km   = abs(float(campo.lon[1] - campo.lon[0])) * 111.32 * math.cos(lat_med)

    with st.spinner("Calculando divergencia…"):
        div, dx, dy = _calcular_div(nc_path)
        st.session_state.div = div
        st.session_state.dx  = dx
        st.session_state.dy  = dy

    nav  = campo.navegable[capa]
    conv = int((nav & (div < 0)).sum())
    agua = int(nav.sum())

    st.markdown(f"`> CAMPO: {pathlib.Path(nc_path).name}`")
    
    col_info, col_mapa = st.columns([1, 1])

    with col_info:
        st.markdown("**[ INFORMACIÓN DEL CAMPO ]**")
        st.info(
            f"▸ Componentes: `uo` (Este↔Oeste), `vo` (Norte↕Sur)  \n"
            f"▸ Resolución: dx ≈ {dx_km:.1f} km · dy ≈ {dy_km:.1f} km"
        )

        st.markdown("**[ DIVERGENCIA HORIZONTAL ]**")
        st.markdown(
            "- `div < 0` → **CONVERGENCIA** (acumulación)  \n"
            "- `div > 0` → **DIVERGENCIA** (dispersión)  \n"
            "- `div ≈ 0` → flujo neutro"
        )

        st.markdown("**[ RESULTADOS ]**")
        col1, col2 = st.columns(2)
        col1.metric("Div. máx.", f"{float(div[nav].max()):.2e} /s")
        col2.metric("Conv. mín.", f"{float(div[nav].min()):.2e} /s")
        st.metric("Celdas convergentes", f"{conv} / {agua}  ({100*conv/agua:.0f} %)")
        
        st.caption("Azul = convergencia · Rojo = divergencia · Marrón = tierra")

    with col_mapa:
        st.markdown('`> CAMPO DE CORRIENTES`')
        with st.spinner("Renderizando campo…"):
            fig_c, ax_c = plt.subplots(figsize=(8, 4))
            plot_campo(campo, capa=capa, ax=ax_c)
            _mostrar_figura(fig_c, "medio")
            plt.close(fig_c)
        st.markdown('`> DIVERGENCIA`')
        with st.spinner("Renderizando divergencia…"):
            fig_d, ax_d = plt.subplots(figsize=(8, 4))
            plot_divergencia(campo, div, capa=capa, ax=ax_d)
            _mostrar_figura(fig_d, "medio")
            plt.close(fig_d)

    if st.session_state.fase_actual == 2:
        st.markdown("")
        col_back2, col_next2 = st.columns([1, 2])
        with col_back2:
            _render_volver(1, "btn_volver_f2")
        with col_next2:
            if st.button(
                "▶  Continuar → Fase 3: Selección de zonas de misión",
                type="primary",
                key="btn_continuar_f2",
                use_container_width=True,
            ):
                st.session_state.nav_direction = "right"
                st.session_state.fase_actual   = 3
                st.rerun()


# ── Fase 3 — Selección de zonas de misión ────────────────────────────────────

def _render_galeria_bases(campo: CampoCorrientes) -> None:
    """Galería de bases seleccionables (mismo patrón visual que la Fase 1):
    tarjetas con borde en fila + una tarjeta final para agregar una base nueva.
    """
    bases_custom = st.session_state.bases_personalizadas
    base_key     = st.session_state.base_key
    capa         = 0
    nav          = campo.navegable[capa]

    opciones = [
        {
            "key": "callao",  "nombre": "Puerto del Callao",
            "lat": _LAT_CALLAO,  "lon": _LON_CALLAO,  "default": True,
        },
        {
            "key": "chancay", "nombre": "Puerto de Chancay",
            "lat": _LAT_CHANCAY, "lon": _LON_CHANCAY, "default": True,
        },
    ]
    for idx, info in enumerate(bases_custom):
        opciones.append({
            "key": idx, "nombre": info["nombre"],
            "lat": info["lat"], "lon": info["lon"], "default": False,
        })

    n_mostrar = min(len(opciones), 3)
    n_cols    = n_mostrar + 1
    cols      = st.columns(n_cols)

    for idx, op in enumerate(opciones[:3]):
        with cols[idx]:
            with st.container(border=True):
                bc = celda_mas_cercana(op["lat"], op["lon"], campo.lat, campo.lon, nav, capa=capa)
                _, bi, bj = bc
                selec = (base_key == op["key"])
                st.markdown(f"**{op['nombre']}**" + ("  \n_(por defecto)_" if op["default"] else ""))
                st.markdown(
                    f"Lat: `{op['lat']:.3f}°`  \n"
                    f"Lon: `{op['lon']:.3f}°`  \n"
                    f"Celda navegable: `({campo.lat[bi]:.3f}°, {campo.lon[bj]:.3f}°)`"
                )
                lbl  = "Seleccionada" if selec else "Seleccionar"
                tipo = "primary" if selec else "secondary"
                if st.button(lbl, key=f"base_sel_{op['key']}", type=tipo, use_container_width=True):
                    st.session_state.base_key = op["key"]
                    st.rerun()

    with cols[-1]:
        with st.container(border=True):
            st.markdown("**+ Nueva base**")

            preset_names = [b["nombre"] for b in _BASES_PREDEFINIDAS]
            preset_seleccion = st.selectbox(
                "Cargar base predefinida del Perú",
                options=["Seleccionar..."] + preset_names,
                index=0,
                key="preset_base_selector",
                label_visibility="collapsed",
                help="Puertos principales del litoral peruano.",
            )
            if preset_seleccion != "Seleccionar...":
                preset_base = next(b for b in _BASES_PREDEFINIDAS if b["nombre"] == preset_seleccion)
                st.caption(f"{preset_base['region']} · {preset_base['desc']}")
                if st.button("Agregar esta base", key="btn_add_preset_base", use_container_width=True):
                    st.session_state.bases_personalizadas.append({
                        "nombre": preset_base["nombre"],
                        "lat":    preset_base["lat"],
                        "lon":    preset_base["lon"],
                    })
                    st.session_state.base_key = len(st.session_state.bases_personalizadas) - 1
                    st.rerun()

            st.markdown("_o ingrese una manualmente:_")
            nombre_inp = st.text_input(
                "Nombre de la base",
                placeholder="Ej: Puerto Salaverry",
                key="inp_base_nombre",
                label_visibility="collapsed",
            )
            c_lat, c_lon = st.columns(2)
            with c_lat:
                lat_inp = st.number_input(
                    "Latitud [°]", value=-12.0, step=0.01, format="%.3f",
                    key="inp_base_lat",
                )
            with c_lon:
                lon_inp = st.number_input(
                    "Longitud [°]", value=-77.0, step=0.01, format="%.3f",
                    key="inp_base_lon",
                )
            if st.button("Agregar base", key="btn_agregar_base", use_container_width=True):
                nombre_final = nombre_inp.strip() or f"Base {len(bases_custom) + 1}"
                st.session_state.bases_personalizadas.append({
                    "nombre": nombre_final,
                    "lat":    lat_inp,
                    "lon":    lon_inp,
                })
                st.session_state.base_key = len(st.session_state.bases_personalizadas) - 1
                st.rerun()


def _render_contenido_fase3() -> None:
    _render_status_bar("PLANIFICACIÓN DE ZONAS  ·  PARÁMETROS ACTIVOS")

    campo = st.session_state.campo
    div   = st.session_state.div
    capa  = 0
    nav   = campo.navegable[capa]

    # ── Galería de bases, ancho completo (mismo patrón que Fase 1) ─────────
    st.markdown("`> SELECCIONAR BASE DE LA MISIÓN`")
    _render_galeria_bases(campo)

    st.divider()

    base_key = st.session_state.base_key
    if base_key == "callao":
        b_nombre = "Puerto del Callao"
        b_lat, b_lon = _LAT_CALLAO, _LON_CALLAO
    elif base_key == "chancay":
        b_nombre = "Puerto de Chancay"
        b_lat, b_lon = _LAT_CHANCAY, _LON_CHANCAY
    else:
        info = st.session_state.bases_personalizadas[base_key]
        b_nombre = info["nombre"]
        b_lat, b_lon = info["lat"], info["lon"]

    # ── Parámetros (1/3) + Mapa (2/3) ───────────────────────────────────────
    col_panel, col_mapa = st.columns([1, 2])

    with col_panel:
        with st.container(border=True):
            st.markdown("**[ PARÁMETROS ]**")
            st.caption(f"Base activa: {b_nombre}")

            k_zonas = st.slider(
                "Cantidad de zonas",
                2, 8, st.session_state.k_zonas_f3, key="sl_k_zonas",
            )
            k_cent = st.slider(
                "Centinelas offshore",
                1, 4, st.session_state.k_cent_f3, key="sl_k_cent",
            )
            dist_min = st.slider(
                "Separación mínima [celdas]",
                1, 6, st.session_state.dist_min_f3, key="sl_dist_min",
            )
            st.session_state.k_zonas_f3  = k_zonas
            st.session_state.k_cent_f3   = k_cent
            st.session_state.dist_min_f3 = dist_min

            # Las zonas se muestran automáticamente y se recalculan solas
            # ante cualquier cambio de base o parámetros (sin botón ni toggle).
            firma = (base_key, k_zonas, k_cent, dist_min)
            if st.session_state.firma_zonas_f3 != firma:
                with st.spinner("Calculando zonas…"):
                    uo   = campo.uo[capa]
                    vo   = campo.vo[capa]
                    wps  = seleccionar_waypoints(div, nav, k_zonas, capa=capa, dist_min_celdas=dist_min)
                    cent = seleccionar_centinelas(uo, vo, nav, campo.lon, n=k_cent, capa=capa)
                    base = celda_mas_cercana(b_lat, b_lon, campo.lat, campo.lon, nav, capa=capa)
                    todos, base_nodo = agregar_puntos_fijos(wps + cent, wps[0], base)

                st.session_state.wps        = wps
                st.session_state.cent       = cent
                st.session_state.base_celda = base
                st.session_state.todos      = todos
                st.session_state.base_nodo  = base_nodo
                st.session_state.base_idx   = todos.index(base_nodo)
                st.session_state.firma_zonas_f3 = firma
                st.rerun()

            if st.session_state.wps is not None:
                st.markdown("---")
                n_inter = len(st.session_state.todos) - 1
                ordenes = math.factorial(n_inter)
                st.metric("Zonas convergencia", len(st.session_state.wps))
                st.metric("Centinelas", len(st.session_state.cent))
                st.metric("Órdenes ATSP", f"{ordenes:,}")

    with col_mapa:
        with st.container(border=True):
            st.markdown("**[ MAPA DE ZONAS DE MISIÓN ]**")
            if st.session_state.wps is not None:
                with st.spinner("Renderizando mapa…"):
                    fig, ax = plt.subplots(figsize=(10, 8))
                    plot_zonas(campo, div, st.session_state.wps,
                              centinelas=st.session_state.cent,
                              base=st.session_state.base_celda, capa=0, ax=ax)
                    _mostrar_figura(fig, "medio")
                    plt.close(fig)
            else:
                st.info("Calculando zonas…")

    # ── Tabla, ancho completo ────────────────────────────────────────────────
    if st.session_state.wps is not None:
        st.divider()
        st.markdown("**[ DETALLE DE WAYPOINTS ]**")
        tabla = []
        for k, (p, i, j) in enumerate(st.session_state.wps):
            tabla.append({
                "ID":   f"C{k+1}",
                "Tipo": "Convergencia",
                "Lat [°]": f"{campo.lat[i]:.3f}",
                "Lon [°]": f"{campo.lon[j]:.3f}",
                "Divergencia [1/s]": f"{div[i, j]:.2e}",
            })
        for k, (p, i, j) in enumerate(st.session_state.cent):
            tabla.append({
                "ID":   f"S{k+1}",
                "Tipo": "Centinela",
                "Lat [°]": f"{campo.lat[i]:.3f}",
                "Lon [°]": f"{campo.lon[j]:.3f}",
                "Divergencia [1/s]": "—",
            })
        _, bi, bj = st.session_state.base_celda
        tabla.append({
            "ID":   "B",
            "Tipo": f"Base ({b_nombre})",
            "Lat [°]": f"{campo.lat[bi]:.3f}",
            "Lon [°]": f"{campo.lon[bj]:.3f}",
            "Divergencia [1/s]": "—",
        })
        st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)

    if st.session_state.fase_actual == 3 and st.session_state.wps is not None:
        st.markdown("")
        col_back3, col_next3 = st.columns([1, 2])
        with col_back3:
            _render_volver(2, "btn_volver_f3")
        with col_next3:
            if st.button(
                "▶  Continuar → Fase 4: Modelo energético y grafo",
                type="primary", key="btn_continuar_f3",
                use_container_width=True,
            ):
                st.session_state.nav_direction = "right"
                st.session_state.fase_actual   = 4
                st.rerun()


# ── Fase 4 — Modelo energético y grafo ───────────────────────────────────────

def _get_drone_img_src(drone: dict | None) -> str:
    src = None
    if drone:
        path = _drone_img_path(drone.get("nombre", ""))
        if path:
            ext  = path.suffix.lstrip(".")
            mime = _IMG_MIME.get(ext, "image/png")
            src  = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
        elif drone.get("imagen_b64"):
            mime = drone.get("imagen_mime", "image/png")
            src  = f"data:{mime};base64,{drone['imagen_b64']}"
    if src is None:
        src = f"data:image/svg+xml;base64,{base64.b64encode(_SVG_AUV.encode()).decode()}"
    return src


def _drone_img_html(drone: dict | None = None) -> str:
    src = _get_drone_img_src(drone)
    return (
        '<div style="width:110px;height:70px;flex-shrink:0;display:flex;'
        'align-items:center;justify-content:center;overflow:hidden;'
        'border-radius:6px;background:rgba(46,139,158,0.07);">'
        f'<img src="{src}" style="width:100%;height:100%;object-fit:contain;"/>'
        '</div>'
    )


def _drone_card_banner_html(drone: dict | None = None) -> str:
    src = _get_drone_img_src(drone)
    return (
        '<div style="width:100%;height:130px;display:flex;align-items:center;'
        'justify-content:center;overflow:hidden;border-radius:6px;'
        'background:rgba(4,12,24,0.55);margin-bottom:10px;">'
        f'<img src="{src}" style="max-width:80%;max-height:80%;object-fit:contain;"/>'
        '</div>'
    )


@st.cache_resource(show_spinner=False)
def _construir_grafo_cache(
    nc_path: str,
    s: float, eta: float, k_p: float, k_r: float, e_max: float, k_zonas: int,
) -> tuple:
    campo  = cargar_corrientes(nc_path)
    params = ParametrosModelo(s=s, eta=eta, k_p=k_p, k_r=k_r, e_max=e_max, k_zonas=k_zonas)
    return construir_grafo(campo, params), params


@st.dialog("Drone", width="large")
def _dialogo_drone(idx: int) -> None:
    """idx == -1 → nuevo drone; idx >= 0 → editar existente."""
    es_nuevo = idx == -1
    drones   = st.session_state.drones
    base     = {} if es_nuevo else drones[idx]

    st.subheader("Agregar drone" if es_nuevo else f"Editar — {base.get('nombre','')}")
    st.divider()

    # Selector de presets (solo para drones nuevos)
    if es_nuevo:
        st.markdown("**Cargar preset de drone**")
        preset_names = [p["nombre"] for p in _DRONE_PRESETS]
        presetSeleccionado = st.selectbox(
            "Seleccionar preset",
            options=["Personalizado"] + preset_names,
            index=1,  # REMUS 100 por defecto
            key="preset_selector",
            help="Carga parámetros predefinidos de drones conocidos.",
        )
        if presetSeleccionado != "Personalizado":
            preset = next(p for p in _DRONE_PRESETS if p["nombre"] == presetSeleccionado)
            base = {
                "nombre":  preset["nombre"],
                "s":       preset["s"],
                "eta":     preset["eta"],
                "k_p":     preset["k_p"],
                "k_r":     preset["k_r"],
                "e_max":   preset["e_max"],
                "pct_ini": preset["pct_ini"],
            }
            st.info(f"**{preset['desc']}**")
        st.divider()

    nombre = st.text_input(
        "Nombre del drone",
        value=base.get("nombre", ""),
        placeholder="Ej: AUV Bluefin-9",
    )

    st.markdown("**Parámetros hidrodinámicos**")
    c1, c2 = st.columns(2)
    with c1:
        s_val = float(base.get("s", 0.5))
        s = st.number_input(
            "Velocidad de crucero v [m/s]",
            min_value=0.1, max_value=max(3.0, s_val + 1.0),
            value=s_val, step=0.05, format="%.2f",
            help="Velocidad del AUV respecto al agua. Valores típicos: 0.3–1.5 m/s.",
        )
        st.caption("Velocidad del cuerpo relativa al agua (no respecto al fondo).")
    with c2:
        eta_val = float(base.get("eta", 0.30))
        eta = st.number_input(
            "Eficiencia de regeneración η [0–1]",
            min_value=0.01, max_value=0.99,
            value=eta_val, step=0.01, format="%.2f",
            help="Fracción de energía cinética convertida en carga eléctrica al regenerar.",
        )
        st.caption("Fracción de energía recuperada al dejarse llevar por la corriente.")

    st.markdown("**Coeficientes energéticos**")
    c3, c4 = st.columns(2)
    with c3:
        k_p_val = float(base.get("k_p", 1.0))
        k_p = st.number_input(
            "Coeficiente de propulsión kp",
            min_value=0.01, max_value=max(100.0, k_p_val + 10.0),
            value=k_p_val, step=0.1, format="%.2f",
            help="Escala el consumo energético en modo propulsión. Mayor kp → más gasto.",
        )
        st.caption("Escala el consumo en modo propulsión (corriente en contra o lateral).")
    with c4:
        k_r_val = float(base.get("k_r", 1.0))
        k_r = st.number_input(
            "Coeficiente de regeneración kr",
            min_value=0.01, max_value=max(100.0, k_r_val + 10.0),
            value=k_r_val, step=0.1, format="%.2f",
            help="Escala la energía recuperada en modo regeneración. Mayor kr → más ganancia.",
        )
        st.caption("Escala la ganancia energética en modo regeneración (corriente a favor).")

    st.markdown("**Batería**")
    c5, c6 = st.columns(2)
    with c5:
        e_max_wh_val = float(base.get("e_max", 1_000_000)) / 3_600.0
        e_max_wh = st.number_input(
            "Capacidad máxima [Wh]",
            min_value=1.0, max_value=max(100_000.0, e_max_wh_val + 10_000.0),
            value=e_max_wh_val,
            step=10.0, format="%.0f",
            help="Energía almacenada al 100 % de carga.",
        )
        st.caption("Energía total de la batería en Wh (1 Wh = 3 600 J).")
    with c6:
        pct_ini = st.number_input(
            "Carga inicial [%]",
            min_value=1, max_value=100,
            value=int(base.get("pct_ini", 100)), step=1,
            help="Estado de carga al inicio de la misión.",
        )
        st.caption("Porcentaje de carga con que el AUV comienza la misión.")

    st.markdown("**Imagen del drone** *(opcional)*")
    img_preview, img_upload = st.columns([1, 3])
    with img_preview:
        st.markdown(_drone_img_html(base), unsafe_allow_html=True)
    with img_upload:
        uploaded_img = st.file_uploader(
            "PNG, JPG o SVG — se ajusta al recuadro",
            type=["png", "jpg", "jpeg", "svg", "webp"],
            key="dlg_drone_img",
            label_visibility="visible",
        )

    st.divider()
    bc, bs = st.columns(2)
    with bc:
        if st.button("Cancelar", use_container_width=True, key="dlg_cancel"):
            st.session_state.abrir_drone_idx = None
            st.rerun()
    with bs:
        if st.button("Guardar drone", type="primary", use_container_width=True, key="dlg_save"):
            nombre_final = nombre.strip() or (f"Drone {len(drones)+1}" if es_nuevo else base["nombre"])
            if uploaded_img is not None:
                img_bytes = uploaded_img.read()
                ext       = uploaded_img.name.rsplit(".", 1)[-1].lower()
                slug      = re.sub(r"[^\w\-]", "_", nombre_final.lower())
                ((_ASSETS_DRONES / f"{slug}.{ext}").write_bytes(img_bytes))
                imagen_b64  = None
                imagen_mime = None
            else:
                imagen_b64  = base.get("imagen_b64")
                imagen_mime = base.get("imagen_mime")

            nuevo = {
                "nombre":     nombre_final,
                "s":          s,
                "eta":        eta,
                "k_p":        k_p,
                "k_r":        k_r,
                "e_max":      int(e_max_wh * 3_600),
                "pct_ini":    int(pct_ini),
                "imagen_b64": imagen_b64,
                "imagen_mime": imagen_mime,
            }
            if es_nuevo:
                st.session_state.drones.append(nuevo)
                st.session_state.drone_key = len(st.session_state.drones) - 1
            else:
                st.session_state.drones[idx] = nuevo
            st.session_state.grafo        = None
            st.session_state.params_f4    = None
            st.session_state.hay_ciclo_f4 = None
            st.session_state.ruta         = None
            st.session_state.orden_f5     = None
            st.session_state.costo_f5     = None
            st.session_state.M_f5         = None
            st.session_state.caminos_f5   = None
            st.session_state.costo_sin_f5 = None
            if st.session_state.fase_actual >= 5:
                st.session_state.fase_actual = 4
            st.session_state.abrir_drone_idx = None
            st.rerun()


def _render_tarjeta_drone(idx: int) -> None:
    """Gallery card con imagen arriba y parámetros abajo."""
    drone = st.session_state.drones[idx]
    selec = st.session_state.drone_key == idx
    e_wh  = drone["e_max"] / 3_600

    badge      = ('<span style="color:#FFB000;font-size:11px;font-weight:600;'
                  'letter-spacing:0.05em;">● activo</span>') if selec else ""
    nombre_txt = drone["nombre"].upper()
    src        = _get_drone_img_src(drone)

    card_head = (
        f'<div style="width:100%;height:128px;display:flex;align-items:center;'
        f'justify-content:center;overflow:hidden;border-radius:6px;'
        f'background:rgba(4,12,24,0.6);margin-bottom:10px;">'
        f'<img src="{src}" style="max-width:80%;max-height:80%;object-fit:contain;"/>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'margin-bottom:5px;">'
        f'<span style="font-weight:700;color:#C5D5E8;font-size:13px;'
        f'letter-spacing:0.06em;">{nombre_txt}</span>'
        f'{badge}'
        f'</div>'
        f'<hr style="border:none;border-top:1px solid #1A3050;margin:0 0 8px;"/>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 10px;'
        f'font-size:12px;color:#7A94B0;font-family:\'JetBrains Mono\',monospace;'
        f'margin-bottom:10px;">'
        f'<span><b style="color:#C5D5E8;">v</b>&nbsp;{drone["s"]:.2f} m/s</span>'
        f'<span><b style="color:#C5D5E8;">η</b>&nbsp;{drone["eta"]:.2f}</span>'
        f'<span><b style="color:#C5D5E8;">kp</b>&nbsp;{drone["k_p"]:.2f}</span>'
        f'<span><b style="color:#C5D5E8;">kr</b>&nbsp;{drone["k_r"]:.2f}</span>'
        f'<span><b style="color:#C5D5E8;">Bat</b>&nbsp;{e_wh:.0f} Wh</span>'
        f'<span><b style="color:#C5D5E8;">Ini</b>&nbsp;{drone["pct_ini"]}%</span>'
        f'</div>'
    )

    with st.container(border=True):
        st.markdown(card_head, unsafe_allow_html=True)
        b1, b2, b3 = st.columns(3)
        with b1:
            lbl  = "Activo" if selec else "Seleccionar"
            tipo = "primary" if selec else "secondary"
            if st.button(lbl, key=f"sel_d_{idx}", type=tipo, use_container_width=True):
                st.session_state.drone_key = idx

                # Auto-construir grafo al seleccionar
                drone_sel = st.session_state.drones[idx]
                nc_path = st.session_state.nc_path
                base_nodo = st.session_state.base_nodo

                with st.spinner("Construyendo grafo..."):
                    grafo, params = _construir_grafo_cache(
                        nc_path,
                        s=drone_sel["s"],
                        eta=drone_sel["eta"],
                        k_p=drone_sel["k_p"],
                        k_r=drone_sel["k_r"],
                        e_max=drone_sel["e_max"],
                        k_zonas=st.session_state.k_zonas_f3,
                    )
                    dist_val, _ = bellman_ford(grafo, base_nodo)
                    hay_ciclo = hay_ciclo_negativo(grafo, dist_val)

                st.session_state.grafo = grafo
                st.session_state.params_f4 = params
                st.session_state.bat_ini_j = int(drone_sel["e_max"] * drone_sel["pct_ini"] / 100)
                st.session_state.hay_ciclo_f4 = hay_ciclo
                st.session_state.ruta = None
                st.session_state.orden_f5 = None
                st.session_state.costo_f5 = None
                st.session_state.M_f5 = None
                st.session_state.caminos_f5 = None
                st.session_state.costo_sin_f5 = None
                st.rerun()
        with b2:
            if st.button("Editar", key=f"edit_d_{idx}", use_container_width=True):
                st.session_state.abrir_drone_idx = idx
                st.rerun()
        with b3:
            if st.button("Quitar", key=f"del_d_{idx}", use_container_width=True):
                st.session_state.drones.pop(idx)
                n = len(st.session_state.drones)
                if n == 0:
                    st.session_state.drones = [{
                        "nombre":  _DRONE_PRESETS[0]["nombre"],
                        "s":       _DRONE_PRESETS[0]["s"],
                        "eta":     _DRONE_PRESETS[0]["eta"],
                        "k_p":     _DRONE_PRESETS[0]["k_p"],
                        "k_r":     _DRONE_PRESETS[0]["k_r"],
                        "e_max":   _DRONE_PRESETS[0]["e_max"],
                        "pct_ini": _DRONE_PRESETS[0]["pct_ini"],
                    }]
                if st.session_state.drone_key >= len(st.session_state.drones):
                    st.session_state.drone_key = max(0, len(st.session_state.drones) - 1)
                st.session_state.grafo        = None
                st.session_state.hay_ciclo_f4 = None
                st.session_state.ruta         = None
                st.session_state.orden_f5     = None
                st.session_state.costo_f5     = None
                st.session_state.M_f5         = None
                st.session_state.caminos_f5   = None
                st.session_state.costo_sin_f5 = None
                if st.session_state.fase_actual >= 5:
                    st.session_state.fase_actual = 4
                st.rerun()


def _render_gestor_drones() -> None:
    """Galería de tarjetas 3 por fila con botón de agregar al final."""
    drones = st.session_state.drones

    if st.session_state.abrir_drone_idx is not None:
        _dialogo_drone(st.session_state.abrir_drone_idx)

    for i in range(0, len(drones), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(drones):
                with col:
                    _render_tarjeta_drone(i + j)

    st.markdown("")
    if st.button("Agregar drone", key="btn_agregar_drone"):
        st.session_state.abrir_drone_idx = -1
        st.rerun()


def _render_contenido_fase4() -> None:
    _render_status_bar("CONFIGURACIÓN DE DRONES  ·  ACTIVO")

    campo     = st.session_state.campo
    nc_path   = st.session_state.nc_path
    todos     = st.session_state.todos
    base_nodo = st.session_state.base_nodo

    st.markdown("`> SELECCIONAR DRONES PARA LA MISIÓN`")

    # Si no hay drone seleccionado, mostrar selector fullscreen
    if st.session_state.grafo is None:
        _render_gestor_drones()
        return

    # Ya hay grafo construido → mostrar resultado arriba + continuar a Fase 5
    grafo     = st.session_state.grafo
    params    = st.session_state.params_f4
    bat_ini   = st.session_state.bat_ini_j
    hay_ciclo = st.session_state.hay_ciclo_f4
    drone_sel = st.session_state.drones[st.session_state.drone_key]

    st.markdown(f"**Drone seleccionado:** `{drone_sel['nombre']}`")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nodos", f"{grafo.num_nodos:,}")
    col2.metric("Aristas", f"{grafo.num_aristas:,}")
    col3.metric("Batería inicial", f"{bat_ini / 3_600:.0f} Wh")
    col4.metric("Ciclo negativo", "Sí" if hay_ciclo else "No")

    if hay_ciclo:
        st.warning(
            "Ciclo de energía negativa detectado. Ajustá kp, kr o η antes de continuar."
        )
        if st.button("Cambiar drone", key="btn_cambiar_drone"):
            st.session_state.grafo = None
            st.session_state.hay_ciclo_f4 = None
            st.rerun()
        return

    # Compute cost matrix and optimal route if not already done
    if st.session_state.ruta is None:
        with st.spinner("Calculando ruta óptima…"):
            wps_f4    = st.session_state.wps
            cent_f4   = st.session_state.cent
            base_idx  = st.session_state.base_idx
            params_f4 = st.session_state.params_f4

            M_viz, caminos_viz = matriz_costos(grafo, todos)
            orden_viz, costo_viz = atsp_fuerza_bruta(M_viz, base_idx)
            ruta_viz = ensamblar_ruta(orden_viz, caminos_viz)

            # Comparación: costo SIN beneficio de corrientes (enfoque naive/Dijkstra)
            M_sin = matriz_costos_sin_corrientes(grafo, todos, campo, params_f4)
            orden_sin, costo_sin = atsp_fuerza_bruta(M_sin, base_idx)

            st.session_state.M_f5       = M_viz
            st.session_state.caminos_f5 = caminos_viz
            st.session_state.orden_f5   = orden_viz
            st.session_state.costo_f5   = costo_viz
            st.session_state.ruta       = ruta_viz
            st.session_state.M_sin_f5   = M_sin
            st.session_state.costo_sin_f5 = costo_sin

    M_f5_local     = st.session_state.M_f5
    orden_f5_local = st.session_state.orden_f5

    st.markdown("---")

    # ── Fila de 3 paneles a tercio de ancho c/u ─────────────────────────────
    etiq_dict = _build_etiquetas(todos, st.session_state.wps, st.session_state.cent, base_nodo)
    etiq_list = _build_etiquetas_list(todos, etiq_dict)

    col_grafo, col_tours, col_prox = st.columns(3)

    with col_grafo:
        with st.container(border=True):
            st.markdown("**[ GRAFO DE COSTOS ]**")
            fig_g, ax_g = plt.subplots(figsize=(6, 5))
            plot_grafo_costos(todos, campo, M_f5_local, etiq_dict, ax=ax_g)
            _mostrar_figura(fig_g)
            plt.close(fig_g)

    with col_tours:
        with st.container(border=True):
            st.markdown("**[ TOURS ATSP ]**")
            n_inter = len(todos) - 1
            if math.factorial(n_inter) <= 40320:
                fig_t = plot_tours_atsp(M_f5_local, etiq_list, orden_f5_local)
                st.pyplot(fig_t, use_container_width=True)
                plt.close(fig_t)
            else:
                st.info("Visualización no disponible para >8 zonas (demasiadas permutaciones).")

    with col_prox:
        with st.container(border=True):
            st.markdown("**[ GRAFO 3D ]**")
            try:
                import plotly.graph_objects as go  # noqa: F401
                fig_3d_grafo = plot_grafo_3d(grafo, campo)
                st.plotly_chart(fig_3d_grafo, use_container_width=True, height=380)
                st.caption("🟩 Costo negativo (regeneración)  ·  🟥 Costo positivo (consumo)")
            except ImportError:
                st.info("Para ver el grafo en 3D, instale plotly: `pip install plotly`")

    st.markdown("---")

    if st.session_state.fase_actual == 4:
        col_back4, col_next4 = st.columns([1, 2])
        with col_back4:
            _render_volver(3, "btn_volver_f4")
        with col_next4:
            if st.button(
                "▶  Continuar → Fase 5: Ruta óptima",
                type="primary",
                key="btn_continuar_f4",
                use_container_width=True,
            ):
                st.session_state.nav_direction = "right"
                st.session_state.fase_actual = 5
                st.rerun()


# ── Fase 5 — Ruta óptima (fusionada con Fase 4) ─────────────────────────────

def _render_contenido_fase5() -> None:
    _render_status_bar("SOLVER ATSP  ·  VALIDACIÓN DE RUTA  ·  COMPLETADO")

    campo     = st.session_state.campo
    todos     = st.session_state.todos
    wps       = st.session_state.wps
    cent      = st.session_state.cent
    base_nodo = st.session_state.base_nodo
    ruta      = st.session_state.ruta
    orden     = st.session_state.orden_f5
    costo_opt = st.session_state.costo_f5
    M         = st.session_state.M_f5
    params    = st.session_state.params_f4

    etiq_dict = _build_etiquetas(todos, wps, cent, base_nodo)
    etiq_list = _build_etiquetas_list(todos, etiq_dict)
    ruta_str  = "  →  ".join(etiq_list[i] for i in orden)

    tramos     = _calcular_tramos(orden, st.session_state.caminos_f5, etiq_list, M, params.s)
    total_dist = sum(float(t["Dist (km)"]) for t in tramos)
    total_time = sum(float(t["Tiempo (h)"]) for t in tramos)

    costo_sin  = st.session_state.costo_sin_f5
    hay_ahorro = costo_sin is not None and costo_sin > 0
    if hay_ahorro:
        ahorro_j   = costo_sin - costo_opt
        ahorro_pct = (ahorro_j / costo_sin) * 100

    # ── Fila de islas parejas ──────────────────────────────────────────────
    isla_ruta, isla_resumen, isla_beneficio = st.columns(3)

    with isla_ruta:
        with st.container(border=True):
            st.markdown("**[ RUTA ÓPTIMA ]**")
            st.markdown(ruta_str)
            st.caption(f"{len(wps)} zonas · {len(cent)} centinelas · base")

    with isla_resumen:
        with st.container(border=True):
            st.markdown("**[ RESUMEN ]**")
            r1, r2 = st.columns(2)
            r1.metric("Costo", f"{costo_opt/3600:.1f} Wh")
            r2.metric("Distancia", f"{total_dist:.1f} km")
            r3, r4 = st.columns(2)
            r3.metric("Tiempo", f"{total_time:.1f} h")
            r4.metric("Algoritmo", "ATSP · BF")

    with isla_beneficio:
        with st.container(border=True):
            st.markdown("**[ BENEFICIO vs OTROS ALGORITMOS ]**")
            if hay_ahorro:
                b1, b2 = st.columns(2)
                b1.metric("Ahorro", f"{ahorro_j/3600:.1f} Wh")
                b2.metric("Reducción", f"{ahorro_pct:.1f}%")
            else:
                st.info("Sin datos de comparación disponibles.")

    # ── Mapa de ruta + comparativa de algoritmos (mitad y mitad) ────────────
    col_mapa, col_comp = st.columns(2)

    with col_mapa:
        with st.container(border=True):
            st.markdown("**[ MAPA DE RUTA ]**")
            fig_r, ax_r = plt.subplots(figsize=(7, 6))
            plot_ruta(campo, ruta, waypoints=wps, centinelas=cent, base=base_nodo, ax=ax_r)
            st.pyplot(fig_r, use_container_width=True)
            plt.close(fig_r)
            st.caption("⬤ BASE · ⬤ ZONA CONV. · ⬤ CENTINELA · ━ RUTA")

    with col_comp:
        with st.container(border=True):
            st.markdown("**[ COMPARATIVA DE ALGORITMOS ]**")
            costos_cmp = {"Bellman-Ford\n(óptimo)": costo_opt}
            if hay_ahorro:
                costos_cmp["Dijkstra\n(sin regen.)"] = costo_sin
                costos_cmp["A*\n(sin regen.)"]       = costo_sin
            fig_c, ax_c = plt.subplots(figsize=(7, 6))
            plot_comparativa_algoritmos(costos_cmp, ax=ax_c)
            st.pyplot(fig_c, use_container_width=True)
            plt.close(fig_c)
            st.caption(
                "Dijkstra y A* exigen pesos ≥ 0: no pueden explotar la regeneración "
                "de batería, por eso ambos llegan al mismo consumo (A* solo busca "
                "más rápido gracias a su heurística, no reduce el costo)."
            )

    # ── Detalle de tramos, visible por defecto ──────────────────────────────
    with st.container(border=True):
        st.markdown("**[ DETALLE DE TRAMOS ]**")
        st.dataframe(
            pd.DataFrame([{
                "TRAMO": f"{t['De']} → {t['→']}",
                "DIST (km)": t["Dist (km)"],
                "ENERG (Wh)": f"{float(t['Costo (J)'])/3600:.1f}",
                "ETA (h)": t["Tiempo (h)"],
            } for t in tramos]),
            use_container_width=True, hide_index=True,
        )

    st.markdown("")
    if st.session_state.fase_actual == 5:
        col_back5, col_next5 = st.columns([1, 2])
        with col_back5:
            _render_volver(4, "btn_volver_f5")
        with col_next5:
            if st.button(
                "▶  CONTINUAR → FASE 06",
                type="primary", key="btn_continuar_f5",
                use_container_width=True,
            ):
                st.session_state.nav_direction = "right"
                st.session_state.fase_actual = 6
                st.rerun()


# ── Fase 6 — Resultados y exportación ────────────────────────────────────────

def _render_contenido_fase6() -> None:
    _render_status_bar("MISIÓN LISTA  ·  TODOS LOS SISTEMAS OPERATIVOS")

    campo     = st.session_state.campo
    ruta      = st.session_state.ruta
    orden     = st.session_state.orden_f5
    grafo     = st.session_state.grafo
    todos     = st.session_state.todos
    wps       = st.session_state.wps
    cent      = st.session_state.cent
    base_nodo = st.session_state.base_nodo
    bat_ini   = st.session_state.bat_ini_j
    params    = st.session_state.params_f4

    bat      = estado_bateria(ruta, grafo, params.e_max, bateria_inicial=bat_ini)
    pct_min  = bat.minimo / params.e_max * 100
    bat_disp = bat_ini - bat.consumido
    drone    = st.session_state.drones[st.session_state.drone_key]

    # ── Fila de islas parejas: drone · batería · exportar ──────────────────
    isla_drone, isla_bateria, isla_export = st.columns(3)

    with isla_drone:
        with st.container(border=True):
            st.markdown("**[ DRONE ASIGNADO ]**")
            bat_pct = drone["pct_ini"]
            bat_bar = "█" * (bat_pct // 10) + "░" * (10 - bat_pct // 10)
            st.markdown(f"**{drone['nombre']}**")
            st.markdown(f"Batería: `{bat_bar}` {bat_pct}%")
            st.markdown(f"Vel: `{drone['s']:.1f} m/s`  ·  Rol: `PRINCIPAL`")

    with isla_bateria:
        with st.container(border=True):
            st.markdown("**[ BATERÍA DE MISIÓN ]**")
            st.markdown(f"Disponible: `{bat_disp/3600:.1f} Wh` (de {params.e_max/3600:.0f} Wh)")
            st.markdown(f"Mínima alcanzada: `{bat.minimo/3600:.1f} Wh` ({pct_min:.1f}%)")
            if not bat.viable:
                st.error("La batería llega a 0 en algún punto de la misión.")

    with isla_export:
        with st.container(border=True):
            st.markdown("**[ EXPORTAR ]**")
            col_csv, col_png, col_json = st.columns(3)
            with col_csv:
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["paso", "prof_m", "lat_deg", "lon_deg"])
                for paso, (p, i, j) in enumerate(ruta):
                    writer.writerow([
                        paso,
                        round(float(campo.prof[p]), 4),
                        round(float(campo.lat[i]), 6),
                        round(float(campo.lon[j]), 6),
                    ])
                st.download_button(
                    label="CSV", data=buf.getvalue().encode("utf-8"),
                    file_name="ruta_auv.csv", mime="text/csv",
                    use_container_width=True,
                )
            with col_png:
                fig_png, ax_png = plt.subplots(figsize=(9, 7))
                plot_ruta(campo, ruta, waypoints=wps, centinelas=cent, base=base_nodo, ax=ax_png)
                png_bytes = _fig_a_bytes(fig_png)
                plt.close(fig_png)
                st.download_button(
                    label="PNG", data=png_bytes,
                    file_name="ruta_auv.png", mime="image/png",
                    use_container_width=True,
                )
            with col_json:
                ruta_json = json.dumps([
                    {
                        "paso": k,
                        "prof_m": round(float(campo.prof[p]), 4),
                        "lat_deg": round(float(campo.lat[i]), 6),
                        "lon_deg": round(float(campo.lon[j]), 6),
                    }
                    for k, (p, i, j) in enumerate(ruta)
                ])
                st.download_button(
                    label="JSON", data=ruta_json.encode(),
                    file_name="ruta_auv.json", mime="application/json",
                    use_container_width=True,
                )

    # ── Visualizaciones en 3 paneles a tercio de ancho c/u ──────────────────
    col_mapa6, col_bat6, col_3d6 = st.columns(3)

    with col_3d6:
        with st.container(border=True):
            st.markdown("**[ VISTA 3D ]**")
            try:
                import plotly.graph_objects as go  # noqa: F401
                fig_3d = plot_grafo_3d(
                    grafo, campo,
                    ruta=ruta, waypoints=wps, centinelas=cent, base=base_nodo,
                )
                st.plotly_chart(fig_3d, use_container_width=True, height=420)
                st.caption("🟩 Regeneración  ·  🟥 Consumo  ·  ── Ruta AUV")
            except ImportError:
                st.info("Para ver la visualización 3D, instale plotly: `pip install plotly`")

    with col_mapa6:
        with st.container(border=True):
            st.markdown("**[ MAPA ]**")
            fig2d, ax2d = plt.subplots(figsize=(6, 5))
            plot_ruta(campo, ruta, waypoints=wps, centinelas=cent, base=base_nodo, ax=ax2d)
            st.pyplot(fig2d, use_container_width=True)
            plt.close(fig2d)
            st.caption("━ RUTA · ⬤ ZONA CONV. · ⬤ CENTINELA · ⬤ BASE")

    with col_bat6:
        with st.container(border=True):
            st.markdown("**[ PERFIL DE BATERÍA ]**")
            st.markdown(
                f"Disp.: `{bat_disp/3600:.1f} Wh`  \n"
                f"Cons.: `{bat.consumido/3600:.1f} Wh`  \n"
                f"Cap.: `{params.e_max/3600:.0f} Wh`"
            )
            fig_bat, ax_bat = plt.subplots(figsize=(6, 5))
            plot_bateria(
                campo, ruta, bat.niveles, params.e_max,
                waypoints=todos, orden=orden, ax=ax_bat,
            )
            st.pyplot(fig_bat, use_container_width=True)
            plt.close(fig_bat)

    # ── Acción final ────────────────────────────────────────────────────────
    st.markdown("")
    col_back6, col_exec6 = st.columns([1, 2])
    with col_back6:
        _render_volver(5, "btn_volver_f6")
    with col_exec6:
        if st.button(
            "[  EJECUTAR MISIÓN  ]",
            type="primary",
            use_container_width=True,
            key="btn_ejecutar",
        ):
            st.success("Misión enviada al AUV. Secuencia de waypoints transmitida.")
            st.balloons()


# ── Layout principal ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Planificador AUV — Lima",
    page_icon=None,
    layout="wide",
)

st.markdown(_ESTILOS, unsafe_allow_html=True)
_init_state()
_render_sidebar()
_render_stepper()
st.divider()
_render_fase_actual()

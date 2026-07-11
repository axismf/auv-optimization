<div align="center">

# 🌊 Planificador de Rutas AUV

**Planificación de rutas de mínima energía para Vehículos Submarinos Autónomos
usando datos de corrientes marinas, Bellman-Ford y TSP asimétrico.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.45+-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Tests](https://img.shields.io/badge/tests-42%20passing-brightgreen?style=flat-square)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

[**Demo en vivo**](https://auv-optimization.streamlit.app/) · [**Informe técnico**](informe/main.pdf)

English · [**English README**](README_EN.md)

</div>

---

## ¿Qué es esto?

Un AUV (Vehículo Submarino Autónomo) planifica una misión a lo largo de la
costa peruana para monitorear zonas de convergencia de contaminantes. El
sistema debe encontrar la **ruta de mínima energía** — porque cada joule
cuenta cuando estás bajo el agua con una batería finita.

La clave: **las corrientes marinas pueden ayudar y perjudicar**. Moverse a
favor de la corriente recarga batería (peso negativo). Moverse en contra la
gasta más rápido. Esto hace que el problema sea fundamentalmente diferente
al de caminos mínimos estándar.

```
 ┌─────────────────────────────────────────────────────────────┐
 │  Copernicus Marine    →    Grafo Dirigido    →    Ruta     │
 │  Datos NetCDF oceánicos    (Bellman-Ford)       Óptima     │
 │  (uo, vo corrientes)       con pesos             (ATSP)    │
 │                             negativos                       │
 └─────────────────────────────────────────────────────────────┘
```

| Ruta 2D | Zonas de Misión | Grafo de Costos |
|:---:|:---:|:---:|
| ![Ruta 2D](informe/media/ruta_2d.png) | ![Zonas](informe/media/zonas_mision.png) | ![Grafo](informe/media/grafo_costos.png) |

| Corrientes | Perfil de Batería |
|:---:|:---:|
| ![Corrientes](informe/media/campo_corrientes.png) | ![Batería](informe/media/bateria.png) |

---

## ¿Cómo funciona?

### 1. Datos oceánicos como grafo

El océano se discretiza en una grilla 3D (lat × lon × profundidad). Cada
celda navegable es un **nodo**. Cada celda se conecta con sus **26 vecinos**
(vecindario de Moore 3D) mediante aristas dirigidas.

El peso de cada arista es la **energía neta** para recorrerla:

```
E_neta = E_arr − E_regen + E_grav

donde:
  E_arr    = k_p · ‖v_r‖³ · Δt       (ecuación de arrastre NASA)
  E_regen  = k_r · η · ‖v_c‖³ · Δt   (regeneración turbina)
  E_grav   = m · g · |Δz| / η          (movimiento vertical)
  v_r      = s·ê − v_c                 (velocidad relativa al agua)
```

Cuando la corriente empuja al AUV hacia adelante, `E_regen > E_arr` → **peso
negativo**. Ahí es donde Bellman-Ford le gana a Dijkstra.

### 2. Selección de zonas de misión

Las zonas no se eligen a mano. Se derivan de la **divergencia horizontal**
del campo de corrientes:

```
div = ∂uo/∂x + ∂vo/∂y
```

Donde `div < 0`, el flujo converge — los contaminantes se acumulan ahí.
Las celdas de mayor convergencia se vuelven **waypoints**. Se agregan
**celdas centinela** offshore para detección temprana de derrames.

### 3. Ruta óptima (Bellman-Ford + ATSP)

- **Bellman-Ford** encuentra el camino de mínima energía entre cada par de
  zonas (maneja pesos negativos por regeneración).
- La matriz de costos resultante alimenta un solver de **Problema del
  Viajante Asimétrico** (enumeración exacta) para encontrar el orden de
  visita óptimo.
- Un detector de ciclos negativos valida el modelo antes de resolver.

---

## Características

- **Flujo de trabajo interactivo de 6 fases**: Datos → Corrientes → Zonas → Grafo → ATSP → Misión
- **6 presets de AUV**: REMUS 100, REMUS 600, REMUS 620, Bluefin-9, Genérico, Prueba
- **8 bases portuarias peruanas** preconfiguradas + bases personalizadas
- **Carga de NetCDF personalizada** con detección automática de variables CMEMS
- **Ajuste de parámetros en tiempo real**: velocidad, eficiencia, coeficientes, batería
- **Comparativa de algoritmos**: Bellman-Ford vs Dijkstra/A* (muestra ventaja de regeneración)
- **Visualización 3D interactiva** con Plotly (aristas coloreadas por signo de energía)
- **Exportación**: CSV, PNG, JSON de la ruta
- **Tema marino oscuro** con diseño industrial

---

## Arquitectura

```
rutas-auv/
├── src/                        # Núcleo (cero dependencia de Streamlit)
│   ├── config.py               # ParametrosModelo — dataclass inmutable
│   ├── datos.py                # Cargador NetCDF + resolución de alias CMEMS
│   ├── grafo.py                # Grafo dirigido + función de costo energético
│   ├── zonas.py                # Divergencia, selección de waypoints y centinelas
│   ├── algoritmos.py           # Bellman-Ford, matriz de costos, solver ATSP
│   ├── metricas.py             # Simulación de batería + exportación CSV
│   └── visualizacion.py        # Gráficos Matplotlib + Plotly (framework-agnostic)
├── app.py                      # Interfaz Streamlit (capa de presentación)
├── data/                       # Datasets NetCDF (CMEMS)
├── tests/                      # 42 pruebas unitarias
├── informe/                    # Informe técnico (Typst → PDF)
└── assets/                     # Imágenes de drones
```

**Regla de dependencias**: `src/` nunca importa de `app.py`. El núcleo es
framework-agnostic — la UI puede cambiarse por Flask, FastAPI o una CLI
sin tocar los algoritmos.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Algoritmos | Python, NumPy, itertools |
| Datos | xarray, NetCDF4 (Copernicus Marine CMEMS) |
| Visualización | Matplotlib (2D), Plotly (3D interactivo) |
| UI | Streamlit ≥ 1.45 |
| Testing | pytest |
| Informe | Typst |

---

## Inicio rápido

```bash
# Clonar
git clone https://github.com/axismf/auv-optimization.git
cd rutas-auv

# Instalar
pip install -r requirements.txt

# Ejecutar
streamlit run app.py

# Tests
pytest
```

La app carga un dataset de ejemplo (`data/Lima-New.nc`) automáticamente.
También podés subir tu propio NetCDF de Copernicus Marine.

---

## Testing

```bash
$ pytest

..........................................                    [100%]
42 passed in 1.36s
```

Los tests cubren: corrección de Bellman-Ford, detección de ciclos negativos,
optimalidad del ATSP, construcción del grafo, función de costo, selección de
waypoints, simulación de batería y cálculo de métricas.

---

## Contexto

Este proyecto fue desarrollado como parte de una tesis de pregrado sobre
planificación de misiones de AUV para monitoreo ambiental a lo largo de la
costa peruana. El modelo energético se basa en:

- **Ecuación de Arrastre NASA** para resistencia hidrodinámica
- Modelo de **regeneración turbina** (Sun et al., 2022)
- **Divergencia horizontal** para detección de convergencia de contaminantes
- **Bellman-Ford** para caminos mínimos con pesos negativos
- **Enumeración exacta ATSP** para secuenciación óptima de visita

---

<div align="center">

**Hecho con Python** 🐍

</div>

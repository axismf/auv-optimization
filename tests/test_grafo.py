"""Tests para src/grafo.py — Grafo, GrafoBase, construir_grafo, costo_arista."""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.grafo import Grafo, Nodo, costo_arista
from src.config import ParametrosModelo
from src.datos import CampoCorrientes


# ── Grafo.agregar_nodo / agregar_arista ──────────────────────────────────────

def test_grafo_agrega_nodo():
    g = Grafo()
    n: Nodo = (0, 0, 0)
    g.agregar_nodo(n)
    assert g.num_nodos == 1
    assert g.num_aristas == 0


def test_grafo_agrega_arista_implica_ambos_nodos():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_arista(a, b, 5.0)
    assert g.num_nodos == 2
    assert g.num_aristas == 1


def test_grafo_vecinos_vacios_nodo_sin_salidas():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_arista(a, b, 2.0)
    assert g.vecinos(b) == []


# ── Grafo.peso ───────────────────────────────────────────────────────────────

def test_peso_devuelve_valor_arista_existente():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_arista(a, b, 7.5)
    assert g.peso(a, b) == pytest.approx(7.5)


def test_peso_devuelve_none_arista_inexistente():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_nodo(a)
    g.agregar_nodo(b)
    assert g.peso(a, b) is None


def test_peso_arista_negativa():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_arista(a, b, -3.0)
    assert g.peso(a, b) == pytest.approx(-3.0)


def test_peso_no_confunde_direccion():
    g = Grafo()
    a, b = (0, 0, 0), (0, 0, 1)
    g.agregar_arista(a, b, 1.0)
    assert g.peso(b, a) is None


# ── Grafo.nodos / aristas ────────────────────────────────────────────────────

def test_nodos_incluye_extremos_arista():
    g = Grafo()
    a, b = (0, 0, 0), (0, 1, 0)
    g.agregar_arista(a, b, 1.0)
    assert set(g.nodos()) == {a, b}


def test_aristas_itera_correctamente():
    g = Grafo()
    a, b, c = (0, 0, 0), (0, 0, 1), (0, 1, 0)
    g.agregar_arista(a, b, 2.0)
    g.agregar_arista(b, c, 3.0)
    resultado = list(g.aristas())
    assert (a, b, 2.0) in resultado
    assert (b, c, 3.0) in resultado
    assert len(resultado) == 2


# ── costo_arista — fixtures ──────────────────────────────────────────────────

@pytest.fixture
def campo_mock():
    """CampoCorrientes mínimo 2×2×2 para testing de costo_arista.

    Grid: prof=[0, 10], lat=[-12.0, -11.9], lon=[-77.1, -77.0]
    Todos los nodos naveganbles, corrientes controladas por test.
    """
    lat = np.array([-12.0, -11.9])
    lon = np.array([-77.1, -77.0])
    prof = np.array([0.0, 10.0])

    # Corrientes: uo (zonal), vo (meridional) — se configuran por test
    uo = np.zeros((2, 2, 2))
    vo = np.zeros((2, 2, 2))
    navegable = np.ones((2, 2, 2), dtype=bool)

    return CampoCorrientes(lat, lon, prof, uo, vo, navegable)


@pytest.fixture
def campo_vertical():
    """CampoCorrientes con cambio de profundidad para test gravitacional."""
    lat = np.array([-12.0, -11.9])
    lon = np.array([-77.1, -77.0])
    prof = np.array([0.0, 10.0])

    uo = np.zeros((2, 2, 2))
    vo = np.zeros((2, 2, 2))
    navegable = np.ones((2, 2, 2), dtype=bool)

    return CampoCorrientes(lat, lon, prof, uo, vo, navegable)


@pytest.fixture
def params():
    """ParametrosModelo con valores realistas para testing."""
    return ParametrosModelo(s=0.5, m=100.0, g=9.81, rho=1025.0, C_d=1.24)


# ── costo_arista — tests ────────────────────────────────────────────────────

def test_costo_arista_zero_current(campo_mock, params):
    """Caso base: sin corriente, v_paralela=0 < s → propulsión."""
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost = costo_arista(origen, destino, campo_mock, params)
    assert cost > 0  # propulsión (v_paralela=0 < s=0.5)
    assert not math.isinf(cost)


def test_costo_arista_favorable_current(campo_mock, params):
    """Corriente favorable (0.2 < s=0.5): v_g mayor, tiempo menor, menos arrastre."""
    # Corriente en dirección del movimiento (eje lon, componente zonal positiva)
    campo_mock.uo[0, 0, 0] = 0.2  # corriente favorable (pero < s)
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost_favorable = costo_arista(origen, destino, campo_mock, params)

    # Sin corriente para comparar
    campo_mock.uo[0, 0, 0] = 0.0
    cost_base = costo_arista(origen, destino, campo_mock, params)

    # Con corriente favorable: v_g mayor → tiempo menor → menos arrastre → menor costo
    assert cost_favorable < cost_base  # menor costo con corriente favorable
    assert not math.isinf(cost_favorable)


def test_costo_arista_adverse_current(campo_mock, params):
    """Corriente adversa aumenta tiempo y costo energético."""
    # Corriente en contra del movimiento
    campo_mock.uo[0, 0, 0] = -0.2  # corriente adversa
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost_adverso = costo_arista(origen, destino, campo_mock, params)

    # Sin corriente para comparar
    campo_mock.uo[0, 0, 0] = 0.0
    cost_base = costo_arista(origen, destino, campo_mock, params)

    assert cost_adverso > cost_base  # mayor costo con corriente adversa


def test_costo_arista_infeasible_edge(campo_mock, params):
    """v_g <= 0 retorna inf (arista infactible)."""
    # Corriente adversa fuerte: |v_paralela| >= s
    campo_mock.uo[0, 0, 0] = -0.6  # |0.6| > s=0.5
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost = costo_arista(origen, destino, campo_mock, params)
    assert math.isinf(cost)


def test_costo_arista_gravitational_energy(campo_vertical, params):
    """Cambio de profundidad agrega energía gravitacional."""
    # Movimiento vertical: profundidad 0 → 10
    origen = (0, 0, 0)
    destino = (1, 0, 0)  # cambio de profundidad
    cost = costo_arista(origen, destino, campo_vertical, params)

    # Debe incluir término gravitacional: m*g*|dz|/eta = 100*9.81*10/0.3
    e_grav_esperado = 100.0 * 9.81 * 10.0 / 0.3
    # Costo ≈ e_grav (menos pequeña regeneración por v_r vertical)
    assert cost == pytest.approx(e_grav_esperado, rel=0.01)  # within 1%


def test_costo_arista_regeneration_threshold(campo_mock, params):
    """Regeneración se activa cuando ‖v_c‖ >= s (corriente tan fuerte como crucero)."""
    # Corriente fuerte (magnitud >= s=0.5) → regeneración
    campo_mock.uo[0, 0, 0] = 0.6  # magnitud > s=0.5
    campo_mock.vo[0, 0, 0] = 0.0
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost = costo_arista(origen, destino, campo_mock, params)
    assert cost < 0  # regeneración (costo negativo)


def test_costo_arista_regeneration_not_exceeds_e_max(campo_mock, params):
    """Regeneración no excede e_max."""
    # Corriente muy fuerte (magnitud > s=0.5)
    campo_mock.uo[0, 0, 0] = 0.7
    campo_mock.vo[0, 0, 0] = 0.0
    origen = (0, 0, 0)
    destino = (0, 0, 1)
    cost = costo_arista(origen, destino, campo_mock, params)
    assert cost >= -params.e_max  # no excede capacidad de batería

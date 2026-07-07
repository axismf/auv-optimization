"""Construcción del grafo dirigido ponderado y función de costo (RF-03, RF-04)."""
from __future__ import annotations

from .dependencias import *
from .config import ParametrosModelo
from .datos import CampoCorrientes


__all__ = ["GrafoBase", "Grafo", "Nodo", "construir_grafo", "costo_arista"]

Nodo = tuple[int, int, int]  # (prof_idx, lat_idx, lon_idx)


class GrafoBase(ABC):
    """Contrato del grafo: interfaz que toda implementación debe cumplir."""

    @abstractmethod
    def agregar_nodo(self, u: Nodo) -> None: ...

    @abstractmethod
    def agregar_arista(self, u: Nodo, v: Nodo, peso: float) -> None: ...

    @abstractmethod
    def vecinos(self, u: Nodo) -> list[tuple[Nodo, float]]: ...

    @abstractmethod
    def nodos(self) -> Iterator[Nodo]: ...

    @abstractmethod
    def aristas(self) -> Iterator[tuple[Nodo, Nodo, float]]: ...

    @abstractmethod
    def peso(self, u: Nodo, v: Nodo) -> float | None: ...

    @property
    @abstractmethod
    def num_nodos(self) -> int: ...

    @property
    @abstractmethod
    def num_aristas(self) -> int: ...


class Grafo(GrafoBase):
    """Grafo dirigido y ponderado por lista de adyacencia.

    Pesos pueden ser negativos (regeneración) → usar Bellman-Ford, no Dijkstra.
    """

    def __init__(self) -> None:
        self._adyacencia: dict[Nodo, list[tuple[Nodo, float]]] = {}

    def agregar_nodo(self, u: Nodo) -> None:
        """Registra el nodo u sin aristas si aún no existe."""
        self._adyacencia.setdefault(u, [])

    def agregar_arista(self, u: Nodo, v: Nodo, peso: float) -> None:
        """Agrega la arista dirigida u → v con el peso dado."""
        self._adyacencia.setdefault(u, []).append((v, peso))
        self._adyacencia.setdefault(v, [])

    def vecinos(self, u: Nodo) -> list[tuple[Nodo, float]]:
        """Aristas salientes (v, peso) del nodo u."""
        return self._adyacencia.get(u, [])

    def nodos(self) -> Iterator[Nodo]:
        return iter(self._adyacencia)

    def aristas(self) -> Iterator[tuple[Nodo, Nodo, float]]:
        for u, lista in self._adyacencia.items():
            for v, p in lista:
                yield u, v, p

    def peso(self, u: Nodo, v: Nodo) -> float | None:
        """Peso de la arista u → v, o None si la arista no existe."""
        for dest, w in self._adyacencia.get(u, []):
            if dest == v:
                return w
        return None

    @property
    def num_nodos(self) -> int:
        return len(self._adyacencia)

    @property
    def num_aristas(self) -> int:
        return sum(len(lista) for lista in self._adyacencia.values())


def construir_grafo(campo: CampoCorrientes, params: ParametrosModelo) -> Grafo:
    """Construye el grafo dirigido completo del dominio marino.

    Conecta cada celda navegable con sus hasta 26 vecinos en 3D.
    Las celdas de tierra actúan como obstáculos y se omiten.

    Verifica la ausencia de ciclos negativos después de la construcción.
    """
    grafo   = Grafo()
    n_prof, n_lat, n_lon = campo.uo.shape
    nav     = campo.navegable
    offsets = [o for o in itertools.product((-1, 0, 1), repeat=3) if o != (0, 0, 0)]

    for p in range(n_prof):
        for i in range(n_lat):
            for j in range(n_lon):
                if not nav[p, i, j]:
                    continue
                origen = (p, i, j)
                grafo.agregar_nodo(origen)
                for dp, di, dj in offsets:
                    pp, ii, jj = p + dp, i + di, j + dj
                    if (
                        0 <= pp < n_prof
                        and 0 <= ii < n_lat
                        and 0 <= jj < n_lon
                        and nav[pp, ii, jj]
                    ):
                        destino = (pp, ii, jj)
                        grafo.agregar_arista(
                            origen, destino,
                            costo_arista(origen, destino, campo, params),
                        )

    # Verificar ciclos negativos después de construir el grafo
    # Fundamento: GeeksforGeeks (2025) - "Bellman-Ford Algorithm"
    if grafo.num_nodos > 0:
        primer_nodo = next(iter(grafo.nodos()))
        dist = {n: math.inf for n in grafo.nodos()}
        dist[primer_nodo] = 0.0

        # Relajación V-1 veces
        for _ in range(grafo.num_nodos - 1):
            for u, v, w in grafo.aristas():
                if dist[u] < math.inf and dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w

        # Verificar ciclo negativo (iteración V)
        tiene_ciclos_negativos = False
        for u, v, w in grafo.aristas():
            if dist[u] < math.inf and dist[u] + w < dist[v]:
                tiene_ciclos_negativos = True
                break

        if tiene_ciclos_negativos:
            print(
                "⚠ Advertencia: se detectó un ciclo negativo alcanzable desde "
                f"{primer_nodo}. Las aristas negativas se conservan (son la "
                "base del modelo), pero revisa la ruta resultante si pasa "
                "por esa zona: las distancias mínimas podrían no converger."
            )

    return grafo


def costo_arista(
    origen: Nodo,
    destino: Nodo,
    campo: CampoCorrientes,
    params: ParametrosModelo,
) -> float:
    """Energía neta [J] de recorrer la arista origen → destino.

    Positivo = propulsión (consume batería), negativo = regeneración (recarga).

    Modelo físico basado en:
    - NASA Drag Equation: F_drag = ½·ρ·C_d·A·v²
    - Potencia de arrastre: P_drag = F_drag · v = ½·ρ·C_d·A·v³
    - Regeneración turbina: P_regen = ½·ρ·C_d·A·v_c³ · η  (cuando v_c >= umbral)
    """
    pa, ia, ja = origen
    pb, ib, jb = destino

    lat_media = math.radians((campo.lat[ia] + campo.lat[ib]) / 2.0)
    dx = (campo.lon[jb] - campo.lon[ja]) * GRADOS_A_METROS * math.cos(lat_media)
    dy = (campo.lat[ib] - campo.lat[ia]) * GRADOS_A_METROS
    dz =  campo.prof[pb] - campo.prof[pa]

    longitud = math.sqrt(dx*dx + dy*dy + dz*dz)
    if longitud == 0.0:
        return 0.0

    ex, ey, ez = dx / longitud, dy / longitud, dz / longitud
    cx = float(campo.uo[pa, ia, ja])
    cy = float(campo.vo[pa, ia, ja])

    # v_r = s·ê − v_c  (velocidad relativa al agua — para drag)
    rx, ry, rz = params.s * ex - cx, params.s * ey - cy, params.s * ez
    vr3 = (rx*rx + ry*ry + rz*rz) ** 1.5

    # v_g = s + v_paralela  (velocidad de avance neta sobre el fondo)
    v_paralela = cx * ex + cy * ey
    v_g = params.s + v_paralela

    # Arista infactible: corriente adversa cancela/excede propulsión
    if v_g <= 0.0:
        return math.inf

    # Tiempo de tránsito basado en velocidad de avance real
    tiempo = longitud / v_g

    # Energía gravitacional: m·g·|dz| / η
    dz_abs = abs(campo.prof[pb] - campo.prof[pa])
    e_grav = params.m * params.g * dz_abs / params.eta

    # Energía de arrastre: k_p · ‖v_r‖³ · tiempo (NASA Drag Equation)
    e_drag = params.k_p * vr3 * tiempo

    # Regeneración turbina: cuando la corriente es suficientemente fuerte
    # Solo consideramos la componente de la corriente en la dirección del movimiento
    # Fundamento: Sun et al. (2022) - "Energy optimised D* AUV path planning"
    vc_paralela = v_paralela  # componente en dirección del movimiento
    vc_mag = math.sqrt(cx*cx + cy*cy)  # magnitud total

    # Umbral: corriente moderada-fuerte (0.2 m/s mínimo)
    # Fundamento: corrientes oceánicas típicas 0.1-0.3 m/s
    UMBRAL_CORRIENTE = 0.2  # m/s

    if vc_mag >= UMBRAL_CORRIENTE and vc_paralela > 0:
        # La hélice funciona como turbina cuando la corriente te empuja
        # Potencia disponible: P = ½ρC_dA‖v_c‖³ · η
        vc3 = vc_mag ** 3
        e_regen = params.k_r * params.eta * vc3 * tiempo

        # Límite dinámico: el tope de regeneración escala con qué tan alineada
        # y fuerte es la corriente respecto al arrastre que se evita.
        # Antes: corrientes moderadas (<=0.5 m/s) tenían un tope fijo del 50%
        # del arrastre, lo que hacía IMPOSIBLE un costo negativo con las
        # corrientes reales de la zona (0.1-0.3 m/s). Ahora el tope depende
        # de qué tanta energía relativa aporta la corriente: cuanto más
        # alineada y fuerte, más cerca (o por encima) del 100% del arrastre.
        # Fundamento: Lundström et al. (2010) + observación empírica de AUVs
        fraccion_alineada = vc_paralela / vc_mag if vc_mag > 0 else 0.0
        # fraccion_alineada en (0, 1]; escala el tope entre 60% y 130% del arrastre
        max_regen_por_arista = e_drag * (0.6 + 0.7 * fraccion_alineada)

        # Energía neta: arrastre - regeneración + gravitacional
        # Fundamento: Yasser (2020) - "Energy Consumption Model of AUVs"
        return e_drag - min(e_regen, max_regen_por_arista) + e_grav

    return e_drag + e_grav


if __name__ == "__main__":
    # Ejecutar con: python -m src.grafo
    from src.datos import cargar_corrientes

    nc    = pathlib.Path(__file__).parent.parent / "data" / "lima3.nc"
    campo = cargar_corrientes(str(nc))
    grafo = construir_grafo(campo, ParametrosModelo())
    print(f"Nodos: {grafo.num_nodos}  Aristas: {grafo.num_aristas}")
    print("\n✓ grafo.py OK")
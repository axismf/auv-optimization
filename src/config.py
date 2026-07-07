"""Parámetros de configuración del modelo energético del AUV."""
from __future__ import annotations

from .dependencias import *


__all__ = ["ParametrosModelo"]


# ════════════════════════════════════════════════════════════════
#  DECLARACIÓN
# ════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ParametrosModelo:
    """Parámetros físicos y de misión del planificador de rutas.

    Attributes:
        s:                  Velocidad de crucero respecto al agua [m/s].
        k_p:                Coeficiente de costo en régimen de propulsión.
        k_r:                Coeficiente de recuperación en regeneración.
        eta:                Eficiencia de conversión de la regeneración, en (0, 1).
        e_max:              Capacidad máxima de batería [J].
        k_zonas:            Número de zonas de convergencia a visitar.
        resolucion_grados:  Tamaño de celda de la malla [grados].
        m:                  Masa del AUV [kg].
        g:                  Aceleración gravitacional [m/s²].
        rho:                Densidad del agua de mar [kg/m³].
        C_d:                Coeficiente de arrastre hidrodinámico [-].
    """

    # ── campos ───────────────────────────────────────────────────────────────
    s: float = 1.0           # m/s — velocidad de crucero (REMUS 100: 1-2 m/s)
    k_p: float = 18.0        # ½ · ρ · C_d_eff · A (calibrado con REMUS 100 real: ~18 kJ/km)
    k_r: float = 1.0
    eta: float = 0.3
    e_max: float = 3.6e6     # J — batería REMUS 100 (1 kWh = 3.6 MJ)
    k_zonas: int = 6
    resolucion_grados: float = 1.0 / 12.0
    m: float = 37.0          # kg — masa REMUS 100
    g: float = 9.81
    rho: float = 1025.0
    C_d: float = 1.24        # coeficiente de arrastre efectivo (incluye fricción + apéndices)

    # ── implementación ───────────────────────────────────────────────────────
    def __post_init__(self) -> None:
        if not 0.0 < self.eta < 1.0:
            raise ValueError("eta debe estar en el intervalo (0, 1).")
        if self.s <= 0.0:
            raise ValueError("La velocidad de crucero s debe ser positiva.")
        if self.k_zonas < 2:
            raise ValueError("Se requieren al menos 2 zonas para una ruta.")
        if self.m <= 0.0:
            raise ValueError("La masa m debe ser positiva.")
        if self.rho <= 0.0:
            raise ValueError("La densidad rho debe ser positiva.")

"""Pronóstico de partidos del Mundial 2026 mediante un modelo Elo propio.

No usa ninguna API externa ni IA: el porcentaje se calcula localmente a partir
de ratings Elo de selecciones (valores públicos aproximados, estilo
eloratings.net) y una fórmula logística estándar para fútbol.

Salida principal: ``forecast(home_name, away_name)`` -> ``(p_local, p_empate, p_visita)``
con tres porcentajes que suman 100.

Cómo funciona el modelo
------------------------
1. Cada selección tiene un rating Elo. La diferencia de rating (ajustada por la
   ventaja de localía) determina el resultado esperado del local ``We`` con la
   curva logística clásica de Elo:

       dr = (elo_local + VENTAJA_LOCAL) - elo_visita
       We = 1 / (1 + 10 ** (-dr / 400))

   ``We`` está en [0, 1] y mezcla "ganar" + medio "empatar" (es el valor
   esperado de puntos normalizado del local).

2. El fútbol tiene muchos empates, así que repartimos: estimamos primero la
   probabilidad de empate ``p_draw`` en función de lo parejo que sea el duelo
   (más parejo => más empate) y luego distribuimos el resto entre local y visita
   de forma consistente con ``We``.

Los ratings son configurables/expandibles editando ``_ELO``. Si una selección no
está en el mapa, se usa ``DEFAULT_ELO``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Ventaja de jugar en casa, en puntos Elo. En selecciones suele estimarse menor
# que en clubes; ~65 es un valor habitual. Para el Mundial 2026 (sedes USA/MEX/CAN)
# solo los anfitriones juegan "en casa" de verdad, pero ESPN marca un home/away
# nominal en cada partido y lo respetamos como pequeña ventaja.
HOME_ADVANTAGE: float = 65.0

# Controla cuánto empate hay como máximo en un partido perfectamente parejo.
# 0.28 => hasta ~28% de empate en duelos igualados; baja al alejarse la paridad.
MAX_DRAW_PROB: float = 0.28

# Qué tan rápido cae la probabilidad de empate cuando el duelo es desparejo.
# Mayor => el empate se desploma con poca diferencia de Elo.
DRAW_SHARPNESS: float = 1.6

DEFAULT_ELO: float = 1600.0


# Ratings Elo aproximados de selecciones (clave = displayName inglés de ESPN en
# minúsculas, igual que en app/teams.py). Valores de referencia estilo
# eloratings.net (orden de 2025/2026); ajústalos cuando quieras recalibrar.
_ELO: dict[str, float] = {
    # --- Élite ---
    "argentina": 2103.0,
    "france": 2080.0,
    "spain": 2068.0,
    "england": 1985.0,
    "brazil": 1995.0,
    "portugal": 1975.0,
    "netherlands": 1970.0,
    "belgium": 1915.0,
    "italy": 1910.0,
    "germany": 1925.0,
    "croatia": 1880.0,
    # --- Muy fuertes ---
    "uruguay": 1900.0,
    "colombia": 1870.0,
    "morocco": 1840.0,
    "switzerland": 1835.0,
    "denmark": 1820.0,
    "usa": 1800.0,
    "united states": 1800.0,
    "mexico": 1790.0,
    "méxico": 1790.0,
    "japan": 1830.0,
    "senegal": 1800.0,
    "ecuador": 1790.0,
    "austria": 1810.0,
    # --- Fuertes ---
    "ukraine": 1770.0,
    "serbia": 1765.0,
    "iran": 1760.0,
    "south korea": 1755.0,
    "korea republic": 1755.0,
    "peru": 1735.0,
    "sweden": 1745.0,
    "wales": 1740.0,
    "poland": 1735.0,
    "nigeria": 1730.0,
    "egypt": 1725.0,
    "turkey": 1755.0,
    "türkiye": 1755.0,
    "turkiye": 1755.0,
    "algeria": 1740.0,
    "scotland": 1730.0,
    "canada": 1720.0,
    "australia": 1715.0,
    "chile": 1730.0,
    "ivory coast": 1720.0,
    "cote d'ivoire": 1720.0,
    "norway": 1745.0,
    "czechia": 1725.0,
    "czech republic": 1725.0,
    "tunisia": 1710.0,
    "cameroon": 1705.0,
    "ghana": 1700.0,
    "mali": 1700.0,
    # --- Medios ---
    "paraguay": 1690.0,
    "qatar": 1680.0,
    "costa rica": 1670.0,
    "saudi arabia": 1665.0,
    "south africa": 1690.0,
    "venezuela": 1685.0,
    "greece": 1700.0,
    "hungary": 1715.0,
    "slovakia": 1690.0,
    "slovenia": 1685.0,
    "romania": 1690.0,
    "ireland": 1680.0,
    "republic of ireland": 1680.0,
    "iraq": 1660.0,
    "jordan": 1645.0,
    "uzbekistan": 1660.0,
    "burkina faso": 1665.0,
    "cape verde": 1640.0,
    "dr congo": 1660.0,
    "congo dr": 1660.0,
    "democratic republic of the congo": 1660.0,
    "panama": 1650.0,
    "panamá": 1650.0,
    "jamaica": 1640.0,
    "honduras": 1620.0,
    "united arab emirates": 1620.0,
    "albania": 1660.0,
    "north macedonia": 1660.0,
    "bosnia and herzegovina": 1670.0,
    "bosnia-herzegovina": 1670.0,
    "finland": 1660.0,
    "iceland": 1650.0,
    "kosovo": 1620.0,
    "angola": 1610.0,
    "gabon": 1610.0,
    "guinea": 1640.0,
    # --- Más modestos ---
    "el salvador": 1560.0,
    "guatemala": 1560.0,
    "trinidad and tobago": 1545.0,
    "haiti": 1560.0,
    "curacao": 1540.0,
    "curaçao": 1540.0,
    "cuba": 1500.0,
    "bolivia": 1640.0,
    "new zealand": 1620.0,
    "north korea": 1620.0,
    "northern ireland": 1640.0,
}


def get_elo(display_name: str) -> float:
    """Rating Elo de una selección por su ``displayName`` inglés (ESPN)."""
    key = (display_name or "").strip().lower()
    return _ELO.get(key, DEFAULT_ELO)


def _expected_home_score(elo_home: float, elo_away: float) -> float:
    """Resultado esperado del local (0..1) con ventaja de localía incluida."""
    dr = (elo_home + HOME_ADVANTAGE) - elo_away
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))


def _draw_probability(elo_home: float, elo_away: float) -> float:
    """Probabilidad de empate según lo parejo que sea el duelo.

    En un duelo perfectamente igualado (dr=0) vale ``MAX_DRAW_PROB`` y decae
    suavemente conforme aumenta la diferencia de Elo efectiva.
    """
    dr = abs((elo_home + HOME_ADVANTAGE) - elo_away)
    # Normalizamos la diferencia: ~400 Elo ya es una brecha enorme.
    spread = (dr / 400.0) * DRAW_SHARPNESS
    decay = 1.0 / (1.0 + spread * spread)
    return MAX_DRAW_PROB * decay


def forecast(home_name: str, away_name: str) -> tuple[int, int, int]:
    """Pronóstico (p_local, p_empate, p_visita) en porcentajes enteros que suman 100.

    Parámetros usan el ``displayName`` inglés de ESPN (igual que ``app.teams``).
    """
    elo_home = get_elo(home_name)
    elo_away = get_elo(away_name)

    we = _expected_home_score(elo_home, elo_away)  # valor esperado del local 0..1
    p_draw = _draw_probability(elo_home, elo_away)

    # ``we`` ya incluye medio empate (Elo: victoria=1, empate=0.5, derrota=0),
    # es decir we = p_home + p_draw/2. Despejamos cada lado restando medio
    # empate a cada uno, lo que conserva el centro del duelo en ``we``.
    p_home = we - p_draw / 2.0
    p_away = (1.0 - we) - p_draw / 2.0

    # Salvaguarda numérica: en duelos extremos p_home/p_away podrían quedar < 0.
    p_home = max(0.0, p_home)
    p_away = max(0.0, p_away)
    total = p_home + p_draw + p_away
    if total <= 0:
        return (33, 34, 33)

    p_home /= total
    p_draw_n = p_draw / total
    p_away /= total

    return _to_int_percentages(p_home, p_draw_n, p_away)


def _to_int_percentages(a: float, b: float, c: float) -> tuple[int, int, int]:
    """Convierte tres probabilidades (suman ~1) a enteros que suman exactamente 100."""
    raw = [a * 100.0, b * 100.0, c * 100.0]
    floors = [int(x) for x in raw]
    remainder = 100 - sum(floors)
    # Reparte las unidades sobrantes a las mayores partes fraccionarias.
    fracs = sorted(range(3), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[fracs[i % 3]] += 1
    return (floors[0], floors[1], floors[2])


def forecast_line(home_name: str, away_name: str) -> str:
    """Línea compacta lista para mostrar, p. ej. ``L 58% · E 24% · V 18%``."""
    pl, pe, pv = forecast(home_name, away_name)
    return f"L {pl}% · E {pe}% · V {pv}%"

"""Mapeo de selecciones nacionales: nombre inglés (ESPN) -> (abreviatura ES, bandera).

La clave principal es el ``displayName`` en inglés que entrega ESPN. Como
respaldo, ``espn.py`` también guarda la abreviatura FIFA de 3 letras de ESPN,
que se usa cuando un equipo no está en este mapa (con bandera 🏳️).
"""

# nombre_ingles_lower -> (abreviatura_es, bandera_emoji)
_TEAMS: dict[str, tuple[str, str]] = {
    # CONMEBOL
    "argentina": ("ARG", "🇦🇷"),
    "bolivia": ("BOL", "🇧🇴"),
    "brazil": ("BRA", "🇧🇷"),
    "chile": ("CHI", "🇨🇱"),
    "colombia": ("COL", "🇨🇴"),
    "ecuador": ("ECU", "🇪🇨"),
    "paraguay": ("PAR", "🇵🇾"),
    "peru": ("PER", "🇵🇪"),
    "uruguay": ("URU", "🇺🇾"),
    "venezuela": ("VEN", "🇻🇪"),
    # CONCACAF
    "canada": ("CAN", "🇨🇦"),
    "costa rica": ("CRC", "🇨🇷"),
    "cuba": ("CUB", "🇨🇺"),
    "curacao": ("CUW", "🇨🇼"),
    "curaçao": ("CUW", "🇨🇼"),
    "el salvador": ("SLV", "🇸🇻"),
    "guatemala": ("GUA", "🇬🇹"),
    "haiti": ("HAI", "🇭🇹"),
    "honduras": ("HON", "🇭🇳"),
    "jamaica": ("JAM", "🇯🇲"),
    "mexico": ("MEX", "🇲🇽"),
    "méxico": ("MEX", "🇲🇽"),
    "panama": ("PAN", "🇵🇦"),
    "panamá": ("PAN", "🇵🇦"),
    "trinidad and tobago": ("TRI", "🇹🇹"),
    "united states": ("USA", "🇺🇸"),
    "usa": ("USA", "🇺🇸"),
    # UEFA
    "albania": ("ALB", "🇦🇱"),
    "austria": ("AUT", "🇦🇹"),
    "belgium": ("BEL", "🇧🇪"),
    "bosnia and herzegovina": ("BIH", "🇧🇦"),
    "bosnia-herzegovina": ("BIH", "🇧🇦"),
    "croatia": ("CRO", "🇭🇷"),
    "czechia": ("CHE", "🇨🇿"),
    "czech republic": ("CHE", "🇨🇿"),
    "denmark": ("DIN", "🇩🇰"),
    "england": ("ING", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "finland": ("FIN", "🇫🇮"),
    "france": ("FRA", "🇫🇷"),
    "germany": ("ALE", "🇩🇪"),
    "greece": ("GRE", "🇬🇷"),
    "hungary": ("HUN", "🇭🇺"),
    "iceland": ("ISL", "🇮🇸"),
    "ireland": ("IRL", "🇮🇪"),
    "republic of ireland": ("IRL", "🇮🇪"),
    "italy": ("ITA", "🇮🇹"),
    "kosovo": ("KOS", "🇽🇰"),
    "netherlands": ("HOL", "🇳🇱"),
    "north macedonia": ("MKD", "🇲🇰"),
    "northern ireland": ("IRN", "🏴"),
    "norway": ("NOR", "🇳🇴"),
    "poland": ("POL", "🇵🇱"),
    "portugal": ("POR", "🇵🇹"),
    "romania": ("RUM", "🇷🇴"),
    "scotland": ("ESC", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    "serbia": ("SRB", "🇷🇸"),
    "slovakia": ("ESV", "🇸🇰"),
    "slovenia": ("ESL", "🇸🇮"),
    "spain": ("ESP", "🇪🇸"),
    "sweden": ("SUE", "🇸🇪"),
    "switzerland": ("SUI", "🇨🇭"),
    "turkey": ("TUR", "🇹🇷"),
    "türkiye": ("TUR", "🇹🇷"),
    "turkiye": ("TUR", "🇹🇷"),
    "ukraine": ("UCR", "🇺🇦"),
    "wales": ("GAL", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
    # CAF
    "algeria": ("ALG", "🇩🇿"),
    "angola": ("ANG", "🇦🇴"),
    "burkina faso": ("BFA", "🇧🇫"),
    "cameroon": ("CAM", "🇨🇲"),
    "cape verde": ("CAB", "🇨🇻"),
    "democratic republic of the congo": ("RDC", "🇨🇩"),
    "dr congo": ("RDC", "🇨🇩"),
    "congo dr": ("RDC", "🇨🇩"),
    "egypt": ("EGI", "🇪🇬"),
    "gabon": ("GAB", "🇬🇦"),
    "ghana": ("GHA", "🇬🇭"),
    "guinea": ("GUI", "🇬🇳"),
    "ivory coast": ("CMA", "🇨🇮"),
    "cote d'ivoire": ("CMA", "🇨🇮"),
    "mali": ("MAL", "🇲🇱"),
    "morocco": ("MAR", "🇲🇦"),
    "nigeria": ("NGA", "🇳🇬"),
    "senegal": ("SEN", "🇸🇳"),
    "south africa": ("SUD", "🇿🇦"),
    "tunisia": ("TUN", "🇹🇳"),
    # AFC
    "australia": ("AUS", "🇦🇺"),
    "iran": ("IRA", "🇮🇷"),
    "iraq": ("IRK", "🇮🇶"),
    "japan": ("JAP", "🇯🇵"),
    "jordan": ("JOR", "🇯🇴"),
    "north korea": ("CDN", "🇰🇵"),
    "south korea": ("COR", "🇰🇷"),
    "korea republic": ("COR", "🇰🇷"),
    "qatar": ("QAT", "🇶🇦"),
    "saudi arabia": ("ARS", "🇸🇦"),
    "united arab emirates": ("EAU", "🇦🇪"),
    "uzbekistan": ("UZB", "🇺🇿"),
    # OFC
    "new zealand": ("NZL", "🇳🇿"),
}

_DEFAULT_FLAG = "🏳️"


def team_parts(display_name: str, espn_abbreviation: str = "") -> tuple[str, str]:
    """Devuelve (bandera, abreviatura) para una selección.

    - Busca por el ``display_name`` inglés en el mapa.
    - Si no está, usa la abreviatura de ESPN (o el nombre) con bandera 🏳️.
    """
    key = (display_name or "").strip().lower()
    entry = _TEAMS.get(key)
    if entry is not None:
        abbr, flag = entry
        return flag, abbr

    fallback_abbr = (espn_abbreviation or display_name or "?").strip().upper()
    return _DEFAULT_FLAG, fallback_abbr


def team_display(display_name: str, espn_abbreviation: str = "") -> str:
    """Devuelve 'BANDERA ABREVIATURA' para una selección."""
    flag, abbr = team_parts(display_name, espn_abbreviation)
    return f"{flag} {abbr}"

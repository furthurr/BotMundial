# BotMundial — Contexto completo del proyecto

> Documento de contexto para IA/desarrolladores. Describe **qué es**, **qué hace**,
> **cómo está construido** y **cómo opera** cada parte del proyecto. Si eres una IA
> leyendo esto, aquí tienes todo lo necesario para entender el sistema sin abrir
> el resto del código.

---

## 1. Resumen ejecutivo

**BotMundial** es un **bot privado de Telegram** escrito en Python que muestra
información del **Mundial de fútbol FIFA 2026** consumiendo la **API pública de
ESPN**. Es de acceso restringido: solo usuarios autorizados (mediante contraseñas
de un solo uso emitidas por el dueño) pueden usar los comandos de datos.

Funcionalidades principales:

- **Partidos** de ayer, hoy y mañana (con marcador, hora y estado en vivo).
- **Pronósticos** en porcentaje (local/empate/visita) de los partidos por jugar,
  calculados localmente con un **modelo Elo propio** (sin APIs externas ni IA).
- **Tabla de grupos** (posiciones, puntos, diferencia de gol).
- **Control de acceso** por contraseñas de un solo uso y un sistema de
  autorización persistido en SQLite.
- **Rate limiting** por usuario para evitar abuso.

**Idioma de la interfaz:** español (México). Toda salida al usuario está en
español, con formato de hora/fecha estilo mexicano y zona horaria
`America/Mexico_City` por defecto.

---

## 2. Stack tecnológico

| Componente | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ (usa `int \| None`, `zoneinfo`) |
| Framework bot | `python-telegram-bot` | >= 21.0 (async) |
| Cliente HTTP | `httpx` | >= 0.27 (async) |
| Base de datos | SQLite vía `aiosqlite` | >= 0.20 (async) |
| Config / entorno | `python-dotenv` | >= 1.0 |

Dependencias declaradas en `requirements.txt`. Todo el código es **asíncrono**
(`async/await`); el bot corre con **long polling** (`run_polling`).

---

## 3. Estructura de archivos

```
BotMundial/
├── README.md                # Documentación de usuario (instalación, comandos)
├── CONTEXT.md               # Este archivo (contexto completo para IA)
├── requirements.txt         # Dependencias Python
├── .env.example             # Plantilla de variables de entorno
├── .env                     # Variables reales (NO versionado, en .gitignore)
├── .gitignore               # Ignora venv, data/, *.db, .env, etc.
├── mundial.png / Icon       # Recursos gráficos
│
├── app/                     # Código fuente principal (paquete Python)
│   ├── __init__.py
│   ├── main.py              # Entry point: arma la Application y registra handlers
│   ├── config.py            # Carga y valida variables de entorno (.env)
│   ├── database.py          # Capa de acceso a SQLite (usuarios y contraseñas)
│   ├── espn.py              # Cliente de la API de ESPN + caché + normalización
│   ├── forecast.py          # Modelo Elo propio para pronósticos %
│   ├── teams.py             # Mapeo selección -> (abreviatura ES, bandera emoji)
│   ├── formatters.py        # Construye los mensajes (tablas monoespaciadas HTML)
│   ├── middleware.py        # Autorización + rate limit (decorador require_auth)
│   └── handlers/            # Handlers de cada comando/mensaje de Telegram
│       ├── __init__.py
│       ├── start.py         # /start y /menu (mensaje de bienvenida)
│       ├── partidos.py      # /partidos
│       ├── pronosticos.py   # /pronosticos
│       ├── grupos.py        # /grupos
│       ├── owner.py         # /crearpass y /cancelar (solo dueño)
│       └── mensajes.py      # Mensajes de texto libres (no comandos)
│
├── sql/
│   └── init.sql             # Schema: authorized_users y access_passwords
│
├── data/
│   └── bot.db               # Base de datos SQLite (gitignored, se crea sola)
│
└── logs/                    # Carpeta de logs (gitignored)
```

---

## 4. Comandos del bot

| Comando | Quién puede usarlo | Qué hace |
|---|---|---|
| `/start` | Todos | Mensaje de bienvenida con la lista de comandos. |
| `/menu` | Todos | Igual que `/start` (mismo texto de bienvenida). |
| `/partidos` | Autorizados | Partidos de **ayer, hoy y mañana** del Mundial 2026. |
| `/pronosticos` | Autorizados | Pronóstico % de los partidos **por jugar** hoy y mañana. |
| `/grupos` | Autorizados | Tabla de posiciones de los grupos. |
| `/crearpass <pass>` | Solo dueño (owner) | Crea una contraseña de un solo uso. |
| `/cancelar` | Solo dueño (owner) | Cancela la creación de contraseña en curso. |

`/start` y `/menu` son **públicos**; el resto exige autorización. Los comandos del
dueño solo responden si el `chat_id` coincide con `OWNER_CHAT_ID`.

El menú de comandos de Telegram se registra en `main.py:register_command_menu`:
los comandos públicos para todos y los del dueño solo en el chat del dueño
(`BotCommandScopeChat`).

---

## 5. Flujo de una petición (request lifecycle)

1. **Telegram** entrega un `Update` al bot (long polling).
2. `python-telegram-bot` lo enruta al **handler** correspondiente
   (`CommandHandler` o `MessageHandler`), todos en el grupo por defecto (0).
3. Cada handler está envuelto por el decorador **`@require_auth`**
   (`app/middleware.py`), que ejecuta **en orden**:
   - **`check_authorization(update)`** — decide si el update puede procesarse.
   - **`enforce_rate_limit(update, context)`** — aplica cooldown por usuario.
4. Si pasa ambos, se ejecuta la lógica del handler (consulta ESPN, formatea,
   responde).
5. Errores no controlados caen en el **error handler global**
   (`main.py:_on_error`), que los registra sin romper el bot.

### Autorización (`check_authorization`)

Orden de evaluación (primer match gana):

1. **Owner bypass**: si `chat_id == OWNER_CHAT_ID` → permitido siempre.
2. **Comandos públicos** (`/start`, `/menu`) → permitidos para todos.
3. **Ya autorizado**: si existe en `authorized_users` con `is_active = 1` →
   permitido.
4. **Intento de contraseña**: si el mensaje es texto libre (no comando), se
   intenta **consumir como contraseña de un solo uso** (`consume_password`). Si
   funciona, responde "✅ Acceso concedido" y **detiene** el update
   (`ApplicationHandlerStop`).
5. **Rechazo**: cualquier otro caso responde "🔒 Bot privado..." indicando pedir
   contraseña a `@OWNER_USERNAME` y detiene el update.

### Rate limit (`enforce_rate_limit`)

- Cooldown configurable: `USER_COOLDOWN_SECONDS` (default **10 s**).
- **El dueño está exento.**
- Se guarda el "próximo permitido" por `chat_id` en
  `context.application.bot_data["user_last_request"]` (memoria del proceso, no
  persiste entre reinicios).
- Si el usuario manda muy rápido: responde "⏳ Espera N segundos..." y detiene el
  update.
- La autorización corre **antes** que el rate limit a propósito: un usuario no
  autorizado recibe el mensaje de "bot privado", no el de "espera".

---

## 6. Sistema de acceso por contraseñas (detalle)

El acceso se gestiona con **contraseñas de un solo uso** que crea el dueño.

### Tablas SQLite (`sql/init.sql`)

**`authorized_users`** — usuarios con acceso concedido:
- `chat_id` (PK, TEXT), `username`, `first_name`, `secret` (contraseña usada),
  `created_at`, `created_by_chat_id`, `is_active` (default 1).

**`access_passwords`** — contraseñas emitidas:
- `id` (PK autoincrement), `secret`, `secret_norm` (**UNIQUE**, normalizada),
  `created_at`, `created_by_chat_id`, `is_active` (default 1),
  `used_by_chat_id`, `used_at`.

### Normalización de contraseñas (`database.normalize_secret`)

`unicodedata.normalize("NFKC", value).strip().lower()` →
**case-insensitive** y sin espacios al borde. Se compara siempre contra
`secret_norm`. Lo almacenado en `secret` también queda en minúsculas.

### Creación (`/crearpass`, `handlers/owner.py`)

- Solo el dueño. Dos modos:
  - **Inline**: `/crearpass MiClave123`.
  - **Conversacional**: `/crearpass` sin argumento → el bot pide la contraseña en
    un mensaje siguiente (estado `awaiting_new_password` en `context.user_data`).
    `/cancelar` aborta.
- **Validaciones**: no vacía, **sin espacios** (`\s` rechazado), **mínimo 4
  caracteres** (`MIN_PASSWORD_LENGTH`), y no duplicada (`password_exists`).
- Si todo OK, `create_password` inserta la fila. El constraint UNIQUE sobre
  `secret_norm` evita duplicados a nivel BD (captura `sqlite3.IntegrityError`).

### Consumo (al escribir la contraseña, `database.consume_password`)

- **Atómico**: un `UPDATE ... WHERE is_active = 1 AND used_by_chat_id IS NULL`
  reclama la contraseña; si `rowcount == 0` significa que ya fue usada/inválida →
  rollback y `None`.
- Si la reclama, hace `INSERT ... ON CONFLICT(chat_id) DO UPDATE` en
  `authorized_users` (alta o reactivación del usuario).
- **Un solo uso real**: solo el **primero** que escriba la contraseña obtiene
  acceso; los demás reciben el rechazo estándar.

---

## 7. Integración con ESPN (`app/espn.py`)

Cliente asíncrono (`httpx`) de la **API pública de ESPN** para fútbol, con
**caché en memoria** y **normalización** de la respuesta.

### Endpoints

- **Scoreboard (partidos)**:
  `{ESPN_BASE_URL}/{ESPN_LEAGUE_SLUG}/scoreboard?dates=YYYYMMDD-YYYYMMDD`
  - Base por defecto: `https://site.api.espn.com/apis/site/v2/sports/soccer`
  - Slug por defecto: `fifa.world`
- **Standings (grupos)**:
  `{ESPN_STANDINGS_BASE_URL}/{ESPN_LEAGUE_SLUG}/standings`
  - Base por defecto: `https://site.api.espn.com/apis/v2/sports/soccer`
    (los standings viven en una ruta distinta a la del scoreboard).

### Caché (`_cache`)

- Diccionario en memoria `clave -> (timestamp_monotónico, payload)`.
- TTL: `ESPN_CACHE_TTL_SECONDS` (default **60 s**). Si es <= 0, la caché se
  desactiva.
- Claves: `scoreboard:YYYYMMDD-YYYYMMDD` y `standings`.

### Filtrado a "Mundial 2026" (`_is_world_cup_2026`)

ESPN puede devolver eventos de otras competencias bajo el mismo slug. Se filtra:

1. Nombre de la liga del evento contra la **regex**
   `ESPN_WORLD_CUP_FILTER_REGEX` (default `fifa|world cup|mundial`,
   case-insensitive).
2. Fallback en `competitions[].altGameNote`/`notes`.
3. Si hay año de temporada, se acepta **solo 2026**; si el campo falta (común en
   la temporada activa), se acepta igualmente.

Para standings: si la temporada reportada no es 2026, devuelve lista vacía.

### Normalización de eventos (`_normalize_event`)

Cada evento crudo de ESPN se transforma a un dict estable:

```python
{
  "id": str,
  "date_utc": datetime.datetime,      # fecha/hora del partido en UTC
  "state": "pre" | "in" | "post",     # por jugar / en vivo / finalizado
  "display_clock": str | None,        # minuto en vivo (p. ej. "62'")
  "completed": bool,
  "home": {"name", "display_name", "abbreviation", "score": int|None},
  "away": {"name", "display_name", "abbreviation", "score": int|None},
  "league_name": str | None,
}
```

Eventos malformados se omiten con un `warning` (no rompen el comando).

### Normalización de grupos (`_normalize_group`)

Cada grupo se transforma a:

```python
{
  "group_name": "Grupo A",            # "Group A" -> "Grupo A"
  "teams": [
    {"rank", "display_name", "abbreviation", "played", "points", "gd"},
    ...                                # ordenado por rank, luego pts desc, GD desc
  ],
}
```

> ⚠️ **Importante**: las entradas de ESPN **no vienen pre-ordenadas**; el código
> las ordena explícitamente (`_sort_key`).

### Manejo de errores

Timeouts (`ESPN_REQUEST_TIMEOUT_SECONDS`, default 10 s), HTTP no-200 y JSON
inválido se registran y se relanzan; el handler los captura y responde con un
mensaje amable de "no pude obtener... intenta de nuevo".

### Zona horaria

`date_utc` se guarda en UTC y se convierte a local en los formatters con
`astimezone(ZoneInfo(DEFAULT_TIMEZONE))`. ESPN interpreta el parámetro `dates`
en **horario del Este de EE. UU.**, por eso los handlers consultan una **ventana
más amplia** (±1 o ±2 días) y luego clasifican estrictamente por **fecha local
de CDMX** en el formatter. Esto evita que los partidos aparezcan en el día
equivocado o se pierdan en los bordes del día.

---

## 8. Modelo de pronóstico Elo (`app/forecast.py`)

> No usa ninguna API externa ni IA. Todo se calcula **localmente**.

### Idea general

Cada selección tiene un **rating Elo** (mapa `_ELO`, valores públicos aproximados
estilo eloratings.net). La diferencia de rating (ajustada por ventaja de localía)
determina las probabilidades de **local / empate / visita** que suman 100%.

### Fórmulas

1. **Resultado esperado del local** (`_expected_home_score`):
   ```
   dr = (elo_local + HOME_ADVANTAGE) - elo_visita
   We = 1 / (1 + 10 ** (-dr / 400))
   ```
   `We ∈ [0,1]` = victoria + medio empate del local (puntos esperados
   normalizados).

2. **Probabilidad de empate** (`_draw_probability`): máxima en duelos parejos,
   decae cuando aumenta la diferencia de Elo efectiva.
   ```
   spread = (|dr| / 400) * DRAW_SHARPNESS
   p_draw = MAX_DRAW_PROB * (1 / (1 + spread²))
   ```

3. **Reparto** (`forecast`): como `We = p_home + p_draw/2`, se despeja:
   ```
   p_home = We - p_draw/2
   p_away = (1 - We) - p_draw/2
   ```
   Se aplican salvaguardas (no negativos), se normaliza a suma 1 y se convierte a
   enteros que **suman exactamente 100** (`_to_int_percentages`, reparte el
   residuo a las mayores partes fraccionarias).

### Constantes calibrables (parte superior del archivo)

| Constante | Valor | Significado |
|---|---|---|
| `HOME_ADVANTAGE` | 65.0 | Ventaja de localía en puntos Elo. |
| `MAX_DRAW_PROB` | 0.28 | Tope de probabilidad de empate en duelo parejo. |
| `DRAW_SHARPNESS` | 1.6 | Qué tan rápido cae el empate al desnivelarse. |
| `DEFAULT_ELO` | 1600.0 | Elo para selecciones no listadas en `_ELO`. |

**Para recalibrar**: edita el mapa `_ELO` (clave = `displayName` inglés de ESPN en
minúsculas, igual que en `teams.py`) o las constantes anteriores.

### API pública del módulo

- `forecast(home_name, away_name) -> (p_local, p_empate, p_visita)` (enteros que
  suman 100).
- `forecast_line(home, away) -> "L 58% · E 24% · V 18%"` (línea compacta).
- `get_elo(display_name) -> float`.

---

## 9. Mapeo de selecciones (`app/teams.py`)

Diccionario `_TEAMS`: **nombre inglés de ESPN (minúsculas)** →
`(abreviatura_ES, bandera_emoji)`. Cubre las confederaciones CONMEBOL, CONCACAF,
UEFA, CAF, AFC y OFC.

- Abreviaturas en **español** (p. ej. `germany → ("ALE", 🇩🇪)`,
  `england → ("ING", 🏴󠁧󠁢󠁥󠁮󠁧󠁿)`).
- Función `team_parts(display_name, espn_abbreviation="") -> (bandera, abreviatura)`:
  busca por nombre inglés; si no está, usa la **abreviatura de ESPN** (o el
  nombre) con bandera por defecto `🏳️`.
- `team_display(...) -> "🇪🇸 ESP"`.

Incluye variantes con acentos/alias (`méxico`, `türkiye`, `congo dr`, etc.) para
robustez ante distintas grafías de ESPN.

---

## 10. Formateo de mensajes (`app/formatters.py`)

Construye los mensajes que se envían a Telegram. Devuelve **listas de
`(texto, parse_mode)`** porque un comando puede generar varios mensajes si excede
el límite de Telegram (`TELEGRAM_MESSAGE_LIMIT = 4096`).

### Técnicas clave

- Las tablas se renderizan dentro de bloques **`<pre>...</pre>`** (HTML) para que
  Telegram use **fuente monoespaciada** y las columnas queden alineadas.
- Todo el texto se pasa por `html.escape(...)` para evitar romper el parseo HTML.
- Fechas/horas **locale-independent**: se calculan a mano el reloj de 12 h y
  AM/PM (`fmt_mx_time` → "h:mm a. m." / "p. m.") y los nombres de día/mes en
  español (`fmt_mx_date` → "domingo 14 de junio de 2026"), sin depender del
  locale del sistema.
- Las banderas emoji se mantienen **fuera** del texto con ancho fijo, porque su
  ancho monoespaciado es irregular y rompería la alineación.

### Funciones principales

- `build_partidos_messages(events, today_local, tz)` — secciones **Ayer / Hoy /
  Mañana**. Para "ayer" muestra marcador final; para "hoy" muestra marcador
  (final/en vivo) u hora según estado; para "mañana" muestra hora programada.
  Estados: `Final`, `EN VIVO 62'`, `Prog.`.
- `build_pronosticos_messages(events, today_local, tz)` — **solo** partidos en
  estado `pre` (por jugar) de **hoy y mañana**, cada uno en dos líneas (equipos +
  hora arriba; porcentajes L/E/V abajo). Usa `forecast()` de `forecast.py`.
- `build_grupos_messages(groups)` — tabla por grupo con columnas
  `#  EQUIPO  PJ  DG  PTS`. Empaqueta varios grupos por mensaje **sin partir un
  grupo** entre mensajes.

---

## 11. Configuración (`app/config.py` y `.env`)

`config.py` carga `.env` con `python-dotenv` y expone constantes tipadas. Hay
helpers `_require` (obligatorias) y `_optional_int` (enteros con default y
warning si son inválidos).

### Variables de entorno (ver `.env.example`)

| Variable | Default | Obligatoria | Descripción |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | **Sí** | Token del bot de Telegram (BotFather). |
| `OWNER_CHAT_ID` | (vacío) | Recomendada | `chat_id` numérico del dueño. Sin esto, no se reconoce al dueño ni se registran sus comandos. |
| `OWNER_USERNAME` | `pedroGVFurthurr` | No | Username mostrado para pedir contraseña. |
| `USER_COOLDOWN_SECONDS` | `10` | No | Cooldown anti-spam por usuario (dueño exento). |
| `SQLITE_DB_PATH` | `data/bot.db` | No | Ruta del archivo SQLite. |
| `SQL_INIT_PATH` | `sql/init.sql` | No | Ruta del schema a ejecutar al iniciar. |
| `LOG_LEVEL` | `INFO` | No | Nivel de logging. |
| `DEFAULT_TIMEZONE` | `America/Mexico_City` | No | Zona horaria para fechas/horas. |
| `ESPN_BASE_URL` | `https://site.api.espn.com/apis/site/v2/sports/soccer` | No | Base del scoreboard. |
| `ESPN_STANDINGS_BASE_URL` | `https://site.api.espn.com/apis/v2/sports/soccer` | No | Base de standings. |
| `ESPN_LEAGUE_SLUG` | `fifa.world` | No | Slug de la liga en ESPN. |
| `ESPN_WORLD_CUP_FILTER_REGEX` | `fifa\|world cup\|mundial` | No | Regex para filtrar eventos del Mundial. |
| `ESPN_REQUEST_TIMEOUT_SECONDS` | `10` | No | Timeout de las peticiones a ESPN. |
| `ESPN_CACHE_TTL_SECONDS` | `60` | No | TTL de la caché en memoria de ESPN. |

Meta del bot (en `config.py`): `BOT_NAME = "BotMundial"`, `BOT_VERSION = "0.1.0"`.

> Variable extra no documentada en `.env.example`: `BOTMUNDIAL_DEBUG` —
> si está definida, fuerza logging en nivel `DEBUG` (ver `main.py`).

---

## 12. Arranque del bot (`app/main.py`)

Secuencia de `main()`:

1. Configura **logging** (silencia el ruido INFO de `httpx`/`httpcore`).
2. Advierte si `OWNER_CHAT_ID` no está configurado.
3. Construye la `Application` con el token
   (`ApplicationBuilder().token(...).build()`).
4. Registra el **error handler global** (`_on_error`).
5. Registra **handlers**:
   - `CommandHandler`: `start`, `menu`, `partidos`, `pronosticos`, `grupos`,
     `crearpass`, `cancelar`.
   - `MessageHandler(filters.TEXT & ~filters.COMMAND, ...)` para texto libre
     (intentos de contraseña / flujo conversacional del dueño / mensaje "no
     entendí").
6. En **`post_init`**: inicializa la BD (`database.init_db`, crea `data/` y
   ejecuta `sql/init.sql`) y registra el **menú de comandos** en Telegram.
7. Arranca con `run_polling(allowed_updates=Update.ALL_TYPES)` (**long polling**,
   no webhooks).

Ejecución:

```bash
python -m app.main
```

---

## 13. Instalación y ejecución (resumen operativo)

```bash
# 1) Entorno virtual e instalación
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2) Configuración
cp .env.example .env
#   Edita .env y coloca al menos:
#     TELEGRAM_BOT_TOKEN=<token de BotFather>
#     OWNER_CHAT_ID=<tu chat_id numérico>

# 3) Ejecutar
python -m app.main
```

La base de datos `data/bot.db` se crea automáticamente al primer arranque
(`post_init` → `init_db`). No requiere migraciones manuales.

---

## 14. Decisiones de diseño y notas para una IA

Puntos importantes a tener en cuenta si vas a **modificar o extender** el código:

- **Todo es async.** Cualquier handler nuevo debe ser `async` y, normalmente,
  ir decorado con `@require_auth` (salvo que deba ser público; entonces añade su
  comando a `PUBLIC_COMMANDS` en `middleware.py`).
- **`ApplicationHandlerStop`** se usa para cortar el flujo en autorización/rate
  limit. No lo captures por error en handlers genéricos.
- **Pronósticos sin IA.** El "pronóstico" es determinista (Elo). No introduzcas
  llamadas a modelos externos a menos que se pida explícitamente; el README y
  este documento afirman que es 100% local.
- **Filtrado del Mundial es heurístico.** Depende del nombre de liga y de la
  regex. Si ESPN cambia el naming, ajusta `ESPN_WORLD_CUP_FILTER_REGEX` o
  `_is_world_cup_2026`.
- **Orden de standings.** Nunca asumas que ESPN los ordena; respeta `_sort_key`.
- **Zona horaria / ventana de fechas.** Para partidos/pronósticos se consulta una
  ventana ampliada por la interpretación de `dates` en horario del Este; la
  clasificación real por día se hace en el formatter con la TZ local. Mantén ese
  patrón si tocas fechas.
- **Límite de mensaje de Telegram.** Respeta `TELEGRAM_MESSAGE_LIMIT` y la lógica
  de "empaquetar bloques sin partirlos" al añadir nuevas secciones.
- **Estado en memoria.** El rate limit y la caché de ESPN viven en memoria del
  proceso; se pierden al reiniciar. Lo persistente está solo en SQLite
  (usuarios y contraseñas).
- **Contraseñas case-insensitive y sin espacios**, mínimo 4 caracteres, **un solo
  uso** garantizado por el UPDATE atómico. No relajes esto sin actualizar la
  lógica de `consume_password`.
- **Seguridad.** `.env` y `data/` están en `.gitignore`. Nunca commitees el token
  ni la base de datos.

---

## 15. Mapa rápido archivo → responsabilidad

| Archivo | Responsabilidad principal |
|---|---|
| `app/main.py` | Bootstrap, registro de handlers y menú, error handler, polling. |
| `app/config.py` | Lectura/validación de `.env` y constantes globales. |
| `app/database.py` | SQLite: usuarios autorizados y contraseñas de un solo uso. |
| `app/espn.py` | Cliente ESPN, caché, filtrado Mundial 2026, normalización. |
| `app/forecast.py` | Modelo Elo y cálculo de probabilidades L/E/V. |
| `app/teams.py` | Selección → abreviatura ES + bandera emoji. |
| `app/formatters.py` | Construcción de mensajes/tablas HTML monoespaciadas. |
| `app/middleware.py` | `require_auth`: autorización + rate limit. |
| `app/handlers/start.py` | `/start`, `/menu`. |
| `app/handlers/partidos.py` | `/partidos`. |
| `app/handlers/pronosticos.py` | `/pronosticos`. |
| `app/handlers/grupos.py` | `/grupos`. |
| `app/handlers/owner.py` | `/crearpass`, `/cancelar` (dueño). |
| `app/handlers/mensajes.py` | Texto libre (contraseñas / flujo dueño / fallback). |
| `sql/init.sql` | Schema de la base de datos. |

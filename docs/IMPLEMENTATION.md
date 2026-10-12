# Agente de agendamiento de mantenimiento — qué implementamos y por qué

Documento de entrega para el take-home de Nuvaliving. Resume el problema, la solución, las
decisiones de diseño y las salvaguardas (prompt injection, validación de fechas y entradas).
Las reglas vinculantes viven en `BUSINESS_RULES.md`; la arquitectura en
`TECHNICAL_ARCHITECTURE.md`; cada decisión aprobada en `docs/decisions/`.

## 1. El problema

Un agente CLI (Docker) coordina, por cada orden de trabajo del CSV, a un **inquilino** y a un
**handyman único** hasta llegar a exactamente uno de dos resultados terminales:

- `scheduled`: ambos aceptaron explícitamente **la misma** fecha y hora.
- `requires_review`: no se pudo coordinar de forma fiable (con razón breve).

Restricciones del enunciado: visitas de 2 h sin solapes, prioridad `Critical > High > Medium > Low`,
handyman siempre en español, inquilino en el idioma de la orden, zona `Europe/Madrid`, varias
órdenes simultáneas con respuestas en cualquier orden, `<NO RESPONSE>` como silencio humano con reintentos (el único temporizador es el de reintento, con reloj UTC real),
stdout/stderr **solo** para el protocolo y trazas JSONL en `/app/traces`.

## 2. Qué implementamos

| Capacidad | Resumen |
|---|---|
| Arranque concurrente | Al iniciar, se emite el primer mensaje de **todas** las órdenes del CSV sin esperar respuestas. |
| Una cola por orden | Cada orden tiene su cola FIFO y estado propio; órdenes distintas progresan en paralelo. |
| Reconocimiento de idioma | Un LLM infiere el idioma de la descripción (ISO 639-1, con valor "indeterminado" si no hay evidencia). Idioma acotado a `(orden, rol)`. |
| Negociación determinista | Tenant primero → candidatos de 2 h → handyman → propuesta inmutable con versión → aceptación de ambos → confirmación → resultado. |
| Agenda compartida | Autoridad en memoria que reserva intervalos semiabiertos `[inicio, fin)` de forma atómica, con holds tentativos y citas confirmadas. |
| Prioridad por urgencia | Un hold de menor urgencia puede ser desplazado atómicamente; igual/mayor urgencia o cita confirmada nunca. Se avisa al desplazado. |
| Peticiones vagas (spec 005) | Ante "esta semana por la tarde, ¿qué días?", se responde con una **tabla Markdown determinista** de huecos libres, validada antes de enviarse. |
| Validación determinista (spec 006) | Fechas, horario de visita, fines de semana/días de la semana, entradas vacías/largas/desconocidas. |
| Guard anti prompt-injection | Pipeline de 3 pasadas sobre cada mensaje entrante (ver §4). |
| Trazas | Carpeta por corrida con `manifest.jsonl`, `events.jsonl`, `runtime.jsonl`; sin handlers de consola. |
| Docker | `Dockerfile` en la raíz con `uv sync --frozen`; las credenciales solo entran en runtime con `--env-file`. |

### Stack

Python 3.12, **LangGraph** (grafo de transición por evento), Pydantic v2 en las fronteras,
`pydantic-settings`, `dependency-injector`, cliente Anthropic (modelo por defecto
`claude-haiku-5-5`), `uv` + `uv.lock`, Ruff, pytest.

### Estructura

```text
src/maintenance_agent/
  bootstrap.py  config.py  dependencies.py      # raíz de composición única + Settings
  domain/          # reglas puras: scheduling, negociación, date_validation, idiomas
  application/     # coordinator, workflow, injection_guard, rejections, slot_table
  agents/scheduling/  graph.py, state.py, nodes/   # LangGraph
  prompts/         # constructores de prompts tipados
  infrastructure/  # CSV, CLI, Anthropic, agenda en memoria, trace writer
tests/{unit,integration,acceptance}/
```

Principios: el dominio no depende de LangGraph/Anthropic/CLI/filesystem; los nodos nunca leen
variables de entorno ni crean clientes; todo se inyecta una vez en `bootstrap.py`.

## 3. Principio rector: el LLM es evidencia, el código decide

Esta es la decisión más importante del diseño (Constitución III). El modelo **interpreta** lenguaje
natural (disponibilidad, sí/no, ambigüedad, idioma), pero nunca:

- decide un resultado terminal,
- valida una fecha,
- reserva o desplaza un hueco,
- infiere consentimiento a partir de una disponibilidad.

Toda salida del modelo es tipada (Pydantic), se valida y se descarta si queda obsoleta frente a la
versión de estado/propuesta. Un error del proveedor **no** se trata como ausencia humana.

## 4. Seguridad: detección de prompt injection

Todo mensaje entrante (salvo el centinela exacto `<NO RESPONSE>`) pasa por el guard **antes** de
cualquier lógica del flujo. Está cableado como nodo previo del grafo
(`START → injection_guard → negotiation_transition`), implementado en
`application/injection_guard.py` y `infrastructure/anthropic_injection_classifier.py`.

### Pipeline de tres pasadas

```text
mensaje ──► (1) ¿es inyección? probabilidad p
              p ≤ umbral ───────────────────────────────► PASS (sigue el mensaje original)
              p > umbral
                 ▼
            (2) extraer el fragmento sospechoso y evaluarlo SOLO
              p ≤ umbral ───────────────────────────────► PASS (falsa alarma)
              p > umbral
                 ▼
            (3) eliminar el fragmento con código determinista y evaluar el resto
              resto limpio y no vacío ──────────────────► PASS_CLEANED (continúa solo el resto)
              resto vacío / aún sospechoso / fragmento
              no encontrado ────────────────────────────► BLOCK
```

- **Umbral**: `INJECTION_THRESHOLD`, por defecto `0.6`, estrictamente `>` (rango `0 ≤ v < 1`).
- **Por qué tres pasadas**: evaluar el fragmento aislado reduce falsos positivos (un inquilino que
  cita "ignora…" en contexto legítimo), y quitarlo con código en lugar de pedirle al LLM que
  "limpie" evita que el propio modelo reescriba el mensaje bajo influencia del atacante.
- **Bloqueo**: el mensaje no se procesa; el remitente recibe un aviso de seguridad **fijo y
  localizado** (es/en/fr/de/it/pt; idioma desconocido → par en/es) seguido del último mensaje que
  se le envió a ese rol, para que la conversación pueda continuar.
- **Fail-open**: si el proveedor falla, el mensaje continúa y el error se registra en
  `runtime.jsonl`. Es deliberado: el guard es evidencia, y la validación determinista posterior
  sigue siendo la autoridad. Solo está activo con `ANTHROPIC_API_KEY`.
- **Trazabilidad**: cada pasada queda en la traza (`stage`, probabilidad, respuesta), de modo que
  se puede reconstruir por qué un mensaje pasó, se limpió o se bloqueó.
- **Urgencia solo del CSV**: ningún texto de mensaje puede subir o bajar la urgencia de una orden.

## 5. Validación determinista (spec 006 / decisión 006)

Las pruebas de extremo a extremo mostraron que fechas extraídas por el LLM llegaban sin control a
la agenda (visitas a las 03:00, año 2062, días de la semana incorrectos, fechas pasadas). Se añadió
una herramienta pura `domain/date_validation.py` (`validate_interval`, `validate_date_text`) que
corre **antes** del LLM y no puede ser anulada por él.

| Código | Se rechaza cuando |
|---|---|
| `outside_visit_hours` | La visita completa (inicio **y** fin) no cae dentro de 09:00–19:00 `Europe/Madrid`. |
| `in_the_past` | La fecha/hora es anterior a la referencia actual. |
| `too_far_ahead` | Más de `VISIT_HORIZON_DAYS` (por defecto 7) días naturales por delante. |
| `weekday_mismatch` | El día de la semana dicho no coincide con la fecha (se informa el real). |
| `not_a_calendar_date` / `invalid_time` | Fecha o hora inexistente (30 de febrero, 25:00). |

Una disponibilidad rechazada **nunca** se registra como evidencia; se responde al remitente con el
motivo y una nueva petición, y se traza como `availability_rejected`. Aplica por igual a inquilino
y handyman.

**Validación de entrada** (antes de cualquier llamada al modelo, respuesta fija localizada):

- orden de trabajo desconocida,
- cuerpo vacío,
- cuerpo mayor que `MAX_MESSAGE_LENGTH` (por defecto 2000).

Líneas con formato inválido se ignoran y se registran como `malformed_input` en `runtime.jsonl`
sin detener el proceso.

**Rol y cancelación**: una respuesta de aclaración se procesa según **quién la envía**, no según la
acción pendiente (bug detectado: respuestas de inquilino tratadas como del handyman). Cancelar una
propuesta pendiente equivale a rechazarla.

## 6. Otras decisiones de diseño relevantes

1. **Disponibilidad ≠ aceptación.** Ambas aceptaciones deben apuntar al mismo `proposal_id` +
   versión; si la visita cambia, las aceptaciones previas se invalidan. Un intérprete tipado
   devuelve `yes` / `no` / `null` + `clarification_required`; la ambigüedad nunca se coacciona.
2. **Candidatos tenant-first** (decisión 005). Se pide al inquilino todos sus intervalos, se
   fusionan solapados/adyacentes, se parten en bloques de 2 h desde el inicio y se ignora el
   residuo menor a 2 h. No se inventan huecos ni disponibilidad del handyman. El handyman puede
   contraproponer un intervalo completo solo si está contenido en la unión del inquilino, y aun así
   el inquilino debe confirmarlo.
3. **Pre-filtrado contra la agenda.** Un candidato ocupado por un hold de igual/mayor urgencia o
   una cita confirmada vuelve al inquilino sin molestar al handyman.
4. **Tabla de slots determinista** (spec 005). Rejilla de presentación (por defecto 7 días, slots
   de 2 h, 09:00–19:00) que solo muestra ocupación de la agenda; **nunca** cuenta como
   disponibilidad ni consentimiento. Un LLM validador revisa la respuesta antes de enviarla; si
   falla, devuelve feedback y se reintenta. Tras 3 intentos (`SLOT_MAX_ATTEMPTS = 3`) se pasa a un
   mensaje que pide ser más específico.
5. **Terminal atómico e idempotente.** `TerminalStatus` es un tipo cerrado con solo `scheduled` y
   `requires_review`. El commit de agendado y el cierre por revisión son mutuamente excluyentes;
   las confirmaciones a ambos se envían de forma secuencial e idempotente **antes** del marco
   terminal. Si falla un envío, la cita se conserva y no se emite un terminal prematuro. Un mensaje
   tardío nunca cambia un resultado terminal.
6. **`<NO RESPONSE>` exacto.** Solo el cuerpo idéntico pone la orden en `RETRYING`: una cola de
   mínimos por hora UTC de colocación, sondeada cada `NO_RESPONSE_POLL_SECONDS` (10 s por defecto). Tras
   `NO_RESPONSE_RETRY_WAIT_SECONDS` (300 s) se envía al rol en silencio un recordatorio fijo seguido del
   mensaje original, como máximo `NO_RESPONSE_MAX_RETRIES` (3) veces. Tras una espera más sin respuesta,
   la orden se cierra como `requires_review`. Un mensaje normal del rol en silencio cancela los reintentos;
   un `<NO RESPONSE>` repetido se ignora (traza). Al llegar EOF, las órdenes en `RETRYING` se cierran
   de inmediato. Las variantes con espacios/prefijos no coinciden. Los ajustes son variables de entorno
   de arranque leídas una vez por Settings. Ver `docs/BUSINESS_RULES.md`.
7. **Razones de revisión deterministas.** `REASON` sale de un código (`no_response`,
   `no_common_availability`, `no_eligible_slot`) más evidencia registrada; si algo se desconoce, se
   dice, nunca se inventa. Si la evidencia completa demuestra que no hay hueco común, primero se
   ofrece al inquilino la agenda humana (sí → `requires_review`, no → nueva disponibilidad).
8. **Reversiones.** Un cambio de disponibilidad requiere confirmación del remitente; el valor previo
   se conserva y el intervalo en disputa se suspende hasta resolverse.
9. **Consola limpia.** stdout/stderr solo llevan el protocolo; todo lo demás va a JSONL.
10. **Configuración startup-only.** Los ajustes se leen una vez (`LOCAL_TIMEZONE`,
    `INJECTION_THRESHOLD`, `VISIT_HORIZON_DAYS`, `MAX_MESSAGE_LENGTH`, rejilla de slots, modelos);
    cambiar uno requiere reiniciar. Ver `docs/configuration.md`.

## 7. Observabilidad

Una carpeta por corrida: `traces/runs/<inicio-Madrid-con-offset>-<run_id>/`

- `manifest.jsonl`: inicio/fin, run ID, configuración efectiva **sin secretos**.
- `events.jsonl`: mensajes entrantes/salientes, transiciones, decisiones, evidencia de
  disponibilidad, rechazos, pasadas del guard y terminales; ordenables por `sequence` y filtrables
  por `work_order_id`.
- `runtime.jsonl`: logs técnicos y errores sanitizados (incl. fallos de proveedor y `malformed_input`).

Hay trazas de corridas reales en `traces/runs/` como ejemplo.

## 8. Pruebas

Unitarias (dominio puro: fechas, agenda, negociación, guard, tabla de slots, settings, trazas),
de integración (consentimiento, preempción, reversiones, cancelación, enrutado por rol, validación
de entrada, flujo del guard, coordinación asíncrona) y de aceptación (CLI, formato de terminal,
petición vaga). Los tests con Anthropic real están separados de los que usan fakes.

## 9. Supuestos, límites y puntos abiertos

- **Sin persistencia**: el estado vive en memoria; no se promete recuperación tras un crash.
- **Horizonte vs. tabla de slots** (resuelto por el usuario): el horizonte de 7 días no se amplía;
  la tabla se limita al horizonte y el agente dice hasta dónde conoce la agenda (ver decisión 006).
- **Ofertas simultáneas**: el mismo hueco libre puede ofrecerse al handyman para dos órdenes antes
  de existir un hold (lo permite `BUSINESS_RULES.md`); se arbitra al crear el hold y las citas
  confirmadas nunca se pre-empten. Una orden Low puede quedarse el hueco si confirma antes.
- **Ruido del LLM**: intervalos vacíos en casos válidos (se reintenta hasta 3 veces); el guard puede
  tener falsos negativos y falla en abierto; los rechazos solo tienen plantillas es/en.
- **DST**: sin política especial. Los offsets (`+01:00`/`+02:00`) salen de la base IANA y las
  visitas solo ocurren entre 09:00 y 19:00, fuera de la madrugada del cambio de hora.
- **Fecha de referencia** para relativos ("mañana"): política abierta; `reported_at` no implica
  "hoy".
- **Guard fail-open**: se acepta el riesgo de que una caída del proveedor deje pasar un mensaje
  hostil porque la validación determinista y la regla "el LLM es solo evidencia" limitan el daño
  (no puede alterar urgencia, terminal ni agenda por sí solo).
- **Delayed yes ambiguo**: stdin no trae campo de correlación, así que un "sí" tardío ambiguo exige
  reconfirmar el hueco completo; no se afirma desambiguación perfecta.
- CSV con filas inválidas/duplicadas, EOF y separador de resultados terminales: políticas pendientes
  de aprobación.

## 10. Cómo ejecutar

```bash
docker build -t agent .
docker run --env-file .env -i \
  -v "$(pwd)/examples/work_orders.csv:/app/work_orders.csv:ro" \
  -v "$(pwd)/traces:/app/traces" \
  agent
```

Desarrollo local: `uv run maintenance-agent --csv ./examples/work_orders.csv`. `.env` contiene
`ANTHROPIC_API_KEY` (no se versiona; ver `.env.example`).

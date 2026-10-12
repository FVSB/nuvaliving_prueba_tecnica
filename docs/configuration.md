# Guía de configuración y logs por corrida

## Estado y fuentes

Esta guía acompaña TECHNICAL_ARCHITECTURE.md y BUSINESS_RULES.md. `Settings`, el contenedor y las trazas JSONL por corrida están implementados; mantener esta guía sincronizada con cada cambio aprobado.

En el repositorio destino, mantener esta información en `docs/configuration.md`, referenciarla desde README y actualizarla con cada cambio aprobado. Las reglas de negocio prevalecen para políticas funcionales; arquitectura define mecanismos.

## Dónde consultar cada cosa

| Ubicación objetivo | Responsabilidad |
|---|---|
| `src/maintenance_agent/config.py` | Settings tipados, validaciones y constantes |
| `src/maintenance_agent/bootstrap.py` | Única lectura del entorno e inicialización |
| `src/maintenance_agent/dependencies.py` | Contenedor dependency-injector y ciclo de vida |
| `src/maintenance_agent/infrastructure/trace_writer.py` | Contexto de corrida y trazas JSONL estructuradas |
| `.env.example` | Solo variables aprobadas e implementadas, sin secretos |
| `docs/configuration.md` | Catálogo vigente, restricciones y aplicación de cambios |
| `docs/decisions/` | Motivos y aprobación de decisiones relevantes |
| `.agents/skills/maintain-runtime-configuration/SKILL.md` | Procedimiento de mantenimiento |

Las rutas listadas reflejan la implementación vigente; crear módulos adicionales solo cuando estén justificados.

## Catálogo inicial

| Parámetro | Categoría | Entorno / estado | Restricción |
|---|---|---|---|
| Zona horaria | Configuración startup-only aprobada | `LOCAL_TIMEZONE=Europe/Madrid` | IANA válida; aplica solo a nuevas corridas |
| Rejilla de sugerencia de slots | Configuración startup-only aprobada | `SLOT_LOOKAHEAD_DAYS=7`, `SLOT_DAILY_START_HOUR=9`, `SLOT_DAILY_END_HOUR=19`, `SLOT_HOURS=2` | Solo presentación; nunca evidencia de disponibilidad; la ventana debe contener al menos un slot; la tabla se limita al horizonte de visita (ventana efectiva = `VISIT_HORIZON_DAYS` + 1 días) |
| Guard de prompt injection | Configuración startup-only aprobada | `INJECTION_THRESHOLD=0.6` | `0 <= valor < 1`; solo activo con `ANTHROPIC_API_KEY`; falla en abierto ante errores del proveedor |
| Horizonte de visita | Configuración startup-only aprobada | `VISIT_HORIZON_DAYS=7` | Entero > 0; días naturales desde hoy; fechas posteriores se rechazan como `too_far_ahead`; el horario de visita permitido es 09:00-19:00 (`SLOT_DAILY_START_HOUR`/`SLOT_DAILY_END_HOUR`). Decisión del usuario: el horizonte no se amplía; el agente indica hasta dónde conoce la agenda («Solo conozco la disponibilidad hasta el miércoles 2026-10-19…») y la tabla de slots se limita a él |
| Longitud máxima de mensaje | Configuración startup-only aprobada | `MAX_MESSAGE_LENGTH=2000` | Entero > 0; los mensajes más largos se rechazan con respuesta fija antes de cualquier llamada al modelo |
| Duración visita | Regla de negocio vinculante | Constante de dos horas | No cambiar duración; el DST lo cubre la base IANA |
| Número de handyman | Regla de negocio vinculante | Constante: uno | No parametrizar para cambiar contrato |
| CSV | Regla de negocio vinculante | `/app/work_orders.csv`, solo lectura | Mantener ruta de evaluación |
| Logs/trazas | Regla de negocio vinculante | `TRACES_DIR=traces` local; `/app/traces` Docker, JSONL | Startup-only; una carpeta por corrida |
| Credencial Anthropic | Credencial documentada | `ANTHROPIC_API_KEY`, si el cliente la necesita | Secreto; no registrar valor ni versionar .env |
| Modelo de reconocimiento de idioma | Configuración startup-only | `ANTHROPIC_LANGUAGE_MODEL=claude-haiku-5-5` | Nombre no vacío; aplica al siguiente arranque |
| Modelo de conversación | Configuración startup-only | `ANTHROPIC_CONVERSATION_MODEL=claude-haiku-5-5` | Nombre no vacío; aplica al siguiente arranque |
| Directorio de trazas | Configuración startup-only aprobada | `TRACES_DIR=traces` local; Docker fija `/app/traces` | No cambia una corrida activa; no registrar secretos |
| Concurrencia LLM | Técnico | Preguntar antes de crear variable | No bloquear recepción de otras órdenes |
| Referencia de fechas relativas | Política abierta | Aprobar política y después preguntar si entorno | `reported_at` no implica «hoy» |
| Horario laboral | Política no definida | Preguntar si se desea añadir y si usar entorno | No inventar franjas/disponibilidades |
| Presupuesto timeout/aclaración | Política abierta | Aprobar política y después preguntar si entorno | Timeout humano solo por marcador, no reloj |

No asignar nombres de variables ni defaults arbitrarios a los candidatos. Registrar después de aprobación: nombre, tipo, valor por defecto, validación, consumidor/provider, fuente, secreto y reinicio requerido.

## Cómo ver los logs por hora de corrida

Organización prevista:

```text
/app/traces/runs/<Madrid_start_with_offset>-<unique_run_id>/
  manifest.jsonl
  events.jsonl
  runtime.jsonl
```

El comando de evaluación documentado en `BUSINESS_RULES.md` monta `./traces` del host en `/app/traces`: en el host, consultar `traces/runs/` y localizar la carpeta por fecha/hora de inicio. Mantener una carpeta por corrida aunque dure varias horas o días. La aplicación crea las tres rutas JSONL al arrancar y no instala handlers de consola.

- `manifest.jsonl`: inicio/cierre, run ID y snapshot efectivo sin secretos.
- `events.jsonl`: mensajes entrantes, decisiones, cambios, mensajes salientes y terminales por orden.
- `runtime.jsonl`: logs técnicos y errores sanitizados.
- `outgoing_message` se escribe después de vaciar el bloque completo en stdout y registra el cuerpo
  y el rol destinatario realmente enviados. `terminal_result` se escribe después de vaciar el marco
  terminal en stdout.
- Las líneas CLI ilegibles (sin `|` o con rol inválido) se ignoran y generan `malformed_input` y
  `message_rejected` (`protocol_mismatch`) en `runtime.jsonl`, con motivo, longitud y línea recibida.
- Las líneas con id y rol válidos pero cuerpo vacío o mayor que `MAX_MESSAGE_LENGTH`, o con id
  desconocido, se responden con un texto fijo (es/en) y generan `message_rejected` (y
  `unknown_work_order` si procede) en `events.jsonl`.
- Los mensajes válidos y rechazados recibidos para una orden ya completada se ignoran; tampoco se
  procesan eventos que quedaron en cola cuando esa orden emitió su resultado terminal.
- Buscar por `work_order_id` para reconstruir una orden y ordenar por `sequence` dentro de la corrida; timestamps conservan offset real de Madrid.
- La hora del log no gobierna los timeouts humanos ni la referencia temporal de negocio.

## Cambiar configuración después

1. Consultar `BUSINESS_RULES.md`, arquitectura, configuración actual y memoria Engram relevante.
2. Presentar propuesta y preguntar si el parámetro debe ser entorno o constante.
3. Para políticas, aprobar primero su significado funcional. No modificar constantes vinculantes.
4. Obtener aprobación específica y previsualizar archivos/pruebas.
5. Actualizar Settings, DI, ejemplo de entorno, catálogo, decisiones, pruebas y skill según proceda.
6. Aplicar el nuevo entorno **solo al siguiente arranque**. No hacer hot reload ni mutar providers activos. En Docker, recrear el contenedor con el entorno actualizado cuando se autorice; cambiar el archivo del host no modifica el proceso activo.
7. Verificar snapshot, corrida nueva, logger y ausencia de cambio en una corrida activa con pruebas aisladas.
8. Guardar resultado verificado y rutas en Engram con claves separadas por tema, sin secretos.

No detener una evaluación o corrida con órdenes pendientes automáticamente para aplicar configuración. Registrar qué quedó propuesto, aprobado, implementado y verificado.

## Zona horaria local aprobada

`LOCAL_TIMEZONE` se lee una sola vez al arrancar y usa `Europe/Madrid` por defecto. Debe ser un
identificador IANA instalado (por ejemplo, `Europe/Madrid`). El lector CSV normaliza `reported_at`
a esta zona conservando el instante original y rechaza marcas de tiempo sin offset. Cambiarla
requiere reiniciar el proceso o contenedor; nunca modifica una corrida activa.

## Modelos Anthropic

`ANTHROPIC_LANGUAGE_MODEL` selecciona el modelo de reconocimiento de idioma y
`ANTHROPIC_CONVERSATION_MODEL` selecciona el modelo de interpretación y composición de mensajes.
Ambas variables usan `claude-haiku-5-5` por defecto y requieren un identificador no vacío. Se
leen al inicio; cada manifiesto de corrida registra los dos modelos efectivos y nunca las
credenciales.

## Local CSV selection

For development run `uv run maintenance-agent --csv ./work_orders.csv`. The argument is passed
to the composition root and injected into the CSV adapter once. Without it, local and Docker
execution both retain `/app/work_orders.csv`. No extra environment variable is introduced.
The root production Dockerfile uses the same `uv.lock` and receives secrets with `--env-file`
at runtime, never during the build.

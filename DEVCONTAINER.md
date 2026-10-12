# Entorno de desarrollo

Este directorio todavía no contiene el código ni un manifiesto que identifique
su stack de aplicación. El dev container instala la base observada en el
proyecto: Node.js para Codex/Claude Code y Go para compilar Engram. Cuando se
incorpore el stack real, se deben añadir aquí sus dependencias y comandos.

## Abrir

Abre el proyecto en VS Code con Docker y la extensión Dev Containers, y elige
**Dev Containers: Reopen in Container**. El primer build instala Codex, Claude
Code y Engram; luego muestra sus versiones.

## Conectar los agentes con Engram

`.mcp.json` registra Engram para Claude Code y usa la ruta del comando, no una
ruta local del host. Para instalar también el plugin y los hooks de sesión de
Engram para ambos agentes, ejecuta una vez desde una terminal del contenedor:

```bash
.devcontainer/setup-agents.sh
```

El setup de Claude Code puede preguntar si se autorizan las herramientas de
memoria. Después, autentica cada CLI dentro del contenedor con `codex` y
`claude`. Sus configuraciones, autenticación y sesiones se conservan en
volúmenes Docker separados por proyecto. La base SQLite de Engram también
persiste en su propio volumen local; no se versiona en Git.

## Uso recomendado

- Engram es la memoria compartida y local de los agentes. Guarda decisiones y
  contexto estable del proyecto, no cada conversación ni resultados crudos.
- Codex y Claude Code son alternativas de interfaz/agente; pueden usar la
  misma memoria Engram. Evita ejecutar ambos sobre el mismo cambio a la vez.
- Las versiones de Codex y Claude Code se actualizan al reconstruir el
  contenedor; Engram queda fijado en `v3.3.2` para mantener compatibles sus
  hooks y el formato de configuración. Actualiza ese pin deliberadamente.
- Los volúmenes persisten tras reconstruir el contenedor. Para eliminar
  autenticación/configuración o la memoria, borra el volumen correspondiente
  desde Docker; el volumen de Engram contiene datos del proyecto.

# Handoff — Migración a Hetzner + Postgres (contexto para continuar)

> Documento de traspaso: dónde quedamos y qué falta, para seguir en otro chat sin perder contexto.
> Fecha: 2026-06.

## 1. Qué es el proyecto (resumen)
App personal de gastos: anotás gastos por chat en lenguaje natural, una IA (**Groq**, gratis)
los clasifica por categoría y tipo (fijo/necesario/prescindible), y ves el mes con barras + un
consejo IA. **FastAPI + SQLite/Postgres + PWA (JS puro)**, con **login multiusuario** (cada uno ve lo suyo).
Detalle completo del código y la teoría en `doc/01..04`.

- **Repo:** https://github.com/juanzeballos/finanzasPersonales
- **Carpeta local:** `F:\proyectos\gastos-ia`
- **Correr local (dev):** `.\run.ps1` (usa SQLite + `IA_PROVIDER` del registro).

## 2. Por qué estamos migrando
- La app estaba deployada en **Fly** (`finanzas-jz.fly.dev`) pero **se acabó el uso gratis de Fly**.
- Evaluamos hosting: **Oracle Always Free** (ARM A1 sin capacidad disponible → descartado) y **Hetzner**
  (VPS ~US$5,60/mes, CX22) → **elegimos Hetzner + Postgres** (para multiusuario real).

## 3. Ramas del repo
- **`main`** — versión que corría en Fly (SQLite). Intacta.
- **`oracle`** — rama de la migración. **La Fase A YA está hecha y pusheada acá**:
  - `requirements.txt`: + `psycopg[binary]` (driver Postgres).
  - `app/database.py`: elige config según SQLite (local) o Postgres (`DATABASE_URL`).
  - `app/routers/gastos.py`: filtro por mes **portable** con `rango_mes()` (rango de fechas; se sacó `func.strftime`, que era solo de SQLite).
  - `docker-compose.yml`: **Postgres + app (web) + Caddy** con volúmenes persistentes.
  - `Caddyfile`: HTTPS automático para `{$DOMINIO}`.
  - `.env.example`: plantilla de secretos (el `.env` real NO se sube).
  - **Trabajar y deployar Hetzner desde la rama `oracle`.**

## 4. Servidor Hetzner
- **Server activo: IP `135.181.34.126`** (CX22, Ubuntu 24.04, Backups OFF). Usuario SSH: **`root`**.
  - (Hubo uno previo, `167.233.37.32`, descartado porque no tenía cargada la clave SSH.)
- **Clave SSH** (en la PC del usuario): privada `C:\Users\54347\.ssh\hetzner`, pública `...\.ssh\hetzner.pub` (comentario `gastos-hetzner`).
  - Conectarse: `ssh -i $HOME\.ssh\hetzner root@135.181.34.126`
  - ⚠️ La VM nueva debe tener cargada la **pública `gastos-hetzner`** (el server anterior fallaba con "Permission denied" justamente por no tenerla).
- Hetzner cobra **por hora** (borrar/recrear cuesta centavos).

## 5. Deploy en la VM — ✅ HECHO (2026-06-13)
**La app está viva en https://gastos-ia.duckdns.org** (HTTPS con cert Let's Encrypt OK).
(También responde por la URL vieja `135.181.34.126.sslip.io`, pero ya no se usa.)
Todos los pasos quedaron completados:
1. ✅ **SSH verificado** — `ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126` entra OK.
2. ✅ **git + Docker instalados** (Docker 29.5.3, compose v5.1.4; Ubuntu **26.04** — la VM venía con 26, no 24). git ya venía.
3. ✅ **Rama oracle clonada** en `/opt/gastos`.
4. ✅ **`/opt/gastos/.env` creado** (LF, sin BOM/CRLF — se generó en el server con `printf` + `openssl rand -hex`):
   - `DOMINIO=135.181.34.126.sslip.io` (sslip.io → HTTPS sin DNS propio).
   - `POSTGRES_PASSWORD` = 48 hex aleatorios; `SECRET_KEY` = 96 hex aleatorios.
   - `GROQ_API_KEY` copiada desde la var de entorno User de la PC (pasada por stdin con encoding ASCII para no colar BOM).
   - ⚠️ Si hay que pasar el `.env` por PowerShell, **no** pipear strings directo a `ssh` (mete BOM/CRLF y se comen las comillas): generar en el server o copiar un script por `scp` (UTF8 sin BOM, LF).
5. ✅ **Levantado:** `docker compose up -d --build` — 3 contenedores `Up` (db healthy, web, caddy con restart `unless-stopped` → sobreviven reboot).
6. ✅ **Verificado:** `curl https://135.181.34.126.sslip.io/ping` → `{"status":"ok"}` (HTTP 200, cert al primer intento).
7. ✅ **End-to-end probado:** registro + login (cookie JWT) + POST `/gastos` "cafe 1500 y uber 3200" → el worker lo clasificó con **Groq** (Transporte $3200 / Comida y delivery $1500) y se persistió en Postgres. **El usuario de test (`test-deploy@example.com`) y sus datos se borraron de la base** (incluida `clasificacion_aprendida`, que tiene FK al usuario) → base limpia (0 filas en todas las tablas).

8. ✅ **Dominio lindo (DuckDNS):** se creó `gastos-ia.duckdns.org` apuntando a `135.181.34.126`, se cambió `DOMINIO` en el `.env` y se recreó Caddy (`docker compose up -d`) → reemitió el cert solo. `https://gastos-ia.duckdns.org/ping` → 200 OK.

> **Falta solo lo manual del navegador:** entrar a https://gastos-ia.duckdns.org, registrar tu cuenta real e instalar la PWA desde `/download`.

> Notas: Hetzner Ubuntu no tiene el doble-firewall de Oracle (puertos abiertos por defecto). La imagen
> es x86 (CX22). `create_all` arma el esquema en Postgres al arrancar. El worker corre como hilo dentro de la app.

## 6. Decisiones clave (para no re-discutir)
- **IA:** Groq (gratis), proveedor **conmutable** por `IA_PROVIDER` (`groq`/`deepseek`/`ollama`). Key en var de entorno.
- **DB:** Postgres en la VM (Docker) para multiusuario; SQLite sigue para dev local (el código soporta ambos).
- **HTTPS:** Caddy + **DuckDNS** (`gastos-ia.duckdns.org`, gratis). Para cambiar de dominio: apuntar el nuevo nombre a `135.181.34.126`, editar `DOMINIO` en `/opt/gastos/.env` y `docker compose up -d` (Caddy reemite el cert solo).
- **Rutas:** `/` = app/login · `/download` = landing PWA (botones instalar Android/iOS) · `/app` redirige a `/`. `manifest start_url=/`.
- **Login:** JWT en cookie HttpOnly + bcrypt. Registro abierto.

## 7. Pendientes a futuro (post-deploy)
- ✅ ~~Dominio lindo~~ → ya está en `gastos-ia.duckdns.org`.
- Backups de la base (Postgres) si se vuelve serio (el volumen `gastos_pgdata` tiene los datos).
- Ya andando en Hetzner: mergear `oracle` → `main` (o renombrar) para que sea la rama principal.
- Apagar Fly del todo si todavía quedaba algo corriendo (ya no se usa).

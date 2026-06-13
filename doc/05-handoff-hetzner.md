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

## 5. Lo que FALTA hacer (deploy en la VM, por SSH desde la PC)
1. ✅ **SSH verificado** — `ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126` entra OK con la clave. (Arrancar el próximo chat directo por el paso 2.)
2. **Instalar git + Docker:** `apt-get update -y && apt-get install -y git && curl -fsSL https://get.docker.com | sh`.
3. **Clonar rama oracle:** `git clone -b oracle https://github.com/juanzeballos/finanzasPersonales.git /opt/gastos`.
4. **Crear `/opt/gastos/.env`** (sin CRLF) con:
   - `DOMINIO=135.181.34.126.sslip.io`  ← **sslip.io** = HTTPS sin necesidad de DuckDNS ni dominio propio (apunta solo a esa IP; Caddy le saca el cert Let's Encrypt).
   - `POSTGRES_PASSWORD=` (generar aleatoria, URL-safe).
   - `GROQ_API_KEY=` (está en la **variable de entorno User `GROQ_API_KEY`** de la PC: `[Environment]::GetEnvironmentVariable("GROQ_API_KEY","User")`).
   - `SECRET_KEY=` (generar aleatoria larga).
5. **Levantar:** `cd /opt/gastos && docker compose up -d --build`.
6. **Verificar:** `docker compose ps`; esperar ~30s el cert y `curl https://135.181.34.126.sslip.io/ping` → `{"status":"ok"}`. Revisar `docker compose logs caddy` si el HTTPS no sale (rate limit de sslip.io es el único riesgo).
7. **Probar end-to-end:** entrar a `https://135.181.34.126.sslip.io`, registrarse, cargar un gasto, ver que clasifica (Groq) y aparece. Instalar la PWA.

> Notas: Hetzner Ubuntu no tiene el doble-firewall de Oracle (puertos abiertos por defecto). La imagen
> es x86 (CX22). `create_all` arma el esquema en Postgres al arrancar. El worker corre como hilo dentro de la app.

## 6. Decisiones clave (para no re-discutir)
- **IA:** Groq (gratis), proveedor **conmutable** por `IA_PROVIDER` (`groq`/`deepseek`/`ollama`). Key en var de entorno.
- **DB:** Postgres en la VM (Docker) para multiusuario; SQLite sigue para dev local (el código soporta ambos).
- **HTTPS:** Caddy + **sslip.io** (`<ip>.sslip.io`) → cero config DNS. Se puede pasar a DuckDNS/dominio propio después (cambiar `DOMINIO` en `.env` + DNS).
- **Rutas:** `/` = app/login · `/download` = landing PWA (botones instalar Android/iOS) · `/app` redirige a `/`. `manifest start_url=/`.
- **Login:** JWT en cookie HttpOnly + bcrypt. Registro abierto.

## 7. Pendientes a futuro (post-deploy)
- Cambiar `DOMINIO` a uno propio/DuckDNS si se quiere URL más linda.
- Backups de la base (Postgres) si se vuelve serio.
- Cuando esté andando en Hetzner, mergear `oracle` → `main` (o renombrar) para que sea la rama principal.

# Cómo funciona el servidor (Hetzner) — explicación sin tecnicismos

> Nota para entender el deploy y no depender de seguir pasos a ciegas.

## 1. Qué es el servidor
Hetzner te **alquila una computadora prendida 24/7** en un datacenter (una "CX22" con Ubuntu).
Su dirección en internet es la IP **`135.181.34.126`**. Es como una PC tuya pero que vive en
Alemania y nunca se apaga. No tiene pantalla: entrás **por SSH** con tu llave (igual que git).

## 2. El recorrido de un pedido (lo más importante)
Cuando alguien abre `https://gastos-ia.duckdns.org`:

```
📱 Celular
   │  (https://gastos-ia.duckdns.org)
   ▼
🌐 DuckDNS  → traduce el nombre lindo a la IP 135.181.34.126
   ▼
🖥️  SERVIDOR HETZNER
   ├─ 🚪 Caddy        → recibe en la puerta (HTTPS/candadito), reparte el tráfico
   │      ▼
   ├─ ⚙️  web (app)    → la lógica: login, clasificar gastos… (FastAPI)
   │      ▼
   └─ 🗄️  db (Postgres) → la base: usuarios, gastos, grupos…
```
El celu nunca habla directo con la base: habla con **Caddy** → **app** → **base**.
Por eso la base puede estar cerrada al mundo (se accede solo por túnel SSH, ver `doc/06`).

## 3. Las 3 "cajas" (Docker)
**Docker** son cajas aisladas dentro de la misma compu, cada una con un programa. No se instala
nada a mano: todo está definido en `docker-compose.yml` y Docker arma las cajas solo.

| Caja | Qué es | Comparación |
|---|---|---|
| `db` | Base de datos (Postgres) | el **archivero** |
| `web` | La app (código Python/FastAPI) | el **empleado** que atiende |
| `caddy` | Recibe de internet + HTTPS | el **recepcionista/portero** |

(El mismo Caddy también sirve otros sitios, ej. los del "Prode Liga Cañadense".)

## 4. Los archivos de configuración (en `/opt/gastos` del server)
- **`docker-compose.yml`** → la "receta": qué cajas levantar y cómo conectarlas. El corazón.
- **`Caddyfile`** → "para el dominio X, sacá HTTPS y mandá todo a la app (web:8080)".
- **`.env`** → el **sobre con secretos** (contraseña de la base, API key de Groq, SECRET_KEY).
  NUNCA se sube a GitHub.
- **`Dockerfile`** → cómo construir la caja de la app a partir del código.

## 5. Dos conceptos clave
- **Volúmenes:** las cajas son descartables (se recrean al actualizar). Para que los datos NO se
  pierdan, la base guarda todo en un **volumen** aparte (`gastos_pgdata`) que sobrevive. Por eso
  cada deploy conserva usuarios y gastos.
- **`restart: unless-stopped`:** si el server se reinicia (mantenimiento de Hetzner), las cajas
  **se vuelven a prender solas**. No hay que hacer nada.

## 6. Dominio y candadito (HTTPS)
- **DuckDNS** (gratis) convierte `gastos-ia.duckdns.org` en la IP.
- **Caddy** consigue solo el certificado HTTPS (Let's Encrypt, gratis) → el candadito 🔒. Automático.

## 7. Chuleta: "si algún día tengo que tocar algo"
Entrar: `ssh -i $env:USERPROFILE\.ssh\hetzner root@135.181.34.126` y `cd /opt/gastos`. Después:

| Quiero… | Comando |
|---|---|
| Ver si está todo prendido | `docker compose ps` |
| Ver errores de la app | `docker compose logs web --tail 50` |
| Subir una versión nueva del código | `git pull && docker compose up -d --build` |
| Reiniciar todo | `docker compose restart` |
| Apagar / prender | `docker compose down` / `docker compose up -d` |

**Idea central:** no se "configura el servidor" a mano — toda la config vive en los archivos del
repo (`docker-compose.yml`, `Caddyfile`, `Dockerfile`, `.env`), y Docker arma todo a partir de ellos.
Para cambiar algo, se edita el archivo, se sube (`git`) y se redeploya.

# 04 — Deploy a Fly.io (paso a paso)

Cómo poner la app en internet, disponible 24/7, en Fly.io. La app corre en un contenedor,
guarda la base en un **volumen persistente** y usa **Groq** como IA.

> ⚠️ **Aviso importante:** tal como está, la app **no tiene login**. Una vez deployada, **cualquiera
> con la URL puede ver y cargar gastos**. La URL es difícil de adivinar (`.fly.dev`), pero conviene
> agregar autenticación pronto (ver el final).

---

## Lo que ya dejamos preparado (en el repo)

- `Dockerfile` — receta del contenedor.
- `.dockerignore` — qué no copiar.
- `fly.toml` — config de Fly (puerto, volumen, auto-apagado).
- `database.py` lee `DATABASE_URL` de una variable → la apuntamos al volumen.

---

## Requisitos previos

1. **Cuenta en Fly.io** (https://fly.io/app/sign-up). Pide **tarjeta** al registrarse, pero con
   el auto-apagado (`min_machines_running = 0`) una app personal cuesta **centavos** (o nada).
2. **Una GROQ_API_KEY válida.** La que usamos antes era temporal de 24h y ya venció — sacá una
   nueva gratis en https://console.groq.com/keys.

---

## Pasos

### 1. Instalar flyctl (el CLI de Fly)
En PowerShell:
```powershell
pwr -useb https://fly.io/install.ps1 | iex
```
Cerrá y reabrí la terminal para que tome el `fly` en el PATH. Verificá con `fly version`.

### 2. Iniciar sesión
```powershell
fly auth login
```
(Se abre el navegador para loguearte.)

### 3. Elegir un nombre único para la app
Editá `fly.toml` y cambiá la línea `app = "finanzas-personales-jz"` por un nombre tuyo único
(ej. `finanzas-juanz-2026`). Si está ocupado, Fly te avisa.

### 4. Crear la app en tu cuenta (sin deployar todavía)
Desde la carpeta del proyecto:
```powershell
cd F:\proyectos\gastos-ia
fly launch --no-deploy
```
Cuando pregunte, **usá la configuración existente** (detecta el `Dockerfile` y el `fly.toml`).

### 5. Crear el volumen persistente (para la base)
```powershell
fly volumes create gastos_data --size 1 --region eze
```
El nombre `gastos_data` y la región deben coincidir con el `fly.toml`. `--size 1` = 1 GB (sobra).

### 6. Cargar los secretos (la key y la config)
```powershell
fly secrets set IA_PROVIDER=groq GROQ_API_KEY=tu_key_de_groq DATABASE_URL=sqlite:////data/gastos.db
```
- `DATABASE_URL=sqlite:////data/gastos.db` → la base vive en el volumen (los 4 `/` son a propósito:
  `sqlite://` + la ruta absoluta `/data/gastos.db`).
- Los secrets viven cifrados en Fly, **nunca en el código ni en la imagen**.

### 7. Deployar 🚀
```powershell
fly deploy
```
Fly construye la imagen con el `Dockerfile`, la sube y prende la máquina.

### 8. Abrir la app
```powershell
fly open
```
Queda en `https://<tu-app>.fly.dev`.

---

## Comandos útiles del día a día

| Acción | Comando |
|---|---|
| Ver logs en vivo | `fly logs` |
| Estado de la app | `fly status` |
| Redeployar tras cambios | `fly deploy` |
| Cambiar/agregar un secreto | `fly secrets set CLAVE=valor` |
| Apagar la app | `fly scale count 0` |
| Volver a prenderla | `fly scale count 1` |

> **Nota:** subir a GitHub (`git push`) **no** redeploya solo. El deploy se hace con `fly deploy`
> (más adelante se puede automatizar con GitHub Actions, pero no es necesario ahora).

---

## Cómo se comporta en Fly

- Con `auto_stop_machines`, la máquina **se apaga sola** cuando nadie la usa y **se prende** al
  primer pedido (tarda ~1-2s en despertar). Por eso gasta casi nada.
- El **worker** (que clasifica los gastos) corre dentro de la app: cuando la máquina está
  despierta, procesa las entradas pendientes. Mientras usás la app, está despierta.
- La **base** vive en el volumen `/data`, así que los datos **persisten** entre deploys y reinicios.

---

## Próximo paso recomendado: login

Como la app queda pública, lo ideal es agregar autenticación. Opciones simples:
- Una **clave única** (HTTP Basic Auth) — la más rápida, una sola contraseña para entrar.
- Usuario + contraseña con sesión.

Pedímelo y lo armamos antes de compartir la URL con nadie.

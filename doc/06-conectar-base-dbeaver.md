# Conectarse a la base de datos con DBeaver (vía túnel SSH)

> Nota práctica: cómo consultar la base de producción (Postgres en el server Hetzner)
> desde DBeaver en la PC. Igual que el SSH de git: hay una llave **privada** (queda en tu
> compu) y una **pública** (se registra en el server).

## La idea en simple
Los datos viven en una "pieza con llave" (Postgres) dentro del servidor. Esa pieza **no está
abierta a internet** por seguridad: solo se entra **por SSH** (la entrada segura del edificio),
y desde adentro se abre la base con usuario + contraseña.

Entonces en DBeaver se llenan **2 partes**:
1. **SSH** → entrar al edificio con la llave.
2. **Main** → abrir la base con usuario/contraseña.

## Datos de conexión (DBeaver, conexión PostgreSQL)

**Pestaña "SSH"** (tildar "Use SSH Tunnel"):
| Campo | Valor |
|---|---|
| Host/IP | `135.181.34.126` |
| Port | `22` |
| User Name | `root` |
| Authentication Method | **Public Key** *(NO "Password")* |
| Private Key | `C:\Users\54347\.ssh\hetzner_dbeaver` *(la RSA-PEM, ver abajo)* |
| Passphrase | *(vacío)* |

**Pestaña "Main":**
| Campo | Valor |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `gastos` |
| Username | `gastos` |
| Password | *(la del `.env` del server — ver "Sacar la contraseña")* |

> ⚠️ Importante: la base está publicada **solo en `127.0.0.1` del server** + detrás de SSH.
> NO está expuesta a internet. No cambiar eso a `0.0.0.0`.

## ⭐ El detalle clave de la llave
DBeaver **no lee** la llave `hetzner` (tipo `ed25519`, formato OpenSSH nuevo). Hay que usar una
llave **RSA en formato PEM** (`hetzner_dbeaver`), que DBeaver sí entiende. Ese fue el problema
del clásico error *"SSH password authentication failed / Exhausted available authentication methods"*.

## Receta: crear la llave de nuevo (si alguna vez hace falta)

**Paso 1 — Crear el par de archivos** (PowerShell en la PC):
```powershell
ssh-keygen -t rsa -b 4096 -m PEM -C "dbeaver-gastos" -f $env:USERPROFILE\.ssh\hetzner_dbeaver
```
- Cuando pida *"Enter passphrase"* → apretar **Enter dos veces** (sin contraseña).
- `-t rsa` = tipo clásico que cualquier programa lee · `-m PEM` = formato que DBeaver entiende.
- Crea 2 archivos: `hetzner_dbeaver` (privada, NO compartir) y `hetzner_dbeaver.pub` (pública).

**Paso 2 — Autorizar la pública en el server** (entra con la llave vieja `hetzner` que sí anda):
```powershell
type $env:USERPROFILE\.ssh\hetzner_dbeaver.pub | ssh -i $env:USERPROFILE\.ssh\hetzner root@135.181.34.126 "cat >> ~/.ssh/authorized_keys"
```
Esto agrega la pública a `~/.ssh/authorized_keys` del server (la lista de llaves que acepta).

## Sacar la contraseña de la base (no está en el repo, es secreta)
```powershell
ssh -i $env:USERPROFILE\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126 "grep '^POSTGRES_PASSWORD=' /opt/gastos/.env"
```

## Habilitar el puerto en el server (ya está hecho)
En `docker-compose.yml`, el servicio `db` publica el puerto solo en loopback:
```yaml
  db:
    ports:
      - "127.0.0.1:5432:5432"   # solo accesible por túnel SSH, NO desde internet
```

## Tablas para consultar
`usuarios`, `gastos`, `entradas`, `clasificacion_aprendida`.

> Si algún día perdés TODAS las llaves SSH, ya no podés entrar por acá: hay que usar la
> **consola web de Hetzner** (en el panel del servidor) para volver a cargar una clave.

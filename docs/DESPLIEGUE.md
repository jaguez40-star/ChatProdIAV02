# Despliegue de ProdIA V02

> Runbook operativo. Escrito para ejecutarse en el **139** sin necesidad de leer
> el plan de F6 ni esta conversación.

---

## 0. Lo que hay que saber antes de tocar nada

**El sistema viejo y ProdIA V02 conviven.** Los puertos no chocan:

| Sistema | Puertos | Estado |
|---|---|---|
| ProdIA viejo (Flask + FastAPI) | `8020`, `8088` | Sigue corriendo |
| **ProdIA V02** | **`6034`** | Se despliega en paralelo |
| Chatbot clásico | dentro de `:8020` | **No se toca nunca** |

Desplegar V02 **no retira nada**. El retiro del sistema viejo es una operación
aparte, manual y verificada paso a paso (F6, Bloque 5).

**Un solo puerto.** En producción el backend sirve también el frontend
compilado, así que no hay dev server de Vite ni `:6033`. Todo entra por `6034`.

---

## 1. Primera vez en una máquina

```bat
git clone https://github.com/jaguez40-star/ChatProdIAV02.git
cd ChatProdIAV02
pnpm setup
```

Luego crear el `.env`:

```bat
copy prodia_v02_backend\.env.example prodia_v02_backend\.env
```

y completarlo. **Lo mínimo que cambia respecto al ejemplo:**

```ini
APP_ENV=production
SERVE_STATIC=true
SECRET_KEY=<cadena aleatoria de 32+ caracteres — NO la del ejemplo>
PROD_DATABASE_URL=postgresql+psycopg2://usuario:clave@10.100.26.139:5432/daily_report_prod?sslmode=disable
OPS_DATABASE_URL=postgresql+psycopg2://robustez:clave%C2%A3aqui@10.100.26.139:5432/robustez_v02?sslmode=disable
ENABLE_LOCAL_LOGIN=false
CONSULTA_LLM_MODEL=gemma4:latest
EJECUTIVO_USAR_LLM=true
```

⚠️ **La contraseña de `robustez` lleva un `£`** que debe ir URL-encodeado como
`%C2%A3`, o SQLAlchemy falla al autenticar sin decir por qué.

⚠️ **`ENABLE_LOCAL_LOGIN=false` en producción.** Y `LOCAL_LOGIN_ALLOWED_IPS`
nunca admite `*`: el backend se niega a arrancar si lo lleva (D3).

Abrir el puerto en el firewall (una sola vez):

```bat
netsh advfirewall firewall add rule name="ProdIA V02 TCP In" dir=in action=allow protocol=TCP localport=6034
```

---

## 2. Desplegar una versión nueva

```bat
desplegar_v02.bat
```

Hace: `git pull` → `uv sync` + `pnpm install` → `alembic upgrade head` →
`pnpm build` → arranca en `:6034`.

**Aborta al primer error y no detiene el servicio anterior hasta el último
paso**, así que un fallo de compilación deja lo que ya estaba corriendo.

Para arrancar sin desplegar (por ejemplo tras reiniciar la máquina):

```bat
Start_Prod.bat
```

---

## 3. Verificar que quedó bien

```bat
curl http://localhost:6034/api/v1/health
```

Esperado:

```json
{"status":"ok","database_auth":"connected","database_prod":"connected",
 "database_ops":"connected","environment":"production"}
```

`degraded` significa que Postgres no responde: el backend arranca igual y el
login funciona, pero Análisis y Consulta devuelven 503 (decisión H9).

Luego, en el navegador — `http://<ip-del-139>:6034`:

| # | Prueba | Esperado |
|---|---|---|
| 1 | Abrir la raíz sin sesión | Pantalla de **login**, no un 401 |
| 2 | Entrar con usuario LDAP | Entra y ve el header con las secciones |
| 3 | Ir a `/analisis` y **recargar (F5)** | Sigue funcionando, **no un 404** |
| 4 | Consulta: preguntar «¿cuánto produjo Castilla?» | Responde con cifra y panel |

🔑 La prueba 3 es la que detecta un fallback SPA roto. Es lo primero que hace
cualquier usuario y lo último que se prueba.

### Gate de paridad — antes de retirar el sistema viejo

```bat
cd prodia_v02_backend
uv run python scripts\humo_paridad.py
```

Compara V02 contra las anclas de CLAUDE.md §6. **Sale con código 1 si alguna no
coincide.** No se retira nada hasta que salga en verde.

---

## 4. Rollback

El despliegue es un `git pull`, así que revertir es volver al commit anterior:

```bat
git log --oneline -5
git checkout <hash-anterior>
Start_Prod.bat
```

**Las migraciones no se revierten automáticamente.** Si el commit anterior es de
antes de una migración, hay que bajarla a mano:

```bat
cd prodia_v02_backend
uv run alembic downgrade -1
```

Solo afecta a `db_auth` (SQLite, usuarios y permisos). **Ninguna migración toca
`daily_report_prod`**: ese Postgres lo comparten los dos sistemas y V02 solo
escribe ahí desde Ingesta, con su propia transacción.

---

## 5. Problemas conocidos

### `os error 4551` al arrancar

WDAC / Smart App Control / el EDR corporativo bloquean el *trampoline* de `uv`
(`.venv\Scripts\python.exe`). No es una instalación rota de Python.

`Start_Prod.bat` ya lo rodea: lanza con el intérprete base que declara
`pyvenv.cfg` y exporta `PYTHONPATH` al `site-packages` del venv. Si ves el error,
es que cayó al fallback `uv run` porque no halló el intérprete base — revisa que
`prodia_v02_backend\.venv\pyvenv.cfg` exista y tenga la línea `home = ...`.

### `WinError 10048` — puerto ocupado

Un proceso anterior quedó a medio morir. `Start_Prod.bat` libera el puerto al
arrancar; si persiste:

```bat
netstat -ano | findstr ":6034"
taskkill /F /PID <pid>
```

### La página carga pero no hay datos

Casi siempre es la VPN o `PROD_DATABASE_URL`. Confirma con `/api/v1/health`: si
dice `degraded`, es la base de datos, no el frontend.

### Un 404 al recargar en `/analisis`

El fallback SPA no está activo. Verifica `SERVE_STATIC=true` en el `.env` y que
exista `prodia_v02_frontend\dist\index.html`.

### El log dice `static_no_montado`

Falta el build. Corre `pnpm build` — o `Start_Prod.bat`, que lo hace. El backend
arranca igual (queda solo como API), que es deliberado: en desarrollo nadie
compila el frontend y el import de `src.main` no puede depender del `dist/`.

---

## 6. Qué NO hace este despliegue

- **No migra datos.** `daily_report_prod` es el mismo Postgres que usa el
  sistema viejo (decisión U3). No hay ETL de corte.
- **No retira el sistema viejo.** Ver el Bloque 5 del plan de F6: es quirúrgico,
  ruta por ruta, y el chatbot clásico debe sobrevivir intacto.
- **No configura HTTPS.** Diferido a infraestructura, decisión heredada vigente.

# 03 — Teoría del Frontend (clase paso a paso)

Esta es la clase de la parte visual: lo que corre en el **navegador**. Está hecho en
**HTML + CSS + JavaScript puro**, sin React ni ningún framework, y sin paso de "build"
(no hay que compilar nada: son archivos que el navegador lee directo).

> **Idea base:** el frontend guarda un **estado** (los datos en memoria), dibuja la pantalla
> a partir de ese estado, y cuando algo cambia (cargás un gasto, llega la clasificación),
> vuelve a dibujar. Le habla al backend por HTTP con `fetch`.

---

## Paso 0 — Qué es una PWA y por qué sin framework

- **PWA** (Progressive Web App) = una web que se comporta como app: se puede "instalar",
  tiene ícono, etc. Se logra con dos archivos: `manifest.json` (metadatos) y `sw.js`
  (service worker).
- **Sin framework**: para una app chica, JS puro alcanza y se entiende todo (no hay magia
  escondida). React/Vue tienen sentido cuando la app crece mucho.

Tres archivos hacen el trabajo:
- `index.html` → la cáscara.
- `style.css` → cómo se ve.
- `app.js` → toda la lógica.

---

## Paso 1 — La cáscara (`index.html`)

Mínima a propósito: solo el header y un contenedor; el resto lo dibuja JavaScript.
```html
<body>
  <div class="app">
    <header class="header" id="header"></header>   <!-- lo llena app.js -->
    <main class="view" id="view"></main>            <!-- lo llena app.js -->
  </div>
  <script src="/static/app.js"></script>
</body>
```
La idea: el HTML es casi vacío; `app.js` **inyecta** el contenido dentro de `#header` y
`#view` según el estado.

---

## Paso 2 — El tema claro/oscuro (`style.css`)

Usamos **variables CSS**. Definís los colores una vez y los usás en todos lados:
```css
:root {                      /* tema claro (por defecto) */
  --bg: #F2F1ED;
  --ink: #1C1E26;            /* texto */
  --fijo: #4338CA; --necesario: #0E8C7F; --prescindible: #D97706;
}
html[data-theme="dark"] {    /* tema oscuro */
  --bg: #15161A;
  --ink: #ECEDEF;
  ...
}
body { background: var(--bg); color: var(--ink); }
```
Para cambiar de tema, JavaScript solo pone `data-theme="dark"` en el `<html>` y **todos** los
colores cambian solos (porque todo usa `var(--...)`). Es la forma más simple y potente de
hacer temas.

---

## Paso 3 — El estado (`app.js`)

Todo lo que la app "sabe" en un momento vive en un objeto `state`:
```js
const state = {
  tab: "registrar",        // pestaña activa: "registrar" | "mes"
  dark: false,             // tema
  expenses: [],            // gastos clasificados (vienen del backend)
  entradas: [],            // entradas pendientes / con error
  cursor: { y, m },        // mes que estás mirando
  draft: "",               // lo que estás tipeando
  open: new Set(),         // qué tarjetas están desplegadas
  ...
};
```
**Regla de oro:** la pantalla es un reflejo del estado. No tocás el HTML "a mano" en cada
lado; cambiás el `state` y volvés a dibujar. Eso mantiene todo coherente.

---

## Paso 4 — Dibujar (render)

Una función `render()` arma el HTML como **texto** y lo mete en la página:
```js
function render() {
  renderHeader();
  document.getElementById("view").innerHTML =
    state.tab === "registrar" ? renderRegistrar() : renderMes();
}
```
Cada `renderX()` devuelve un string de HTML construido con **template literals** (las comillas
`` ` `` que permiten meter variables con `${...}`):
```js
function cardHTML(e) {
  return `
    <div class="card">
      <span class="card-emoji">${e.emoji}</span>
      <div class="card-desc">${e.descripcion}</div>
      <span class="card-amount">${fmt(e.monto)}</span>
    </div>`;
}
```
Es "re-render completo": cada vez que algo cambia, reconstruimos esa sección entera. Simple
y predecible (React hace algo parecido pero optimizado; acá lo hacemos a mano).

> ⚠️ Siempre **escapá** lo que viene del usuario (función `esc()`) antes de meterlo en HTML,
> para no romper la página ni permitir inyección (es lo mínimo de seguridad).

---

## Paso 5 — Los eventos (delegación)

Como el HTML se reconstruye seguido, no conviene enganchar un listener a cada botón. Usamos
**delegación de eventos**: UN solo listener en `document` que mira qué se clickeó:
```js
document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  const a = el.dataset.action;
  if (a === "send")    enviar();
  else if (a === "tab")  { state.tab = el.dataset.tab; render(); }
  else if (a === "del")  borrar(Number(el.dataset.id));
  // ...
});
```
Cada botón lleva `data-action="..."` (y a veces `data-id`). El listener lee esos atributos y
decide qué hacer. Así funciona aunque el botón se haya recreado mil veces.

---

## Paso 6 — Las dos vistas

**Registrar (el chat):** muestra los gastos de hoy como tarjetas, las entradas "clasificando…"
como burbujas, y abajo el input para escribir. Apretás Enter o el botón → `enviar()`.

**El mes (el dashboard):** navegador de mes (‹ junio 2026 ›), el total, una **barra apilada**
de los 3 tipos, el dato de cuánto fue prescindible, un toggle "Por control / Por categoría"
con barras, y el botón "Consejo IA".

Las **barras** no usan ninguna librería de gráficos: son `<div>` con un ancho en %:
```js
`<div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>`
```
Simple, liviano y se entiende. (Antes usábamos Chart.js y lo sacamos: para barras no hace falta.)

---

## Paso 7 — Hablarle al backend (`fetch`)

`fetch` es la función del navegador para hacer pedidos HTTP. La envolvimos en un helper:
```js
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 204) return null;
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Error");
  return data;
}
const cargarGastos = () => api("/gastos");
const postGasto = (texto) => api("/gastos", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ texto }),
});
```
`async/await` es para esperar respuestas sin colgar el navegador (es asíncrono: mientras espera,
la pantalla sigue viva).

---

## Paso 8 — El polling (reflejar el worker) — ⭐ clave del flujo asíncrono

Como el backend clasifica **en segundo plano**, el front no recibe el resultado de inmediato.
Entonces **sondea** (pregunta cada 2s) hasta que ya no haya pendientes:
```js
function asegurarPolling() {
  if (!pollTimer) pollTimer = setInterval(refrescar, 2000);
}
async function refrescar() {
  state.expenses = await cargarGastos();
  state.entradas = await cargarEntradas();
  if (cambió_algo) render();
  if (no_hay_pendientes) { clearInterval(pollTimer); pollTimer = null; }  // frena solo
}
```
Flujo: cargás un gasto → aparece la burbuja "clasificando…" → el polling pregunta cada 2s →
cuando el worker terminó, la burbuja desaparece y aparece la tarjeta clasificada → si no quedan
pendientes, el polling **se detiene solo** (para no consultar para siempre).

---

## Paso 9 — Que no parpadee (dos trucos finos)

El polling cada 2s, hecho ingenuamente, **repinta toda la pantalla** cada 2s → parpadeo molesto.
Dos arreglos:

1. **Re-renderizar solo si cambió algo.** Hacemos un "snapshot" (un resumen en texto de los
   datos) y solo dibujamos si difiere del anterior:
   ```js
   if (snapshot() !== ultimoSnapshot) render();
   ```
2. **Animar cada cosa una sola vez.** La animación de entrada de las tarjetas se aplicaba en
   cada repintado. Con un `Set` de "ya vistos", solo le ponemos la clase de animación a los
   elementos nuevos:
   ```js
   function popOnce(id) { if (vistos.has(id)) return ""; vistos.add(id); return "pop"; }
   ```

Resultado: la pantalla queda **quieta**, y solo se anima lo que realmente aparece.

---

## Paso 10 — Tema persistente + PWA

- **Tema:** se guarda en `localStorage` para que recuerde tu preferencia entre sesiones:
  ```js
  localStorage.setItem("gastos-theme-v1", "dark");
  ```
- **PWA:** `manifest.json` define nombre, ícono y colores; `sw.js` (service worker) es un script
  que el navegador registra y que habilita que la app sea "instalable". Por ahora es mínimo
  (la parte offline queda para más adelante).

---

## Receta: hacerlo de cero, en orden

1. `index.html` con el header y un `<main id="view">` vacío + `<script>`.
2. `style.css` con las variables de color (claro/oscuro) y unos estilos base.
3. `app.js`: el objeto `state` y una `render()` que dibuje algo simple (ej. "Hola").
4. **Cargar y mostrar:** un `fetch("/gastos")` al iniciar y dibujar las tarjetas.
5. **Registrar:** el input + `enviar()` que hace el `POST` y agrega la burbuja pendiente.
6. **Eventos:** el listener de delegación (`data-action`) para tabs, enviar, borrar.
7. **El mes:** la vista con total y barras (div con `width:%`).
8. **Polling:** `setInterval` que refresca mientras haya pendientes.
9. **Pulido:** anti-parpadeo (snapshot), animación una sola vez, tema en `localStorage`.
10. **PWA:** `manifest.json` + `sw.js`.

Igual que en el backend: andá en orden, teniendo **algo que se ve y funciona en cada paso**.
Primero que se dibuje algo, después que cargue datos, después que escriba, y al final el pulido.

---

## Resumen mental del frontend

```
state (los datos)  ──render()──►  HTML en pantalla
   ▲                                   │
   │                                   │ (click / Enter)
   └──── eventos / fetch / polling ◄───┘
```
Cambiás el estado → redibujás. Los eventos y las respuestas del backend cambian el estado.
Ese ciclo simple es, en el fondo, lo que hacen también los frameworks grandes.

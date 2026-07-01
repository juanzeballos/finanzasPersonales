// Genera capacitacion-completa.html concatenando los .md en orden,
// con marked + mermaid (CDN), CSS de impresión y saltos de página por etapa.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const dir = dirname(fileURLToPath(import.meta.url));
const order = [
  "00-indice.md",
  "etapa-0-por-que-eventos.md",
  "etapa-1-vocabulario-mensajeria.md",
  "etapa-2-rabbitmq-en-el-proyecto.md",
  "etapa-3-hexagonal-clean-cqrs.md",
  "etapa-4-recorrido-microservicios.md",
  "etapa-5-patrones.md",
  "etapa-6-flujos-end-to-end.md",
  "etapa-7-infraestructura.md",
  "etapa-8-consolidar.md",
  "apendice-A-fundamentos-docker-k8s.md",
  "99-respuestas.md",
];

const docs = order.map((f) => readFileSync(join(dir, f), "utf8"));
const payload = JSON.stringify(docs);

const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Capacitación — Programación orientada a eventos (GWP)</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  :root { --ink:#1a1a1a; --muted:#555; --line:#d0d0d0; --accent:#b5341a; --code-bg:#f5f5f5; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--ink); line-height: 1.55; max-width: 46rem; margin: 0 auto;
    padding: 2rem 1.5rem; font-size: 11.5pt;
  }
  h1 { font-size: 1.9rem; border-bottom: 3px solid var(--accent); padding-bottom: .3rem; }
  h2 { font-size: 1.4rem; margin-top: 1.8rem; color: #111; }
  h3 { font-size: 1.12rem; margin-top: 1.3rem; }
  a { color: var(--accent); text-decoration: none; }
  code { background: var(--code-bg); padding: .1rem .3rem; border-radius: 3px; font-size: .88em; }
  pre { background: var(--code-bg); padding: .8rem 1rem; border-radius: 6px; overflow-x: auto;
        border: 1px solid var(--line); font-size: .82rem; line-height: 1.4; }
  pre code { background: none; padding: 0; }
  blockquote { border-left: 4px solid var(--accent); margin: 1rem 0; padding: .3rem 0 .3rem 1rem;
               color: var(--muted); background: #fafafa; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
  th, td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; vertical-align: top; }
  th { background: #f0f0f0; }
  hr { border: none; border-top: 1px solid var(--line); margin: 1.5rem 0; }
  .mermaid { text-align: center; margin: 1.2rem 0; }
  .doc { page-break-after: always; }
  .doc:last-child { page-break-after: auto; }
  @media print {
    body { padding: 0; max-width: none; }
    pre, table, blockquote, .mermaid { page-break-inside: avoid; }
    h2, h3 { page-break-after: avoid; }
  }
  @page { margin: 16mm 14mm; }
</style>
</head>
<body>
<div id="content"></div>
<script>
  const DOCS = ${payload};
  marked.setOptions({ gfm: true, breaks: false });
  const container = document.getElementById("content");
  for (const md of DOCS) {
    const div = document.createElement("div");
    div.className = "doc";
    div.innerHTML = marked.parse(md);
    container.appendChild(div);
  }
  // Reemplazar bloques \`\`\`mermaid por divs que mermaid pueda renderizar
  document.querySelectorAll("code.language-mermaid").forEach((code) => {
    const pre = code.closest("pre");
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = code.textContent;
    pre.replaceWith(div);
  });
  mermaid.initialize({ startOnLoad: false, theme: "neutral" });
  mermaid.run().then(() => { window.__renderDone = true; })
              .catch((e) => { console.error(e); window.__renderDone = true; });
</script>
</body>
</html>`;

writeFileSync(join(dir, "capacitacion-completa.html"), html, "utf8");
console.log("HTML generado: capacitacion-completa.html");

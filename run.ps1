# Lanzador del backend de Gastos IA.
# Lee las variables persistentes (nivel usuario) DIRECTO del registro, así funciona
# aunque la terminal sea vieja (las terminales abiertas no ven cambios de entorno).

$env:IA_PROVIDER      = [Environment]::GetEnvironmentVariable("IA_PROVIDER", "User")
$env:GROQ_API_KEY     = [Environment]::GetEnvironmentVariable("GROQ_API_KEY", "User")
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
$env:OLLAMA_MODEL     = [Environment]::GetEnvironmentVariable("OLLAMA_MODEL", "User")

if (-not $env:IA_PROVIDER) { $env:IA_PROVIDER = "ollama" }

Write-Host "Arrancando backend con IA_PROVIDER = $($env:IA_PROVIDER)" -ForegroundColor Cyan

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

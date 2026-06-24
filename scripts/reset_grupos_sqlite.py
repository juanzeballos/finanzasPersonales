"""Resetea las tablas de GRUPOS en la base local de dev (SQLite).

El refactor a `Participante` cambió columnas (ronda_participantes/gastos_grupo ahora usan
participante_id) y `create_all` NO modifica tablas existentes. Esto borra solo las tablas de
grupo (datos de PRUEBA) para que se recreen con el esquema nuevo al reiniciar la app.
NO toca usuarios ni gastos personales.

Correr una vez:  .\.venv\Scripts\python.exe scripts\reset_grupos_sqlite.py
Después reiniciar run.ps1 (create_all recrea las tablas).
"""
import sqlite3

con = sqlite3.connect("gastos.db")
for t in ("gastos_grupo", "ronda_participantes", "rondas", "participantes", "grupo_miembros", "grupos"):
    con.execute(f"DROP TABLE IF EXISTS {t}")
    print("drop", t)
con.commit()
con.close()
print("listo — reiniciá run.ps1 y create_all recrea las tablas de grupo con el esquema nuevo")

"""Migración local (SQLite dev): agrega la columna divisa a gastos y entradas.

create_all no modifica tablas existentes, así que esta columna hay que agregarla a mano.
Idempotente: si la columna ya existe, lo informa y sigue.
"""
import sqlite3

con = sqlite3.connect("gastos.db")
for tabla in ("gastos", "entradas"):
    try:
        con.execute(f"ALTER TABLE {tabla} ADD COLUMN divisa VARCHAR NOT NULL DEFAULT 'ARS'")
        print(f"{tabla}: columna divisa agregada")
    except sqlite3.OperationalError as e:
        print(f"{tabla}: {e}")   # 'duplicate column name' si ya existía
con.commit()
con.close()

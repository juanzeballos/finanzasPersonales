"""Migración local (SQLite dev): agrega la columna fecha_gasto a entradas.

create_all no modifica tablas existentes. Idempotente: si ya existe, lo informa y sigue.
"""
import sqlite3

con = sqlite3.connect("gastos.db")
try:
    con.execute("ALTER TABLE entradas ADD COLUMN fecha_gasto DATE")
    print("entradas: columna fecha_gasto agregada")
except sqlite3.OperationalError as e:
    print(f"entradas: {e}")
con.commit()
con.close()

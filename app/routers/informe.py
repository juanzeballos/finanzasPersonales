"""Endpoint del informe: arma el resumen del mes (con porcentajes) y pide consejos a la IA."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import ia
from ..database import get_db
from .gastos import calcular_resumen

router = APIRouter()


def _formatear_resumen(resumen: dict) -> str:
    """Convierte el resumen en texto con porcentajes YA calculados, para el prompt.

    Así el modelo solo redacta el consejo; la matemática la hace Python (los modelos
    chicos se equivocan con porcentajes).
    """
    total = resumen["total"] or 1  # evita división por cero
    lineas = [f"Total del mes: ${resumen['total']:,.0f}", "", "Por tipo:"]
    for fila in sorted(resumen["por_tipo"], key=lambda f: f["total"], reverse=True):
        pct = fila["total"] / total * 100
        lineas.append(f"  - {fila['tipo']}: ${fila['total']:,.0f} ({pct:.0f}%)")
    lineas.append("")
    lineas.append("Por categoría:")
    for fila in sorted(resumen["por_categoria"], key=lambda f: f["total"], reverse=True):
        pct = fila["total"] / total * 100
        lineas.append(f"  - {fila['categoria']}: ${fila['total']:,.0f} ({pct:.0f}%)")
    return "\n".join(lineas)


@router.post("/informe")
def generar_informe(mes: str = Query(..., description="Mes en formato YYYY-MM"), db: Session = Depends(get_db)):
    resumen = calcular_resumen(db, mes)
    if resumen["total"] == 0:
        return {"mes": mes, "consejo": "Todavía no hay gastos cargados en este mes."}
    try:
        consejo = ia.generar_informe(_formatear_resumen(resumen))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de la IA: {e}")
    return {"mes": mes, "consejo": consejo, "resumen": resumen}

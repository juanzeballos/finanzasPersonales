from app import clasificador, models, schemas, worker


def test_falta_monto(Session, monkeypatch):
    db = Session()
    # IA: detecta "café" pero sin monto -> missing
    def fake(_texto):
        return schemas.ClasificacionIA(items=[], missing=["café"])
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)

    entrada = models.Entrada(usuario_id=1, texto="café", divisa="ARS")
    db.add(entrada)
    db.commit()

    worker._procesar_una(db, entrada.id)
    db.refresh(entrada)

    assert entrada.estado == "falta_monto"
    assert "monto" in entrada.error.lower()
    assert "café" in entrada.error

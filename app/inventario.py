from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from .db import engine

router = APIRouter(prefix='/api/productos', tags=['Inventario'])

@router.get('')
def catalogo():
    with engine.connect() as c:
        return [dict(p) for p in c.execute(text('SELECT id,nombre,precio_centavos,stock FROM productos ORDER BY id')).mappings()]

@router.get('/{producto_id}')
def producto(producto_id: str):
    with engine.connect() as c:
        p = c.execute(text('SELECT id,nombre,precio_centavos,stock FROM productos WHERE id=:id'), {'id':producto_id}).mappings().first()
    if p is None: raise HTTPException(404, 'Producto no encontrado')
    return dict(p)

import hashlib, json
from uuid import UUID, uuid4
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from .db import engine
from .usuarios import usuario_actual

router = APIRouter(prefix='/api/pedidos', tags=['Pedidos'])

class Item(BaseModel):
    producto_id: str = Field(min_length=1,max_length=80)
    cantidad: int = Field(strict=True,gt=0,le=100)

class Compra(BaseModel):
    items: list[Item] = Field(min_length=1,max_length=20)

def detalle(c, pedido):
    items = [dict(i) for i in c.execute(text('''SELECT producto_id,nombre,cantidad,precio_centavos
        FROM detalles_pedido WHERE pedido_id=:id ORDER BY producto_id'''), {'id':pedido['id']}).mappings()]
    return {**dict(pedido),'moneda':'MXN','items':items}

@router.post('', status_code=201)
def comprar(compra: Compra, response: Response,
            clave: Annotated[str,Header(alias='Idempotency-Key',min_length=8,max_length=128)],
            usuario=Depends(usuario_actual)):
    cantidades = {}
    for item in compra.items:
        cantidades[item.producto_id] = cantidades.get(item.producto_id,0) + item.cantidad
    if any(cantidad > 100 for cantidad in cantidades.values()):
        raise HTTPException(422, 'Máximo 100 unidades por producto')
    contenido = json.dumps(cantidades, sort_keys=True, separators=(',',':'))
    solicitud_hash = hashlib.sha256(contenido.encode()).hexdigest()
    # La misma compra se serializa entre procesos y réplicas usando PostgreSQL, no un Map local.
    lock = int.from_bytes(hashlib.sha256((str(usuario['id'])+':'+clave).encode()).digest()[:8],'big',signed=True)
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(:lock)'), {'lock':lock})
        previo = c.execute(text('''SELECT id,usuario_id,total_centavos,estado,creado_en,solicitud_hash FROM pedidos
            WHERE usuario_id=:usuario AND clave=:clave'''), dict(usuario=usuario['id'],clave=clave)).mappings().first()
        if previo:
            if previo['solicitud_hash'] != solicitud_hash:
                raise HTTPException(409, 'La llave ya se usó para otra compra')
            response.status_code=200
            response.headers['Idempotent-Replayed']='true'
            return detalle(c,{k:v for k,v in previo.items() if k!='solicitud_hash'})
        productos = []
        # Orden fijo de candados para compras con varios productos.
        for producto_id,cantidad in sorted(cantidades.items()):
            p = c.execute(text('SELECT * FROM productos WHERE id=:id FOR UPDATE'),{'id':producto_id}).mappings().first()
            if p is None: raise HTTPException(404,'Producto no encontrado: '+producto_id)
            if p['stock'] < cantidad: raise HTTPException(409,'Stock insuficiente: '+producto_id)
            productos.append((p,cantidad))
        total = sum(p['precio_centavos']*cantidad for p,cantidad in productos)
        pedido = c.execute(text('''INSERT INTO pedidos(id,usuario_id,clave,solicitud_hash,total_centavos,estado)
            VALUES(:id,:usuario,:clave,:hash,:total,'CONFIRMADO')
            RETURNING id,usuario_id,total_centavos,estado,creado_en'''),
            dict(id=uuid4(),usuario=usuario['id'],clave=clave,hash=solicitud_hash,total=total)).mappings().one()
        for p,cantidad in productos:
            c.execute(text('UPDATE productos SET stock=stock-:cantidad WHERE id=:id'), dict(cantidad=cantidad,id=p['id']))
            c.execute(text('''INSERT INTO detalles_pedido(pedido_id,producto_id,nombre,cantidad,precio_centavos)
                VALUES(:pedido,:producto,:nombre,:cantidad,:precio)'''),
                dict(pedido=pedido['id'],producto=p['id'],nombre=p['nombre'],cantidad=cantidad,precio=p['precio_centavos']))
        resultado=detalle(c,pedido)
    # El contexto transaccional confirma ANTES de responder éxito.
    return resultado

@router.get('')
def mis_pedidos(usuario=Depends(usuario_actual)):
    with engine.connect() as c:
        pedidos = c.execute(text('''SELECT id,usuario_id,total_centavos,estado,creado_en FROM pedidos
            WHERE usuario_id=:usuario ORDER BY creado_en DESC LIMIT 100'''),{'usuario':usuario['id']}).mappings()
        return [detalle(c,p) for p in pedidos]

@router.get('/{pedido_id}')
def consultar_pedido(pedido_id: UUID,usuario=Depends(usuario_actual)):
    with engine.connect() as c:
        pedido=c.execute(text('''SELECT id,usuario_id,total_centavos,estado,creado_en FROM pedidos
            WHERE id=:id AND usuario_id=:usuario'''),{'id':pedido_id,'usuario':usuario['id']}).mappings().first()
        if pedido is None: raise HTTPException(404,'Pedido no encontrado')
        return detalle(c,pedido)

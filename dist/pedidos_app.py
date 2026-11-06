import os,json,hashlib,time,threading,copy
from uuid import UUID,uuid4
from contextlib import asynccontextmanager
from typing import Annotated
from datetime import datetime,timezone
import httpx
from fastapi import FastAPI,Header,HTTPException,Depends,Request,Response
from pydantic import BaseModel,Field
from sqlalchemy import text
from .sql import engine,initialize
from .comun import instrumentar,log
from .remotos import inventario,Rechazo,NoDisponible,circuito

stop=threading.Event()
class Item(BaseModel):
    producto_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    cantidad:int=Field(strict=True,gt=0,le=100)
class Compra(BaseModel):items:list[Item]=Field(min_length=1,max_length=20)

def leer(id):
    with engine.connect() as c:
        row=c.execute(text('SELECT * FROM pedidos WHERE id=:id'),dict(id=id)).mappings().first()
        return dict(row) if row else None
def persistir(id,items,estado,motivo=None):
    total=sum(i.get('precio_centavos',0)*i['cantidad'] for i in items) if estado=='CONFIRMADO' else None
    h=json.dumps([dict(estado=estado,fecha=datetime.now(timezone.utc).isoformat())])
    with engine.begin() as c:
        c.execute(text('''UPDATE pedidos SET items=CAST(:items AS jsonb),estado=:estado,motivo=:motivo,
            total_centavos=:total,actualizado_en=now(),historial=historial || CAST(:h AS jsonb)
            WHERE id=:id'''),dict(id=id,items=json.dumps(items),estado=estado,motivo=motivo,total=total,h=h))

def procesar(id):
    # Candado de sesion: un trabajador por pedido. Los commits de progreso son independientes
    # de las llamadas HTTP y sobreviven a la muerte del proceso.
    k=int.from_bytes(hashlib.sha256(('saga:'+str(id)).encode()).digest()[:8],'big',signed=True)
    with engine.connect() as guard:
        if not guard.execute(text('SELECT pg_try_advisory_lock(:k)'),dict(k=k)).scalar():return
        guard.commit()
        try:
            p=leer(id)
            if not p or p['estado'] not in ('PENDIENTE','COMPENSANDO'):return
            items=copy.deepcopy(p['items']);trace=p['trace_id'];estado=p['estado'];motivo=p['motivo']
            if estado=='PENDIENTE':
                for item in items:
                    if item.get('reserva') in ('RESERVADA','CONFIRMADA'):continue
                    try:
                        r=inventario('/interno/productos/'+item['producto_id']+'/reservas',
                            dict(pedido_id=str(id),cantidad=item['cantidad']),trace)
                    except Rechazo as e:
                        estado='COMPENSANDO';motivo=str(e)
                        persistir(id,items,estado,motivo);break
                    item.update(reserva=r['estado'],nombre=r['nombre'],precio_centavos=r['precio_centavos'])
                    persistir(id,items,'PENDIENTE')
            if estado=='COMPENSANDO':
                for item in items:
                    if item.get('reserva')=='LIBERADA' or not item.get('reserva'):continue
                    try:
                        inventario('/interno/productos/'+item['producto_id']+'/reservas/'+str(id)+'/liberar',{},trace)
                    except Rechazo as e:
                        persistir(id,items,'REVISION_PENDIENTE',str(e));return
                    item['reserva']='LIBERADA';persistir(id,items,'COMPENSANDO',motivo)
                persistir(id,items,'RECHAZADO',motivo);return
            for item in items:
                if item.get('reserva')=='CONFIRMADA':continue
                try:
                    inventario('/interno/productos/'+item['producto_id']+'/reservas/'+str(id)+'/confirmar',{},trace)
                except Rechazo as e:
                    persistir(id,items,'REVISION_PENDIENTE',str(e));return
                item['reserva']='CONFIRMADA';persistir(id,items,'PENDIENTE')
            persistir(id,items,'CONFIRMADO')
        except Exception as e:
            log.exception('saga_pendiente pedido=%s',id)
            with engine.begin() as c:
                c.execute(text('''UPDATE pedidos SET intentos=intentos+1,motivo=:motivo,
                    proximo=now()+least(30,power(2,least(intentos+1,5))) * interval '1 second'
                    WHERE id=:id AND estado IN ('PENDIENTE','COMPENSANDO')'''),dict(id=id,motivo=str(e)[:300]))
        finally:
            guard.execute(text('SELECT pg_advisory_unlock(:k)'),dict(k=k));guard.commit()

def trabajador():
    while not stop.is_set():
        try:
            with engine.connect() as c:
                ids=c.execute(text('''SELECT id FROM pedidos WHERE estado IN ('PENDIENTE','COMPENSANDO')
                    AND proximo<=now() ORDER BY creado_en LIMIT 20''')).scalars().all()
            for id in ids:
                if stop.is_set():break
                procesar(id)
        except Exception:log.exception('trabajador_saga')
        stop.wait(1)

@asynccontextmanager
async def lifespan(app):
    initialize();stop.clear();hilo=threading.Thread(target=trabajador,daemon=True);hilo.start()
    yield;stop.set();hilo.join(timeout=5);engine.dispose()

app=FastAPI(title='Docker Rangers · Pedidos',lifespan=lifespan)
instrumentar(app)
def usuario(request:Request,authorization:Annotated[str|None,Header()]=None):
    if not authorization:raise HTTPException(401,'Se requiere sesión')
    try:r=httpx.get(os.environ['USUARIOS_URL']+'/api/usuarios/me',headers={'Authorization':authorization,
        'X-Request-ID':request.state.trace_id},timeout=httpx.Timeout(3,connect=1))
    except httpx.HTTPError:raise HTTPException(503,'No se pudo verificar la sesión')
    if r.status_code==401:raise HTTPException(401,'Sesión inválida o vencida')
    if r.status_code!=200:raise HTTPException(503,'No se pudo verificar la sesión')
    return UUID(r.json()['id'])
def vista(p):
    return {k:p[k] for k in ('id','items','estado','motivo','total_centavos','creado_en','actualizado_en','historial')}

@app.post('/api/pedidos',status_code=201)
def comprar(compra:Compra,response:Response,request:Request,
            clave:Annotated[str,Header(alias='Idempotency-Key',min_length=8,max_length=128)],u=Depends(usuario)):
    cantidades={}
    for i in compra.items:cantidades[i.producto_id]=cantidades.get(i.producto_id,0)+i.cantidad
    if any(q>100 for q in cantidades.values()):raise HTTPException(422,'Máximo 100 unidades por producto')
    items=[dict(producto_id=p,cantidad=q) for p,q in sorted(cantidades.items())]
    fingerprint=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()
    key=int.from_bytes(hashlib.sha256((str(u)+':'+clave).encode()).digest()[:8],'big',signed=True)
    repetido=False
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(:k)'),dict(k=key))
        anterior=c.execute(text('SELECT id,solicitud_hash FROM pedidos WHERE usuario_id=:u AND clave=:k'),dict(u=u,k=clave)).mappings().first()
        if anterior:
            if anterior['solicitud_hash']!=fingerprint:raise HTTPException(409,'La llave ya se usó para otra compra')
            id=anterior['id'];repetido=True
        else:
            id=uuid4()
            c.execute(text('''INSERT INTO pedidos(id,usuario_id,clave,solicitud_hash,items,estado,trace_id,historial)
                VALUES(:id,:u,:k,:h,CAST(:items AS jsonb),'PENDIENTE',:trace,CAST(:hist AS jsonb))'''),
                dict(id=id,u=u,k=clave,h=fingerprint,items=json.dumps(items),trace=request.state.trace_id,
                hist=json.dumps([dict(estado='PENDIENTE',fecha=datetime.now(timezone.utc).isoformat())])))
    procesar(id);p=leer(id)
    if p['estado']=='CONFIRMADO':response.status_code=200 if repetido else 201
    elif p['estado']=='RECHAZADO':response.status_code=409
    else:response.status_code=202
    if repetido:response.headers['Idempotent-Replayed']='true'
    return vista(p)

@app.get('/api/pedidos/{id}')
def consultar(id:UUID,u=Depends(usuario)):
    p=leer(id)
    if not p or p['usuario_id']!=u:raise HTTPException(404,'Pedido no encontrado')
    return vista(p)
@app.get('/api/pedidos')
def mis_pedidos(u=Depends(usuario)):
    with engine.connect() as c:
        rows=c.execute(text('SELECT * FROM pedidos WHERE usuario_id=:u ORDER BY creado_en DESC LIMIT 100'),dict(u=u)).mappings()
        return [vista(dict(p)) for p in rows]
@app.get('/health')
def health():
    with engine.connect() as c:c.execute(text('SELECT 1'))
    return dict(status='ok',servicio='pedidos',circuito=circuito.foto())

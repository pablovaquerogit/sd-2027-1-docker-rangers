"""Pruebas HTTP con los servicios distribuidos reales. Datos ficticios y productos propios de prueba."""
import json,urllib.request,urllib.error,time,uuid,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='http://localhost:18091'
def compose(*args):
    return subprocess.run(['docker','compose','-f',str(ROOT/'compose.distribuido.yml'),*args],
        check=True,capture_output=True,text=True).stdout
def mongo(js):
    return json.loads(compose('exec','-T','mongo','mongosh','--quiet','inventario','--eval','JSON.stringify('+js+')'))
def http(path,body=None,headers=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json',**(headers or {})})
    try:r=urllib.request.urlopen(req,timeout=30)
    except urllib.error.HTTPError as e:r=e
    raw=r.read().decode()
    try:data=json.loads(raw)
    except ValueError:data=raw
    return dict(status=r.code,body=data,instancia=r.headers.get('X-Instancia'),trace_id=r.headers.get('X-Request-ID'))
def sesion():
    correo=str(uuid.uuid4())+'@example.test'
    r=http('/api/usuarios',dict(correo=correo,nombre='Prueba distribuida',password='password-demo-123'))
    assert r['status']==201,r
    s=http('/api/sesiones',dict(correo=correo,password='password-demo-123'))
    assert s['status']==200,s
    return {'Authorization':'Bearer '+s['body']['access_token']}
def producto(prefijo,stock):
    id=prefijo+'-'+str(uuid.uuid4())[:8]
    mongo('db.productos.insertOne('+json.dumps(dict(_id=id,nombre='Producto de prueba',precio_centavos=1234,stock=stock,reservas={})) +')')
    return id
def comprar(auth,p,cantidad=1,key=None):
    return http('/api/pedidos',{'items':[dict(producto_id=p,cantidad=cantidad)]},
        {**auth,'Idempotency-Key':key or str(uuid.uuid4())})
def final(auth,id):
    for _ in range(180):
        r=http('/api/pedidos/'+id,headers=auth)
        if r['status']==200 and r['body']['estado'] not in ('PENDIENTE','COMPENSANDO'):return r
        time.sleep(.5)
    raise AssertionError(r)

def main():
    resultado={};auth=sesion();otro=sesion()
    lecturas=[http('/api/productos') for _ in range(8)]
    assert all(r['status']==200 for r in lecturas)
    assert len({r['instancia'] for r in lecturas})==2,lecturas
    resultado['balanceo']=[dict(instancia=r['instancia'],status=r['status']) for r in lecturas]
    p=producto('idempotencia',5);key=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=5) as pool:respuestas=list(pool.map(lambda _:comprar(auth,p,key=key),range(5)))
    ids={r['body']['id'] for r in respuestas};assert len(ids)==1,respuestas
    id=ids.pop();f=final(auth,id);assert f['body']['estado']=='CONFIRMADO',f
    assert http('/api/productos/'+p)['body']['stock']==4
    assert comprar(auth,p,cantidad=2,key=key)['status']==409
    assert http('/api/pedidos/'+id,headers=otro)['status']==404
    assert http('/api/pedidos/'+id)['status']==401
    resultado['idempotencia_concurrente']=dict(pedido=f,stock=4,intentos=5)
    p=producto('concurrencia',3)
    with ThreadPoolExecutor(max_workers=5) as pool:rs=list(pool.map(lambda _:comprar(auth,p),range(10)))
    finales=[final(auth,r['body']['id']) for r in rs]
    estados=[r['body']['estado'] for r in finales]
    assert estados.count('CONFIRMADO')==3 and estados.count('RECHAZADO')==7,estados
    assert http('/api/productos/'+p)['body']['stock']==0
    resultado['sin_sobreventa']=dict(estados=estados,stock=0)
    a=producto('comp-a',5);b=producto('comp-b',0)
    r=http('/api/pedidos',dict(items=[dict(producto_id=a,cantidad=2),dict(producto_id=b,cantidad=1)]),
        {**auth,'Idempotency-Key':str(uuid.uuid4())})
    f=final(auth,r['body']['id']);assert f['body']['estado']=='RECHAZADO',f
    assert http('/api/productos/'+a)['body']['stock']==5
    assert any(h['estado']=='COMPENSANDO' for h in f['body']['historial'])
    resultado['compensacion']=dict(pedido=f,stock_restaurado=5)
    assert comprar(auth,a,cantidad=True)['status']==422
    assert http('/interno/productos/'+a+'/reservas',dict(pedido_id=str(uuid.uuid4()),cantidad=1))['status']==404
    resultado['validacion_y_rutas_internas']='aprobadas'
    p=producto('recuperacion',5)
    compose('stop','inventario-lb')
    try:
        pendiente=comprar(auth,p);assert pendiente['status']==202,pendiente
        id=pendiente['body']['id'];assert pendiente['body']['estado']=='PENDIENTE',pendiente
        compose('restart','pedidos')
        limite=time.monotonic()+90
        while time.monotonic()<limite:
            try:
                despues=http('/api/pedidos/'+id,headers=auth)
                if despues['status']==200:break
            except Exception:pass
            time.sleep(.5)
        assert despues['status']==200 and despues['body']['estado']=='PENDIENTE',despues
    finally:compose('start','inventario-lb')
    f=final(auth,id);assert f['body']['estado']=='CONFIRMADO',f
    assert http('/api/productos/'+p)['body']['stock']==4
    resultado['recuperacion_tras_reinicio']=dict(antes=pendiente,despues_del_reinicio=despues,final=f,stock=4)
    resultado['fecha_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    out=ROOT/'evidencia/pruebas-distribuidas.json';out.write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+'\n')
    print('APROBADAS: balanceo, idempotencia concurrente, no sobreventa, autorizacion, compensacion, validacion, rutas internas y recuperacion persistente.',flush=True)
    print(out,flush=True)
if __name__=='__main__':main()

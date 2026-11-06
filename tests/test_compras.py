from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import engine

@pytest.fixture
def client():
    with TestClient(app) as client: yield client

def sesion(client):
    correo=f'{uuid4()}@example.test'
    r=client.post('/api/usuarios',json=dict(correo=correo,nombre='Prueba',password='password-pruebas-123'))
    assert r.status_code==201,r.text
    r=client.post('/api/sesiones',json=dict(correo=correo,password='password-pruebas-123'))
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def producto(stock=5):
    id='prueba-'+str(uuid4())
    with engine.begin() as c:
        c.execute(text('INSERT INTO productos VALUES (:id,:nombre,1234,:stock)'),dict(id=id,nombre='Producto de prueba',stock=stock))
    return id

def compra(client,auth,p,clave=None,cantidad=1):
    return client.post('/api/pedidos',headers={**auth,'Idempotency-Key':clave or str(uuid4())},
                       json={'items':[dict(producto_id=p,cantidad=cantidad)]})

def test_reintento_no_descuenta_dos_veces_y_rechaza_cambio_de_payload(client):
    auth=sesion(client); p=producto(); clave=str(uuid4())
    primero=compra(client,auth,p,clave,2); segundo=compra(client,auth,p,clave,2)
    assert primero.status_code==201 and segundo.status_code==200
    assert primero.json()==segundo.json()
    assert client.get('/api/productos/'+p).json()['stock']==3
    assert compra(client,auth,p,clave,1).status_code==409

def test_concurrencia_no_sobrevende(client):
    auth=sesion(client); p=producto(3)
    with ThreadPoolExecutor(max_workers=5) as pool:
        respuestas=list(pool.map(lambda _:compra(client,auth,p).status_code,range(10)))
    assert respuestas.count(201)==3,respuestas
    assert respuestas.count(409)==7,respuestas
    assert client.get('/api/productos/'+p).json()['stock']==0

def test_misma_llave_concurrente_crea_un_solo_pedido(client):
    auth=sesion(client); p=producto(5); clave=str(uuid4())
    with ThreadPoolExecutor(max_workers=5) as pool:
        respuestas=list(pool.map(lambda _:compra(client,auth,p,clave),range(5)))
    assert sorted(r.status_code for r in respuestas)==[200,200,200,200,201]
    assert len({r.json()['id'] for r in respuestas})==1
    assert client.get('/api/productos/'+p).json()['stock']==4

def test_pedido_ajeno_y_sin_sesion(client):
    auth=sesion(client); otro=sesion(client); p=producto()
    id=compra(client,auth,p).json()['id']
    assert client.get('/api/pedidos/'+id,headers=auth).status_code==200
    assert client.get('/api/pedidos/'+id,headers=otro).status_code==404
    assert client.get('/api/pedidos/'+id).status_code==401

def test_compra_multilinea_fallida_no_reserva_stock_ni_crea_pedido(client):
    auth=sesion(client); a=producto(5); b=producto(0)
    r=client.post('/api/pedidos',headers={**auth,'Idempotency-Key':str(uuid4())},
        json={'items':[dict(producto_id=a,cantidad=2),dict(producto_id=b,cantidad=1)]})
    assert r.status_code==409
    assert client.get('/api/productos/'+a).json()['stock']==5
    assert client.get('/api/pedidos',headers=auth).json()==[]

def test_precio_del_pedido_permanece_y_password_no_se_expone(client):
    auth=sesion(client); p=producto(); pedido=compra(client,auth,p).json()
    with engine.begin() as c: c.execute(text('UPDATE productos SET precio_centavos=9999 WHERE id=:id'),dict(id=p))
    previo=client.get('/api/pedidos/'+pedido['id'],headers=auth).json()
    assert previo['items'][0]['precio_centavos']==1234
    assert 'password' not in client.get('/api/usuarios/me',headers=auth).text

def test_cantidades_invalidas_y_llave_ausente(client):
    auth=sesion(client); p=producto()
    assert compra(client,auth,p,cantidad=0).status_code==422
    assert compra(client,auth,p,cantidad=True).status_code==422
    assert client.post('/api/pedidos',headers=auth,json={'items':[dict(producto_id=p,cantidad=1)]}).status_code==422

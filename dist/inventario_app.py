import os
from uuid import UUID
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI,Depends,HTTPException
from pydantic import BaseModel,Field
from pymongo import MongoClient,ReturnDocument
from .comun import interno,instrumentar

mongo=MongoClient(os.environ['MONGO_URI'],serverSelectionTimeoutMS=2000,
                  connectTimeoutMS=2000,socketTimeoutMS=3000)
productos=mongo.inventario.productos

@asynccontextmanager
async def lifespan(app):
    mongo.admin.command('ping')
    for id,nombre,precio,stock in [('teclado','Teclado mecánico',65000,20),('mouse','Mouse inalámbrico',35000,30),('monitor','Monitor 24 pulgadas',320000,10)]:
        productos.update_one({'_id':id},{'$setOnInsert':dict(nombre=nombre,precio_centavos=precio,stock=stock,reservas={})},upsert=True)
    yield;mongo.close()

app=FastAPI(title='Docker Rangers · Inventario',lifespan=lifespan)
instrumentar(app)
class Reserva(BaseModel):
    pedido_id:UUID
    cantidad:int=Field(strict=True,gt=0,le=100)

def publico(p):
    return dict(id=p['_id'],nombre=p['nombre'],precio_centavos=p['precio_centavos'],stock=p['stock'])
def buscar(id):
    p=productos.find_one({'_id':id})
    if p is None:raise HTTPException(404,'Producto no encontrado')
    return p
@app.get('/api/productos')
def catalogo():return [publico(p) for p in productos.find().sort('_id',1)]
@app.get('/api/productos/{id}')
def producto(id:str):return publico(buscar(id))
@app.get('/health')
def health():mongo.admin.command('ping');return {'status':'ok','servicio':'inventario'}

def respuesta(p,reserva):
    return dict(producto_id=p['_id'],**reserva)
def validar_previa(p,key,cantidad):
    previa=p.get('reservas',{}).get(key)
    if previa and previa['cantidad']!=cantidad:raise HTTPException(409,'Reserva usada con otra cantidad')
    if previa and previa['estado']=='LIBERADA':raise HTTPException(409,'Reserva ya liberada')
    return previa

@app.post('/interno/productos/{id}/reservas',dependencies=[Depends(interno)])
def reservar(id:str,solicitud:Reserva):
    key=str(solicitud.pedido_id);campo='reservas.'+key
    p=buscar(id);previa=validar_previa(p,key,solicitud.cantidad)
    if previa:return respuesta(p,previa)
    # Stock y marca idempotente se escriben ATOMICAMENTE en el mismo documento.
    actualizado=productos.find_one_and_update(
        {'_id':id,'stock':{'$gte':solicitud.cantidad},campo:{'$exists':False}},
        [{'$set':{'stock':{'$subtract':['$stock',solicitud.cantidad]},campo:{
            'cantidad':solicitud.cantidad,'estado':'RESERVADA','precio_centavos':'$precio_centavos','nombre':'$nombre'}}}],
        return_document=ReturnDocument.AFTER)
    if actualizado:return respuesta(actualizado,actualizado['reservas'][key])
    p=buscar(id);previa=validar_previa(p,key,solicitud.cantidad)
    if previa:return respuesta(p,previa)
    raise HTTPException(409,'Stock insuficiente: '+id)

@app.post('/interno/productos/{id}/reservas/{pedido_id}/{accion}',dependencies=[Depends(interno)])
def cambiar_reserva(id:str,pedido_id:UUID,accion:str):
    if accion not in ('confirmar','liberar'):raise HTTPException(404,'Acción desconocida')
    key=str(pedido_id);campo='reservas.'+key;p=buscar(id);r=p.get('reservas',{}).get(key)
    if not r:raise HTTPException(404,'Reserva no encontrada')
    final='CONFIRMADA' if accion=='confirmar' else 'LIBERADA'
    if r['estado']==final:return respuesta(p,r)
    if r['estado']!='RESERVADA':raise HTTPException(409,'Estado de reserva incompatible')
    cambio={'$set':{campo+'.estado':final}}
    if accion=='liberar':cambio['$inc']={'stock':r['cantidad']}
    updated=productos.find_one_and_update({'_id':id,campo+'.estado':'RESERVADA'},cambio,return_document=ReturnDocument.AFTER)
    if not updated:
        p=buscar(id);r=p['reservas'][key]
        if r['estado']!=final:raise HTTPException(409,'Conflicto concurrente de reserva')
        return respuesta(p,r)
    return respuesta(updated,updated['reservas'][key])

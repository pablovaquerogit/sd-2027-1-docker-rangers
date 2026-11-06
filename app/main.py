from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from .db import engine, initialize
from . import usuarios, inventario, pedidos

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield
    engine.dispose()

app=FastAPI(title='Docker Rangers · Tienda',version='0.1.0',lifespan=lifespan)
for modulo in (usuarios,inventario,pedidos): app.include_router(modulo.router)

@app.get('/health',tags=['Estado'])
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    return {'status':'ok','version':'01-monolito'}

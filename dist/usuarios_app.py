from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from .sql import engine,initialize
from .usuarios import router
from .comun import instrumentar
@asynccontextmanager
async def lifespan(app):
    initialize();yield;engine.dispose()
app=FastAPI(title='Docker Rangers · Usuarios',lifespan=lifespan)
app.include_router(router);instrumentar(app)
@app.get('/health')
def health():
    with engine.connect() as c:c.execute(text('SELECT 1'))
    return {'status':'ok','servicio':'usuarios'}

import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS usuarios (
        id UUID PRIMARY KEY, correo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
        password_hash TEXT NOT NULL, creado_en TIMESTAMPTZ NOT NULL DEFAULT now())''',
    '''CREATE TABLE IF NOT EXISTS sesiones (
        token_hash TEXT PRIMARY KEY, usuario_id UUID NOT NULL REFERENCES usuarios(id),
        expira_en TIMESTAMPTZ NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS productos (
        id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
        precio_centavos BIGINT NOT NULL CHECK(precio_centavos > 0),
        stock INTEGER NOT NULL CHECK(stock >= 0))''',
    '''CREATE TABLE IF NOT EXISTS pedidos (
        id UUID PRIMARY KEY, usuario_id UUID NOT NULL REFERENCES usuarios(id),
        clave TEXT NOT NULL, solicitud_hash TEXT NOT NULL,
        total_centavos BIGINT NOT NULL CHECK(total_centavos > 0),
        estado TEXT NOT NULL CHECK(estado='CONFIRMADO'),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(usuario_id, clave))''',
    '''CREATE TABLE IF NOT EXISTS detalles_pedido (
        pedido_id UUID NOT NULL REFERENCES pedidos(id), producto_id TEXT NOT NULL REFERENCES productos(id),
        nombre TEXT NOT NULL, cantidad INTEGER NOT NULL CHECK(cantidad > 0),
        precio_centavos BIGINT NOT NULL CHECK(precio_centavos > 0),
        PRIMARY KEY(pedido_id, producto_id))'''
]

def initialize():
    with engine.begin() as c:
        for statement in SCHEMA:
            c.execute(text(statement))
        c.execute(text('''INSERT INTO productos(id,nombre,precio_centavos,stock) VALUES
            ('teclado','Teclado mecánico',65000,20),('mouse','Mouse inalámbrico',35000,30),
            ('monitor','Monitor 24 pulgadas',320000,10) ON CONFLICT(id) DO NOTHING'''))

import os
from sqlalchemy import create_engine,text
engine=create_engine(os.environ['DATABASE_URL'],pool_pre_ping=True)
def initialize():
    role=os.environ['ROLE']
    if role=='usuarios':
        statements=[
            '''CREATE TABLE IF NOT EXISTS usuarios(id UUID PRIMARY KEY, correo TEXT NOT NULL UNIQUE,
               nombre TEXT NOT NULL,password_hash TEXT NOT NULL,creado_en TIMESTAMPTZ NOT NULL DEFAULT now())''',
            '''CREATE TABLE IF NOT EXISTS sesiones(token_hash TEXT PRIMARY KEY,
               usuario_id UUID NOT NULL REFERENCES usuarios(id),expira_en TIMESTAMPTZ NOT NULL)''']
    elif role=='pedidos':
        statements=[
            '''CREATE TABLE IF NOT EXISTS pedidos(id UUID PRIMARY KEY,usuario_id UUID NOT NULL,
               clave TEXT NOT NULL,solicitud_hash TEXT NOT NULL,items JSONB NOT NULL,
               total_centavos BIGINT,estado TEXT NOT NULL CHECK(estado IN
               ('PENDIENTE','COMPENSANDO','CONFIRMADO','RECHAZADO','REVISION_PENDIENTE')),
               motivo TEXT,intentos INT NOT NULL DEFAULT 0,proximo TIMESTAMPTZ NOT NULL DEFAULT now(),
               creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
               historial JSONB NOT NULL DEFAULT '[]',trace_id TEXT NOT NULL,UNIQUE(usuario_id,clave))''',
            '''CREATE INDEX IF NOT EXISTS pendientes ON pedidos(proximo) WHERE estado IN ('PENDIENTE','COMPENSANDO')''']
    else:raise RuntimeError('Rol SQL desconocido')
    with engine.begin() as c:
        for statement in statements:c.execute(text(statement))

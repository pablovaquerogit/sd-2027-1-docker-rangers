import hashlib, hmac, secrets
from uuid import uuid4
from typing import Annotated
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from .sql import engine

router = APIRouter(prefix='/api', tags=['Usuarios'])
bearer = HTTPBearer(auto_error=False)

class Registro(BaseModel):
    correo: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    nombre: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)

class Login(BaseModel):
    correo: str = Field(max_length=254)
    password: str = Field(max_length=128)

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 210000).hex()
    return salt + ':' + digest

def usuario_actual(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if auth is None:
        raise HTTPException(401, 'Se requiere sesión', headers={'WWW-Authenticate':'Bearer'})
    token_hash = hashlib.sha256(auth.credentials.encode()).hexdigest()
    with engine.connect() as c:
        usuario = c.execute(text('''SELECT u.id,u.correo,u.nombre FROM sesiones s JOIN usuarios u
            ON u.id=s.usuario_id WHERE s.token_hash=:hash AND s.expira_en>now()'''), {'hash':token_hash}).mappings().first()
    if usuario is None:
        raise HTTPException(401, 'Sesión inválida o vencida', headers={'WWW-Authenticate':'Bearer'})
    return dict(usuario)

@router.post('/usuarios', status_code=201)
def registrar(registro: Registro):
    correo = registro.correo.strip().lower()
    nombre = registro.nombre.strip()
    if not nombre: raise HTTPException(422, 'El nombre no puede estar vacío')
    usuario = dict(id=uuid4(), correo=correo, nombre=nombre)
    try:
        with engine.begin() as c:
            c.execute(text('INSERT INTO usuarios(id,correo,nombre,password_hash) VALUES (:id,:correo,:nombre,:password)'),
                      {**usuario,'password':password_hash(registro.password)})
    except IntegrityError:
        raise HTTPException(409, 'El correo ya está registrado')
    return usuario

@router.post('/sesiones')
def iniciar_sesion(login: Login):
    with engine.begin() as c:
        usuario = c.execute(text('SELECT id,password_hash FROM usuarios WHERE correo=:correo'),
                            {'correo':login.correo.strip().lower()}).mappings().first()
        # Mismo trabajo criptográfico aunque el correo no exista.
        almacenado = usuario['password_hash'] if usuario else '00'*16 + ':' + '00'*32
        candidato = password_hash(login.password, almacenado.split(':')[0])
        if not hmac.compare_digest(candidato, almacenado) or usuario is None:
            raise HTTPException(401, 'Credenciales inválidas')
        token = secrets.token_urlsafe(32)
        expira = datetime.now(timezone.utc) + timedelta(hours=8)
        c.execute(text('INSERT INTO sesiones(token_hash,usuario_id,expira_en) VALUES (:token,:usuario,:expira)'),
                  dict(token=hashlib.sha256(token.encode()).hexdigest(), usuario=usuario['id'], expira=expira))
    return dict(access_token=token, token_type='bearer', expires_at=expira)

@router.get('/usuarios/me')
def perfil(usuario=Depends(usuario_actual)):
    return usuario

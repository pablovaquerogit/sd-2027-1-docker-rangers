import json,logging,os,time,re
from uuid import uuid4
from fastapi import Header,HTTPException
from typing import Annotated
logging.basicConfig(level=logging.INFO)
log=logging.getLogger('tienda')

def instrumentar(app):
    @app.middleware('http')
    async def medir(request,call_next):
        recibido=request.headers.get('X-Request-ID','')
        trace=recibido if re.fullmatch(r'[a-zA-Z0-9-]{1,80}',recibido) else str(uuid4())
        request.state.trace_id=trace
        inicio=time.monotonic()
        try:
            response=await call_next(request)
        except Exception:
            log.exception(json.dumps(dict(servicio=os.getenv('ROLE','inventario'),trace_id=trace,ruta=request.url.path)))
            raise
        response.headers['X-Request-ID']=trace
        response.headers['X-Instancia']=os.getenv('HOSTNAME','local')
        log.info(json.dumps(dict(servicio=os.getenv('ROLE','inventario'),trace_id=trace,metodo=request.method,
             ruta=request.url.path,status=response.status_code,duracion_ms=round((time.monotonic()-inicio)*1000,2))))
        return response

def interno(x_internal_key: Annotated[str|None,Header()]=None):
    import hmac
    if not x_internal_key or not hmac.compare_digest(x_internal_key,os.environ['INTERNAL_KEY']):
        raise HTTPException(401,'Credencial interna requerida')

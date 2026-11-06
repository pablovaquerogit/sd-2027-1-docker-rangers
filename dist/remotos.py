import os,time,threading
import httpx

class Rechazo(Exception):pass
class NoDisponible(Exception):pass

class Circuito:
    def __init__(self):
        self.lock=threading.Lock();self.estado='CLOSED';self.fallas=0;self.hasta=0;self.generacion=0
    def entrar(self):
        with self.lock:
            if self.estado=='HALF_OPEN':raise NoDisponible('Prueba de recuperación en curso')
            if self.estado=='OPEN':
                if time.monotonic()<self.hasta:raise NoDisponible('Circuito abierto')
                self.estado='HALF_OPEN'
            return self.generacion
    def resultado(self,g,exito):
        with self.lock:
            if g!=self.generacion:return
            if exito:
                if self.estado=='HALF_OPEN':self.generacion+=1
                self.estado='CLOSED';self.fallas=0
            else:
                self.fallas+=1
                if self.estado=='HALF_OPEN' or self.fallas>=3:
                    self.estado='OPEN';self.hasta=time.monotonic()+10;self.generacion+=1
    def foto(self):
        with self.lock:return dict(estado=self.estado,fallas=self.fallas)

circuito=Circuito()
def inventario(path,body,trace):
    g=circuito.entrar()
    try:
        r=httpx.post(os.environ['INVENTARIO_URL']+path,json=body,timeout=httpx.Timeout(3,connect=1),
            headers={'X-Internal-Key':os.environ['INTERNAL_KEY'],'X-Request-ID':trace})
    except httpx.HTTPError as e:
        circuito.resultado(g,False);raise NoDisponible('Inventario no respondió') from e
    if r.status_code>=500 or r.status_code==401:
        circuito.resultado(g,False);raise NoDisponible('Inventario temporalmente no disponible')
    circuito.resultado(g,True)
    if r.status_code in (404,409,422):raise Rechazo(r.json().get('detail','Reserva rechazada'))
    if r.status_code!=200:raise NoDisponible('Respuesta inesperada de inventario')
    return r.json()

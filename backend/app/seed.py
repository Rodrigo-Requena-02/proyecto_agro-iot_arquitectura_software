"""Datos de demostración (idempotente). Usuarios:
   agronomo@agro.cl      / Agro2026!   -> rol AGRONOMO (ve todos los sectores)
   jefe.a@agro.cl        / Terreno2026! -> rol JEFE_TERRENO (solo Sector A)
   jefe.b@agro.cl        / Terreno2026! -> rol JEFE_TERRENO (solo Sector B)
   jefe.c@agro.cl        / Terreno2026! -> rol JEFE_TERRENO (solo Sector C)
"""
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Rol, Sector, Usuario
from app.repositories.sqlalchemy_repos import SqlSectorRepository, SqlUsuarioRepository


def seed(db: Session) -> None:
    sectores, usuarios = SqlSectorRepository(db), SqlUsuarioRepository(db)
    if sectores.listar():
        return
    a = sectores.guardar(Sector(nombre="Sector A - Invernadero", tipo="invernadero"))
    b = sectores.guardar(Sector(nombre="Sector B - Hidropónico", tipo="hidroponico"))
    c = sectores.guardar(Sector(nombre="Sector C - Frutales", tipo="frutal"))
    usuarios.guardar(Usuario(email="agronomo@agro.cl", nombre="Ana Agrónoma", rol=Rol.AGRONOMO,
                             password_hash=hash_password("Agro2026!")))
    usuarios.guardar(Usuario(email="jefe.a@agro.cl", nombre="Juan Jefe (Sector A)", rol=Rol.JEFE_TERRENO,
                             sector_id=a.id, password_hash=hash_password("Terreno2026!")))
    usuarios.guardar(Usuario(email="jefe.b@agro.cl", nombre="Berta Jefa (Sector B)", rol=Rol.JEFE_TERRENO,
                             sector_id=b.id, password_hash=hash_password("Terreno2026!")))
    usuarios.guardar(Usuario(email="jefe.c@agro.cl", nombre="Carlos Jefe (Sector C)", rol=Rol.JEFE_TERRENO,
                             sector_id=c.id, password_hash=hash_password("Terreno2026!")))

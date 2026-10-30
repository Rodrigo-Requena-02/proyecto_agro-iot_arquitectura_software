from fastapi import APIRouter, Depends

from app.models import Usuario
from app.routers.deps import get_auth_service, get_current_user
from app.schemas import LoginIn, TokenOut, UsuarioOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, auth: AuthService = Depends(get_auth_service)):
    usuario, token, expira_en = auth.login(datos.email, datos.password)
    return TokenOut(access_token=token, expires_in=expira_en, usuario=UsuarioOut.model_validate(usuario))


@router.get("/me", response_model=UsuarioOut)
def me(usuario: Usuario = Depends(get_current_user)):
    return usuario

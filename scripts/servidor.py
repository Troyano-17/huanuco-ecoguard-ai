"""Servidor CPU para Render. Falla al arrancar si no hay un modelo verificado."""
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs


def create_server():
    import gradio as gr
    from app_gradio import build_app
    from auth_pages import auth_page
    from auth_store import (
        SESSION_COOKIE,
        SESSION_HOURS,
        AuthError,
        AuthStore,
        DuplicateEmail,
        InvalidCredentials,
        InvalidRegistration,
        LoginBlocked,
    )
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from mongo_store import AnalysisStore, StorageError
    weights = os.environ.get('MODEL_PATH', 'models/best.onnx')
    logging.getLogger('ecoguard').info('Arranque CPU: %s', Path(weights).name)
    blocks, _ = build_app(weights)
    server = FastAPI(title='HUÁNUCO ECOGUARD AI', docs_url=None, redoc_url=None,
                     openapi_url=None)
    health_store = AnalysisStore()
    auth_store = AuthStore()

    def current_user(request):
        cached = getattr(request.state, 'ecoguard_user', None)
        if cached:
            return cached['_id']
        user = auth_store.resolve_session(request.cookies.get(SESSION_COOKIE))
        return user['_id'] if user else None

    def is_https(request):
        forwarded = request.headers.get('x-forwarded-proto', '').split(',')[0].strip()
        return forwarded == 'https' or request.url.scheme == 'https'

    def same_origin(request):
        source = request.headers.get('origin') or request.headers.get('referer')
        if not source:
            return True
        from urllib.parse import urlsplit
        return urlsplit(source).netloc == request.headers.get('host')

    async def fields(request):
        body = await request.body()
        if len(body) > 8192:
            raise ValueError
        return {key: values[0] for key, values in parse_qs(
            body.decode('utf-8'), keep_blank_values=True).items()}

    class PrivateRouteMiddleware:
        """Puerta ASGI previa a Gradio; no consume ni reconstruye cuerpos POST."""
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http':
                return await self.app(scope, receive, send)
            request = Request(scope, receive=receive)
            path = scope.get('path', '')
            public = path in {'/healthz', '/readyz', '/login', '/register'}
            if not public:
                user = auth_store.resolve_session(request.cookies.get(SESSION_COOKIE))
                scope.setdefault('state', {})['ecoguard_user'] = user
                if not user and path != '/logout':
                    accepts_html = 'text/html' in request.headers.get('accept', '')
                    response = (RedirectResponse('/login', status_code=303)
                                if request.method == 'GET' and accepts_html else
                                JSONResponse({'detail': 'Debes iniciar sesión.'}, status_code=401))
                    return await response(scope, receive, send)

            async def secure_send(message):
                if message['type'] == 'http.response.start':
                    headers = list(message.get('headers', []))
                    headers.extend([(b'x-content-type-options', b'nosniff'),
                                    (b'x-frame-options', b'DENY'),
                                    (b'referrer-policy', b'same-origin')])
                    if path in {'/login', '/register'}:
                        headers.append((b'cache-control', b'no-store'))
                    message['headers'] = headers
                await send(message)
            return await self.app(scope, receive, secure_send)

    server.add_middleware(PrivateRouteMiddleware)

    @server.get('/login', response_class=HTMLResponse)
    def login_page(request: Request, created: int = 0, ended: int = 0):
        if current_user(request):
            return RedirectResponse('/', status_code=303)
        message = 'Tu cuenta se creó correctamente.' if created else ('Tu sesión ha finalizado.' if ended else '')
        return HTMLResponse(auth_page('login', message, success=bool(message)))

    @server.post('/login', response_class=HTMLResponse)
    async def login(request: Request):
        if not same_origin(request):
            return HTMLResponse(auth_page('login', 'No pudimos procesar la solicitud.'), status_code=403)
        try:
            data = await fields(request)
            user = auth_store.authenticate(data.get('email', ''), data.get('password', ''))
            token = auth_store.create_session(user['_id'])
        except LoginBlocked as exc:
            return HTMLResponse(auth_page('login', str(exc)), status_code=429)
        except (InvalidCredentials, ValueError):
            return HTMLResponse(auth_page('login', 'No pudimos iniciar sesión. Revisa tus datos e inténtalo nuevamente.'), status_code=401)
        except AuthError:
            return HTMLResponse(auth_page('login', 'No pudimos iniciar sesión en este momento. Inténtalo más tarde.'), status_code=503)
        response = RedirectResponse('/', status_code=303)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600,
                            httponly=True, secure=is_https(request), samesite='lax', path='/')
        return response

    @server.get('/register', response_class=HTMLResponse)
    def register_page(request: Request):
        if current_user(request):
            return RedirectResponse('/', status_code=303)
        return HTMLResponse(auth_page('register'))

    @server.post('/register', response_class=HTMLResponse)
    async def register(request: Request):
        if not same_origin(request):
            return HTMLResponse(auth_page('register', 'No pudimos procesar la solicitud.'), status_code=403)
        try:
            data = await fields(request)
            auth_store.register(data.get('name', ''), data.get('email', ''), data.get('password', ''))
        except DuplicateEmail as exc:
            return HTMLResponse(auth_page('register', str(exc)), status_code=409)
        except InvalidRegistration as exc:
            return HTMLResponse(auth_page('register', str(exc)), status_code=422)
        except AuthError:
            return HTMLResponse(auth_page('register',
                                'No pudimos crear tu cuenta en este momento. Inténtalo más tarde.'),
                                status_code=503)
        except ValueError:
            return HTMLResponse(auth_page('register', 'Revisa los datos e inténtalo nuevamente.'), status_code=422)
        return RedirectResponse('/login?created=1', status_code=303)

    @server.post('/logout')
    def logout(request: Request):
        if not same_origin(request):
            return JSONResponse({'detail': 'Solicitud no válida.'}, status_code=403)
        auth_store.revoke_session(request.cookies.get(SESSION_COOKIE))
        response = RedirectResponse('/login?ended=1', status_code=303)
        response.delete_cookie(SESSION_COOKIE, path='/', secure=is_https(request),
                               httponly=True, samesite='lax')
        return response

    @server.get('/healthz')
    def health():
        return {'estado': 'activo', 'modelo': 'cargado', 'motor': Path(weights).suffix.lstrip('.')}

    @server.get('/readyz')
    def ready():
        try:
            health_store.connect()
            auth_store.connect()
            return {'estado': 'listo', 'modelo': 'cargado', 'mongodb': 'conectado'}
        except (StorageError, AuthError):
            return JSONResponse(status_code=503, content={'estado': 'degradado', 'mongodb': 'no disponible'})

    return gr.mount_gradio_app(server, blocks, path='/', max_file_size='20mb',
                               auth_dependency=current_user, show_error=False,
                               blocked_paths=[str(Path.cwd())])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    import uvicorn
    uvicorn.run(create_server(), host='0.0.0.0', port=int(os.environ.get('PORT', '7860')), workers=1,
                access_log=False)

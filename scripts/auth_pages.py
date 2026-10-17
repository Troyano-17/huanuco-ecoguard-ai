"""HTML pequeño y accesible para acceso y registro."""
from html import escape

CSS = """
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#0b1412;color:#e5eeea}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:22px;
background:radial-gradient(circle at 80% 10%,#19432e 0,transparent 34%),#0b1412}
main{width:min(100%,460px)}.brand{color:#8ae8b5;font-size:.75rem;letter-spacing:.14em;font-weight:750}
.card{margin-top:18px;padding:clamp(24px,6vw,38px);background:#111f1a;border:1px solid #355441;border-radius:22px;
box-shadow:0 22px 70px #0007}h1{font-size:clamp(1.75rem,6vw,2.35rem);line-height:1.12;letter-spacing:-.035em;margin:0 0 13px;color:#f2f8f4}
.intro{color:#afc7b9;line-height:1.6;margin:0 0 25px}label{display:block;margin:17px 0 7px;color:#d8e8df;font-weight:650;font-size:.9rem}
input{width:100%;min-height:48px;padding:11px 13px;border-radius:10px;border:1px solid #486555;background:#0e1a15;color:#fff;font:inherit}
input:focus{outline:2px solid #8ae8b5;outline-offset:2px}button{width:100%;min-height:49px;margin-top:24px;border:0;border-radius:10px;
background:#72dfaa;color:#082017;font:inherit;font-weight:750;cursor:pointer}button:hover{background:#94ebbf}.switch{text-align:center;margin:22px 0 0;color:#afc7b9}
a{color:#91eab8;font-weight:650}.message{padding:12px 14px;border-radius:10px;line-height:1.5;margin:0 0 18px;background:#2c2018;border:1px solid #745238;color:#ffd9bd}
.message.ok{background:#153225;border-color:#356f50;color:#b9f2d0}.help{font-size:.8rem;color:#91aa9c;line-height:1.5;margin-top:8px}
@media(max-width:480px){body{padding:12px;align-items:start}.card{margin-top:10px;border-radius:16px}}
"""


def auth_page(mode="login", message="", success=False):
    register = mode == "register"
    title = "Crear cuenta" if register else "Bienvenido a Huánuco EcoGuard AI"
    intro = ("Regístrate para guardar tus análisis y consultar solo tus resultados."
             if register else "Ingresa a tu cuenta para analizar imágenes y consultar tus resultados.")
    fields = ('<label for="name">Nombre</label><input id="name" name="name" autocomplete="name" '
              'maxlength="80" required>' if register else "")
    fields += ('<label for="email">Correo electrónico</label><input id="email" name="email" '
               'type="email" autocomplete="email" maxlength="254" required>')
    fields += ('<label for="password">Contraseña</label><input id="password" name="password" '
               'type="password" autocomplete="new-password" minlength="10" maxlength="128" required>'
               if register else
               '<label for="password">Contraseña</label><input id="password" name="password" '
               'type="password" autocomplete="current-password" maxlength="128" required>')
    if register:
        fields += '<p class="help">Usa de 10 a 128 caracteres e incluye una letra y un número.</p>'
    notice = (f'<div class="message{" ok" if success else ""}" role="status">{escape(message)}</div>'
              if message else "")
    action, button = ("/register", "Crear cuenta") if register else ("/login", "Iniciar sesión")
    switch = ('¿Ya tienes una cuenta? <a href="/login">Iniciar sesión</a>' if register else
              '¿Aún no tienes una cuenta? <a href="/register">Crear cuenta</a>')
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style></head><body><main><div class="brand">HUÁNUCO · ECOGUARD AI</div>
<section class="card"><h1>{escape(title)}</h1><p class="intro">{escape(intro)}</p>{notice}
<form method="post" action="{action}">{fields}<button type="submit">{button}</button></form>
<p class="switch">{switch}</p></section></main></body></html>'''

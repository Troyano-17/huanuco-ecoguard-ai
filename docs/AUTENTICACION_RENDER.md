# Autenticación, MongoDB Atlas y Render

## Arquitectura implementada

FastAPI sirve `/login`, `/register`, `/logout`, `/healthz` y `/readyz`. Gradio permanece montado en `/` mediante la API `mount_gradio_app` de Gradio 5.49.1 con `auth_dependency`. Un middleware ASGI valida la sesión antes de permitir configuración, cola, predicción, cámara, archivos temporales, guardado, historial o estadísticas. Los callbacks reciben el identificador que Gradio toma de la sesión; ningún identificador enviado como dato por el navegador decide el propietario.

`usuarios` conserva UUID, nombre, correo normalizado, hash Argon2id, fecha de registro y estado. El índice `correo_unico` rechaza duplicados. `sesiones` conserva solamente un HMAC-SHA-256 del token aleatorio, usuario, creación, caducidad y revocación; sus índices permiten búsqueda única, consulta por usuario y eliminación TTL. `intentos_login` mantiene el bloqueo temporal y también caduca por TTL.

`analisis` conserva UUID, UUID propietario, fecha UTC, categoría aceptada, puntuaciones originales y versión del modelo. Sus índices son `analisis_unico` e `historial_por_usuario` sobre propietario y fecha descendente. No guarda fotografías. La capa de persistencia vuelve a aplicar `accepted_label`, por lo que una puntuación inferior al 60 % no puede confirmarse aunque se invoque el guardado directamente.

Las cookies son HttpOnly, SameSite=Lax, limitadas a `/`, duran 12 horas y llevan Secure cuando FastAPI recibe HTTPS directamente o `X-Forwarded-Proto: https` de Render. Cerrar sesión revoca el documento antes de borrar la cookie. Las páginas de acceso no se almacenan en caché. Los mensajes no exponen excepciones, consultas, hashes ni URI.

## Variables de entorno

| Variable | Obligatoria | Uso |
|---|---:|---|
| `MONGODB_URI` | Sí | URI secreta de Atlas con usuario de mínimo privilegio. |
| `MONGODB_DB` | Sí | Base de datos; `ecoguard` en Render. |
| `SESSION_SECRET` | Sí | Al menos 32 caracteres aleatorios; Render la genera en `render.yaml`. |
| `MODEL_PATH` | Sí | `models/best.onnx`. |
| `SESSION_HOURS` | No | Caducidad; valor preparado: 12. |
| `MAX_LOGIN_ATTEMPTS` | No | Fallos antes del bloqueo; valor predeterminado: 5. |
| `LOGIN_WINDOW_MINUTES` | No | Ventana y bloqueo; valor predeterminado: 15. |
| `PORT` | En Render | Puerto entregado por la plataforma. |

## Configuración humana pendiente

1. En Atlas, crear un proyecto y clúster, un usuario con lectura/escritura únicamente sobre la base `ecoguard` y una contraseña larga distinta de `SESSION_SECRET`.
2. Autorizar en Atlas la salida de red de Render. Si el plan de Render no ofrece una IP fija, aplicar la regla de red que corresponda al plan y revisar el riesgo antes de publicar.
3. Copiar la URI de conexión a `MONGODB_URI` en el panel de Render. No escribirla en archivos ni commits.
4. Crear el servicio desde `render.yaml`. Confirmar que `SESSION_SECRET` aparece como valor generado y secreto, `MODEL_PATH=models/best.onnx`, un solo worker y despliegue automático desactivado.
5. Ejecutar un despliegue manual solo cuando se decida publicar. Después comprobar `/healthz`, `/readyz`, registro, acceso, cierre, fotografía, cámara HTTPS y aislamiento con dos cuentas reales.
6. Activar `ECOGUARD_ATLAS_REAL_TESTS=1`, `MODEL_PATH` y `ECOGUARD_SAMPLE` únicamente en un entorno de aceptación para ejecutar la prueba marcada de Atlas. Los tests con `mongomock` prueban contratos e aislamiento local, pero no certifican Atlas.

No se realizó despliegue, compra ni conexión real a Atlas durante esta entrega.

## Archivos de esta entrega

Se crearon `scripts/auth_store.py`, `scripts/auth_pages.py`, `tests/test_authentication.py`, `requirements-test.txt` y este documento. Se modificaron `scripts/servidor.py`, `scripts/app_gradio.py`, `scripts/mongo_store.py`, `scripts/ecoguard_ui.css`, `requirements-production.txt`, `render.yaml`, `.env.example` y `README.md`.

## Verificación del 16 de octubre de 2026

- Suite completa: 90 pruebas ejecutadas en 4,336 s; 85 aprobadas, 5 omitidas y 0 fallidas. Cuatro omisiones corresponden a la suite histórica que exige PyTorch y `best.pt`; una corresponde a la integración real con Atlas no configurada. Aparecieron avisos de cierre de event loop de Gradio y una deprecación interna de `mongomock`; no fueron fallos.
- Seguridad nueva: 13 pruebas aprobadas. Cubren registro, duplicado, Argon2id, contraseña incorrecta, límite de intentos, acceso, cierre, reutilización de sesión revocada, caducidad, MongoDB ausente, aislamiento entre dos usuarios, estadísticas, umbral, archivos protegidos y puerta de las operaciones de fotografía, cámara, guardado e historial.
- Revisión estática: Ruff aprobó todos los archivos creados o modificados de Python.
- Modelo: `scripts/verificar_modelo_render.py` aprobó integridad, procedencia, clases y equivalencia ONNX. Los SHA-256 de ONNX, manifiesto, `best.pt` y `last.pt` permanecen iguales a los valores verificados.
- HTTP local real: `/healthz` 200; `/login` 200; raíz sin sesión 303 hacia `/login`; `/config` sin sesión 401; predicción sin sesión 401; `/readyz` y registro sin MongoDB 503. El proceso se detuvo después de la prueba.
- Memoria al construir el servidor con modelo ONNX y autenticación: máximo RSS 219.680 KiB (aproximadamente 214,5 MiB), medido con `/usr/bin/time -v`. Es una medición local de arranque, no una medición de carga concurrente ni de Render.

La preparación de código y configuración está completa. Continúan pendientes la creación humana de Atlas, la carga de secretos en Render, la prueba de integración real con Atlas, la validación en teléfonos físicos y el despliegue, que se dejó desactivado como se solicitó.

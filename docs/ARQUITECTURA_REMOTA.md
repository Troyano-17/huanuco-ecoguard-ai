# Arquitectura remota persistente · 2026-10-16

## Auditoría del transporte

CLI instalada: 0.7.4. Se inspeccionaron `contents.py`, `commands/files.py`,
`commands/execution.py` y la ayuda de `drivemount`. `ContentsClient.upload` lee el
archivo entero, codifica base64 y realiza una petición PUT; `chunk: 1` no ofrece
un protocolo de reanudación. Un ZIP de 95 582 861 bytes implica aproximadamente
127 MB de base64 más JSON. `REQUEST_TIMEOUT=180` no resuelve cierres TLS.
No se modificaron paquetes instalados ni se desactivó SSL.

El adaptador tenía una caché vacía que ocultaba `laboratorio-t4`; ahora importa
la configuración original cuando es más reciente o la caché está vacía.
Se probaron `status` y el montaje oficial `drivemount`. Después de corregir la
caché ambos fallaron por DNS, antes de poder comprobar Drive. La prueba real
`prepare` agotó cuatro intentos controlados, sin subir datos ni iniciar GPU.
La CLI sigue siendo utilizable desde una terminal WSL con acceso de red.

SHA256 local del respaldo existente:

```text
f17a403815f2d184c668ebda60c9e963916bef296522d98e70b43721d3ceeca5
```

## Persistencia y transporte por fragmentos

Primero ejecutar el montaje oficial, con interacción humana si solicita OAuth:

```bash
export REQUEST_TIMEOUT=180
/home/troyano/proyectos/gpu-t4/.venv/bin/colab drivemount -s laboratorio-t4 /content/drive
```

El controlador verifica que `/content/drive` sea un montaje, que `MyDrive` exista
y que se pueda escribir y leer un archivo de prueba. No crea una carpeta vacía
para simular Drive. El montaje por sí solo no sube archivos locales.

La transferencia alternativa al PUT gigante utiliza 92 fragmentos de 1 MiB
(el último es menor). WSL calcula hashes y transmite bytes; no abre fotografías.
Cada fragmento se sube a staging en `/content`, se verifica, se copia a Drive,
se verifica otra vez y se publica mediante rename. Antes de cada reintento se
consulta el fragmento persistente y el staging. Una respuesta perdida después
de guardar no obliga a retransmitirlo. Al cambiar de máquina se reutilizan los
fragmentos confirmados en Drive.

La reconstrucción ocurre en Colab. Se comprueban todos los fragmentos y SHA256
del ZIP completo antes de publicar `manifest-transporte.json`. Un ZIP íntegro
ya presente en Drive permite omitir la transferencia, incluso si se subió por
otro mecanismo a la misma ruta. Se conservan los fragmentos verificados como
respaldo de recuperación; no se vuelve a convertir las 165 fotografías.

Rutas persistentes:

```text
MyDrive/HuanucoEcoGuard/
  datasets/<sha256>/ecoguard-validacion.zip
  datasets/<sha256>/manifest-transporte.json
  datasets/<sha256>/parts/*.part
  datasets/<sha256>/preparado.zip
  datasets/<sha256>/preparado.json
  datasets/<sha256>/arquitectura-validada.json
  pretrained/<release>/yolo11n-cls.pt
  pretrained/<release>/sha256.json
  runs/train100-<sha256>/config.json
  runs/train100-<sha256>/owner.json
  runs/train100-<sha256>/owner.guard/
  runs/train100-<sha256>/estado.json
  runs/train100-<sha256>/terminal.log
  runs/train100-<sha256>/checkpoints/<epoch>-<generation>/COMMITTED.json
  runs/train100-<sha256>/entrega.zip
  runs/train100-<sha256>/entrega.json
```

`preparado.zip` conserva la partición y los 151 PNG únicos para no repetir
agrupación/preparación entre máquinas. El respaldo original con los 165 PNG y
manifiesto siempre permanece disponible. Las copias en `/content` son cachés.

## Alternativa independiente del montaje: Drive API resumable

Si el montaje no es viable para transferir, `scripts/subir_respaldo_drive.py`
sube directamente desde WSL a Google Drive mediante su API oficial. No usa el
transporte de Colab CLI. Conserva el URI privado de la sesión en `.runtime`,
consulta el rango aceptado antes de continuar y después de un ACK perdido,
y verifica SHA256 del contenido remoto mediante lectura completa por streaming.
Las pruebas con servidor simulado cubren ACK TLS perdido, reanudación desde el
offset remoto, archivo ya completo, rango inválido y ausencia de progreso.
La autenticación y transferencia reales de esta alternativa aún no se probaron.

Requiere OAuth de usuario con alcance Drive y API Drive habilitada en su proyecto.
Si ya existen credenciales ADC con ese alcance, se reutilizan. En caso contrario,
con Google Cloud CLI y un cliente OAuth de escritorio propio:

```bash
gcloud auth application-default login --client-id-file=/ruta/cliente-oauth.json \
  --scopes=https://www.googleapis.com/auth/drive
```

No enviar tokens ni credenciales por chat. En Drive, crear la carpeta
`HuanucoEcoGuard/datasets/f17a403815f2d184c668ebda60c9e963916bef296522d98e70b43721d3ceeca5`
y reservar allí un archivo vacío que será reemplazado por el respaldo. Obtener
su file ID desde la URL de Drive, sin habilitar acceso público. El script utiliza
PATCH sobre ese ID para evitar crear archivos duplicados tras una respuesta
ambigua. Ejecutar:

```bash
/home/troyano/proyectos/gpu-t4/.venv/bin/python scripts/subir_respaldo_drive.py \
  --file-id ID_ARCHIVO_RESERVADO
```

Si se interrumpe, la siguiente ejecución consulta la sesión y continúa desde los
bytes confirmados. Si Drive informa que expiró, se detiene explícitamente:
consultar primero el archivo final y retirar únicamente su caché
`.runtime/drive-resumable-ID_ARCHIVO_RESERVADO.json` antes de abrir otra sesión
contra el mismo file ID. No se prometen sesiones de subida perpetuas.

Esta alternativa garantiza el procedimiento de transporte sin montaje. El
backend de entrenamiento implementado sigue requiriendo Drive montado en Colab;
una vez disponible, `prepare` detecta el ZIP íntegro y omite la subida. Si solo
falla OAuth en la CLI, se puede montar en el notebook oficial mediante
`from google.colab import drive; drive.mount('/content/drive')`. Si FUSE no está
disponible en absoluto, no se inicia entrenamiento con este backend.

Referencias oficiales: [protocolo de subida reanudable](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
y [ADC para servicios como Drive](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

## Autonomía, bloqueo y recuperación

`start` lanza un proceso desacoplado con stdin cerrado, sesión de proceso nueva
y stdout/stderr en Drive. Este proceso ejecuta las épocas, evaluación e inicio
de Gradio sin supervisión local. `status` solo consulta; `download` recibe la
entrega y comprueba su SHA256, las 2+100 épocas y los archivos necesarios.

Un `flock` local heredado por el trabajador bloquea lanzamientos concurrentes
en la misma máquina y también protege la instalación del código. Si START
pierde la respuesta, el cliente consulta estado y nunca repite automáticamente
ese lanzamiento. Un registro persistente de propietario identifica el boot ID.
No se roba por antigüedad. Si cambia la máquina, el usuario debe comprobar que
la anterior terminó y proporcionar el ID mostrado por `status`:

```bash
python3 scripts/entrenar_165_wsl.py run --recover-boot ID_ANTERIOR
```

Este paso evita interpretar una desconexión como muerte de la máquina. Drive
FUSE no es un servicio de bloqueo distribuido transaccional: la exclusión fuerte
con `flock` cubre una máquina; el registro persistente evita la toma automática
desde otra. Este flujo se opera con una única sesión `laboratorio-t4`; no debe
lanzarse simultáneamente desde varias máquinas Colab independientes. Para
orquestación concurrente entre varias máquinas se necesita un servicio externo
con adquisición condicional de leases. Si queda `owner.guard` sin `owner.json`,
se bloquea la ejecución y se requiere inspeccionar esa reclamación incompleta.

En cada época completada, antes de que Ultralytics quite el optimizador en la
evaluación final, se verifica y conserva el checkpoint reanudable. Se publica
una generación inmutable que incluye pesos, optimizador/EMA, scheduler, scaler,
RNG, configuración, métricas CSV, prueba técnica, versiones, run ID y SHA256 del
dataset. `COMMITTED.json` contiene los hashes de todos sus archivos y se escribe
al final. Un fallo a mitad de copia no publica la generación.

Al reiniciar se recorren generaciones comprometidas y se comprueban sus hashes.
Se restaura la última válida; si la más reciente está dañada se retrocede a la
anterior válida. Si ninguna generación de entrenamiento es recuperable, se
bloquea antes de reiniciar 100 épocas. La prueba de 2 épocas se conserva aparte.
Se rechazan cambios silenciosos de código, configuración, PyTorch o Ultralytics.
La recuperación de RNG no promete identidad bit a bit entre runtimes distintos.

Ultralytics restaura optimizador/EMA y contador con `resume=True`; el callback
adicional restaura scheduler/scaler/RNG guardados. Referencias oficiales:
[entrenamiento y resume](https://docs.ultralytics.com/modes/train/) y
[implementación del trainer](https://docs.ultralytics.com/reference/engine/trainer/).

## Red y límites

Todos los comandos reciben `REQUEST_TIMEOUT=180`; `exec` también usa 180 segundos.
El cliente termina una CLI colgada tras 210 segundos, puesto que la implementación
de subida instalada no pasa un timeout HTTP explícito. Los reintentos de lecturas
y operaciones idempotentes son limitados, con backoff y jitter, para DNS, TLS,
408, 429 y HTTP 5xx seleccionados. Errores permanentes no disparan reintentos.
Las copias de checkpoints también tienen reintentos de E/S limitados. Las trazas
HTTP de la CLI no se vuelcan a la terminal para evitar exponer tokens.

La prueba de lectura posterior en Drive demuestra funcionamiento a través del
montaje; no es una prueba independiente de durabilidad del servidor de Google.
Debe comprobarse recuperación real después de un cambio de runtime cuando la
conexión esté disponible. Los límites de Colab pueden terminar la máquina; no
se crean runtimes ni se eluden esos límites. Documentación:
[FAQ oficial](https://research.google.com/colaboratory/faq.html) y
[montaje de Drive](https://colab.research.google.com/notebooks/io.ipynb).

Gradio mantiene inferencia con `best.pt` entrenado y una prueba real de imagen
antes de publicar la URL. Si se pierde la máquina, se recuperan los pesos y se
abre otra URL. Su funcionamiento real sigue pendiente de completar entrenamiento.

## Validación y evidencias

Las pruebas locales usan bytes sintéticos y procesos CPU mínimos. Cubren:

- TLS con respuesta perdida después de persistir: consulta y omisión del envío.
- Fragmentos corruptos, reconstrucción multifragmento y pérdida del staging.
- Nueva caché de VM y recuperación desde la época 37, ignorando la 38 corrupta.
- Generaciones incompletas, dataset distinto y ausencia de checkpoints válidos.
- Reintentos limitados, errores permanentes, bloqueo heredado y doble START.
- START ambiguo: consulta de estado sin segundo lanzamiento.
- Evidencia exacta de 2 y 100 épocas y barreras contra procesamiento local.

`prepare` realiza adicionalmente una prueba remota sin GPU: primera llamada
escribe un checkpoint sintético en Drive y elimina la caché local; una segunda
llamada lo recupera en otra carpeta temporal y verifica la época 37. Solo después
publica el marcador de arquitectura validada. Esto simula pérdida de `/content`
y reconexión; no elimina realmente el runtime ni comprueba aún la reanudación
numérica de un modelo real, que se validará durante ejecución en T4.

Evidencias terminales:
[pruebas locales](evidencias/arquitectura-pruebas.txt) y
[intento real de persistencia bloqueado por DNS](evidencias/persistencia-intento.txt).

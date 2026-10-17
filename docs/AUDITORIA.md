# Auditoría inicial · 2026-10-15

Estado comprobado, sin métricas de entrenamiento inventadas:

| Elemento | Resultado |
| --- | --- |
| Proyecto local | Scripts previos, galeria.html y tres láminas en revision conservados. Sin AGENTS.md aplicable encontrado. |
| Control de versiones | `git status` informa que no es un repositorio Git; no se inicializó ni modificó `.git`. |
| Dataset local | `dataset/train`, `dataset/val`, `dataset/test` vacíos. No hay originales individuales de las 105 candidatas en el árbol local. |
| Modelos | Carpeta models vacía; no hay pesos entrenados locales. |
| Candidatas anteriores | Tres láminas con 35 entradas cada una, inspeccionadas visualmente. Predominan escaneos, portadas e imágenes irrelevantes. Ninguna aprobada; posibles fotos de agua requieren originales/procedencia/contexto. |
| CLI instalada | 0.7.4, ejecutable en `/home/troyano/proyectos/gpu-t4/.venv/bin/colab`. Sintaxis comprobada mediante ayuda y código instalado. |
| Sesión remota | `sessions`, `status -s laboratorio-t4` y `exec` intentados: fallan por resolución DNS de Colab / runtime. No se confirmó actividad ni disponibilidad actual de T4. |
| Descargas | Intento Commons falla por DNS; también falla resolución local de huggingface.co y raw.githubusercontent.com. Cero fotografías nuevas descargadas. |
| Instalaciones | Ninguna. Python local no tiene Pillow; entorno de CLI tiene requests. Procesamiento real con Pillow pendiente en Colab. |
| Recursos | No se inició entrenamiento ni se crearon/detuvieron sesiones. No se conoce el consumo por tiempo de una sesión previamente asignada. |

`scripts/colab_workspace.py` adapta exclusivamente los registros y la caché de
sesiones al directorio privado `.runtime`. Reutiliza autenticación existente,
desactiva comprobación automática de actualizaciones y no cambia HOME ni la
instalación. La caché puede contener secretos y está excluida de entregables.
No usar `--logtostderr` para registrar solicitudes autenticadas completas.

Comandos comprobados: `colab --help`, `colab version`, `colab sessions`,
`colab status --help`, `colab exec --help`, `colab upload --help`,
`colab download --help`. La ejecución directa requiere escribir el log en
`~/.config/colab-cli`; este entorno lo monta como solo lectura incluso con
`--logtostderr`, por eso se creó el adaptador local.

Las fuentes se investigaron mediante el navegador disponible, que tiene una
conexión distinta de los procesos de Ubuntu. Poder leer una página web no
implica poder descargar archivos en Ubuntu ni comunicarse con la sesión Colab.

Validación local: compilación Python y pruebas unitarias de barreras de datos,
esquema TACO, rutas y particiones. No se han probado descargas exitosas,
integridad de imágenes nuevas, entrenamiento, inferencia ni web.

Estado de fases: FASE 1 parcial (estado remoto sin confirmar); FASE 2 en curso
(fuentes investigadas y recolectores preparados, descarga bloqueada). FASES 3–8
pendientes. No solicitar aprobación de un dataset inexistente ni autorización
de entrenamiento todavía.

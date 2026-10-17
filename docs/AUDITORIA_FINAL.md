# Auditoría final — 16 de octubre de 2026

## Estado observado

Se inspeccionó `/home/troyano/proyectos/huanuco-ecoguard-ai`. La carpeta `.git`
no contiene un repositorio Git operativo en este entorno: `git status` devuelve
«not a git repository». No se afirma disponer de un diff Git verificable.
No se encontraron archivos AGENTS.md aplicables en el árbol inspeccionado.

Estructura previa: `scripts`, `tests`, `docs`, `dataset`, `data`, `imagenes`,
`revision`, `revision_ecoguard`, `models` y `.runtime`. `models` no contenía
archivos. El respaldo `ecoguard-validacion.zip` sí existe localmente. No había
`best.pt`, `last.pt` ni `entrega.zip` descargados dentro de `models`.

## Flujo previo identificado

- `scripts/entrenar_165_wsl.py`: preparación/transferencia, estado, descarga y
  control del trabajador remoto. Se conserva; no se invocaron acciones de entrenamiento.
- `scripts/entrenar_colab.py`: preparación agrupada, entrenamiento, evaluación,
  creación de entrega y lanzamiento de Gradio en Colab. Se conserva sin cambios.
- `scripts/control_entrenamiento_colab.py`: control y bloqueo del trabajador.
- `scripts/persistencia_colab.py`: checkpoints generacionales y verificación de Drive.
- `scripts/verificar_recuperacion.py` y `restaurar_dataset_colab.py`: recuperación.
- `scripts/app_gradio.py`: aplicación original; mejorada durante este cierre.
  Su versión original de 2611 bytes se recuperó del payload de despliegue del
  historial y se conserva en `entrega/evidencias/app_gradio_original.py`.

## Evidencia original recuperada

Se extrajeron únicamente salidas stdout pertinentes de
`.runtime/history/laboratorio-t4.jsonl`, sin copiar la caché de sesiones,
credenciales ni los comandos del historial al paquete.

`entrega/evidencias/colab-final-original.txt` conserva la salida original con:
100 épocas completas, GPU Tesla T4, Ultralytics 8.4.178, validación 0.957,
105/23/23 fotografías, evaluación test 21/23 y fase completo con entrega true.
También conserva una prueba real de la aplicación ANTERIOR. Esa prueba no
valida la interfaz mejorada durante este cierre.

Los JSON/CSV con sufijo «recuperadas_historial» y «desde_historial» son extracciones
de esa salida, no nuevos resultados ni sustitutos de los originales pendientes.
La matriz conserva agua, aire, suelo y los errores agua → suelo (2 fotografías).
El estado guardado en `estado_reportado_colab.json` es histórico, no una consulta
del estado actual de la sesión. Su URL temporal no se considera vigente.

## Integridad

SHA256 comprobados localmente:

- `ecoguard-validacion.zip`:
  `f17a403815f2d184c668ebda60c9e963916bef296522d98e70b43721d3ceeca5`.
- `.runtime/imagenes-165-candidatas.tar`:
  `2afa249d42c9ffe95347070f7a2a153d2a195843eed0e9e9c42a0ccbd892385b`.
- Aplicación original conservada:
  `5c4fcdc75e7423f2666e3a14342c8847cabb38fa561ebab95f3d82a5cb1613dd`.

SHA256 de entrega original REPORTADO por Colab, todavía no comprobado sobre
una copia local porque no se pudo descargar:
`ac10f88a010ef3fd0a7480cd984482496c77aa486e2548ff740c6da2fbf6f284`.

No se cargaron, modificaron ni reemplazaron checkpoints. Se verificó el respaldo
como bytes; no se procesó masivamente ninguna imagen en Linux.

## Bloqueo real

El CLI instalado puede mostrar su ayuda, pero al ejecutar una consulta remota
solicita «Enter the authorization code» y aborta sin interacción. El bloqueo
observado es autenticación Google no disponible para este proceso. No se atribuye
a DNS sin evidencia. Se intentaron las acciones finales `recuperar`, `app` y
`pruebas-colab`; ninguna pudo superar este bloqueo.

Faltan localmente los checkpoints, CSV de 100 épocas, gráficas originales,
configuración, versiones, particiones y predicciones originales. No se
fabricaron estos archivos. La entrega enumera las ausencias en `ESTADO_ENTREGA.json`.

Origen persistente esperado, confirmado por el estado histórico:
`/content/drive/MyDrive/HuanucoEcoGuard/runs/train100-f17a403815f2d184c668ebda60c9e963916bef296522d98e70b43721d3ceeca5/entrega.zip`.
Los pesos están dentro de ese ZIP bajo `train100/weights/`.

## Cambios y validación

Se añadió una entrada `ecoguard.py` sin acciones de entrenamiento, inferencia
real con validación del orden de clases, interfaz española, recuperación
conservadora, manifiesto SHA256, notebook, documentación académica y pruebas.
Los scripts de entrenamiento y persistencia permanecen intactos.

La suite local ejecutó 49 pruebas: 45 correctas y 4 omitidas por requerir Colab.
La compilación Python y de las celdas del notebook fue correcta. Se descomprimió
el paquete en /tmp y se comprobaron estado, pruebas, guion, evidencias e
integridad después de ejecutarlo, todos correctamente.

La suite local se ejecutó con biblioteca estándar; las pruebas de contratos usan
dobles explícitos. Las cuatro pruebas de integración real se omiten localmente
por diseño y deben ejecutarse en Colab. Compilar los módulos y las celdas del
notebook comprueba sintaxis; no prueba funcionamiento remoto.

Quedan pendientes la verificación original de las 100 filas de entrenamiento,
la inspección de sus curvas, carga real del modelo con la aplicación mejorada,
pruebas HTTP/API remotas y revisión visual en escritorio/teléfono. El paquete
no se declara completamente demostrado antes de superar esos pasos.

## Comandos de cierre desde WSL autenticado

```bash
cd /home/troyano/proyectos/huanuco-ecoguard-ai
export REQUEST_TIMEOUT=180
/home/troyano/proyectos/gpu-t4/.venv/bin/colab drivemount -s laboratorio-t4 /content/drive
python3 ecoguard.py recuperar
python3 ecoguard.py verificar
python3 ecoguard.py pruebas-colab
python3 ecoguard.py app
python3 ecoguard.py empaquetar
```

Si falta autenticación, completa el flujo Google del CLI desde esa terminal.
El notebook ofrece otra vía mediante la cuenta Google del navegador y restaura
la entrega desde Drive sin necesitar la caché CLI. No hay despliegue permanente.

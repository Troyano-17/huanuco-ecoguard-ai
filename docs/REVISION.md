# Revisión semántica y aprobación

Objetivo: 50 fotografías originales por clase (150). Mínimo académico: 50 en
total; selección equilibrada con diferencia máxima de una imagen entre clases.
Una descarga y una caja de detección no constituyen validación semántica.

1. Ejecutar `audit` para generar `review/gallery.html`, láminas y `audit.json`.
2. Abrir cada original y su página de fuente/licencia; no decidir solo por miniatura.
3. Editar `manifest.csv`: `estado=aprobada` o `rechazada`, `revisor`, fecha ISO,
   `evidencia` concreta de lo observado y, para aprobadas, ubicación real y
   `grupo_escena`. Respaldar el CSV antes de editar. No cambiar hashes para ocultar cambios.
4. Agua: basura reconocible dentro de ríos/quebradas; agua turbia sola no basta.
   Suelo: residuos reconocibles sobre suelo/vegetación en contexto natural/rural.
   Aire: humo visible y residuos reconocibles quemándose; excluir incendios de
   bosques, tala, actividad minera, niebla y escenas ambiguas o multiclase.
5. Rechazar páginas, capturas, dibujos, imágenes IA, duplicados exactos y fotos
   ajenas al alcance. Marcar lo incierto como `pendiente`; esto bloqueará build.
6. Agrupar la misma escena, ráfaga, fotogramas del mismo video/sitio y versiones
   recortadas aunque el hash no las detecte. No aumentar el conteo de originales
   con aumentos, recortes ni múltiples fotogramas casi idénticos. Si se requiere
   fotografía de cámara exclusivamente, rechazar fotogramas de video.
7. Revisar pares perceptuales (dHash <=6). El método es una alerta, no prueba de
   identidad: también puede omitir recortes. La revisión de escenas es obligatoria.
8. Volver a ejecutar audit. Con el manifiesto cerrado, obtener su SHA256 y pedir
   aprobación del dataset al usuario, entregando galería, cantidades, procedencias,
   licencias, ubicaciones y distribución por escenas. No crear una aprobación por él.
9. Registrar la aprobación explícita en un JSON:

```json
{"approved": true, "reviewer": "NOMBRE", "date": "FECHA_ISO", "manifest_sha256": "HASH_REAL"}
```

Ejecutar `build --approval approval.json` solo después de esa aprobación. Genera
`dataset/train`, `dataset/val`, `dataset/test` con objetivo 70/15/15, semilla 42.
Agrupa vecinos perceptuales por componentes transitivos y escenas revisadas.
Exige al menos dos fotos de cada clase en cada partición y limita desequilibrios;
puede rechazar un conjunto con pocas escenas independientes aunque tenga 150 fotos.
Los originales siguen en `candidates`; nunca se borran ni se sobreescribe un dataset.

La aprobación del dataset no autoriza las 100 épocas. Después corresponde una
prueba corta en T4 y una autorización separada para el entrenamiento final.

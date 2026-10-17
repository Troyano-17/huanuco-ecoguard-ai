# Fuentes investigadas (15 de octubre de 2026)

Estas fuentes son candidatas, no un dataset aprobado. Ninguna acredita fotografías
de Huánuco. Registrar ubicación real y no presentar datos internacionales como locales.
Para acreditar generalización regional harán falta fotografías de campo de Huánuco
con autorización de reutilización y evaluación independiente.

| Fuente | Utilidad y decisión | Licencia / atribución |
| --- | --- | --- |
| [TACO](https://github.com/pedropro/TACO) | Residuos en contexto; buscar fondos de vegetación/agua. Sus etiquetas de objetos no son nuestras tres clases. | MIT del software no demuestra licencia de cada foto de Flickr. Consultar autor y licencia individual antes de admitirla. Anotaciones sin licencia: revisión obligatoria. |
| [FloatWaste](https://huggingface.co/datasets/OliviaWuYJ/sc-floatwaste) | Fuente especializada de basura flotante. Priorizar Indonesia y evitar imágenes de agua limpia. Hay fotogramas: agrupar secuencias por escena antes de dividir. | La ficha declara CC BY 4.0 y atribución al dataset. Autor bibliográfico provisional Yujiao Wu; la propia ficha contiene autores/año pendientes. Conservar README, LICENSE y revisión del repositorio. |
| [Roboflow River-Pollution-Master](https://universe.roboflow.com/lumsworkspace/river-pollution-master) | Alternativa especializada de agua. Descarga según mecanismo oficial y condiciones de Universe; sin credenciales ni exportación comprobada, no automatizar acceso privado. | Página declara CC BY 4.0; verificar además procedencia de fotografías y si son originales o aumentos. |
| [Roboflow river data](https://universe.roboflow.com/simons-workspace-atqyl/river-data) | Incluye contaminación y algas. No aceptar todas sus categorías como contaminación visible por residuos. | Página declara CC BY 4.0; atribuir a Simons Workspace y registrar versión. |
| [Commons: Burning waste in India](https://commons.wikimedia.org/wiki/Category:Burning_waste_in_India) | Semillas para aire; comprobar humo y residuos reconocibles, pertinencia rural y escenas repetidas. | Licencia por archivo, no por categoría. Guardar autor, enlace y modificaciones. |
| [Commons: Burning garbage](https://commons.wikimedia.org/wiki/File:Burning_garbage.JPG) | Ejemplo de fuente individual con descripción de quema de residuos. Falta inspección visual local. | Página declara dominio público, autor Maher A. A. Abdussalam. |

No se ha descargado ninguna fotografía nueva en esta ejecución: DNS restringido.
Los recolectores guardan datos crudos de procedencia y proponen clases; nunca
aprueban semánticamente una imagen por su nombre, consulta, caja o etiqueta.
No usar como aire incendios forestales, niebla, chimeneas o quema agrícola sin
residuos identificables. No usar basura urbana sobre pavimento para completar
artificialmente suelo rural. Excluir páginas escaneadas, dibujos, IA y montajes.

Las licencias BY requieren atribución; BY-SA también exige respetar compartir
igual para adaptaciones aplicables. Conservar originales y registrar cambios.
La compatibilidad de una recopilación con diferentes licencias debe revisarse
antes de publicar el dataset. No adjudicar una licencia global a todas las fotos.

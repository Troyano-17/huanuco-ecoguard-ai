"""Interfaz ambiental: fotografías y cámara con ONNX CPU validado."""
import argparse
import json
import logging
import os
from html import escape
from pathlib import Path

from camera_analysis import CameraAnalyzer, CameraSession
from inferencia import (
    ADVICE,
    INCONCLUSIVE_DESCRIPTION,
    INCONCLUSIVE_TITLE,
    LABELS,
    AnalysisError,
    accepted_label,
    create_classifier,
    load_image,
)
from mongo_store import AnalysisStore, StorageError

ASSETS = Path(__file__).resolve().parent
NOTICE = 'Este resultado es una orientación visual. No reemplaza una evaluación técnica o ambiental.'
# Textos de presentación; las categorías y puntuaciones originales se conservan.
VISUAL_DESCRIPTIONS = {
    'aire_contaminado': 'La imagen tiene rasgos visuales que se parecen a escenas con humo o contaminación del aire.',
    'agua_contaminada': 'La imagen tiene rasgos visuales que se parecen a escenas con residuos o cambios visibles en el agua.',
    'suelo_contaminado': 'La imagen tiene rasgos visuales que se parecen a escenas con residuos sobre el suelo o la vegetación.',
}
VISUAL_ADVICE = {label: text.replace('Como orientación general, ', '').replace('vertimientos', 'descargas de residuos en el agua').capitalize() for label, text in ADVICE.items()}
EMPTY_RESULT = ('<div class="eco-empty"><span class="eco-empty-symbol" aria-hidden="true">◌</span>'
                '<h3>Una mirada a tu entorno</h3><p>Tu resultado aparecerá aquí cuando analices una imagen.</p>'
                '<span class="eco-caption">Agua · Aire · Suelo</span></div>')


def storage_message(error):
    """Traduce los avisos del almacenamiento solo en la interfaz."""
    if 'no está configurado' in str(error):
        return 'El guardado no está habilitado. El análisis no se ha guardado.'
    return 'No pudimos acceder a los resultados guardados. Inténtalo de nuevo más tarde. El resultado actual sigue visible.'


CSS = (ASSETS / 'ecoguard_ui.css').read_text()
STOP_JS = '''() => {
  for (const id of ['live-camera', 'manual-camera']) {
    const root = document.getElementById(id);
    // Acción semántica nativa: cierra también el estado de grabación de Gradio.
    const capture = root?.querySelector('button[aria-label="capture photo"]');
    if (id === 'live-camera' && capture) {
      // El control nativo también existe mientras se espera un resultado.
      if (capture.querySelector('[title="start recording"]')) capture.click();
      capture.click();
    } else if (id === 'manual-camera' && capture) {
      capture.click();
    }
    root?.querySelectorAll('video').forEach(video => {
      video.srcObject?.getTracks().forEach(track => track.stop());
      video.srcObject = null;
    });
  }
  const feedback = document.getElementById('eco-camera-feedback');
  if (feedback) feedback.textContent = 'Cámara detenida. El último resultado se conserva sin guardar.';
  return [];
}'''


def score_bars(scores):
    bars = []
    for name, title in LABELS.items():
        percent = max(0, min(100, scores[name] * 100))
        bars.append(f'<div class="eco-score"><div class="eco-score-label">'
                    f'<span>{escape(title)}</span><strong>{percent:.2f} %</strong></div>'
                    f'<div class="eco-track" role="meter" aria-label="Coincidencia visual: {escape(title)}" '
                    f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent:.2f}">'
                    f'<div class="eco-fill" style="width:{percent:.2f}%"></div></div></div>')
    return '<p class="eco-eyebrow">Coincidencia visual</p>' + ''.join(bars) + '<p class="eco-caption">Estos valores indican parecido visual, no el nivel de contaminación.</p>'


def result_html(result=None):
    if result is None:
        return '<section class="eco-result">' + EMPTY_RESULT.replace('cuando analices una imagen', 'cuando analices una escena') + '</section>'
    scores = result['scores']
    label = accepted_label(scores)
    if label is None:
        return (f'<section class="eco-result eco-inconclusive" aria-live="polite"><h3>{INCONCLUSIVE_TITLE}</h3>'
                f'<p>{INCONCLUSIVE_DESCRIPTION}</p></section>')
    return (f'<section class="eco-result" aria-live="polite"><p class="eco-eyebrow">Resultado principal</p>'
            f'<h3 class="eco-main-result">{escape(LABELS[label])}</h3>{score_bars(scores)}'
            f'<div class="eco-explanation"><h4>¿Por qué dio este resultado?</h4><p>{escape(VISUAL_DESCRIPTIONS[label])}</p></div>'
            f'<div class="eco-recommendation"><h4>¿Qué podrías hacer en una situación así?</h4><p>{escape(VISUAL_ADVICE[label])}</p></div>'
            '</section>')


def build_app(weights):
    import gradio as gr
    classifier = create_classifier(weights)
    camera_analyzer = CameraAnalyzer(classifier)
    store = AnalysisStore()
    from artefactos import sha256
    version = getattr(classifier, 'version', None) or sha256(weights)

    def authenticated_user(request):
        """Gradio inyecta la identidad devuelta por auth_dependency.

        ``None`` solo existe al invocar funciones directamente desde pruebas Python;
        las rutas HTTP siempre quedan bajo la dependencia de autenticación.
        """
        if request is None:
            return None
        user_id = getattr(request, 'username', None)
        if not user_id:
            raise gr.Error('Tu sesión finalizó. Inicia sesión nuevamente.')
        return user_id

    def save_result(label, scores, request=None):
        user_id = authenticated_user(request)
        if accepted_label(scores) != label or label is None:
            return INCONCLUSIVE_TITLE + '. No se ha guardado el resultado.'
        try:
            ident = (store.insert_for_user(user_id, label, scores, version)
                     if user_id else store.insert(label, scores, version))
            return 'Resultado guardado. Referencia: ' + ident
        except StorageError as exc:
            return storage_message(exc)
        except Exception:  # noqa: BLE001 - frontera UI: mensaje seguro sin detalles internos
            return 'No pudimos confirmar el guardado. El resultado sigue visible.'

    def infer(image, request: gr.Request = None):
        authenticated_user(request)
        try:
            with camera_analyzer.engine_lock:
                label, scores = classifier.predict(image)
            label = accepted_label(scores)
            if label is None:
                return '', result_html({'label': None, 'scores': scores}), '', '', 'Puedes intentar nuevamente con otra fotografía. No se ha guardado el resultado.'
            return LABELS[label], score_bars(scores), VISUAL_DESCRIPTIONS[label], VISUAL_ADVICE[label], 'Análisis completado. ' + save_result(label, scores, request)
        except AnalysisError as exc:
            return '', '', '', '', str(exc)
        except Exception:  # noqa: BLE001 - frontera UI: mensaje seguro sin detalles internos
            logging.getLogger('ecoguard').error('Inferencia falló; revisa integridad del modelo y dependencias.')
            return '', '', '', '', 'No pudimos completar el análisis. Reinicia e inténtalo de nuevo.'

    def reset(request: gr.Request = None):
        authenticated_user(request)
        return None, None, '', '', '', '', 'Elige una fotografía para comenzar.'

    def update_preview(source, request: gr.Request = None):
        authenticated_user(request)
        if source is None:
            return None, '', '', '', '', 'Elige una fotografía para comenzar.'
        try:
            return load_image(source), '', '', '', '', 'Fotografía lista. Pulsa Analizar imagen para ver el resultado.'
        except AnalysisError as exc:
            return None, '', '', '', '', str(exc)
        except Exception:  # noqa: BLE001 - frontera UI: mensaje seguro sin detalles internos
            return None, '', '', '', '', 'No se pudo mostrar la fotografía. Carga otro archivo.'

    def history(request: gr.Request = None):
        user_id = authenticated_user(request)
        try:
            records = store.history_for_user(user_id) if user_id else store.history()
            counts = store.stats_for_user(user_id) if user_id else store.stats()
            rows = [[r['fecha_hora'].isoformat(), LABELS.get(r['categoria'], r['categoria']),
                     r['analisis_id'], r['version_modelo']] for r in records]
            return rows, [[LABELS[c], n] for c, n in counts.items()], 'Resultados actualizados.' if records else 'Todavía no hay resultados guardados.'
        except StorageError as exc:
            return [], [], storage_message(exc)
        except Exception as exc:  # noqa: BLE001 - frontera UI: mensaje seguro
            logging.getLogger('ecoguard').warning('Consulta de historial falló (%s)', type(exc).__name__)
            return [], [], 'No se pudo interpretar el historial. Avisa al responsable de la aplicación.'

    def start(session, request: gr.Request = None):
        authenticated_user(request)
        session.start()
        return result_html(), 'Análisis habilitado. Permite el acceso a la cámara y pulsa Grabar / Record en la vista previa. Los resultados no se guardan automáticamente.', gr.update(interactive=False)

    def stop(session, request: gr.Request = None):
        authenticated_user(request)
        session.stop()
        return 'Análisis detenido. Puedes guardar el último resultado con el botón Guardar resultado.'

    def frame(source, session, manual=False, request: gr.Request = None):
        authenticated_user(request)
        try:
            result = camera_analyzer.frame(source, session, manual=manual)
            if result is None:
                return gr.skip(), gr.skip(), gr.skip()
            accepted = result['label'] is not None
            status = 'Resultado actualizado. Aún no se ha guardado.' if accepted else 'Puedes volver a orientar la cámara o analizar otra captura. No hay un resultado actual para guardar.'
            return result_html(result), status, gr.update(interactive=accepted)
        except AnalysisError as exc:
            return result_html(), str(exc).replace('fotograma', 'imagen de la cámara') + ' No hay resultado actual para guardar.', gr.update(interactive=False)
        except Exception:  # noqa: BLE001 - frontera UI: mensaje seguro sin detalles internos
            return result_html(), 'No se pudo analizar la imagen de la cámara. Detén y vuelve a iniciar la cámara. No se guardó el resultado.', gr.update(interactive=False)

    def manual_frame(source, session, request: gr.Request = None):
        return frame(source, session, manual=True, request=request)

    def save_current(session, request: gr.Request = None):
        authenticated_user(request)
        current = camera_analyzer.snapshot(session)
        if current is None:
            return 'No hay un resultado actual para guardar. Analiza una escena primero.'
        return save_result(current['label'], current['scores'], request) + ' No se guardó ninguna imagen.'

    theme = gr.themes.Soft(primary_hue='emerald', secondary_hue='slate', neutral_hue='slate',
                           font=['ui-sans-serif', 'system-ui', 'sans-serif'])
    theme.set(
        body_background_fill='#0b1412', body_background_fill_dark='#0b1412',
        body_text_color='#e5eeea', body_text_color_dark='#e5eeea',
        body_text_color_subdued='#a4b9af', body_text_color_subdued_dark='#a4b9af',
        background_fill_primary='#111f1a', background_fill_primary_dark='#111f1a',
        background_fill_secondary='#162720', background_fill_secondary_dark='#162720',
        block_background_fill='#111f1a', block_background_fill_dark='#111f1a',
        block_border_color='#2b4036', block_border_color_dark='#2b4036',
        block_label_background_fill='#162720', block_label_background_fill_dark='#162720',
        block_label_text_color='#c4d6cd', block_label_text_color_dark='#c4d6cd',
        input_background_fill='#0e1a15', input_background_fill_dark='#0e1a15',
        input_border_color='#344d40', input_border_color_dark='#344d40',
        button_primary_background_fill='#72dfaa', button_primary_background_fill_hover='#94ebbf',
        button_primary_background_fill_dark='#72dfaa', button_primary_background_fill_hover_dark='#94ebbf',
        button_primary_text_color='#082017', button_primary_text_color_dark='#082017',
        button_secondary_background_fill='#1c3027', button_secondary_background_fill_dark='#1c3027',
        button_secondary_background_fill_hover='#294336', button_secondary_background_fill_hover_dark='#294336',
        button_secondary_text_color='#e5eeea', button_secondary_text_color_dark='#e5eeea',
        table_even_background_fill='#14271d', table_even_background_fill_dark='#14271d',
        table_odd_background_fill='#192d22', table_odd_background_fill_dark='#192d22',
        table_text_color='#d4e4db', table_text_color_dark='#d4e4db',
        table_border_color='#344d40', table_border_color_dark='#344d40',
        border_color_primary='#2b4036', border_color_primary_dark='#2b4036', block_radius='16px',
    )
    with gr.Blocks(title='HUÁNUCO ECOGUARD AI', css=CSS, theme=theme,
                   js=(ASSETS / 'camera_browser.js').read_text(), analytics_enabled=False,
                   delete_cache=(60, 120)) as app:
        session = gr.State(CameraSession(), time_to_live=1800, delete_callback=lambda s: s.stop())
        with gr.Column(elem_id='eco-shell'):
            gr.HTML('<header id="eco-intro"><span class="eco-kicker">HUÁNUCO · CUIDADO DEL ENTORNO</span>'
                    '<h1>HUÁNUCO ECOGUARD AI</h1><p class="eco-subtitle">Observa tu entorno y aprende a cuidarlo.</p>'
                    '<p class="eco-intro-copy">Esta herramienta ayuda a reconocer visualmente escenas relacionadas con agua, aire o suelo.</p></header>')
            gr.HTML(f'<aside id="eco-notice"><strong>Importante:</strong> {NOTICE}</aside>')
            gr.HTML('<form class="eco-logout" method="post" action="/logout">'
                    '<button type="submit">Cerrar sesión</button></form>')
            with gr.Tabs(elem_id='eco-tabs'):
                with gr.Tab('Fotografía'):
                    with gr.Row(elem_classes='eco-workspace'):
                        with gr.Column(min_width=260, elem_classes='eco-input-panel'):
                            gr.Markdown('### 1. Elige una imagen\nSube una fotografía donde se observe una escena de agua, aire o suelo.')
                            image = gr.File(type='filepath', file_count='single', label='Elegir fotografía', file_types=['.jpg', '.jpeg', '.png', '.webp'], elem_id='eco-upload')
                            gr.Markdown('JPG, PNG o WEBP · Hasta 20 MB y 20 megapíxeles.', elem_classes='eco-help')
                            preview = gr.Image(label='Tu fotografía', interactive=False, height=250, elem_id='eco-preview')
                            with gr.Row(elem_classes='eco-actions'):
                                button = gr.Button('Analizar imagen', variant='primary')
                                clear = gr.Button('Limpiar')
                            gr.Markdown('Al analizar, se intentará guardar el resultado si el guardado está habilitado. Las fotografías no se guardan en el historial.', elem_classes='eco-help')
                        with gr.Column(min_width=260, elem_id='eco-photo-output'):
                            gr.Markdown('### 2. Resultado')
                            with gr.Column(elem_classes='eco-result', elem_id='eco-photo-result', min_width=0):
                                gr.HTML(EMPTY_RESULT, elem_id='eco-photo-empty')
                                gr.Markdown('Resultado principal', elem_classes='eco-result-label')
                                category = gr.Markdown('', elem_classes='eco-category')
                                scores = gr.HTML('', elem_id='eco-photo-scores')
                                with gr.Column(elem_classes='eco-explanation', min_width=0):
                                    gr.Markdown('#### ¿Por qué dio este resultado?')
                                    description = gr.Markdown('')
                                with gr.Column(elem_classes='eco-recommendation', min_width=0):
                                    gr.Markdown('#### ¿Qué podrías hacer en una situación así?')
                                    advice = gr.Markdown('')
                    status = gr.Markdown('Elige una fotografía para comenzar.', elem_classes='eco-status')
                with gr.Tab('Cámara'):
                    gr.Markdown('### Usa tu cámara para observar una escena')
                    gr.HTML('<ol class="eco-steps"><li><span>1</span><p>Pulsa <strong>Iniciar análisis</strong>.</p></li>'
                            '<li><span>2</span><p>Permite el acceso a tu cámara.</p></li>'
                            '<li><span>3</span><p>Pulsa <strong>Grabar / Record</strong> en la vista previa.</p></li></ol>')
                    with gr.Row(elem_classes='eco-workspace'):
                        with gr.Column(min_width=260, elem_classes='eco-input-panel'):
                            live = gr.Image(sources=['webcam'], type='pil', streaming=True, height=320,
                                            label='Cámara en vivo', elem_id='live-camera',
                                            webcam_options=gr.WebcamOptions(mirror=False, constraints={'video': {
                                                'facingMode': {'ideal': 'environment'}, 'width': {'ideal': 960},
                                                'height': {'ideal': 720}, 'frameRate': {'ideal': 10}}}),
                                            show_download_button=False)
                            with gr.Row(elem_classes='eco-actions'):
                                begin = gr.Button('Iniciar análisis', variant='primary')
                                end = gr.Button('Detener análisis y cámara')
                            gr.Markdown('La escena se revisa aproximadamente cada 2 segundos. Usa la flecha del control de cámara para elegir otra, si está disponible.', elem_classes='eco-help')
                            gr.HTML('<p id="eco-camera-feedback" role="status" aria-live="polite">'
                                    'Si la cámara pide permiso, permite el acceso en tu navegador. '
                                    'También puedes usar la pestaña Fotografía.</p>')
                        with gr.Column(min_width=260):
                            gr.Markdown('### Resultado de la cámara')
                            camera_result = gr.HTML(result_html())
                            save = gr.Button('Guardar resultado', interactive=False)
                    camera_status = gr.Markdown('Cámara inactiva. Tú decides cuándo guardar un resultado.', elem_classes='eco-status')
                    with gr.Accordion('¿Conexión lenta? Prueba una captura manual', open=False):
                        gr.Markdown('1. Detén el análisis en vivo.\n2. Permite el acceso a la cámara y pulsa el icono de captura.\n3. Pulsa **Analizar captura**. Después puedes guardar el resultado.')
                        manual = gr.Image(sources=['webcam'], type='pil', height=280, elem_id='manual-camera', label='Captura manual',
                                          webcam_options=gr.WebcamOptions(mirror=False, constraints={'video': {'facingMode': {'ideal': 'environment'}, 'width': {'ideal': 960}, 'height': {'ideal': 720}}}))
                        manual_button = gr.Button('Analizar captura')
            with gr.Accordion('Resultados guardados', open=False, elem_id='eco-history'):
                gr.Markdown('Consulta tus últimos 100 resultados. El historial es privado y no incluye fotografías.', elem_classes='eco-help')
                refresh = gr.Button('Actualizar resultados')
                history_status = gr.Markdown('Pulsa Actualizar resultados para consultar el historial.', elem_classes='eco-status')
                records = gr.Dataframe(value=[], row_count=0, headers=['Fecha (UTC)', 'Resultado', 'Referencia', 'Versión'], interactive=False, label='Últimos resultados', wrap=False)
                counts = gr.Dataframe(value=[], row_count=0, headers=['Resultado', 'Total guardado'], interactive=False, label='Resultados por categoría', wrap=False)
            with gr.Accordion('Acerca de esta herramienta', open=False):
                gr.Markdown('Este proyecto ayuda a observar escenas relacionadas con **agua, aire o suelo**. '
                            'Muestra una categoría cuando el parecido visual alcanza el mínimo requerido; en caso contrario, te invita a intentar de nuevo. No identifica una categoría de ambiente limpio.\n\n'
                            'En una prueba con 23 fotografías, acertó en 21. Son pocas imágenes y puede equivocarse con escenas nuevas, '
                            'mezcladas o con poca luz. No identifica objetos individuales ni mide la contaminación.')
            gr.HTML('<div id="eco-footer">HUÁNUCO ECOGUARD AI <span>·</span> Observa, aprende y cuida tu entorno.</div>')
        outputs = [category, scores, description, advice, status]
        button.click(infer, inputs=image, outputs=outputs, concurrency_limit=1, concurrency_id='engine', api_name='analizar')
        clear.click(reset, outputs=[image, preview, *outputs], queue=False, api_name='reiniciar')
        image.change(update_preview, inputs=image, outputs=[preview, *outputs], queue=False, api_name=False)
        begin.click(start, session, [camera_result, camera_status, save], queue=False, api_name='iniciar_camara')
        stream = live.stream(frame, [live, session], [camera_result, camera_status, save], stream_every=2,
                             trigger_mode='once', concurrency_limit=None,
                             time_limit=300, show_progress='hidden', api_name='fotograma')
        end.click(stop, session, camera_status, cancels=[stream], js=STOP_JS, queue=False, api_name='detener_camara')
        manual_button.click(manual_frame, [manual, session], [camera_result, camera_status, save],
                            concurrency_limit=1, concurrency_id='engine', api_name='captura_manual')
        save.click(save_current, session, camera_status, concurrency_limit=1, api_name='guardar_camara')
        refresh.click(history, outputs=[records, counts, history_status], concurrency_limit=1, api_name='historial')
    return app.queue(max_size=4, default_concurrency_limit=1), infer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', default=os.environ.get('MODEL_PATH', 'models/best.onnx'))
    parser.add_argument('--share', action='store_true')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '7860')))
    parser.add_argument('--status-file', type=Path)
    args = parser.parse_args()
    app, _ = build_app(args.weights)
    _, local, public = app.launch(share=args.share, server_name='0.0.0.0', server_port=args.port,
                                 prevent_thread_lock=True, show_error=False, max_file_size='20mb')
    if args.status_file:
        args.status_file.write_text(json.dumps({'local': local, 'url': public, 'pid': os.getpid()}, ensure_ascii=False))
    import threading
    threading.Event().wait()


if __name__ == '__main__':
    main()

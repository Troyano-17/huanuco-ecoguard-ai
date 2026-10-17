() => {
  // Traducción de los mensajes nativos de carga, sin alterar sus controles.
  const translateControls = () => {
    const translations = {'Drop File Here': 'Arrastra aquí tu fotografía', '- or -': 'o', 'or': 'o', 'Click to Upload': 'Elige un archivo', 'Click to Access Webcam': 'Permitir acceso a la cámara'};
    for (const root of document.querySelectorAll('#eco-upload, #live-camera, #manual-camera')) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const translated = translations[node.textContent.trim()];
      if (translated) node.textContent = ' ' + translated + ' ';
    }
    root.querySelector('button[aria-dropeffect]')?.setAttribute('aria-label', 'Elige una fotografía o arrástrala aquí');
    root.querySelector('input[type="file"]')?.setAttribute('aria-label', 'Elegir fotografía');
    }
  };
  translateControls();
  new MutationObserver(translateControls).observe(document.getElementById('eco-shell') || document.body, {childList: true, characterData: true, subtree: true});
  const message = (text) => {
    const node = document.getElementById('eco-camera-feedback');
    if (node) node.textContent = text;
  };
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    message('Para usar la cámara, abre la app desde una conexión segura (HTTPS) o en este equipo (localhost). También puedes usar una fotografía.');
  }
  // Gradio 5.49.1 puede rechazar getUserMedia sin publicar un evento Python.
  window.addEventListener('unhandledrejection', (event) => {
    const messages = {
      NotAllowedError: 'Permiso de cámara rechazado. Habilítalo en la configuración del navegador y vuelve a intentarlo.',
      NotFoundError: 'No se encontró una cámara. Conecta una o utiliza una fotografía.',
      NotReadableError: 'La cámara no está disponible. Cierra otras aplicaciones que la estén usando.',
      OverconstrainedError: 'La cámara no admite esta configuración. Prueba otra cámara o carga una fotografía.',
      AbortError: 'Se interrumpió el acceso a la cámara. Vuelve a conectarla.'
    };
    if (messages[event.reason?.name]) message(messages[event.reason.name]);
  });
  // Eventos del video y sus tracks, acotados a nuestros componentes.
  const watched = new WeakSet();
  document.addEventListener('loadedmetadata', (event) => {
    const video = event.target;
    if (!(video instanceof HTMLVideoElement) || !video.closest('#live-camera, #manual-camera')) return;
    message('Cámara conectada. Para observar en vivo, pulsa Iniciar análisis y luego Grabar / Record en la vista previa.');
    for (const track of video.srcObject?.getVideoTracks() || []) {
      if (watched.has(track)) continue;
      watched.add(track);
      track.addEventListener('ended', () => message('La cámara se desconectó. Detén el análisis y vuelve a conectarla.'));
      track.addEventListener('mute', () => message('La cámara dejó de entregar imagen. Comprueba la conexión y el permiso.'));
    }
  }, true);
  window.addEventListener('pagehide', () => {
    document.querySelectorAll('#live-camera video, #manual-camera video').forEach(video => {
      video.srcObject?.getTracks().forEach(track => track.stop());
    });
  });
}

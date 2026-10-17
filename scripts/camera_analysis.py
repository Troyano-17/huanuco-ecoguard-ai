"""Sesiones de cámara: solo resultados, sin almacenar fotogramas."""
import copy
import threading
import time

from inferencia import AnalysisError, accepted_label, load_image


class CameraSession:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = False
        self.generation = 0
        self.latest = None
        self.last_started = None

    def __deepcopy__(self, memo):
        return CameraSession()

    def start(self):
        with self.lock:
            self.generation += 1
            self.active = True
            self.latest = None
            self.last_started = None

    def stop(self):
        with self.lock:
            self.active = False
            self.generation += 1


class CameraAnalyzer:
    def __init__(self, classifier, interval=2.0):
        self.classifier = classifier
        self.interval = interval
        # También compartido con fotografía; no esperan fotogramas detrás del motor.
        self.engine_lock = threading.Lock()

    def frame(self, source, session, manual=False):
        with session.lock:
            if not manual and not session.active:
                return None
            now = time.monotonic()
            if not manual and session.last_started is not None and now - session.last_started < self.interval:
                return None
            generation = session.generation
            if not self.engine_lock.acquire(blocking=False):
                return None
            session.last_started = now
        try:
            if source is None:
                raise AnalysisError('No hay fotograma. Permite el acceso a la cámara o vuelve a conectarla.')
            image = load_image(source)
            # La vista previa conserva su resolución; solo reducimos la copia de inferencia.
            image.thumbnail((960, 960))
            start = time.perf_counter()
            label, scores = self.classifier.predict(image)
            label = accepted_label(scores)
            result = {'label': label, 'scores': scores, 'ms': (time.perf_counter() - start) * 1000}
            with session.lock:
                if generation != session.generation or (not manual and not session.active):
                    return None
                session.latest = copy.deepcopy(result)
            return result
        except Exception:
            with session.lock:
                if generation == session.generation:
                    session.latest = None
            raise
        finally:
            self.engine_lock.release()

    @staticmethod
    def snapshot(session):
        with session.lock:
            current = session.latest
            if current is None or accepted_label(current['scores']) is None:
                return None
            return copy.deepcopy(current)

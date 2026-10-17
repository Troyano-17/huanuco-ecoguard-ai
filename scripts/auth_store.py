"""Usuarios y sesiones persistentes para MongoDB Atlas."""
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

SESSION_COOKIE = "ecoguard_session"
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_WINDOW_MINUTES = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Parámetros interactivos recomendados para Argon2id con memoria contenida en Render.
PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1,
                                 hash_len=32, salt_len=16)


class AuthError(RuntimeError):
    """Error esperado que puede convertirse en un mensaje público seguro."""


class DuplicateEmail(AuthError):
    pass


class InvalidRegistration(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class LoginBlocked(AuthError):
    pass


def utcnow():
    return datetime.now(UTC)


def normalize_email(value):
    return (value or "").strip().casefold()


def validate_registration(name, email, password):
    name = " ".join((name or "").split())
    email = normalize_email(email)
    errors = []
    if not 2 <= len(name) <= 80:
        errors.append("Escribe tu nombre (entre 2 y 80 caracteres).")
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        errors.append("Escribe un correo electrónico válido.")
    if not 10 <= len(password or "") <= 128:
        errors.append("La contraseña debe tener entre 10 y 128 caracteres.")
    elif not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", password) or not re.search(r"\d", password):
        errors.append("La contraseña debe incluir al menos una letra y un número.")
    return name, email, errors


class AuthStore:
    def __init__(self, client=None, uri=None, database=None, secret=None):
        self.uri = os.environ.get("MONGODB_URI", "") if uri is None else uri
        self.database_name = database or os.environ.get("MONGODB_DB", "ecoguard")
        self.secret = secret if secret is not None else os.environ.get("SESSION_SECRET", "")
        self.client = client
        self.db = None
        self._indexed = False

    def connect(self):
        if not self.uri and self.client is None:
            raise AuthError("El servicio de cuentas no está disponible.")
        if len(self.secret) < 32:
            raise AuthError("La configuración de sesiones no es válida.")
        try:
            if self.client is None:
                from pymongo import MongoClient
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000, socketTimeoutMS=5000, maxPoolSize=5, tz_aware=True)
                self.client.admin.command("ping")
            self.db = self.client[self.database_name]
            if not self._indexed:
                self._ensure_indexes()
                self._indexed = True
            return self.db
        except AuthError:
            raise
        except PyMongoError:
            raise AuthError("El servicio de cuentas no está disponible.") from None

    def _ensure_indexes(self):
        self.db.usuarios.create_index([("correo_normalizado", ASCENDING)], unique=True,
                                      name="correo_unico")
        self.db.sesiones.create_index([("token_hash", ASCENDING)], unique=True,
                                      name="sesion_unica")
        self.db.sesiones.create_index([("expira_en", ASCENDING)], expireAfterSeconds=0,
                                      name="sesion_expira")
        self.db.sesiones.create_index([("usuario_id", ASCENDING)], name="sesiones_usuario")
        self.db.intentos_login.create_index([("expira_en", ASCENDING)], expireAfterSeconds=0,
                                            name="intentos_expiran")

    def register(self, name, email, password):
        name, email, errors = validate_registration(name, email, password)
        if errors:
            raise InvalidRegistration(" ".join(errors))
        db = self.connect()
        now = utcnow()
        user_id = str(uuid.uuid4())
        document = {"_id": user_id, "usuario_id": user_id, "nombre": name,
                    "correo_normalizado": email,
                    "password_hash": PASSWORD_HASHER.hash(password),
                    "fecha_registro": now, "estado": "activo"}
        try:
            db.usuarios.insert_one(document)
        except DuplicateKeyError:
            raise DuplicateEmail("Este correo ya tiene una cuenta.") from None
        except PyMongoError:
            raise AuthError("No pudimos crear tu cuenta. Inténtalo más tarde.") from None
        return user_id

    def _attempt_key(self, email):
        # HMAC evita almacenar el correo también en la colección de intentos.
        return hmac.new(self.secret.encode(), email.encode(), hashlib.sha256).hexdigest()

    def _record_failure(self, key, now):
        db = self.connect()
        try:
            window = now - timedelta(minutes=LOGIN_WINDOW_MINUTES)
            current = db.intentos_login.find_one({"_id": key})
            count = 1 if not current or current.get("ventana_desde", now) < window else current.get("fallos", 0) + 1
            blocked_until = now + timedelta(minutes=LOGIN_WINDOW_MINUTES) if count >= MAX_LOGIN_ATTEMPTS else None
            db.intentos_login.update_one({"_id": key}, {"$set": {
                "fallos": count, "ventana_desde": now if count == 1 else current["ventana_desde"],
                "bloqueado_hasta": blocked_until,
                "expira_en": now + timedelta(minutes=LOGIN_WINDOW_MINUTES * 2)}}, upsert=True)
        except PyMongoError:
            raise AuthError("El servicio de cuentas no está disponible.") from None

    def authenticate(self, email, password):
        email = normalize_email(email)
        db = self.connect()
        now, key = utcnow(), self._attempt_key(email)
        try:
            attempt = db.intentos_login.find_one({"_id": key})
            user = db.usuarios.find_one({"correo_normalizado": email, "estado": "activo"})
        except PyMongoError:
            raise AuthError("El servicio de cuentas no está disponible.") from None
        if attempt and attempt.get("bloqueado_hasta") and attempt["bloqueado_hasta"] > now:
            raise LoginBlocked("Espera unos minutos antes de intentarlo nuevamente.")
        valid = False
        if user:
            try:
                valid = PASSWORD_HASHER.verify(user["password_hash"], password or "")
            except (VerifyMismatchError, InvalidHashError, KeyError):
                valid = False
        else:
            # Trabajo equivalente para reducir diferencias observables entre correos existentes y ausentes.
            PASSWORD_HASHER.hash(password or secrets.token_urlsafe(16))
        if not valid:
            self._record_failure(key, now)
            raise InvalidCredentials("No pudimos iniciar sesión. Revisa tus datos e inténtalo nuevamente.")
        try:
            db.intentos_login.delete_one({"_id": key})
            if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
                db.usuarios.update_one({"_id": user["_id"]}, {"$set": {"password_hash": PASSWORD_HASHER.hash(password)}})
        except PyMongoError:
            raise AuthError("El servicio de cuentas no está disponible.") from None
        return user

    def _digest(self, token):
        return hmac.new(self.secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def create_session(self, user_id):
        db, now = self.connect(), utcnow()
        token = secrets.token_urlsafe(32)
        try:
            db.sesiones.insert_one({"_id": str(uuid.uuid4()), "token_hash": self._digest(token),
                "usuario_id": user_id, "creada_en": now,
                "expira_en": now + timedelta(hours=SESSION_HOURS), "revocada_en": None})
        except PyMongoError:
            raise AuthError("El servicio de cuentas no está disponible.") from None
        return token

    def resolve_session(self, token):
        if not token:
            return None
        try:
            db, now = self.connect(), utcnow()
            session = db.sesiones.find_one({"token_hash": self._digest(token),
                "revocada_en": None, "expira_en": {"$gt": now}})
            if not session:
                return None
            user = db.usuarios.find_one({"_id": session["usuario_id"], "estado": "activo"},
                                        {"password_hash": 0})
            return user
        except (AuthError, PyMongoError):
            return None

    def revoke_session(self, token):
        if not token:
            return
        try:
            self.connect().sesiones.update_one({"token_hash": self._digest(token)},
                {"$set": {"revocada_en": utcnow()}})
        except (AuthError, PyMongoError):
            return

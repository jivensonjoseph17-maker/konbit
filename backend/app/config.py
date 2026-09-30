"""
Konbit — Konfigirasyon

Chanjman prensipal parapò ak vèsyon anvan an:
  - `secret_key` PA gen valè pa defo. Si l pa nan .env, app la p ap demare.
    Sa anpeche ou voye yon kle piblik nan pwodiksyon san w pa konnen.
  - `environment` pou ou ka fè verifikasyon pi sevè nan pwodiksyon.
  - Refresh token separe ak access token.
  - `database_url`: "postgres://" ak "postgresql://" (fòma Render bay la)
    vin "postgresql+psycopg://" otomatikman (Psycopg 3).
"""

from typing import List, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Anviwonman ---
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # --- Baz done ---
    # Devlopman: sqlite:///./konbit.db
    # Pwodiksyon: postgresql+psycopg://user:pass@host:5432/konbit
    database_url: str = "sqlite:///./konbit.db"

    # --- Sekirite ---
    # PA GEN VALÈ PA DEFO. Jenere l konsa:
    #   python -c "import secrets; print(secrets.token_urlsafe(64))"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    password_min_length: int = 10
    # --- Pwoteksyon koneksyon (app/login_guard.py) ---
    # Move esè sou YON imel nan fenèt la → imel sa a bloke jiskaske fenèt la pase.
    max_failed_logins: int = 5
    login_window_minutes: int = 15
    # Move esè depi YON IP nan fenèt la (sou nenpòt imel) → IP sa a bloke.
    login_max_failures_per_ip: int = 30
    signup_max_per_ip_hour: int = 5

    # --- Kiyòsk ---
    # Kle HMAC pou mòd "kòd sèlman" tablèt la (routers/kiosk.py). SEPARE ak
    # SECRET_KEY: konsa yon rotasyon SECRET_KEY pa kase kòd tablèt yo.
    # Vid = SECRET_KEY (devlopman). Obligatwa nan pwodiksyon.
    kiosk_lookup_key: str = ""

    # --- CORS ---
    # Nan varyab anviwonman: ALLOWED_ORIGINS=["https://konmbit.com","https://www.konmbit.com"]
    frontend_url: str = "http://localhost:3000"
    allowed_origins: List[str] = ["http://localhost:3000"]

    # --- Fichye ---
    upload_dir: str = "./uploads"
    max_upload_mb: int = 25

    # --- MonCash (Digicel) ---
    moncash_client_id: str = ""
    moncash_client_secret: str = ""
    moncash_base_url: str = "https://sandbox.moncashbutton.digicelgroup.com"

    # --- NatCash (Natcom) ---
    natcash_merchant_id: str = ""
    natcash_api_key: str = ""
    natcash_base_url: str = "https://api.natcash.ht"

    # --- Kobara / Stripe ---
    kobara_api_key: str = ""
    kobara_base_url: str = "https://api.kobara.app"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url")
    @classmethod
    def use_psycopg3_driver(cls, v: str) -> str:
        """
        Render (ak lòt sèvis) bay "postgres://…" oswa "postgresql://…".
        San drayv la nan adrès la, SQLAlchemy chèche psycopg2, ki pa enstale:
        app la ta kraze nan demaraj. Nou mete Psycopg 3 esplisitman.
        """
        v = v.strip()
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY twò kout. Li dwe gen omwen 32 karaktè. "
                'Jenere l: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        weak = {"secret", "changeme", "dev", "test", "konbit", "change-this"}
        if any(w in v.lower() for w in weak):
            raise ValueError("SECRET_KEY sa a twò fasil pou devine. Jenere yon lòt.")
        return v

    @field_validator("kiosk_lookup_key")
    @classmethod
    def kiosk_key_must_be_strong(cls, v: str) -> str:
        v = v.strip()
        if v and len(v) < 32:
            raise ValueError("KIOSK_LOOKUP_KEY twò kout. Li dwe gen omwen 32 karaktè.")
        return v

    @property
    def kiosk_key(self) -> str:
        return self.kiosk_lookup_key or self.secret_key

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()

# Gad siplemantè pou pwodiksyon
if settings.is_production:
    if settings.database_url.startswith("sqlite"):
        raise RuntimeError("Pa sèvi ak SQLite nan pwodiksyon. Sèvi ak PostgreSQL.")
    if settings.debug:
        raise RuntimeError("DEBUG pa ka True nan pwodiksyon.")
    if not settings.kiosk_lookup_key:
        raise RuntimeError("KIOSK_LOOKUP_KEY obligatwa nan pwodiksyon (kle separe ak SECRET_KEY).")
    if settings.kiosk_lookup_key == settings.secret_key:
        raise RuntimeError("KIOSK_LOOKUP_KEY dwe diferan de SECRET_KEY.")
    for _origin in (settings.frontend_url, *settings.allowed_origins):
        if not _origin.startswith("https://") or "localhost" in _origin or "127.0.0.1" in _origin:
            raise RuntimeError(f"Orijin CORS pa sekirize nan pwodiksyon: {_origin}")

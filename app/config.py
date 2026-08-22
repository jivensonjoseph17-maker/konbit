from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    moncash_client_id: str = ""
    moncash_client_secret: str = ""
    moncash_base_url: str = "https://sandbox.moncashbutton.digicelgroup.com"
    kobara_api_key: str = ""
    kobara_base_url: str = "https://api.kobara.app"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    frontend_url: str = "http://localhost:3000"
    
    class Config:
        env_file = ".env"

settings = Settings()
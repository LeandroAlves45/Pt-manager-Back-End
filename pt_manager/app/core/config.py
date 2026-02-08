from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    """
    Configurações da aplicação

    database_url:
    - SQlite local: "sqlite:///./pt_manager.db"
    - PostgreSQL: "postgresql+psycopg2://user:pass@host:5432/dbname"
    """

    #pydantic Settings v2
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive= False)

    database_url: str
    api_key: str 

    #---Notificações---

    timezone: str = "Europe/Lisbon" #Definir o fuso horário para as notificações
    reminder_hour_local: int = 9 #Hora local para enviar as notificações (0-23)

    trainer_email: str | None = None #Email do treinador para receber notificações

    #---- Servidor de email ----

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_email: str | None = None

    #--- Whataspp Cloud API (ex: Meta) ---
    wa_token: str | None = None #Token de acesso para WhatsApp Cloud API
    wa_phone_number_id: str | None = None #ID do número de telefone registrado na WhatsApp Cloud API

settings = Settings()
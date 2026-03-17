from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    """
    Configurações da aplicação

    database_url:
    - SQlite local: "sqlite:///./pt_manager.db"
    - PostgreSQL: "postgresql+psycopg2://user:pass@host:5432/dbname"

    Novas variáveis para Stripe:
        STRIPE_SECRET_KEY      : chave secreta da API Stripe (sk_test_... ou sk_live_...)
        STRIPE_WEBHOOK_SECRET  : chave para verificar assinaturas dos webhooks (whsec_...)
        STRIPE_PRICE_FREE      : ID do Price Stripe para o tier FREE (0€)
        STRIPE_PRICE_STARTER   : ID do Price Stripe para o tier STARTER (20€/mês)
        STRIPE_PRICE_PRO       : ID do Price Stripe para o tier PRO (40€/mês)
        STRIPE_SUCCESS_URL     : URL de redirecionamento após checkout bem sucedido
        STRIPE_CANCEL_URL      : URL de redirecionamento após cancelamento do checkout
    """

    #pydantic Settings v2
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive= False)

    #base de dados
    database_url: str

    #API KEY
    api_key: str 

    #JWT
    secret_key: str
    access_token_expire_minutes: int = 60 

    #Trial em dias
    trial_days: int = 15

    #STRIPE

    #Chave secreta da API Stripe 
    stripe_secret_key: str = ""

    #Chave para verificar assinaturas dos webhooks do Stripe
    stripe_webhook_secret: str = ""

    #IDs dos Prices do Stripe para cada tier de subscrição
    stripe_price_free: str = "" # 0€/mês - tier FREE
    stripe_price_starter: str = "" # 20€/mês - tier STARTER
    stripe_price_pro: str = "" # 40€/mês - tier PRO

    #URLs de redirecionamento após checkout do Stripe
    #Normalmente apontam para o frontend
    stripe_success_url: str = "http://localhost:5173/billing?success=true"
    stripe_cancel_url: str = "http://localhost:5173/billing?cancelled=true"
    stripe_portal_url: str = "http://localhost:5173/billing" 


    #---Notificações---

    timezone: str = "Europe/Lisbon" #Definir o fuso horário para as notificações
    reminder_hour_local: int = 9 #Hora local para enviar as notificações (0-23)

    trainer_email: str | None = None #Email do treinador para receber notificações

    #---- Servidor de email ----

    resend_api_key: str = "" #Chave da API do Resend para envio de emails
    email_from: str = "" #Email remetente para os emails enviados via Resend

    #---- Cloudinary ----
    cloudinary_cloud_name: str = "" #Cloud name do Cloudinary
    cloudinary_api_key: str = "" #API key do Cloudinary
    cloudinary_api_secret: str = "" #API secret do Cloudinary

    # Dentro da classe Settings:
    notification_test_mode: bool = False
    notification_test_minutes: int = 2

    # Configurações de CORS
    cors_origins: str = "http://localhost:3000, http://localhost:5173"  # Pode ser uma lista separada por vírgulas

    # Superuser seed
    superuser_email: str = ""
    superuser_password: str = ""
    superuser_name: str = "Admin"

    # Demo data seed
    seed_demo_data: bool = False
    demo_trainer_email: str = "trainer@demo.pt"
    demo_trainer_password: str = "Trainer123!"
    demo_trainer_name: str = "Trainer Demo"
    demo_client_email: str = "cliente@demo.pt"
    demo_client_password: str = "Cliente123!"
    demo_client_name: str = "Cliente Demo"

settings = Settings()
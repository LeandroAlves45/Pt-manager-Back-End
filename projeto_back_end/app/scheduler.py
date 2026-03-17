"""
Scheduler de notificações — APScheduler em background.
 
Executa um job a cada 60 segundos que processa todas as notificações
com estado "pending" cuja hora de envio já passou.
 
Arquitectura de isolamento de erros:
    Cada notificação é processada de forma independente dentro de um try/except.
    Uma falha numa notificação não aborta as restantes — o job continua.
    A notificação falhada é marcada como FAILED com a mensagem de erro.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

from app.db.session import get_session
from app.db.models.notification import NotificationChannel, NotificationStatus
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService
from app.utils.time import utc_now_datetime

logger = logging.getLogger(__name__)

# Instância global do scheduler — iniciada uma vez no startup da aplicação
scheduler = BackgroundScheduler()

def dispatch_job():

    """
    Job que processa e envia notificações de EMAIL pendentes.
    
    Executa a cada 60 segundos (configurado no scheduler).
    
    Fluxo:
    1. Verifica o canal (EMAIL é o único suportado actualmente)
    2. Se a mensagem começa com "TEMPLATE_HTML|" → email HTML com branding do trainer (para clientes)
    3. Caso contrário → email de texto simples para o trainer
    4. Marca como SENT ou FAILED consoante o resultado
    5. Faz commit de todos os estados no final do job
    """
    logger.info(f"[SCHEDULER] 🔄 Iniciando dispatch às {utc_now_datetime()}")

    with next(get_session()) as session:
        # Buscar notificações pendentes cuja hora de envio já chegou
        notifications = NotificationService.list_due_notifications(session, limit=100)
        logger.info(f"[SCHEDULER] 📬 Encontradas {len(notifications)} notificação(ões) para enviar")
        for notification in notifications:
            try:
                recipient =(notification.recipient or "").strip()

                # ================================================
                # PROCESSAR EMAIL
                # ================================================
                if notification.channel == NotificationChannel.EMAIL:
                    logger.info(f"[EMAIL] 📧 Processando para {recipient}")
                
                    #verificar se é template HTML (cliente)
                    if notification.message.startswith("TEMPLATE_HTML|"):
                        # ========================================
                        # EMAIL HTML PARA CLIENTE
                        # ========================================
                        
                        # Extrai os pares chave=valor do template
                        raw = notification.message.replace("TEMPLATE_HTML|", "")
                        parts = dict(
                            item.split("=", 1)
                            for item in raw.split(";")
                            if "=" in item
                        )

                        EmailService.send_session_email(
                            to_email=notification.recipient,
                            client_name=parts.get("client_name", ""),
                            session_date=parts.get("session_date", ""),
                            session_time=parts.get("session_time", ""),
                            duration_minutes=int(parts.get("duration_minutes", "60")),
                            location=parts.get("location", ""),
                            trainer_logo_url=parts.get("trainer_logo_url", ""),
                        )
                        logger.info(f"[EMAIL] ✅ Email HTML enviado para {recipient}")
                            
                    else:
                        # ========================================
                        # EMAIL SIMPLES PARA TREINADOR
                        # ========================================
                        
                        EmailService.send_trainer_reminder(
                            to_email=recipient,
                            subject="Lembrete de Sessão - PT Manager",
                            body=notification.message,
                        )

                        logger.info(f"[EMAIL] ✅ Email simples enviado para {recipient}")

                    # Marcar como enviada com timestamp UTC
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = utc_now_datetime()
                    session.add(notification)
                    
                    logger.info(f"[SUCCESS] ✅ Notificação {notification.id[:8]} processada com sucesso")

                # ================================================
                # CANAL NÃO SUPORTADO
                # Cancela a notificação em vez de a deixar eternamente pending
                # ================================================
                else:
                    logger.warning(
                        f"[SCHEDULER] ⚠️  Canal {notification.channel} não suportado. "
                        f"Cancelando notificação {notification.id[:8]}"
                    )
                    notification.status = NotificationStatus.CANCELLED
                    notification.error_message = f"Canal {notification.channel} não está ativo"
                    session.add(notification)
                    
            except Exception as e:
                # Isolamento de erros: uma falha numa notificação não impede as restantes de serem processadas
                logger.error(f"[FAILED] ❌ Erro ao processar notificação {notification.id[:8]}: {e}")
                logger.exception("Stacktrace completo:")
                
                notification.status = NotificationStatus.FAILED
                notification.error_message = str(e)[:500]  # Limitar tamanho
                session.add(notification)

        session.commit()
        logger.info(f"[SCHEDULER] ✅ Dispatch concluído. {len(notifications)} processada(s).")

# ---------------------------------------------------------------
# Limpeza periódica de tokens expirados — para manter a tabela active_tokens enxuta
# ---------------------------------------------------------------
 
def token_cleanup_job():
    """
    Exclui as linhas expiradas de active_tokens.

    Esta é uma limpeza adicional — os tokens já são invalidados
    ao fazer logout, excluindo a linha. Esta tarefa captura tokens que expiraram
    naturalmente (o usuário nunca fez logout explicitamente) para manter a tabela enxuta.
    """
    from datetime import timezone
    from datetime import datetime
    from sqlmodel import select
    from app.db.models.active_token import ActiveToken
 
    logger.info("[SCHEDULER] Token cleanup started")
 
    with next(get_session()) as session:
        now = datetime.now(timezone.utc)
        try:
            # Apagar tokens expirados
            expired = session.exec(
                select(ActiveToken).where(ActiveToken.expires_at < now)
            ).all()
 
            count = len(expired)
            for token in expired:
                session.delete(token)
 
            session.commit()
            logger.info(f"[SCHEDULER] Limpeza de tokens concluída — {count} token(s) expirado(s) removido(s).")
        except Exception as e:
            session.rollback()
            logger.error(f"[SCHEDULER] Falha na limpeza de tokens: {e}")

def start_scheduler():
    """
    Inicia o scheduler APScheduler em background.
 
    Chamado no hook on_startup do FastAPI (main.py).
    max_instances=1 garante que o job não se sobrepõe a si mesmo
    se a execução anterior demorar mais de 60 segundos.
    """
    logger.info("[SCHEDULER] Iniciando scheduler de notificações")
    
    scheduler.add_job(
        dispatch_job, 
        IntervalTrigger(seconds=60), 
        id="notification_dispatch", 
        replace_existing=True, 
        max_instances=1
    )
    
    scheduler.start()
    logger.info("[SCHEDULER] Scheduler iniciado com sucesso")

def shutdown_scheduler():
    """
    Desliga o scheduler graciosamente.
 
    Chamado no hook on_shutdown do FastAPI (main.py) para garantir
    que o job não fica a correr após o processo terminar.
    """

    logger.info("[SCHEDULER] Desligando scheduler de notificações")
    scheduler.shutdown(wait=False)
    logger.info("[SCHEDULER] Scheduler desligado")
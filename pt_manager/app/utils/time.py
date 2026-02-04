from datetime import datetime, timezone, date

def utc_now() -> date:
    """
    Devolve a data atual em UTC.
    Ideal para persistir apenas datas no DB com consistência.
    """
    return datetime.now(timezone.utc).date()

# Backward compatibility
utc_now_dt = utc_now

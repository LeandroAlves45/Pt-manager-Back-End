from datetime import datetime, timezone, date, timedelta, time
from zoneinfo import ZoneInfo

def utc_now() -> date:
    """
    Devolve a data atual em UTC.
    Ideal para persistir apenas datas no DB com consistência.
    """
    return datetime.now(timezone.utc).date()

def utc_now_datetime() -> datetime:
    """
    Devolve a data e hora atual em UTC.
    Ideal para persistir timestamps no DB com consistência.
    """
    return datetime.now(timezone.utc)

def local_date_to_utc_datetime(local_date: date, *,  hour: int, minute: int, tz_str: str) -> datetime:
    """
    Converte uma data e hora local para um timestamp UTC.
    """
    tz = ZoneInfo(tz_str)
    local_dt = datetime.combine(local_date, time(hour, minute), tzinfo=tz)
    return local_dt.astimezone(timezone.utc)

# Backward compatibility
utc_now_dt = utc_now

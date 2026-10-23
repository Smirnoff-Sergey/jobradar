from datetime import datetime

from pydantic import BaseModel


class TelegramLinkRead(BaseModel):
    """Ссылка на бота с одноразовым кодом: открыть её в Telegram и нажать «Start»."""

    url: str
    expires_at: datetime

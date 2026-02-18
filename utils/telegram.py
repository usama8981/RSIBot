"""Send messages via Telegram Bot API."""

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class TelegramLogHandler(logging.Handler):
    """Sends each INFO log record to a Telegram chat."""

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(level=logging.INFO)
        self.bot_token = bot_token
        self.chat_id = chat_id

    def emit(self, record: logging.LogRecord) -> None:
        if not self.bot_token or not self.chat_id:
            return
        try:
            text = self.format(record)
            # Plain text for log lines (no HTML to avoid escaping issues)
            send_message_plain(self.bot_token, self.chat_id, text)
        except Exception:
            self.handleError(record)


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message_plain(bot_token: str, chat_id: str, text: str) -> bool:
    """Send plain text (no HTML). Returns True if sent successfully."""
    if not bot_token or not chat_id:
        return False
    url = TELEGRAM_API.format(token=bot_token)
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if r.ok:
            return True
        logger.warning("Telegram send failed: %s %s", r.status_code, r.text)
        return False
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a text message to a Telegram chat (HTML). Returns True if sent successfully."""
    if not bot_token or not chat_id:
        return False
    url = TELEGRAM_API.format(token=bot_token)
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.ok:
            return True
        logger.warning("Telegram send failed: %s %s", r.status_code, r.text)
        return False
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


def format_trade_alert(
    symbol: str,
    side: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    dry_run: bool = False,
) -> str:
    """Format entry/SL/TP for Telegram."""
    mode = "DRY RUN " if dry_run else ""
    return (
        f"🔔 <b>{mode}Trade Entry</b>\n\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Side:</b> {side}\n"
        f"<b>Entry:</b> {entry:.4f}\n"
        f"<b>Stop Loss:</b> {stop_loss:.4f}\n"
        f"<b>Take Profit:</b> {take_profit:.4f}"
    )


def format_rsi_alert(
    symbol: str,
    interval: str,
    signal: str,
    rsi6: float,
    rsi12: float,
    rsi24: float | None,
    close_time: int,
) -> str:
    """Format RSI oversold/overbought alert for Telegram (HTML). close_time is Unix ms."""
    r24 = f"{rsi24:.1f}" if rsi24 is not None else "N/A"
    dt = datetime.fromtimestamp(close_time / 1000.0, tz=timezone.utc)
    close_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"📊 <b>RSI {signal}</b> {interval}\n\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>RSI(6):</b> {rsi6:.1f}\n"
        f"<b>RSI(12):</b> {rsi12:.1f}\n"
        f"<b>RSI(24):</b> {r24}\n"
        f"<b>Candle close:</b> {close_str}"
    )

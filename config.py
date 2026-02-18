import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_key: str
    api_secret: str
    symbol: str
    quantity: float
    leverage: int
    account_balance: float
    margin_percent: float
    use_testnet: bool
    dry_run: bool
    poll_seconds: float
    move_sl_on_hold: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_breakout_chat_id: str  # Breakout/trade alerts (e.g. -5014696467)
    telegram_rsi_chat_id: str  # RSI oversold/overbought alerts (e.g. -5113087721)
    rsi_symbols: tuple[str, ...]


def _get_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> Config:
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    symbol = os.getenv("SYMBOL", "BTCUSDT").strip().upper()
    quantity = float(os.getenv("QUANTITY", "0.001"))
    leverage = int(os.getenv("LEVERAGE", "150"))
    account_balance = float(os.getenv("ACCOUNT_BALANCE", "100"))
    margin_percent = float(os.getenv("MARGIN_PERCENT", "1"))
    use_testnet = _get_bool(os.getenv("USE_TESTNET", "false"))
    dry_run = _get_bool(os.getenv("DRY_RUN", "true"))
    poll_seconds = float(os.getenv("POLL_SECONDS", "2.0"))
    move_sl_on_hold = _get_bool(os.getenv("MOVE_SL_ON_HOLD", "false"))
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    telegram_breakout_chat_id = os.getenv("TELEGRAM_BREAKOUT_CHAT_ID", "").strip()
    telegram_rsi_chat_id = os.getenv("TELEGRAM_RSI_CHAT_ID", "").strip()
    rsi_symbols_raw = os.getenv("RSI_SYMBOLS", "BTCUSDT,ETHUSDT,XAUUSDT,SOLUSDT").strip()
    rsi_symbols = tuple(s.strip().upper() for s in rsi_symbols_raw.split(",") if s.strip())

    if not api_key or not api_secret:
        if not dry_run:
            raise ValueError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in environment")

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        symbol=symbol,
        quantity=quantity,
        leverage=leverage,
        account_balance=account_balance,
        margin_percent=margin_percent,
        use_testnet=use_testnet,
        dry_run=dry_run,
        poll_seconds=poll_seconds,
        move_sl_on_hold=move_sl_on_hold,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        telegram_breakout_chat_id=telegram_breakout_chat_id,
        telegram_rsi_chat_id=telegram_rsi_chat_id,
        rsi_symbols=rsi_symbols,
    )

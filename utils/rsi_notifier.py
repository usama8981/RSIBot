"""RSI oversold/overbought notifier: checks M1, M5, M15 on each close and sends Telegram alerts."""

import logging
import time
from typing import TYPE_CHECKING

from utils.rsi import rsi, rsi_multi
from utils.telegram import format_rsi_alert, send_message

if TYPE_CHECKING:
    from exchange.binance_futures import BinanceFutures

logger = logging.getLogger(__name__)

# Step 1: Get kline data from Binance API (symbol, interval, limit).
# Equivalent to: GET .../klines?symbol=SYMBOL&interval=1m|5m|15m&limit=500
# Kline format: [open_time, open, high, low, close, volume, close_time, ...]; we use close (index 4).
# RSI is not in the API response — we compute RSI(6/12/24) from these close prices only.
RSI_KLINES_LIMIT = 500
RSI_INTERVALS = ("1m", "5m", "15m")
POLL_SECONDS = 10


def _is_oversold(interval: str, r6: float, r12: float) -> bool:
    """Per-interval oversold: M1 RSI6<20 & RSI12<30, M5 RSI6<30 & RSI12<40, M15 RSI6<40."""
    if interval == "1m":
        return r6 < 20 and r12 < 30
    if interval == "5m":
        return r6 < 30 and r12 < 40
    if interval == "15m":
        return r6 < 40
    return False


def _is_overbought(interval: str, r6: float, r12: float) -> bool:
    """Per-interval overbought: M1 RSI6>80 & RSI12>70. M5/M15: first gate only (r6>70); 1m confirmation done in _check_and_notify."""
    if interval == "1m":
        return r6 > 80 and r12 > 70
    if interval in ("5m", "15m"):
        return r6 > 70
    return False


def _get_klines_from_binance(
    exchange: "BinanceFutures", symbol: str, interval: str
) -> list[list] | None:
    """
    Step 1: Fetch klines from Binance API (symbol, interval, limit=500).
    Uses spot klines endpoint (/api/v3/klines) first per deployment requirement.
    Falls back to futures klines if spot is unavailable for a symbol.
    """
    raw: list[list] | None = None
    try:
        raw = exchange.get_spot_klines(symbol, interval, limit=RSI_KLINES_LIMIT)
    except Exception as e:
        logger.warning("RSI spot klines failed %s %s: %s", symbol, interval, e)
        try:
            raw = exchange.get_klines(symbol, interval, limit=RSI_KLINES_LIMIT)
        except Exception as fe:
            logger.warning("RSI futures klines failed %s %s: %s", symbol, interval, fe)
            return None
    if not raw or len(raw) < 25:
        logger.warning("RSI insufficient klines %s %s: got=%s", symbol, interval, len(raw) if raw else 0)
        return None
    return raw


def _closes_from_klines(exchange: "BinanceFutures", symbol: str, interval: str) -> list[float] | None:
    """Get close prices from Binance klines (each kline[4] is close)."""
    raw = _get_klines_from_binance(exchange, symbol, interval)
    if not raw:
        return None
    return [float(k[4]) for k in raw]


def _check_and_notify(
    exchange: "BinanceFutures",
    symbol: str,
    interval: str,
    close_time: int,
    bot_token: str,
    chat_id: str,
) -> None:
    """
    On one closed candle: compute RSI(6/12/24), send at most one oversold or overbought notification.
    Per-interval thresholds: M1/M5/M15 oversold and overbought rules.
    """
    closes = _closes_from_klines(exchange, symbol, interval)
    if not closes:
        return
    values = rsi_multi(closes, (6, 12, 24))
    r6 = values.get(6)
    r12 = values.get(12)
    r24 = values.get(24)
    if r6 is None or r12 is None:
        return
    logger.info("RSI values %s %s -> RSI6=%.1f RSI12=%.1f RSI24=%s", symbol, interval, r6, r12, f"{r24:.1f}" if r24 is not None else "N/A")

    if _is_oversold(interval, r6, r12):
        text = format_rsi_alert(
            symbol, f"M{interval.replace('m', '')}", "Oversold", r6, r12, r24, close_time
        )
        send_message(bot_token, chat_id, text)
        logger.info("RSI Oversold %s %s RSI6=%.1f RSI12=%.1f", symbol, interval, r6, r12)
    elif _is_overbought(interval, r6, r12):
        # For 5m and 15m: only notify if last closed 1m candle also has RSI > 80
        if interval in ("5m", "15m"):
            closes_1m = _closes_from_klines(exchange, symbol, "1m")
            if not closes_1m:
                return
            rsi6_1m = rsi(closes_1m, 6)
            if rsi6_1m is None or rsi6_1m <= 80:
                return
            logger.info("RSI 1m confirm %s: RSI6=%.1f", symbol, rsi6_1m)
        text = format_rsi_alert(
            symbol, f"M{interval.replace('m', '')}", "Overbought", r6, r12, r24, close_time
        )
        send_message(bot_token, chat_id, text)
        logger.info("RSI Overbought %s %s RSI6=%.1f RSI12=%.1f", symbol, interval, r6, r12)


def run_rsi_notifier(
    exchange: "BinanceFutures",
    symbols: tuple[str, ...],
    bot_token: str,
    chat_id: str,
    poll_seconds: float = POLL_SECONDS,
) -> None:
    """
    Run forever: on each closed candle for M1/M5/M15 per symbol, compute RSI(6/12/24).
    Oversold: M1 RSI6<20 & RSI12<30, M5 RSI6<30 & RSI12<40, M15 RSI6<40.
    Overbought: M1 RSI6>80 & RSI12>70. M5/M15: notify only if (HTF RSI>70) and (last closed 1m RSI>80).
    Only one notification per closed candle (no repeats for the same candle).
    """
    if not bot_token or not chat_id:
        logger.warning("RSI notifier: no Telegram token/chat_id, skipping")
        return
    if not symbols:
        logger.warning("RSI notifier: no symbols, skipping")
        return
    # One last_close_time per (symbol, interval) so each candle triggers at most one alert
    last_close_time: dict[tuple[str, str], int] = {}
    for sym in symbols:
        for interval in RSI_INTERVALS:
            last_close_time[(sym, interval)] = 0
    while True:
        try:
            for symbol in symbols:
                for interval in RSI_INTERVALS:
                    try:
                        kline = exchange.last_closed_kline(symbol, interval)
                        ct = kline["close_time"]
                        key = (symbol, interval)
                        if ct <= last_close_time[key]:
                            continue
                        last_close_time[key] = ct
                        _check_and_notify(
                            exchange, symbol, interval, ct, bot_token, chat_id
                        )
                    except Exception as e:
                        logger.warning("RSI check %s %s: %s", symbol, interval, e)
            time.sleep(poll_seconds)
        except Exception as e:
            logger.warning("RSI notifier loop: %s", e)
            time.sleep(poll_seconds)

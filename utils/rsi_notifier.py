"""RSI oversold/overbought notifier: checks M1, M5, M15 on each close and sends Telegram alerts."""

import logging
import time
from typing import TYPE_CHECKING

from utils.rsi import rsi_multi
from utils.telegram import format_rsi_alert, send_message

if TYPE_CHECKING:
    from exchange.binance_futures import BinanceFutures

logger = logging.getLogger(__name__)

RSI_KLINES_LIMIT = 50
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
    """Per-interval overbought: M1 RSI6>80 & RSI12>70, M5 RSI6>70, M15 RSI6>60."""
    if interval == "1m":
        return r6 > 80 and r12 > 70
    if interval == "5m":
        return r6 > 70
    if interval == "15m":
        return r6 > 60
    return False


def _closes_from_klines(exchange: "BinanceFutures", symbol: str, interval: str) -> list[float] | None:
    raw = exchange.get_klines(symbol, interval, limit=RSI_KLINES_LIMIT)
    if not raw or len(raw) < 25:
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

    if _is_oversold(interval, r6, r12):
        text = format_rsi_alert(
            symbol, f"M{interval.replace('m', '')}", "Oversold", r6, r12, r24, close_time
        )
        send_message(bot_token, chat_id, text)
        logger.info("RSI Oversold %s %s RSI6=%.1f RSI12=%.1f", symbol, interval, r6, r12)
    elif _is_overbought(interval, r6, r12):
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
    Overbought: M1 RSI6>80 & RSI12>70, M5 RSI6>70, M15 RSI6>60.
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

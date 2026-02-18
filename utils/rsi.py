"""RSI (Relative Strength Index) using Wilder smoothing — matches Binance/TradingView.

Binance API does not provide RSI; it only returns OHLCV klines. This module computes
RSI from close prices using the standard Wilder method so values match chart platforms.
"""


def rsi(closes: list[float], period: int) -> float | None:
    """
    Compute RSI for the last close using Wilder's smoothing (same as TradingView/Binance).
    First average = SMA of first `period` gains/losses; then Wilder: prev_avg * (period-1) + current, over period.
    Needs at least period+1 closes. Returns None if not enough data.
    """
    if len(closes) < period + 1:
        return None
    changes = []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        changes.append((ch if ch > 0 else 0.0, -ch if ch < 0 else 0.0))

    # First average: SMA of first `period` gains and losses
    gains = [c[0] for c in changes[:period]]
    losses = [c[1] for c in changes[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # Wilder smoothing for the rest
    for i in range(period, len(changes)):
        g, l = changes[i]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_multi(closes: list[float], periods: tuple[int, ...] = (6, 12, 24)) -> dict[int, float | None]:
    """Compute RSI for multiple periods. Returns {period: value or None}."""
    return {p: rsi(closes, p) for p in periods}

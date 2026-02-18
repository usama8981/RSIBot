"""RSI (Relative Strength Index) calculation using Wilder smoothing."""


def rsi(closes: list[float], period: int) -> float | None:
    """
    Compute RSI for the last close in the series.
    Needs at least period+1 closes. Returns None if not enough data.
    """
    if len(closes) < period + 1:
        return None
    changes = []
    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])
    # Use last `period` changes for the RSI at the last close
    use = changes[-period:]
    gains = [c if c > 0 else 0.0 for c in use]
    losses = [-c if c < 0 else 0.0 for c in use]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_multi(closes: list[float], periods: tuple[int, ...] = (6, 12, 24)) -> dict[int, float | None]:
    """Compute RSI for multiple periods. Returns {period: value or None}."""
    return {p: rsi(closes, p) for p in periods}

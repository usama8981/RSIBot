from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class TradePlan:
    side: str
    entry: float
    stop_loss: float
    take_profit: float


def build_trade_plan(range_high: float, range_low: float, entry: float, side: str) -> TradePlan:
    """Build entry plan: SL = opposite side of 15m range, TP = 2R."""
    if side == "LONG":
        stop_loss = range_low
        take_profit = entry + 2 * (entry - stop_loss)
    else:
        stop_loss = range_high
        take_profit = entry - 2 * (stop_loss - entry)

    return TradePlan(
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def hold_or_exit_on_15m(
    side: str,
    range_high: float,
    range_low: float,
    fifteen_m_close: float,
    fifteen_m_high: float,
    fifteen_m_low: float,
) -> Tuple[bool, Optional[float]]:
    """
    On each 15m close: decide HOLD vs EXIT and optional new SL.
    Returns (should_hold, new_sl or None).
    - Long: HOLD if 15m_close > Previous_RangeHigh; else EXIT. When holding, new_sl = new 15m low.
    - Short: HOLD if 15m_close < Previous_RangeLow; else EXIT. When holding, new_sl = new 15m high.
    """
    if side == "LONG":
        should_hold = fifteen_m_close > range_high
        new_sl = fifteen_m_low if should_hold else None
        return should_hold, new_sl
    else:
        should_hold = fifteen_m_close < range_low
        new_sl = fifteen_m_high if should_hold else None
        return should_hold, new_sl

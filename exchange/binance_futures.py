import time
from typing import Optional

from binance.client import Client


class BinanceFutures:
    def __init__(self, api_key: str, api_secret: str, use_testnet: bool = False):
        self.client = Client(api_key, api_secret, testnet=use_testnet)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def get_klines(self, symbol: str, interval: str, limit: int = 2):
        """Fetch klines from Binance API (symbol, interval, limit). Same as GET .../klines?symbol=...&interval=...&limit=..."""
        return self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)

    def get_position_amt(self, symbol: str) -> float:
        positions = self.client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos["symbol"] == symbol:
                return float(pos["positionAmt"])
        return 0.0

    def place_market_order(self, symbol: str, side: str, quantity: float):
        return self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
        )

    def place_stop_market(self, symbol: str, side: str, stop_price: float, quantity: float):
        return self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type="STOP_MARKET",
            stopPrice=stop_price,
            closePosition="false",
            quantity=quantity,
            timeInForce="GTC",
            workingType="CONTRACT_PRICE",
        )

    def place_take_profit_market(self, symbol: str, side: str, stop_price: float, quantity: float):
        return self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=stop_price,
            closePosition="false",
            quantity=quantity,
            timeInForce="GTC",
            workingType="CONTRACT_PRICE",
        )

    def cancel_all_orders(self, symbol: str):
        return self.client.futures_cancel_all_open_orders(symbol=symbol)

    @staticmethod
    def _parse_kline(kline):
        return {
            "open_time": int(kline[0]),
            "open": float(kline[1]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "close": float(kline[4]),
            "close_time": int(kline[6]),
        }

    def last_closed_kline(self, symbol: str, interval: str):
        klines = self.get_klines(symbol, interval, limit=2)
        return self._parse_kline(klines[-2])

    def latest_kline(self, symbol: str, interval: str):
        klines = self.get_klines(symbol, interval, limit=1)
        return self._parse_kline(klines[-1])

    def wait_for_new_closed_kline(
        self,
        symbol: str,
        interval: str,
        last_close_time: Optional[int],
        poll_seconds: float,
    ):
        while True:
            kline = self.last_closed_kline(symbol, interval)
            if last_close_time is None or kline["close_time"] > last_close_time:
                return kline
            time.sleep(poll_seconds)

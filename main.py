import logging
import threading

from dotenv import load_dotenv

from config import load_config
from exchange.binance_futures import BinanceFutures
from strategy.simple_strategy import build_trade_plan, hold_or_exit_on_15m
from utils.logger import setup_logger
from utils.rsi_notifier import run_rsi_notifier
from utils.telegram import TelegramLogHandler, format_trade_alert, send_message


def _side_to_binance(side: str) -> str:
    return "BUY" if side == "LONG" else "SELL"


def _opposite_side(side: str) -> str:
    return "SELL" if side == "BUY" else "BUY"


def _in_position(position_amt: float) -> bool:
    return abs(position_amt) > 0


def _calc_sim_qty(entry_price: float, balance: float, leverage: int, margin_percent: float) -> float:
    margin = balance * (margin_percent / 100.0)
    notional = margin * leverage
    return notional / entry_price


def main():
    load_dotenv()
    config = load_config()
    logger = setup_logger()

    if config.telegram_bot_token and config.telegram_chat_id:
        handler = TelegramLogHandler(config.telegram_bot_token, config.telegram_chat_id)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s - %(message)s", datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)

    exchange = BinanceFutures(config.api_key, config.api_secret, config.use_testnet)
    if not config.dry_run:
        exchange.set_leverage(config.symbol, config.leverage)

    logger.info("Starting bot for %s (dry_run=%s)", config.symbol, config.dry_run)

    rsi_chat_id = config.telegram_rsi_chat_id or config.telegram_chat_id
    if config.telegram_bot_token and rsi_chat_id and config.rsi_symbols:
        rsi_thread = threading.Thread(
            target=run_rsi_notifier,
            args=(exchange, config.rsi_symbols, config.telegram_bot_token, rsi_chat_id),
            kwargs={"poll_seconds": max(10, config.poll_seconds)},
            daemon=True,
        )
        rsi_thread.start()
        logger.info("RSI notifier started (M1, M5, M15) for %s", ", ".join(config.rsi_symbols))

    last_15m_close_time = None

    while True:
        last_closed_15m = exchange.wait_for_new_closed_kline(
            config.symbol,
            "15m",
            last_15m_close_time,
            config.poll_seconds,
        )
        last_15m_close_time = last_closed_15m["close_time"]
        range_high = last_closed_15m["high"]
        range_low = last_closed_15m["low"]
        logger.info(
            "New 15m close. range_high=%.4f range_low=%.4f",
            range_high,
            range_low,
        )

        active_15m = exchange.latest_kline(config.symbol, "15m")
        active_15m_open = active_15m["open_time"]

        # WHILE current 15m candle is active: wait for 1m close, check breakout
        entry_plan = None
        last_1m_close_time = last_15m_close_time
        while True:
            last_closed_1m = exchange.wait_for_new_closed_kline(
                config.symbol,
                "1m",
                last_1m_close_time,
                config.poll_seconds,
            )
            last_1m_close_time = last_closed_1m["close_time"]
            close_price = last_closed_1m["close"]

            active_check = exchange.latest_kline(config.symbol, "15m")
            if active_check["open_time"] != active_15m_open:
                logger.info("15m candle rolled without breakout, waiting for next setup.")
                break

            if close_price > range_high:
                entry_plan = build_trade_plan(range_high, range_low, close_price, "LONG")
                break
            if close_price < range_low:
                entry_plan = build_trade_plan(range_high, range_low, close_price, "SHORT")
                break

        if entry_plan is None:
            continue

        side = _side_to_binance(entry_plan.side)
        sim_qty = _calc_sim_qty(
            entry_plan.entry,
            config.account_balance,
            config.leverage,
            config.margin_percent,
        )
        logger.info(
            "Entry signal %s at %.4f SL %.4f TP %.4f (sim_qty=%.6f)",
            entry_plan.side,
            entry_plan.entry,
            entry_plan.stop_loss,
            entry_plan.take_profit,
            sim_qty,
        )

        if config.telegram_bot_token:
            breakout_chat_id = config.telegram_breakout_chat_id or config.telegram_chat_id
            if breakout_chat_id:
                text = format_trade_alert(
                    config.symbol,
                    entry_plan.side,
                    entry_plan.entry,
                    entry_plan.stop_loss,
                    entry_plan.take_profit,
                    dry_run=config.dry_run,
                )
                send_message(config.telegram_bot_token, breakout_chat_id, text)

        if not config.dry_run:
            exchange.cancel_all_orders(config.symbol)
            exchange.place_market_order(config.symbol, side, config.quantity)
            exchange.place_stop_market(
                config.symbol,
                _opposite_side(side),
                entry_plan.stop_loss,
                config.quantity,
            )
            exchange.place_take_profit_market(
                config.symbol,
                _opposite_side(side),
                entry_plan.take_profit,
                config.quantity,
            )

        # AFTER trade entry: on every 15m close, HOLD or EXIT (and optionally move SL)
        current_sl = entry_plan.stop_loss
        position_15m_close_time = last_15m_close_time

        while True:
            last_closed_15m = exchange.wait_for_new_closed_kline(
                config.symbol,
                "15m",
                position_15m_close_time,
                config.poll_seconds,
            )
            position_15m_close_time = last_closed_15m["close_time"]
            fifteen_m_close = last_closed_15m["close"]
            fifteen_m_high = last_closed_15m["high"]
            fifteen_m_low = last_closed_15m["low"]

            if not config.dry_run:
                position_amt = exchange.get_position_amt(config.symbol)
                if not _in_position(position_amt):
                    logger.info("Position closed (TP/SL). Returning to setup loop.")
                    break
            else:
                position_amt = config.quantity

            should_hold, new_sl = hold_or_exit_on_15m(
                entry_plan.side,
                range_high,
                range_low,
                fifteen_m_close,
                fifteen_m_high,
                fifteen_m_low,
            )

            if not should_hold:
                logger.info(
                    "15m close %.4f fails hold (range H=%.4f L=%.4f). Exiting %s.",
                    fifteen_m_close,
                    range_high,
                    range_low,
                    entry_plan.side,
                )
                if not config.dry_run:
                    exchange.cancel_all_orders(config.symbol)
                    exchange.place_market_order(
                        config.symbol,
                        _opposite_side(side),
                        abs(position_amt),
                    )
                break

            logger.info(
                "15m close %.4f holds %s (range H=%.4f L=%.4f). Keeping position.",
                fifteen_m_close,
                entry_plan.side,
                range_high,
                range_low,
            )

            # Optional: move SL to BE or new 15m low/high (only tighten)
            if config.move_sl_on_hold and new_sl is not None:
                tighten = (
                    entry_plan.side == "LONG" and new_sl > current_sl
                ) or (
                    entry_plan.side == "SHORT" and new_sl < current_sl
                )
                if tighten:
                    current_sl = new_sl
                    logger.info("Moving SL to %.4f", current_sl)
                    if not config.dry_run:
                        exchange.cancel_all_orders(config.symbol)
                        exchange.place_stop_market(
                            config.symbol,
                            _opposite_side(side),
                            current_sl,
                            config.quantity,
                        )
                        exchange.place_take_profit_market(
                            config.symbol,
                            _opposite_side(side),
                            entry_plan.take_profit,
                            config.quantity,
                        )

        # After position loop, sync so next outer iteration waits for next 15m
        last_15m_close_time = position_15m_close_time


if __name__ == "__main__":
    main()

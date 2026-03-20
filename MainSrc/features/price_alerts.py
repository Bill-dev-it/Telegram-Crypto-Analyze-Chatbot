"""
features/price_alerts.py
─────────────────────────
Price alert system — users set target prices, bot notifies them.

Storage: JSON file (no database needed)
Alert types:
  - ABOVE: notify when price goes above target
  - BELOW: notify when price goes below target

Usage from main.py:
    from features.price_alerts import AlertManager, format_alert_message
    alert_manager = AlertManager()
    # then use in handlers + start background task
"""

import os
import json
import asyncio
import time
from dataclasses import dataclass, asdict
from typing import Optional
import requests


ALERTS_FILE = "data/price_alerts.json"


@dataclass
class PriceAlert:
    user_id:    int
    chat_id:    int
    symbol:     str        # e.g. "BTC", "ETH"
    target:     float      # target price in USD
    direction:  str        # "above" or "below"
    created_at: float      # unix timestamp
    alert_id:   str        # unique id


class AlertManager:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.alerts: list[PriceAlert] = []
        self._load()

    def _load(self):
        try:
            with open(ALERTS_FILE, "r") as f:
                raw = json.load(f)
                self.alerts = [PriceAlert(**a) for a in raw]
        except (FileNotFoundError, json.JSONDecodeError):
            self.alerts = []

    def _save(self):
        with open(ALERTS_FILE, "w") as f:
            json.dump([asdict(a) for a in self.alerts], f, indent=2)

    def add_alert(self, user_id: int, chat_id: int, symbol: str,
                  target: float, direction: str) -> PriceAlert:
        alert = PriceAlert(
            user_id=user_id,
            chat_id=chat_id,
            symbol=symbol.upper(),
            target=target,
            direction=direction,
            created_at=time.time(),
            alert_id=f"{user_id}_{symbol}_{int(time.time())}"
        )
        self.alerts.append(alert)
        self._save()
        return alert

    def remove_alert(self, user_id: int, alert_id: str) -> bool:
        before = len(self.alerts)
        self.alerts = [
            a for a in self.alerts
            if not (a.user_id == user_id and a.alert_id == alert_id)
        ]
        if len(self.alerts) < before:
            self._save()
            return True
        return False

    def get_user_alerts(self, user_id: int) -> list[PriceAlert]:
        return [a for a in self.alerts if a.user_id == user_id]

    def clear_user_alerts(self, user_id: int):
        self.alerts = [a for a in self.alerts if a.user_id != user_id]
        self._save()

    def pop_triggered(self, prices: dict[str, float]) -> list[PriceAlert]:
        """
        Check all alerts against current prices.
        Returns triggered alerts and removes them from storage.
        prices = {"BTC": 65000.0, "ETH": 3200.0, ...}
        """
        triggered = []
        remaining = []
        for alert in self.alerts:
            price = prices.get(alert.symbol.upper())
            if price is None:
                remaining.append(alert)
                continue
            hit = (
                (alert.direction == "above" and price >= alert.target) or
                (alert.direction == "below" and price <= alert.target)
            )
            if hit:
                triggered.append(alert)
            else:
                remaining.append(alert)
        if triggered:
            self.alerts = remaining
            self._save()
        return triggered


def get_current_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of symbols via Binance."""
    prices = {}
    for symbol in symbols:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            prices[symbol.upper()] = float(r.json()["price"])
        except Exception:
            # fallback: CoinGecko
            try:
                common = {
                    "BTC": "bitcoin", "ETH": "ethereum",
                    "SOL": "solana",  "BNB": "binancecoin",
                    "DOGE": "dogecoin",
                }
                cg_id = common.get(symbol.upper(), symbol.lower())
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
                r = requests.get(url, timeout=5)
                data = r.json().get(cg_id, {})
                if "usd" in data:
                    prices[symbol.upper()] = float(data["usd"])
            except Exception:
                pass
    return prices


def format_alert_message(alert: PriceAlert, current_price: float) -> str:
    arrow = "📈" if alert.direction == "above" else "📉"
    return (
        f"🔔 *Price Alert Triggered!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{arrow} *{alert.symbol}* hit your target!\n\n"
        f"🎯 Target:  *${alert.target:,.2f}*\n"
        f"💵 Current: *${current_price:,.2f}*\n"
        f"📌 Condition: price went *{alert.direction}* target\n\n"
        f"⚠️ _Not financial advice. Always DYOR._"
    )


async def alert_polling_loop(bot, alert_manager: AlertManager, interval: int = 60):
    """
    Background task — runs forever, checks prices every `interval` seconds.
    Start this in main() with: asyncio.create_task(alert_polling_loop(app.bot, alert_manager))
    """
    print("🔔 Price alert polling started...")
    while True:
        try:
            if alert_manager.alerts:
                # collect unique symbols
                symbols = list({a.symbol for a in alert_manager.alerts})
                prices  = get_current_prices(symbols)
                triggered = alert_manager.pop_triggered(prices)
                for alert in triggered:
                    current = prices.get(alert.symbol, alert.target)
                    msg = format_alert_message(alert, current)
                    try:
                        await bot.send_message(
                            chat_id=alert.chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print(f"[alert] Failed to send to {alert.chat_id}: {e}")
        except Exception as e:
            print(f"[alert_loop] Error: {e}")

        await asyncio.sleep(interval)
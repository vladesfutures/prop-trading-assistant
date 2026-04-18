"""
prop_risk.py — Stateful prop firm risk monitor for ES/NQ futures.

Tracks daily PnL, trailing drawdown, consecutive losses, trade count,
and cooldown state across a live trading session. Call record_trade()
after every completed trade to keep state current.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime, date


class RiskStatus(str, Enum):
    GREEN = "GREEN"       # All limits healthy, trade normally
    YELLOW = "YELLOW"     # Approaching a limit, reduce size
    RED = "RED"           # At or past a limit, no new trades
    LOCKOUT = "LOCKOUT"   # Hard stop for the day


@dataclass
class PropLimits:
    """Define your prop firm's specific account rules here."""
    account_size: float = 50000.0
    daily_loss_limit: float = 1000.0
    trailing_drawdown_cap: float = 2000.0
    max_contracts: int = 2
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 5
    yellow_zone_pct: float = 0.70
    cooldown_after_max_losses: bool = True


@dataclass
class TradeRecord:
    """A completed trade outcome."""
    trade_id: int
    symbol: str
    side: str
    entry: float
    exit: float
    contracts: int
    pnl: float
    timestamp: datetime = field(default_factory=datetime.now)
    setup_tag: str = ""
    rule_break: bool = False
    notes: str = ""


@dataclass
class PropRiskMonitor:
    """
    Stateful risk monitor. Instantiate once per session and call
    record_trade() after each completed trade.
    """
    limits: PropLimits = field(default_factory=PropLimits)
    session_date: date = field(default_factory=date.today)

    realized_pnl: float = 0.0
    peak_pnl: float = 0.0
    trailing_drawdown_used: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    trades_today: int = 0
    locked_out: bool = False
    cooldown_active: bool = False
    trade_log: List[TradeRecord] = field(default_factory=list)

    _trade_counter: int = field(default=0, repr=False)

    def record_trade(self, symbol: str, side: str, entry: float, exit: float,
                     contracts: int, setup_tag: str = "", rule_break: bool = False,
                     notes: str = "") -> TradeRecord:
        """Record a completed trade and update all risk state."""
        point_value = {"ES": 50.0, "MES": 5.0, "NQ": 20.0, "MNQ": 2.0}
        pv = point_value.get(symbol.upper(), 50.0)

        if side.upper() == "LONG":
            pnl = (exit - entry) * contracts * pv
        else:
            pnl = (entry - exit) * contracts * pv

        self._trade_counter += 1
        record = TradeRecord(
            trade_id=self._trade_counter,
            symbol=symbol.upper(),
            side=side.upper(),
            entry=entry,
            exit=exit,
            contracts=contracts,
            pnl=round(pnl, 2),
            setup_tag=setup_tag,
            rule_break=rule_break,
            notes=notes,
        )
        self.trade_log.append(record)

        self.realized_pnl += pnl
        self.realized_pnl = round(self.realized_pnl, 2)
        self.trades_today += 1

        if self.realized_pnl > self.peak_pnl:
            self.peak_pnl = self.realized_pnl
        drawdown = self.peak_pnl - self.realized_pnl
        if drawdown > self.trailing_drawdown_used:
            self.trailing_drawdown_used = round(drawdown, 2)

        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        elif pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0

        self._evaluate_lockout()
        return record

    def _evaluate_lockout(self):
        lim = self.limits
        if self.realized_pnl <= -lim.daily_loss_limit:
            self.locked_out = True
            return
        if self.trailing_drawdown_used >= lim.trailing_drawdown_cap:
            self.locked_out = True
            return
        if lim.cooldown_after_max_losses and self.consecutive_losses >= lim.max_consecutive_losses:
            self.cooldown_active = True
        if self.trades_today >= lim.max_trades_per_day:
            self.locked_out = True

    def status(self) -> RiskStatus:
        """Return current overall risk status."""
        if self.locked_out:
            return RiskStatus.LOCKOUT
        if self.cooldown_active:
            return RiskStatus.RED
        lim = self.limits
        yellow = lim.yellow_zone_pct
        daily_loss_pct = abs(min(self.realized_pnl, 0)) / lim.daily_loss_limit
        dd_pct = self.trailing_drawdown_used / lim.trailing_drawdown_cap
        loss_streak_pct = self.consecutive_losses / lim.max_consecutive_losses
        trade_count_pct = self.trades_today / lim.max_trades_per_day
        if any(v >= 1.0 for v in [daily_loss_pct, dd_pct, loss_streak_pct, trade_count_pct]):
            return RiskStatus.RED
        if any(v >= yellow for v in [daily_loss_pct, dd_pct, loss_streak_pct, trade_count_pct]):
            return RiskStatus.YELLOW
        return RiskStatus.GREEN

    def remaining_daily_loss_buffer(self) -> float:
        return round(self.limits.daily_loss_limit + min(self.realized_pnl, 0), 2)

    def remaining_drawdown_buffer(self) -> float:
        return round(self.limits.trailing_drawdown_cap - self.trailing_drawdown_used, 2)

    def max_contracts_now(self, risk_per_contract: float) -> int:
        """Return max contracts allowed given current risk state."""
        if self.locked_out or self.cooldown_active:
            return 0
        buffer = min(self.remaining_daily_loss_buffer(), self.limits.daily_loss_limit)
        size_by_buffer = max(int(buffer // risk_per_contract), 0) if risk_per_contract > 0 else 0
        return min(self.limits.max_contracts, size_by_buffer)

    def reset_cooldown(self):
        """Manually clear the cooldown after a deliberate break."""
        self.cooldown_active = False
        self.consecutive_losses = 0

    def summary(self) -> dict:
        return {
            "date": str(self.session_date),
            "status": self.status().value,
            "realized_pnl": self.realized_pnl,
            "peak_pnl": self.peak_pnl,
            "trailing_drawdown_used": self.trailing_drawdown_used,
            "remaining_daily_loss_buffer": self.remaining_daily_loss_buffer(),
            "remaining_drawdown_buffer": self.remaining_drawdown_buffer(),
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "trades_today": self.trades_today,
            "locked_out": self.locked_out,
            "cooldown_active": self.cooldown_active,
            "total_trades_logged": len(self.trade_log),
        }

    def print_dashboard(self):
        s = self.summary()
        lim = self.limits
        print("\n========== PROP RISK MONITOR ==========")
        print(f"  Date        : {s['date']}")
        print(f"  Status      : {s['status']}")
        print(f"  PnL today   : ${s['realized_pnl']:+.2f}  (peak: ${s['peak_pnl']:+.2f})")
        print(f"  Daily buffer: ${s['remaining_daily_loss_buffer']:.2f} / ${lim.daily_loss_limit:.0f}")
        print(f"  DD used     : ${s['trailing_drawdown_used']:.2f} / ${lim.trailing_drawdown_cap:.0f}  (buffer: ${s['remaining_drawdown_buffer']:.2f})")
        print(f"  Streak      : {s['consecutive_losses']} loss / {s['consecutive_wins']} win")
        print(f"  Trades      : {s['trades_today']} / {lim.max_trades_per_day}")
        if s['locked_out']:
            print("  ** LOCKED OUT — no more trades today **")
        elif s['cooldown_active']:
            print("  ** COOLDOWN ACTIVE — take a break before next trade **")
        print("=======================================\n")


if __name__ == "__main__":
    limits = PropLimits(
        account_size=50000,
        daily_loss_limit=1000,
        trailing_drawdown_cap=2000,
        max_contracts=2,
        max_consecutive_losses=3,
        max_trades_per_day=5,
        yellow_zone_pct=0.70,
    )
    monitor = PropRiskMonitor(limits=limits)
    monitor.print_dashboard()
    monitor.record_trade("ES", "LONG", 5210.25, 5214.75, 1, setup_tag="trend_continuation")
    monitor.print_dashboard()
    monitor.record_trade("ES", "SHORT", 5216.00, 5218.50, 1, setup_tag="reversal")
    monitor.print_dashboard()
    monitor.record_trade("ES", "LONG", 5212.00, 5210.00, 1, setup_tag="countertrend", rule_break=True)
    monitor.print_dashboard()
    monitor.record_trade("ES", "LONG", 5208.00, 5206.00, 1, setup_tag="panic_entry", rule_break=True)
    monitor.print_dashboard()
    print("Max contracts for $100 risk/contract:", monitor.max_contracts_now(100))

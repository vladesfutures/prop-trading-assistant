#!/usr/bin/env python3
"""
run.py — CLI runner wiring decision_engine + prop_risk + journal_analysis.

Usage:
    python run.py

One entry point for a full trading session:
    1. session.check(setup)   → pre-trade gate
    2. session.record(...)    → post-trade: updates risk monitor + journal
    3. session.review()       → end-of-day coaching report
"""

from trading_assistant.decision_engine import (
    AccountRules, SessionState, TradeSetup, Decision, evaluate_trade
)
from trading_assistant.prop_risk import PropLimits, PropRiskMonitor, RiskStatus
from trading_assistant.journal_analysis import JournalCoach

from datetime import date
from typing import List, Optional


class TradingSession:
    """
    Wires all three modules into a single session object.

    Workflow:
        session = TradingSession(rules=AccountRules(...))
        result  = session.check(setup)        # pre-trade gate
        if result.decision != Decision.LOCKOUT:
            session.record(symbol, side, entry, exit, stop, target, contracts, ...)
        session.review()                      # end-of-day report + coaching
    """

    def __init__(self, rules: AccountRules = None, limits: PropLimits = None):
        self.rules  = rules  or AccountRules()
        self.limits = limits or PropLimits(
            account_size          = self.rules.account_size,
            daily_loss_limit      = self.rules.daily_loss_limit,
            trailing_drawdown_cap = self.rules.max_trailing_drawdown,
            max_contracts         = self.rules.max_contracts,
            max_consecutive_losses= self.rules.max_consecutive_losses,
            max_trades_per_day    = self.rules.max_trades_per_session,
        )
        self.risk    = PropRiskMonitor(limits=self.limits)
        self.journal = JournalCoach()
        self.today   = date.today()
        self._state  = SessionState()
        self._trade_count = 0

    # ── sync ─────────────────────────────────────────────────────────────────

    def _sync_state(self):
        """Mirror PropRiskMonitor live state into decision_engine SessionState."""
        self._state.realized_pnl_today       = self.risk.realized_pnl
        self._state.trailing_drawdown_used   = self.risk.trailing_drawdown_used
        self._state.consecutive_losses       = self.risk.consecutive_losses
        self._state.trades_taken_this_session= self.risk.trades_today
        self._state.cooldown_active          = self.risk.cooldown_active

    # ── pre-trade gate ────────────────────────────────────────────────────────

    def check(self, setup: TradeSetup):
        """Run decision_engine against current live session state and print result."""
        self._sync_state()
        result = evaluate_trade(setup, self.rules, self._state)
        _print_check(setup, result, self.risk)
        return result

    # ── post-trade record ─────────────────────────────────────────────────────

    def record(
        self,
        symbol: str, side: str,
        entry: float, exit_price: float, stop: float, target: float,
        contracts: int,
        setup_tag: str = "other",
        rule_break_tags: List[str] = None,
        emotion_tag: str = "calm",
        setup_quality: str = "A",
        trend_aligned: bool = True,
        notes: str = "",
    ) -> dict:
        """Record a completed trade — updates PropRiskMonitor AND JournalCoach."""
        # 1 — risk monitor
        self.risk.record_trade(
            symbol, side, entry, exit_price, contracts,
            setup_tag=setup_tag,
            rule_break=bool(rule_break_tags and rule_break_tags != ["none"]),
            notes=notes,
        )
        # 2 — journal
        self.journal.add_trade(
            self.today, symbol, side, entry, exit_price,
            stop, target, contracts, setup_tag,
            rule_break_tags or ["none"], emotion_tag,
            setup_quality, trend_aligned, notes,
        )
        self._trade_count += 1
        last = self.risk.trade_log[-1]
        sign = "+" if last.pnl >= 0 else ""
        print(f"  📝 Trade #{self._trade_count}  |  PnL: {sign}${last.pnl:.2f}"
              f"  |  Session: {'+' if self.risk.realized_pnl >= 0 else ''}${self.risk.realized_pnl:.2f}"
              f"  |  Risk: {self.risk.status().value}\n")
        return {
            "pnl": last.pnl,
            "session_pnl": self.risk.realized_pnl,
            "risk_status": self.risk.status().value,
            "locked_out": self.risk.locked_out,
            "cooldown": self.risk.cooldown_active,
        }

    # ── end-of-session review ─────────────────────────────────────────────────

    def review(self, export_csv: str = None) -> dict:
        """Print full session summary + coaching. Optionally export trade log to CSV."""
        summary = self.journal.session_summary(self.today)
        _print_review(summary)
        if export_csv:
            self.journal.export_csv(export_csv)
            print(f"  📄 Trade log exported → {export_csv}\n")
        return summary


# ── print helpers ─────────────────────────────────────────────────────────────

def _print_check(setup, result, risk):
    icon = {"ALLOW":"✅","ALLOW_REDUCED":"⚠️","SKIP":"🚫","LOCKOUT":"🔒"}.get(result.decision.value,"?")
    print(f"\n{'─'*50}")
    print(f"  PRE-TRADE CHECK  {setup.symbol} {setup.side}  {icon} {result.decision.value}")
    print(f"{'─'*50}")
    print(f"  Entry: {setup.entry}  Stop: {setup.stop}  Target: {setup.target}")
    print(f"  R:R  : {result.reward_to_risk}   Risk/contract: ${result.risk_per_contract}")
    print(f"  Max contracts : {result.max_contracts_allowed}   Score: {result.score}/100")
    for r in result.reasons:  print(f"  → {r}")
    for w in result.warnings: print(f"  ⚠ {w}")
    print(f"  Risk status : {risk.status().value}   Daily buffer: ${risk.buf_daily()}   DD buffer: ${risk.buf_dd()}")
    print(f"{'─'*50}\n")


def _print_review(s):
    print(f"\n{'═'*50}")
    print(f"  SESSION REVIEW — {s['date']}")
    print(f"{'═'*50}")
    print(f"  Trades     : {s.get('trades',0)}  ({s.get('wins',0)}W / {s.get('losses',0)}L)")
    print(f"  Win rate   : {s.get('win_rate','n/a')}%")
    print(f"  Total PnL  : ${'+'if s.get('pnl',0)>=0 else ''}{s.get('pnl',0):.2f}")
    print(f"  Avg R      : {s.get('avg_r','n/a')}R")
    print(f"  Discipline : {s.get('discipline',0)}/100")
    print(f"  Rule breaks: {s.get('rule_breaks',0)}")
    print(f"  Best setup : {s.get('best_setup','n/a')}")
    print(f"\n  COACHING:")
    for note in s.get("coaching",[]):
        print(f"    • {note}")
    print(f"{'═'*50}\n")


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    session = TradingSession(
        rules=AccountRules(
            account_size=50000, daily_loss_limit=1000,
            max_trailing_drawdown=2000, max_contracts=2,
            risk_per_trade=150, max_consecutive_losses=3,
            max_trades_per_session=5, require_trend_alignment=True,
        )
    )

    print("\n" + "═"*50)
    print("  PROP TRADING ASSISTANT — SESSION START")
    print("═"*50)

    setup1 = TradeSetup("ES","LONG","RTH",5210.25,5208.25,5214.75,"trend_continuation",True,"A")
    r1 = session.check(setup1)
    if r1.decision != Decision.LOCKOUT:
        session.record("ES","LONG",5210.25,5214.75,5208.25,5215.25,1,"trend_continuation",["none"],"calm","A",True,"Clean trend trade")

    setup2 = TradeSetup("ES","SHORT","RTH",5216.00,5217.50,5213.00,"reversal",True,"B")
    r2 = session.check(setup2)
    if r2.decision != Decision.LOCKOUT:
        session.record("ES","SHORT",5216.00,5218.50,5217.50,5213.00,1,"reversal",["countertrend"],"frustrated","B",False,"Against trend")

    setup3 = TradeSetup("ES","LONG","RTH",5212.00,5211.25,5215.00,"pullback",True,"B")
    r3 = session.check(setup3)
    if r3.decision != Decision.LOCKOUT:
        session.record("ES","LONG",5212.00,5210.00,5211.25,5215.00,1,"pullback",["moved_stop"],"fearful","B",True,"Moved stop")

    setup4 = TradeSetup("ES","LONG","RTH",5208.00,5207.00,5211.00,"trend_continuation",True,"C")
    r4 = session.check(setup4)
    if r4.decision != Decision.LOCKOUT:
        session.record("ES","LONG",5208.00,5209.50,5207.00,5211.00,1,"trend_continuation",["revenge_trade"],"frustrated","C",True,"Revenge trade")

    setup5 = TradeSetup("ES","LONG","RTH",5211.00,5209.50,5214.50,"pullback",True,"A")
    r5 = session.check(setup5)
    if r5.decision != Decision.LOCKOUT:
        session.record("ES","LONG",5211.00,5214.00,5209.50,5214.50,1,"pullback",["early_exit"],"calm","A",True,"Closed early")

    session.review(export_csv="session_log.csv")

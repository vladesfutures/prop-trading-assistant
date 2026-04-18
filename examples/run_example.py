import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trading_assistant import (
    AccountRules,
    SessionState,
    TradeSetup,
    evaluate_trade,
)

# --- Configure your prop account rules ---
rules = AccountRules(
    account_size=50000,
    daily_loss_limit=1000,
    max_trailing_drawdown=2000,
    max_contracts=2,
    risk_per_trade=150,
    max_consecutive_losses=3,
    max_trades_per_session=5,
    require_trend_alignment=True,
    allow_countertrend_but_reduce=False,
)

# --- Today's session state (update these live as trades happen) ---
state = SessionState(
    realized_pnl_today=-250,
    trailing_drawdown_used=400,
    consecutive_losses=1,
    trades_taken_this_session=2,
    cooldown_active=False,
)

# --- Your trade setup ---
setup = TradeSetup(
    symbol="ES",
    side="LONG",
    session="RTH",
    entry=5210.25,
    stop=5208.25,
    target=5214.75,
    setup_tag="trend_continuation",
    trend_aligned=True,
    setup_quality="A",
)

# --- Evaluate ---
result = evaluate_trade(setup, rules, state)

print("\n========== PROP TRADE ASSISTANT ==========\n")
print(f"  Symbol     : {setup.symbol} {setup.side}")
print(f"  Entry      : {setup.entry}")
print(f"  Stop       : {setup.stop}")
print(f"  Target     : {setup.target}")
print()
print(f"  DECISION   : {result.decision.value}")
print(f"  Max size   : {result.max_contracts_allowed} contract(s)")
print(f"  Risk/cont  : ${result.risk_per_contract}")
print(f"  Total risk : ${result.total_risk_if_max_size}")
print(f"  R:R        : {result.reward_to_risk}")
print(f"  Score      : {result.score}/100")
print()
if result.reasons:
    for r in result.reasons:
        print(f"  >> {r}")
if result.warnings:
    for w in result.warnings:
        print(f"  !! {w}")
print()
print("==========================================\n")

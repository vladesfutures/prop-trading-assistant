# Prop Trading Assistant

A Python-based trading assistant and journal coach for prop futures traders on ES and NQ.

Built for traders using prop firm accounts with strict daily loss limits, trailing drawdown rules, and disciplined setup filters.

---

## Modules

| File | Purpose |
|---|---|
| `trading_assistant/decision_engine.py` | Core trade validator — returns ALLOW / ALLOW_REDUCED / SKIP / LOCKOUT |
| `trading_assistant/prop_risk.py` | _(coming next)_ Daily loss, trailing drawdown, lockout tracking |
| `trading_assistant/journal_analysis.py` | _(coming next)_ Post-trade review, mistake tagging, coaching output |

---

## Supported Instruments

- ES (E-mini S&P 500, $50/pt)
- MES (Micro E-mini S&P 500, $5/pt)
- NQ (E-mini Nasdaq-100, $20/pt)
- MNQ (Micro E-mini Nasdaq-100, $2/pt)

---

## Quick Start

```bash
python examples/run_example.py
```

---

## Decision Output

Each call to `evaluate_trade()` returns:

- **Decision**: `ALLOW` / `ALLOW_REDUCED` / `SKIP` / `LOCKOUT`
- **Max contracts allowed**
- **Risk per contract** (in dollars)
- **Reward-to-risk ratio**
- **Score** (0–100)
- **Reasons** and **warnings**

---

## Account Rules (configurable)

```python
AccountRules(
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
```

---

## Roadmap

- [x] Decision engine (v1)
- [ ] Prop risk monitor (daily loss, drawdown, lockout state)
- [ ] Trade logger (CSV/JSON)
- [ ] Journal analyzer (mistake patterns, discipline score)
- [ ] Coach output (session feedback)
- [ ] Simple terminal UI

---

## License

MIT — personal use, prop trading, educational purposes.

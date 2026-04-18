"""
journal_analysis.py — Post-trade journal coach for prop futures traders.

Reads completed trade logs, scores discipline, identifies recurring
mistake patterns, and produces plain-language coaching feedback
after each session or across multiple sessions.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date, datetime
from collections import Counter
import csv


SETUP_TAGS = [
    "trend_continuation", "reversal", "breakout", "pullback",
    "opening_range", "vwap_reclaim", "failed_breakdown", "other",
]

RULE_BREAK_TAGS = [
    "countertrend", "oversized", "moved_stop", "early_exit",
    "late_entry", "revenge_trade", "no_plan", "overtrading", "fomo", "none",
]

EMOTION_TAGS = [
    "calm", "rushed", "fearful", "greedy", "frustrated", "confident", "uncertain",
]


@dataclass
class JournalEntry:
    trade_id: int
    session_date: date
    symbol: str
    side: str
    entry: float
    exit: float
    stop: float
    target: float
    contracts: int
    pnl: float
    result_r: float
    setup_tag: str = "other"
    rule_break_tags: List[str] = field(default_factory=lambda: ["none"])
    emotion_tag: str = "calm"
    setup_quality: str = "A"
    trend_aligned: bool = True
    notes: str = ""


@dataclass
class SessionReport:
    session_date: date
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    total_pnl: float
    avg_win: float
    avg_loss: float
    avg_r: float
    win_rate: float
    profit_factor: float
    rule_break_count: int
    discipline_score: int
    best_setup: str
    worst_mistake: str
    coaching_notes: List[str]


class JournalCoach:

    def __init__(self):
        self.entries: List[JournalEntry] = []
        self._counter = 0

    def add_trade(
        self,
        session_date: date,
        symbol: str,
        side: str,
        entry: float,
        exit_price: float,
        stop: float,
        target: float,
        contracts: int,
        setup_tag: str = "other",
        rule_break_tags: Optional[List[str]] = None,
        emotion_tag: str = "calm",
        setup_quality: str = "A",
        trend_aligned: bool = True,
        notes: str = "",
    ) -> JournalEntry:
        point_value = {"ES": 50.0, "MES": 5.0, "NQ": 20.0, "MNQ": 2.0}
        pv = point_value.get(symbol.upper(), 50.0)
        if side.upper() == "LONG":
            pnl = (exit_price - entry) * contracts * pv
            risk_pts = entry - stop
        else:
            pnl = (entry - exit_price) * contracts * pv
            risk_pts = stop - entry
        risk_dollars = risk_pts * pv * contracts
        result_r = round(pnl / risk_dollars, 2) if risk_dollars != 0 else 0.0
        if rule_break_tags is None:
            rule_break_tags = ["none"]
        self._counter += 1
        entry_obj = JournalEntry(
            trade_id=self._counter,
            session_date=session_date,
            symbol=symbol.upper(),
            side=side.upper(),
            entry=entry,
            exit=exit_price,
            stop=stop,
            target=target,
            contracts=contracts,
            pnl=round(pnl, 2),
            result_r=result_r,
            setup_tag=setup_tag,
            rule_break_tags=rule_break_tags,
            emotion_tag=emotion_tag,
            setup_quality=setup_quality,
            trend_aligned=trend_aligned,
            notes=notes,
        )
        self.entries.append(entry_obj)
        return entry_obj

    def _entries_for_date(self, d: date) -> List[JournalEntry]:
        return [e for e in self.entries if e.session_date == d]

    def _all_rule_breaks(self, entries: List[JournalEntry]) -> List[str]:
        return [tag for e in entries for tag in e.rule_break_tags if tag != "none"]

    def _discipline_score(self, entries: List[JournalEntry]) -> int:
        if not entries:
            return 100
        total = len(entries)
        breaks = self._all_rule_breaks(entries)
        score = 100
        score -= int((len(breaks) / total) * 40)
        score -= int((sum(1 for e in entries if not e.trend_aligned) / total) * 20)
        score -= int((sum(1 for e in entries if e.setup_quality.upper() not in ("A", "B")) / total) * 20)
        return max(min(score, 100), 0)

    def _profit_factor(self, entries: List[JournalEntry]) -> float:
        gross_win = sum(e.pnl for e in entries if e.pnl > 0)
        gross_loss = abs(sum(e.pnl for e in entries if e.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 1.0
        return round(gross_win / gross_loss, 2)

    def _best_setup(self, entries: List[JournalEntry]) -> str:
        setup_pnl: Dict[str, float] = {}
        for e in entries:
            setup_pnl[e.setup_tag] = setup_pnl.get(e.setup_tag, 0) + e.pnl
        return max(setup_pnl, key=setup_pnl.get) if setup_pnl else "n/a"

    def _worst_mistake(self, entries: List[JournalEntry]) -> str:
        breaks = self._all_rule_breaks(entries)
        return Counter(breaks).most_common(1)[0][0] if breaks else "none"

    def _generate_coaching(self, entries: List[JournalEntry], score: int) -> List[str]:
        notes = []
        if not entries:
            return ["No trades logged for this session."]
        breaks = Counter(self._all_rule_breaks(entries))
        wins = [e for e in entries if e.pnl > 0]
        losses = [e for e in entries if e.pnl < 0]
        avg_win_r = sum(e.result_r for e in wins) / len(wins) if wins else 0
        avg_loss_r = sum(e.result_r for e in losses) / len(losses) if losses else 0

        if breaks.get("revenge_trade", 0) >= 2:
            notes.append("You took revenge trades. Your worst losses often follow a previous loss — walk away and reset before the next entry.")
        if breaks.get("early_exit", 0) >= 1:
            notes.append(f"You closed winners before target {breaks['early_exit']} time(s). Average win was {avg_win_r:.1f}R — let your winners breathe.")
        if breaks.get("moved_stop", 0) >= 1:
            notes.append("You moved your stop at least once. Stops exist before the trade — honour them every time.")
        if breaks.get("oversized", 0) >= 1:
            notes.append("You exceeded your max contract size. One oversized trade can erase multiple winning sessions.")
        if breaks.get("countertrend", 0) >= 2:
            notes.append("You traded against the trend more than once. Your rules say trend alignment is required — filter these out before entry.")
        if breaks.get("fomo", 0) >= 1:
            notes.append("FOMO entry detected. If you missed the entry, the trade is gone — wait for the next one.")
        if breaks.get("no_plan", 0) >= 1:
            notes.append("You entered at least one trade without a defined stop or target. No plan = no edge.")
        if breaks.get("overtrading", 0) >= 1:
            notes.append("You exceeded your daily trade limit. More trades does not mean more profit — it means more noise.")

        unaligned = sum(1 for e in entries if not e.trend_aligned)
        if unaligned > 0:
            notes.append(f"{unaligned}/{len(entries)} trades were against the higher timeframe direction. Align before entry.")
        if avg_loss_r < -1.5:
            notes.append(f"Your average loss was {avg_loss_r:.1f}R. You are either moving stops or holding losers too long.")

        if score >= 90:
            notes.append("Excellent discipline today. Your only job is to repeat this process.")
        elif score >= 70:
            notes.append("Good session with minor issues. Focus on the one mistake that cost you the most and fix it first.")
        elif score >= 50:
            notes.append("Mixed session. Review each rule break — most of your losses were avoidable.")
        else:
            notes.append("Difficult session. Stop trading for the day, review the rule breaks, and do not trade again until you know exactly what you will do differently.")
        return notes

    def session_review(self, session_date: date) -> SessionReport:
        entries = self._entries_for_date(session_date)
        if not entries:
            return SessionReport(
                session_date=session_date, total_trades=0, wins=0, losses=0,
                breakeven=0, total_pnl=0.0, avg_win=0.0, avg_loss=0.0,
                avg_r=0.0, win_rate=0.0, profit_factor=1.0,
                rule_break_count=0, discipline_score=100,
                best_setup="n/a", worst_mistake="none",
                coaching_notes=["No trades logged for this session."],
            )
        wins = [e for e in entries if e.pnl > 0]
        losses = [e for e in entries if e.pnl < 0]
        be = [e for e in entries if e.pnl == 0]
        score = self._discipline_score(entries)
        return SessionReport(
            session_date=session_date,
            total_trades=len(entries),
            wins=len(wins),
            losses=len(losses),
            breakeven=len(be),
            total_pnl=round(sum(e.pnl for e in entries), 2),
            avg_win=round(sum(e.pnl for e in wins) / len(wins), 2) if wins else 0.0,
            avg_loss=round(sum(e.pnl for e in losses) / len(losses), 2) if losses else 0.0,
            avg_r=round(sum(e.result_r for e in entries) / len(entries), 2),
            win_rate=round(len(wins) / len(entries) * 100, 1),
            profit_factor=self._profit_factor(entries),
            rule_break_count=len(self._all_rule_breaks(entries)),
            discipline_score=score,
            best_setup=self._best_setup(entries),
            worst_mistake=self._worst_mistake(entries),
            coaching_notes=self._generate_coaching(entries, score),
        )

    def print_session_report(self, session_date: date):
        r = self.session_review(session_date)
        print(f"\n{'='*46}")
        print(f"  JOURNAL COACH — {r.session_date}")
        print(f"{'='*46}")
        print(f"  Trades      : {r.total_trades}  ({r.wins}W / {r.losses}L / {r.breakeven}BE)")
        print(f"  Win rate    : {r.win_rate}%")
        print(f"  Total PnL   : ${r.total_pnl:+.2f}")
        print(f"  Avg win     : ${r.avg_win:+.2f}   Avg loss: ${r.avg_loss:+.2f}")
        print(f"  Avg R       : {r.avg_r:+.2f}R")
        print(f"  Prof. factor: {r.profit_factor}")
        print(f"  Rule breaks : {r.rule_break_count}")
        print(f"  Discipline  : {r.discipline_score}/100")
        print(f"  Best setup  : {r.best_setup}")
        print(f"  Top mistake : {r.worst_mistake}")
        print()
        print("  COACHING:")
        for note in r.coaching_notes:
            print(f"    \u2022 {note}")
        print(f"{'='*46}\n")

    def export_csv(self, filepath: str):
        if not self.entries:
            return
        keys = ["trade_id","session_date","symbol","side","entry","exit","stop",
                "target","contracts","pnl","result_r","setup_tag","rule_break_tags",
                "emotion_tag","setup_quality","trend_aligned","notes"]
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for e in self.entries:
                row = {k: getattr(e, k) for k in keys}
                row["rule_break_tags"] = "|".join(e.rule_break_tags)
                row["session_date"] = str(e.session_date)
                writer.writerow(row)


if __name__ == "__main__":
    coach = JournalCoach()
    today = date(2026, 4, 18)
    coach.add_trade(today, "ES", "LONG",  5210.25, 5214.75, 5208.25, 5216.25, 1, "trend_continuation", ["none"], "calm", "A", True, "Clean setup")
    coach.add_trade(today, "ES", "SHORT", 5216.00, 5218.50, 5217.50, 5213.00, 1, "reversal", ["countertrend"], "frustrated", "B", False, "Against trend")
    coach.add_trade(today, "ES", "LONG",  5212.00, 5210.00, 5211.25, 5215.00, 1, "pullback", ["moved_stop"], "fearful", "B", True, "Moved stop")
    coach.add_trade(today, "ES", "LONG",  5208.00, 5209.50, 5207.00, 5211.00, 1, "trend_continuation", ["revenge_trade"], "frustrated", "C", True, "Revenge trade")
    coach.add_trade(today, "ES", "LONG",  5211.00, 5214.00, 5209.50, 5214.50, 1, "pullback", ["early_exit"], "calm", "A", True, "Closed early")
    coach.print_session_report(today)
    coach.export_csv("output/trades_demo.csv")

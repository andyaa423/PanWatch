"""Event gate: scan rules often, call LLM only on meaningful changes."""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from src.platform.persistence.json_store import read_json, write_json_atomic

DEFAULT_ATR_K = 1.5
DEFAULT_HEARTBEAT_MINUTES = 120

def _path() -> str: return os.path.join(os.environ.get("DATA_DIR", "./data"), "state", "intraday_monitor_state.json")
def _num(v: Any) -> float | None:
    try: return None if v is None else float(v)
    except (TypeError, ValueError): return None
def adaptive_price_threshold(atr_pct: float | None, fixed_threshold: float, k: float = DEFAULT_ATR_K) -> float:
    return max(_num(fixed_threshold) or 0, (_num(atr_pct) or 0) * (_num(k) or DEFAULT_ATR_K))
def is_abnormal_move(change_pct: float | None, atr_pct: float | None, k: float = DEFAULT_ATR_K, fixed_threshold: float = 0) -> bool:
    return _num(change_pct) is not None and abs(_num(change_pct) or 0) >= adaptive_price_threshold(atr_pct, fixed_threshold, k)

@dataclass(frozen=True)
class EventDecision:
    should_analyze: bool
    reasons: list[str]
    snapshot: dict[str, Any]

def _score(k: dict[str, Any]) -> int:
    s=0; trend=str(k.get("trend") or ""); macd=str(k.get("macd_status") or ""); kdj=str(k.get("kdj_status") or "")
    s += 2 if "多头" in trend else -2 if "空头" in trend else 0
    s += 2 if "金叉" in macd else -2 if "死叉" in macd else 0
    s += 1 if "金叉" in kdj else -1 if "死叉" in kdj else 0
    hist=_num(k.get("macd_hist")) or 0; return s + (1 if hist>0 else -1 if hist<0 else 0)
def _volume(k: dict[str, Any], score: int) -> str:
    obv,mfi=_num(k.get("obv_change")),_num(k.get("mfi"))
    if obv is None or mfi is None or not score:return "unavailable"
    bull=score>0; same=(obv>0 and mfi>=55) if bull else (obv<0 and mfi<=45); opposite=(obv<0 or mfi<=45) if bull else (obv>0 or mfi>=55)
    return "confirm" if same else "warn" if opposite else "neutral"
def _snap(change_pct: float | None, volume_ratio: float | None, k: dict[str, Any]) -> dict[str, Any]:
    score=_score(k); price,sup,res=_num(k.get("last_close")),_num(k.get("support")),_num(k.get("resistance"))
    zone="above_resistance" if price and res and price>=res else "below_support" if price and sup and price<sup else "inside_range"
    return {"trend_score":score,"volume_state":_volume(k,score),"price_zone":zone,"change_pct":_num(change_pct),"volume_ratio":_num(volume_ratio)}
def _time(v: Any) -> datetime | None:
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except (TypeError,ValueError):return None

def check_trigger(*,symbol:str,change_pct:float|None,volume_ratio:float|None,kline_summary:dict|None,price_threshold:float,volume_threshold:float,heartbeat_minutes:int=DEFAULT_HEARTBEAT_MINUTES,score_delta:int=2,now:datetime|None=None)->EventDecision:
    now=now or datetime.now(timezone.utc); state=read_json(_path(),default={}); rec=state.get(symbol,{}) if isinstance(state,dict) else {}; snap=_snap(change_pct,volume_ratio,kline_summary or {}); prior=rec.get("last_analysis_snapshot")
    reasons=[]
    if not isinstance(prior,dict): reasons.append("first_analysis")
    else:
        if abs(snap["trend_score"]-prior.get("trend_score",0))>=score_delta: reasons.append("trend_score_changed")
        if snap["volume_state"]!=prior.get("volume_state"): reasons.append("volume_confirmation_changed")
        if snap["price_zone"]!=prior.get("price_zone"): reasons.append("support_resistance_crossed")
        last=_time(rec.get("last_analysis_at"))
        if last is None or (now-last).total_seconds()>=heartbeat_minutes*60: reasons.append("heartbeat")
    cp,vr=_num(change_pct),_num(volume_ratio)
    if cp is not None and abs(cp)>=price_threshold: reasons.append("price_threshold")
    if vr is not None and vr>=volume_threshold: reasons.append("volume_threshold")
    return EventDecision(bool(reasons),list(dict.fromkeys(reasons)),snap)
def mark_analyzed(symbol:str,snapshot:dict[str,Any],now:datetime|None=None)->None:
    state=read_json(_path(),default={}); state=state if isinstance(state,dict) else {}; rec=state.get(symbol,{}); rec.update(last_analysis_at=(now or datetime.now(timezone.utc)).isoformat(),last_analysis_snapshot=snapshot); state[symbol]=rec; write_json_atomic(_path(),state)
def check_and_update(**kwargs:Any)->EventDecision:return check_trigger(**kwargs)

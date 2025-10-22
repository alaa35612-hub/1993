#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ماسح Binance USDT‑M Futures عبر CCXT، مع كاشف مضمّن لـ:
- Golden Zone (0.618–0.786) على أحدث ساق سعرية قابلة للاعتماد
- CHOCH (Change of Character)
- BOS (Break of Structure)
- FVG (Fair Value Gap)
- OB (Order Block)

السياسات الصارمة:
- لا منطق تنبيهات إطلاقًا.
- لا مخرجات لأي حدث/منطقة خارج نافذة آخر N=5 شموع.
- المخرجات JSON/Markdown فقط.

إعدادات:
--symbols, --limit, --timeframe, --bars, --max-age-bars, --smc-path, --out-json, --out-md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import ccxt  # type: ignore
except Exception:
    print("[ERROR] ccxt غير مثبت. ثبّت بالحزمة: pip install ccxt", file=sys.stderr)
    sys.exit(1)


class _SMCProxy:
    """Proxy loader for optional SmartMoneyAlgoProE5 module."""

    def __init__(self, base_timeframe: str, module_path: Optional[str]) -> None:
        self.base_timeframe = base_timeframe
        self._cls = None
        if module_path:
            path = pathlib.Path(module_path)
            if path.exists():
                spec = importlib.util.spec_from_file_location("_smc_mod", str(path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[attr-defined]
                    self._cls = getattr(module, "SmartMoneyAlgoProE5", None)

    def available(self) -> bool:
        return self._cls is not None

    def run(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        if not self.available():
            return {}
        smc = self._cls(base_timeframe=self.base_timeframe)  # type: ignore[call-arg]
        smc.process(candles)
        labels = [
            {"time": int(lbl.x), "text": lbl.text, "price": float(lbl.y)}
            for lbl in getattr(smc, "labels", [])
        ]
        boxes = [
            {
                "left": int(box.left),
                "right": int(box.right),
                "top": float(box.top),
                "bottom": float(box.bottom),
                "text": box.text,
            }
            for box in getattr(smc, "boxes", [])
        ]
        return {"labels": labels, "boxes": boxes}


_DEF_TIMEFRAME = "15m"
_DEF_LIMIT_SYMBOLS = 30
_DEF_BARS = 300
_DEF_MAX_AGE_BARS = 5


def _mk_exchange() -> Any:
    return ccxt.binanceusdm({"enableRateLimit": True})


def _pick_symbols(exchange: Any, limit: int, explicit: Optional[str]) -> List[str]:
    if explicit:
        return [symbol.strip() for symbol in explicit.split(",") if symbol.strip()]
    markets = exchange.load_markets()
    usdtm = [m for m in markets.values() if m.get("linear") and m.get("quote") == "USDT"]
    try:
        tickers = exchange.fetch_tickers()
    except Exception:
        tickers = {}

    def _volume(symbol: str) -> float:
        ticker = tickers.get(symbol) or {}
        if isinstance(ticker.get("quoteVolume"), (int, float)):
            return float(ticker["quoteVolume"])
        info = ticker.get("info") or {}
        for key in ("quoteVolume", "volume"):
            value = info.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for key in ("baseVolume", "volume"):
            value = ticker.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    sorted_markets = sorted(
        (market for market in usdtm),
        key=lambda market: _volume(market["symbol"]),
        reverse=True,
    )
    return [market["symbol"] for market in sorted_markets[:limit]]


def _fetch_ohlcv(exchange: Any, symbol: str, timeframe: str, bars: int) -> List[List[float]]:
    return exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=bars)


def _to_candles(ohlcv: List[List[float]]) -> List[Dict[str, float]]:
    return [
        {
            "time": int(ts),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }
        for ts, open_, high, low, close, volume in ohlcv
    ]


def _time_of(candle: Dict[str, float]) -> int:
    return int(candle.get("time", 0))


def _last_nth_time(candles: List[Dict[str, float]], n: int) -> int:
    if not candles:
        return 0
    index = max(0, len(candles) - n)
    return _time_of(candles[index])


def pivots(candles: List[Dict[str, float]], lookback: int = 1) -> Tuple[List[int], List[int]]:
    highs: List[int] = []
    lows: List[int] = []
    for idx in range(lookback, len(candles) - lookback):
        if all(
            candles[idx]["high"] > candles[idx - offset]["high"]
            for offset in range(1, lookback + 1)
        ) and all(
            candles[idx]["high"] > candles[idx + offset]["high"]
            for offset in range(1, lookback + 1)
        ):
            highs.append(idx)
        if all(
            candles[idx]["low"] < candles[idx - offset]["low"]
            for offset in range(1, lookback + 1)
        ) and all(
            candles[idx]["low"] < candles[idx + offset]["low"]
            for offset in range(1, lookback + 1)
        ):
            lows.append(idx)
    return highs, lows


def last_structure_direction(
    candles: List[Dict[str, float]], highs: List[int], lows: List[int]
) -> str:
    if not highs or not lows:
        return "none"
    last_high = highs[-1]
    last_low = lows[-1]
    if _time_of(candles[last_high]) > _time_of(candles[last_low]):
        if len(highs) >= 2 and candles[highs[-1]]["high"] > candles[highs[-2]]["high"]:
            return "bull"
    else:
        if len(lows) >= 2 and candles[lows[-1]]["low"] < candles[lows[-2]]["low"]:
            return "bear"
    return "none"


def detect_fvg(candles: List[Dict[str, float]], gate_ts: int) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    for idx in range(1, len(candles) - 1):
        if _time_of(candles[idx + 1]) < gate_ts or _time_of(candles[idx - 1]) < gate_ts:
            continue
        if candles[idx + 1]["low"] > candles[idx - 1]["high"]:
            boxes.append(
                {
                    "left": _time_of(candles[idx - 1]),
                    "right": _time_of(candles[idx + 1]),
                    "bottom": candles[idx - 1]["high"],
                    "top": candles[idx + 1]["low"],
                    "text": "FVG↑",
                }
            )
        if candles[idx + 1]["high"] < candles[idx - 1]["low"]:
            boxes.append(
                {
                    "left": _time_of(candles[idx - 1]),
                    "right": _time_of(candles[idx + 1]),
                    "bottom": candles[idx + 1]["high"],
                    "top": candles[idx - 1]["low"],
                    "text": "FVG↓",
                }
            )
    return boxes


def detect_bos_choch(
    candles: List[Dict[str, float]],
    highs: List[int],
    lows: List[int],
    gate_ts: int,
) -> List[Dict[str, Any]]:
    labels: List[Dict[str, Any]] = []
    if not highs or not lows:
        return labels
    direction = last_structure_direction(candles, highs, lows)
    last_high = highs[-1]
    last_low = lows[-1]
    level_high = candles[last_high]["high"]
    level_low = candles[last_low]["low"]
    for idx in range(max(1, len(candles) - 10), len(candles)):
        if _time_of(candles[idx]) < gate_ts:
            continue
        close_value = candles[idx]["close"]
        if direction == "bull" and close_value > level_high:
            labels.append({"time": _time_of(candles[idx]), "text": "BOS↑", "price": close_value})
        if direction == "bear" and close_value < level_low:
            labels.append({"time": _time_of(candles[idx]), "text": "BOS↓", "price": close_value})
        if direction == "bull" and close_value < level_low:
            labels.append({"time": _time_of(candles[idx]), "text": "CHOCH↓", "price": close_value})
        if direction == "bear" and close_value > level_high:
            labels.append({"time": _time_of(candles[idx]), "text": "CHOCH↑", "price": close_value})
    return labels


def detect_ob(
    candles: List[Dict[str, float]],
    bos_labels: List[Dict[str, Any]],
    gate_ts: int,
    lookback: int = 10,
) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    for label in bos_labels:
        timestamp = label["time"]
        if timestamp < gate_ts:
            continue
        candle_index = next(
            (idx for idx in range(len(candles) - 1, -1, -1) if _time_of(candles[idx]) <= timestamp),
            len(candles) - 1,
        )
        sign = 1 if "↑" in label["text"] else -1
        for idx in range(max(0, candle_index - lookback), candle_index):
            if _time_of(candles[idx]) < gate_ts:
                continue
            bullish = candles[idx]["close"] > candles[idx]["open"]
            if (sign == 1 and not bullish) or (sign == -1 and bullish):
                bottom = min(candles[idx]["open"], candles[idx]["close"])
                top = max(candles[idx]["open"], candles[idx]["close"])
                boxes.append(
                    {
                        "left": _time_of(candles[idx]),
                        "right": timestamp,
                        "bottom": bottom,
                        "top": top,
                        "text": "OB↑" if sign == 1 else "OB↓",
                    }
                )
                break
    return boxes


def detect_golden_zone(
    candles: List[Dict[str, float]],
    highs: List[int],
    lows: List[int],
    gate_ts: int,
) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    if not highs or not lows:
        return boxes
    last_high_index = highs[-1]
    last_low_index = lows[-1]
    last_high_time = _time_of(candles[last_high_index])
    last_low_time = _time_of(candles[last_low_index])
    if last_high_time >= gate_ts and last_low_time >= gate_ts:
        if last_high_time > last_low_time:
            start_candidates = [idx for idx in lows if idx < last_high_index]
            if start_candidates:
                start_index = start_candidates[-1]
                if _time_of(candles[start_index]) >= gate_ts:
                    swing_low = candles[start_index]["low"]
                    swing_high = candles[last_high_index]["high"]
                    gz_min = swing_high - 0.786 * (swing_high - swing_low)
                    gz_max = swing_high - 0.618 * (swing_high - swing_low)
                    boxes.append(
                        {
                            "left": _time_of(candles[start_index]),
                            "right": last_high_time,
                            "bottom": gz_min,
                            "top": gz_max,
                            "text": "GoldenZone↑",
                        }
                    )
        else:
            start_candidates = [idx for idx in highs if idx < last_low_index]
            if start_candidates:
                start_index = start_candidates[-1]
                if _time_of(candles[start_index]) >= gate_ts:
                    swing_high = candles[start_index]["high"]
                    swing_low = candles[last_low_index]["low"]
                    gz_min = swing_low + 0.618 * (swing_high - swing_low)
                    gz_max = swing_low + 0.786 * (swing_high - swing_low)
                    boxes.append(
                        {
                            "left": _time_of(candles[start_index]),
                            "right": last_low_time,
                            "bottom": gz_min,
                            "top": gz_max,
                            "text": "GoldenZone↓",
                        }
                    )
    return boxes


def scan_symbols(
    symbols: List[str],
    timeframe: str,
    bars: int,
    max_age_bars: int,
    smc_path: Optional[str],
) -> Dict[str, Any]:
    exchange = _mk_exchange()
    report: Dict[str, Any] = {
        "timeframe": timeframe,
        "max_age_bars": max_age_bars,
        "results": [],
    }
    proxy = _SMCProxy(base_timeframe=timeframe, module_path=smc_path)
    for symbol in symbols:
        try:
            raw = _fetch_ohlcv(exchange, symbol, timeframe, bars)
            candles = _to_candles(raw)
            if len(candles) < max_age_bars + 2:
                continue
            gate_ts = _last_nth_time(candles, max_age_bars)
            labels: List[Dict[str, Any]] = []
            boxes: List[Dict[str, Any]] = []
            parsed = proxy.run(candles) if proxy.available() else {}
            if parsed:
                labels.extend(
                    [label for label in parsed.get("labels", []) if int(label.get("time", 0)) >= gate_ts]
                )
                boxes.extend(
                    [
                        box
                        for box in parsed.get("boxes", [])
                        if int(box.get("left", 0)) >= gate_ts
                        and int(box.get("right", 0)) >= gate_ts
                    ]
                )
            highs, lows = pivots(candles, lookback=1)
            boxes.extend(detect_fvg(candles, gate_ts))
            bos_choch = detect_bos_choch(candles, highs, lows, gate_ts)
            labels.extend(bos_choch)
            boxes.extend(detect_ob(candles, bos_choch, gate_ts))
            boxes.extend(detect_golden_zone(candles, highs, lows, gate_ts))
            report["results"].append(
                {
                    "symbol": symbol,
                    "latest_close": candles[-1]["close"],
                    "events": {"labels": labels, "boxes": boxes},
                }
            )
            if getattr(exchange, "rateLimit", 0):
                time.sleep(exchange.rateLimit / 1000)
            else:
                time.sleep(0.05)
        except Exception as exc:
            report["results"].append({"symbol": symbol, "error": str(exc)})
    return report


def write_reports(report: Dict[str, Any], json_path: str, md_path: str) -> None:
    pathlib.Path(json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Scan Report — TF: {report['timeframe']} (last {report['max_age_bars']} bars)",
        "",
    ]
    for row in report["results"]:
        if "error" in row:
            lines.extend([f"## {row['symbol']}", f"**ERROR**: {row['error']}", ""])
            continue
        lines.append(f"## {row['symbol']} — close: {row['latest_close']}")
        events = row["events"]
        if events["labels"]:
            lines.append("**Labels (last window):**")
            for label in events["labels"]:
                timestamp = time.strftime(
                    "%Y-%m-%d %H:%M:%S UTC",
                    time.gmtime(int(label["time"]) / 1000),
                )
                lines.append(f"- [{timestamp}] {label['text']} @ {label['price']}")
        if events["boxes"]:
            lines.append("**Boxes/Zones (last window):**")
            for box in events["boxes"]:
                timestamp = time.strftime(
                    "%Y-%m-%d %H:%M:%S UTC",
                    time.gmtime(int(box.get("left", 0)) / 1000),
                )
                lines.append(
                    f"- [{timestamp}] {box.get('text', '')} {box.get('bottom', '?')} → {box.get('top', '?')}"
                )
        lines.append("")
    pathlib.Path(md_path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Binance USDT‑M scanner (last 5 bars only) + SMC concepts"
    )
    parser.add_argument("--symbols", type=str, default=None, help="قائمة رموز مفصولة بفواصل (اختياري)")
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEF_LIMIT_SYMBOLS,
        help="عدد الأسواق التلقائية إن لم تُحدد --symbols",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default=_DEF_TIMEFRAME,
        help="الإطار الزمني (مثال: 1m, 5m, 15m, 1h)",
    )
    parser.add_argument("--bars", type=int, default=_DEF_BARS, help="عدد الشموع المطلوب جلبها")
    parser.add_argument(
        "--max-age-bars",
        type=int,
        default=_DEF_MAX_AGE_BARS,
        help="النافذة الزمنية للأحداث (افتراضي 5)",
    )
    parser.add_argument(
        "--smc-path",
        type=str,
        default=None,
        help="مسار ملف SmartMoneyAlgoProE5.py (اختياري)",
    )
    parser.add_argument("--out-json", type=str, default="SCAN_REPORT.json")
    parser.add_argument("--out-md", type=str, default="SCAN_REPORT.md")
    args = parser.parse_args(argv)

    exchange = _mk_exchange()
    symbols = _pick_symbols(exchange, args.limit, args.symbols)
    report = scan_symbols(symbols, args.timeframe, args.bars, args.max_age_bars, args.smc_path)
    write_reports(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {"symbols": len(symbols), "out_json": args.out_json, "out_md": args.out_md},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

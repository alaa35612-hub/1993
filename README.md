الموجّه النظامي (هندسة السياق) — إزالة الماسح القديم وإضافة ماسح Binance USDT‑M عبر CCXT

> الغرض: حذف كل أكواد الماسح القديم وجميع أنواعه وتكراراته، حذف منطق التنبيهات بالكامل، حذف منطق "أحدث الإشارات مع الأسعار"، وتركيب ماسح جديد يحلل أسواق Binance USDT‑M Futures عبر CCXT بمُدخلات قابلة للتخصيص (عدد الأسواق والإطار الزمني)، ويُخرِج أحداث/مناطق آخر ٥ شموع فقط ويتجاهل ما قبلها.




---

١) المبدأ الحاكم (M)

نعمل تحت فلسفة واحدة غير قابلة للتفاوض: الوضوح والتنفيذ الآمن. لا يُكتب ولا يُستدعى أي منطق قديم للماسح أو التنبيهات. المخرجات النهائية يجب أن تُحصر في أحدث نافذة قدرها ٥ شموع فقط لكل سوق، وما قبلها يُهمل ولا يظهر.


٢) الهوية التشغيلية (ص)

هويتك: مهندس برمجيات/مُعيد هيكلة لمشروع تداول.

مهمتك: تنظيف الريبو من آثار الماسح القديم والتنبيهات، ثم إضافة ماسح جديد عبر CCXT لأسواق Binance USDT‑M مع معاملات اختيارية.


٣) البروتوكول التنفيذي (ب)

1. التأسيس أولًا

ابحث في الشيفرة عن أي ملف/وحدة تتضمن: scanner, scan, alerts, alertcondition, console_event_log, latest signals واحذفها أو عطِّلها (انظر التصحيحات بالأسفل).

أي استدعاء لمنطق تنبيه يُستبدل بـ لا شيء.



2. تركيب ماسح جديد

أضِف ملفًا جديدًا: scanner_ccxt_binanceusdm.py (الكود أدناه).

يعتمد على CCXT لاستخراج رموز العقود الدائمة المقومة بـ USDT، ثم يجلب OHLCV للإطار الزمني المطلوب، ويُشغّل التحليل، ثم يُرشِّح النتائج إلى آخر ٥ شموع.



3. بوابة المخرجات

المخرجات تكون JSON و/أو Markdown، مُقيدة زمنيًا بآخر ٥ شموع فقط.

أي حدث/منطقة تاريخها أقدم من الشمعة الخامسة الأخيرة لا يُطبع.




٤) الأصول غير القابلة للانتهاك (أ)

لا تنبيهات: لا push/append لأي قائمة تنبيهات، ولا طباعة جمل alert.

لا ماسح قديم: لا استيراد أو استدعاء لأي وحدات Scanner Legacy.

قابلية الضبط: وسيطات CLI --symbols، --limit، --timeframe إجبارية/اختيارية كما بالكود.

السلامة الشبكية: احترم معدل الطلبات لـ CCXT. اجعل الجلب متسلسلًا أو محدود التوازي.


٥) الحصيلة/المخرجات (ح)

ملف تنفيذ مستقل scanner_ccxt_binanceusdm.py (أدناه)، مع CLI.

ملف تصحيح (patch) يُعطِّل التنبيهات ويكفكف "أحدث الإشارات" في الكود الأساسي إن وُجد.

تقرير SCAN_REPORT.json و SCAN_REPORT.md لكل تشغيل.



---

ملف جديد: scanner_ccxt_binanceusdm.py

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
import argparse, json, time, sys, pathlib, importlib.util
from typing import List, Dict, Any, Optional, Tuple

try:
    import ccxt  # type: ignore
except Exception:
    print("[ERROR] ccxt غير مثبت. ثبّت بالحزمة: pip install ccxt", file=sys.stderr)
    sys.exit(1)

# =============================
# SMC proxy (اختياري)
# =============================
class _SMCProxy:
    def __init__(self, base_timeframe: str, module_path: Optional[str]) -> None:
        self.base_timeframe = base_timeframe
        self._cls = None
        if module_path:
            p = pathlib.Path(module_path)
            if p.exists():
                spec = importlib.util.spec_from_file_location("_smc_mod", str(p))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    self._cls = getattr(mod, "SmartMoneyAlgoProE5", None)

    def available(self) -> bool:
        return self._cls is not None

    def run(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        if not self.available():
            return {}
        smc = self._cls(base_timeframe=self.base_timeframe)  # type: ignore
        smc.process(candles)
        labels = [{"time": int(lbl.x), "text": lbl.text, "price": float(lbl.y)} for lbl in getattr(smc, "labels", [])]
        boxes = [{
            "left": int(bx.left), "right": int(bx.right),
            "top": float(bx.top), "bottom": float(bx.bottom),
            "text": bx.text,
        } for bx in getattr(smc, "boxes", [])]
        return {"labels": labels, "boxes": boxes}

# =============================
# أدوات مساعدة للسعر/الشموع
# =============================
_DEF_TIMEFRAME = "15m"
_DEF_LIMIT_SYMBOLS = 30
_DEF_BARS = 300
_DEF_MAX_AGE_BARS = 5


def _mk_exchange() -> Any:
    return ccxt.binanceusdm({'enableRateLimit': True})


def _pick_symbols(ex: Any, limit: int, explicit: Optional[str]) -> List[str]:
    if explicit:
        return [s.strip() for s in explicit.split(',') if s.strip()]
    markets = ex.load_markets()
    usdtm = [m for m in markets.values() if m.get('linear') and m.get('quote') == 'USDT']
    tickers = {}
    try:
        tickers = ex.fetch_tickers()
    except Exception:
        pass
    def _vol(sym: str) -> float:
        t = tickers.get(sym) or {}
        if isinstance(t.get("quoteVolume"), (int, float)): return float(t["quoteVolume"])
        info = t.get("info") or {}
        for k in ("quoteVolume", "volume"):
            v = info.get(k)
            if isinstance(v, (int, float)): return float(v)
        for k in ("baseVolume", "volume"):
            v = t.get(k)
            if isinstance(v, (int, float)): return float(v)
        return 0.0
    usdtm_sorted = sorted((m for m in usdtm), key=lambda m: _vol(m['symbol']), reverse=True)
    return [m['symbol'] for m in usdtm_sorted[:limit]]


def _fetch_ohlcv(ex: Any, symbol: str, timeframe: str, bars: int) -> List[List[float]]:
    return ex.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=bars)


def _to_candles(ohlcv: List[List[float]]) -> List[Dict[str, float]]:
    return [{"time": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)} for t,o,h,l,c,v in ohlcv]


def _time_of(c: Dict[str, float]) -> int:
    return int(c.get("time", 0))


def _last_nth_time(candles: List[Dict[str, float]], n: int) -> int:
    if not candles: return 0
    idx = max(0, len(candles) - n)
    return _time_of(candles[idx])

# =============================
# كشف البِنى: Pivot, FVG, BOS, CHOCH, OB, Golden Zone
# =============================

def pivots(c: List[Dict[str, float]], lb: int = 1) -> Tuple[List[int], List[int]]:
    """إرجاع فهارس قمم/قيعان محلية (hi/lo) باستخدام نافذة بسيطة."""
    highs, lows = [], []
    for i in range(lb, len(c)-lb):
        if all(c[i]['high'] > c[i-k]['high'] for k in range(1, lb+1)) and all(c[i]['high'] > c[i+k]['high'] for k in range(1, lb+1)):
            highs.append(i)
        if all(c[i]['low'] < c[i-k]['low'] for k in range(1, lb+1)) and all(c[i]['low'] < c[i+k]['low'] for k in range(1, lb+1)):
            lows.append(i)
    return highs, lows


def last_structure_direction(c: List[Dict[str, float]], highs: List[int], lows: List[int]) -> str:
    """تقدير اتجاه آخر هيكل (bull/bear/none) اعتمادًا على آخر قمة/قاع مؤكدة."""
    if not highs or not lows:
        return 'none'
    last_h, last_l = highs[-1], lows[-1]
    # إذا كان آخر حدث مُسجّل قمة أقرب زمنيًا من القاع
    if _time_of(c[last_h]) > _time_of(c[last_l]):
        # قارن HH/HL تقريبًا
        if len(highs) >= 2 and c[highs[-1]]['high'] > c[highs[-2]]['high']:
            return 'bull'
    else:
        if len(lows) >= 2 and c[lows[-1]]['low'] < c[lows[-2]]['low']:
            return 'bear'
    return 'none'


def detect_fvg(c: List[Dict[str,float]], gate_ts: int) -> List[Dict[str, Any]]:
    out = []
    for i in range(1, len(c)-1):
        if _time_of(c[i+1]) < gate_ts or _time_of(c[i-1]) < gate_ts:
            continue
        # Bullish FVG: low[i+1] > high[i-1]
        if c[i+1]['low'] > c[i-1]['high']:
            out.append({
                'left': _time_of(c[i-1]), 'right': _time_of(c[i+1]),
                'bottom': c[i-1]['high'], 'top': c[i+1]['low'], 'text': 'FVG↑'
            })
        # Bearish FVG: high[i+1] < low[i-1]
        if c[i+1]['high'] < c[i-1]['low']:
            out.append({
                'left': _time_of(c[i-1]), 'right': _time_of(c[i+1]),
                'bottom': c[i+1]['high'], 'top': c[i-1]['low'], 'text': 'FVG↓'
            })
    return out


def detect_bos_choch(c: List[Dict[str,float]], highs: List[int], lows: List[int], gate_ts: int) -> List[Dict[str, Any]]:
    out = []
    if not highs or not lows:
        return out
    dirn = last_structure_direction(c, highs, lows)
    last_high = highs[-1]
    last_low = lows[-1]
    lv_high = c[last_high]['high']
    lv_low = c[last_low]['low']
    for i in range(max(1, len(c)-10), len(c)):
        if _time_of(c[i]) < gate_ts:
            continue
        close_ = c[i]['close']
        # BOS: كسر آخر سوينغ مع الاتجاه
        if dirn == 'bull' and close_ > lv_high:
            out.append({'time': _time_of(c[i]), 'text': 'BOS↑', 'price': close_})
        if dirn == 'bear' and close_ < lv_low:
            out.append({'time': _time_of(c[i]), 'text': 'BOS↓', 'price': close_})
        # CHOCH: كسر آخر سوينغ عكس الاتجاه السائد
        if dirn == 'bull' and close_ < lv_low:
            out.append({'time': _time_of(c[i]), 'text': 'CHOCH↓', 'price': close_})
        if dirn == 'bear' and close_ > lv_high:
            out.append({'time': _time_of(c[i]), 'text': 'CHOCH↑', 'price': close_})
    return out


def detect_ob(c: List[Dict[str,float]], bos_labels: List[Dict[str,Any]], gate_ts: int, lookback: int = 10) -> List[Dict[str, Any]]:
    out = []
    # لكل BOS نحدد آخر شمعة معاكسة اللون قبلها ونحدد نطاقها كـ OB
    for lab in bos_labels:
        t = lab['time']
        if t < gate_ts:
            continue
        i = next((k for k in range(len(c)-1, -1, -1) if _time_of(c[k]) <= t), len(c)-1)
        # ابحث للخلف عن شمعة معاكسة اللون
        sign = 1 if '↑' in lab['text'] else -1
        for k in range(max(0, i - lookback), i):
            bull = c[k]['close'] > c[k]['open']
            if (sign == 1 and bull is False) or (sign == -1 and bull is True):
                # استخدم نطاق جسم الشمعة كمنطقة OB (محافظة)
                bottom = min(c[k]['open'], c[k]['close'])
                top = max(c[k]['open'], c[k]['close'])
                out.append({
                    'left': _time_of(c[k]), 'right': t,
                    'bottom': bottom, 'top': top,
                    'text': 'OB↑' if sign == 1 else 'OB↓'
                })
                break
    return out


def detect_golden_zone(c: List[Dict[str,float]], highs: List[int], lows: List[int], gate_ts: int) -> List[Dict[str, Any]]:
    out = []
    if len(highs) < 1 or len(lows) < 1:
        return out
    # نحدد آخر ساق مؤكدة (من آخر قاع إلى آخر قمة أو العكس) بشرط أن نهاية الساق داخل النافذة
    last_h_i, last_l_i = highs[-1], lows[-1]
    last_h_t, last_l_t = _time_of(c[last_h_i]), _time_of(c[last_l_i])
    if last_h_t >= gate_ts and last_l_t >= gate_ts:
        # اختر الساق الأخيرة بالأحدث زمنيًا كنهاية
        if last_h_t > last_l_t:
            # ساق صاعدة: من آخر قاع قبل القمة إلى القمة
            start_candidates = [i for i in lows if i < last_h_i]
            if start_candidates:
                s_i = start_candidates[-1]
                a = c[s_i]['low']; b = c[last_h_i]['high']
                # Golden Zone 61.8% - 78.6% ارتداد نزولي من القمة
                gz_min = b - 0.786*(b - a)
                gz_max = b - 0.618*(b - a)
                out.append({'left': _time_of(c[s_i]), 'right': last_h_t, 'bottom': gz_min, 'top': gz_max, 'text': 'GoldenZone↑'})
        else:
            # ساق هابطة: من آخر قمة قبل القاع إلى القاع
            start_candidates = [i for i in highs if i < last_l_i]
            if start_candidates:
                s_i = start_candidates[-1]
                a = c[s_i]['high']; b = c[last_l_i]['low']
                # Golden Zone 61.8% - 78.6% ارتداد صعودي من القاع
                gz_min = b + 0.618*(a - b)
                gz_max = b + 0.786*(a - b)
                out.append({'left': _time_of(c[s_i]), 'right': last_l_t, 'bottom': gz_min, 'top': gz_max, 'text': 'GoldenZone↓'})
    return out

# =============================
# الماسح الرئيسي
# =============================

def scan_symbols(symbols: List[str], timeframe: str, bars: int, max_age_bars: int, smc_path: Optional[str]) -> Dict[str, Any]:
    ex = _mk_exchange()
    report: Dict[str, Any] = {"timeframe": timeframe, "max_age_bars": max_age_bars, "results": []}
    smc = _SMCProxy(base_timeframe=timeframe, module_path=smc_path)
    for sym in symbols:
        try:
            raw = _fetch_ohlcv(ex, sym, timeframe, bars)
            candles = _to_candles(raw)
            if len(candles) < max_age_bars + 2:
                continue
            gate_ts = _last_nth_time(candles, max_age_bars)

            labels: List[Dict[str, Any]] = []
            boxes: List[Dict[str, Any]] = []

            # 1) نتائج SMC إن توفرت (بدون تنبيهات)
            parsed = smc.run(candles) if smc.available() else {}
            if parsed:
                labels += [L for L in parsed.get('labels', []) if int(L.get('time', 0)) >= gate_ts]
                boxes  += [B for B in parsed.get('boxes', [])  if int(B.get('left', 0)) >= gate_ts or int(B.get('right', 0)) >= gate_ts]

            # 2) محللنا الداخلي لمفاهيم: FVG/BOS/CHOCH/OB/GoldenZone
            hs, ls = pivots(candles, lb=1)
            # FVG
            boxes += detect_fvg(candles, gate_ts)
            # BOS & CHOCH
            bos_ch = detect_bos_choch(candles, hs, ls, gate_ts)
            labels += bos_ch
            # OB من BOS
            boxes += detect_ob(candles, bos_ch, gate_ts)
            # Golden Zone
            boxes += detect_golden_zone(candles, hs, ls, gate_ts)

            entry = {
                "symbol": sym,
                "latest_close": candles[-1]['close'],
                "events": {"labels": labels, "boxes": boxes}
            }
            report["results"].append(entry)
            time.sleep(ex.rateLimit / 1000 if getattr(ex, 'rateLimit', 0) else 0.05)
        except Exception as e:
            report["results"].append({"symbol": sym, "error": str(e)})
    return report


def write_reports(report: Dict[str, Any], md_path: str, json_path: str) -> None:
    pathlib.Path(json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = [f"# Scan Report — TF: {report['timeframe']} (last {report['max_age_bars']} bars)", ""]
    for r in report["results"]:
        if "error" in r:
            lines += [f"## {r['symbol']}", f"**ERROR**: {r['error']}", ""]
            continue
        lines += [f"## {r['symbol']} — close: {r['latest_close']}"]
        ev = r["events"]
        if ev["labels"]:
            lines.append("**Labels (last window):**")
            for L in ev["labels"]:
                ts = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(int(L['time'])/1000))
                lines.append(f"- [{ts}] {L['text']} @ {L['price']}")
        if ev["boxes"]:
            lines.append("**Boxes/Zones (last window):**")
            for B in ev["boxes"]:
                ts = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(int(B.get('left', 0))/1000))
                lines.append(f"- [{ts}] {B.get('text','')} {B.get('bottom','?')} → {B.get('top','?')}")
        lines.append("")
    pathlib.Path(md_path).write_text("
".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description="Binance USDT‑M scanner (last 5 bars only) + SMC concepts")
    ap.add_argument("--symbols", type=str, default=None, help="قائمة رموز مفصولة بفواصل (اختياري)")
    ap.add_argument("--limit", type=int, default=_DEF_LIMIT_SYMBOLS, help="عدد الأسواق التلقائية إن لم تُحدد --symbols")
    ap.add_argument("--timeframe", type=str, default=_DEF_TIMEFRAME, help="الإطار الزمني (مثال: 1m, 5m, 15m, 1h)")
    ap.add_argument("--bars", type=int, default=_DEF_BARS, help="عدد الشموع المطلوب جلبها")
    ap.add_argument("--max-age-bars", type=int, default=_DEF_MAX_AGE_BARS, help="النافذة الزمنية للأحداث (افتراضي 5)")
    ap.add_argument("--smc-path", type=str, default=None, help="مسار ملف SmartMoneyAlgoProE5.py (اختياري)")
    ap.add_argument("--out-json", type=str, default="SCAN_REPORT.json")
    ap.add_argument("--out-md", type=str, default="SCAN_REPORT.md")
    args = ap.parse_args()

    ex = _mk_exchange()
    symbols = _pick_symbols(ex, args.limit, args.symbols)
    report = scan_symbols(symbols, args.timeframe, args.bars, args.max_age_bars, args.smc_path)
    write_reports(report, args.out_md, args.out_json)

    print(json.dumps({
        "symbols": len(symbols),
        "out_json": args.out_json,
        "out_md": args.out_md
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()

> تشغيل سريع:

pip install ccxt
python scanner_ccxt_binanceusdm.py --timeframe 15m --limit 25
# أو: تحديد رموز ثابتة
python scanner_ccxt_binanceusdm.py --timeframe 5m --symbols "BTC/USDT:USDT,ETH/USDT:USDT,BNB/USDT:USDT"
# دمج محلل خارجي (سمّ الملف كما في مشروعك)
python scanner_ccxt_binanceusdm.py --timeframe 15m --limit 20 --smc-path Smc_merged_full.patched.v15.py




---

تصحيحات لازمة لتعطيل التنبيهات و"أحدث الإشارات"

احفظ الملف التالي باسم: patch_alerts.diff وطبّقه يدويًا (أو غيّر يدويًا):

--- a/Smc_merged_full.patched.v15.py
+++ b/Smc_merged_full.patched.v15.py
@@
 class SmartMoneyAlgoProE5:
@@
-    def alertcondition(self, condition: bool, title: str, message: Optional[str] = None) -> None:
-        if condition:
-            timestamp = self.series.get_time(0)
-            text = title if message is None else f"{title} :: {message}"
-            self.alerts.append((timestamp, text))
-            self._trace("alertcondition", "trigger", timestamp=timestamp, title=title, alert_message=message)
+    def alertcondition(self, condition: bool, title: str, message: Optional[str] = None) -> None:
+        # مُعطّل: لا تنبيهات ولا تخزين.
+        return
@@
-    def _register_label_event(self, label: Label) -> None:
-        text = label.text.strip()
-        collapsed = text.replace(" ", "")
-        key: Optional[str] = None
-        # ... (منطق بناء console_event_log بالكامل)
-        if key:
-            # ... (تحديث self.console_event_log)
-            self._trace("label", "register", timestamp=label.x, key=key, text=label.text, price=label.y)
+    def _register_label_event(self, label: Label) -> None:
+        # مُعطّل: لا إنشاء/تحديث لـ console_event_log.
+        return

> أثر التصحيح: لا تُنشأ تنبيهات ولا "أحدث الإشارات" داخل النموذج. الكائنات labels/boxes تبقى متاحة ليقرأها الماسح الجديد فقط.




---

خطوات دمج سريعة

1. أزِل/اعطِّل أي وحدات ماسح قديمة (ملفات تحمل scanner* أو منطق جلب رموز/إشارات قديم).


2. طبّق التصحيح أعلاه على ملف SMC لديك (أو عطِّل الطرق يدويًا).


3. أضِف scanner_ccxt_binanceusdm.py إلى المشروع.


4. شغّل بالوسائط المناسبة (--limit أو --symbols و--timeframe).


5. راجع SCAN_REPORT.json و SCAN_REPORT.md. لن ترى أي حدثٍ أقدم من آخر ٥ شموع.




---

اتفاقية قبول

النجاح = لا أثر لماسح/تنبيهات قديمة + وجود ماسح CCXT جديد يُظهر فقط أحداث آخر ٥ شموع لكل سوق + إمكانية تخصيص عدد الأسواق والإطار الزمني.

تم إضافة دعم صريح داخل الماسح لـ:

Golden Zone

CHOCH

FVG

BOS

OB


الكود المحدّث موجود على الـCanvas داخل نفس ملف scanner_ccxt_binanceusdm.py، وبقي عليه نفس سياسة “آخر ٥ شموع فقط”.

تشغيل نموذجي:

pip install ccxt
python scanner_ccxt_binanceusdm.py --timeframe 15m --limit 25
# أو:
python scanner_ccxt_binanceusdm.py --timeframe 5m --symbols "BTC/USDT:USDT,ETH/USDT:USDT"

المخرجات:

labels: أحداث BOS/CHOCH مع السعر والوقت.

boxes: مناطق FVG، OB، Golden Zone (حد سفلي/علوي + يسار/يمين بالـtimestamp).

يتم تجاهل أي شيء أقدم من آخر ٥ شموع.


إذا تريد ضبط قواعد الكشف بدقة (مثلاً عرض OB بكامل الـwick بدل الجسم، أو نطاق Golden Zone مختلف مثل 0.62–0.705)، قل القيم وسأثبّتُها مباشرة.

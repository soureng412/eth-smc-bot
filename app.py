import os
import time
import json
import requests
from datetime import datetime
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify

# ==================== টেলিগ্রাম ও মাল্টি-কয়েন কনফিগারেশন ====================
# ==================== ভারতীয় সময় (IST Timezone) কনফিগারেশন ====================
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_time_str():
    return datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

def get_ist_short_str():
    return datetime.now(IST).strftime("%d %b, %I:%M %p IST")

# ==================== টেলিগ্রাম ও কনফিগারেশন ====================
TELEGRAM_BOT_TOKEN = "8553506343:AAFUtxPSjXoC0H5ForsccaduEpsURMuUcaE"
TELEGRAM_CHAT_ID = "5333453283"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUTUSDT", "MUBARAKUSDT"]
RRR = 2.0  # 1:2 Risk to Reward Ratio
JOURNAL_FILE = "journal_trades.json"
RENDER_URL = "https://eth-smc-bot.onrender.com"

app = Flask(__name__)

# ডুপ্লিকেট অ্যালার্ট ঠেকানোর মেমোরি
last_alert_times = {}
last_logs = []

# ==================== স্বয়ংক্রিয় জার্নাল ডাটা স্টোরেজ ====================
def load_journal():
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # প্রাথমিক স্যাম্পল রেকর্ড
    return [
        {
            "id": 1,
            "time": "29 Oct 2026, 01:00:00 PM IST",
            "symbol": "XAUTUSDT",
            "type": "SELL",
            "entry": 4026.00,
            "sl": 4037.60,
            "tp": 4002.70,
            "status": "RUNNING",
            "pnl_r": 0.0,
            "close_time": None,
            "notes": "1H High ($4031.9) সুইপ + 5m MSS + FVG"
        }
    ]

def save_journal(trades):
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Journal Save Error]: {e}")

def fmt_price(val):
    if val >= 1.0:
        return f"{val:.2f}"
    return f"{val:.6f}"

def send_telegram_alert(text_msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text_msg,
            "parse_mode": "HTML"
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram Error]: {e}")
        return False

# সার্বজনীন ডেটা সোর্স (Gate.io + Bybit Fallback)
# ==================== সার্বজনীন ডেটা সোর্স (Gate.io + Bybit Fallback) ====================
def get_klines(symbol, interval, limit=30):
    # ১. Gate.io
    try:
        gate_sym = symbol.replace("USDT", "_USDT")
        gate_interval = "1h" if interval == "1h" else "5m"
        url = f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={gate_sym}&interval={gate_interval}&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                candles = []
                for d in data:
                    candles.append({
                        "time": int(d[0]) * 1000,
                        "open": float(d[5]),
                        "high": float(d[3]),
                        "low": float(d[4]),
                        "close": float(d[2])
                    })
                return candles
    except:
    except Exception:
        pass

    # ২. Bybit Fallback
    try:
        bybit_interval = "60" if interval == "1h" else "5"
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={bybit_interval}&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data.get("retCode") == 0 and "list" in data.get("result", {}):
                raw_list = data["result"]["list"]
                raw_list.reverse()
                candles = []
                for d in raw_list:
                    candles.append({
                        "time": int(d[0]),
                        "open": float(d[1]),
                        "high": float(d[2]),
                        "low": float(d[3]),
                        "close": float(d[4])
                    })
                return candles
    except:
    except Exception:
        pass

    return []

# কয়েন স্ক্যান
# ==================== অটোমেটিক TP/SL ট্র্যাকার ====================
def check_running_trades(symbol, latest_m5):
    trades = load_journal()
    updated = False
    
    for t in trades:
        if t.get("symbol") == symbol and t.get("status") == "RUNNING":
            entry = t["entry"]
            sl = t["sl"]
            tp = t["tp"]
            is_buy = t["type"] == "BUY"
            
            c_high = latest_m5["high"]
            c_low = latest_m5["low"]
            
            # BUY ট্রেড আউটকাম চেক
            if is_buy:
                if c_high >= tp:
                    t["status"] = "WIN"
                    t["pnl_r"] = 2.0
                    t["close_time"] = get_ist_time_str()
                    updated = True
                    msg = (
                        f"🏆 <b>[{symbol}] TAKE-PROFIT (TP) HIT!</b> 🎯\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>Market:</b> #{symbol} (BUY)\n"
                        f"💵 <b>Entry:</b> ${fmt_price(entry)}\n"
                        f"🎯 <b>Target (TP):</b> ${fmt_price(tp)}\n"
                        f"💰 <b>ফলাফল:</b> +2R নিট প্রফিট অর্জিত! 🟢\n"
                        f"⏰ <b>সময়:</b> {get_ist_time_str()}\n"
                        f"📱 <a href='{RENDER_URL}/journal'>মোবাইল ট্রেডিং জার্নাল দেখুন</a>"
                    )
                    send_telegram_alert(msg)
                elif c_low <= sl:
                    t["status"] = "LOSS"
                    t["pnl_r"] = -1.0
                    t["close_time"] = get_ist_time_str()
                    updated = True
                    msg = (
                        f"🛑 <b>[{symbol}] STOP-LOSS (SL) HIT!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>Market:</b> #{symbol} (BUY)\n"
                        f"💵 <b>Entry:</b> ${fmt_price(entry)}\n"
                        f"🛑 <b>Stop Loss:</b> ${fmt_price(sl)}\n"
                        f"📉 <b>ফলাফল:</b> -1R লস রিকভারি প্ল্যান 🔴\n"
                        f"⏰ <b>সময়:</b> {get_ist_time_str()}\n"
                        f"📱 <a href='{RENDER_URL}/journal'>মোবাইল ট্রেডিং জার্নাল দেখুন</a>"
                    )
                    send_telegram_alert(msg)
            # SELL ট্রেড আউটকাম চেক
            else:
                if c_low <= tp:
                    t["status"] = "WIN"
                    t["pnl_r"] = 2.0
                    t["close_time"] = get_ist_time_str()
                    updated = True
                    msg = (
                        f"🏆 <b>[{symbol}] TAKE-PROFIT (TP) HIT!</b> 🎯\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>Market:</b> #{symbol} (SELL)\n"
                        f"💵 <b>Entry:</b> ${fmt_price(entry)}\n"
                        f"🎯 <b>Target (TP):</b> ${fmt_price(tp)}\n"
                        f"💰 <b>ফলাফল:</b> +2R নিট প্রফিট অর্জিত! 🟢\n"
                        f"⏰ <b>সময়:</b> {get_ist_time_str()}\n"
                        f"📱 <a href='{RENDER_URL}/journal'>মোবাইল ট্রেডিং জার্নাল দেখুন</a>"
                    )
                    send_telegram_alert(msg)
                elif c_high >= sl:
                    t["status"] = "LOSS"
                    t["pnl_r"] = -1.0
                    t["close_time"] = get_ist_time_str()
                    updated = True
                    msg = (
                        f"🛑 <b>[{symbol}] STOP-LOSS (SL) HIT!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>Market:</b> #{symbol} (SELL)\n"
                        f"💵 <b>Entry:</b> ${fmt_price(entry)}\n"
                        f"🛑 <b>Stop Loss:</b> ${fmt_price(sl)}\n"
                        f"📉 <b>ফলাফল:</b> -1R লস রিকভারি প্ল্যান 🔴\n"

import os
import time
import requests
from datetime import datetime
import threading
from flask import Flask

# ==================== টেলিগ্রাম ও মার্কেট কনফিগারেশন ====================
TELEGRAM_BOT_TOKEN = "8553506343:AAFUtxPSjXoC0H5ForsccaduEpsURMuUcaE"
TELEGRAM_CHAT_ID = "5333453283"
SYMBOL = "ETHUSDT"
RRR = 2.0  # 1:2 Risk to Reward Ratio

app = Flask(__name__)

# হেলথ চেক রাউট (Render সার্ভার যাতে ২৪ ঘণ্টা জেগে থাকে)
@app.route('/')
def home():
    return "🟢 ETH SMC Sniper 24/7 Cloud Bot is Running Successfully!"

# টেলিগ্রামে মেসেজ পাঠানো
def send_telegram_alert(text_msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text_msg,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram Error]: {e}")
        return False

# ফ্রি ক্যান্ডেল ডাটা ফেচ
def get_klines(interval, limit):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            candles = []
            for d in res.json():
                candles.append({
                    "time": int(d[0]),
                    "open": float(d[1]),
                    "high": float(d[2]),
                    "low": float(d[3]),
                    "close": float(d[4])
                })
            return candles
        return []
    except Exception as e:
        print(f"[Data Error for {interval}]: {e}")
        return []

# ২৪/৭ লাইভ মার্কেট স্ক্যানার থ্রেড
def background_market_scanner():
    print("=" * 50)
    print("🚀 24/7 Cloud Scanner Started...")
    print("=" * 50)
    
    welcome = (
        "🌐 <b>ETH SMC Sniper 24/7 ক্লাউডে সক্রিয় হয়েছে!</b>\n\n"
        "✅ আপনার ল্যাপটপ বন্ধ থাকলেও এই বট দিন-রাত ২৪ ঘণ্টা আপনার মোবাইলে সিগন্যাল পাঠাবে।\n"
        "📊 <b>লজিক:</b> 1H CRT + 5m MSS + 5m FVG"
    )
    send_telegram_alert(welcome)
    
    last_alert_time = 0
    
    while True:
        try:
            h1 = get_klines("1h", 5)
            m5 = get_klines("5m", 25)
            
            if h1 and m5 and len(h1) >= 2 and len(m5) >= 10:
                prev_h1 = h1[-2]
                h1_high = prev_h1["high"]
                h1_low = prev_h1["low"]
                
                closed_m5 = m5[:-1]
                curr = closed_m5[-1]
                curr_time = curr["time"]
                
                # 5m সুইং হাই ও লো (MSS)
                recent_highs = [c["high"] for c in closed_m5[-6:-1]]
                recent_lows = [c["low"] for c in closed_m5[-6:-1]]
                swing_high = max(recent_highs)
                swing_low = min(recent_lows)
                
                # 5m FVG
                c0 = closed_m5[-1]
                c2 = closed_m5[-3]
                bullish_fvg = c0["low"] > c2["high"]
                bearish_fvg = c0["high"] < c2["low"]
                
                # সুইপ চেক
                ssl_taken = False
                bsl_taken = False
                sweep_low = curr["low"]
                sweep_high = curr["high"]
                
                for c in closed_m5[-5:]:
                    if c["low"] < h1_low and c["close"] > h1_low:
                        ssl_taken = True
                        sweep_low = min(sweep_low, c["low"])
                    if c["high"] > h1_high and c["close"] < h1_high:
                        bsl_taken = True
                        sweep_high = max(sweep_high, c["high"])
                
                mss_up = curr["close"] > swing_high
                mss_down = curr["close"] < swing_low
                
                # বাই সিগন্যাল
                if ssl_taken and mss_up and bullish_fvg and curr_time != last_alert_time:
                    last_alert_time = curr_time
                    entry = curr["close"]
                    sl = round(sweep_low * 0.999, 2)
                    tp = round(entry + ((entry - sl) * RRR), 2)
                    
                    msg = (
                        "🟢 <b>ETH SMC BUY (LONG) SIGNAL!</b> 🎯\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💵 <b>Entry Price:</b> ${entry}\n"
                        f"🛑 <b>Stop-Loss (SL):</b> ${sl}\n"
                        f"🎯 <b>Take-Profit (TP 1:2):</b> ${tp}\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 1H Low (${h1_low}) লিকুইডিটি সুইপ + 5m MSS + FVG!\n"
                        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    send_telegram_alert(msg)
                    print("🔥 [BUY SIGNAL SENT TO TELEGRAM!]")
                
                # সেল সিগন্যাল
                if bsl_taken and mss_down and bearish_fvg and curr_time != last_alert_time:
                    last_alert_time = curr_time
                    entry = curr["close"]
                    sl = round(sweep_high * 1.001, 2)
                    tp = round(entry - ((sl - entry) * RRR), 2)
                    
                    msg = (
                        "🔴 <b>ETH SMC SELL (SHORT) SIGNAL!</b> 🎯\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💵 <b>Entry Price:</b> ${entry}\n"
                        f"🛑 <b>Stop-Loss (SL):</b> ${sl}\n"
                        f"🎯 <b>Take-Profit (TP 1:2):</b> ${tp}\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 1H High (${h1_high}) লিকুইডিটি সুইপ + 5m MSS + FVG!\n"
                        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    send_telegram_alert(msg)
                    print("🔥 [SELL SIGNAL SENT TO TELEGRAM!]")
                    
        except Exception as e:
            print(f"[Loop Error]: {e}")
            
        time.sleep(30)

# অ্যাপ চালুর সাথে সাথে ব্যাকগ্রাউন্ডে স্ক্যানার চালু করা
threading.Thread(target=background_market_scanner, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

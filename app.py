import os
import time
import requests
from datetime import datetime
import threading
from flask import Flask
from flask import Flask, jsonify

# ==================== টেলিগ্রাম ও মাল্টি-কয়েন কনফিগারেশন ====================
TELEGRAM_BOT_TOKEN = "8553506343:AAFUtxPSjXoC0H5ForsccaduEpsURMuUcaE"
TELEGRAM_CHAT_ID = "5333453283"

# আপনি যেসব কয়েন স্ক্যান করতে চান (এখানে আরও কয়েন যোগ করতে পারেন)
# কয়েনসমূহ
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUTUSDT", "MUBARAKUSDT"]

RRR = 2.0  # 1:2 Risk to Reward Ratio

app = Flask(__name__)

# গ্লোবাল স্ট্যাটাস ট্র্যাকার
system_status = {
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "last_scan_time": "Never",
    "total_scans": 0,
    "last_signals": [],
    "coins_status": {}
}

@app.route('/')
def home():
    pairs = ", ".join(SYMBOLS)
    return f"🟢 Multi-Coin SMC Sniper Bot is Running 24/7! Scanning: {pairs}"
    return f"🟢 Multi-Coin SMC Sniper Bot 24/7 Live! Scanning: {pairs} | <a href='/status'>View Live Diagnostics</a>"

@app.route('/status')
def status():
    return jsonify(system_status)

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

# Bybit পাবলিক API (আন্তর্জাতিক ও লাইভ ডেটা সোর্স)
# সার্বজনীন ডেটা সোর্স (Gate.io + Bybit Fallback - কোনো দেশে বা ক্লাউডে ব্লকড নয়)
def get_klines(symbol, interval, limit=30):
    # ১. প্রথমে Gate.io থেকে ডেটা নেওয়া (US ক্লাউডে ১০০% আনব্লকড)
    try:
        # Bybit: 60 = 1 hour, 5 = 5 minutes
        gate_sym = symbol.replace("USDT", "_USDT")
        gate_interval = "1h" if interval == "1h" else "5m"
        url = f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={gate_sym}&interval={gate_interval}&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=8)
        
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                candles = []
                for d in data:
                    # Gate.io ফরম্যাট: [time, quote_vol, close, high, low, open, base_vol]
                    candles.append({
                        "time": int(d[0]) * 1000,
                        "open": float(d[5]),
                        "high": float(d[3]),
                        "low": float(d[4]),
                        "close": float(d[2])
                    })
                return candles
    except Exception as e:
        pass

    # ২. ব্যাকআপ হিসেবে Bybit থেকে চেষ্টা
    try:
        bybit_interval = "60" if interval == "1h" else "5"
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={bybit_interval}&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data.get("retCode") == 0 and "list" in data.get("result", {}):
                raw_list = data["result"]["list"]
                raw_list.reverse()  # সময় অনুযায়ী ক্রমান্বয়ে সাজানো
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
        return []
    except Exception as e:
        print(f"[Data Error for {symbol} - {interval}]: {e}")
        return []
        pass

# একক কয়েন স্ক্যানিং ফাংশন
    return []

def scan_single_symbol(symbol, last_alerts):
    h1 = get_klines(symbol, "1h", 5)
    m5 = get_klines(symbol, "5m", 25)
    
    if not (h1 and m5 and len(h1) >= 2 and len(m5) >= 10):
        system_status["coins_status"][symbol] = f"Error fetching candles at {datetime.now().strftime('%H:%M:%S')}"
        return
        
    system_status["coins_status"][symbol] = f"Active (1H: {len(h1)}, 5M: {len(m5)})"
    
    prev_h1 = h1[-2]
    h1_high = prev_h1["high"]
    h1_low  = prev_h1["low"]
    
    closed_m5 = m5[:-1]
    curr = closed_m5[-1]
    curr_time = curr["time"]
    
    # 5m সুইং হাই ও লো (MSS)
    recent_highs = [c["high"] for c in closed_m5[-6:-1]]
    recent_lows  = [c["low"] for c in closed_m5[-6:-1]]
    swing_high = max(recent_highs)
    swing_low  = min(recent_lows)
    
    # 5m FVG
    c0 = closed_m5[-1]
    c2 = closed_m5[-3]
    bullish_fvg = c0["low"] > c2["high"]
    bearish_fvg = c0["high"] < c2["low"]
    
    # লিকুইডিটি সুইপ চেক (গত ৫টি ক্যান্ডেলে)
    # লিকুইডিটি সুইপ চেক
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
    
    last_time = last_alerts.get(symbol, 0)
    
    # বাই সিগন্যাল
    if ssl_taken and mss_up and bullish_fvg and curr_time != last_time:
        last_alerts[symbol] = curr_time
        entry = curr["close"]
        sl = round(sweep_low * 0.999, 4)
        tp = round(entry + ((entry - sl) * RRR), 4)
        
        msg = (
            f"🟢 <b>[{symbol}] SMC BUY (LONG) SIGNAL!</b> 🎯\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>Coin:</b> #{symbol}\n"
            f"🪙 <b>Market:</b> #{symbol}\n"
            f"💵 <b>Entry Price:</b> ${entry}\n"
            f"🛑 <b>Stop-Loss (SL):</b> ${sl}\n"
            f"🎯 <b>Take-Profit (TP 1:2):</b> ${tp}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>কারণ:</b> 1H Low (${h1_low}) লিকুইডিটি সুইপ + 5m MSS + FVG!\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        send_telegram_alert(msg)
        system_status["last_signals"].append(f"BUY {symbol} at {datetime.now().strftime('%H:%M:%S')}")
        print(f"🔥 [BUY SIGNAL SENT FOR {symbol}!]")
        
    # সেল সিগন্যাল
    if bsl_taken and mss_down and bearish_fvg and curr_time != last_time:
        last_alerts[symbol] = curr_time
        entry = curr["close"]
        sl = round(sweep_high * 1.001, 4)
        tp = round(entry - ((sl - entry) * RRR), 4)
        
        msg = (
            f"🔴 <b>[{symbol}] SMC SELL (SHORT) SIGNAL!</b> 🎯\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>Coin:</b> #{symbol}\n"
            f"🪙 <b>Market:</b> #{symbol}\n"
            f"💵 <b>Entry Price:</b> ${entry}\n"
            f"🛑 <b>Stop-Loss (SL):</b> ${sl}\n"
            f"🎯 <b>Take-Profit (TP 1:2):</b> ${tp}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>কারণ:</b> 1H High (${h1_high}) লিকুইডিটি সুইপ + 5m MSS + FVG!\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        send_telegram_alert(msg)
        system_status["last_signals"].append(f"SELL {symbol} at {datetime.now().strftime('%H:%M:%S')}")
        print(f"🔥 [SELL SIGNAL SENT FOR {symbol}!]")

# ২৪/৭ মাল্টি-কয়েন স্ক্যানার থ্রেড
def background_market_scanner():
    print("=" * 55)
    print("🚀 24/7 Multi-Coin SMC Cloud Scanner Started...")
    print("🚀 24/7 Global Multi-Feed Cloud Scanner Running...")
    print(f"Scanning Pairs: {', '.join(SYMBOLS)}")
    print("=" * 55)
    
    welcome = (
        "🔥 <b>Multi-Coin SMC Sniper সক্রিয় হয়েছে!</b>\n\n"
        "✅ <b>স্ক্যানিং পেয়ারসমূহ:</b>\n"
        "• Bitcoin (BTCUSDT)\n"
        "• Ethereum (ETHUSDT)\n"
        "• Solana (SOLUSDT)\n"
        "• Gold / Tether Gold (XAUTUSDT)\n"
        "• Mubarak (MUBARAKUSDT)\n\n"
        "📊 <b>লজিক:</b> 1H CRT + 5m MSS + 5m FVG\n"
        "⏰ প্রতি ক্যান্ডেলে সবকটি কয়েন স্ক্যান হচ্ছে—যেকোনোটিতে সুযোগ পেলেই সাথে সাথে অ্যালার্ট পাবেন!"
        "⚡ <b>SMC Sniper ইঞ্জিন সম্পূর্ণ অপ্টিমাইজড ও সক্রিয়!</b>\n\n"
        "✅ <b>ডাটা সোর্স:</b> গ্লোবাল মাল্টিপল আনরেস্ট্রিক্টেড ফিড যুক্ত।\n"
        "📊 <b>স্ক্যানিং পেয়ার:</b> BTC, ETH, SOL, Gold (XAUT), Mubarak\n"
        "⏰ ২৪ ঘণ্টা একটানা লাইভ স্ক্যান চলছে..."
    )
    send_telegram_alert(welcome)
    
    last_alerts = {}
    
    while True:
        try:
            system_status["last_scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_status["total_scans"] += 1
            for s in SYMBOLS:
                scan_single_symbol(s, last_alerts)
                time.sleep(2)  # প্রতিটি কয়েনের মাঝে সামান্য বিরতি
                time.sleep(2)
        except Exception as e:
            print(f"[Multi-Scan Loop Error]: {e}")
            print(f"[Loop Error]: {e}")
            
        time.sleep(25)

# অ্যাপ চালুর সাথে সাথে ব্যাকগ্রাউন্ডে মাল্টি-কয়েন স্ক্যানার চালু
threading.Thread(target=background_market_scanner, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

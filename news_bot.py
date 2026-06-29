import feedparser
import requests
import schedule
import time
import json
import re
import os
import sys
from datetime import datetime, timezone, timedelta
from flask import Flask, request

# ═══════════════════════════════════════════════════════════
#  ⚙️  تنظیمات اصلی
# ═══════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = "8870002623:AAGLT969sR7wxWUcBTgc3npRjN2Mg_VsGf4"
TELEGRAM_CHAT_ID   = "7343350447"
OPENROUTER_API_KEY = "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"
TELEGRAM_API_BASE  = "https://morning-tooth-e39a.mortzapakdel85.workers.dev"
SENT_CACHE_FILE    = "sent_news.json"
SERPAPI_KEY        = "0fdc02509c76acf6d00cdd3d1a64265e25ab7d96d78b0878620551572bf8acb6"

# ═══════════════════════════════════════════════════════════
#  📦  متغیرهای سراسری
# ═══════════════════════════════════════════════════════════
last_analysis = ""
last_news_time = ""
last_selected_news = []

# ═══════════════════════════════════════════════════════════
#  🌐  سرور Flask
# ═══════════════════════════════════════════════════════════
app = Flask(__name__)

@app.route('/')
def home():
    return "Gold News Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return "OK", 200
            
        chat_id = data['message']['chat']['id']
        user_message = data['message'].get('text', '')

        if str(chat_id) != TELEGRAM_CHAT_ID:
            return "OK", 200
        if not user_message:
            return "OK", 200

        send_chat_action(chat_id, "typing")
        
        # ── قیمت طلا ──
        if "قیمت" in user_message and ("طلا" in user_message or "اونس" in user_message):
            gold_price = get_gold_price()
            if gold_price:
                send_telegram_response(chat_id, gold_price)
                return "OK", 200
        
        # ── جستجو ──
        web_results = search_web(user_message)
        
        context = ""
        if web_results:
            context = f"نتایج جستجو:\n{web_results}"
        elif last_analysis:
            context = f"آخرین تحلیل (به‌روز {last_news_time}):\n{last_analysis[:800]}"

        prompt = f"""
تو دستیار تحلیلگر بازار طلا هستی.

{context}

سوال: {user_message}

پاسخ مختصر و مفید به فارسی (۳-۵ جمله).
"""
        response = call_ai(prompt, max_tokens=800)
        send_telegram_response(chat_id, response or "❌ خطا. دوباره تلاش کن.")
        return "OK", 200
        
    except Exception as e:
        print(f"⚠️ خطا: {e}")
        return "OK", 200

# ── توابع کمکی ──
def send_chat_action(chat_id, action):
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendChatAction"
    try:
        requests.post(url, json={'chat_id': chat_id, 'action': action}, timeout=5)
    except Exception as e:
        print(f"⚠️ {e}")

def send_telegram_response(chat_id, text):
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        print(f"❌ {e}")

def search_web(query):
    try:
        url = "https://serpapi.com/search"
        params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google", "hl": "en", "gl": "us", "num": 3}
        response = requests.get(url, params=params, timeout=15)
        if not response.ok:
            return None
        data = response.json()
        results = []
        
        # answer_box
        answer = data.get('answer_box', {})
        if answer.get('answer'):
            return f"📌 {answer.get('answer')}"
        if answer.get('snippet'):
            return f"📌 {answer.get('snippet')}"
        
        # knowledge_graph
        kg = data.get('knowledge_graph', {})
        if kg.get('description'):
            results.append(f"📊 {kg.get('title', '')}: {kg.get('description')}")
        
        # organic_results
        for item in data.get('organic_results', [])[:3]:
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            if title and snippet:
                results.append(f"• {title}\n  {snippet}")
        
        return "\n\n".join(results) if results else None
    except Exception as e:
        print(f"⚠️ {e}")
        return None

def get_gold_price():
    try:
        url = "https://www.gold-api.com/price/XAU"
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            price = data.get('price', '')
            if price:
                return f"💰 قیمت لحظه‌ای طلا: ${price} (هر اونس)"
    except Exception as e:
        print(f"⚠️ {e}")
    return None

# ═══════════════════════════════════════════════════════════
#  🧠  پرامپت اخبار (اصلاح‌شده و قوی)
# ═══════════════════════════════════════════════════════════
NEWS_PROMPT = """
⚠️ **دستور اکید: فقط اخبار مرتبط با بازار طلا را انتخاب کن!**

✅ اخبار مرتبط:
- فدرال رزرو، نرخ بهره، تورم (CPI, PPI, PCE)
- اشتغال آمریکا (NFP، نرخ بیکاری)
- رشد اقتصادی (GDP)
- بانک‌های مرکزی (Fed, ECB, PBoC, BOJ, BOE)
- تنش‌های ژئوپولیتیک (جنگ، تحریم، بحران) که بر طلا تأثیر می‌گذارند
- خرید/فروش طلا توسط بانک‌های مرکزی
- قیمت طلا و دلار آمریکا (DXY)

❌ اخبار بی‌ربط (نادیده بگیر):
- فوتبال، ورزش، سرگرمی، هنر
- آب و هوا، گرمای هوا، زلزله (بدون تأثیر اقتصادی)
- جنایت، تصادفات، حوادث محلی
- سیاست داخلی کشورها (بدون تأثیر بر اقتصاد جهانی)
- اخبار عادی و روزمره

از لیست زیر، فقط اخبار مرتبط با طلا و اقتصاد جهانی را انتخاب کن.
"""

# ═══════════════════════════════════════════════════════════
#  📡  منابع خبری
# ═══════════════════════════════════════════════════════════
RSS_FEEDS = {
    "BBC World"            : "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera"           : "https://www.aljazeera.com/xml/rss/all.xml",
    "The Guardian"         : "https://www.theguardian.com/world/rss",
    "CNBC Economy"         : "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "MarketWatch"          : "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Reuters Business"     : "https://feeds.reuters.com/reuters/businessNews",
    "Kitco News"           : "https://www.kitco.com/rss/rss-news.xml",
    "Federal Reserve"      : "https://www.federalreserve.gov/feeds/press_all.xml",
    "Bloomberg"            : "https://feeds.bloomberg.com/markets/news.rss",
    "Financial Times"      : "https://www.ft.com/?format=rss",
    "Yahoo Finance"        : "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F",
    "Investing.com"        : "https://www.investing.com/rss/news.rss",
    "ZeroHedge"            : "https://feeds.feedburner.com/zerohedge/feed",
    "FXStreet"             : "https://www.fxstreet.com/feeds/rss/news",
    "DailyFX"              : "https://www.dailyfx.com/feeds/forex_news",
    "Reuters Markets"      : "https://feeds.reuters.com/reuters/Markets",
}

# ═══════════════════════════════════════════════════════════
#  📂  کش اخبار قبلی
# ═══════════════════════════════════════════════════════════

def load_sent_cache():
    if os.path.exists(SENT_CACHE_FILE):
        try:
            with open(SENT_CACHE_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent_cache(cache):
    with open(SENT_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache)[-1000:], f, ensure_ascii=False)

# ═══════════════════════════════════════════════════════════
#  📰  دریافت اخبار RSS
# ═══════════════════════════════════════════════════════════

def get_all_articles():
    time_limit = datetime.now(timezone.utc) - timedelta(hours=72)
    articles = []
    
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                pub = entry.get('published_parsed')
                if pub:
                    pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                    if pub_dt < time_limit:
                        continue
                title = entry.get('title', '').strip()
                link  = entry.get('link', '')
                if title:
                    articles.append({'title': title, 'source': source, 'url': link})
        except Exception as e:
            print(f"   ⚠️  {source}: {e}")

    seen, unique = set(), []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique.append(a)
    return unique

def filter_new_articles(articles, sent_cache):
    return [a for a in articles if a['title'] not in sent_cache]

# ═══════════════════════════════════════════════════════════
#  📅  تقویم اقتصادی
# ═══════════════════════════════════════════════════════════

def get_economic_calendar():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if not r.ok:
            print(f"   ⚠️  خطا در تقویم: {r.status_code}")
            return []

        events = r.json()
        today  = datetime.now().strftime('%Y-%m-%d')

        us_keywords = ['interest rate', 'rate decision', 'gdp', 'inflation', 'cpi', 'ppi', 
                       'pce', 'nonfarm payrolls', 'unemployment', 'employment', 'retail sales',
                       'manufacturing pmi', 'services pmi', 'fed', 'jobless claims', 'consumer confidence']
        eu_cn_keywords = ['interest rate', 'rate decision', 'gdp', 'growth']

        filtered = []
        for event in events:
            event_date = event.get('date', '')[:10]
            if event_date != today:
                continue

            country = event.get('country', '').upper()
            impact  = event.get('impact', '')
            title   = event.get('title', '').lower()

            if country == 'USD' and impact in ['High', 'Medium']:
                if any(kw in title for kw in us_keywords) or impact == 'High':
                    filtered.append(event)
            elif country in ['EUR', 'CNY'] and impact in ['High', 'Medium']:
                if any(kw in title for kw in eu_cn_keywords):
                    filtered.append(event)
            elif country in ['GBP', 'JPY'] and impact == 'High':
                if 'interest' in title or 'rate' in title:
                    filtered.append(event)

        return filtered

    except Exception as e:
        print(f"   ⚠️  خطا در تقویم: {e}")
        return []

# ═══════════════════════════════════════════════════════════
#  🤖  پردازش با OpenRouter
# ═══════════════════════════════════════════════════════════

def call_ai(prompt, max_tokens=6000):
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com",
                "X-Title": "Gold News Bot"
            },
            json={
                "model": "deepseek/deepseek-chat",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        if not r.ok:
            print(f"   ⚠️  OpenRouter: {r.status_code} - {r.text[:200]}")
            return None
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"   ⚠️  خطا در AI: {e}")
        return None

def ai_process_news(articles):
    if not articles:
        return [], ''

    articles_text = "\n".join([
        f"{i+1}. [{a['source']}] {a['title']}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""
{NEWS_PROMPT}

اخبار:
{articles_text}

**فقط اخبار مرتبط با طلا و اقتصاد جهانی را انتخاب کن.**
**اخبار بی‌ربط (فوتبال، آب‌وهوا، جنایت، هنر) را کاملاً نادیده بگیر.**

برای هر خبر انتخاب‌شده:
۱. عنوان را به فارسی ترجمه کن
۲. تاثیر بر اقتصاد و طلا را توضیح بده
۳. جهت (صعودی/نزولی/خنثی) را مشخص کن

سپس یک تحلیل جامع و متعادل بنویس.

فقط JSON:
{{
  "selected": [
    {{
      "index": 1,
      "title_fa": "ترجمه فارسی",
      "impact": "تاثیر بر اقتصاد و طلا",
      "direction": "صعودی/نزولی/خنثی — دلیل"
    }}
  ],
  "analysis": "تحلیل جامع..."
}}
"""
    response = call_ai(prompt, max_tokens=4000)
    if not response:
        return articles[:5], ''

    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            selected = []
            for item in data.get('selected', []):
                idx = item['index'] - 1
                if 0 <= idx < len(articles):
                    articles[idx]['title_fa'] = item.get('title_fa', articles[idx]['title'])
                    articles[idx]['impact']   = item.get('impact', '')
                    articles[idx]['direction'] = item.get('direction', '')
                    selected.append(articles[idx])
            
            analysis = data.get('analysis', '')
            if not isinstance(analysis, str):
                analysis = str(analysis)
            return selected, analysis
    except Exception as e:
        print(f"   ⚠️  خطا در پردازش JSON اخبار: {e}")
        return articles[:5], ''

    return articles[:5], ''

def ai_analyze_calendar(events):
    if not events:
        return None

    events_text = ""
    for e in events:
        country  = e.get('country', '')
        impact   = e.get('impact', '')
        title    = e.get('title', '')
        ev_time  = e.get('time', '--:--')
        actual   = e.get('actual', '') or '—'
        forecast = e.get('forecast', '') or '—'
        previous = e.get('previous', '') or '—'
        events_text += f"[{country}][{impact}] {ev_time} | {title} | قبلی: {previous} | پیش‌بینی: {forecast} | واقعی: {actual}\n"

    prompt = f"""
رویدادهای اقتصادی امروز:
{events_text}

برای هر رویداد:
۱. جایگاه در اقتصاد
۲. تاثیر بر طلا (صعودی/نزولی)
۳. تفسیر actual vs forecast

فقط JSON:
{{
  "events": [
    {{
      "title": "نام رویداد",
      "role": "جایگاه در اقتصاد",
      "gold_impact": "تاثیر بر طلا"
    }}
  ],
  "summary": "جمع‌بندی"
}}
"""
    response = call_ai(prompt, max_tokens=2000)
    if not response:
        return None

    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"   ⚠️  خطا در JSON تقویم: {e}")
    return None

# ═══════════════════════════════════════════════════════════
#  📤  ارسال تلگرام
# ═══════════════════════════════════════════════════════════

def send_telegram(text):
    try:
        url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }, timeout=30)
        if not r.ok:
            print(f"   ⚠️  تلگرام: {r.status_code}")
        return r.ok
    except Exception as e:
        print(f"   ❌  {e}")
        return False

def send_long_message(text):
    max_len = 4000
    if len(text) <= max_len:
        return send_telegram(text)

    parts = []
    while len(text) > max_len:
        cut = text[:max_len].rfind('\n')
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:]
    if text:
        parts.append(text)

    success = True
    for i, part in enumerate(parts):
        if i > 0:
            time.sleep(1)
        if not send_telegram(part):
            success = False
    return success

# ═══════════════════════════════════════════════════════════
#  🚀  اجرای اصلی
# ═══════════════════════════════════════════════════════════

def run():
    global last_analysis, last_news_time, last_selected_news
    
    print(f"\n{'═'*45}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}]  شروع اجرا")
    print(f"{'═'*45}")

    sent_cache = load_sent_cache()
    print(f"  📂  {len(sent_cache)} خبر در کش")

    print("  📡  دریافت اخبار RSS (۷۲ ساعت گذشته)...")
    all_articles = get_all_articles()
    new_articles = filter_new_articles(all_articles, sent_cache)
    print(f"  ✔   {len(all_articles)} کل | {len(new_articles)} جدید")

    selected, news_analysis = [], ''
    if new_articles:
        print("  🧠  AI در حال تحلیل اخبار...")
        selected, news_analysis = ai_process_news(new_articles)
        print(f"  ✔   {len(selected)} خبر مرتبط انتخاب شد")
    else:
        print("  ℹ️   همه اخبار قبلاً فرستاده شده‌اند")

    print("  📅  دریافت تقویم اقتصادی امروز...")
    calendar_events = get_economic_calendar()
    print(f"  ✔   {len(calendar_events)} رویداد امروز")

    calendar_analysis = None
    if calendar_events:
        print("  🧠  AI در حال تحلیل تقویم...")
        calendar_analysis = ai_analyze_calendar(calendar_events)

    if news_analysis:
        last_analysis = news_analysis
        last_news_time = datetime.now().strftime('%Y/%m/%d %H:%M')
        last_selected_news = selected
        print(f"  📝  تحلیل ذخیره شد برای گفتگو")
    else:
        print("  ℹ️  تحلیلی برای ذخیره وجود ندارد")

    if not selected and not calendar_events:
        print("  ℹ️   هیچ محتوایی برای ارسال نیست")
        return

    now = datetime.now().strftime('%Y/%m/%d  |  %H:%M')
    
    msg = f"🥇 <b>اخبار طلا و بازار جهانی</b>\n"
    msg += f"🤖 <i>تحلیل توسط هوش مصنوعی</i>\n"
    msg += f"🕐 {now}\n"
    msg += "═" * 30 + "\n\n"

    if selected:
        msg += "📰 <b>اخبار مهم بازار</b>\n"
        msg += "─" * 30 + "\n\n"

        for i, a in enumerate(selected, 1):
            title_fa = a.get('title_fa', a['title'])
            impact = a.get('impact', '')
            direction = a.get('direction', '')

            msg += f"<b>{i}. {title_fa}</b>\n"
            if impact:
                msg += f"📌 {impact}\n"
            if direction:
                msg += f"📈 {direction}\n"
            msg += f"📰 {a['source']}  |  <a href='{a['url']}'>منبع</a>\n\n"

        if news_analysis:
            msg += "─" * 30 + "\n"
            msg += "📊 <b>تحلیل جامع اخبار</b>\n\n"
            msg += news_analysis + "\n"

    if calendar_events or calendar_analysis:
        if selected:
            msg += "\n" + "═" * 30 + "\n\n"
        
        msg += "📅 <b>رویدادهای اقتصادی امروز</b>\n"
        msg += "─" * 30 + "\n\n"

        if calendar_events:
            impact_icon = {'High': '🔴', 'Medium': '🟡', 'Low': '⚪'}
            
            for e in calendar_events:
                country = e.get('country', '')
                impact = e.get('impact', '')
                title = e.get('title', '')
                ev_time = e.get('time', '--:--')
                actual = e.get('actual', '') or '—'
                forecast = e.get('forecast', '') or '—'
                previous = e.get('previous', '') or '—'
                icon = impact_icon.get(impact, '⚪')

                msg += f"{icon} <b>{title}</b> [{country}]\n"
                msg += f"⏰ {ev_time}  |  قبلی: <code>{previous}</code>  |  پیش‌بینی: <code>{forecast}</code>  |  واقعی: <code>{actual}</code>\n"
                msg += "\n"

        if calendar_analysis:
            msg += "─" * 30 + "\n"
            msg += "🔬 <b>تحلیل رویدادهای اقتصادی</b>\n\n"

            for ev in calendar_analysis.get('events', []):
                msg += f"▪️ <b>{ev.get('title', '')}</b>\n"
                msg += f"   {ev.get('role', '')}\n"
                msg += f"   📈 {ev.get('gold_impact', '')}\n"
                msg += "\n"

            summary = calendar_analysis.get('summary', '')
            if summary:
                msg += f"💬 <b>جمع‌بندی:</b> {summary}\n"

    if send_long_message(msg):
        print("  ✅  پیام ارسال شد!")
        if selected:
            for a in selected:
                sent_cache.add(a['title'])
            save_sent_cache(sent_cache)
    else:
        print("  ❌  ارسال ناموفق.")

# ═══════════════════════════════════════════════════════════
#  🚀  نقطه شروع
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 45)
    print("   🤖  ربات اخبار طلا — نسخه نهایی")
    print("=" * 45)
    print("🐍 Python version:", sys.version)

    # تنظیم Webhook
    webhook_url = "https://gold-news-bot-rwg4.onrender.com/webhook"
    set_webhook_url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"
    
    try:
        response = requests.get(set_webhook_url)
        if response.ok:
            print("✅ Webhook تنظیم شد:", response.json())
        else:
            print("⚠️ خطا در تنظیم Webhook:", response.status_code, response.text)
    except Exception as e:
        print(f"⚠️ خطا در تنظیم Webhook: {e}")

    run()
    schedule.every(4).hours.do(run)

    print("\n⏰  هر ۴ ساعت یک‌بار | Ctrl+C برای خروج\n")
    print("🟢 ربات در حال اجراست...")
    print("🔍 جستجوی وب با SerpApi فعال است.")
    print("💰 قیمت طلا از GoldAPI دریافت میشود.")

    app.run(host='0.0.0.0', port=10000)

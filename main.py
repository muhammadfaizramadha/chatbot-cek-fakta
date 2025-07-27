import logging
import os
import re
import requests
import json
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# --- INITIAL CONFIGURATION ---
load_dotenv()

# Credentials from .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- NOTIFICATION MANAGEMENT ---
SUBSCRIBERS_FILE = 'subscribers.json'
subscribers = set()
last_sent_article_url = None

def load_subscribers():
    """Load subscriber list from JSON file."""
    global subscribers
    try:
        with open(SUBSCRIBERS_FILE, 'r') as f:
            subscribers = set(json.load(f))
            logger.info(f"Successfully loaded {len(subscribers)} subscribers.")
    except FileNotFoundError:
        logger.info("subscribers.json not found, starting with an empty list.")
        subscribers = set()

def save_subscribers():
    """Save subscriber list to JSON file."""
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(list(subscribers), f)

def fetch_latest_hoaxes(count: int = 1) -> list[dict] | None:
    """Fetch the latest hoax clarification articles from NewsAPI."""
    # --- THIS IS THE MODIFIED PART ---
    # The query is broadened to get more results
    query = '"hoax" OR "klarifikasi" OR "cek fakta" OR "berita bohong" OR "disinformasi"'
    url = "https://newsapi.org/v2/everything"
    params = {
        'q': query,
        'language': 'id',
        'sortBy': 'publishedAt', # Get the newest
        'apiKey': NEWSAPI_KEY,
        'pageSize': count
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('totalResults', 0) > 0:
            return data.get('articles', []) # Return a list of articles
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching latest hoaxes from NewsAPI: {e}")
    return None

async def send_hoax_notification(context: ContextTypes.DEFAULT_TYPE):
    """Function run periodically to send notifications."""
    global last_sent_article_url
    logger.info("Running hoax notification check job...")

    latest_articles = fetch_latest_hoaxes(count=1)

    if latest_articles:
        latest_article = latest_articles[0]
        if latest_article and latest_article.get('url') != last_sent_article_url:
            last_sent_article_url = latest_article.get('url')
            title = latest_article.get('title')
            url = latest_article.get('url')
            source = latest_article.get('source', {}).get('name')

            message = (
                f"🔔 *Notifikasi Hoaks Terbaru*\n\n"
                f"*{title}*\n"
                f"Sumber: {source}\n\n"
                f"Baca klarifikasi lengkapnya di sini:\n{url}\n\n"
                f"_Untuk berhenti menerima notifikasi, ketik /unsubscribe_"
            )

            for chat_id in list(subscribers):
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                    logger.info(f"Sent notification to {chat_id}")
                except Exception as e:
                    logger.warning(f"Failed to send notification to {chat_id}: {e}. Removing subscriber.")
                    subscribers.discard(chat_id)
                    save_subscribers()


# --- EXISTING FEATURE FUNCTIONS ---
def cross_reference_news(query: str) -> str:
    """Search query on mainstream Indonesian media via NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {'q': query, 'language': 'id', 'sortBy': 'relevancy', 'apiKey': NEWSAPI_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data['totalResults'] > 0:
            result_text = "📰 *Liputan dari Media Mainstream:*\n\n"
            for article in data['articles'][:3]:
                result_text += f"▪️ *{article['source']['name']}:* {article['title']}\n  [Baca di sini]({article['url']})\n\n"
            return result_text
        else:
            return "📰 *Liputan dari Media Mainstream:*\n\nTidak ditemukan liputan signifikan terkait isu ini di media arus utama."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling NewsAPI: {e}")
        return "Gagal menghubungi layanan berita mainstream."

def analyze_url_safety(url: str) -> str:
    """Analyze URL safety via Google Web Risk API."""
    api_url = f"https://webrisk.googleapis.com/v1/uris:search?key={GOOGLE_API_KEY}"
    payload = {'uri': url, 'threatTypes': ['MALWARE', 'SOCIAL_ENGINEERING', 'UNWANTED_SOFTWARE']}
    try:
        response = requests.post(api_url, json=payload)
        data = response.json()
        if 'threat' in data:
            threat_type = data['threat']['threatTypes'][0].replace('_', ' ').title()
            return f"🚨 *Peringatan Keamanan!* 🚨\n\nLink yang Anda kirim terdeteksi berbahaya oleh Google sebagai: *{threat_type}*. Sangat disarankan untuk *TIDAK MEMBUKA* link tersebut."
        else:
            return f"✅ *Link Aman* ✅\n\nGoogle tidak menemukan ancaman keamanan pada link yang Anda kirim."
    except Exception as e:
        logger.error(f"Error calling Google Web Risk API: {e}")
        return "Gagal menganalisis keamanan link."

def verify_image(image_url: str) -> str:
    """Perform a reverse image search via SerpApi."""
    params = {"engine": "google_reverse_image", "image_url": image_url, "api_key": SERPAPI_KEY}
    try:
        response = requests.get('https://serpapi.com/search.json', params=params)
        response.raise_for_status()
        results = response.json()
        if 'image_results' in results and len(results['image_results']) > 0:
            result_text = "🖼️ *Hasil Verifikasi Gambar (Reverse Image Search):*\n\nGambar ini pernah muncul di situs-situs berikut:\n\n"
            for item in results['image_results'][:5]:
                result_text += f"▪️ *{item['source']}*: {item['title']}\n  [Lihat di sini]({item['link']})\n\n"
            result_text += "_Cermati apakah konteks penggunaan gambar di situs-situs tersebut sama dengan berita yang Anda terima._"
            return result_text
        else:
            return "🖼️ *Hasil Verifikasi Gambar:*\n\nTidak ditemukan gambar serupa di internet. Ini bisa berarti gambar ini baru atau unik."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling SerpApi: {e}")
        return "Gagal melakukan verifikasi gambar."

def search_fact_check(query: str) -> str:
    """Search for a query on trusted fact-checking sites."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': GOOGLE_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        if 'items' in results and len(results['items']) > 0:
            formatted_results = "🔍 *Hasil Cek Fakta dari Situs Terpercaya:*\n\n"
            for item in results['items'][:3]:
                title = item.get('title')
                link = item.get('link')
                snippet = item.get('snippet', '').replace('\n', ' ')
                formatted_results += f"📝 *Judul:* {title}\n🔗 *Link:* {link}\n📄 *Kutipan:* {snippet}\n\n"
            return formatted_results
        else:
            return "❌ *Tidak ditemukan di database cek fakta.*"
    except requests.exceptions.RequestException:
        return "Gagal menghubungi layanan cek fakta."

# --- TELEGRAM HANDLERS (Updated) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with an updated feature menu."""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔔 Atur Notifikasi Hoaks", callback_data='fitur_notifikasi')],
        [InlineKeyboardButton("📰 Lihat Hoaks Terbaru", callback_data='fitur_lihat_hoaks')],
        [InlineKeyboardButton("🔍 Cek Teks / Link Hoaks", callback_data='fitur_cek_teks')],
        [InlineKeyboardButton("🖼️ Verifikasi Gambar", callback_data='fitur_verifikasi_gambar')],
        [InlineKeyboardButton("💡 Panduan Kenali Hoax", callback_data='fitur_panduan')],
        [InlineKeyboardButton("ℹ️ Tentang Bot Ini", callback_data='fitur_tentang')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"Halo, *{user.mention_markdown_v2()}*\\!\n\nSelamat datang di Bot Cek Fakta v4\\.0\\.\n\nSaya kini bisa menampilkan daftar hoaks terbaru sesuai permintaan Anda\\. Silakan pilih menu di bawah ini:"
    await update.message.reply_markdown_v2(text, reply_markup=reply_markup)

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /subscribe command."""
    chat_id = update.message.chat_id
    if chat_id in subscribers:
        await update.message.reply_text("Anda sudah berlangganan notifikasi.")
    else:
        subscribers.add(chat_id)
        save_subscribers()
        await update.message.reply_text("✅ Berhasil! Anda akan menerima notifikasi hoaks terbaru dari kami.")
        logger.info(f"User {chat_id} has subscribed.")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /unsubscribe command."""
    chat_id = update.message.chat_id
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text("Anda telah berhenti berlangganan notifikasi.")
        logger.info(f"User {chat_id} has unsubscribed.")
    else:
        await update.message.reply_text("Anda memang belum berlangganan notifikasi.")

async def latest_hoaxes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /hoaxterbaru command."""
    waiting_message = await update.message.reply_text("📰 Sedang mengambil berita hoaks terbaru, mohon tunggu...")
    
    articles = fetch_latest_hoaxes(count=5)
    
    if articles:
        message = "📰 *5 Klarifikasi Hoaks Terbaru:*\n\n---\n\n"
        for article in articles:
            title = article.get('title')
            url = article.get('url')
            source = article.get('source', {}).get('name', 'N/A')
            message += f"*{title}*\n"
            message += f"Sumber: {source}\n"
            message += f"[Baca selengkapnya]({url})\n\n---\n\n"
        
        await waiting_message.edit_text(message, parse_mode='Markdown', disable_web_page_preview=True)
    else:
        await waiting_message.edit_text("Gagal mengambil berita hoaks terbaru saat ini. Silakan coba lagi nanti.")

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process text messages: Fact Check, Cross-Reference, and URL Safety Check."""
    query = update.message.text
    logger.info(f"Received query from user {update.effective_user.id}: {query}")
    
    url_pattern = r'https?://\S+'
    found_urls = re.findall(url_pattern, query)
    
    waiting_message = await update.message.reply_text("⏳ Sedang menganalisis, mohon tunggu...")
    
    security_result = ""
    if found_urls:
        security_result = analyze_url_safety(found_urls[0]) + "\n\n---\n\n"
        
    fact_check_result = search_fact_check(query) + "\n\n---\n\n"
    cross_ref_result = cross_reference_news(query)
    
    final_result = security_result + fact_check_result + cross_ref_result
    await waiting_message.edit_text(final_result, parse_mode='Markdown', disable_web_page_preview=True)

async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler to process images sent by the user."""
    photo_file = await update.message.photo[-1].get_file()
    image_url = photo_file.file_path

    logger.info(f"Received image from user {update.effective_user.id} for verification.")
    waiting_message = await update.message.reply_text("🖼️ Sedang memverifikasi gambar, mohon tunggu...")
    
    result_text = verify_image(image_url)
    await waiting_message.edit_text(result_text, parse_mode='Markdown', disable_web_page_preview=True)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle actions when buttons are pressed."""
    query = update.callback_query
    await query.answer()
    
    # Each block now handles its own response
    if query.data == 'fitur_notifikasi':
        text = (
            "� *Fitur Notifikasi Hoaks Terbaru*\n\n"
            "Dapatkan peringatan dini mengenai hoaks atau disinformasi yang sedang viral langsung di chat Anda.\n\n"
            "Gunakan perintah berikut:\n"
            "• `/subscribe` - untuk *mulai* menerima notifikasi.\n"
            "• `/unsubscribe` - untuk *berhenti* menerima notifikasi."
        )
        await query.message.reply_markdown(text, disable_web_page_preview=True)
        
    elif query.data == 'fitur_lihat_hoaks':
        text = "Untuk melihat 5 klarifikasi hoaks terbaru, silakan gunakan perintah:\n\n/hoaxterbaru"
        await query.message.reply_markdown(text, disable_web_page_preview=True)
        
    elif query.data == 'fitur_cek_teks':
        text = "Silakan kirimkan potongan berita, judul artikel, atau link yang ingin Anda periksa."
        await query.message.reply_markdown(text, disable_web_page_preview=True)
        
    elif query.data == 'fitur_verifikasi_gambar':
        text = "Silakan kirimkan sebuah gambar (bukan sebagai file/dokumen) untuk saya coba verifikasi."
        await query.message.reply_markdown(text, disable_web_page_preview=True)
        
    elif query.data == 'fitur_panduan':
        # --- THIS IS THE MODIFIED PART ---
        photo_url = "D:\KULIAH\SKRIPSI\chatbot-cek-fakta\panduan_kenali_hoax.webp"
        caption_text = "Berikut adalah panduan visual untuk mengenali hoaks."
        await query.message.reply_photo(photo=photo_url, caption=caption_text)
        
    elif query.data == 'fitur_tentang':
        text = "*ℹ️ Tentang Bot Cek Fakta v4.0*\n\nBot ini menggabungkan beberapa API untuk verifikasi dan notifikasi:\n- *Google Custom Search* (Cek Fakta)\n- *Google Web Risk* (Cek Link)\n- *NewsAPI* (Cek Lintas Media & Notifikasi)\n- *SerpApi* (Cek Gambar)"
        await query.message.reply_markdown(text, disable_web_page_preview=True)
        
    else:
        text = "Fitur tidak dikenali."
        await query.message.reply_markdown(text, disable_web_page_preview=True)

async def crosscheck_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /crosscheck command."""
    try:
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Silakan masukkan topik setelah perintah. Contoh: `/crosscheck kenaikan harga BBM`")
            return
            
        waiting_message = await update.message.reply_text("📰 Sedang mencari di media mainstream...")
        result = cross_reference_news(query)
        await waiting_message.edit_text(result, parse_mode='Markdown', disable_web_page_preview=True)
    except (IndexError, ValueError):
        await update.message.reply_text("Format salah. Gunakan: `/crosscheck <topik berita>`")


def main() -> None:
    """Main function to run the bot."""
    # Load subscribers on bot startup
    load_subscribers()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # --- SCHEDULE NOTIFICATION JOB ---
    job_queue = application.job_queue
    # Run the job every 4 hours (14400 seconds), starting 15 seconds after the bot runs
    job_queue.run_repeating(send_hoax_notification, interval=14400, first=15)

    # Register all handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("hoaxterbaru", latest_hoaxes_command))
    application.add_handler(CommandHandler("crosscheck", crosscheck_command_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))
    application.add_handler(MessageHandler(filters.PHOTO, image_handler))

    logger.info("Bot Cek Fakta v4.0 (with Visual Guide) is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
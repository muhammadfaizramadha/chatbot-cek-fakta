import logging
import os
import re
import requests
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# --- KONFIGURASI AWAL ---
load_dotenv()

# Kredensial dari .env
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

# --- FUNGSI-FUNGSI FITUR BARU ---

def cross_reference_news(query: str) -> str:
    """FITUR BARU: Mencari query di media mainstream Indonesia via NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {
        'q': query,
        'language': 'id',
        'sortBy': 'relevancy',
        'apiKey': NEWSAPI_KEY
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data['totalResults'] > 0:
            result_text = "📰 *Liputan dari Media Mainstream:*\n\n"
            for article in data['articles'][:3]:
                result_text += f"▪️ *{article['source']['name']}:* {article['title']}\n"
                result_text += f"  [Baca di sini]({article['url']})\n\n"
            return result_text
        else:
            return "📰 *Liputan dari Media Mainstream:*\n\nTidak ditemukan liputan signifikan terkait isu ini di media arus utama."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error saat menghubungi NewsAPI: {e}")
        return "Gagal menghubungi layanan berita mainstream."

def analyze_url_safety(url: str) -> str:
    """FITUR BARU: Menganalisis keamanan URL via Google Web Risk API."""
    api_url = f"https://webrisk.googleapis.com/v1/uris:search?key={GOOGLE_API_KEY}"
    payload = {
        'uri': url,
        'threatTypes': ['MALWARE', 'SOCIAL_ENGINEERING', 'UNWANTED_SOFTWARE']
    }
    try:
        response = requests.post(api_url, json=payload)
        data = response.json()
        if 'threat' in data:
            threat_type = data['threat']['threatTypes'][0].replace('_', ' ').title()
            return f"🚨 *Peringatan Keamanan!* 🚨\n\nLink yang Anda kirim terdeteksi berbahaya oleh Google sebagai: *{threat_type}*. Sangat disarankan untuk *TIDAK MEMBUKA* link tersebut."
        else:
            return f"✅ *Link Aman* ✅\n\nGoogle tidak menemukan ancaman keamanan pada link yang Anda kirim."
    except Exception as e:
        logger.error(f"Error saat menghubungi Google Web Risk API: {e}")
        return "Gagal menganalisis keamanan link."

def verify_image(image_url: str) -> str:
    """FITUR BARU: Melakukan reverse image search via SerpApi."""
    params = {
        "engine": "google_reverse_image",
        "image_url": image_url,
        "api_key": SERPAPI_KEY
    }
    try:
        response = requests.get('https://serpapi.com/search.json', params=params)
        response.raise_for_status()
        results = response.json()
        if 'image_results' in results and len(results['image_results']) > 0:
            result_text = "🖼️ *Hasil Verifikasi Gambar (Reverse Image Search):*\n\nGambar ini pernah muncul di situs-situs berikut:\n\n"
            for item in results['image_results'][:5]:
                result_text += f"▪️ *{item['source']}*: {item['title']}\n"
                result_text += f"  [Lihat di sini]({item['link']})\n\n"
            result_text += "_Cermati apakah konteks penggunaan gambar di situs-situs tersebut sama dengan berita yang Anda terima._"
            return result_text
        else:
            return "🖼️ *Hasil Verifikasi Gambar:*\n\nTidak ditemukan gambar serupa di internet. Ini bisa berarti gambar ini baru atau unik."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error saat menghubungi SerpApi: {e}")
        return "Gagal melakukan verifikasi gambar."

# --- FUNGSI LAMA (Tidak berubah) ---
def search_fact_check(query: str) -> str:
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

# --- HANDLER TELEGRAM (Diperbarui) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan sambutan dengan tombol fitur yang sudah diperbarui."""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔍 Cek Teks / Link Hoaks", callback_data='fitur_cek_teks')],
        [InlineKeyboardButton("🖼️ Verifikasi Gambar", callback_data='fitur_verifikasi_gambar')],
        [InlineKeyboardButton("📰 Cek Lintas Media", callback_data='fitur_crosscheck')],
        [InlineKeyboardButton("💡 Panduan Kenali Hoax", callback_data='fitur_panduan')],
        [InlineKeyboardButton("ℹ️ Tentang Bot Ini", callback_data='fitur_tentang')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"Halo, *{user.mention_markdown_v2()}*\\!\n\nSelamat datang di Bot Cek Fakta v2\\.0\\.\n\nSaya kini memiliki lebih banyak fitur untuk membantu Anda memverifikasi informasi\\. Silakan pilih menu di bawah ini:"
    await update.message.reply_markdown_v2(text, reply_markup=reply_markup)

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Memproses pesan teks: Cek Fakta, Cek Lintas Media, dan Cek Keamanan Link."""
    query = update.message.text
    logger.info(f"Menerima query dari user {update.effective_user.id}: {query}")
    
    # Deteksi URL dalam pesan
    url_pattern = r'https?://\S+'
    found_urls = re.findall(url_pattern, query)
    
    waiting_message = await update.message.reply_text("⏳ Sedang menganalisis, mohon tunggu...")
    
    # 1. Analisis Keamanan Link (jika ada link)
    security_result = ""
    if found_urls:
        security_result = analyze_url_safety(found_urls[0]) + "\n\n---\n\n"
        
    # 2. Cek Fakta
    fact_check_result = search_fact_check(query) + "\n\n---\n\n"
    
    # 3. Cek Lintas Media
    cross_ref_result = cross_reference_news(query)
    
    final_result = security_result + fact_check_result + cross_ref_result
    await waiting_message.edit_text(final_result, parse_mode='Markdown', disable_web_page_preview=True)

async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler baru untuk memproses gambar yang dikirim pengguna."""
    photo_file = await update.message.photo[-1].get_file()
    image_url = photo_file.file_path

    logger.info(f"Menerima gambar dari user {update.effective_user.id} untuk verifikasi.")
    waiting_message = await update.message.reply_text("🖼️ Sedang memverifikasi gambar, mohon tunggu...")
    
    result_text = verify_image(image_url)
    await waiting_message.edit_text(result_text, parse_mode='Markdown', disable_web_page_preview=True)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani aksi ketika tombol ditekan."""
    query = update.callback_query
    await query.answer()
    
    # Teks untuk setiap tombol
    if query.data == 'fitur_cek_teks':
        text = "Silakan kirimkan potongan berita, judul artikel, atau link yang ingin Anda periksa."
    elif query.data == 'fitur_verifikasi_gambar':
        text = "Silakan kirimkan sebuah gambar (bukan sebagai file/dokumen) untuk saya coba verifikasi."
    elif query.data == 'fitur_crosscheck':
        text = "Ketik `/crosscheck <topik berita>` untuk melihat liputan dari media mainstream.\nContoh: `/crosscheck pemilu 2024`"
    elif query.data == 'fitur_panduan':
        text = "*💡 Panduan Sederhana Mengenali Hoax:*\n\n1. *Jangan Panik*, berita heboh seringkali memancing emosi.\n2. *Periksa Sumbernya*, apakah dari media kredibel?\n3. *Cek Judul Provokatif*, hoaks seringkali sensasional.\n4. *Bandingkan dengan Berita Lain*, apakah media besar juga meliputnya?"
    elif query.data == 'fitur_tentang':
        text = "*ℹ️ Tentang Bot Cek Fakta v2.0*\n\nBot ini menggabungkan beberapa API untuk verifikasi:\n- *Google Custom Search* (Cek Fakta)\n- *Google Web Risk* (Cek Link)\n- *NewsAPI* (Cek Lintas Media)\n- *SerpApi* (Cek Gambar)"
    else:
        text = "Fitur tidak dikenali."
        
    await query.message.reply_markdown(text)

async def crosscheck_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler untuk perintah /crosscheck"""
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
    """Fungsi utama untuk menjalankan bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Daftarkan semua handler
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("crosscheck", crosscheck_command_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))
    application.add_handler(MessageHandler(filters.PHOTO, image_handler)) # Handler baru untuk foto

    logger.info("Bot Cek Fakta v2.0 mulai berjalan...")
    application.run_polling()

if __name__ == "__main__":
    main()
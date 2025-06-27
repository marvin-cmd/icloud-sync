# --------------------------------------------------------------------------------- #
# icloud_s3_sync_bot.py - VERSI 7.0 (FINAL) - Konfigurasi .env & Notifikasi Lengkap #
# --------------------------------------------------------------------------------- #

import os
import sys
import time
import logging
import json
import boto3
import requests
from botocore.exceptions import ClientError
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException
from dotenv import load_dotenv

# Memuat variabel dari file .env ke dalam environment script
load_dotenv()

# --- 1. KONFIGURASI (Dibaca dari Environment / .env) ---
ICLOUD_USERNAME = os.environ.get('ICLOUD_ID')
ICLOUD_ALBUM_NAME = os.environ.get('ICLOUD_ALBUM_NAME', 'Nikon')
CREDENTIALS_FILE = os.environ.get('CREDENTIALS_FILE', 'credentials.json')
COOKIE_DIRECTORY = os.environ.get('COOKIE_DIRECTORY', 'icloud_session')
DOWNLOAD_PATH = os.environ.get('DOWNLOAD_PATH', 'downloaded_photos')
PROCESSED_LOG_FILE = os.environ.get('PROCESSED_LOG_FILE', 'processed.log')
CHECK_INTERVAL_SECONDS = int(os.environ.get('CHECK_INTERVAL_SECONDS', 45))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')

# --- 2. SETUP LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

# --- 3. FUNGSI-FUNGSI BANTU ---

def send_telegram_notification(message):
    """Mengirim pesan notifikasi ke pengguna melalui Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Token atau Chat ID Telegram tidak diatur di .env. Melewatkan notifikasi.")
        return
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(api_url, data=params, timeout=10)
        if response.status_code != 200:
            logging.error(f"Gagal mengirim notifikasi Telegram: {response.text}")
    except Exception as e:
        logging.error(f"Terjadi error saat mencoba mengirim notifikasi Telegram: {e}")

def load_s3_credentials(filepath):
    """Membaca kredensial S3-compatible dari file JSON."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"File kredensial tidak ditemukan di: {filepath}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        logging.error(f"File kredensial '{filepath}' tidak valid atau ada key yang hilang: {e}")
        return None

def load_processed_files():
    """Memuat daftar nama file yang sudah diproses dari file log."""
    if not os.path.exists(PROCESSED_LOG_FILE):
        return set()
    with open(PROCESSED_LOG_FILE, 'r') as f:
        return set(line.strip() for line in f)

def save_processed_file(filename):
    """Menyimpan nama file yang baru diproses ke file log."""
    with open(PROCESSED_LOG_FILE, 'a') as f:
        f.write(filename + '\n')

def upload_to_s3_compatible(local_file_path, s3_object_name, credentials):
    """Mengunggah file ke S3-compatible storage (R2, MinIO, dll)."""
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=credentials['endpoint_url'],
            aws_access_key_id=credentials['access_key'],
            aws_secret_access_key=credentials['secret_key'],
            region_name=credentials.get('region', 'us-east-1')
        )
        bucket_name = credentials['bucket']
        logging.info(f"    Mengunggah '{s3_object_name}' ke bucket '{bucket_name}' di {credentials['provider']}...")
        s3_client.upload_file(local_file_path, bucket_name, s3_object_name)
        logging.info("    Upload berhasil.")
        return True
    except ClientError as e:
        logging.error(f"    Gagal saat upload (ClientError): {e}")
        return False
    except Exception as e:
        logging.error(f"    Terjadi error tak terduga saat upload: {e}")
        return False

def process_new_photos(api, processed_files, s3_credentials):
    """Memeriksa foto baru, memprosesnya, dan mengirim notifikasi status upload."""
    logging.info(f"Mencari album dengan nama: '{ICLOUD_ALBUM_NAME}'...")
    try:
        album = api.photos.albums[ICLOUD_ALBUM_NAME]
    except KeyError:
        error_msg = f"Album '{ICLOUD_ALBUM_NAME}' tidak ditemukan!"
        logging.error(error_msg)
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg}")
        return

    logging.info(f"Album ditemukan. Memeriksa {len(album)} foto...")
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    successfully_uploaded_files = []
    
    for photo in album:
        if photo.filename not in processed_files:
            logging.info(f"--> FOTO BARU DITEMUKAN: {photo.filename}")
            local_file_path = os.path.join(DOWNLOAD_PATH, photo.filename)
            try:
                logging.info(f"    Mengunduh '{photo.filename}' dari iCloud...")
                download = photo.download('original')
                with open(local_file_path, 'wb') as f:
                    f.write(download.content)
                
                upload_successful = upload_to_s3_compatible(local_file_path, photo.filename, s3_credentials)
                
                if upload_successful:
                    successfully_uploaded_files.append(photo.filename)
                    save_processed_file(photo.filename)
                    processed_files.add(photo.filename)
                    os.remove(local_file_path)
                else:
                    failure_msg = f"⚠️ *Gagal Upload*\n\nFile `{photo.filename}` gagal diunggah ke S3/R2."
                    logging.warning(failure_msg)
                    send_telegram_notification(failure_msg)
                    # KIRIM SINYAL KE SERVER NODE.JS
                    if R2_PUBLIC_URL:
                        try:
                            photo_url = f"{R2_PUBLIC_URL}/{photo.filename}"
                            notification_url = "http://localhost:3000/notify-new-photo" # Endpoint di Node.js
                            requests.post(notification_url, json={"url": photo_url, "filename": photo.filename}, timeout=5)
                            logging.info(f"    Sinyal foto baru untuk '{photo.filename}' telah dikirim ke server Node.js.")
                        except Exception as e:
                            logging.error(f"    Gagal mengirim sinyal ke server Node.js: {e}")
            
            except Exception as e:
                error_msg = f"‼️ *Error Proses*\n\nTerjadi error saat memproses file `{photo.filename}`: `{e}`"
                logging.error(error_msg)
                send_telegram_notification(error_msg)

    if successfully_uploaded_files:
        count = len(successfully_uploaded_files)
        success_msg = f"✅ *Sinkronisasi Berhasil*\n\nTelah mengunggah *{count}* foto baru."
        if count <= 5:
            filenames_str = "\n- `".join(successfully_uploaded_files)
            success_msg += f"\n\nFile yang diunggah:\n- `{filenames_str}`"
        logging.info(success_msg)
        send_telegram_notification(success_msg)

# --- 4. BAGIAN EKSEKUSI UTAMA SCRIPT ---
if __name__ == "__main__":
    logging.info("Memulai script iCloud S3-Compatible Sync Bot...")
    send_telegram_notification("🚀 *iCloud Sync Bot Dimulai*\n\nScript sedang berjalan dan akan memulai proses sinkronisasi.")

    s3_creds = load_s3_credentials(CREDENTIALS_FILE)
    if not s3_creds:
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\nGagal memuat kredensial dari `{CREDENTIALS_FILE}`. Script berhenti.")
        sys.exit(1)
    
    if not ICLOUD_USERNAME:
        error_msg = "ICLOUD_ID tidak diatur di file .env"
        logging.error(error_msg)
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg}")
        sys.exit(1)

    logging.info(f"Menggunakan Apple ID: {ICLOUD_USERNAME}")
    os.makedirs(COOKIE_DIRECTORY, exist_ok=True)
    
    try:
        api = PyiCloudService(ICLOUD_USERNAME, cookie_directory=COOKIE_DIRECTORY)
    except PyiCloudFailedLoginException as e:
        error_msg = f"Login iCloud Gagal! Periksa kredensial di Keychain. Error: {e}"
        logging.error(error_msg)
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg}")
        sys.exit(1)

    if api.requires_2fa:
        logging.info("Otentikasi Dua Faktor (2FA) dibutuhkan.")
        code = input("Masukkan kode 6 digit: ")
        if not api.validate_2fa_code(code):
            error_msg = "Kode 2FA salah."
            logging.error(error_msg)
            send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg} Script berhenti.")
            sys.exit(1)

    if not api.is_trusted_session:
        error_msg = "Login iCloud gagal atau sesi tidak terpercaya."
        logging.error(error_msg)
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg} Script berhenti.")
        sys.exit(1)
    
    logging.info("Login ke iCloud berhasil via Keychain dan/atau Sesi.")
    processed_files = load_processed_files()

    try:
        while True:
            process_new_photos(api, processed_files, s3_creds)
            logging.info(f"Pengecekan selesai. Akan menunggu selama {CHECK_INTERVAL_SECONDS} detik.")
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logging.info("Script dihentikan oleh pengguna.")
        send_telegram_notification("👋 *iCloud Sync Bot Dihentikan*\n\nScript dihentikan secara manual oleh pengguna.")
    except Exception as e:
        error_msg = f"Terjadi error tak terduga di loop utama: {e}"
        logging.critical(error_msg)
        send_telegram_notification(f"‼️ *ERROR KRITIS*\n\n{error_msg}\n\nScript akan berhenti.")

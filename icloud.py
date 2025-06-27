# --------------------------------------------------------------------------------- #
# icloud_s3_sync_bot.py - VERSI 5.0 DENGAN KONFIGURASI DI FILE .ENV                 #
# --------------------------------------------------------------------------------- #

import os
import sys
import time
import logging
import json
import boto3
from botocore.exceptions import ClientError
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException
from dotenv import load_dotenv  # <-- DITAMBAHKAN

# Memuat variabel dari file .env ke dalam environment script
load_dotenv() # <-- DITAMBAHKAN

# --- 1. KONFIGURASI (Dibaca dari Environment yang dimuat oleh dotenv) ---
ICLOUD_USERNAME = os.environ.get('ICLOUD_ID')
ICLOUD_ALBUM_NAME = os.environ.get('ICLOUD_ALBUM_NAME', 'Nikon') # 'Nikon' sebagai default
CREDENTIALS_FILE = os.environ.get('CREDENTIALS_FILE', 'credentials.json')
COOKIE_DIRECTORY = os.environ.get('COOKIE_DIRECTORY', 'icloud_session')
DOWNLOAD_PATH = os.environ.get('DOWNLOAD_PATH', 'downloaded_photos')
PROCESSED_LOG_FILE = os.environ.get('PROCESSED_LOG_FILE', 'processed.log')

# Variabel interval dibaca sebagai string, jadi perlu diubah ke integer
# Menambahkan nilai default 45 jika tidak ditemukan di .env
CHECK_INTERVAL_SECONDS = int(os.environ.get('CHECK_INTERVAL_SECONDS', 45))

# --- 2. SETUP LOGGING (Tidak ada perubahan) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)

# --- FUNGSI-FUNGSI BANTU (Tidak ada perubahan) ---
# ... (Salin semua fungsi bantu: load_s3_credentials, load_processed_files, save_processed_file, upload_to_s3_compatible, process_new_photos) ...
# ... dari script versi sebelumnya ke sini. Tidak ada yang perlu diubah di dalam fungsi-fungsi tersebut. ...
def load_s3_credentials(filepath):
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
    if not os.path.exists(PROCESSED_LOG_FILE): return set()
    with open(PROCESSED_LOG_FILE, 'r') as f:
        return set(line.strip() for line in f)

def save_processed_file(filename):
    with open(PROCESSED_LOG_FILE, 'a') as f:
        f.write(filename + '\n')

def upload_to_s3_compatible(local_file_path, s3_object_name, credentials):
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
    logging.info(f"Mencari album dengan nama: '{ICLOUD_ALBUM_NAME}'...")
    try:
        album = api.photos.albums[ICLOUD_ALBUM_NAME]
    except KeyError:
        logging.error(f"Album '{ICLOUD_ALBUM_NAME}' tidak ditemukan!")
        return
    logging.info(f"Album ditemukan. Memeriksa {len(album)} foto...")
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
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
                    save_processed_file(photo.filename)
                    processed_files.add(photo.filename)
                    os.remove(local_file_path)
                    logging.info(f"    File lokal '{photo.filename}' dihapus.")
            except Exception as e:
                logging.error(f"    Gagal memproses {photo.filename}: {e}")

# --- 5. BAGIAN EKSEKUSI SCRIPT (Tidak ada perubahan logika) ---
if __name__ == "__main__":
    logging.info("Memulai script iCloud S3-Compatible Sync Bot...")
    
    s3_creds = load_s3_credentials(CREDENTIALS_FILE)
    if not s3_creds:
        sys.exit(1)
    logging.info(f"Kredensial untuk '{s3_creds['provider']}' berhasil dimuat. Target bucket: {s3_creds['bucket']}")
    
    if not ICLOUD_USERNAME:
        logging.error("Harap atur ICLOUD_ID di file .env")
        sys.exit(1)
    
    logging.info(f"Menggunakan Apple ID: {ICLOUD_USERNAME}")
    
    os.makedirs(COOKIE_DIRECTORY, exist_ok=True)
    try:
        api = PyiCloudService(ICLOUD_USERNAME, cookie_directory=COOKIE_DIRECTORY)
    except PyiCloudFailedLoginException as e:
        logging.error(f"Login iCloud Gagal! Error: {e}")
        sys.exit(1)

    if api.requires_2fa:
        logging.info("Otentikasi Dua Faktor (2FA) dibutuhkan.")
        code = input("Masukkan kode 6 digit: ")
        if not api.validate_2fa_code(code):
            logging.error("Kode 2FA salah.")
            sys.exit(1)

    if not api.is_trusted_session:
        logging.error("Login iCloud gagal atau sesi tidak terpercaya.")
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
        sys.exit(0)

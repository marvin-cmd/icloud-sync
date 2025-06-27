# --------------------------------------------------------------------------------- #
# icloud_s3_sync_bot.py - VERSI 4.0 UNTUK CLOUDFLARE R2 & S3-COMPATIBLE             #
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

# --- 1. KONFIGURASI ---
ICLOUD_USERNAME = os.environ.get('ICLOUD_ID') or "email"
ICLOUD_ALBUM_NAME = "Nikon"
CREDENTIALS_FILE = "credentials.json"
COOKIE_DIRECTORY = "icloud_session"

DOWNLOAD_PATH = "downloaded_photos"
PROCESSED_LOG_FILE = "processed_files.log"
CHECK_INTERVAL_SECONDS = 300

# --- 2. SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)

# --- FUNGSI-FUNGSI BANTU ---

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

def upload_to_s3_compatible(local_file_path, s3_object_name, credentials):
    """Mengunggah file ke S3-compatible storage (R2, MinIO, dll)."""
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=credentials['endpoint_url'],
            aws_access_key_id=credentials['access_key'],
            aws_secret_access_key=credentials['secret_key'],
            region_name=credentials.get('region', 'us-east-1') # Mengambil region dari file, default 'us-east-1'
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

# ... (Fungsi load_processed_files, save_processed_file, dan process_new_photos tetap sama persis seperti sebelumnya) ...
def load_processed_files():
    if not os.path.exists(PROCESSED_LOG_FILE): return set()
    with open(PROCESSED_LOG_FILE, 'r') as f:
        return set(line.strip() for line in f)

def save_processed_file(filename):
    with open(PROCESSED_LOG_FILE, 'a') as f:
        f.write(filename + '\n')

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
                
                # Menggunakan fungsi upload yang sudah digeneralisasi
                upload_successful = upload_to_s3_compatible(local_file_path, photo.filename, s3_credentials)
                
                if upload_successful:
                    save_processed_file(photo.filename)
                    processed_files.add(photo.filename)
                    os.remove(local_file_path)
                    logging.info(f"    File lokal '{photo.filename}' dihapus.")
            except Exception as e:
                logging.error(f"    Gagal memproses {photo.filename}: {e}")


# --- 5. BAGIAN EKSEKUSI SCRIPT ---
if __name__ == "__main__":
    logging.info("Memulai script iCloud S3-Compatible Sync Bot...")
    
    # Memuat kredensial S3 (R2, MinIO, dll)
    s3_creds = load_s3_credentials(CREDENTIALS_FILE)
    if not s3_creds:
        logging.error("Gagal memuat kredensial S3. Script berhenti.")
        sys.exit(1)
    logging.info(f"Kredensial untuk '{s3_creds['provider']}' berhasil dimuat. Target bucket: {s3_creds['bucket']}")
    
    # Logika login iCloud via Keychain/Sesi (tidak ada perubahan)
    if not ICLOUD_USERNAME:
        # Jika username tidak di-hardcode, coba ambil dari keychain atau prompt.
        # Untuk automasi penuh, disarankan menggunakan ICLOUD_ID env var atau di-hardcode.
        logging.warning("ICLOUD_USERNAME tidak diset. pyicloud akan mencoba mencari dari sesi atau keychain.")
    
    os.makedirs(COOKIE_DIRECTORY, exist_ok=True)
    try:
        api = PyiCloudService(ICLOUD_USERNAME, cookie_directory=COOKIE_DIRECTORY)
    except PyiCloudFailedLoginException as e:
        logging.error(f"Login iCloud Gagal! Periksa kredensial atau keychain. Error: {e}")
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

    # Lanjut ke proses utama
    processed_files = load_processed_files()
    try:
        while True:
            process_new_photos(api, processed_files, s3_creds)
            logging.info(f"Pengecekan selesai. Akan menunggu selama {CHECK_INTERVAL_SECONDS / 60:.1f} menit.")
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logging.info("Script dihentikan oleh pengguna.")
        sys.exit(0)

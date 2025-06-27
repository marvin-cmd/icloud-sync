// File: create-admin.js (Versi dengan Debugging Lebih Baik)
require('dotenv').config();
const { Pool } = require('pg');
const bcrypt = require('bcrypt');
const readline = require('readline');
const fs = require('fs');
const path = require('path');

// Cek semua prasyarat sebelum mencoba koneksi
const caPath = path.join(__dirname, 'ca.pem');
if (!fs.existsSync(caPath)) {
    console.error("‼️  Error: File 'ca.pem' tidak ditemukan. Pastikan Anda sudah mengunduhnya dari Aiven dan meletakkannya di folder proyek.");
    process.exit(1);
}

// Konfigurasi Pool dari .env
const pool = new Pool({
    host: process.env.DB_HOST,
    port: process.env.DB_PORT,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_DATABASE,
    ssl: {
        rejectUnauthorized: true,
        ca: fs.readFileSync(caPath).toString(),
    },
});

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

const saltRounds = 10;

async function createAdmin() {
    console.log("--- Pembuatan Akun Admin ---");
    let client;
    try {
        // Langkah 1: Tes koneksi
        console.log("Mencoba menghubungkan ke database Aiven...");
        client = await pool.connect();
        console.log("✅ Koneksi berhasil.");

        // Langkah 2: Meminta input pengguna
        const username = await new Promise(resolve => rl.question('Masukkan username admin baru: ', resolve));
        const password = await new Promise(resolve => rl.question('Masukkan password admin baru: ', resolve));

        if (!username.trim() || !password.trim()) {
            throw new Error("Username dan password tidak boleh kosong.");
        }
        
        // Langkah 3: Hash password
        console.log("Mengenkripsi password...");
        const hashedPassword = await bcrypt.hash(password, saltRounds);
        console.log("Password berhasil di-hash.");

        // Langkah 4: Masukkan ke database
        const sql = 'INSERT INTO admins (username, password) VALUES ($1, $2)';
        await client.query(sql, [username, hashedPassword]);
        
        console.log(`✅ Admin dengan username '${username}' berhasil dibuat.`);

    } catch (err) {
        console.error("❌ Gagal membuat admin.");
        console.error("--- Pesan Error Lengkap ---");
        console.error(err);
        console.error("--------------------------");

        if (err.message.includes('admins_username_key')) {
            console.error("-> Petunjuk: Username ini sudah ada di database.");
        } else if (err.code === '42P01') {
             console.error("-> Petunjuk: Tabel 'admins' tidak ditemukan. Jalankan 'node init-db.js' terlebih dahulu.");
        } else {
             console.error("-> Petunjuk: Periksa kembali detail koneksi di file .env dan pastikan file ca.pem sudah benar.");
        }

    } finally {
        if (client) client.release();
        await pool.end();
        rl.close();
    }
}

createAdmin();
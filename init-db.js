// File: init-db.js (Versi Final dengan Tabel Sesi)
require('dotenv').config();
const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');

// --- DATA PRICELIST ANDA (Tidak berubah) ---
const packagesData = [
    { category: 'Akad Nikah', name: 'Paket 1', price: 1100000, features: '1 Photografer, 1 Hari Kerja, 40 Cetak Photo 5R (Sistem Pilih), Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Akad Nikah 1.' },
    { category: 'Akad Nikah', name: 'Paket 2', price: 1800000, features: '1 Photografer, 1 Asestin Photografer, 1 Hari Kerja, 80 Cetak Photo 5R (Sistem Pilih), Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 14R+Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Akad Nikah 2.' },
    { category: 'Resepsi', name: 'Paket 1', price: 1800000, features: '1 Photografer, 1 Asestin Photografer, 1 Hari Kerja, 40 Cetak Photo 5R (Sistem Pilih), Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 14R+Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Resepsi 1.' },
    { category: 'Resepsi', name: 'Paket 2', price: 2300000, features: '1 Photografer, 1 Asestin Photografer, 1 Hari Kerja, 80 Cetak Photo 5R (Sistem Pilih), Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 14R+Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Resepsi 2.' },
    { category: 'Akad Nikah & Resepsi', name: 'Paket 1', price: 3000000, features: '1 Photografer, 1 Asestin Photografer, 2 Hari Kerja, 80 Cetak Photo 5R (Sistem Pilil), Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 14R+Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Akad Nikah & Resepsi 1.' },
    { category: 'Akad Nikah & Resepsi', name: 'Paket 2', price: 3500000, features: '1 Photografer, 1 Asestin Photografer, 2 Hari Kerja, 80 Cetak Photo 5R (Sistem Pilil), 1 Photo Box, Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 14R Jumbo + Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Akad Nikah & Resepsi 2.' },
    { category: 'Akad Nikah & Resepsi', name: 'Paket 3', price: 5000000, features: '2 Photografer, 1 Asestin Photografer, 2 Hari Kerja, 120 Cetak Photo 5R (Sistem Pili), 1 Hart Cover, Album Magnetik (Tempel), Unlimited file Pictures, Flasdisk softcopy All file, 1 Cetak Besar 16R Jumbo + Frame', whatsapp_message: 'Halo Hafi Portrait, saya tertarik dengan Paket Akad Nikah & Resepsi 3.' }
];

// --- KONEKSI DAN LOGIKA SCRIPT ---
const caPath = path.join(__dirname, 'ca.pem');
if (!fs.existsSync(caPath)) {
    console.error("‼️  Error: File 'ca.pem' tidak ditemukan.");
    process.exit(1);
}

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

async function initializeAndSeedDb() {
    let client;
    try {
        console.log('Mencoba terhubung ke database Aiven...');
        client = await pool.connect();
        console.log('✅ Terhubung! Memulai proses setup database...');

        // 1. Buat SEMUA Tabel (jika belum ada)
        await client.query(`
            CREATE TABLE IF NOT EXISTS packages (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                name VARCHAR(255) NOT NULL,
                price INT NOT NULL,
                features TEXT NOT NULL,
                whatsapp_message TEXT
            );
            
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            );

            -- ===============================================
            -- === TABEL BARU UNTUK MANAJEMEN SESI LOGIN ===
            -- ===============================================
            CREATE TABLE IF NOT EXISTS "user_sessions" (
                "sid" varchar NOT NULL COLLATE "default",
                "sess" json NOT NULL,
                "expire" timestamp(6) NOT NULL
            )
            WITH (OIDS=FALSE);
            
            ALTER TABLE "user_sessions" ADD CONSTRAINT "user_sessions_pkey" PRIMARY KEY ("sid") NOT DEFERRABLE INITIALLY IMMEDIATE;
            CREATE INDEX IF NOT EXISTS "IDX_user_sessions_expire" ON "user_sessions" ("expire");
        `);
        console.log('Semua tabel (packages, admins, user_sessions) berhasil diperiksa/dibuat.');

        // 2. Kosongkan tabel packages untuk memastikan data bersih
        await client.query('DELETE FROM packages;');
        console.log('Data lama di tabel "packages" telah dihapus.');

        // 3. Masukkan data pricelist (Seeding)
        const insertSql = `INSERT INTO packages (category, name, price, features, whatsapp_message) VALUES ($1, $2, $3, $4, $5)`;
        for (const pkg of packagesData) {
            const values = [pkg.category, pkg.name, pkg.price, pkg.features, pkg.whatsapp_message];
            await client.query(insertSql, values);
        }
        console.log(`✅ Berhasil memasukkan ${packagesData.length} paket pricelist.`);
        console.log('Database Anda sekarang sudah siap!');

    } catch (err) {
        // Abaikan error "relation "..." already exists" karena itu berarti tabel sudah ada
        if (err.message.includes('already exists')) {
            console.log('Tabel sudah ada, melanjutkan...');
        } else {
            console.error("❌ Gagal menjalankan setup database:", err.stack);
        }
    } finally {
        if (client) client.release();
        await pool.end();
        console.log('Koneksi database ditutup.');
    }
}

initializeAndSeedDb();
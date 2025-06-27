// File: server.js (Versi 9.0 - FINAL & BENAR)
require('dotenv').config();
const express = require('express');
const path = require('path');
const fs = require('fs').promises;
const fsSync = require('fs');
const { Pool } = require('pg');
const bcrypt = require('bcrypt');
const session = require('express-session');
const pgSession = require('connect-pg-simple')(session);

// --- PERBAIKAN: Impor yang benar dari AWS SDK untuk S3 ---
const { S3Client, ListObjectsV2Command } = require("@aws-sdk/client-s3");

const app = express();
const port = process.env.PORT || 3000;

// Cek file ca.pem
const caPath = path.join(__dirname, 'ca.pem');
if (!fsSync.existsSync(caPath)) {
    console.error("‼️  Error: File 'ca.pem' tidak ditemukan.");
    process.exit(1);
}

// Konfigurasi database pool
const dbConfig = {
    host: process.env.DB_HOST,
    port: process.env.DB_PORT,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_DATABASE,
    ssl: {
        rejectUnauthorized: true,
        ca: fsSync.readFileSync(caPath).toString(),
    },
};
const pool = new Pool(dbConfig);

// Verifikasi koneksi startup
pool.query('SELECT NOW()', (err) => {
    if (err) { console.error("‼️ GAGAL terhubung ke database Aiven:", err); } 
    else { console.log("✅ Berhasil terhubung ke database Aiven."); }
});

// Konfigurasi Sesi
app.use(session({
    store: new pgSession({ pool: pool, tableName: 'user_sessions' }),
    secret: process.env.SESSION_SECRET || 'rahasia-yang-sangat-aman',
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 30 * 24 * 60 * 60 * 1000 }
}));

// Konfigurasi Express lainnya
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Middleware untuk memeriksa login
function requireLogin(req, res, next) {
    if (req.session.userId) { next(); } else { res.redirect('/login'); }
}

// --- RUTE-ROUTE APLIKASI ---

// Rute Halaman Publik Pricelist
app.get('/', async (req, res) => {
    const sql = `SELECT * FROM packages ORDER BY category, price`;
    try {
        const result = await pool.query(sql);
        const groupedPackages = result.rows.reduce((acc, pkg) => { (acc[pkg.category] = acc[pkg.category] || []).push(pkg); return acc; }, {});
        res.render('pricelist', { title: "Daftar Harga - Hafi Portrait", groupedPackages });
    } catch (err) {
        res.status(500).send("Gagal memuat data pricelist.");
    }
});

// === RUTE GALERI YANG SUDAH DIPERBAIKI SEPENUHNYA ===
app.get('/gallery', async (req, res) => {
    console.log("Menerima permintaan untuk halaman galeri...");
    try {
        const credsRaw = await fs.readFile('credentials.json', 'utf-8');
        const creds = JSON.parse(credsRaw);
        
        // Baca URL publik R2 langsung dari file .env
        const publicR2Url = process.env.R2_PUBLIC_URL;
        if (!publicR2Url) {
            throw new Error("Variabel R2_PUBLIC_URL belum diatur di file .env");
        }

        // PERBAIKAN: Menggunakan S3Client dari @aws-sdk dengan sintaks yang benar
        const s3Client = new S3Client({
            endpoint: creds.endpoint_url,
            region: creds.region,
            credentials: {
                accessKeyId: creds.access_key,
                secretAccessKey: creds.secret_key,
            }
        });

        const command = new ListObjectsV2Command({ Bucket: creds.bucket });
        const response = await s3Client.send(command);

        let imageList = [];
        if (response.Contents && response.Contents.length > 0) {
            const sortedObjects = response.Contents.sort((a, b) => new Date(b.LastModified) - new Date(a.LastModified));
            imageList = sortedObjects
                .filter(obj => /\.(jpg|jpeg)$/i.test(obj.Key)) // Hanya mengambil file .jpg dan .jpeg
                .map(obj => ({
                    url: `${publicR2Url}/${obj.Key}`,
                    filename: obj.Key
                }));
        }
        
        res.render('gallery_page', { 
            title: "Galeri Foto - Hafi Portrait",
            images: imageList 
        });

    } catch (error) {
        console.error("Gagal memuat halaman galeri:", error);
        res.status(500).send(`Terjadi kesalahan saat memuat galeri: ${error.message}`);
    }
});


// --- RUTE LAINNYA (SSE, Admin, dll - tidak ada perubahan) ---
let clients = []; 
app.get('/events', (req, res) => { res.setHeader('Content-Type', 'text/event-stream'); res.setHeader('Cache-Control', 'no-cache'); res.setHeader('Connection', 'keep-alive'); res.flushHeaders(); const clientId = Date.now(); const newClient = { id: clientId, res: res }; clients.push(newClient); console.log(`Browser baru terhubung ke stream galeri dengan ID: ${clientId}`); req.on('close', () => { console.log(`Koneksi stream galeri ID: ${clientId} terputus.`); clients = clients.filter(client => client.id !== clientId); }); });
app.post('/notify-new-photo', (req, res) => { const newPhoto = req.body; console.log('Menerima sinyal foto baru dari Python:', newPhoto); clients.forEach(client => { client.res.write(`data: ${JSON.stringify(newPhoto)}\n\n`); }); res.status(204).end(); });
app.get('/login', (req, res) => { res.render('login', { error: null, title: "Admin Login" }); });
app.post('/login', async (req, res) => { const { username, password } = req.body; try { const result = await pool.query('SELECT * FROM admins WHERE username = $1', [username]); if (result.rows.length === 0) { return res.render('login', { error: 'Username atau password salah.', title: "Admin Login" }); } const admin = result.rows[0]; const match = await bcrypt.compare(password, admin.password); if (match) { req.session.userId = admin.id; res.redirect('/admin/dashboard'); } else { res.render('login', { error: 'Username atau password salah.', title: "Admin Login" }); } } catch (err) { console.error(err); res.status(500).send("Terjadi error di server."); } });
app.get('/logout', (req, res) => { req.session.destroy(err => { if (err) { return res.redirect('/admin/dashboard'); } res.clearCookie('connect.sid'); res.redirect('/login'); }); });
app.get('/admin/dashboard', requireLogin, async (req, res) => { try { const result = await pool.query('SELECT * FROM packages ORDER BY category, id'); res.render('admin_dashboard', { title: "Admin Dashboard", packages: result.rows }); } catch (err) { console.error("Gagal mengambil data paket untuk dashboard:", err); res.status(500).send("Gagal memuat dashboard."); } });
app.get('/admin/packages/add', requireLogin, (req, res) => { res.render('admin_add_package', { title: "Tambah Paket Baru" }); });
app.post('/admin/packages/add', requireLogin, async (req, res) => { const { category, name, price, features, whatsapp_message } = req.body; const sql = `INSERT INTO packages (category, name, price, features, whatsapp_message) VALUES ($1, $2, $3, $4, $5)`; const values = [category, name, parseInt(price), features, whatsapp_message]; try { await pool.query(sql, values); res.redirect('/admin/dashboard'); } catch (err) { console.error("Gagal menambahkan paket baru:", err); res.status(500).send("Gagal menyimpan paket baru."); } });
app.get('/admin/packages/edit/:id', requireLogin, async (req, res) => { const { id } = req.params; const sql = 'SELECT * FROM packages WHERE id = $1'; try { const result = await pool.query(sql, [id]); if (result.rows.length === 0) { return res.status(404).send("Paket tidak ditemukan."); } res.render('admin_edit_package', { title: "Edit Paket", package: result.rows[0] }); } catch (err) { console.error("Gagal mengambil paket untuk diedit:", err); res.status(500).send("Gagal memuat halaman edit."); } });
app.post('/admin/packages/edit/:id', requireLogin, async (req, res) => { const { id } = req.params; const { category, name, price, features, whatsapp_message } = req.body; const sql = `UPDATE packages SET category = $1, name = $2, price = $3, features = $4, whatsapp_message = $5 WHERE id = $6`; const values = [category, name, parseInt(price), features, whatsapp_message, id]; try { await pool.query(sql, values); res.redirect('/admin/dashboard'); } catch (err) { console.error("Gagal mengupdate paket:", err); res.status(500).send("Gagal mengupdate paket."); } });
app.post('/admin/packages/delete/:id', requireLogin, async (req, res) => { const { id } = req.params; const sql = 'DELETE FROM packages WHERE id = $1'; try { await pool.query(sql, [id]); res.redirect('/admin/dashboard'); } catch (err) { console.error("Gagal menghapus paket:", err); res.status(500).send("Gagal menghapus paket."); } });

// Jalankan server
app.listen(port, () => {
    console.log(`✅ Server Hafi Portrait berjalan di http://localhost:${port}`);
});
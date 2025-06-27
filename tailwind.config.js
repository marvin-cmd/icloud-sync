/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./views/**/*.ejs",
  ],
  theme: {
    extend: {
      // Menambahkan atau memperluas palet warna default
       colors: {
        'brand-dark': '#0d1f2d',          // Background Biru Dongker / Deep Sapphire
        'brand-light': '#e5e7eb',         // Teks Putih Platina / Platinum White
        'brand-accent': '#00b4d8',       // Aksen Cyan/Teal Cerah
        'brand-accent-hover': '#0096b4', // Versi hover dari aksen
        'brand-muted': '#6b7280',        // Abu-abu untuk teks sekunder
      },
      // Mengatur font kustom agar mudah dipanggil
      fontFamily: {
        'sans': ['Montserrat', 'sans-serif'],
        'display': ['Playfair Display', 'serif'],
      }
    },
  },
  plugins: [],
}
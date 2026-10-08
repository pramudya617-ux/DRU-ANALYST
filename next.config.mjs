/* Header keamanan sejak commit pertama.
 *
 * Satu berkas, dan nilainya naik dari F ke A di securityheaders.com. Di proyek
 * DRC ini baru dipasang belakangan dan sempat mematikan chart, jadi di sini
 * CSP-nya ditulis bersamaan dengan halamannya - bukan ditambal sesudahnya.
 *
 * ASAL YANG WAJIB DISEBUT, dan kenapa:
 *   s3.tradingview.com          skrip widget chart
 *   *.tradingview-widget.com    iframe chart-nya. BUKAN www.tradingview.com,
 *                               yang diblokir sebagian jaringan di Indonesia.
 *   cdn.discordapp.com          avatar analis (tertanam data URI, tapi lampiran
 *                               gambar call masih ditautkan dari sana)
 *
 * Satu asal yang terlewat berarti halaman blank TANPA pesan galat apa pun.
 * Mengujinya wajib di mode produksi: 'unsafe-eval' hanya dibutuhkan webpack
 * saat pengembangan, jadi di dev ia menyala dan menutupi kesalahan.
 */
const dev = process.env.NODE_ENV !== "production";

const csp = [
  "default-src 'self'",
  /* 'unsafe-inline' tidak bisa dihindari tanpa middleware nonce, dan middleware
     berarti Edge runtime - yang sudah dua kali menggagalkan build di DRC
     karena node:crypto tidak lengkap di sana. Nilai A sudah plafon yang wajar. */
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""} https://s3.tradingview.com`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://cdn.discordapp.com https://*.tradingview.com",
  "font-src 'self' data:",
  "connect-src 'self' https://*.tradingview.com",
  "frame-src https://*.tradingview.com https://*.tradingview-widget.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig = {
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: csp },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        /* preload SENGAJA tidak dipakai: sekali domainnya masuk daftar preload
           browser, mencabutnya makan berbulan-bulan. */
        ...(dev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
      ],
    }];
  },
};

export default nextConfig;

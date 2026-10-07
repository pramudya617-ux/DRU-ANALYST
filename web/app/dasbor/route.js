import { readFile } from "node:fs/promises";
import path from "node:path";
import { gerbang } from "@/lib/gerbang";
import { bacaKoreksi } from "@/lib/berkas";

/* Dashboard disajikan dari sini, BUKAN dari folder public.
 *
 * Berkas di public/ dilayani Next.js sebelum kode mana pun jalan, jadi menaruh
 * DRU-dashboard.html di sana berarti siapa pun bisa mengunduhnya tanpa pernah
 * menyentuh gerbang. Satu-satunya cara menjaganya adalah menyajikannya lewat
 * route handler yang memanggil gerbang() lebih dulu.
 *
 * Ini juga satu-satunya tempat berkasnya dibaca, jadi tidak ada pintu kedua
 * yang bisa lupa dikunci - pelajaran mahal dari proyek DRC, di mana rute API
 * pernah terbuka lebar sementara halamannya meminta sandi.
 */
export const dynamic = "force-dynamic";

// Di dalam folder aplikasi, bukan di luarnya: itu satu-satunya tempat yang
// pasti ikut ter-deploy. pipa/gabung.py yang menulisnya tiap kali dibangun.
const BERKAS = path.join(process.cwd(), "dasbor.html");

function tombolKeluar(nama) {
  /* Disuntik di sisi server, bukan ditulis di dashboard-nya.
     DRU-dashboard.html harus tetap bisa dibuka dengan klik ganda tanpa server;
     kalau tombol keluar ditanam di sana, berkas itu akan memajang kontrol yang
     tidak pernah berfungsi di luar web app. */
  return `<div style="position:fixed;right:14px;bottom:14px;z-index:99;display:flex;
    gap:9px;align-items:center;background:rgba(18,18,22,.92);border:1px solid #26262d;
    border-radius:99px;padding:6px 8px 6px 14px;font:12px ui-sans-serif,system-ui,sans-serif;
    color:#8b8b94">
    <span>${nama ? nama.replace(/[<>&"]/g, "") : "member"}</span>
    <button onclick="fetch('/api/auth/discord',{method:'DELETE'}).then(()=>location.href='/')"
      style="background:#1a1a20;border:1px solid #26262d;color:#f4f4f5;
      border-radius:99px;padding:4px 11px;font:inherit;cursor:pointer">Keluar</button></div>`;
}

export async function GET() {
  const izin = await gerbang();
  if (!izin.boleh) {
    /* Penolakan TIDAK memulangkan halaman masuk di sini. Rute ini hanya
       menyajikan data berbayar; yang mengurus login adalah "/". Memulangkan
       302 membuat tab yang dibuka langsung ke /dasbor tetap mendarat benar. */
    return Response.redirect(new URL("/", process.env.APP_URL || "http://localhost:3200"), 302);
  }

  let html;
  try {
    html = await readFile(BERKAS, "utf8");
  } catch {
    return new Response(
      "dasbor.html belum dibangun. Jalankan: python perbarui.py",
      { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } });
  }

  /* Koreksi disuntik sebagai lapisan kedua, bukan dipanggang ulang ke datanya.
     Halamannya menerapkannya saat dimuat, jadi suntingan dari /koreksi langsung
     terlihat - tanpa menunggu pipeline Python yang hanya jalan di laptop.
     Python tetap menyerapnya saat rebuild berikutnya; keduanya memakai berkas
     yang sama, jadi tidak ada dua kebenaran yang bisa menyimpang. */
  const koreksi = await bacaKoreksi();
  html = html.replace("</head>",
    `<script>window.KOREKSI = ${JSON.stringify(koreksi).replace(/</g, "<")};</script></head>`);
  html = html.replace("</body>", tombolKeluar(izin.nama) + "</body>");
  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      /* Jangan pernah disinggahi proxy atau browser: isinya berbayar dan
         rolenya diperiksa ulang tiap permintaan. Salinan cache akan tetap
         terbuka setelah role dicabut. */
      "cache-control": "no-store, must-revalidate",
    },
  });
}

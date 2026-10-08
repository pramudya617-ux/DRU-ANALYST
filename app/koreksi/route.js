import { readFile } from "node:fs/promises";
import path from "node:path";
import { gerbangKoreksi } from "@/lib/gerbang";

/* Halaman koreksi, disajikan di balik gerbang editor.
 *
 * Sama seperti /dasbor: berkasnya TIDAK ditaruh di public/, karena apa pun di
 * sana dilayani sebelum kode mana pun jalan. Satu-satunya cara menjaganya
 * adalah route handler yang memanggil gerbangnya lebih dulu.
 *
 * koreksi.html dibangun pipa/gabung.py dengan dataset sudah disuntik di
 * dalamnya, jadi halaman ini tidak perlu rute data terpisah yang harus
 * dijaga sendiri.
 */
export const dynamic = "force-dynamic";

const BERKAS = path.join(process.cwd(), "koreksi.html");

export async function GET() {
  const izin = await gerbangKoreksi();
  if (!izin.boleh) {
    const pesan = izin.sebab === "belum-masuk"
      ? "Masuk dulu lewat halaman utama."
      : izin.galat || "Akun ini tidak boleh mengubah data.";
    return new Response(
      `<!doctype html><meta charset="utf-8"><title>Koreksi DRU</title>
       <body style="background:#09090b;color:#f4f4f5;font:15px/1.6 system-ui;padding:40px;max-width:520px;margin:auto">
       <h1 style="font-size:20px">Tidak diizinkan</h1><p style="color:#8b8b94">${pesan}</p>
       <p><a href="/" style="color:#ffd60a">Kembali ke dashboard</a></p>`,
      { status: 403, headers: { "content-type": "text/html; charset=utf-8" } }
    );
  }

  let html;
  try {
    html = await readFile(BERKAS, "utf8");
  } catch {
    return new Response("koreksi.html belum dibangun. Jalankan: python perbarui.py",
      { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } });
  }

  /* Penanda bahwa halaman ini berjalan di server, bukan dibuka dari berkas.
     Halamannya memakai ini untuk mengganti tombol "Unduh" jadi "Simpan ke
     server" - satu berkas, dua perilaku, tanpa dua salinan yang harus
     dijaga tetap sama. */
  html = html.replace("</head>",
    `<script>window.DI_SERVER = true; window.PENGEDIT = ${JSON.stringify(izin.nama || "")};</script></head>`);

  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store, must-revalidate",
    },
  });
}

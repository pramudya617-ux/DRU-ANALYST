import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
import path from "node:path";

/* Tempat koreksi manual disimpan di server.
 *
 * KENAPA HARUS VOLUME, BUKAN FOLDER APLIKASI
 *   Berkas yang ditulis ke dalam folder aplikasi di Railway hilang pada setiap
 *   redeploy maupun restart - containernya dibangun ulang dari image. Koreksi
 *   yang ditulis seseorang Senin sore akan lenyap begitu ada push hari Selasa,
 *   tanpa pesan apa pun. Karena itu DATA_DIR harus menunjuk ke volume yang
 *   di-mount, DI LUAR folder aplikasi.
 *
 * SATU SUMBER YANG DITULIS, SATU YANG DIBACA
 *   Repo juga membawa data/koreksi.json. Kalau keduanya dibaca dan digabung
 *   sementara hanya volume yang ditulis, penghapusan tidak akan pernah
 *   berhasil: entri yang asalnya dari repo akan terbaca lagi dari sana. Pola
 *   bug itu sudah muncul tiga kali di proyek DRC.
 *
 *   Jadi aturannya tegas: begitu volume punya berkasnya, volume adalah
 *   SATU-SATUNYA kebenaran. Salinan repo hanya dipakai sebagai benih pada
 *   penulisan pertama, lalu tidak pernah dilirik lagi.
 */
export function dirData() {
  return process.env.DATA_DIR || path.join(process.cwd(), "..", "data");
}

const BERKAS = () => path.join(dirData(), "koreksi.json");
const BENIH = () => path.join(process.cwd(), "koreksi-benih.json");

export async function bacaKoreksi() {
  try {
    return JSON.parse(await readFile(BERKAS(), "utf8"));
  } catch {
    /* Volume masih kosong: pakai salinan yang ikut ter-deploy sebagai titik
       awal, supaya koreksi yang sudah dibuat di laptop tidak hilang saat
       pertama kali halaman ini dipakai dari server. */
    try {
      return JSON.parse(await readFile(BENIH(), "utf8"));
    } catch {
      return {};
    }
  }
}

export async function tulisKoreksi(isi) {
  const dir = dirData();
  await mkdir(dir, { recursive: true });
  /* Tulis ke berkas sementara lalu rename. rename bersifat atomik di satu
     sistem berkas, jadi pembaca tidak akan pernah menemukan JSON separuh
     tertulis kalau prosesnya mati di tengah penyimpanan. */
  const semi = path.join(dir, ".koreksi.tmp");
  await writeFile(semi, JSON.stringify(isi, null, 1), "utf8");
  await rename(semi, BERKAS());
  return Object.keys(isi).length;
}

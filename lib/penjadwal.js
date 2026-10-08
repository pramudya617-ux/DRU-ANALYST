/* Penjadwal pipeline data, jalan di dalam proses Next.js.
 *
 * Aturannya meniru penjadwal DRC, yang sudah terbukti di Railway:
 *
 *   1. Satu pekerjaan pada satu waktu. Dua penarikan sekaligus menulis berkas
 *      yang sama dan berbagi kuota API yang sama.
 *   2. Kunci yang tidak ada berarti DILEWATI, bukan gagal berulang. Tanpa
 *      DRU_BOT_TOKEN penarikan tidak akan pernah berhasil, jadi mencobanya
 *      tiap jam hanya mengotori log.
 *   3. Jam terakhir jalan disimpan ke berkas di DATA_DIR. Server dimulai ulang
 *      jauh lebih sering daripada yang disangka orang, dan tanpa ini tiap
 *      restart memicu penarikan baru.
 */

/* Modul Node dimuat lewat require yang DISEMBUNYIKAN dari webpack.
 *
 * Next mengompilasi instrumentation.js untuk semua runtime termasuk bundel
 * klien, dan webpack menolak impor "node:*" di sana dengan UnhandledSchemeError
 * meski kodenya tidak pernah benar-benar berjalan di peramban. Alias resolve
 * dan impor dinamis sama-sama tidak menolong karena keduanya masih ditelusuri
 * secara statis. eval("require") tidak bisa ditelusuri. */
const _req = eval("require");
const fs = _req("fs");
const path = _req("path");

function jalankan(perintah, argumen, opsi) {
  const { execFile } = _req("child_process");
  const { promisify } = _req("util");
  return promisify(execFile)(perintah, argumen, opsi);
}

const AKAR = process.cwd();

/* DATA_DIR harus volume. Tanpa itu seluruh hasil penarikan - termasuk
   dasbor.html yang disajikan - hilang pada redeploy berikutnya, dan penjadwal
   akan menarik ulang semuanya dari nol seolah belum pernah jalan. */
function dirData() {
  const d = process.env.DATA_DIR;
  try {
    if (d && fs.statSync(d).isDirectory()) return d;
  } catch {}
  return path.join(AKAR, "data");
}

const JEJAK = () => path.join(dirData(), "jadwal-terakhir.json");

function terakhir() {
  try {
    return JSON.parse(fs.readFileSync(JEJAK(), "utf8")).waktu || 0;
  } catch {
    return 0;
  }
}

function catat() {
  try {
    fs.mkdirSync(dirData(), { recursive: true });
    fs.writeFileSync(JEJAK(), JSON.stringify({ waktu: Date.now() }), "utf8");
  } catch (e) {
    console.warn("[jadwal] gagal mencatat jejak:", e.message);
  }
}

/* ENOENT berarti perintahnya tidak ada - lanjut ke nama berikutnya. Galat lain
   adalah kegagalan pipeline yang sesungguhnya dan harus dilempar apa adanya,
   bukan disamarkan jadi "python tidak ketemu". */
async function coba(nama, argumen, opsi) {
  let akhir;
  for (const n of nama) {
    try {
      return await jalankan(n, argumen, opsi);
    } catch (e) {
      if (e && e.code === "ENOENT") { akhir = e; continue; }
      throw e;
    }
  }
  throw akhir || new Error("python tidak ditemukan");
}

let sibuk = false;

async function sekali() {
  if (sibuk) {
    console.log("[jadwal] masih ada yang jalan, dilewati");
    return;
  }
  if (!process.env.DRU_BOT_TOKEN) {
    console.log("[jadwal] DRU_BOT_TOKEN kosong, penarikan dilewati");
    return;
  }
  sibuk = true;
  const t0 = Date.now();
  try {
    /* python3 di image Nixpacks, python di Windows. Dicoba berurutan supaya
       penjadwal yang sama bisa diuji di laptop sebelum dikirim ke server.
       Seluruh urutan langkahnya diserahkan ke perbarui.py, jadi logikanya
       hanya hidup di satu tempat. */
    const { stdout } = await coba(["python3", "python"], [path.join(AKAR, "perbarui.py")], {
      cwd: AKAR,
      timeout: 15 * 60 * 1000,
      maxBuffer: 8 * 1024 * 1024,
      env: process.env,
    });
    const ringkas = stdout.split("\n").filter((b) => /SELESAI|GAGAL|total call/.test(b));
    console.log("[jadwal] selesai dalam", Math.round((Date.now() - t0) / 1000), "detik");
    for (const b of ringkas) console.log("[jadwal]  ", b.trim());
    catat();
  } catch (e) {
    /* Jejak TIDAK dicatat saat gagal, jadi siklus berikutnya mencoba lagi
       alih-alih menunggu satu jam penuh dengan data yang tidak jadi diperbarui. */
    console.error("[jadwal] gagal:", (e.stderr || e.message || "").slice(0, 600));
  } finally {
    sibuk = false;
  }
}

const JEDA = Number(process.env.JADWAL_MENIT || 60) * 60 * 1000;

export function mulaiPenjadwal() {
  if (process.env.JADWAL_MATI === "1") {
    console.log("[jadwal] dimatikan lewat JADWAL_MATI");
    return;
  }

  const sejak = Date.now() - terakhir();
  /* Penarikan pertama ditunda 30 detik supaya tidak bersaing dengan permintaan
     yang datang tepat setelah deploy; kalau jejaknya masih baru, tunggu sisa
     jedanya. */
  const tunda = sejak >= JEDA ? 30_000 : JEDA - sejak;
  console.log(
    "[jadwal] aktif, tiap", JEDA / 60000, "menit; berikutnya dalam",
    Math.round(tunda / 1000), "detik"
  );

  setTimeout(function putar() {
    sekali().finally(() => setTimeout(putar, JEDA));
  }, tunda);
}

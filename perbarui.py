"""Satu perintah untuk memperbarui seluruh dashboard, aman dijadwalkan.

URUTANNYA WAJIB, karena tiap langkah memakai keluaran langkah sebelumnya:

    tarik_calls   Discord  -> calls_mentah.json
    urai_calls    regex    -> calls.json + invest.json
    gabung        satukan  -> dataset.json        (butuh daftar ticker)
    tarik_harga   Yahoo    -> data/harga/*.json   (hanya yang basi)
    verifikasi_tp telusuri -> verifikasi.json
    gabung        ulang    -> dataset.json + DRU-dashboard.html

gabung dijalankan DUA KALI dengan sengaja: yang pertama membentuk daftar ticker
yang dibutuhkan penarik harga, yang kedua menempelkan hasil verifikasinya.

SOPAN SANTUN TERHADAP SUMBER
    - Discord  : 100 pesan per panggilan, jeda 0,4 detik, hormati 429
    - Yahoo    : hanya ticker yang berkasnya lebih tua dari --umur jam
    - TradingView: satu panggilan borongan untuk seluruh ticker

    Dijadwalkan tiap jam, yang benar-benar ditarik ulang hanyalah Discord
    (ringan) dan satu panggilan TradingView. Riwayat harga menyentuh Yahoo
    paling sering sekali per --umur jam per ticker.

Pakai:
    python perbarui.py                -> siklus penuh
    python perbarui.py --cepat        -> lewati penarikan harga (UI saja)
    python perbarui.py --umur 6       -> harga dianggap basi setelah 6 jam
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import subprocess
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def jalan(nama, *args):
    print("\n=== %s %s" % (nama, " ".join(args)), flush=True)
    t = time.time()
    r = subprocess.run([sys.executable, str(HERE / "pipa" / nama), *args],
                       cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for baris in (r.stdout or "").splitlines():
        print("   " + baris)
    if r.returncode != 0:
        print("   GAGAL (kode %d)" % r.returncode)
        for baris in (r.stderr or "").splitlines()[-12:]:
            print("   ! " + baris)
    print("   (%.0f detik)" % (time.time() - t))
    return r.returncode == 0


def main():
    umur = ["--umur", sys.argv[sys.argv.index("--umur") + 1]] if "--umur" in sys.argv else []
    mulai = time.time()
    print("PERBARUI DRU  %s" % datetime.now().isoformat(timespec="seconds"))

    # Discord gagal (token hilang, jaringan putus) BUKAN alasan membatalkan
    # sisanya: dataset lama masih ada dan tetap layak dibangun ulang dengan
    # harga terbaru. Yang tidak boleh dilewati hanyalah gabung.
    jalan("tarik_calls.py")
    jalan("urai_calls.py")
    if not jalan("gabung.py", "--tanpaharga"):
        print("\ngabung tahap 1 gagal - berhenti, dataset tidak disentuh")
        return 1

    if "--cepat" not in sys.argv:
        jalan("tarik_harga.py", *umur)
        jalan("verifikasi_tp.py")

    if not jalan("gabung.py"):
        print("\ngabung tahap 2 gagal")
        return 1

    print("\nSELESAI dalam %.0f detik" % (time.time() - mulai))
    return 0


if __name__ == "__main__":
    sys.exit(main())

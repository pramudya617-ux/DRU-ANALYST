"""Uji parser Discord dengan jurnal Excel sebagai kunci jawaban.

KENAPA INI ADA
    Jurnal Excel berisi ratusan baris (tanggal, ticker, entry, TP1-4, SL,
    status) yang sudah diperiksa manusia. Itu menjadikannya test set berlabel
    yang gratis: parser Discord bisa diukur, bukan sekadar "kelihatannya jalan".

    Tanpa ini, satu regex yang meleset diam-diam akan menggeser win rate di
    dashboard, dan tidak ada yang tahu sampai ada member yang menghitung ulang.

BATAS YANG DISADARI
    - Channel Iron baru dibuat Sep 2025, sedangkan jurnalnya mulai Apr 2024.
      Baris Excel sebelum channelnya ada MEMANG tidak akan punya pasangan.
    - Tarikan Discord lebih baru daripada jurnal, jadi call terakhir juga
      tidak punya pasangan. Keduanya dilaporkan terpisah dari ketidakcocokan
      sungguhan.

Pakai:
    python cocok_excel.py
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import datetime
import json
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent
UNDUHAN = Path.home() / "Downloads"

JURNAL = {
    "Tyler": UNDUHAN / "Trading Journal @Tyler.xlsx",
    "Iron": UNDUHAN / "Trading Journal @Iron (FIX).xlsx",
    "Oracle": UNDUHAN / "(FIX) Trading Journal @Do .xlsx",
}


def angka(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", ".").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


# Kata berhuruf besar yang bentuknya seperti ticker tapi muncul sebagai isi
# kolom status atau sisa header di jurnal.
BUKAN_TICKER = {"CLOSE", "OPEN", "SL", "TP", "TP1", "TP2", "TP3", "TP4",
                "ENTRY", "EXIT", "BEP", "CL", "NO", "DATE", "NAME", "TOTAL"}

_singgahan = {}


def baca_jurnal(path):
    """Tarik baris trade dari semua sheet.

    Hasilnya disinggahi: berkas Oracle 1,4 MB dengan 20 sheet, dan gabung.py
    membutuhkan isinya dua kali. Tanpa singgahan, satu kali jalan memuat ulang
    seluruh workbook enam kali dan makan menit, bukan detik.

    Tata letak kolomnya beda antar berkas (Tyler punya kolom "No." di depan),
    tetapi jarak RELATIF dari kolom ticker selalu sama:
    ticker, timeframe, entry, TP1, TP2, TP3, TP4, SL. Jadi yang dicari posisi
    tickernya, bukan nomor kolom tetap - itu yang membuat satu pembaca cukup
    untuk ketiga berkas.
    """
    if str(path) in _singgahan:
        return _singgahan[str(path)]
    # read_only=True tidak dipakai: mode itu tidak mendukung ws.cell() akses
    # acak, dan pembacaan di bawah memang butuh indeks kolom relatif.
    wb = openpyxl.load_workbook(path, data_only=True)
    baris = []
    for ws in wb.worksheets:
        if ws.title.strip().lower() in ("summary", "invest"):
            continue
        for r in range(3, ws.max_row + 1):
            row = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            tgl = next((v for v in row if isinstance(v, datetime.datetime)), None)
            if not tgl:
                continue
            i = next((k for k, v in enumerate(row)
                      if isinstance(v, str) and v.isalpha() and v.isupper()
                      and 1 < len(v) <= 5 and v not in BUKAN_TICKER), None)
            if i is None or i + 7 >= len(row):
                continue
            # Baris tanpa harga entry yang masuk akal bukan call - itu baris
            # ringkasan atau sisa header yang kebetulan memuat tanggal. Tiga
            # baris semacam ini sempat lolos sebagai ticker "CLOSE" dan "SL",
            # dan baru ketahuan saat penarik harga membalas 404.
            masuk = angka(row[i + 2])
            if masuk is None or masuk <= 0:
                continue
            ambil = [angka(row[i + n]) for n in range(2, 8)]
            # Status ada di ekor baris, tetapi TIDAK selalu di kolom terakhir.
            # Jurnal Oracle menulis DUA kolom berdampingan - hasilnya ("SL",
            # "TP3") lalu keadaannya ("CLOSE"). Mengambil yang terakhir berarti
            # selalu dapat "CLOSE", dan seluruh 179 call Oracle terbaca sebagai
            # masih berjalan. Jadi token hasil dicari lebih dulu; CLOSE/OPEN
            # hanya dipakai kalau tidak ada hasil sama sekali.
            ekor = [v.strip() for v in row[i + 8:]
                    if isinstance(v, str) and v.strip()
                    and not v.strip().lower().startswith("swing")]
            hasil = [v for v in ekor
                     if v.lower().startswith(("tp", "sl", "stoploss", "cut"))]
            baris.append({
                "tanggal": tgl.date().isoformat(),
                "ticker": row[i],
                "timeframe": row[i + 1],
                "entry": ambil[0],
                "tp": ambil[1:5],
                "sl": angka(row[i + 7]),
                "status": (hasil[0] if hasil else (ekor[-1] if ekor else None)),
            })
    _singgahan[str(path)] = baris
    return baris


def main():
    calls = json.loads((AKAR / "data" / "calls.json").read_text(encoding="utf-8"))

    for nama, path in JURNAL.items():
        if not path.exists():
            print("%-7s jurnal tidak ditemukan: %s" % (nama, path))
            continue
        xl = baca_jurnal(path)
        dc = [c for c in calls if c["analis"] == nama]
        print("\n%s" % ("=" * 64))
        print("%s  | Excel %d baris  | Discord %d call" % (nama, len(xl), len(dc)))
        if not dc:
            print("  (tidak ada channel Discord - Excel satu-satunya sumber)")
            continue

        awal_dc = min(c["tanggal"] for c in dc)
        akhir_xl = max(b["tanggal"] for b in xl)

        cocok = beda_entry = 0
        luar_jangkauan = []
        tak_ketemu = []
        for b in xl:
            if b["tanggal"] < awal_dc:
                luar_jangkauan.append(b)
                continue
            # Toleransi 14 hari. Terukur: jurnal tidak dicatat di hari yang sama
            # dengan postingan. Tyler $AMD diposting 20 Feb tapi dicatat 27 Feb;
            # Iron $MDT diposting 29 Sep dicatat 20 Sep - jadi pergeserannya
            # bisa ke DUA arah, bukan cuma terlambat.
            #
            # Jendela selebar ini aman karena pemenangnya dipilih lewat harga
            # entry, bukan lewat urutan. Ticker yang di-call dua kali dalam
            # sebulan tetap terpisah selama entrynya beda.
            kandidat = [c for c in dc if c["ticker"] == b["ticker"]
                        and abs((datetime.date.fromisoformat(c["tanggal"])
                                 - datetime.date.fromisoformat(b["tanggal"])).days) <= 14]
            if not kandidat:
                tak_ketemu.append(b)
                continue
            if b["entry"] is not None:
                kandidat.sort(key=lambda c: abs((c["entry"] or 0) - b["entry"]))
            c = kandidat[0]
            # Entry sering ditulis rentang di Discord ("425-430") sedangkan
            # jurnal mencatat satu angka. Dianggap cocok kalau angka jurnal
            # jatuh di dalam rentang itu.
            lo, hi = c["entry"], (c["entryAtas"] or c["entry"])
            if b["entry"] is not None and lo is not None:
                if min(lo, hi) - 0.01 <= b["entry"] <= max(lo, hi) + 0.01:
                    cocok += 1
                else:
                    beda_entry += 1
                    if beda_entry <= 3:
                        print("   entry beda: %s %s  excel=%s  discord=%s-%s"
                              % (b["tanggal"], b["ticker"], b["entry"], lo, hi))
            else:
                cocok += 1

        dibanding = len(xl) - len(luar_jangkauan)
        baru = [c for c in dc if c["tanggal"] > akhir_xl]
        print("  dibandingkan   : %d baris Excel (sejak %s, awal channel Discord)"
              % (dibanding, awal_dc))
        if luar_jangkauan:
            print("  sebelum channel: %d baris - HANYA ada di Excel, wajib dipertahankan"
                  % len(luar_jangkauan))
        print("  entry COCOK    : %d / %d  (%.0f%%)"
              % (cocok, dibanding, 100.0 * cocok / dibanding if dibanding else 0))
        if beda_entry:
            print("  entry BEDA     : %d" % beda_entry)
        if tak_ketemu:
            print("  tak ada di Discord: %d  contoh: %s" % (
                len(tak_ketemu), ", ".join("%s %s" % (b["tanggal"], b["ticker"])
                                           for b in tak_ketemu[:6])))
        if baru:
            print("  lebih baru dari jurnal: %d call (%s s/d %s) - belum masuk Excel"
                  % (len(baru), min(c["tanggal"] for c in baru),
                     max(c["tanggal"] for c in baru)))


if __name__ == "__main__":
    main()

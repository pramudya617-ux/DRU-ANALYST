"""Tarik riwayat harga harian (OHLC) tiap ticker, dengan singgahan dan rem.

KENAPA PERLU RIWAYAT, BUKAN HANYA HARGA SEKARANG
    scanner.tradingview.com memberi harga terakhir dalam satu panggilan, dan itu
    cukup untuk kolom "harga kini". Tapi untuk menentukan TP mana yang BENAR
    tercapai, yang dibutuhkan adalah harga TERTINGGI setelah tanggal call -
    sebuah angka yang hanya ada di riwayat harian.

SUMBERNYA
    Endpoint chart Yahoo Finance: tanpa API key, tanpa login, memulangkan
    open/high/low/close harian. Stooq sudah dicoba lebih dulu dan ditolak
    tantangan JavaScript dari mesin ini.

KENAPA ADA SINGGAHAN DAN REM
    201 ticker x sekali jalan = 201 permintaan. Dijalankan tiap jam oleh
    penjadwal, itu ribuan permintaan sehari untuk data yang hampir seluruhnya
    TIDAK berubah: lilin harian yang sudah lewat bersifat final selamanya.

    Jadi tiap ticker disimpan ke berkasnya sendiri dan hanya ditarik ulang
    kalau sudah basi. Yang sering berubah cuma beberapa hari terakhir.

Pakai:
    python tarik_harga.py               -> perbarui yang basi saja
    python tarik_harga.py --semua       -> paksa tarik ulang semuanya
    python tarik_harga.py --umur 6      -> anggap basi setelah 6 jam
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent
GUDANG = AKAR / "data" / "harga"
API = "https://query1.finance.yahoo.com/v8/finance/chart/%s?period1=%d&period2=%d&interval=1d"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Jeda antar permintaan. 0,35 detik menahan laju di sekitar 3/detik - terukur
# aman untuk 15 permintaan beruntun, dan 201 ticker selesai dalam ~70 detik.
# Angka ini sengaja bisa diputar: kalau endpointnya mulai menolak, naikkan.
JEDA = 0.35
# Berapa jam sebuah berkas dianggap masih segar. Lilin harian baru bertambah
# sekali sehari, jadi 12 jam sudah jauh lebih rapat daripada yang dibutuhkan.
UMUR_SEGAR = 12.0

# Berapa hari tumpang tindih saat menarik inkremental. Bursa merevisi harga
# penutupan beberapa hari setelahnya, dan lilin hari berjalan masih bergerak.
OVERLAP_HARI = 5


def muat(tk):
    f = GUDANG / ("%s.json" % tk)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return None


def basi(d, umur_jam):
    if not d or not d.get("diperbarui"):
        return True
    t = datetime.fromisoformat(d["diperbarui"])
    return (datetime.now(timezone.utc) - t).total_seconds() > umur_jam * 3600


def tarik(tk, sejak, punya=None):
    """Satu ticker. Kembalikan (data, galat). Menghormati 429 dengan mundur.

    `punya` adalah lilin yang sudah tersimpan. Kalau ada, yang diminta hanya
    sejak beberapa hari terakhir, bukan seluruh riwayat - lilin harian yang
    sudah lewat bersifat final, dan menariknya ulang tiap hari berarti 99,8%
    dari data yang dipindahkan adalah angka yang sudah kita punya.

    Proyek DRC membayar pelajaran ini dengan ban IP dari Binance setelah
    menarik ulang 6 bulan lilin untuk 98 aset setiap hari.
    """
    mulai = sejak
    if punya:
        # Mundur beberapa hari, bukan tepat di lilin terakhir: bursa merevisi
        # harga penutupan, dan hari terakhir yang tersimpan bisa saja lilin
        # setengah jadi dari sesi yang belum tutup.
        akhir = datetime.fromisoformat(punya[-1][0])
        mulai = (akhir - timedelta(days=OVERLAP_HARI)).date().isoformat()

    p1 = int(datetime.fromisoformat(mulai).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time())
    url = API % (tk, p1, p2)
    for coba in range(4):
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=30).read()
            r = json.loads(raw)["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            baru = []
            for i, ts in enumerate(r["timestamp"]):
                h, l, c = q["high"][i], q["low"][i], q["close"][i]
                # Hari libur sebagian kadang pulang sebagai null. Dilewati,
                # bukan diisi nol - nol akan terbaca sebagai stoploss kena.
                if h is None or l is None:
                    continue
                baru.append([datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                             round(h, 4), round(l, 4), round(c, 4) if c else None])

            # Gabung: yang baru menimpa yang lama pada tanggal yang sama, karena
            # revisi bursa selalu lebih benar daripada yang tersimpan.
            if punya:
                peta = {c[0]: c for c in punya}
                peta.update({c[0]: c for c in baru})
                lilin = [peta[k] for k in sorted(peta)]
            else:
                lilin = baru

            m = r.get("meta") or {}
            return {"ticker": tk, "sejak": sejak, "lilin": lilin,
                    "hargaKini": m.get("regularMarketPrice"),
                    "bursaYahoo": m.get("exchangeName"),
                    "diperbarui": datetime.now(timezone.utc).isoformat(timespec="seconds")}, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 999, 503):
                # Mundur berlipat. Menyerbu ulang saat ditolak adalah cara
                # tercepat untuk diblokir lebih lama.
                jeda = 5 * (2 ** coba)
                print("      %s ditolak %d, menunggu %ds" % (tk, e.code, jeda))
                time.sleep(jeda)
                continue
            return None, "HTTP %d" % e.code
        except Exception as e:                               # noqa: BLE001
            return None, str(e)[:60]
    return None, "ditolak terus"


def main():
    GUDANG.mkdir(parents=True, exist_ok=True)
    ds = json.loads((AKAR / "data" / "dataset.json").read_text(encoding="utf-8"))

    # Tanggal call paling awal per ticker: tidak ada gunanya menarik lilin dari
    # sebelum tickernya pernah di-call.
    awal = {}
    for b in ds["calls"] + ds.get("invest", []):
        t = b["ticker"]
        awal[t] = min(awal.get(t, "9999"), b["tanggal"])

    umur = UMUR_SEGAR
    if "--umur" in sys.argv:
        umur = float(sys.argv[sys.argv.index("--umur") + 1])
    paksa = "--semua" in sys.argv

    # Ticker yang SELURUH call-nya sudah tertutup tidak perlu harga baru lagi:
    # hasilnya sudah final, dan lilin sesudahnya tidak mengubah apa pun. Yang
    # tersisa hanya yang masih punya posisi berjalan atau muncul di Invest -
    # dan itulah satu-satunya yang benar-benar butuh harga sekarang.
    hidup = {b["ticker"] for b in ds["calls"] if b.get("status") == "ongoing"}
    hidup |= {b["ticker"] for b in ds.get("invest", [])}

    perlu, lewat, beku = [], 0, 0
    for tk, tgl in sorted(awal.items()):
        d = muat(tk)
        if not d:
            perlu.append((tk, tgl))          # belum pernah ditarik sama sekali
            continue
        if not paksa and tk not in hidup:
            beku += 1                        # semua call-nya sudah selesai
            continue
        if paksa or basi(d, umur) or d.get("sejak", "9999") > tgl:
            perlu.append((tk, tgl))
        else:
            lewat += 1

    print("ticker total %d | selesai (beku) %d | masih segar %d | ditarik %d"
          % (len(awal), beku, lewat, len(perlu)))
    if not perlu:
        return

    ok = gagal = 0
    for i, (tk, tgl) in enumerate(perlu, 1):
        lama = muat(tk)
        d, galat = tarik(tk, tgl, (lama or {}).get("lilin"))
        if galat:
            gagal += 1
            print("   %-6s GAGAL %s" % (tk, galat))
        else:
            (GUDANG / ("%s.json" % tk)).write_text(
                json.dumps(d, separators=(",", ":")), encoding="utf-8")
            ok += 1
        if i % 25 == 0:
            print("   ... %d/%d" % (i, len(perlu)), flush=True)
        time.sleep(JEDA)

    print("selesai: %d tersimpan, %d gagal -> %s" % (ok, gagal, GUDANG))


if __name__ == "__main__":
    main()

"""Tentukan TP/SL yang BENAR tercapai, dari riwayat harga, bukan dari klaim.

APA YANG DILAKUKAN
    Untuk tiap call, lilin harian sejak tanggal call ditelusuri berurutan:

      - kalau HIGH hari itu >= level TP, TP itu dicatat tercapai
      - kalau LOW hari itu <= stoploss, penelusuran BERHENTI di situ

    Hasilnya: TP tertinggi yang pernah disentuh harga sebelum posisinya kena
    stoploss. Itu definisi yang bisa diperiksa ulang siapa pun dengan chart.

SATU KETIDAKPASTIAN YANG TIDAK BISA DIHILANGKAN
    Lilin harian tidak menyimpan URUTAN di dalam satu hari. Kalau pada hari
    yang sama harga menyentuh TP1 DAN stoploss, tidak ada cara mengetahui mana
    yang lebih dulu dari data harian.

    Pilihan di sini: TP dihitung lebih dulu, lalu posisinya ditutup sebagai SL.
    Alasannya, analis memasang TP di atas entry dan SL di bawahnya, dan harga
    harus melewati TP dulu untuk sampai ke sana dalam skenario naik-lalu-jatuh.
    Kasus seperti ini ditandai `ragu: true` supaya bisa dihitung terpisah -
    bukan disembunyikan.

Pakai:
    python verifikasi_tp.py            -> data/verifikasi.json + ringkasan
    python verifikasi_tp.py --beda     -> daftar call yang klaimnya tidak cocok
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent
GUDANG = AKAR / "data" / "harga"

# Berapa hari bursa sebuah zona entry masih dianggap berlaku. Lewat ini, call
# yang harganya tak pernah turun ke zona dianggap hangus, bukan menunggu.
JENDELA_ISI = 10

# Seberapa dekat harga harus datang ke zona entry untuk dianggap terisi.
#
# 0,1% terlalu kejam: $META meleset 0,26%, $ADSK 0,35%, $NVDA 0,78% - lalu
# harganya lari naik 26-45%. Menyebut itu "posisi tidak pernah ada" secara
# teknis benar untuk order limit yang kaku, tetapi menyesatkan sebagai
# rekaman: hampir semua orang yang membaca call itu akan masuk di sekitar
# level tersebut.
#
# 1% adalah batas yang masih bisa dipertahankan. Di atas itu, yang dibeli
# bukan lagi harga yang ditulis analisnya.
TOLERANSI_ISI = 0.01


def lilin(tk):
    f = GUDANG / ("%s.json" % tk)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))["lilin"]
    except Exception:                                        # noqa: BLE001
        return None


def telusuri(b, lilins):
    """Kembalikan dict hasil verifikasi, atau None kalau tidak bisa dinilai."""
    entry = b.get("entry")
    if not entry:
        return None
    level = [(n, b.get("tp%d" % n)) for n in (1, 2, 3, 4)]
    level = [(n, v) for n, v in level if v]
    sl = b.get("sl")
    if not level and not sl:
        return None

    # Lilin pada hari call ikut dihitung: analis memposting saat pasar buka,
    # dan membuangnya akan melewatkan call yang langsung bergerak hari itu.
    jalur = [c for c in lilins if c[0] >= b["tanggal"]]
    if not jalur:
        return None

    # KOREKSI SPLIT. Yahoo memulangkan harga yang sudah disesuaikan pemecahan
    # saham, sedangkan entry/TP/SL analis adalah angka mentah saat call ditulis.
    # Untuk ticker yang split SETELAH call, keduanya berada di skala berbeda -
    # $CRWD tercatat entry 256 sementara riwayatnya 67,7, dan tanpa koreksi
    # seluruh levelnya mustahil tersentuh.
    #
    # Rasionya diukur dari lilin pertama setelah call. Ambangnya sengaja lebar:
    # entry limit yang meleset beberapa persen dari harga hari itu TIDAK boleh
    # ikut diskalakan, hanya selisih sebesar pemecahan saham yang boleh.
    acuan = (jalur[0][1] + jalur[0][2]) / 2
    skala = acuan / entry
    # Di luar rentang pemecahan saham yang masuk akal, selisihnya bukan split
    # melainkan entry yang salah baca. Call seperti itu TIDAK dinilai, bukan
    # diskalakan - menskalakan angka sampah hanya menyembunyikan bugnya.
    if not (0.05 < skala < 20):
        return None
    if not (0.7 < skala < 1.4):
        entry *= skala
        level = [(n, v * skala) for n, v in level]
        sl = sl * skala if sl else sl
    else:
        skala = 1.0

    # DUA pembacaan, dan selisihnya nyata:
    #   tertinggi      - TP tertinggi yang disentuh SEBELUM stoploss kena.
    #                    Ini yang bisa benar-benar dipanen seorang pemegang.
    #   tertinggiTotal - TP tertinggi yang pernah disentuh KAPAN PUN setelah
    #                    call terbit, meski posisinya sudah lama tersapu SL.
    # Keduanya disimpan; dashboard yang memilih mana yang dipakai.
    tertinggi = tertinggiTotal = 0
    puncak = puncakTotal = None
    kenaSL = False
    tglSL = None
    ragu = False
    # KAPAN POSISINYA TERBUKA.
    #
    # Ini order limit BELI: ia baru terisi saat harga TURUN menyentuh zona
    # entry. Menghitung TP/SL sejak tanggal posting berarti membebankan
    # stoploss pada posisi yang belum pernah dibuka - dan itu terjadi pada 110
    # dari 418 call, yang baru terisi beberapa hari setelah diposting.
    #
    # Pemicunya batas ATAS zona ("Entry: 157.5-160" terisi begitu harga <= 160),
    # sedangkan untung-ruginya tetap dihitung dari `entry` seperti persentase
    # yang ditulis analisnya sendiri. Asimetri ini disengaja supaya angka di
    # dashboard sebanding dengan angka di pesan aslinya.
    pemicu = b.get("entryAtas") or entry
    if b.get("entryAtas") and skala != 1.0:
        pemicu = b["entryAtas"] * skala
    # Zona entry TIDAK berlaku selamanya. Tanpa batas waktu, $SNAP yang
    # di-call September 2024 baru "terisi" Maret 2025 - 125 hari bursa
    # kemudian, saat kondisi yang mendasari call-nya sudah lama tidak ada.
    # Sepuluh hari bursa sudah longgar untuk order limit; lewat itu, call-nya
    # hangus, bukan menunggu.
    mulai = next((i for i, c in enumerate(jalur[:JENDELA_ISI])
                  if c[2] <= pemicu * (1 + TOLERANSI_ISI)), None)
    if mulai is None:
        # Limitnya tidak pernah tersentuh - tapi itu TIDAK berarti tidak ada
        # posisi. Analis menulis "Limit Entry: 93" lalu memberi call-nya saat
        # harga 95, dan membernya masuk di situ. Angka limit adalah level yang
        # diinginkan, bukan syarat mutlak.
        #
        # Jadi posisinya dianggap terbuka di hari call. Untung-ruginya tetap
        # dihitung dari `entry` yang ditulis analisnya, supaya persentase di
        # dashboard sebanding dengan yang tertulis di pesan aslinya.
        mulai = 0
    jalur = jalur[mulai:]

    # Patokan stoploss: penutupan harian kalau analisnya memang menulis begitu,
    # kalau tidak, harga terendah hari itu.
    pakai_close = bool(b.get("slClose"))
    for tgl, hi, lo, _cl in jalur:
        bawah = _cl if (pakai_close and _cl is not None) else lo
        puncakTotal = hi if puncakTotal is None else max(puncakTotal, hi)
        capai = [n for n, v in level if hi >= v]
        if capai:
            tertinggiTotal = max(tertinggiTotal, max(capai))
        if not kenaSL:
            puncak = hi if puncak is None else max(puncak, hi)
            if capai:
                tertinggi = max(tertinggi, max(capai))
            if sl and bawah is not None and bawah <= sl:
                kenaSL = True
                tglSL = tgl
                # Dua peristiwa di hari yang sama, urutannya tidak diketahui.
                if capai:
                    ragu = True

    def nilai(n):
        return (dict(level)[n] - entry) / entry * 100

    # SATU aturan:
    #   TP disentuh lebih dulu  -> TP tertinggi yang dicapai. Stoploss yang
    #                              datang SESUDAHNYA tidak membatalkannya,
    #                              karena posisinya sudah membayar.
    #   SL disentuh lebih dulu  -> SL. Pemegangnya sudah keluar; kenaikan
    #                              berbulan-bulan kemudian bukan miliknya.
    #   belum keduanya          -> ongoing.
    if tertinggi:
        status, hasil = "TP%d" % tertinggi, nilai(tertinggi)
    elif kenaSL:
        status, hasil = "SL", (sl - entry) / entry * 100
    else:
        status, hasil = "ongoing", None

    return {
        "status": status, "persen": hasil,
        "puncak": puncakTotal,
        "puncakPersen": (puncakTotal - entry) / entry * 100 if puncakTotal else None,
        "kenaSL": kenaSL, "tglSL": tglSL, "ragu": ragu,
        "skala": round(skala, 4),
        "lilinDipakai": len(jalur),
    }


def main():
    ds = json.loads((AKAR / "data" / "dataset.json").read_text(encoding="utf-8"))
    hasil = {}
    tak_bisa = collections.Counter()
    cocok = beda = 0
    contoh = []
    matriks = collections.Counter()

    for b in ds["calls"]:
        lp = lilin(b["ticker"])
        if lp is None:
            tak_bisa["tanpa riwayat harga"] += 1
            continue
        v = telusuri(b, lp)
        if v is None:
            tak_bisa["entry/level tidak lengkap"] += 1
            continue
        kunci = "%s|%s|%s" % (b["analis"], b["ticker"], b["tanggal"])
        hasil[kunci] = v
        # Bandingkan dengan KLAIM aslinya, bukan dengan b["status"].
        # gabung.py menimpa status dengan hasil verifikasi, jadi pada jalan
        # kedua dan seterusnya b["status"] sudah berisi jawaban yang sedang
        # diuji - dan angka kecocokannya melambung jadi omong kosong.
        klaim = b.get("klaim") or b["status"]
        matriks[(klaim, v["status"])] += 1
        if klaim == v["status"]:
            cocok += 1
        else:
            beda += 1
            if "--beda" in sys.argv and len(contoh) < 40:
                contoh.append("   %-6s %-5s %s  diklaim %-8s harga %-8s puncak %+.1f%%"
                              % (b["analis"], b["ticker"], b["tanggal"], klaim,
                                 v["status"], v["puncakPersen"] or 0))

    (AKAR / "data" / "verifikasi.json").write_text(
        json.dumps(hasil, separators=(",", ":")), encoding="utf-8")

    total = cocok + beda
    print("terverifikasi : %d call" % total)
    print("  klaim COCOK : %d (%.0f%%)" % (cocok, 100.0 * cocok / total if total else 0))
    print("  klaim BEDA  : %d" % beda)
    print("  ragu (TP dan SL di hari yang sama): %d"
          % sum(1 for v in hasil.values() if v["ragu"]))
    print("  dikoreksi split: %d call"
          % sum(1 for v in hasil.values() if v["skala"] != 1.0))
    for k, v in tak_bisa.items():
        print("  tidak dinilai: %d (%s)" % (v, k))

    print("\narah ketidakcocokan terbanyak:")
    for (klaim, nyata), n in matriks.most_common(10):
        if klaim != nyata:
            print("   diklaim %-8s ternyata %-8s : %d" % (klaim, nyata, n))

    for z in contoh:
        print(z)


if __name__ == "__main__":
    main()

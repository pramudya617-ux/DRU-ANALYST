"""Satukan Excel + Discord jadi satu dataset, lalu ambil harga berjalan.

ATURAN SUMBER (terbukti lewat cocok_excel.py)
    Untuk periode yang tumpang tindih, DISCORD menang. Jurnal Excel membulatkan
    saat disalin tangan (AMD 197.9 -> 197.79, NVDA 193.45 -> 193.0), dan
    jurnalnya juga tertinggal sekitar dua bulan dari channel.

    Tapi Excel TIDAK bisa dibuang:
      - Oracle sudah nonaktif dan channelnya tidak ada  -> Excel satu-satunya
      - Iron sebelum Sep 2025 (channel belum dibuat)    -> Excel satu-satunya

HARGA BERJALAN
    Diambil dari scanner TradingView: satu POST, tanpa API key, tanpa login.
    Analisnya memang sudah memakai TradingView - angka "Current Price" di
    jurnal cocok persis dengan yang dipulangkan endpoint ini.

    Bursanya tidak disimpan di mana pun, jadi ketiga prefiks dicoba sekaligus
    dalam satu panggilan; yang tidak ada tidak dipulangkan. Ticker yang sudah
    delisting (mis. WBA) memang tidak akan ketemu, dan itu ditangani dengan
    jatuh ke harga terakhir yang tercatat, bukan dengan menganggapnya nol.

Pakai:
    python gabung.py              -> data/dataset.json
    python gabung.py --tanpaharga -> lewati TradingView (offline)
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import datetime
import json
import urllib.request
from pathlib import Path

from cocok_excel import JURNAL, baca_jurnal

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent

# DARI MANA STATUS SEBUAH CALL DIAMBIL, per analis.
#
#   "klaim"  - apa yang analis catat/umumkan. Menghormati keputusan
#              diskresioner (keluar manual sebelum TP/SL) yang tidak terlihat
#              di grafik. Kelemahannya: baris yang lupa diperbarui tetap
#              tercatat "ongoing" walau harga sudah menembus stoploss.
#
#   "harga"  - telusuri lilin harian. Konsisten dan bisa diperiksa siapa pun,
#              tapi buta terhadap keluar manual.
#
#   "isi"    - klaim menang; harga hanya mengisi yang masih "ongoing".
#
# Oracle memakai "klaim" karena channelnya sudah berhenti: catatannya tidak
# akan bertambah lagi, jadi tidak ada baris yang akan jadi basi. Analis yang
# masih aktif memakai "harga", supaya status ikut bergerak sendiri begitu
# harga menyentuh TP tanpa menunggu pengumuman.
SUMBER_HASIL = {"Oracle": "klaim"}
SUMBER_BAWAAN = "harga"


def sumber(analis):
    return SUMBER_HASIL.get(analis, SUMBER_BAWAAN)



# Batas mulai sumber Discord per analis. Baris Excel sebelum tanggal ini
# dipertahankan; sesudahnya Discord yang dipakai.
AWAL_DISCORD = {"Tyler": "2024-09-16", "Iron": "2025-09-17", "Omni": "2026-09-01"}

NORMAL = {"stoploss": "SL", "sl": "SL", "cut loss": "SL", "cl": "SL",
          "ongoing": "ongoing", "open": "ongoing", "close": None}


def normal_status(s, tp_ada):
    """Samakan kosakata status dua sumber.

    CLOSE di Excel bukan hasil - itu kolom terpisah yang artinya posisinya sudah
    ditutup. Status sebenarnya ada di kolom sebelahnya, jadi CLOSE dipetakan ke
    None supaya tidak terhitung sebagai menang maupun kalah.
    """
    if not s:
        return "ongoing"
    k = str(s).strip().lower()
    if k in NORMAL:
        return NORMAL[k]
    if k.startswith("tp"):
        if "full" in k:
            # "FULL TP" = semua target kena. Dipetakan ke TP tertinggi yang
            # memang ada di call itu, bukan ke TP4 yang mungkin tidak pernah
            # ditulis analisnya.
            return "TP%d" % max(tp_ada) if tp_ada else "TP1"
        n = "".join(c for c in k if c.isdigit())
        return "TP%s" % (n or "1")
    return "ongoing"


# Status tutup yang TIDAK berasal dari level harga:
#   BEP    - keluar di titik impas, hasilnya nol.
#   Closed - ditutup manual sebelum TP maupun SL kena. Besarnya tidak bisa
#            disimpulkan dari level mana pun, jadi harus diisi tangan lewat
#            kolom persen di koreksi.html; tanpa itu ia tetap terhitung sebagai
#            call tertutup tapi tidak menyumbang gain.
TUTUP_MANUAL = {"BEP", "Closed"}


def hasil_persen(b):
    """Untung/rugi yang terealisasi, dihitung dari entry dan level yang kena.

    SENGAJA dihitung ulang, bukan menyalin kolom Progress dari Excel: ketiga
    jurnal menghitungnya dengan cara yang sedikit berbeda, dan angka yang tidak
    sebanding akan membuat perbandingan antar analis jadi menyesatkan.
    """
    e = b.get("entry")
    s = b.get("status") or ""
    if s == "BEP":
        return 0.0
    if s == "Closed":
        return None                          # hanya dari koreksi manual
    if not e:
        return None
    if s == "SL" and b.get("sl"):
        return (b["sl"] - e) / e * 100
    if s.startswith("TP"):
        v = b.get(s.lower())
        if v:
            return (v - e) / e * 100
    return None


def dari_excel(nama, path):
    baris = []
    for b in baca_jurnal(path):
        batas = AWAL_DISCORD.get(nama)
        if batas and b["tanggal"] >= batas:
            continue                         # periode ini dipegang Discord
        tp = {"tp%d" % (i + 1): v for i, v in enumerate(b["tp"])}
        baris.append({
            "analis": nama, "ticker": b["ticker"], "tanggal": b["tanggal"],
            "entry": b["entry"], "entryAtas": None, "sl": b["sl"],
            "timeframe": b["timeframe"], "kapitalisasi": None, "rrr": None,
            "sumber": "", "asal": "excel", "gambar": [], "pasti": True, **tp,
        })
    return baris


def tulis_mandiri(teks):
    """Suntik dataset ke dalam HTML jadi satu berkas tanpa subresource.

    dashboard.html memuat datanya lewat <script src>, yang butuh server.
    Berkas mandiri ini tidak punya subresource sama sekali, jadi tidak ada
    pertanyaan soal aturan file:// browser - bisa diklik ganda, ditaruh di
    Drive, atau dikirim sebagai satu lampiran.
    """
    sumber = (AKAR / "halaman" / "dashboard.html").read_text(encoding="utf-8")
    tanda = '<script src="data/dataset.js"></script>'
    if tanda not in sumber:
        raise SystemExit("dashboard.html tidak lagi memuat %s - perbarui gabung.py" % tanda)
    # Pemisahan </script> wajib: string itu di dalam JSON akan menutup tag
    # pembungkusnya lebih awal dan merusak seluruh halaman.
    aman = teks.replace("</", "<\\/")
    # Salinan kedua untuk web app. Next.js hanya boleh membaca berkas DI DALAM
    # folder aplikasinya - di Railway, direktori kerja proses adalah web/, dan
    # "../DRU-dashboard.html" berada di luar konteks build.
    (AKAR / "web" / "dasbor.html").write_text(
        sumber.replace(tanda, "<script>window.DATA = %s;</script>" % aman),
        encoding="utf-8")
    (AKAR / "DRU-dashboard.html").write_text(
        sumber.replace(tanda, "<script>window.DATA = %s;</script>" % aman),
        encoding="utf-8")
    # Halaman koreksi ikut dibangun dengan dataset di dalamnya, supaya versi
    # yang disajikan web app tidak membutuhkan rute data terpisah - satu rute
    # lebih sedikit berarti satu pintu lebih sedikit yang bisa lupa dijaga.
    kor_src = AKAR / "halaman" / "koreksi.html"
    if kor_src.exists():
        ks = kor_src.read_text(encoding="utf-8")
        tanda_k = '<script src="../data/dataset.js"></script>'
        if tanda_k in ks:
            (AKAR / "web" / "koreksi.html").write_text(
                ks.replace(tanda_k, "<script>window.DATA = %s;</script>" % aman),
                encoding="utf-8")

    # Benih koreksi: salinan yang ikut ter-deploy, dipakai hanya saat volume
    # masih kosong. Setelah ada penulisan pertama dari web, volume yang menang
    # dan berkas ini tidak pernah dilirik lagi.
    fk = AKAR / "data" / "koreksi.json"
    (AKAR / "web" / "koreksi-benih.json").write_text(
        fk.read_text(encoding="utf-8") if fk.exists() else "{}", encoding="utf-8")

    print("-> DRU-dashboard.html (%d KB)" % (len(sumber) + len(aman) >> 10))


def main():
    # Mengubah tampilan tidak perlu membaca ulang tiga workbook Excel dan
    # memanggil TradingView - itu 90 detik untuk perubahan CSS.
    if "--htmlsaja" in sys.argv:
        tulis_mandiri((AKAR / "data" / "dataset.json").read_text(encoding="utf-8"))
        return

    calls = json.loads((AKAR / "data" / "calls.json").read_text(encoding="utf-8"))
    semua = []

    for c in calls:
        semua.append({k: c.get(k) for k in (
            "analis", "ticker", "tanggal", "entry", "entryAtas", "tp1", "tp2",
            "tp3", "tp4", "sl", "slClose", "timeframe", "kapitalisasi", "rrr",
            "sumber", "gambar", "pasti")} | {"asal": "discord", "_status": c.get("status")})

    for nama, path in JURNAL.items():
        if path.exists():
            for b in dari_excel(nama, path):
                b["_status"] = None
                semua.append(b)

    # Status Excel diambil dari kolomnya sendiri; Discord sudah membawa sendiri.
    xl_status = {}
    for nama, path in JURNAL.items():
        if path.exists():
            for b in baca_jurnal(path):
                xl_status[(nama, b["ticker"], b["tanggal"])] = b["status"]

    for b in semua:
        tp_ada = [i for i in (1, 2, 3, 4) if b.get("tp%d" % i)]
        mentah = b.pop("_status") or xl_status.get((b["analis"], b["ticker"], b["tanggal"]))
        b["status"] = normal_status(mentah, tp_ada) or "ongoing"
        b["persen"] = hasil_persen(b)

    # Tambal: call Discord yang masih "ongoing" padahal jurnal sudah mencatat
    # hasilnya. Analis tidak selalu mengumumkan tiap TP di channel - $GOOG dan
    # $AMT kena TP3 menurut jurnal tanpa pernah diumumkan. Tanpa tambalan ini
    # keduanya terhitung belum selesai dan win rate ikut turun.
    #
    # Arahnya SATU JALAN SAJA: Excel hanya boleh mengisi yang kosong, tidak
    # boleh menimpa hasil dari Discord. Jurnalnya tertinggal sekitar dua bulan,
    # jadi "ongoing" di Excel sering hanya berarti belum sempat diperbarui.
    tambal = 0
    for nama, path in JURNAL.items():
        if not path.exists():
            continue
        for b in semua:
            if b["analis"] != nama or b["asal"] != "discord" or b["status"] != "ongoing":
                continue
            d = datetime.date.fromisoformat(b["tanggal"])
            for x in baca_jurnal(path):
                if x["ticker"] != b["ticker"]:
                    continue
                if abs((datetime.date.fromisoformat(x["tanggal"]) - d).days) > 14:
                    continue
                s = normal_status(x["status"], [i for i in (1, 2, 3, 4) if b.get("tp%d" % i)])
                if s and s != "ongoing":
                    b["status"] = s
                    b["asal"] = "discord+excel"
                    b["persen"] = hasil_persen(b)
                    tambal += 1
                    break
    print("ditambal dari jurnal: %d call Discord yang hasilnya tak diumumkan" % tambal)

    # KOREKSI MANUAL. Discord dan Excel adalah sumber yang dibaca ulang tiap
    # kali, jadi menghapus atau membetulkan sesuatu di dataset tidak akan
    # bertahan - jalan berikutnya akan membangkitkannya lagi. Karena itu
    # koreksi disimpan terpisah dan DITERAPKAN ULANG tiap kali.
    #
    # Penghapusan ditulis sebagai nisan (`dibatalkan: true`), bukan dengan
    # membuang barisnya, dengan alasan yang sama: baris yang dibuang akan
    # terbaca lagi dari sumbernya.
    fk = AKAR / "data" / "koreksi.json"
    if fk.exists():
        kor = json.loads(fk.read_text(encoding="utf-8"))
        pakai = batal = 0
        sisa = []
        for b in semua:
            k = kor.get("%s|%s|%s" % (b["analis"], b["ticker"], b["tanggal"]))
            if not k:
                sisa.append(b)
                continue
            if k.get("dibatalkan"):
                batal += 1
                continue
            for bidang in ("entry", "entryAtas", "tp1", "tp2", "tp3", "tp4",
                           "sl", "status", "timeframe", "catatan", "persen"):
                if bidang in k and k[bidang] is not None:
                    b[bidang] = k[bidang]
            b["dikoreksi"] = True
            # Persen yang ditulis tangan ikut mengunci: menghitung ulang dari
            # level akan membuangnya. Itu satu-satunya cara mencatat hasil
            # keluar manual, yang tidak punya level untuk dihitung.
            if k.get("persen") is None:
                b["persen"] = hasil_persen(b)
            else:
                b["persenDikunci"] = True
            # Status yang DITULIS TANGAN mengunci barisnya. Tanpa ini,
            # verifikasi harga di bawah akan menimpanya diam-diam, dan koreksi
            # manual jadi mustahil untuk analis yang sumbernya "harga" -
            # orangnya mengetik, menyimpan, lalu angkanya kembali sendiri.
            if k.get("status"):
                b["statusDikunci"] = True
            pakai += 1
            sisa.append(b)
        semua = sisa
        print("koreksi manual    : %d diubah, %d dibatalkan" % (pakai, batal))

    semua.sort(key=lambda b: (b["tanggal"], b["analis"]))

    invest = json.loads((AKAR / "data" / "invest.json").read_text(encoding="utf-8"))

    # Harga sekarang dan bursa dibaca dari singgahan riwayat yang sudah ada.
    # Panggilan terpisah ke scanner TradingView DIHAPUS: Yahoo memulangkan
    # regularMarketPrice dan exchangeName dalam respons yang sama dengan lilin
    # hariannya, jadi memanggil dua layanan untuk satu fakta hanya menambah
    # satu titik gagal tanpa menambah satu pun informasi.
    BURSA = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NSM": "NASDAQ",
             "NYQ": "NYSE", "ASE": "AMEX", "AMX": "AMEX", "PCX": "AMEX"}
    harga = {}
    gudang = AKAR / "data" / "harga"
    for f in sorted(gudang.glob("*.json")) if gudang.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            continue
        if d.get("hargaKini") is None:
            continue
        harga[d["ticker"]] = {
            "harga": d["hargaKini"],
            "bursa": BURSA.get(d.get("bursaYahoo"), d.get("bursaYahoo") or ""),
        }
    jalan = sorted({b["ticker"] for b in semua} | {b["ticker"] for b in invest})

    for b in semua:
        h = harga.get(b["ticker"])
        if h:
            b["bursa"] = h["bursa"]
            # Harga sekarang disimpan di SEMUA baris, bukan hanya yang ongoing:
            # halaman koreksi memakainya untuk tombol "pakai harga sekarang",
            # dan itu berlaku untuk baris mana pun yang hasilnya mau dikunci.
            b["hargaKini"] = h["harga"]
        if b["status"] == "ongoing" and h and b["entry"]:
            b["persen"] = (h["harga"] - b["entry"]) / b["entry"] * 100

    for b in invest:
        h = harga.get(b["ticker"])
        # Entry Invest selalu rentang ("790-810"). Titik tengahnya dipakai
        # supaya hasilnya tidak bisa dipilih-pilih ke sisi yang menguntungkan.
        tengah = ((b["entry"] + b["entryAtas"]) / 2
                  if b.get("entryAtas") else b.get("entry"))
        b["entryTengah"] = tengah
        # Umur pos ikut disimpan. Tanpa itu "+14%" tidak bisa ditafsirkan:
        # pos di sini umurnya 44 sampai 673 hari, jadi satu angka median
        # mencampur yang baru terbit enam minggu dengan yang sudah dua tahun.
        b["umurHari"] = (datetime.date.today()
                         - datetime.date.fromisoformat(b["tanggal"])).days
        if h and tengah:
            b["hargaKini"] = h["harga"]
            b["bursa"] = h["bursa"]
            b["persen"] = (h["harga"] - tengah) / tengah * 100

    # Avatar sebagai data URI, bukan tautan ke CDN Discord: URL avatar Discord
    # memuat tanda tangan yang kedaluwarsa, dan berkas mandiri harus tetap utuh
    # tanpa internet. Lihat ambil_avatar.py.
    fav = AKAR / "data" / "avatar.json"
    avatar = json.loads(fav.read_text(encoding="utf-8")) if fav.exists() else {}
    if not avatar:
        print("avatar.json belum ada - jalankan: python ambil_avatar.py")

    out = {
        "diperbarui": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "calls": semua,
        "invest": invest,
        "avatar": avatar,
        "bursa": {t: h["bursa"] for t, h in harga.items()},
    }
    # Hasil verifikasi harga ditempel sebagai lapisan TERPISAH, tidak menimpa
    # status klaim. Keduanya sah dan berbeda definisi: klaim analis mencatat
    # kapan posisinya ditutup, verifikasi mencatat level mana yang pernah
    # disentuh harga. Dashboard yang memilih mana yang ditampilkan.
    # CALL CACAT: level yang tidak mungkin berasal dari analis waras.
    # Call beli yang sah selalu punya TP di ATAS entry dan stoploss di BAWAHnya.
    # Kalau tidak, yang rusak adalah pembacaannya, bukan analisnya - dan
    # memverifikasi angka rusak hanya melahirkan hasil rusak yang terlihat
    # resmi. Baris begini ditandai, dikeluarkan dari verifikasi, dan dibiarkan
    # memakai klaim analis sampai dibetulkan lewat koreksi.html.
    cacat = 0
    for b in semua:
        e = b.get("entry")
        if not e:
            continue
        salah = []
        for n in (1, 2, 3, 4):
            v = b.get("tp%d" % n)
            if v is not None and v <= e:
                salah.append("tp%d<=entry" % n)
        if b.get("sl") is not None and b["sl"] >= e:
            salah.append("sl>=entry")
        if salah:
            b["cacat"] = ", ".join(salah)
            # Persennya ikut dikosongkan. Menghitung hasil dari level yang baru
            # saja dinyatakan tidak masuk akal akan memajang angka seperti
            # -77,8% yang terlihat resmi padahal berasal dari salah tulis.
            # Statusnya tetap dipakai (klaim analis masih mungkin benar),
            # hasilnya tidak ikut ke statistik gain.
            b["persen"] = None
            cacat += 1
    if cacat:
        print("call cacat        : %d (level tidak masuk akal, pakai klaim analis)" % cacat)

    fv = AKAR / "data" / "verifikasi.json"
    if fv.exists():
        ver = json.loads(fv.read_text(encoding="utf-8"))
        kena = 0
        for b in semua:
            if b.get("cacat"):
                continue                     # angkanya rusak, jangan diverifikasi
            v = ver.get("%s|%s|%s" % (b["analis"], b["ticker"], b["tanggal"]))
            if not v:
                continue
            kena += 1
            # Klaim aslinya SELALU disimpan, apa pun sumber yang dipilih:
            # tanpa itu selisih jurnal-vs-grafik tidak bisa ditelusuri lagi,
            # dan menukar SUMBER_HASIL jadi mustahil tanpa menarik ulang.
            if v["status"] != b["status"]:
                b["klaim"] = b["status"]
            b["vStatus"] = v["status"]
            b["vPersen"] = v["persen"]
            src = sumber(b["analis"])
            ambil = (not b.get("statusDikunci")
                     and (src == "harga"
                          or (src == "isi" and b["status"] == "ongoing")))
            if ambil:
                b["status"] = v["status"]
                b["persen"] = v["persen"]
            b["puncak"] = v["puncakPersen"]
            b["vKenaSL"] = v["kenaSL"]
            b["vRagu"] = v["ragu"]
            b["vSkala"] = v["skala"]
        print("verifikasi harga  : %d dari %d call (%d klaimnya berbeda)"
              % (kena, len(semua), sum(1 for b in semua if b.get("klaim"))))
        pakai = {a: sumber(a) for a in sorted({b["analis"] for b in semua})}
        dikunci = sum(1 for b in semua if b.get("statusDikunci"))
        print("sumber status     : %s%s"
              % (pakai, "  (%d dikunci koreksi manual)" % dikunci if dikunci else ""))
    else:
        print("verifikasi.json belum ada - jalankan tarik_harga.py lalu verifikasi_tp.py")

    teks = json.dumps(out, ensure_ascii=False)
    (AKAR / "data" / "dataset.json").write_text(teks, encoding="utf-8")
    (AKAR / "data" / "dataset.js").write_text(
        "window.DATA = %s;" % teks, encoding="utf-8")

    tulis_mandiri(teks)

    print("total call  : %d" % len(semua))
    for nama in ("Tyler", "Iron", "Omni", "Oracle"):
        s = [b for b in semua if b["analis"] == nama]
        d = sum(1 for b in s if b["asal"] == "discord")
        tutup = [b for b in s if b["status"] not in ("ongoing", "tak-terisi")]
        menang = sum(1 for b in tutup if b["status"].startswith("TP"))
        print("  %-7s %3d call (%3d discord, %3d excel)  win %d/%d = %.0f%%"
              % (nama, len(s), d, len(s) - d, menang, len(tutup),
                 100.0 * menang / len(tutup) if tutup else 0))
    print("harga + bursa: %d dari %d ticker terpeta" % (len(harga), len(jalan)))


if __name__ == "__main__":
    main()

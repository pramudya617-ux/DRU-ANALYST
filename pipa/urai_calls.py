"""Ubah pesan mentah Discord jadi baris call terstruktur.

KENAPA REGEX, BUKAN LLM
    Ketiga analis memposting dengan template tetap: Entry, TP1-4, SL, Timeframe
    di baris sendiri-sendiri. Regex itu deterministik, gratis, dan bisa diuji.
    LLM per pesan berarti hasil parsing bisa berbeda tiap dijalankan — untuk
    angka entry dan stoploss itu tidak bisa diterima.

    Variasi antar analis ditangani lewat beberapa pola alternatif, BUKAN lewat
    cabang per-analis. Formatnya berubah seiring waktu (Tyler 2024 memakai
    "Entry :", 2026 memakai "Limit Entry :"), jadi mengikat pola ke nama analis
    akan patah sendiri.

DUA JENIS PESAN
    CALL  - punya Entry dan setidaknya satu TP atau SL.
    HASIL - balasan ke sebuah call, isinya kabar "TP1 kena" / "SL triggered".
            Ditautkan lewat message_reference, BUKAN lewat tebakan "pesan
            berikutnya yang menyebut ticker sama".

Pakai:
    python urai_calls.py            -> data/calls.json + ringkasan
    python urai_calls.py --dump     -> tulis juga pesan yang tidak terklasifikasi
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent

# Ticker: "$MRVL", "## $ABNB– Airbnb", "# SHOP". Didahulukan yang pakai $
# karena itu yang paling tidak ambigu; judul tanpa $ baru dipakai kalau tak ada.
RE_TICKER_DOLAR = re.compile(r"\$([A-Z]{1,5})(?![A-Za-z0-9.])")
RE_TICKER_JUDUL = re.compile(r"^#{1,3}\s*\**\s*([A-Z]{1,5})\b", re.M)

# "Limit Entry : 253", "Entry : 425-430", "Entry: pre-market price (440 - 442)".
# Teks apa pun antara kata Entry dan angka pertama dilompati, tapi dibatasi 30
# karakter supaya tidak menyeret angka dari baris berikutnya.
# Harga boleh memakai pemisah ribuan: "Entry: 1,256-1,257". Tanpa ini regex
# berhenti di koma dan memulangkan 1 - kesalahan yang lolos diam-diam sampai
# verifikasi harga memulangkan +112.600%.
# Menerima pemisah ribuan ("1,558") DAN desimal gaya Indonesia ("136,2").
# Kelompok ribuan dicoba lebih dulu, jadi "1,558" tidak terbaca 1,558.
NUM = r"[0-9]+(?:,[0-9]{3})*(?:[.,][0-9]+)?"
RE_ENTRY = re.compile(
    r"\bEntry\b\s*:?[^\n0-9]{0,30}(" + NUM + r")\s*(?:[-–—]\s*(" + NUM + r"))?",
    re.I)
# "TP 1 : 280", "TP1: 169.46", "TP : 465". Nomor opsional -> dianggap TP1.
# Nomor TP hanya diakui kalau TIDAK diikuti digit atau titik. Tanpa
# penjaga itu, "TP 141.2" terbaca sebagai TP nomor 1 dengan harga 41.2 -
# dan hasilnya muncul di dashboard sebagai TP1 bernilai -70%.
RE_TP = re.compile(r"\bTP\s*(?:([1-4])(?![0-9.]))?\s*:?\s*(" + NUM + r")", re.I)
# Stoploss tidak selalu ditulis sebagai angka telanjang. Omni menulis
# "SL: daily candle close under 14.87" - kalimat di antara label dan
# harganya. Sela diizinkan, tapi TANPA baris baru dan TANPA digit, supaya
# angka dari baris berikutnya tidak ikut tersedot.
RE_SL = re.compile(r"\bSL\b\s*:?[^\n0-9]{0,40}(" + NUM + r")", re.I)
# "close under/below X" adalah aturan yang BERBEDA dari "harga menyentuh X":
# yang membatalkan posisi adalah penutupan harian, bukan sundulan intraday.
# Bedanya nyata - banyak lilin menusuk level lalu menutup di atasnya.
RE_SL_CLOSE = re.compile(r"\bSL\b[^\n]{0,40}\bclose\b", re.I)
RE_TIMEFRAME = re.compile(r"Timeframe\s*:?\s*\**\s*([^\n*]{1,40})", re.I)
RE_SCALP = re.compile(r"#\s*SCALPING|1\s*day\s*trade", re.I)
RE_RRR = re.compile(r"(?:RRR|Risk\s*/?\s*Reward)\s*:?\s*\**\s*1\s*:\s*([0-9]+(?:\.[0-9]+)?)", re.I)
RE_CAP = re.compile(r"(Big|Mid|Small)\s*Caps?", re.I)

# Kabar hasil. Urutan penting: rugi diperiksa SEBELUM TP, karena pesan cutloss
# kerap ikut menyebut angka TP yang gagal dicapai ("Fail to reach TP high at
# 152.5 ... CUTLOSS").
#
# "CL" adalah istilah Tyler untuk cut loss dan muncul jauh lebih sering daripada
# "SL" di channelnya. Batas kata wajib: tanpa itu ticker seperti $CLSK ikut
# tertangkap.
RE_HASIL_SL = re.compile(
    r"\b(CL|CUT\s*LOSS|CUTLOSS|SL\s*(?:triggered|kena|hit)|STOP\s*LOSS)\b", re.I)
RE_HASIL_FULL = re.compile(r"\bFULL\s*TP\b", re.I)
RE_HASIL_TP = re.compile(r"\bTP\s*([1-4])\b", re.I)
# Menyebut "TP2" TIDAK berarti TP2 kena. Analis juga menulis saat HAMPIR kena,
# dan kalimat itu bentuknya nyaris sama: "TP1 SOON", "Nyaris banget TP1",
# "Setipis itu buat TP3 for $DJT". Tanpa penyaring ini semuanya terhitung
# sebagai kemenangan - persis jenis galat yang menaikkan win rate secara palsu.
# Hanya berlaku untuk cabang TP; kabar rugi sudah ditangani lebih dulu di atas.
RE_BELUM = re.compile(
    r"\b(soon|nyaris|hampir|almost|setipis|belum|menuju|mendekati|"
    r"approaching|close to|on the way|tinggal)\b", re.I)
RE_PERSEN = re.compile(r"([+-]?\s*[0-9]+(?:[.,][0-9]+)?)\s*%")
RE_KATA = re.compile(r"\b([A-Z]{1,5})\b")

# Kata yang bentuknya seperti ticker tapi di pesan hasil hampir selalu berarti
# hal lain. CL dan A benar-benar ticker (Colgate, Agilent) - justru itu
# masalahnya, keduanya lolos pemeriksaan kosakata.
KATA_HASIL = {"CL", "SL", "TP", "TP1", "TP2", "TP3", "TP4", "FULL", "HIT",
              "A", "I", "AT", "IN", "IS", "IT", "OR", "ON", "NO", "DO", "SO",
              "UP", "WE", "BE", "ALL", "FOR", "AND", "THE", "NEW", "BUY"}


def angka(s):
    """Koma bisa berarti dua hal di jurnal ini.

    "1,256" adalah seribu dua ratus lima puluh enam (pemisah ribuan), sedangkan
    "+10,67%" adalah sepuluh koma enam tujuh (desimal gaya Indonesia). Yang
    membedakan: pemisah ribuan selalu diikuti TEPAT tiga digit.
    """
    if not s:
        return None
    t = re.sub(r",(?=[0-9]{3}(?![0-9]))", "", str(s).strip())
    return float(t.replace(",", "."))


def ticker(teks):
    m = RE_TICKER_DOLAR.search(teks)
    if m:
        return m.group(1)
    m = RE_TICKER_JUDUL.search(teks)
    return m.group(1) if m else None


def urai_call(teks):
    """Kembalikan dict call, atau None kalau ini bukan call."""
    e = RE_ENTRY.search(teks)
    tps = RE_TP.findall(teks)
    sl = RE_SL.search(teks)
    if not e or (not tps and not sl):
        return None
    tk = ticker(teks)
    if not tk:
        return None

    # TP tanpa nomor ("TP : 465") dianggap TP1. Kalau nomornya ada, dipakai apa
    # adanya supaya urutan tidak tertukar saat analis melompati TP2.
    # YANG PERTAMA MENANG. Blok harga selalu ditulis di atas, prosa analisanya
    # di bawah - dan prosa itu kerap menyebut "TP 2" atau "balik ke TP 3" tanpa
    # harga. Sebutan begitu tak bernomor di mata regex, jatuh ke tp1, dan
    # menimpa harga TP1 yang sudah benar: $NVDA sempat tercatat tp1 = 3.0.
    tp = {}
    for n, v in tps:
        k = "tp%s" % (n or "1")
        if k not in tp:
            tp[k] = angka(v)

    tf = None
    if RE_SCALP.search(teks):
        tf = "Scalping"
    else:
        m = RE_TIMEFRAME.search(teks)
        if m:
            tf = m.group(1).strip(" *:")

    cap = RE_CAP.search(teks)
    rrr = RE_RRR.search(teks)
    return {
        "ticker": tk,
        "entry": angka(e.group(1)),
        # Entry sering ditulis rentang ("425-430"). Batas atas disimpan terpisah
        # supaya tidak ada yang diam-diam dibulatkan jadi satu angka.
        "entryAtas": angka(e.group(2)),
        "tp1": tp.get("tp1"), "tp2": tp.get("tp2"),
        "tp3": tp.get("tp3"), "tp4": tp.get("tp4"),
        "sl": angka(sl.group(1)) if sl else None,
        "slClose": bool(RE_SL_CLOSE.search(teks)),
        "timeframe": tf,
        "kapitalisasi": (cap.group(1).title() + " Caps") if cap else None,
        "rrr": angka(rrr.group(1)) if rrr else None,
    }


def urai_hasil(teks, kosakata, wajib_ticker=True):
    """Kembalikan dict hasil, atau None kalau ini bukan kabar hasil.

    `kosakata` adalah himpunan ticker yang pernah muncul di call. Dipakai karena
    kabar hasil sering menulis ticker TANPA tanda $ ("FULL TP for CLSK"), dan
    menebaknya lewat pola huruf besar saja akan menangkap kata seperti FULL, TP,
    atau CL. Mencocokkan ke kosakata jauh lebih tepat daripada daftar stopword
    yang harus ditambal terus.
    """
    if RE_HASIL_SL.search(teks):
        jenis = "SL"
    elif RE_HASIL_FULL.search(teks):
        jenis = "TP_FULL"
    else:
        # Negasi diperiksa per-sebutan, BUKAN per-pesan. Satu pesan sering
        # memuat keduanya sekaligus: "TP 1 HIT in just a week! ... TP2 soon?"
        # TP1-nya kena, TP2-nya belum. Membuang seluruh pesan karena ada kata
        # "soon" menghapus kemenangan yang sah - terukur: agreement dengan
        # jurnal Excel turun dari 78% ke 75% saat negasinya se-pesan.
        jenis = None
        for m in RE_HASIL_TP.finditer(teks):
            jendela = teks[max(0, m.start() - 30):m.end() + 15]
            if RE_BELUM.search(jendela):
                continue
            jenis = "TP%s" % m.group(1)
            break
        if not jenis:
            return None

    # Satu pesan bisa mengabarkan beberapa ticker sekaligus:
    # "CL for $MU, $SIRI, dan $COP" adalah TIGA hasil, bukan satu.
    #
    # Kalau ada ticker bertanda $, HANYA itu yang dipercaya. Pencarian kata
    # telanjang baru dipakai kalau tidak ada satu pun - dan itu penting, karena
    # beberapa KATA KUNCI HASIL ternyata juga ticker sungguhan: CL adalah
    # Colgate-Palmolive, A adalah Agilent. Versi sebelumnya membaca "CL for $F"
    # sebagai kabar untuk Colgate, dan 35 dari 43 "yatim" berasal dari situ.
    tickers = [t for t in RE_TICKER_DOLAR.findall(teks) if t in kosakata]
    if not tickers:
        tickers = [t for t in RE_KATA.findall(teks)
                   if t in kosakata and t not in KATA_HASIL and len(t) > 1]
    if not tickers and wajib_ticker:
        return None

    p = RE_PERSEN.search(teks)
    return {
        "jenis": jenis,
        "persen": angka(p.group(1).replace(" ", "")) if p else None,
        "tickers": tickers,
    }


RE_BIDANG = {
    "ticker": re.compile(r"Kode\s*Saham\s*:\s*\$?([A-Z]{1,5})", re.I),
    "sektor": re.compile(r"Sektor\s*:\s*([^\n>]{2,40})", re.I),
    "industri": re.compile(r"Industri\s*:\s*([^\n>]{2,50})", re.I),
    "kapitalisasi": re.compile(r"MarketCap\s*:\s*([^\n>]{2,20})", re.I),
}
RE_ENTRY_INV = re.compile(r"Entry\s*:\s*(" + NUM + r")\s*(?:[-–—]\s*(" + NUM + r"))?", re.I)
RE_FUNDA = re.compile(r"ANALISA\s*FUNDAMENTAL.*?\n>\s*(.{40,600})", re.I | re.S)


def urai_invest(pesan):
    """Pos OUTLOOK INVEST: pilihan jangka panjang, TANPA TP dan TANPA SL.

    Karena tidak ada target maupun stoploss, "win rate" tidak punya arti di
    sini - satu-satunya ukuran yang jujur adalah pergerakan harga sejak pos
    terbit. Itu sebabnya segmen ini tidak digabung ke statistik analis.
    """
    out = []
    for p in reversed(pesan):
        t = p["teks"]
        e = RE_ENTRY_INV.search(t)
        m = RE_BIDANG["ticker"].search(t)
        if not e or not m:
            continue
        b = {"ticker": m.group(1), "entry": angka(e.group(1)),
             "entryAtas": angka(e.group(2)), "tanggal": p["waktu"][:10],
             "waktu": p["waktu"], "penulis": p["penulis"],
             "sumber": p["sumber"], "gambar": p["gambar"]}
        for k, rx in RE_BIDANG.items():
            if k == "ticker":
                continue
            g = rx.search(t)
            b[k] = g.group(1).strip(" *`") if g else None
        f = RE_FUNDA.search(t)
        b["ringkas"] = " ".join(f.group(1).split())[:420] if f else None
        out.append(b)
    return out


def main():
    mentah = json.loads((AKAR / "data" / "calls_mentah.json").read_text(encoding="utf-8"))
    calls, bukan_call = [], []

    # LANGKAH 1 - kumpulkan call lebih dulu. Kosakata ticker dari sini yang
    # dipakai langkah 2; tanpa itu kabar hasil tanpa tanda $ tidak terbaca.
    for nama, pesan in mentah.items():
        if nama.lower() == "invest":
            continue                         # segmen tersendiri, diurai di bawah
        # Pesan datang terbaru-dulu; dibalik supaya call selalu terlihat
        # sebelum kabar hasilnya.
        for p in reversed(pesan):
            c = urai_call(p["teks"])
            if c:
                c.update({
                    "analis": nama, "tanggal": p["waktu"][:10], "waktu": p["waktu"],
                    "pesanId": p["pesanId"], "sumber": p["sumber"],
                    "gambar": p["gambar"], "hasil": [],
                })
                calls.append(c)
            else:
                bukan_call.append((nama, p))

    kosakata = {c["ticker"] for c in calls}

    # LANGKAH 2 - tempel kabar hasil.
    indeks_pesan = {c["pesanId"]: c for c in calls}
    nempel = yatim = 0
    sisa = []
    for nama, p in bukan_call:
        h = urai_hasil(p["teks"], kosakata)
        if not h and p["balasKe"] in indeks_pesan:
            # Kalau pesannya BALASAN ke sebuah call, induknya sudah pasti dan
            # tickernya tidak diperlukan sama sekali. Itu membuka kabar seperti
            # "TP 1 HIT in just a week!" yang memang tidak pernah menyebut
            # ticker karena konteksnya ada di pesan yang dibalas.
            h = urai_hasil(p["teks"], kosakata, wajib_ticker=False)
        if not h:
            sisa.append(p)
            continue
        catatan = {"jenis": h["jenis"], "persen": h["persen"],
                   "waktu": p["waktu"], "sumber": p["sumber"]}

        # Balasan adalah tautan PASTI ke call aslinya - selalu didahulukan.
        induk = indeks_pesan.get(p["balasKe"]) if p["balasKe"] else None
        if induk:
            induk["hasil"].append(dict(catatan, cara="balasan"))
            nempel += 1
            continue

        # Tyler mengumumkan hasil sebagai pesan berdiri sendiri, jadi untuk dia
        # tautan pastinya tidak ada. Jatuh ke pencocokan ticker: call TERAKHIR
        # milik analis yang sama, dengan ticker itu, yang waktunya SEBELUM kabar
        # ini. Ditandai cara="ticker" supaya dashboard bisa membedakan hasil
        # yang pasti dari yang disimpulkan.
        #
        # Call yang SUDAH punya hasil tetap boleh menerima hasil berikutnya:
        # satu posisi bergerak TP1 -> TP2 -> TP3, dan tiap tahap diumumkan
        # terpisah. Versi pertama kode ini menolaknya, dan akibatnya seluruh
        # TP2-TP4 Tyler hilang jadi "yatim".
        for tk in h["tickers"]:
            calon = [c for c in calls
                     if c["analis"] == nama and c["ticker"] == tk
                     and c["waktu"] < p["waktu"]]
            if not calon:
                yatim += 1
                continue
            induk = max(calon, key=lambda c: c["waktu"])
            if any(x["waktu"] == catatan["waktu"] and x["jenis"] == catatan["jenis"]
                   for x in induk["hasil"]):
                continue                     # pesan yang sama disebut dua kali
            induk["hasil"].append(dict(catatan, cara="ticker"))
            nempel += 1

    # Status akhir = tingkat TERTINGGI yang pernah dicapai, bukan kabar
    # pertama. Satu posisi bisa kena TP1 lalu lanjut TP3; jurnal Excel mencatat
    # yang tertinggi, dan dashboard harus setuju dengan jurnal.
    urut = {"SL": 0, "TP1": 1, "TP2": 2, "TP3": 3, "TP4": 4, "TP_FULL": 5}
    for c in calls:
        if not c["hasil"]:
            c["status"] = "ongoing"
            continue
        puncak = max(c["hasil"], key=lambda h: urut.get(h["jenis"], 0))
        c["status"] = puncak["jenis"]
        c["persen"] = puncak["persen"]
        # Kalau SATU-satunya kabar adalah SL, itu kerugian. Kalau ada TP lebih
        # dulu, posisinya sudah untung duluan - dan itu beda cerita.
        c["kenaSL"] = any(h["jenis"] == "SL" for h in c["hasil"])
        c["pasti"] = all(h["cara"] == "balasan" for h in c["hasil"])

    (AKAR / "data" / "calls.json").write_text(
        json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")

    inv = urai_invest(mentah.get("invest", []))
    (AKAR / "data" / "invest.json").write_text(
        json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")

    print("CALL terurai : %d" % len(calls))
    print("INVEST       : %d dari %d pos" % (len(inv), len(mentah.get("invest", []))))
    for nama in mentah:
        n = sum(1 for c in calls if c["analis"] == nama)
        lengkap = sum(1 for c in calls if c["analis"] == nama and c["sl"] and c["tp1"])
        print("   %-6s %3d call, %3d punya TP1+SL lengkap" % (nama, n, lengkap))
    pasti = sum(1 for c in calls for h in c["hasil"] if h["cara"] == "balasan")
    simpul = sum(1 for c in calls for h in c["hasil"] if h["cara"] == "ticker")
    berhasil = sum(1 for c in calls if c["hasil"])
    print("HASIL nempel : %d (%d lewat balasan/pasti, %d lewat ticker/disimpulkan)"
          % (nempel, pasti, simpul))
    print("             : %d dari %d call punya hasil, %d yatim" % (berhasil, len(calls), yatim))
    print("TIDAK terurai: %d" % len(sisa))

    if "--dump" in sys.argv:
        f = AKAR / "data" / "tidak_terurai.txt"
        with f.open("w", encoding="utf-8") as fh:
            for p in sisa:
                fh.write("--- %s %s\n%s\n\n" % (p["waktu"][:16], p["sumber"], p["teks"][:500]))
        print("-> %s" % f)


if __name__ == "__main__":
    main()

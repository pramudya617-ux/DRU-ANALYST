"""Adu status hasil parser Discord dengan status di jurnal Excel.

cocok_excel.py membuktikan angka ENTRY-nya cocok. Berkas ini menguji hal yang
berbeda dan lebih rawan: apakah HASILNYA (TP1/TP2/SL) juga cocok.

Itu bagian yang paling mungkin salah, karena 148 dari 231 kabar hasil ditempel
lewat pencocokan ticker, bukan lewat balasan Discord yang pasti. Kalau
penempelan itu meleset, win rate di dashboard ikut meleset - dan tidak ada yang
akan menyadarinya.

Pakai:
    python audit_status.py
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import collections
import datetime
import json
from pathlib import Path

from cocok_excel import JURNAL, baca_jurnal

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent


def normal(s):
    if s is None:
        return None
    k = str(s).strip().lower()
    if k.startswith("tp"):
        n = "".join(c for c in k if c.isdigit())
        return "TP%s" % (n or "1")
    if k in ("sl", "stoploss", "cut loss", "cutloss", "cl"):
        return "SL"
    if k in ("ongoing", "open"):
        return "ongoing"
    return None                              # CLOSE dan sejenisnya: bukan hasil


def main():
    calls = json.loads((AKAR / "data" / "dataset.json").read_text(encoding="utf-8"))["calls"]

    for nama in ("Tyler", "Iron"):
        dc = [c for c in calls if c["analis"] == nama and c["asal"] == "discord"]
        xl = baca_jurnal(JURNAL[nama])
        awal = min(c["tanggal"] for c in dc)

        setuju = beda = 0
        matriks = collections.Counter()
        contoh = []
        for b in xl:
            if b["tanggal"] < awal:
                continue
            xs = normal(b["status"])
            if xs is None:
                continue
            kandidat = [c for c in dc if c["ticker"] == b["ticker"]
                        and abs((datetime.date.fromisoformat(c["tanggal"])
                                 - datetime.date.fromisoformat(b["tanggal"])).days) <= 14]
            if not kandidat:
                continue
            if b["entry"] is not None:
                kandidat.sort(key=lambda c: abs((c["entry"] or 0) - b["entry"]))
            ds = kandidat[0]["status"]
            matriks[(xs, ds)] += 1
            if xs == ds:
                setuju += 1
            else:
                beda += 1
                if len(contoh) < 8:
                    contoh.append("   %s %-5s excel=%-7s discord=%-7s"
                                  % (b["tanggal"], b["ticker"], xs, ds))

        total = setuju + beda
        print("\n%s" % ("=" * 62))
        print("%s  status cocok %d / %d  (%.0f%%)"
              % (nama, setuju, total, 100.0 * setuju / total if total else 0))
        for z in contoh:
            print(z)

        # Yang paling penting: apakah MENANG/KALAH-nya tertukar, bukan apakah
        # nomor TP-nya persis. TP2 terbaca TP1 tidak mengubah win rate.
        def sisi(s):
            return "menang" if s.startswith("TP") else ("rugi" if s == "SL" else "jalan")
        salah_sisi = sum(v for (a, b2), v in matriks.items() if sisi(a) != sisi(b2))
        print("   salah NOMOR TP saja : %d" % (beda - salah_sisi))
        print("   salah MENANG/RUGI   : %d  <- ini yang menggeser win rate" % salah_sisi)


if __name__ == "__main__":
    main()

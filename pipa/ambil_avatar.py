"""Unduh avatar Discord tiap analis, simpan sebagai data URI.

KENAPA DIUNDUH, BUKAN DITAUTKAN
    DRU-dashboard.html dibangun tanpa satu pun subresource supaya bisa diklik
    ganda, ditaruh di Drive, atau dikirim sebagai satu lampiran. Menautkan ke
    cdn.discordapp.com akan membatalkan itu - berkasnya jadi butuh internet,
    dan URL avatar Discord memuat tanda tangan `ex=`/`hm=` yang KEDALUWARSA.
    Gambar yang hari ini tampil akan jadi kotak kosong beberapa minggu lagi.

    ID dan hash avatarnya tidak ditulis tangan: keduanya sudah ikut tertarik di
    tiap pesan oleh tarik_calls.py. Oracle tidak punya channel calls, tetapi
    menulis di channel Invest - dari situlah identitasnya terbaca.

Pakai:
    python ambil_avatar.py      -> data/avatar.json
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import base64
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent

# Nama tampilan di Discord tidak selalu sama dengan nama yang dipakai dashboard.
# Omni memakai nama "Kris" di Discord; tanpa peta ini avatarnya tidak ketemu.
NAMA = {"Tyler": "Tyler", "Iron": "Iron", "Omni": "Kris", "Oracle": "Oracle"}


def main():
    mentah = json.loads((AKAR / "data" / "calls_mentah.json").read_text(encoding="utf-8"))
    jati = {}
    for pesan in mentah.values():
        for p in pesan:
            if p.get("penulisId") and p.get("avatarHash"):
                jati[p["penulis"]] = (p["penulisId"], p["avatarHash"])

    out = {}
    for nama, di_discord in NAMA.items():
        if di_discord not in jati:
            print("%-7s tidak ketemu di pesan mana pun" % nama)
            continue
        uid, h = jati[di_discord]
        url = "https://cdn.discordapp.com/avatars/%s/%s.png?size=64" % (uid, h)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:                               # noqa: BLE001
            print("%-7s gagal: %s" % (nama, e))
            continue
        out[nama] = "data:image/png;base64," + base64.b64encode(data).decode()
        print("%-7s %s  %5.1f KB -> %5.1f KB base64"
              % (nama, di_discord, len(data) / 1024, len(out[nama]) / 1024))

    (AKAR / "data" / "avatar.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("-> data/avatar.json (%d avatar, total %.0f KB)"
          % (len(out), sum(len(v) for v in out.values()) / 1024))


if __name__ == "__main__":
    main()

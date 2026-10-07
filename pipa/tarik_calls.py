"""Tarik riwayat calls analis DRU dari Discord, lewat Bot API resmi.

KENAPA BOT RESMI, BUKAN TOKEN AKUN PRIBADI
    Memakai token akun sendiri untuk membaca pesan (self-bot) melanggar
    Ketentuan Layanan Discord secara eksplisit dan berujung banned permanen.
    Bot punya identitas sendiri, diundang pemilik server, dan hanya melihat
    channel yang izinnya diberikan.

SIAPKAN SEKALI
    1. discord.com/developers/applications -> aplikasi baru
    2. Tab "Bot" -> Reset Token -> setx DRU_BOT_TOKEN "..."
    3. Tab "Bot" -> nyalakan MESSAGE CONTENT INTENT.
       TANPA INI GAGALNYA DIAM-DIAM: pesan tetap terhitung ada, tetapi
       `content`-nya string kosong. Kelihatan seperti channel sepi, bukan
       seperti error. `--probe` di bawah memang dibuat untuk menangkap ini.
    4. Tab "OAuth2" -> URL Generator -> scope `bot`, permission
       `View Channels` + `Read Message History` -> undang ke server DRU

    Nama variabelnya SENGAJA bukan DISCORD_BOT_TOKEN: mesin ini sudah punya
    token bot DRC dengan nama itu, dan `setx` menimpa tanpa bertanya.

Pakai:
    python tarik_calls.py --probe     -> cek akses + intent, tidak menulis apa pun
    python tarik_calls.py             -> seluruh riwayat -> data/calls_mentah.json
    python tarik_calls.py --nama Omni -> satu analis saja
"""
import sys

# Nama analis/pesan bisa memuat karakter di luar cp1252 (tanda kutip miring,
# emoji). Windows memakai cp1252 begitu keluaran dialihkan ke berkas atau
# ditangkap proses lain, dan satu print sudah cukup menjatuhkan seluruh
# penarikan dengan UnicodeEncodeError. Sudah kejadian di proyek DRC.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Skrip pipeline tinggal di pipa/; data dan halaman ada di akar proyek.
AKAR = HERE.parent
API = "https://discord.com/api/v10"
# Discord mensyaratkan format User-Agent "DiscordBot (url, versi)".
UA = "DiscordBot (https://localhost, 1.0)"
RE_URL = re.compile(r"https?://\S+")

TOKEN = os.environ.get("DRU_BOT_TOKEN", "")
if not TOKEN:
    # .env hanya dibaca kalau environment aslinya kosong — environment menang.
    _env = HERE / ".env"
    if _env.exists():
        for _baris in _env.read_text(encoding="utf-8").splitlines():
            if _baris.strip().startswith("DRU_BOT_TOKEN="):
                TOKEN = _baris.split("=", 1)[1].strip().strip('"')


def minta(url):
    """GET ke Discord dengan penanganan 429. Kembalikan (data, galat)."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bot {TOKEN}", "User-Agent": UA})
    for _ in range(5):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Discord menyebut jedanya sendiri; menebak sendiri justru
                # memperpanjang hukumannya.
                try:
                    jeda = float(json.loads(e.read()).get("retry_after", 2))
                except Exception:                            # noqa: BLE001
                    jeda = 2.0
                time.sleep(min(jeda + 0.3, 30))
                continue
            return None, "HTTP %d %s" % (e.code, e.read()[:160].decode("utf8", "replace"))
        except Exception as e:                               # noqa: BLE001
            return None, str(e)
    return None, "429 terus menerus"


def baca_channel(cid, guild="", sampai=None):
    """Ambil pesan dari yang terbaru mundur ke belakang.

    Discord memulangkan maksimal 100 pesan sekali panggil, terbaru lebih dulu,
    dan halaman berikutnya diambil lewat parameter `before`.
    """
    pesan, sebelum, gagal = [], None, None
    for _ in range(300):                     # atap 30.000 pesan per channel
        q = {"limit": 100}
        if sebelum:
            q["before"] = sebelum
        batch, galat = minta("%s/channels/%s/messages?%s" % (API, cid, urllib.parse.urlencode(q)))
        if galat:
            print("      berhenti: %s" % galat)
            gagal = galat
            break
        if not batch:
            break
        for m in batch:
            t = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            if sampai and t < sampai:
                return pesan
            isi = (m.get("content") or "").strip()
            # Kalau analis memposting lewat bot/webhook, isi sebenarnya ada di
            # embed, bukan di `content` — dan `content`-nya kosong melompong.
            for e in (m.get("embeds") or []):
                bagian = [e.get("title"), e.get("description")]
                for f in (e.get("fields") or []):
                    bagian.append("%s: %s" % (f.get("name"), f.get("value")))
                isi = (isi + " " + " ".join(x for x in bagian if x)).strip()
            # Sebagian analis mengirim kartu posisi sebagai gambar. URL-nya
            # disimpan; tanpa itu satu-satunya bukti hasilnya hilang.
            gambar = [a.get("url") for a in (m.get("attachments") or [])
                      if (a.get("content_type") or "").startswith("image/")][:4]
            if not isi and not gambar:
                continue
            au = m.get("author") or {}
            mid = str(m.get("id") or "")
            pesan.append({
                "waktu": t.isoformat(),
                "penulis": au.get("global_name") or au.get("username") or "?",
                # ID disimpan karena username bisa diganti kapan saja; ID tidak.
                # Penyaring analis WAJIB memakai ini, bukan nama.
                "penulisId": str(au.get("id") or ""),
                "bot": bool(au.get("bot")),
                "teks": isi[:2000],
                "pesanId": mid,
                "kanalId": str(cid),
                "sumber": ("https://discord.com/channels/%s/%s/%s" % (guild, cid, mid)
                           if guild and mid else ""),
                "tautan": RE_URL.findall(isi)[:6],
                # Balasan menautkan kabar hasil ("TP1 kena") ke call aslinya
                # SECARA PASTI. Jauh lebih dipercaya daripada menebak lewat
                # "pesan berikutnya yang menyebut ticker sama".
                "balasKe": str((m.get("message_reference") or {}).get("message_id") or ""),
                "balasTeks": ((m.get("referenced_message") or {}).get("content") or "")[:400],
                "gambar": gambar,
                "avatarHash": au.get("avatar") or "",
            })
        sebelum = batch[-1]["id"]
        if len(batch) < 100:
            break
        time.sleep(0.4)                      # Discord membatasi laju per rute
    return pesan, gagal


def probe(cfg):
    """Buktikan akses DAN intent sebelum menarik apa pun.

    Dipisah dari penarikan penuh karena dua kegagalannya beda sifat: 403 berisik
    dan langsung ketahuan, sedangkan intent mati itu sunyi.
    """
    me, galat = minta("%s/users/@me" % API)
    if galat:
        print("token ditolak: %s" % galat)
        return False
    print("BOT: %s (%s)" % (me.get("username"), me.get("id")))

    g, _ = minta("%s/users/@me/guilds" % API)
    for x in (g or []):
        print("  anggota server: %s %s" % (x["id"], x["name"]))

    sasaran = [(a["nama"], a["kanal"]) for a in cfg["analis"] if a.get("kanal")]
    sasaran += [(k, v["kanal"]) for k, v in cfg.get("segmen", {}).items()]
    ok = True
    for nama, cid in sasaran:
        info, galat = minta("%s/channels/%s" % (API, cid))
        if galat:
            print("  %-8s GAGAL akses  %s" % (nama, galat))
            ok = False
            continue
        msg, galat = minta("%s/channels/%s/messages?limit=20" % (API, cid))
        if galat:
            print("  %-8s channel terlihat tapi pesan ditolak  %s" % (nama, galat))
            ok = False
            continue
        kosong = sum(1 for m in msg if not (m.get("content") or "").strip()
                     and not m.get("embeds") and not m.get("attachments"))
        gejala = ""
        if msg and kosong == len(msg):
            gejala = "  <-- SEMUA ISI KOSONG: MESSAGE CONTENT INTENT kemungkinan MATI"
            ok = False
        print("  %-8s #%-24s contoh=%3d kosong=%d%s"
              % (nama, info.get("name", "?"), len(msg), kosong, gejala))
    return ok


def main():
    cfg = json.loads((HERE / "saluran.json").read_text(encoding="utf-8"))
    if not TOKEN:
        sys.exit("DRU_BOT_TOKEN belum diset. Lihat docstring di atas berkas ini.")
    if "--probe" in sys.argv:
        sys.exit(0 if probe(cfg) else 1)

    hanya = None
    if "--nama" in sys.argv:
        hanya = sys.argv[sys.argv.index("--nama") + 1].lower()

    # Segmen (mis. Invest) ikut ditarik ke berkas yang sama. Isinya bukan call
    # trading, jadi urai_calls.py mengabaikannya - tapi menariknya di sini
    # berarti hanya ada SATU tempat yang menyentuh Discord.
    sasaran = [(a["nama"], a["kanal"], a.get("userId", "")) for a in cfg["analis"]]
    sasaran += [(k, v["kanal"], "") for k, v in cfg.get("segmen", {}).items()]

    keluar = AKAR / "data" / "calls_mentah.json"
    # Dimuat lebih dulu, BUKAN dimulai kosong: dengan --nama, menulis dict
    # kosong yang hanya berisi satu channel akan menghapus semua channel lain
    # dari berkas. Sudah kejadian sekali.
    hasil = json.loads(keluar.read_text(encoding="utf-8")) if keluar.exists() else {}
    for nama, kanal, uid in sasaran:
        if not kanal or (hanya and nama.lower() != hanya):
            continue
        print("  %s ..." % nama, flush=True)
        pesan, gagal = baca_channel(kanal, cfg.get("guild", ""))
        # Penarikan yang GAGAL tidak boleh menimpa apa pun. Menyimpan daftar
        # kosong karena satu 403 sesaat akan menghapus seluruh riwayat channel
        # itu dari berkas - dan jalan berikutnya tidak punya cara tahu bahwa
        # dulu pernah ada isinya.
        if gagal and not pesan:
            print("      dilewati, isi lama dipertahankan (%d pesan)"
                  % len(hasil.get(nama, [])))
            continue
        milik = [p for p in pesan if p["penulisId"] == uid] if uid else pesan
        hasil[nama] = pesan
        print("      %d pesan, %d dari %s sendiri" % (len(pesan), len(milik), nama))

    keluar.write_text(json.dumps(hasil, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> %s" % keluar)


if __name__ == "__main__":
    main()

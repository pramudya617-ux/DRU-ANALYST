# DRU Analyst

Rekam jejak call empat analyst DRU, ditarik dari Discord dan jurnal Excel,
diverifikasi terhadap riwayat harga, disajikan di balik login Discord.

---

## Susunan berkas

```
perbarui.py          satu perintah untuk memperbarui semuanya
jadwal.bat           pembungkus untuk Windows Task Scheduler

pipa/                langkah pipeline, dijalankan berurutan oleh perbarui.py
  saluran.json         guild, channel, dan user ID tiap analyst
  tarik_calls.py       Discord  -> data/calls_mentah.json
  urai_calls.py        regex    -> data/calls.json + data/invest.json
  tarik_harga.py       Yahoo    -> data/harga/<TICKER>.json  (bersinggahan)
  verifikasi_tp.py     telusuri -> data/verifikasi.json
  gabung.py           satukan  -> data/dataset.json + halaman jadi
  cocok_excel.py       pembaca jurnal Excel, dipakai gabung & audit
  ambil_avatar.py      avatar Discord -> data URI (jalankan sekali)
  audit_status.py      uji parser lawan jurnal; jalankan tiap regex diubah

halaman/             sumber HTML yang diedit tangan
  dashboard.html       dashboard; datanya dimuat dari data/dataset.js
  koreksi.html         halaman koreksi manual (LOKAL SAJA, lihat di bawah)

data/                seluruhnya turunan KECUALI koreksi.json
web/                 aplikasi Next.js: gerbang login + penyaji dashboard
DRU-dashboard.html   hasil jadi, satu berkas, bisa diklik ganda
```

Dua hasil jadi dibangun tiap kali `gabung.py` jalan, isinya sama:
`DRU-dashboard.html` di akar (untuk dibagikan sebagai lampiran) dan
`web/dasbor.html` (yang disajikan Railway di balik gerbang).

---

## Memperbarui data

```bash
python perbarui.py              # siklus penuh, ~3 menit
python perbarui.py --cepat      # lewati penarikan harga
python pipa/gabung.py --htmlsaja   # hanya bangun ulang HTML, ~1 detik
```

Butuh `DRU_BOT_TOKEN` di environment. Riwayat harga hanya ditarik ulang kalau
berkasnya lebih tua dari 12 jam, jadi menjalankan ini tiap jam hanya menyentuh
Discord dan beberapa ticker.

Menjadwalkannya di Windows:

```bash
schtasks /create /tn "DRU Dashboard" /tr "C:\DRU\analyst-dashboard\jadwal.bat" /sc hourly /f
```

---

## Halaman koreksi

```bash
python -m http.server 8777
```

Lalu buka `http://localhost:8777/halaman/koreksi.html`.

**Ini bukan pengaman.** Berkas statis tidak bisa memeriksa siapa pun; yang
menjaganya hanya kenyataan bahwa ia tidak ikut di-deploy. Kalau akses koreksi
perlu dibatasi ke orang tertentu, itu butuh gerbang login seperti dashboardnya.

Alurnya: edit → **Unduh koreksi.json** → simpan ke `data/koreksi.json` →
`python perbarui.py`. Koreksi diterapkan **ulang tiap kali** dibangun, karena
Discord dan Excel dibaca ulang terus dan tanpa itu suntinganmu akan tertimpa
sumbernya. Status yang ditulis tangan mengunci barisnya dari verifikasi harga.

---

## Sumber status

`pipa/gabung.py` baris atas:

```python
SUMBER_HASIL = {"Oracle": "klaim"}
SUMBER_BAWAAN = "harga"
```

- `klaim` — catatan analis sendiri. Dipakai Oracle karena channelnya sudah
  berhenti, jadi catatannya tidak akan jadi basi.
- `harga` — telusuri lilin harian; status bergerak sendiri saat harga menyentuh
  TP, tanpa menunggu pengumuman.
- `isi` — klaim menang, harga hanya mengisi yang masih `ongoing`.

---

## Deploy ke Railway

Yang di-deploy hanya `web/`. Pipeline Python tetap jalan di mesin lokal dan
hasilnya (`web/dasbor.html`) ikut ter-commit.

1. Buat repo GitHub **private**, push seluruh folder ini.
2. Railway → New Project → Deploy from GitHub repo.
3. **Settings → Root Directory → `web`.** WAJIB, dan ini yang pertama kali
   menggagalkan deploy: tanpa itu Railpack memeriksa akar repo, hanya menemukan
   folder dan satu skrip Python, lalu berhenti dengan "could not determine how
   to build the app". Railway sendiri menawarkan tombol **Set root directory**
   di layar kegagalannya.

   Port TIDAK boleh dipaku di `npm start`. Railway menyuntikkan $PORT dan
   healthcheck-nya menunggu di situ; `next start -p 3200` akan lolos build
   lalu gagal deploy karena aplikasinya mendengar di port yang salah.
4. Isi variabel berikut di Railway → Variables:

   | Variabel | Dari mana |
   |---|---|
   | `DRU_BOT_TOKEN` | Developer Portal → Bot |
   | `DISCORD_CLIENT_ID` | Developer Portal → OAuth2 |
   | `DISCORD_CLIENT_SECRET` | Developer Portal → OAuth2 → Reset Secret |
   | `DISCORD_GUILD_ID` | `1270940870408929330` |
   | `PREMIUM_ROLE_IDS` | sembilan role yang boleh MEMBACA, dipisah koma |
   | `KOREKSI_ROLE_IDS` | role yang boleh MENGUBAH. Saat ini DRU Official saja |
   | `DATA_DIR` | mount path volume, mis. `/data`. Wajib kalau koreksi lewat web |
   | `APP_URL` | domain Railway, tanpa garis miring di ujung |

5. Developer Portal → OAuth2 → Redirects → tambah
   `https://<domain>/api/auth/discord` → **Save Changes** → refresh halamannya
   untuk memastikan benar-benar tersimpan.
6. Baru push.

Urutannya wajib begitu. Railway tidak punya tahap staging: push = deploy =
langsung kena member. Kalau variabelnya belum ada saat kode tayang, semua orang
melihat "belum dikonfigurasi".

**Uji dengan akun yang TIDAK punya role premium.** Ini yang paling sering
dilewati, dan satu-satunya cara membuktikan gerbangnya benar-benar menutup.

### Memperbarui data setelah tayang

```bash
python perbarui.py
git add web/dasbor.html data/koreksi.json
git commit -m "perbarui data"
git push
```

Railway membangun ulang otomatis. `watchPatterns` di `railway.json` dibatasi ke
`web/**`, jadi commit yang hanya menyentuh skrip Python tidak memicu deploy.

---

## Jebakan yang sudah pernah memakan waktu

- **`--env-file` tidak menimpa variabel yang sudah ada.** Mesin pengembangan
  punya `DISCORD_BOT_TOKEN` berisi token bot DRC; karena itu kode ini membaca
  `DRU_BOT_TOKEN` lebih dulu. Gejalanya menyesatkan: semua member terbaca
  "bukan anggota server".
- **SERVER MEMBERS INTENT tidak diperlukan** untuk membaca satu member.
  Yang wajib menyala adalah **MESSAGE CONTENT INTENT**, dan tanpa itu pesan
  pulang dalam keadaan kosong — gagal yang sunyi.
- **Role baca dan role tulis dipisah.** Sembilan role boleh membaca dashboard;
  hanya `DRU Official` boleh mengubah angka. Kalau `KOREKSI_ROLE_IDS` kosong,
  tidak ada yang bisa mengedit - gagal ke arah tertutup. `Co-owner` sengaja
  belum didaftarkan di mana pun, karena menambah role berarti membuka akses
  dan itu keputusan pemilik server.
- **Koreksi lewat web butuh volume.** Tanpa `DATA_DIR` menunjuk ke volume yang
  di-mount, koreksi yang ditulis hari ini lenyap pada push berikutnya: filesystem
  container dibangun ulang tiap deploy. Volume adalah SATU-SATUNYA kebenaran
  begitu berkasnya ada; salinan repo hanya jadi benih pada pembacaan pertama.
- **Harga Yahoo sudah disesuaikan split**, entry analis belum. Dikoreksi
  per-call dengan batas kewarasan; di luar rentang itu call-nya tidak dinilai.
- **Jangan menaruh dashboard di `web/public/`.** Berkas di sana dilayani
  sebelum kode mana pun jalan, jadi siapa pun bisa mengunduhnya tanpa menyentuh
  gerbang.

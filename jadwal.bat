@echo off
REM Pembungkus untuk Windows Task Scheduler.
REM
REM Penjadwal menjalankan tugas dengan environment yang BERSIH - variabel yang
REM diset lewat setx memang ikut, tetapi direktori kerjanya tidak. Karena itu
REM skripnya dipanggil dengan path penuh dan cd dilakukan eksplisit.
REM
REM Keluarannya ditimpa tiap jalan, bukan ditambahkan: yang dibutuhkan saat
REM memeriksa adalah hasil jalan TERAKHIR, dan berkas log yang tumbuh selamanya
REM adalah masalah yang muncul berbulan-bulan kemudian.

cd /d "%~dp0"
python "%~dp0perbarui.py" %* > "%~dp0data\jadwal.log" 2>&1
exit /b %ERRORLEVEL%

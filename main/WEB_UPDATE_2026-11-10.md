# Baterai hardware dan form Patrol langsung — 10 November 2026

Dashboard produksi: **http://192.168.0.141:3000**. Muat ulang dengan
**Ctrl+F5** setelah pergantian build.

## Perilaku baru

- Baris baterai Husky dan Devi tersedia pada semua halaman. System Overview
  dan ringkasan robot juga menampilkan persentase serta voltase.
- **New Task** langsung membuka **Patrol**: pilih satu atau beberapa waypoint
  sesuai urutan kunjungan, pilih jumlah putaran, lalu kirim.
- **Otomatis · bidding RMF** memakai `POST /tasks/dispatch_task`, dengan
  `type: dispatch_task_request`, tanpa memaksakan robot/fleet tertentu.
- Pilihan **Devi/devi** atau **HuskyA200/husky_0** memakai
  `POST /tasks/robot_task`, `type: robot_task_request`, dengan pasangan fleet
  dan robot yang dipilih. Tidak ada fallback diam-diam ke robot lain.
- Robot dengan telemetry lebih tua dari 15 detik atau status tidak siap
  dinonaktifkan pada pilihan manual. Tombol kirim menunggu waypoint, robot
  terhubung, dan putaran valid. Error/penolakan RMF tetap terlihat.
- **Opsi lanjutan** mempertahankan form sebelumnya untuk jenis task,
  favorit, impor dan penjadwalan yang sudah tersedia.

## Sumber baterai

| Robot | Sumber asli | Data yang dipakai |
| --- | --- | --- |
| Husky | `/a200_1060/platform/bms/state`, `sensor_msgs/msg/BatteryState`, Fast DDS domain 0 | `percentage` dalam 0–1 dan `voltage`; pesan harus `present` |
| Devi | `/devi/roboteq/battery/measured`, `std_msgs/msg/Float32`, Fast DDS domain 73 | Tegangan `data`; SOC estimasi linear dengan 15 V = 0% dan 25 V = 100% |

Kalibrasi Devi berasal dari operator. Rumus:
`SOC = clamp((V - 15) / (25 - 15), 0, 1)`. Tegangan asli tidak dibatasi;
misalnya 25,7 V tetap ditampilkan 25,70 V dengan estimasi 100%.
Kalibrasi dapat ditentukan lewat `battery_empty_voltage` dan
`battery_full_voltage` pada integration config. Default juga berlaku untuk
runtime config lama, sehingga konfigurasi startup robot tidak ditimpa.

Husky memakai pembaca sensor Fast DDS terpisah dari adapter Cyclone DDS;
TF bridge yang sudah berjalan tidak dimulai ulang. Devi memakai gateway
Nav2 yang sudah ada; laporan baterai tidak memengaruhi hasil preflight Nav2.
Adapter mengirim SOC valid ke native RMF dan telemetry tambahan pada
`/brin/battery_states` (`std_msgs/String`, JSON, domain 0).

Layanan dashboard menjalankan subscriber read-only dan menyediakan
`GET /brin/batteries` pada port 3000. Cache dilindungi lock; payload tidak
valid ditolak. Kesegaran memakai waktu penerimaan sensor, sebab header BMS
Husky yang teramati memiliki timestamp nol. Data berumur lebih dari
10 detik dikosongkan dan ditandai kedaluwarsa, termasuk ketika publisher
berhenti. Nilai 0% valid; nilai NaN, SOC di luar 0–1, dan baterai yang belum
terbaca tidak ditampilkan sebagai 95%/0% buatan.

Sensor asli dan SOC di `/fleets` terverifikasi setelah aktivasi. Contoh
pengamatan: Husky SOC 0,15175 pada 23,78 V; Devi SOC 1 pada 25,70 V.
SOC Husky berikutnya teramati sekitar 13–15%. Ambang planner lama 20%
tetap berlaku, sehingga task Husky dapat ditolak saat baterainya rendah,
termasuk permintaan manual. `account_for_battery_drain: false` tidak
menghapus pemeriksaan ambang SOC pada model GoToPlace Humble.

Rujukan protokol: [Battery Clearpath](https://docs.clearpathrobotics.com/docs/ros/config/yaml/platform/battery/),
[schema permintaan robot RMF](https://github.com/open-rmf/rmf_api_msgs/blob/main/rmf_api_msgs/schemas/robot_task_request.json).
Tipe pesan dan field di atas diperiksa lagi pada runtime Humble terpasang.

## Source dan build yang dapat diulang

Perubahan UI disimpan pada `main/web/overlay`, dan diterapkan oleh
`main/web/prepare_dashboard.py` ke direktori source hasil generate.
Checkout `rmf-web` tetap pada revision
`e2861c292bb27014435452e74faa825ecb0e8d91` tanpa diedit. Patch menolak
revision/konteks yang tidak cocok dan hanya mengganti direktori dengan
marker `.brin-generated`. Dependency dan versi Node memakai instalasi Web
yang sudah diaudit. Cache build berada di direktori hasil generate.

Pada komputer utama:

```bash
cd /home/rslab/rmf-integration
bash main/web/build-dashboard.bash
systemctl --user restart brin-rmf-dashboard.service
```

Build disimpan pada `main/log/web/dashboard`; build lama dibackup.
Jangan menyalin build/install ROS antar komputer. Perubahan Python adapter
harus dibangun pada overlay masing-masing robot, lalu adapter diaktifkan
saat robot idle. Snapshot laptop/Husky memiliki implementasi yang sama;
simulasi tetap menggunakan SOC konfigurasinya sendiri.

## Deployment dan verifikasi

Source terpasang dibandingkan dengan snapshot sebelum patch. Guard hash
menolak file yang berubah sejak audit. Hanya file software yang diperlukan
diganti; konfigurasi Nav2, sensor, TF, domain, safety dan peta tidak diubah
oleh update Web/baterai ini.

Sebelum restart, tiga pengamatan telemetry Web yang segar menunjukkan
`idle`, task ID kosong dan timestamp bertambah; audit action Nav2 tidak
menemukan goal aktif. Hanya adapter RMF dimulai ulang:

- Husky: PID 6626 → 18624; reader baterai baru PID 18647. TF bridge dan
  reader IMU/odom lama tetap berjalan. Perintah adapter dan environment
  persis seperti sebelumnya, dengan log baru di direktori aktivasi.
- Devi: PID 4176 → 5371 melalui supervisor yang sudah berjalan. Supervisor,
  bringup, initial-pose bridge, visualization bridge dan Nav2 dipertahankan.
- Komputer utama: hanya layanan dashboard dimulai ulang untuk memuat build
  dan subscriber baterai. Core dan API tetap berjalan.

Backup source:

```text
/home/husky/rmf-integration/husky/log/web-battery-20261110T082200Z
/home/devi/rmf-integration/devi/log/web-battery-20261110T082159Z
/home/rslab/rmf-integration/main/log/web-battery-20261110T082643Z
```

| Pemeriksaan | Hasil |
| --- | --- |
| Build overlay Husky | 4 paket berhasil |
| Build overlay Devi | 1 paket berhasil |
| Regresi pada robot Devi | 102 lulus |
| Regresi paket fisik Husky | 94 lulus |
| Perhitungan baterai, HTTP cache, deployment dan regresi waypoint offline | 53 lulus |
| Payload Patrol otomatis/manual kedua robot serta penolakan API | Lulus |
| Build dashboard produksi | Berhasil; satu warning fungsi ikon baterai lama tidak terpakai |
| Browser Chrome | Baterai nyata tampil; form Patrol langsung; otomatis, Devi, Husky menghasilkan tiga payload benar; tidak ada page error |
| Endpoint `/fleets` dan `/brin/batteries` | SOC/voltase nyata, data segar; kedua robot idle |
| Core dan seluruh layanan utama | Aktif; tepat satu dari setiap node core, digest cocok |

Semua POST task pada uji browser dicegat dan diberi respons uji. **Tidak ada
task/goal gerak fisik dikirim oleh pengujian ini.** Ini memverifikasi alur
UI/payload dan telemetry live, bukan penyelesaian Patrol fisik.

Pemeriksaan luas juga mencatat batas environment yang sudah ada:

- Laptop: 148 lulus, dua tes preset RViz lama gagal sesuai catatan
  [hasil build sebelumnya](BUILD_TEST_RESULT_2026-11-09.md).
- Suite campuran di Husky: 101 lulus, enam tes simulasi gagal karena paket
  `brin_husky_nav2`/`brin_husky_bringup` simulasi tidak terpasang pada robot.
  Suite khusus paket fisik di atas lulus.
- `tsc` tanpa penyaringan test lama menemukan empat error fixture upstream;
  build produksi tidak melaporkan error TypeScript pada implementasi baru.
- Percobaan suite Devi pada laptop tidak memiliki ament package Devi dan
  lokasi log default writable. Verifikasi lengkap dilakukan di Devi, sesuai
  underlay dan overlay robot; hasil 102 lulus di atas adalah hasil robot.

Artefak lokal yang diabaikan Git: `main/log/web/verification/` berisi
screenshot dashboard/form dan `browser-result.json`. Log audit, validasi
dan aktivasi berada pada `/tmp/rmf-web-update-20261110/` dan backup robot.
Untuk rollback, pulihkan file dari backup, bangun kembali overlay terkait,
dan restart hanya adapter idle; dashboard dapat dipulihkan dari direktori
`dashboard.backup-*` lalu layanan dashboard dimulai ulang.

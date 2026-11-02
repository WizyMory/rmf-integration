# Footprint dan inflation untuk uji — 2 November 2026

Nilai akhir yang diminta operator:

| Pengaturan | Nilai |
| --- | --- |
| Radius footprint Open-RMF | 0.55 m |
| Polygon Nav2 | x=±0.45 m, y=±0.30 m (0.90 × 0.60 m) |
| Inflation radius local/global | 0.35 m |
| Footprint padding | Tetap 0.02 m |
| Vicinity RMF | Tetap 0.80 m |

Perubahan diterapkan pada 24 YAML source di kedua perangkat: snapshot
`laptop/src` dan `husky/src` pada masing-masing clone `rmf-integration`,
serta workspace aktif `/mnt/UbuntuData/rmf_ws` dan `/home/husky/rmf_ws`.
Setiap workspace menerima perubahan pada konfigurasi Nav2 yang tersedia,
fleet distributed, fleet alternatif/simulasi, dan fleet khusus `gedungWS_0`.
Koordinat polygon mempertahankan urutan vertex setiap konfigurasi.

File Nav2 fisik yang dipakai tetap
`/home/husky/rmf_ws/src/husky_nav2/config/nav2_params.yaml`.
Nav2 simulasi memakai `brin_husky_nav2/config/nav2.yaml` pada overlay yang
dipilih. Sensor, TF, batas kecepatan/percepatan dan mekanisme collision
checking dipertahankan. Waktu simulasi laptop dan waktu nyata Husky tetap
sesuai konfigurasi masing-masing.

Patch dilakukan pada scalar YAML terpilih, dengan backup, pemeriksaan hash
sebelum penerapan dan perbandingan struktur YAML untuk memastikan field
lain tetap sama. Tes marker RMF diperbarui ke radius 0.55. Komentar kebijakan
occupancy kini merujuk dimensi dari Nav2, tanpa menduplikasi ukuran robot.

Generator `gedungWS_0` dijalankan kembali dengan footprint baru. Graph, map
dan gambar occupancy tetap sama; laporan sapuan berubah menjadi
0.94 × 0.64 m termasuk padding, dengan nol lane terhalang dan nol pixel
occupancy diubah. Ukuran lingkaran RMF dan polygon Nav2 merupakan model
berbeda; nilai uji ini mengikuti permintaan operator, belum diverifikasi
terhadap pengukuran dimensi fisik robot.

Build dan verifikasi:

| Workspace | Paket dibuild | Hasil colcon test-result |
| --- | --- | --- |
| Laptop integrasi | brin_husky_nav2, brin_rmf_maps, brin_husky_fleet_adapter, brin_husky_distributed | 8, 23, 42, 34; nol error/failure |
| Laptop rmf_ws | Paket yang sama | 8, 22, 41, 4; nol error/failure |
| Husky integrasi | brin_rmf_maps, brin_husky_fleet_adapter, brin_husky_distributed | Maps 23, distributed 34; nol error/failure |
| Husky rmf_ws | Tiga paket tersebut dan husky_nav2 | Maps 22, distributed 4; nol error/failure; husky_nav2 tidak mendaftarkan tes pada build ini |

Tes langsung pada snapshot laptop juga lulus 106 kasus. Audit setelah build
memverifikasi 12 YAML source dan 8 YAML terpasang di laptop, serta 12 source
dan 7 terpasang di Husky. Nilai target sesuai, instalasi cocok dengan source,
dan snapshot kedua clone memiliki hash yang sama.

Profil `gedungWS_0` pada empat instalasi maps memiliki digest yang sama:
`ff44d7a33b01732e6c277b523c40ae5c7ef6c011dab83b259e5db44daef9f221`.

Tidak ada goal atau task dikirim. Nav2 dan adapter fisik tidak aktif saat
pemeriksaan awal; proses navigasi tidak dimulai oleh deployment ini.
Nilai baru dimuat pada launch berikutnya. Untuk uji berikutnya, jalankan
ulang core/RViz laptop, Nav2, lalu preflight dan adapter Husky sesuai README,
semuanya dengan profil `gedungWS_0`. Uji gerak fisik belum dilakukan.

Log, rencana perubahan, audit dan backup disimpan pada
`laptop/log/validation/footprint_20261102/` dan
`husky/log/validation/footprint_20261102/` di clone masing-masing perangkat.

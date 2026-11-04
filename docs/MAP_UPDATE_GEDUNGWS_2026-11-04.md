# Pembaruan graph gedungWS_0 — 4 November 2026

Edit operator pada `laptop/src/brin_rmf_maps/maps/gedungWS_0.building.yaml`
menjadi sumber pembaruan. SHA-256 sumber:
`8c51b1f675f2b7a2f34784e5e5d6d8d3368f617927a59a2188d0f80aa90d0357`.

Generator Humble `generate_gedungws.py` dijalankan dalam staging dan
menghasilkan ulang building metric `L1`, graph dan laporan sapuan. Graph
tetap berisi 19 vertex, 38 lane berarah, dan delapan waypoint bernama.
Semua endpoint lane dibandingkan terhadap koordinat edit sumber, termasuk
waypoint tanpa nama; semua waypoint saling terhubung. Pengurutan indeks
vertex berubah setelah pengurutan lane sumber berubah, sehingga seluruh
graph dipasang sebagai satu bundle.

Hanya empat file map berubah pada package `brin_rmf_maps`: source building,
building RMF turunan, graph, dan `gedungWS_0_report.json`. Overlay Devi
menerima dua perubahan dari bundle canonical: building RMF turunan dan
graph. Lima aset yang menentukan digest tetap disamakan dengan laptop,
termasuk file fleet canonical Husky; konfigurasi fleet operasional Devi
tetap terpisah dan tidak ditimpa.

Gambar PNG/PGM, YAML SLAM asli, YAML Nav2 RMF, fleet khusus profil, resolusi
`0.05 m/pixel` dan origin `[0, -33.65, 0]` tidak berubah. Sensor, TF, jaringan,
batas kecepatan, footprint, inflation, konfigurasi startup dan auto initial
pose tidak diubah. Domain Nav2 Devi tetap 73 dan native RMF tetap 0.

Sapuan polygon Husky `0.94 × 0.64 m` termasuk padding tidak menemukan lane
terhalang. Pemeriksaan tambahan konservatif untuk Devi memakai lingkaran
radius `0.56 m` (radius runtime 0.55 m ditambah padding 0.01 m dan raster
quantization). Semua lane yang berubah lolos. Satu segmen lama yang tidak
berubah, vertex sumber 115–116 (lane 0 baru, lane 1 lama), mencakup lima sel
non-free pada sapuan lingkaran tersebut. Temuan ini sudah ada pada graph
lama; tidak ada occupancy atau parameter keselamatan yang diubah untuk
menutupinya. Pemeriksaan statik ini tidak merupakan uji gerak.

| Perangkat / workspace | Build | Tes offline |
| --- | --- | --- |
| Laptop `/mnt/UbuntuData/rmf-integration/laptop` | Empat package integrasi berhasil | Maps + distributed: 99 lulus |
| Laptop `/mnt/UbuntuData/rmf_ws` | `brin_rmf_maps` berhasil | Checksum instalasi cocok |
| Husky `/home/husky/rmf-integration/husky` | Empat package integrasi berhasil | Maps + distributed: 56 lulus |
| Husky `/home/husky/rmf_ws` | `brin_rmf_maps` berhasil | Checksum instalasi cocok |
| Devi `/home/devi/rmf-integration/devi` | `brin_devi_fleet_adapter` berhasil | Seluruh tes package: 95 lulus |

Pengujian awal gabungan di laptop menemui pemilihan overlay lama dan
ketiadaan instalasi package Devi pada laptop. Tes diulang dengan path
source laptop eksplisit; tes Devi dijalankan pada instalasi Devi sendiri.
Hasil di tabel adalah hasil akhir tanpa error. Tidak ada kode produksi atau
test yang diubah untuk meloloskan pemeriksaan.

Checksum sembilan aset terpasang diperiksa pada empat instalasi maps;
lima aset canonical diperiksa pada instalasi Devi. Executable `profile`
masing-masing perangkat juga menghasilkan digest yang sama:

```text
a5c392a4a4446542b69b08d0bb44d8824e8ee081c955f7bc1cee3b795e4294be
```

Snapshot laptop/husky pada clone robot disamakan untuk bundle ini.
Edit kode lokal yang sudah ada di Devi dipertahankan; tidak ada git pull,
reset, commit, atau push yang dilakukan. Verifier underlay Devi tetap
menunjukkan sepuluh file asli tidak berubah.

Saat deployment, core RMF laptop dan Nav2/adapter Husky tidak aktif.
Service `devi_robot.service` tetap aktif dengan MainPID 3224 sepanjang
pembaruan; tidak direstart. Log preflight service pada 13:44 WIB sudah
memuat digest baru dan `nav2_ready: true`, dengan `received_profile_digest:
null` karena core laptop belum aktif. Occupancy Nav2 tidak perlu dimuat
ulang. Core dan adapter yang dimulai berikutnya membaca graph baru.
Tidak ada goal/task atau perintah gerak yang dikirim.

Untuk memakai graph baru, mulai core yang sudah ada di panduan operator:

```bash
bash tools/integration.bash laptop core traffic_profile:=gedungWS_0 rviz:=true
```

Devi melanjutkan loop readiness yang sudah berjalan. Startup/preflight
Husky tetap mengikuti panduan operasionalnya.

Backup, manifest dengan hash sebelum/sesudah, verifikasi instalasi, hasil
tes dan laporan validasi disimpan pada direktori masing-masing clone:

- Laptop: `laptop/log/validation/map_update_gedungws_20261104_WSPVaL/`.
- Husky: `husky/log/validation/map_update_gedungws_20261104_WSPVaL/`.
- Devi: `devi/log/validation/map_update_gedungws_20261104_WSPVaL/`.

Subdirektori `backup/` mempertahankan file sebelumnya per path absolut.
Penulisan menggunakan hash guard dan penggantian atomik. Staging awal ada
di `/tmp/gedungws-update-20261104-WSPVaL/` pada ketiga komputer.

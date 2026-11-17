# Footprint Husky — 17 November 2026

Permintaan operator diterapkan pada konfigurasi fisik Husky:

| Pengaturan | Nilai |
| --- | --- |
| Radius footprint Open-RMF HuskyA200 | 0.65 m |
| Footprint Nav2 local dan global | x=±0.55 m, y=±0.40 m (1.10 × 0.80 m) |
| Footprint padding | Tetap 0.02 m |
| Inflation radius local dan global | Tetap 0.35 m |
| Vicinity RMF | Tetap 0.80 m |

File Nav2 aktif `/home/husky/rmf_ws/src/husky_nav2/config/nav2_params.yaml`
dan snapshot `husky/src/husky_nav2/config/nav2_params.yaml` diperbarui.
Konfigurasi fleet distributed fisik dan fleet khusus `gedungWS_0` disamakan
pada laptop, Husky dan komputer-utama. Salinan pada workspace lama Husky juga
menerima perubahan. Polygon dan parameter Nav2 simulasi laptop tidak diubah;
konfigurasi footprint fisik Devi tetap 0.55 m.

Paket Devi menyimpan salinan fleet Husky dalam bundle map yang di-hash untuk
preflight. Salinan repository `devi/src/brin_devi_fleet_adapter/maps/gedungWS_0_fleet.yaml`
sudah diperbarui. Deployment ke perangkat Devi belum dilakukan karena SSH
`192.168.0.237` melaporkan `No route to host`. Setelah Devi kembali terhubung,
salin bundle ini dan build paket integrasinya sebelum menjalankan preflight;
digest lama tidak cocok dengan digest baru core. Underlay dan domain 73 Devi
tidak diubah.

Patch mengganti scalar YAML terpilih dengan backup, perbandingan hash sebelum
apply, dan pemeriksaan struktur YAML agar field lain tetap sama. Sapuan
footprint termasuk padding pada map `gedungWS_0` adalah 1.14 × 0.84 m; tidak
ada lane terhalang pada pemeriksaan occupancy asli. Report diperbarui, tanpa
mengubah graph, koordinat, initial pose, occupancy, BT atau parameter sensor.

Build laptop: brin_rmf_maps dan brin_husky_distributed. Build overlay Husky:
paket yang sama; workspace lama Husky juga membangun husky_nav2. Build main:
brin_rmf_maps dan brin_husky_distributed dari source yang dipilih helper main.
Tes maps, distributed dan autostart lokal lulus 74 kasus.

Operator menyetujui restart core komputer-utama dan auto bringup Husky.
Service Husky dihentikan bersih, konfigurasi runtime dihasilkan dan diperiksa,
core direstart untuk memuat digest/marker baru, lalu auto bringup Husky dimulai.
Initial pose parkir diterapkan ulang sesuai persetujuan operator. Parameter
live kedua costmap diperiksa melalui ROS GetParameters dan cocok dengan nilai
di tabel. File `fleet_startup.yaml` memuat radius 0.65, dan digest publisher
core sama dengan digest runtime Husky:

`122947376616a242d3310ed73cc490cd850771000756527eb96f3c646c4aa235`

Preflight lulus `errors: []`, `accepted: true`; Husky terdaftar kembali di
schedule dan Web komputer-utama. Telemetri segar menunjukkan idle tanpa task.
Tidak ada goal/task atau uji gerak yang dikirim oleh deployment ini.

Nav2 memunculkan peringatan bahwa inflation radius 0.35 m lebih kecil dari
inscribed radius footprint termasuk padding, yaitu 0.42 m. Nilai inflation
tersebut dipertahankan sesuai instruksi terakhir; peringatan ini belum
diselesaikan oleh perubahan footprint. Kelulusan preflight tidak memvalidasi
kesesuaian inflation radius terhadap inscribed radius.

Log, plan, backup dan bukti parameter live:
`husky/log/validation/footprint_20261117/` pada clone laptop dan Husky;
`main/log/validation/footprint_20261117/` pada komputer-utama.

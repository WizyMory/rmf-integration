# Deployment RViz RMF — 28 Oktober 2026

RViz dan tiga visualizer dapat dibuka dari satu perintah laptop:

```bash
cd /mnt/UbuntuData/rmf-integration
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan rviz:=true
```

Perintah core lama tetap tanpa GUI. Jika core sudah aktif, gunakan launch
`visualization.launch.py` sesuai README paket; jangan membuat core kedua.
Graph memerlukan `/nav_graphs` dari adapter; posisi fleet memerlukan robot
terdaftar di `/fleet_states`. Seluruh visualizer memakai waktu nyata dan
RViz membaca TF Nav2 yang sama dengan RViz Husky sebelumnya.

## Lokasi dan verifikasi

| Pemeriksaan | Laptop | Husky |
| --- | --- | --- |
| Workspace | `/mnt/UbuntuData/rmf-integration/laptop` | `/home/husky/rmf-integration/husky` |
| Build lokal pada mesin target | 4 paket berhasil | 4 paket berhasil |
| Tes paket dan guard helper | 56 lulus | 56 lulus |
| Aset RViz terpasang dan opsi launch | Diperiksa | Diperiksa |

Deployment source dilakukan untuk 15 berkas yang dibatasi manifest,
termasuk helper environment dan paket `brin_husky_distributed` pada kedua
snapshot. Checksum diperiksa sesudah transfer dan build. Ini deployment
per berkas, bukan push GitHub atau penyamaan seluruh checkout. Perubahan
lokal robot dipertahankan: 35 berkas memiliki checksum yang sama sebelum
dan sesudah deployment. Konfigurasi dan overlay graph khusus `husky_nav2`
yang sudah ada di robot tidak diganti oleh snapshot laptop.

Helper diperbaiki agar overlay repository tetap memiliki prioritas ketika
terminal sudah mewarisi workspace ROS lama. Perubahan environment hanya
berlaku pada proses helper dan anaknya; shell startup/service tidak diubah.
Visualisasi berjalan di laptop; proses adapter/Nav2 Husky tetap terpisah.
Paket visualizer ditemukan pada underlay RMF laptop. Paket tersebut tidak
dipasang pada Husky karena tidak dijalankan dalam peran robot.

Backup source Husky sebelum deployment:
`/home/husky/rmf-integration/husky/log/rviz-backup-20261028-095549/sources.tar.gz`.
Manifest akhir dan checksum berkas lokal robot disimpan pada direktori
backup yang sama. Salinan checksum payload tersedia pada
`husky/log/deploy-rviz-20261028/SHA256SUMS` di robot.

## Batas hasil

Verifikasi deployment tidak menjalankan Nav2, sensor, bridge, adapter,
task, goal, atau RViz GUI. Tidak ada uji robot bergerak atau pengamatan
marker dengan data fisik langsung pada sesi ini. Build, tes wiring launch,
QoS preset, executable visualizer laptop, dan aset terpasang telah diperiksa.

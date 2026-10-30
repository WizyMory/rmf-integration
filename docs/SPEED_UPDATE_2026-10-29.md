# Kecepatan 0.5 m/s dan 0.5 rad/s — 29 Oktober 2026

Pengguna meminta kecepatan linear dan angular pada masing-masing perangkat
menjadi 0.5 m/s dan 0.5 rad/s. Konfigurasi simulasi laptop dan konfigurasi
robot fisik ditinjau terpisah sebelum penulisan.

## Perubahan

| Parameter | Laptop/simulasi | Husky/fisik |
| --- | --- | --- |
| `FollowPath.desired_linear_vel` | 0.4 → 0.5 m/s | 0.20 → 0.5 m/s |
| `FollowPath.rotate_to_heading_angular_vel` | tetap 0.5 rad/s | 0.35 → 0.5 rad/s |
| `velocity_smoother.max_velocity` | `[0.5, 0.0, 0.5]` | `[0.5, 0.0, 0.5]` |
| `velocity_smoother.min_velocity[2]` | tetap −0.5 rad/s | −0.35 → −0.5 rad/s |
| `behavior_server.max_rotational_vel` | tetap 0.5 rad/s | 0.35 → 0.5 rad/s |
| Fleet RMF `limits.linear[0]` | 0.5 m/s | 0.5 m/s |
| Fleet RMF `limits.angular[0]` | 0.5 rad/s | 0.5 rad/s |

Nilai percepatan, perlambatan, kecepatan mundur linear, kecepatan recovery
BackUp, collision detection, footprint, costmap, lidar, TF dan penggunaan
waktu masing-masing sistem dipertahankan. Nilai kedua pada array limits
RMF adalah percepatan dan tidak diubah. Angular ±0.5 pada smoother membatasi
kedua arah putaran; batas maju linear adalah 0.5, sementara batas mundur
tetap −0.2 pada simulasi dan −0.10 pada robot fisik.

Pengaturan `rotate_to_heading_angular_vel` adalah kecepatan putar orientasi,
bukan kecepatan tetap pada setiap tikungan. Target kecepatan dan batas
smoother tidak menjamin robot selalu bergerak 0.5: controller tetap dapat
memperlambat sesuai lintasan, obstacle dan pendekatan goal.

Pemeriksaan baca-saja pada konfigurasi controller platform Husky menemukan
batas linear dan angular 1.0. Tidak perlu mengubah konfigurasi platform
untuk target Nav2 0.5; tidak ada service platform yang direstart.

## File dan deployment

Pada kedua clone repository:

- `laptop/src/brin_husky_nav2/config/nav2.yaml`.
- `husky/src/husky_nav2/config/nav2_params.yaml`.
- `laptop/src/brin_husky_distributed/config/fleet_config.yaml`.
- `husky/src/brin_husky_distributed/config/fleet_config.yaml`.
- `laptop/src/brin_husky_fleet_adapter/config/fleet_config.yaml`.
- `husky/src/brin_husky_fleet_adapter/config/fleet_config.yaml`.

Workspace lama laptop `/mnt/UbuntuData/rmf_ws/src/` menerima pembaruan pada
`brin_husky_nav2/config/nav2.yaml` dan kedua konfigurasi fleet tersebut.
Workspace lama Husky `/home/husky/rmf_ws/src/` menerima pembaruan pada
`husky_nav2/config/nav2_params.yaml` dan kedua konfigurasi fleet tersebut.
Konfigurasi fleet tujuh robot tetap menjadi konfigurasi alternatif/simulasi;
fleet distributed fisik tetap berisi hanya `husky_0`.

Sembilan file YAML pada masing-masing perangkat dipatch hanya pada scalar
kecepatan yang diizinkan, tanpa serialisasi ulang seluruh YAML. Pemeriksaan
struktur YAML memastikan tidak ada field lain yang berubah. SHA-256 sebelum
apply dibandingkan dengan rencana perubahan untuk mendeteksi edit bersamaan,
dan seluruh file asli dibackup. Tes simulasi yang sudah ada diperbarui untuk
mengharapkan `desired_linear_vel == 0.5` pada tujuh namespace.

## Build dan validasi

| Workspace | Paket yang dibuild | Tes yang dijalankan | Hasil |
| --- | --- | --- | --- |
| Laptop integrasi | Nav2 simulasi, fleet adapter, distributed | Ketiga paket | 82 lulus |
| Laptop `rmf_ws` | Nav2 simulasi, fleet adapter, distributed | Ketiga paket | 53 lulus |
| Husky integrasi | Fleet adapter, distributed | Distributed | 32 lulus |
| Husky `rmf_ws` | Fleet adapter, distributed | Distributed | 4 lulus |

Semua build dan `colcon test-result` terkait berhasil, nol error/failure/skip.
Suite simulasi fleet tidak dijalankan pada robot fisik. Tidak ada tes gerak.
Konfigurasi Nav2 fisik yang terpasang merupakan symlink ke source runtime;
nilai baru sudah diverifikasi tanpa membuild ulang driver atau Nav2 fisik.

Verifikasi akhir memeriksa sembilan YAML source pada setiap perangkat,
enam konfigurasi terpasang pada laptop dan lima pada Husky. Semua field
kecepatan sesuai dan hash instalasi cocok dengan source masing-masing.

Tidak ada Nav2 atau fleet adapter aktif di Husky saat pemeriksaan sebelum
deployment. Tidak ada goal dikirim, robot tidak digerakkan, dan runtime
tidak diaktifkan/direstart oleh pembaruan. Konfigurasi baru digunakan saat
Nav2 dan adapter diluncurkan berikutnya. Uji kecepatan fisik belum dilakukan.

## Bukti dan backup

- Laptop: `laptop/log/validation/speed_050_20261029/`.
- Husky: `husky/log/validation/speed_050_20261029/`.

Direktori ini berisi rencana field/hash sebelum-sesudah, script apply,
backup per file, log build/test dan hasil verifikasi konfigurasi terpasang.
Staging awal: `/tmp/brin-speed-050-20261029-f6is6r7q/` di kedua perangkat.

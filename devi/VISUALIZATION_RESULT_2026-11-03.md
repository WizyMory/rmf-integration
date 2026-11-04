# Visualisasi Devi dan Husky — 3 November 2026

## Masalah dan perubahan

Preset sebelumnya hanya membawa map/initial pose Devi; laser, costmap,
model dan TF masih berada di domain 73. RViz memakai TF Husky saja.
Selain itu, supervisor mengirim argumen launch kosong `server_uri:=`;
ROS 2 Humble menolaknya sebelum adapter dapat dimulai.

Perubahan:

- Relay `devi_visualization_bridge` hanya membaca telemetry domain 73/Fast DDS
  dan meneruskannya ke `/devi/viz/*` pada domain 0/Cyclone DDS.
- Stream mencakup laser raw/filtered, costmap penuh, footprint, AMCL pose/
  covariance/particles, odometri, model robot dan plan Nav2.
- Salinan frame visualisasi mendapat awalan `devi/`, kecuali frame bersama
  `map`. Angka transform, koordinat, timestamp dan isi sensor tidak diganti.
- Node laptop `rmf_visualization_tf` menggabungkan TF pengamatan Husky dan
  Devi pada `/rmf_visualization/tf*`. Hanya RViz memakai keluaran ini.
- Preset Humble memakai grup `rviz_common/Group` untuk kedua robot dan
  mempertahankan display fleet/traffic/waypoint bersama.
- Supervisor menghilangkan `server_uri` dari CLI jika nilainya kosong.
  Preflight dan commissioning tetap berlaku. Lock mencegah supervisor ganda.
- Helper `laptop view` memulai RViz saja dengan core/visualizer/TF versi baru
  yang sudah berjalan. Bringup Devi memulai relay otomatis pada start berikutnya.

Perubahan tidak mengubah underlay, TF controller, domain Nav2, sensor,
kecepatan, hardware, safety, atau profil jaringan DDS. Komunikasi domain 0
sudah teramati bekerja pada sesi ini; usulan perubahan peer sebelumnya tidak
diterapkan dalam pekerjaan visualisasi.

## Pengujian

- **174 tes lokal lulus**: Devi + paket distributed laptop + helper.
- **72 tes Devi lulus di robot**.
- Setelah penyesuaian grup/plugin dan helper view terakhir, **102 tes
  laptop/helper lulus**.
- Build paket distributed laptop dan paket Devi berhasil.
- Manifest 8 file overlay diverifikasi sebelum build di robot.
- Verifier sebelum/sesudah pemasangan: **10 file underlay asli utuh**.
- Backup robot: `devi/log/visualization_backup_20261103_134642/before_update.tar.gz`.
- Manifest: `devi/log/visualization_update_manifest.json`.

## Uji stream nyata tanpa gerak

Relay sementara dijalankan di Devi untuk menerima data nyata, tanpa restart
Nav2 dan tanpa mengubah initial pose yang sudah diberikan operator.
Pengamatan selama 15 detik dari laptop memperoleh:

| Data | Hasil |
| --- | --- |
| Laser filtered | 144 pesan, 720 titik, frame `devi/rplidar_link` |
| Global costmap | 10 pesan, 755×673, frame `map`, origin `[0, -33.65]` |
| Local costmap | 26 pesan, 80×80, frame `devi/odom` |
| Odometri | 147 pesan, frame `devi/odom` |
| Footprint lokal | 75 pesan, frame `devi/odom` |
| AMCL pose | Pesan latched, frame `map` |
| Model robot | URDF 3182 byte, tanpa resource mesh eksternal |

Lookup TF melalui topic RViz gabungan berhasil untuk `devi/odom`,
`devi/base_link`, `devi/rplidar_link`, dan `devi/wheel_left_link`.
Posisi `devi/base_link` sama dengan pose Nav2 sumber:
`[19.467546391719786, -28.721760858738936]`.
Gambar jendela RViz diperiksa: Global Status OK, grup Devi, laser dan
costmap tampil. Screenshot uji lokal: `/tmp/devi-rviz-visualization.png`.

Tidak ada goal/task atau kecepatan yang dikirim. Plan baru akan muncul
ketika Nav2 menerbitkannya untuk task nyata. Kehadiran Husky bergantung pada
sensor/adapternya yang berjalan; display dan marker kedua fleet tersedia.

## Aktivasi permanen

Relay sementara dihentikan setelah uji agar service menjadi satu-satunya
pemilik. Operator diminta menjalankan `sudo systemctl restart devi_robot.service`
di terminal Devi dan memberikan kembali initial pose lewat RViz laptop.
Core dan RViz baru sudah tersedia di laptop.

Verifikasi akhir yang masih menunggu tindakan operator: relay baru berada
dalam service, registrasi `Devi/devi`, dan marker fleet dari data adapter.
Preflight `robot_registered: false` hanya menyatakan proses pemeriksaan
tidak mendaftarkan robot; bukti registrasi harus dibaca dari adapter dan
`/fleet_states`.

## Verifikasi permanen sesudah pemulihan DDS

Pada sesi berikutnya di hari yang sama, discovery sempat terputus setelah
reboot. Operator menyetujui peer DDS eksplisit; lihat
[hasil pemulihan initial pose](INITIAL_POSE_RECOVERY_2026-11-03.md).
Service direstart dan menerima initial pose manual pada 15:10:35. Preflight
lulus, dan adapter terdaftar pada **15:11:02**. Laptop menerima map Devi,
kedua fleet `HuskyA200/husky_0` dan `Devi/devi`, serta marker `devi`.
Dengan demikian, penantian aktivasi permanen/registrasi di atas sudah
diselesaikan. Pengujian ini tidak mengirim task fisik.

Panduan: [README Devi](README.md) dan [README laptop](../laptop/readme.md).

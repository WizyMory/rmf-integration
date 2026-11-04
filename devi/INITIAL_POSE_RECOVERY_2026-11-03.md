# Pemulihan initial pose setelah reboot — 3 November 2026

## Bukti penyebab

Pemeriksaan pukul 14:56–14:58 WIB menemukan dua masalah yang terpisah:

1. RViz laptop hanya mempunyai publisher initial pose pada
   `/a200_1060/initialpose`. Tidak ada publisher pada `/devi/initialpose`.
   Tool dalam sesi itu masih ditargetkan ke Husky.
2. Domain 0 Devi hanya melihat node lokal `devi_initial_pose_bridge`,
   `devi_visualization_bridge`, observer dan node audit. Tidak ada core laptop.
   Bridge mempunyai subscriber `/devi/initialpose` tetapi menemukan nol
   publisher. Laptop melihat core dan Husky tetapi tidak melihat `/devi/map`
   maupun subscriber initial pose Devi. Digest pada Devi kosong.

Service Devi stabil, PID `3345`, `NRestarts=0`; AMCL menunggu initial pose.
Keberadaan nama `/amcl_pose` pada topic list belum membuktikan data pose.
Beberapa lifecycle Nav2 menunggu map→base_link karena AMCL belum diinisialisasi.

## Perbaikan yang disetujui

Operator secara eksplisit menyetujui patch DDS dan restart core/service.

- Profil laptop tetap memakai `wlp9s0`, menambah peer Devi `192.168.0.237`
  selain peer Husky `192.168.0.120`.
- Profil RMF Devi baru memakai `wlo1`, ParticipantIndex `auto`, peer laptop
  `192.168.0.218` dan Husky `192.168.0.120`, discovery multicast `spdp`.
- Helper Devi memasang `CYCLONEDDS_URI` khusus proses Cyclone domain 0.
  Fast DDS/Nav2 domain 73 dan konfigurasi komputer Husky tidak diubah.
- Target tool RViz untuk pose Devi harus `/devi/initialpose`; target Husky
  tetap `/a200_1060/initialpose`. Tidak ada pose otomatis atau pose contoh
  yang diterbitkan oleh pengujian ini.

File aktif: `tools/devi.bash`, `config/cyclonedds_rmf.xml` dalam paket Devi,
dan profil `cyclonedds_lan.xml` paket distributed laptop.
Backup helper robot: `devi/log/dds_recovery_backup_20261103_150212`.

## Validasi sebelum restart service Devi

- **26 tes helper/configuration lulus** dan pemeriksaan sintaks bash lulus.
- Build paket Devi berhasil; verifier underlay tetap **10 file utuh**.
- Uji `/brin_link_check/devi_recovery_1455/*` memakai String diagnostik
  membuktikan koneksi dua arah melalui profil baru: laptop menerima 3 balasan
  unik dalam 1,04 detik, responder Devi menerima/membalas 3 pesan.
  Kedua endpoint menghasilkan `passed: true`, `goals_sent: 0`.
- Core laptop lama dihentikan sesuai izin; core pengganti terlihat aktif
  dengan satu schedule, dispatcher dan RViz. Nav2 Husky tidak dihentikan.
  Pengamatan sebelum pergantian melihat task ID `patrol.dispatch-1` pada
  Husky; tidak ada goal/cancel yang dikirim ke Husky dalam pekerjaan ini.

## Hasil setelah restart dan initial pose manual

Operator melakukan restart; MainPID berubah menjadi `9219` pada **15:09:55**,
service active/running dengan `NRestarts=0`.
Pada **15:10:35**, journal mencatat:

- Bridge: `Forwarded manual initial pose to Devi AMCL (domain 73)`.
- AMCL: `initialPoseReceived` dan `Setting pose`.
- Pose hasil lokalisasi: sekitar `[27.398, -28.400, 0.0598]` (m, m, rad).

Preflight sesudahnya **`nav2_ready: true`, `accepted: true`, `errors: []`**,
kelima lifecycle bernilai `3`, dan digest yang diterima cocok dengan bundle.
Pada **15:11:02**, adapter mencatat **`Registered devi in Devi`**.

Pengamatan dari laptop membuktikan:

- Map Devi 755×673, resolusi 0,05 dan origin `[0, -33.65]` diterima.
- `/fleet_states` memuat `HuskyA200/husky_0` dan `Devi/devi`, lantai `L1`.
- Kedua robot melaporkan task ID kosong pada snapshot registrasi awal.
- `/fleet_markers` memuat marker nama `devi`, frame `map`.
- Core dan bridge terlihat bersama dalam discovery domain 0.

Pemeriksaan visualisasi permanen berikutnya selama 15 detik menerima 150
scan (720 titik), 150 pesan odometri, 26 local costmap, 11 global costmap,
75 footprint lokal dan model URDF. TF `map` ke body/lidar/odom/wheel Devi
berhasil; marker fleet tetap terlihat. Pada pengamatan lanjutan itu Devi
melaporkan task ID `patrol.dispatch-0`. Pengujian ini hanya berlangganan
telemetry dan tidak membuat task tersebut.

Pemulihan initial pose dan registrasi berhasil. Tidak ada task atau goal
fisik yang dikirim sebagai uji. Koneksi setelah reboot berikutnya belum
diuji dengan reboot tambahan pada sesi ini.

Panduan operasional: [README Devi](README.md).

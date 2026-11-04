# Auto initial pose Devi — 4 November 2026

## Pose yang diminta operator

Peta `gedungWS_0_rmf.yaml`, frame **`map`**:

```yaml
x: 19.423
y: -28.2408
z: 0.0
yaw: 1.83415  # rad
```

Log RViz yang diberikan operator mempunyai quaternion
`(0, 0, 0.793828, 0.608143)`. Sudut yaw yang dipakai adalah nilai angle
`1.83415` dari log yang sama. Robot perlu berada di lokasi dan arah parkir
tersebut ketika bringup dimulai.

## Implementasi

`config/bringup.yaml` sekarang memilih `localization: automatic_initial_pose`
dan menyimpan pose di atas. Wrapper membaca konfigurasi ini dan membuat
parameter AMCL runtime dengan `set_initial_pose: true`,
`always_reset_initial_pose: true`, serta `initial_pose.x/y/z/yaw`.
Pose diterapkan langsung oleh AMCL ketika lifecycle aktif, sehingga tidak
menunggu core laptop atau publisher initial pose eksternal.

Ini mengikuti implementasi [AMCL ROS 2 Humble](https://github.com/ros-navigation/navigation2/blob/humble/nav2_amcl/src/amcl_node.cpp)
yang memakai parameter pose pada `on_activate`. Tidak ada node yang
mengulang pengiriman pose otomatis selama robot beroperasi.
Koreksi manual melalui `/devi/initialpose` tetap tersedia untuk sesi aktif;
startup berikutnya kembali memakai pose parkir yang dikonfigurasi.

Mode `manual_initial_pose` tetap didukung untuk rollback. Mode itu membuat
`set_initial_pose: false` dan menghapus pose awal lama dari parameter runtime.
Pose otomatis yang tidak numerik, tidak finite, tidak lengkap, atau salah
frame ditolak sebelum file runtime ditulis.

Husky tetap memakai initial pose manual. Pada laptop perubahan hanya
memperbarui panduan urutan operasi; konfigurasi sensor/TF/hardware dan profil
DDS kedua komputer tidak diubah. Underlay `devi_ws` tetap dipertahankan.

## Validasi sebelum aktivasi

- Pose Devi yang teramati sebelum perubahan dekat titik parkir:
  `[19.4139, -28.2124, 1.8301]`, task ID kosong, mode idle.
- **79 tes Devi lulus di laptop dan 79 tes lulus di robot**.
- Build paket `brin_devi_fleet_adapter` di robot berhasil.
- Preview parameter mengonfirmasi frame `map`, auto pose True, reset True,
  dan keempat angka persis sesuai permintaan.
- Manifest delapan file diverifikasi di robot.
- Verifier sebelum/sesudah pemasangan: **10 file underlay asli utuh**.
- Backup: `devi/log/auto_pose_backup_20261104_095621/before_update.tar.gz`.
- Manifest: `devi/log/auto_pose_update_manifest.json`.

## Aktivasi

Kode sudah terpasang; service lama masih memuat mode manual sampai
dimulai ulang. SSH memerlukan password sudo sehingga operator diminta
menjalankan `sudo systemctl restart devi_robot.service` langsung di terminal
robot, dengan robot diam di titik parkir, tanpa 2D Pose Estimate untuk uji.
Hasil AMCL/preflight/registrasi sesudah restart masih menunggu verifikasi.

## Verifikasi pada aktivasi service Web otomatis

Pada aktivasi service berikutnya di hari yang sama, service mulai pukul
**10:44:54 WIB** dengan MainPID `11603`. Pada **10:44:56**, AMCL langsung
mencatat `Setting pose: 19.423 -28.241 1.834`, sesuai konfigurasi startup.
Koreksi manual yang teramati terjadi kemudian, mulai 10:46:11. Jadi pose
awal sudah diterapkan saat startup sebelum koreksi operator.
Adapter terdaftar di RMF pada **10:46:00**, kemudian API Web menerima state
Devi yang segar. Lihat [hasil Web otomatis](WEB_BOOT_RESULT_2026-11-04.md).
Penantian verifikasi aktivasi di atas sudah diselesaikan.

Panduan operasi terbaru: [README Devi](README.md) dan
[README laptop](../laptop/readme.md).

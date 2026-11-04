# Bringup Devi gedungWS_0 — 3 November 2026

## Konfirmasi operator

- Footprint lingkaran radius **0,55 m**, diameter 1,10 m.
- Uji Nav2, cancel, kendali manual dan E-stop dinyatakan berhasil oleh operator.
- Auto initial pose ditunda. Setiap start menunggu 2D Pose Estimate.

## Perubahan yang disiapkan

`brin_devi_fleet_adapter/bringup.launch.py` mengikutsertakan launch
`devi_bringup` asli, memakai map canonical `gedungWS_0_rmf.yaml` dan
parameter runtime hasil salinan parameter underlay. AMCL memakai
`set_initial_pose=false`, `always_reset_initial_pose=true`. Kedua costmap dan
profil RMF memakai radius 0,55 m. Parameter sensor, motor, EKF, kecepatan,
smoother, mux dan TF underlay tidak ditimpa.

Nav2 tetap Fast DDS/domain 73; native RMF tetap Cyclone/domain 0.
Bridge terpisah meneruskan map asli ke `/devi/map` dan initial pose manual
dari `/devi/initialpose` ke AMCL. Tidak ada initial pose otomatis, goal atau
kecepatan dari bridge tersebut. Supervisor menunggu preflight diterima
sebelum menjalankan satu adapter. Tidak ada core RMF di Devi.

Laptop mempunyai preset RViz Devi untuk profil gedungWS_0 dan radius marker
Devi 0,55 m. Visualizer menerima kedua fleet. Preset Husky lama tetap ada;
source/runtime Husky tidak dideploy pada pekerjaan ini.

## Bukti sebelum aktivasi service

- SSH ke `devi@192.168.0.237` berhasil; hostname `devi-nuc`.
- Startup lama: terminal desktop menjalankan `devi_autostart.sh` dan Nav2;
  `devi_robot.service` gagal berulang karena paket `devi_config` tidak ada.
- Build paket Devi berhasil di laptop dan robot.
- Build empat paket integrasi laptop berhasil; preset RViz baru terpasang.
- **164 tes lokal lulus**: Devi, paket distributed laptop dan helper deployment.
- **64 tes Devi lulus di robot**.
- `ros2 launch ... bringup.launch.py --show-args` berhasil.
- Render parameter pada `devi/log/bringup_preview` berhasil, tanpa meluncurkan
  Nav2 kedua. Map canonical dan digest cocok.
- `systemd-analyze verify` untuk service gabungan lama + override exit 0.
  Peringatan service netplan/snapd/anydesk lain tidak berasal dari override.
- Verifier underlay sebelum/sesudah penyalinan: **10 file, seluruhnya utuh**.

Source overlay disalin melalui arsip dengan SHA-256:

```text
1d923549dc52c619eb4a8e777360474ab957346a69124e09b604b7d39b90369b
```

Manifest 41 file diverifikasi di robot:
`/home/devi/rmf-integration/devi/log/bringup_update_manifest.json`.
Backup source sebelum penyalinan:
`devi/log/source_backup_20261103_114013/before_bringup.tar.gz`.
Penyalinan ini berasal dari working tree; HEAD awal robot `e8e3dd7`.
Jangan menganggap HEAD tersebut mencakup perubahan bringup baru.

## Aktivasi service dan pengujian yang masih menunggu

SSH tidak mempunyai sudo tanpa password. Installer konkret tersedia pada
`devi/systemd/install.bash`, mem-backup service/entry desktop, menonaktifkan
entry desktop lama, memasang override dan enable service. Installer tidak
menyalakan stack. Operator telah menjalankan installer dengan sudo di
terminal robot, menghentikan bringup desktop lama, lalu start service baru.

Verifikasi SSH setelah aktivasi: service **enabled, active/running**, PID
`31966`; hanya satu launch integrasi, AMCL, map server dan controller.
Entry desktop lama sudah `Hidden=true`, `X-GNOME-Autostart-enabled=false`.
Backup installer: `devi/log/service_backup_20261103_114223`.
`NRestarts=815` adalah hitungan kegagalan service lama dan tetap stabil
selama pemeriksaan service baru.

Parameter node yang berjalan: map canonical, waktu nyata, AMCL initial pose
False/reset True, radius kedua costmap 0,55 m dan footprint string `[]`
(memakai circle). AMCL benar-benar menunggu initial pose; tidak ada goal.
Map relay memiliki satu publisher lokal pada `/devi/map`.

Core/RViz dibuka pada terminal laptop **RMF Core - Husky dan Devi**; tepat
satu core/digest profil teramati. DDS laptop dan Devi belum saling menemukan
dengan profil sebelumnya. Usulan peer khusus proses RMF telah disiapkan
dan menunggu persetujuan perubahan jaringan sesuai AGENTS.md.
Profil yang diusulkan memakai peer eksplisit dan ParticipantIndex `auto`
untuk discovery unicast. Ini mengikuti [dokumentasi Cyclone DDS 0.10.5](https://cyclonedds.io/docs/cyclonedds/0.10.5/config/cyclonedds_specifics.html);
perbaikannya tetap perlu dibuktikan melalui pengamatan dua komputer setelah
disetujui, bukan disimpulkan dari file XML saja.

Keyboard teleop lama keluar karena `pynput` memerlukan X11/`DISPLAY` yang
tidak tersedia dalam system service. Driver, joystick dan twist mux hidup.
Cara menjalankan node keyboard dari desktop dicatat dalam README; tidak ada
pengaturan hardware/safety yang diubah untuk menyembunyikan error tersebut.

Belum dinyatakan selesai: komunikasi DDS RMF dua komputer, initial pose
manual pada peta baru, registrasi otomatis dan marker Devi di RViz laptop.
Tidak ada task/goal fisik yang dikirim dalam
pengujian ini. Reboot otomatis dan traffic bersama juga belum diuji.

## Pemeriksaan sesudah reboot, 13:00 WIB

Operator mengirim status setelah start pada boot `f8cd560f050b4a23bc54fce10cd4df81`.
SSH memverifikasi service tetap active/running, MainPID `4333`, `NRestarts=0`.
Map relay tetap memiliki satu publisher lokal. AMCL dan planner hidup,
menunggu initial pose/map→base_link; supervisor belum mendaftarkan robot
dan masih melaporkan core/digest laptop tidak ditemukan.

Peringatan `/dev/tty-ROBOTEQ` berasal dari alias lama pada skrip tunggu.
Parameter driver aktual adalah `/dev/Roboteq`, dengan udev alias ke
`ttyACM0`; log boot **12:58:02** menyatakan Roboteq tersambung di port itu.
Skrip tunggu diperbaiki mengikuti alias tersebut. Port, baud, parameter
driver dan udev tidak diubah. Perubahan ini berlaku pada start berikutnya.

Traceback gateway `KeyboardInterrupt` pada **12:54:55** terjadi saat
penghentian boot sebelumnya. Perbaikan membuat child menutup lewat Pipe
milik parent dan menjaga cleanup dari SIGINT berulang; SIGTERM tetap
tersedia untuk timeout terminate. **66 tes Devi lulus di laptop dan robot**,
termasuk proses ROS localhost yang menerima SIGINT satu process group dan
berakhir bersih, serta SIGINT berulang saat cleanup. Pengujian tidak
mengirim goal atau kecepatan. Perbaikan kode berlaku setelah proses gateway
dimulai ulang; service aktif tidak dihentikan untuk menerapkan patch ini.
Patch enam file diverifikasi melalui `devi/log/shutdown_fix_manifest.json`;
backup sebelum patch berada di
`devi/log/shutdown_fix_backup_20261103_130625/before_patch.tar.gz`.
Verifier underlay tetap melaporkan 10 file asli utuh. Sesudah pengujian,
service tetap MainPID `4333`, active, `NRestarts=0`.

Log abort planner pada 12:54 juga berasal dari shutdown boot sebelumnya.
Parameter/implementasi Nav2 underlay tidak diubah untuk menutupi pesan itu.
Boot baru memang teramati, tetapi startup otomatis tanpa perintah manual
operator dan traffic bersama tetap belum dinyatakan lulus.

Urutan perintah operasional tersedia pada [README Devi](README.md) dan
[README laptop](../laptop/readme.md).

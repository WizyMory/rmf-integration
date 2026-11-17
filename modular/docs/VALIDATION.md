# Validasi modul v0.1.0 — 17 November 2026

Modul dibangun dan diuji lokal di Ubuntu 22.04 / ROS 2 Humble. Implementasi
mengambil pelajaran dari pemisahan domain/RMW Devi serta kebijakan transit
Husky, tetapi paket baru tidak mengimpor paket khusus kedua robot tersebut.
Source/deployment Husky, Devi dan core aktif tidak diganti pada pekerjaan ini.

## Pengujian yang disediakan

Tes offline mencakup:

- Pembuatan profil baru tanpa menimpa file lama, path relatif dan pin aset.
- Penolakan dimensi/batas gerak yang belum diisi atau bukan nilai finite.
- Validasi domain/RMW/frame/plugin ID dan commissioning.
- Deteksi perubahan peta/image dan metadata charger yang diwajibkan Humble.
- Transformasi koordinat bolak-balik dan jarak ke lane, bukan hanya vertex.
- Read-only gateway menolak goal/cancel sebelum pesan dikirim.
- Preflight menolak profil stale/mismatch, core ganda dan pose jauh dari graph.
- Target task eksplisit dan dry-run sebagai default.
- Pemilihan BT transit/akhir, hold waktu RMF, ETA dari feedback Nav2.
- Path pengganti menunggu hasil action lama meskipun acceptance terlambat.
- Hasil lama/cancel/abort/readiness loss tidak menyelesaikan task sebagai sukses.
- Render fragmen Nav2 internal dan service tanpa memasang/memulai service.

Command dari root modul:

```bash
PYTHONPATH=src/rmf_nav2_onboard PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q src/rmf_nav2_onboard/test
bash -n tools/robot.bash
```

Tes ROS opt-in memakai **loopback**, domain Nav2 `221`, domain RMF `222`,
RMW Fast DDS. Tidak menghubungi core/robot fisik domain produksi:

1. Fake Nav2 menerbitkan map, scan, odometri dan TF serta menyediakan
   lifecycle/GetParameters/ NavigateToPose. Gateway asli membaca semua itu
   dan melaporkan ready. Tidak ada goal yang diterima fake action server.
2. Scheduler RMF native benar-benar dijalankan; node dispatcher/building-map
   untuk tes hanya menyediakan identitas discovery, bukan implementasi task
   dispatcher/building-map penuh. Adapter native melakukan handshake dan
   mendaftarkan `robot_01` di `Robot01Fleet`. Shutdown SIGINT bersih dengan
   exit `0`, dan registrasi tidak mengirim goal idle.

Command setelah source ROS/RMF lokal dan memastikan domain uji bebas:

```bash
source /opt/ros/humble/setup.bash
# Source underlay RMF custom bila paket tidak dipasang melalui apt.
export ROS_DOMAIN_ID=222 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_DISCOVERY_SERVER CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE
PYTHONPATH=src/rmf_nav2_onboard PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  RMF_NAV2_TEST_ROS=1 python3 -m pytest -q src/rmf_nav2_onboard/test
```

Hasil verifikasi lokal: **28 tes offline lulus**, **2 tes integrasi loopback
lulus**, build `rmf_nav2_onboard` berhasil. Tes ROS hanya berjalan jika flag
opt-in diberikan; tanpa flag, dua tes tersebut ditandai skipped.

GitHub Actions disiapkan di `.github/workflows/ci.yml` dengan job offline dan
container ROS Humble. Workflow ini aktif otomatis ketika folder modul
diekspor menjadi root repository mandiri. Jika tetap berada di subfolder
`rmf-integration/modular`, workflow perlu dipanggil/dipindahkan oleh pemilik
workflow root. Workflow GitHub belum dijalankan dari sesi lokal ini.

## Batas hasil

Kelulusan uji ini belum membuktikan task fisik, kualitas lokalisasi, radius
keselamatan, koreksi yaw, performa jaringan multi-host, operasi beberapa
robot bersama, Web end-to-end, boot systemd, atau core opsional dengan semua
building map milik pengguna. Tes native memvalidasi handshake/registrasi dan
shutdown, bukan full dispatch ke robot fisik.

Pada setiap robot baru, penerimaan operator harus mencakup:

1. Driver dan Nav2 asli bekerja tanpa adapter.
2. Initial pose/map/TF dan footprint sesuai fisik.
3. Inspect dan preflight lulus, lalu hanya satu adapter terdaftar.
4. Satu task terminal menuju waypoint nyata selesai dan arah akhir benar.
5. Cancel ketika bergerak ditangani Nav2; task yang gagal tidak dilabel sukses.
6. Bila transit aktif: toleransi XY sesuai goal checker, vertex antara tidak
   mengejar yaw, hold traffic dan arah ujung lintasan tetap benar.
7. Task dari Web, bila Web dipakai, mencapai adapter/robot yang dituju.
8. Disconnect/reconnect, shutdown dan startup otomatis diuji dengan prosedur
   keselamatan dan watchdog asli robot.

Catat commit modul, versi RMF/Nav2, profil robot, hash aset, task booking ID,
durasi, log action dan hasil observasi. Jangan memakai kelulusan tests untuk
menandai `commissioning` true sebelum uji fisik tersebut benar-benar selesai.

## Daftar hasil source

- Paket ament_python `rmf_nav2_onboard`, tanpa dependensi nama robot/sensor.
- Wrapper command lokal dan template YAML dengan nilai fisik wajib diisi.
- Core opsional + site-profile publisher untuk instalasi mandiri.
- Render service dan fragmen Nav2 untuk review operator.
- Task CLI targeted, dry-run, publish sekali dan cancel.
- Dokumentasi parameter, jaringan, commissioning, GitHub dan rollback.
- License Apache-2.0 dan workflow CI untuk repository mandiri.

Archive ekspor dibuat oleh `bundle` dari allowlist source/docs/tools/workflow.
Profil robot, site assets, runtime log, build/install dan cache tidak ikut.

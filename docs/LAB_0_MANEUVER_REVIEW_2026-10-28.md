# Pemeriksaan berhenti dan berputar menuju lab_0 — 28 Oktober 2026

Status: diagnosis baca-saja dan patch proposal. Perilaku navigasi pada
checkout utama dan robot belum diubah. Belum ada deployment atau uji gerak
untuk proposal ini.

## Temuan dari sesi uji

Log pada `/home/husky/rmf-integration/husky/log/ros` mencatat dua task,
masing-masing mulai pukul 10:26:55 dan 10:35:47 WIB. Statistik berikut
mencakup sesi tersebut, bukan pengukuran satu perjalanan `lab_0` terisolasi.

| Kejadian yang dicatat | Jumlah |
| --- | ---: |
| Recovery `Running spin` | 23 |
| Recovery `Running backup` | 22 |
| Recovery `Running wait` | 23 |
| Peringatan controller `detected collision ahead` | 667 |
| Controller `Failed to make progress` | 27 |
| Goal Nav2 berakhir `STATUS_ABORTED` yang diterima adapter | 6 |
| Goal waypoint yang dikirim adapter | 34 |

Angka recovery adalah jumlah percobaan yang dimulai; beberapa dihentikan
karena collision. Angka tersebut bukan bukti semua manuver selesai secara
fisik. Log behavior server secara eksplisit mencatat `Turning 1.57`;
putaran recovery sekitar 90 derajat ini berbeda dari koreksi arah controller
ketika mengikuti lintasan.

Urutan yang terlihat antara lain controller gagal, lalu `Running spin`,
`Running wait`, dan `Running backup`. Planner juga beberapa kali tidak
mendapat jalur ke `(29.22, -40.48)`, dekat waypoint graph sebelum `lab_0`.
Belum dapat ditentukan dari log saja apakah penghalangnya benda nyata,
kesesuaian scan/peta, atau kondisi lokalisasi.

Konfigurasi Nav2 robot pada
`/home/husky/rmf_ws/src/husky_nav2/config/nav2_params.yaml` cocok dengan
snapshot repository saat pemeriksaan. Source adapter laptop dan Husky telah
dibandingkan. Tidak ada parameter footprint, inflation, kecepatan, TF,
sensor, jaringan, atau waktu yang diubah.

## Sumber recovery

`HardwareCommand.__init__` mengosongkan `behavior_tree` yang sebelumnya
dipilih `Nav2Command`. Goal RMF akhirnya memakai behavior tree bawaan Nav2.
Salinan XML terpasang di robot berisi recovery `Spin` 1,57 radian, `Wait`
5 detik, dan `BackUp` 0,30 meter pada 0,05 m/s.

Perilaku ini sesuai
[behavior tree bawaan Nav2 Humble](https://github.com/ros-navigation/navigation2/blob/humble/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml).
Override `_start_escape` pada adapter fisik hanya menghalangi recovery yang
dimulai adapter sendiri; override tersebut tidak menghalangi recovery di
dalam behavior tree Nav2.

Ada sumber berhenti tambahan: adapter mengirim setiap waypoint RMF sebagai
goal Nav2 dan menjaga waktu keberangkatannya. Proposal ini mempertahankan
urutan, orientasi, dan waktu waypoint tersebut. Kontrak RMF memang meminta
robot menunggu sampai waktu waypoint untuk menghindari konflik traffic;
lihat [RobotCommandHandle Humble](https://github.com/open-rmf/rmf_ros2/blob/humble/rmf_fleet_adapter/include/rmf_fleet_adapter/agv/RobotCommandHandle.hpp).

## Proposal perubahan yang telah diuji offline

[Patch yang dapat ditinjau](proposals/lab_0_bounded_recovery.patch) menghapus
override behavior tree kosong pada `HardwareCommand` di kedua snapshot.
Adapter mewarisi `rmf_bounded_navigation.xml`, yang sudah dipilih dan dicari
melalui package share lokal oleh `Nav2Command`.
XML pada instalasi Husky sudah diperiksa dan checksum-nya cocok dengan
snapshot laptop. File tersebut tersedia pada overlay integrasi robot.

XML ini tetap menghitung ulang jalur dan mengikuti jalur. Ketika planner
atau controller gagal, goal berakhir dan kebijakan retry RMF yang sudah
ada mengambil alih. Tidak ada rangkaian recovery `Spin`, `Wait`, atau
`BackUp` di dalam goal RMF. Deteksi collision controller, footprint,
inflation, batas kecepatan dan orientasi tujuan tetap dipertahankan.

Putaran controller yang diperlukan untuk membelok dan mencapai orientasi
tujuan masih dapat terjadi. Peringatan collision perlu diperiksa dengan
scan, peta dan lokalisasi pada uji berikutnya. Proposal ini tidak menjamin
jalur yang terhalang menjadi dapat dilalui atau semua jeda perjalanan hilang.

Patch mencakup dua file pada masing-masing snapshot:

- `brin_husky_hardware/brin_husky_hardware/adapter.py`.
- `brin_husky_hardware/test/test_idle_startup.py`.

Perubahan berlaku pada adapter fisik yang dijalankan di Husky. Salinan
laptop menjaga kesesuaian source; kelas adapter simulasi tidak diubah.
Pemakaian Nav2 manual tetap mengikuti behavior tree yang dipilih pemanggilnya.

Salinan source untuk pengujian dibuat terpisah di
`/tmp/brin-lab0-diagnosis-20261028/review`. Pada setiap snapshot, 33 tes lulus,
meliputi behavior tree yang dikirim ke goal, guard task/idle, pembatalan,
kegagalan action, larangan escape otomatis fisik, serta pemeliharaan waktu
tunggu RMF. Ini bukan bukti hasil gerak fisik.

## Persetujuan penerapan

Proposal mengubah perilaku recovery navigasi Husky. `AGENTS.md` mengharuskan
konfirmasi sebelum perubahan hardware atau pengaturan keselamatan.
Sesudah disetujui, patch dapat diterapkan ke snapshot, diuji kembali,
dideploy dengan backup, lalu dibuild pada target yang tepat. Aktivasi adapter
dan pengulangan uji gerak memerlukan koordinasi operator di lokasi.

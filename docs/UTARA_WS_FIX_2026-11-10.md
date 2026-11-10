# Perbaikan robot berhenti sebelum utara_WS — 10 November 2026

## Penyebab dan bukti

Graph `gedungWS_0` yang dipakai semua fleet mempunyai lane `0 → 18` dengan
`dock_name: utara`. Vertex 18 adalah `utara_WS`; vertex 0 adalah titik
sebelumnya `(10.3372, -25.0535)`. Implementasi Humble `parse_graph.cpp`
menerjemahkan properti lane tersebut menjadi **entry event Dock**. Karena itu
RMF memanggil `RobotCommandHandle.dock()` sebelum melintasi lane terakhir,
bukan mengirim seluruh segmen itu sebagai navigasi biasa.

Baik command handler Husky maupun Devi menyatakan docking tidak didukung.
Callback docking tidak diselesaikan secara palsu. Akibatnya robot berhenti
di vertex sebelumnya dan task menunggu docking yang tidak tersedia.

Audit runtime mengonfirmasi kasus ini pada Devi:

- Task `patrol.dispatch-2`, posisi fleet `(10.3372001648, -25.0534992218)`.
- Mode 7; API menampilkan `status: working`.
- Issue: `Docking utara is unsupported; use park finishing behavior`.

Ini bukan alasan untuk memperbesar toleransi goal Nav2, menggeser waypoint,
menonaktifkan pemeriksaan collision, atau menyatakan robot telah tiba.

## Perubahan source

1. Hapus anotasi `dock_name`/`undock_name` yang tidak didukung dari graph
   runtime dan building RMF turunan, pada salinan laptop, Husky dan Devi.
2. Generator `generate_gedungws.py` kedua snapshot membersihkan anotasi itu
   pada **deep copy building turunan**, sehingga ekspor ulang tidak memunculkan
   bug yang sama. Report mencatat `navigation_only_docks: [utara]`.
3. Editor sumber asli tetap utuh, termasuk anotasi docking untuk dokumentasi.
   Gunakan generator profil ini untuk runtime; jangan mengganti hasilnya
   dengan ekspor mentah dari editor yang masih memuat docking tersebut.
4. Tidak mengubah command handler, callback sukses, koordinat/orientasi
   tujuan, urutan vertex, konektivitas lane, occupancy, origin/resolusi,
   footprint, inflation, toleransi Nav2, sensor, TF atau safety.

Graph tetap 19 vertex/38 lane; `utara_WS` tetap `(1.7381, -27.2952)` dalam
frame RMF map L1. Charger/holding/parking dan metadata task tetap dipertahankan.
SHA-256 editor asli tetap
`8c51b1f675f2b7a2f34784e5e5d6d8d3368f617927a59a2188d0f80aa90d0357`.

Digest profil bersama berubah dari
`a5c392a4a4446542b69b08d0bb44d8824e8ee081c955f7bc1cee3b795e4294be` ke:

```text
dff016256abf2c1c0482212c97272f7cb36fc49dbbd4794185196e61afa8dd99
```

## Pengujian offline

`tools/test_utara_ws_navigation.py` mula-mula mereproduksi sembilan kegagalan
pada bundle lama, termasuk event docking dalam hasil planner native RMF.
Sesudah koreksi, seluruh **14 tes regresi lulus**:

- Lane masuk/keluar tujuan adalah navigasi biasa pada ketiga bundle.
- Native planner mencapai vertex tujuan dari tujuh waypoint bernama lain:
  21 lintasan diuji, tanpa event docking sebelum tujuan.
- Building turunan tidak memunculkan docking kembali.
- Generator bersifat idempotent dan mempertahankan metadata non-docking.
- Regenerasi penuh di staging menghasilkan aset yang byte-identik dengan
  bundle perbaikan, tanpa mengubah input editor atau konfigurasi fleet.

Map tests + regresi: laptop **36 lulus**, snapshot Husky **36 lulus**.
Pengujian lebih luas laptop maps/distributed/regresi: **111 lulus, 2 gagal**.
Kedua kegagalan berada pada preset RViz yang sudah memiliki perubahan lokal
sebelum pekerjaan ini (topic initialpose Devi dan layer Enabled). Preset dan
test tersebut tidak diubah untuk meloloskan pengujian. Percobaan awal juga
terkendala lokasi ROS log read-only; diulang dengan ROS_LOG_DIR di `/tmp`.

Tes di atas tidak membuat node controller, action client robot, task atau
goal fisik. Keberhasilan planner offline bukan bukti task fisik sudah selesai.

## Deployment dan pemulihan runtime

Operator mengizinkan audit dan deployment tersinkron saat robot idle, serta
pembatalan task macet yang ditemukan. Cancel `patrol.dispatch-2` dikirim sekali.
CLI mengalami response timeout; tidak dikirim ulang secara membabi buta.
Pemeriksaan berikutnya menunjukkan Devi `idle` dengan task ID kosong. Task
tersebut tidak ditandai sukses oleh perubahan ini dan tidak dicoba ulang.

Bundle memakai hash guard, backup sebelum penggantian dan penggantian atomik.
Edit lain pada masing-masing worktree dipertahankan; tidak ada git pull/reset,
commit atau push dari pekerjaan ini. Instalasi yang sudah dibangun dan
diverifikasi hash graph/building turunannya:

| Mesin | Instalasi paket map/aset yang diperbarui |
| --- | --- |
| Komputer-utama | `/home/rslab/rmf-integration/main/install/brin_rmf_maps` |
| Laptop | `/mnt/UbuntuData/rmf-integration/laptop/install/brin_rmf_maps` |
| Laptop, workspace lama | `/mnt/UbuntuData/rmf_ws/install/brin_rmf_maps` |
| Husky | `/home/husky/rmf-integration/husky/install/brin_rmf_maps` |
| Husky, workspace lama | `/home/husky/rmf_ws/install/brin_rmf_maps` |
| Devi | `/home/devi/rmf-integration/devi/install/brin_devi_fleet_adapter` |

Core utama di-restart melalui `brin-rmf-core.service` setelah pembaruan.
Statusnya `healthy: true`, tepat satu core/publisher profil, dan digest
publikasi cocok dengan bundle baru. Tidak ada core laptop kedua dijalankan.

Supervisor Devi ditahan sementara agar tidak memulai adapter dengan graph
campuran, lalu dilanjutkan. Preflight setelah pemulihan `accepted: true`,
`errors: []`, domain robot 73, native RMF domain 0, dan digest baru cocok.
Devi terdaftar kembali, Web tersambung ke `ws://192.168.0.141:8000/_internal`,
serta idle tanpa issue docking. Service Nav2/sensor Devi tetap MainPID 3352;
verifier underlay tetap menyatakan sepuluh file asli tidak berubah.

Husky juga memiliki adapter lama di memori. Launcher integrasinya dihentikan
terpisah dari Nav2 dan peluncuran pengganti memakai argumen/environment yang
sama dengan preflight tetap aktif. Unit pengganti adalah unit pengguna
**sementara**, bukan autostart boot. Percobaan awal ditolak dengan dua node
core tidak terdeteksi dari Husky. Profil discovery ternyata masih hanya
menunjuk peer laptop `.218`, bukan core komputer-utama `.141`. Operator secara
terpisah menyetujui penambahan peer `.141` sambil mempertahankan `.218`, hanya
pada XML DDS integrasi Husky. Backup profil sumber/terpasang dibuat; IP
interface, routing, Wi-Fi dan DDS service Clearpath tidak diubah. Tes guard
profil dan regresi graph setelah perubahan ini: **40 lulus**. Hasil preflight
pengganti harus dikonfirmasi dari log baru; cache fleet pada Web bukan bukti:

```bash
systemctl --user status brin-husky-adapter-utara-ws-run.service --no-pager
journalctl --user -u brin-husky-adapter-utara-ws-run.service -n 80 --no-pager
```

Percobaan unit pertama gagal karena helper shell membuka `/dev/stdout` yang
berupa socket journald. Launcher pengganti memakai perintah ROS yang sama
secara langsung; tidak mengubah helper, sensor atau konfigurasi DDS.
Nav2 Husky PID 6194 serta Clearpath platform/sensors PID 1980/1982 dipertahankan.
Jangan menyalakan adapter manual kedua bersamaan dengan unit ini. Saat operator
mengakhiri sesi, stop unit ini hanya setelah task selesai dan robot diam:

```bash
systemctl --user stop brin-husky-adapter-utara-ws-run.service
```

## Uji fisik berikutnya dan rollback

Belum ada task/goal baru menuju `utara_WS` dikirim oleh pekerjaan ini.
Operator perlu menjalankan satu task baru pada satu robot terlebih dahulu,
dengan area aman dan E-stop siap. Pastikan robot melintasi lane terakhir,
Nav2 mengembalikan SUCCEEDED dan task RMF benar-benar completed; respons API
diterima atau task ID kosong saja bukan bukti keberhasilan navigasi.

Backup/manifest berada pada `<target>/log/validation/utara_ws_fix_20261110/`
dan `log/validation/utara_ws_fix_20261110/` untuk workspace lama. Staging utama
ada pada direktori validasi `main/log/.../staging`; staging lain di
`/tmp/utara-ws-fix-20261110.9mFzcb`. Rollback hanya saat robot diam: pulihkan
aset yang dibackup secara tersinkron di seluruh mesin, build ulang paket map,
kemudian reload core/adapter dengan gate normal. Graph lama akan mengembalikan
masalah docking; jangan rollback hanya satu mesin karena digest akan berbeda.

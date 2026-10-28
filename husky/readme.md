# Husky — panduan uji operasional Nav2 dan fleet adapter Open-RMF

Lokasi robot: `/home/husky/rmf-integration/husky/readme.md`.
Jalankan perintah integrasi dari `/home/husky/rmf-integration`.
Panduan pasangan: [README laptop](../laptop/readme.md).

## 1. Peran, workspace dan batas keselamatan

Robot fisik `/a200_1060` terdaftar di RMF sebagai `husky_0`, fleet `HuskyA200`,
lantai L1. RMF core/CLI/Web berada di laptop `192.168.0.218`; Husky Wi-Fi
`192.168.0.120`. Seluruh proses fisik memakai waktu nyata, domain 0.
RViz dan tiga visualizer traffic/fleet juga dapat berjalan di laptop melalui
satu perintah core dengan `rviz:=true`; robot tetap menjalankan sensor, Nav2
dan satu adapter.

Pembaruan RViz 28 Oktober 2026 sudah dideploy dan dibuild di kedua perangkat:
empat paket berhasil dibuild dan 56 tes lulus pada masing-masing perangkat.
Tampilan saat robot bergerak belum diuji langsung. Lihat
[laporan deployment RViz](../docs/RVIZ_DEPLOYMENT_2026-10-28.md).

| Kebutuhan | Lokasi yang dipakai |
| --- | --- |
| Platform Clearpath/UM7 | Instalasi dan service robot yang sudah bekerja |
| Nav2 dan Hokuyo yang sudah bekerja | `/home/husky/rmf_ws/install` |
| Empat paket integrasi hasil deployment | `/home/husky/rmf-integration/husky/install` |
| Profil DDS integrasi | `husky/src/brin_husky_distributed/config/cyclonedds_lan.xml` |

Jangan menimpa workspace lama, menyalin build laptop, atau membangun ulang
sensor saat uji. **API/protokol/IP/port/parameter Hokuyo tidak boleh diubah.**
Jangan mengikuti instruksi lama perubahan IP USB untuk menjalankan uji ini.
Jangan mengubah UM7, EKF, TF, controller, safety, firewall atau jaringan.

Komunikasi sudah diuji; navigasi/task fisik belum dinyatakan lulus. Mulai dari
uji tanpa gerak. Tahap aktivasi sensor/Nav2/bridge memerlukan persetujuan
operator, dan tahap gerak memerlukan area aman, joystick serta E-stop fisik
yang sudah diuji. Putus SSH/DDS dan Ctrl-C bukan pengganti E-stop.

## 2. Arti H0–H4 dan persiapan setiap terminal Husky

`H` berarti terminal di Husky; angka hanya membedakan jendela terminal, bukan
urutan langkah. Tahap waktu sebenarnya diberi huruf `A` sampai `G` dan harus
dikerjakan berurutan. Pasangannya di laptop bernama `L1` sampai `L4`.
`L1 (terminal laptop)` tidak sama dengan `L1 (nama lantai)`.

| Terminal | Fungsi | Perilaku proses |
| --- | --- | --- |
| **H0** | Diagnostik: pemeriksaan awal, DDS, native check dan observasi | Perintah pendek; terminal tetap tersedia selama uji |
| **H1** | Satu driver Hokuyo, hanya bila scan belum punya publisher | Jika dimulai, proses dibiarkan hidup |
| **H2** | Satu Nav2/AMCL/map server, hanya bila belum berjalan | Jika dimulai, proses dibiarkan hidup |
| **H3** | Peran RViz untuk initial pose dan observasi | Dipenuhi RViz laptop di L1 bila memakai `rviz:=true`; GUI Husky menjadi alternatif |
| **H4** | Preflight tanpa dispatch, kemudian satu fleet adapter | Preflight selesai sendiri; terminal yang sama lalu dipakai adapter |

Jika memakai RViz laptop, H3 tidak memerlukan proses RViz di robot. Jika driver
atau Nav2 yang benar sudah hidup dari sesi/service lain, **jangan membuat
duplikat**; H1 atau H2 cukup dipakai untuk pemeriksaan. Setiap kali membuka H0,
H1, H2, H3, atau H4, ulangi blok environment berikut di terminal tersebut.
Overlay integrasi harus terakhir; export DDS dilakukan setelah semua sourcing:

```bash
cd /home/husky/rmf-integration
source /etc/clearpath/setup.bash
source /home/husky/ros2_ws/install/local_setup.bash
source /home/husky/rmf_ws/install/local_setup.bash
source /home/husky/rmf-integration/husky/install/local_setup.bash
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$PWD/husky/src/brin_husky_distributed/config/cyclonedds_lan.xml"
export ROS_LOG_DIR="$PWD/husky/log/ros"
unset ROS_DISCOVERY_SERVER
```

Ini hanya environment terminal, bukan perubahan DDS service Clearpath.
Discovery server khusus memerlukan tinjauan tersendiri sebelum di-unset.
Jangan memakai URI Cyclone localhost simulasi atau `use_sim_time:=true`.
Helper `tools/integration.bash` mengatur environment anak prosesnya sendiri;
terminal lain tetap perlu blok di atas.

Pemeriksaan baca-saja:

```bash
git rev-parse HEAD
ros2 pkg prefix brin_husky_distributed
ros2 pkg prefix husky_nav2
ros2 pkg prefix hokuyo_bringup
python3 -c "import rmf_adapter, rmf_fleet_msgs, rmf_task_msgs; print('RMF runtime OK')"
bash tools/integration.bash husky profile
ip -4 route get 192.168.0.218 from 192.168.0.120
ip -4 route get 192.168.0.10
timeout 8s ros2 node list --no-daemon --spin-time 3
```

Prefix integrasi harus dari clone baru; Nav2/Hokuyo dari workspace lama yang
sudah ditinjau. Digest harus sama dengan laptop:
`20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7`.
Route laptop harus `wlp2s0`, sensor `.10` harus `enx00e04ca286d9`, source `.15`.
Jika tidak sesuai, berhenti dan laporkan; jangan menjalankan perbaikan jaringan
otomatis. DDS memilih Wi-Fi `wlp2s0`, peer laptop `.218`.

Pastikan tidak ada Nav2/AMCL/map server, driver Hokuyo atau adapter duplikat.
Jangan menjalankan `hardware.launch.py` monolitik atau simulasi bersama jalur ini.
Beberapa publisher pada `/tf` tidak otomatis berarti konflik; yang harus
ditinjau adalah lebih dari satu otoritas untuk edge/child frame yang sama.

## 3. Hubungan tahap A–G dengan terminal laptop dan Husky

Tahap berikut memakai proses yang masih hidup dari tahap sebelumnya. Misalnya,
L1 core yang dimulai pada A tetap hidup selama B–F; H2 Nav2 yang dimulai pada C
tetap hidup saat preflight dan adapter berjalan.

| Tahap | Laptop | Husky | Syarat untuk lanjut |
| --- | --- | --- | --- |
| **A — mulai** | **L1** menjalankan satu RMF core dengan `rviz:=true`; **L2** memeriksanya. | Siapkan **H0** dan lakukan pemeriksaan awal. | Tepat satu core, waktu nyata, profil/digest cocok. |
| **B — komunikasi tanpa gerak** | **L2** menjalankan requester DDS; **L1 tetap hidup**. | **H0** menjalankan responder DDS lalu native check. | Semua alat exit `0` dan menyatakan lulus. |
| **C — siapkan robot** | **L1 tetap hidup**; gunakan RViz yang sudah terbuka untuk observasi dan initial pose. | Kerjakan **H1 → H2**, gunakan RViz laptop untuk peran **H3**, lalu uji goal Nav2 pendek tanpa adapter. | Sensor, map, lokalisasi, Nav2, gerak dan penghentian diterima operator. |
| **D — preflight** | **L1 tetap hidup** dan tidak mengirim task. | Jalankan preflight di **H4**; setelah selesai, **H1/H2** tetap hidup. | JSON memuat `accepted: true` dan `errors: []`. |
| **E — daftar robot** | **L2** memeriksa `/fleet_states`. | Gunakan kembali **H4** untuk satu adapter dan biarkan hidup. | `HuskyA200/husky_0` terlihat dengan pose/level yang benar. |
| **F — uji task** | **L2** mengirim satu task, lalu uji cancel terpisah. | **H4/H2** dan jika perlu **H1** tetap hidup; operator menjaga E-stop. | Gerak, hasil task dan penghentian diamati secara fisik. |
| **G — Web opsional** | Setelah robot diam, hentikan adapter dan core lama; mulai **L3 API → L1 core pengganti → H4 adapter pengganti → L4 dashboard**. | Adapter pengganti di **H4** memakai URI API laptop. | Hanya satu core dan satu adapter. |

Alur minimum adalah `A → B → C → D → E → F`. Tahap G hanya dilakukan
setelah CLI/cancel diterima dan merupakan pergantian sesi. Detail perintah
laptop ada di [README laptop](../laptop/readme.md).

Hubungan prosesnya adalah:

```text
Tahap F (CLI):  L2 task → L1 core/dispatcher ↔ H4 adapter → H2 Nav2 → robot
Sensor:                                             H1 lidar → H2 Nav2
Observasi:        RViz L1 (atau H3 terpisah); L2/H0 memeriksa status

Tahap G (Web):  L4 dashboard → L3 API → L1 core ↔ H4 adapter → H2 Nav2
```

L2 atau L4 tidak mengendalikan motor secara langsung. H4 menerjemahkan task
RMF menjadi action Nav2; H2 yang menangani navigasi robot. H1 menyediakan scan,
sedangkan H0 terutama untuk pemeriksaan dan observasi.

## 4. Tahap B — uji komunikasi tanpa gerak (H0)

Minta laptop menjalankan satu core (L1) dan requester DDS (L2), kemudian:

```bash
timeout --signal=INT --kill-after=3s 25s python3 tools/dds_roundtrip.py \
  --role robot --session operasional_01 --timeout 20
```

Kedua endpoint harus `passed: true` dan exit 0. Session harus sama dengan
laptop; tidak ada task, kontrol atau sensor yang dipublikasikan oleh alat ini.
Lalu, dengan core laptop masih berjalan:

```bash
timeout --signal=INT --kill-after=3s 25s python3 tools/native_adapter_check.py
timeout 8s ros2 topic echo /brin_hardware/profile_digest std_msgs/msg/String \
  --once --qos-durability transient_local --qos-reliability reliable
```

Native check harus `native_adapter_connected_to_schedule: true` dan exit 0.
Crash/timeout setelah mencetak sukses tetap gagal. Alat ini tidak membuat
robot/fleet palsu, tidak menyalakan background adapter dispatch, dan bukan
bukti bahwa robot sudah bisa menerima task fisik.

## 5. Tahap C — H1: periksa sensor/platform, baru aktifkan yang belum berjalan

Bagian berikut membutuhkan izin operator untuk aktivasi runtime. Tidak ada
alasan mengubah konfigurasi sensor. Pertama baca kondisi yang sudah ada di H1.
Jika akhirnya driver perlu dijalankan, H1 berubah menjadi terminal foreground
driver dan pemeriksaan berikutnya dilakukan dari H0:

```bash
timeout 8s ros2 topic info /a200_1060/scan --verbose
timeout 8s ros2 topic echo /a200_1060/sensors/imu_0/data sensor_msgs/msg/Imu \
  --once --field header --qos-reliability best_effort
timeout 8s ros2 topic echo /a200_1060/platform/odom/filtered nav_msgs/msg/Odometry \
  --once --field header --qos-reliability best_effort
timeout 15s env -u CYCLONEDDS_URI RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  ros2 service call /a200_1060/controller_manager/list_controllers \
  controller_manager_msgs/srv/ListControllers '{}'
```

Controller `joint_state_broadcaster` dan `platform_velocity_controller` harus
aktif. Service Clearpath memakai Fast DDS; klien Cyclone pada terminal H0
dapat melihat service tetapi tidak menerima responsnya. Override di atas
hanya berlaku untuk proses pemeriksaan. IMU/odom harus nyata dan segar;
bukan hanya nama topic tersedia.
Jika data/platform hilang, hentikan uji dan diagnosis; jangan restart service
Clearpath, UM7 atau controller tanpa tinjauan terpisah.

Jika scan sudah memiliki satu publisher yang mengirim data, **jangan**
menjalankan driver lagi. Jika belum ada publisher dan operator menyetujui,
jalankan satu driver yang sudah terbukti bekerja, di H1 dan biarkan hidup:

```bash
ros2 launch hokuyo_bringup hokuyo_bringup.launch.py
```

Tidak menambah argumen IP/port/protokol atau mengedit parameternya. Pada log
uji sebelumnya driver mengenali `L2201993` dan `Streaming data`. Di H0:

```bash
timeout 8s ros2 topic echo /a200_1060/scan sensor_msgs/msg/LaserScan \
  --once --field header --qos-reliability best_effort
```

Gunakan satu driver saja. Jika scan hilang, jangan menutupinya dengan scan
simulasi atau mengubah API Hokuyo. Berhenti dan laporkan.

## 6. Tahap C — H2: Nav2 dan lokalisasi, sebelum fleet adapter

Jika satu Nav2 yang benar sudah berjalan, jangan launch lagi. Di H2, periksa:

```bash
timeout 8s ros2 lifecycle get /a200_1060/amcl
timeout 8s ros2 lifecycle get /a200_1060/controller_server
timeout 8s ros2 lifecycle get /a200_1060/bt_navigator
timeout 8s ros2 action info /a200_1060/navigate_to_pose
```

Harus lifecycle `active` dan satu server NavigateToPose. Node terdaftar atau
action bernama sama saja tidak cukup. Jika belum berjalan, operator dapat
menjalankan konfigurasi Nav2 yang sudah ditinjau di H2, setelah H1 siap:

```bash
RMF_NAV_MAP="$(ros2 pkg prefix brin_rmf_maps)/share/brin_rmf_maps/maps/banyak_simpangan.yaml"
test -f "$RMF_NAV_MAP"
ros2 launch husky_nav2 navigation.launch.py \
  map:="$RMF_NAV_MAP" use_sim_time:=false start_hokuyo:=false
```

Jika file tidak ada, jangan lanjut. Ini memakai map bundle profil yang sama,
tanpa mengedit parameter Nav2. `start_hokuyo:=false` wajib karena driver H1
sudah hidup. Launch ini memulai EKF navigasi terpisah, map server, AMCL,
relay roda dan Nav2; **bukan** pengganti EKF Clearpath. Jangan jalankan SLAM
atau stack navigasi kedua. Manajer navigasi memiliki penundaan sekitar 12 detik;
tetap tunggu readiness, bukan hanya hitungan waktu.

### H3 — RViz, initial pose dan observasi

Pilihan utama adalah memakai RViz laptop yang dibuka bersama core pada
tahap A. Perintah berikut dijalankan **di laptop**, bukan di terminal Husky:

```bash
cd /mnt/UbuntuData/rmf-integration
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan rviz:=true
```

Jika core di laptop sudah hidup, jangan jalankan core kedua. Bila core itu
belum menyertakan visualisasi, operator laptop dapat menjalankan satu
`ros2 launch brin_husky_distributed visualization.launch.py` pada terminal
tambahan yang telah disiapkan sesuai README laptop. Dengan pilihan ini,
tidak perlu menjalankan tiga visualizer atau menambah display secara manual.
H3 adalah peran observasi; tidak harus berupa terminal GUI di robot.

Preset laptop menampilkan peta `/a200_1060/map`, scan `/a200_1060/scan`,
model Husky, jalur Nav2, `/map_markers`, `/fleet_markers` dan
`/schedule_markers`. Fixed frame tetap `map`, lantai RMF `L1`, dan waktu
nyata. RViz membaca `/a200_1060/nav/tf` serta `/a200_1060/tf_static`, sama
dengan RViz navigasi yang sudah dipakai; tidak menambah publisher TF.

| Tahap | Tampilan yang diharapkan |
| --- | --- |
| A–B, sensor/Nav2 belum aktif | RViz terbuka; layer yang belum memiliki data dapat kosong |
| C, sensor/Nav2 dan AMCL siap | Peta, scan dan pose dapat diperiksa; operator memberi initial pose |
| E, adapter memublikasikan graph dan robot terdaftar | Lane/waypoint serta posisi fleet muncul |
| F, task memiliki itinerary/jalur | Schedule marker dan jalur Nav2 tersedia sesuai data perencanaan |

Jika memilih GUI lokal di Husky, gunakan RViz yang sudah dikonfigurasi untuk
Nav2 dan tersedia pada instalasi robot:

```bash
ros2 launch husky_nav2 rviz.launch.py
```

Jangan mengasumsikan GUI muncul dari SSH tanpa display. Untuk pilihan GUI
Husky saja, laptop dapat mempertahankan core tanpa `rviz:=true` dan menjalankan
`visualization.launch.py rviz:=false` agar marker RMF tetap dipublikasikan
tanpa membuka GUI laptop. Jangan membuat dua set visualizer. Paket visualizer
tetap memakai runtime laptop; tidak perlu dipasang di robot untuk alur ini.
Preset laptop menyediakan `2D Pose Estimate` untuk initial pose; uji goal
Nav2 tetap memakai UI pengiriman goal yang sudah diverifikasi operator.

Operator mengisi **2D Pose Estimate** sesuai posisi dan arah fisik robot;
jangan memakai koordinat tebakan atau TF statik palsu. Pastikan scan sejajar
dengan dinding dan pose stabil. Jika RViz laptop tidak menerima data, jangan
lanjut tanpa observasi lokal robot yang dapat dipercaya.

Pemeriksaan TF navigasi baca-saja (exit timeout 124 wajar untuk observer):

```bash
timeout 8s ros2 run tf2_ros tf2_echo map base_link --ros-args \
  -r /tf:=/a200_1060/nav/tf -r /tf_static:=/a200_1060/tf_static
timeout 8s ros2 param get /a200_1060/bt_navigator use_sim_time
```

Waktu harus `False`. Sebelum uji RMF, lakukan satu uji goal Nav2 pendek
**tanpa adapter**, menggunakan UI Nav2 yang telah diverifikasi operator dan
tujuan bebas rintangan yang benar. Siapkan E-stop, amati gerak nyata, hasil
SUCCEEDED dan kemampuan berhenti. Panduan ini sengaja tidak memberi koordinat
goal universal: koordinat harus dipilih dari peta/lokasi fisik. Bila uji gagal,
jangan menyalakan dispatch RMF untuk mencoba mengatasinya.

## 7. Tahap D — H4: preflight integrasi tanpa dispatch

L1 laptop tetap berjalan. Semua task/goal uji Nav2 harus sudah selesai dan
robot diam. Bagian ini mengaktifkan bridge TF integrasi `husky_0`; lakukan
setelah aktivasi bridge disetujui operator. Jangan menjalankan bridge tambahan.

```bash
timeout --signal=INT --kill-after=5s 210s bash tools/integration.bash husky preflight \
  traffic_profile:=banyak_simpangan
```

Default preflight menunggu maksimal 180 detik. Cari JSON:

```json
{"accepted": true, "errors": []}
```

Ada field lain pada laporan nyata. Jangan menilai dari exit code launch saja.
Pastikan bridge juga berhenti bersih setelah preflight tanpa dispatch; jika
bridge melempar exception saat shutdown, tangani penyebabnya sebelum
menyatakan sesi siap untuk adapter.
Gate memeriksa core tunggal, digest, map, data sensor/TF segar, controller,
lokalisasi dekat graph, action dan lifecycle Nav2. Jangan bypass error atau
mengarang pose agar lulus. Preflight selesai lalu launch/bridge sesi ini
berhenti; Nav2 H2 dan driver H1 tetap berjalan terpisah.
Build preflight khusus Husky yang sudah dideploy memuat `controller_probe_rmw`
untuk memeriksa controller lewat proses Fast DDS terpisah; proses utama
tetap memakai Cyclone DDS. Pertahankan perubahan khusus robot tersebut
saat memperbarui source dan build.

## 8. Tahap E–F — H4: aktifkan satu fleet adapter, DAPAT MENERIMA TASK

Lakukan hanya setelah preflight dan uji Nav2 fisik diterima. Koordinasikan
dengan laptop: tidak boleh ada task tertunda yang tidak diketahui. Operator
siap pada joystick/E-stop. Jangan jalankan preflight/adapter sesi lain bersamaan.

```bash
BRIN_ENABLE_DISPATCH=1 bash tools/integration.bash husky adapter \
  traffic_profile:=banyak_simpangan
```

Flag adalah izin operator untuk sesi ini, bukan bypass: preflight diulang.
Skrip tetap tidak menyalakan Nav2/Hokuyo otomatis. Tunggu log
`Registered husky_0 in HuskyA200`. Minta laptop memeriksa `/fleet_states`
berisi robot, level dan pose sebenarnya. Setelah itu saja laptop mengirim
satu task uji menurut README laptop. Pantau hasil action dan gerak nyata;
respons request diterima belum berarti task selesai.

Pada build Husky yang sudah dideploy, adapter hardware menonaktifkan
responsive wait dan menahan jalur yang belum memiliki task ID dari
`/fleet_states`. Sesudah registrasi harus ada log
`responsive wait disabled; Nav2 paths require an active RMF task ID`.
Log `blocked RMF path without an active task ID` dapat muncul untuk jalur
idle awal; jalur tersebut tidak diteruskan ke Nav2. Setelah task ID baru
diterima, adapter meminta jalur baru dan membuang jalur dari task sebelumnya.

Uji pertama adalah registrasi tanpa task: pastikan `task_id` kosong,
robot tetap diam dan tidak muncul goal Nav2 baru. Task yang sudah antre
tetap dapat dijalankan setelah task ID diterima. Responsive wait yang mati
juga menghilangkan manuver mengalah otomatis saat idle; representasi robot
idle di schedule perlu ditinjau sebelum multi-robot.

Jika fleet terlihat tetapi `robots: []`, periksa
`ros2 node info /brin_husky_fleet_adapter`. Action Clients harus menunjuk
`/a200_1060/navigate_to_pose` dan `/a200_1060/backup`. Pada build Humble
Husky yang sudah dideploy, adapter menyelesaikan remap nama dasar sebelum
membuat ActionClient; nama RMF dan frame hasil bridge tetap memakai
`husky_0`. Source Python tertaut yang diperbarui baru dibaca oleh proses
adapter berikutnya. Jangan menyalakan adapter kedua untuk memuat perubahan.

Untuk observasi H0 (tanpa mengirim goal):

```bash
timeout 8s ros2 topic echo /fleet_states rmf_fleet_msgs/msg/FleetState --once
timeout 8s ros2 topic echo /a200_1060/navigate_to_pose/_action/status \
  action_msgs/msg/GoalStatusArray --once
```

Pembatalan task RMF dilakukan dari laptop memakai ID task yang benar, bukan
request ID. Jika gerak tidak aman, E-stop fisik didahulukan. Jangan menunggu
SSH atau cancel jaringan sebagai satu-satunya jalur penghentian.

## 9. Tahap G (opsional) — sesi RMF Web

Lakukan setelah task CLI dan cancel diterima. Selesaikan task, pastikan diam,
Ctrl-C adapter lama di H4, dan koordinasikan pergantian core laptop agar tidak
ada core/adapter ganda. Tunggu laptop menyelesaikan urutan **L3 API → L1 core
pengganti**. Kemudian gunakan kembali H4 untuk adapter pengganti berikut; baru
setelah robot terdaftar laptop menjalankan L4 dashboard:

```bash
export BRIN_LAPTOP_IP=192.168.0.218
BRIN_ENABLE_DISPATCH=1 bash tools/integration.bash husky adapter \
  traffic_profile:=banyak_simpangan \
  server_uri:="ws://$BRIN_LAPTOP_IP:8000/_internal"
```

Jangan gunakan localhost/127.0.0.1 pada Husky: API berada di laptop. Robot
tidak membutuhkan instalasi API/dashboard. Preflight tetap berlaku dan Web
bukan bukti goal selesai. Penerimaan browser dikoordinasikan di README laptop.

## 10. Penghentian dan kegagalan

1. Minta laptop berhenti mengirim task. Batalkan task aktif bila aman dan
   konfirmasi robot diam. Jika tidak aman, gunakan E-stop lebih dahulu.
2. Ctrl-C adapter H4; pastikan tidak ada goal/task aktif sebelum melanjutkan.
3. Hentikan H3/H2/H1 hanya bila proses itu memang dimulai untuk sesi ini dan
   operator menyetujuinya. Jangan menutup service yang dipakai proses lain.
   Jika peran H3 dipenuhi RViz dalam launch core laptop, tidak ada proses H3
   di robot yang perlu dihentikan.
4. Laptop menghentikan Web/API/core beserta visualisasinya terakhir.
   Clearpath, UM7 dan SSH dibiarkan berjalan; jangan restart controller
   atau NetworkManager.
5. Jangan melepas E-stop sebelum antrean task, goal dan sumber perintah aman.

| Gejala | Tindakan aman |
| --- | --- |
| `No module named rmf_adapter` | Periksa sourcing/runtime yang sudah dipasang; jangan rebuild driver |
| `No scan` | Periksa satu driver yang bekerja dan pesan nyata; jangan ubah API/IP/port Hokuyo |
| Lifecycle/action tidak siap | Tinjau Nav2/AMCL/initial pose dan log; jangan mengirim task |
| TF conflict/stale/map berbeda | Hentikan tahap gerak, tinjau authority, jam dan map; jangan membuat TF/pose palsu |
| Preflight gagal | Simpan JSON `errors`; jangan mengaktifkan bypass atau adapter kedua |
| Fleet/lane marker belum muncul | Periksa `/fleet_states` dan `/nav_graphs` sesudah adapter tahap E; layer dapat kosong sebelum ada data |
| RViz laptop tidak melihat peta/scan | Periksa H1/H2, environment dan TF navigasi yang sudah ada; jangan membuat bridge atau TF statik tambahan |
| SSH timeout | Periksa lokal; SSH putus tidak berarti robot berhenti. Jangan ubah route saat robot bergerak |
| Goal/cancel tidak sesuai harapan | E-stop jika perlu, simpan ID task dan log, jangan retry membabi buta |

Simpan commit, digest, waktu uji, laporan preflight, ID task, hasil action,
pose awal/akhir, hasil cancel dan observasi fisik. Tandai setiap tahap
LULUS/GAGAL/BELUM DIUJI. Log integrasi ada di `husky/log/ros`; jangan upload
password, key, database operasional atau rekaman sensor ke GitHub.

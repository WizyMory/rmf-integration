# Devi — bringup gedungWS_0 dan registrasi ke core RMF laptop

Workspace integrasi: **`/home/devi/rmf-integration`**. Underlay driver/Nav2:
**`/home/devi/devi_ws`**. SSH: `devi@192.168.0.237`, ROS 2 Humble.
Panduan dua robot: [README laptop](../laptop/readme.md).

Bringup integrasi menjalankan driver/sensor dari launch Devi yang sudah ada,
AMCL, Nav2, penghubung peta/initial pose, relay visualisasi read-only, dan
supervisor satu fleet adapter.
Profil bersama **`gedungWS_0`**, lantai **`L1`**, fleet **`Devi`**, robot **`devi`**.
Laptop tetap menjalankan satu core RMF untuk Devi dan Husky.

Operator mengonfirmasi pada 3 November 2026: footprint **radius 0,55 m**
(diameter 1,10 m), serta uji Nav2, cancel, kendali manual dan E-stop berhasil.
Mulai 4 November 2026, AMCL memakai **auto initial pose** pada peta
`gedungWS_0`: frame `map`, **x=19.423, y=-28.2408, z=0, yaw=1.83415 rad**,
sesuai koordinat parkir yang diberikan operator. Robot perlu berada di lokasi
dan arah parkir tersebut ketika bringup dimulai. Koreksi manual melalui
2D Pose Estimate tetap tersedia jika posisi awal berbeda.

## 1. Cara kerja

| Proses | Domain / middleware |
| --- | --- |
| Core RMF laptop dan adapter Devi | `0` / Cyclone DDS |
| Driver, sensor, AMCL dan Nav2 Devi | `73` / Fast DDS |
| Penghubung lokal di Devi | Proses terpisah, komunikasi melalui Pipe privat |

Nav2 tetap memakai domain `73`. Bridge meneruskan peta aktual `/map`
ke **`/devi/map`** pada domain `0`, serta initial pose manual dari
**`/devi/initialpose`** pada domain `0` ke `/initialpose` pada domain `73`.
Bridge ini tidak mengirim goal navigasi atau kecepatan dan tidak menerbitkan TF.

Proses RMF memakai [cyclonedds_rmf.xml](src/brin_devi_fleet_adapter/config/cyclonedds_rmf.xml):
interface `wlo1`, ParticipantIndex `auto`, peer laptop `192.168.0.218` dan
Husky `192.168.0.120`. Profil laptop juga mencantumkan peer Devi
`192.168.0.237`. Ini menyediakan discovery unicast setelah reboot.
Helper memasang `CYCLONEDDS_URI` hanya bagi proses Cyclone domain `0`;
Nav2 domain `73` tetap Fast DDS. Penerapan perubahan DDS ini disetujui
operator pada sesi pemulihan initial pose 3 November 2026.

Urutan setelah service terpasang:

1. Devi menyala → satu bringup hardware/Nav2 berjalan; AMCL menerapkan pose parkir otomatis.
2. Laptop menjalankan core `gedungWS_0` dan RViz.
3. Operator memeriksa lokalisasi Devi pada peta; 2D Pose Estimate tidak diperlukan bila pose awal sesuai.
4. Supervisor mengulang preflight sampai lokalisasi, lifecycle Nav2, profil
   dan core siap, lalu menjalankan satu adapter.
5. `/fleet_states` memuat `Devi/devi`; RViz menampilkan marker posisi Devi.

Core boleh dinyalakan sesudah Devi; auto pose AMCL tidak menunggu core.
Menunggu core atau lokalisasi tidak mematikan Nav2. Registrasi tidak memerintahkan robot berjalan; tugas berasal
dari RMF. Kehadiran marker sebelum lokalisasi benar tidak dijanjikan.

## 2. Build sekali setelah pembaruan kode

Di terminal Devi:

```bash
cd /home/devi/rmf-integration
python3 devi/verify_underlay.py
bash tools/devi.bash build
bash tools/devi.bash profile
```

Verifier diharapkan menunjukkan `files_checked: 10` dan
`all_original_files_unchanged: true`. Jangan menyalin arsip
`devi/reference` kembali ke underlay. Paket runtime RMF dan Cyclone DDS
telah dipasang operator pada setup sebelumnya.

## 3. Pemasangan startup otomatis — sekali saja

Setup lama mempunyai `devi_robot.service` dengan paket `devi_config` yang
tidak ditemukan, sementara desktop menjalankan `devi_autostart.sh` sendiri.
Installer berikut memasang override service dan menonaktifkan **hanya**
entry desktop lama tersebut agar stack tidak berjalan ganda. Source dan
konfigurasi asli `devi_ws`, script desktop lama, serta service platform lain
tetap tersedia. Backup dibuat di `devi/log/service_backup_<waktu>`.

Setelah build berhasil, jalankan di terminal robot; password sudo dimasukkan
langsung di terminal tersebut:

```bash
cd /home/devi/rmf-integration
sudo bash devi/systemd/install.bash
```

Installer memasang dan mengaktifkan service untuk boot, tetapi **belum
menjalankannya**. Hentikan bringup lama dengan **Ctrl-C di terminal
“DEVI bringup”**, tunggu driver/Nav2 lama berhenti, lalu:

```bash
sudo systemctl start devi_robot.service
systemctl status devi_robot.service --no-pager
journalctl -u devi_robot.service -n 100 --no-pager
```

Untuk melihat hanya boot saat ini tanpa log shutdown boot sebelumnya:

```bash
journalctl -b -u devi_robot.service -n 100 --no-pager -l
```

Skrip tunggu memakai alias **`/dev/Roboteq`** sesuai parameter driver dan
udev yang sudah bekerja, serta `/dev/rplidar`. Alias lama `/dev/tty-ROBOTEQ`
tidak digunakan driver; warning untuk nama itu tidak berarti motor controller
terputus. Konfirmasi koneksi memakai log driver, bukan status service saja.

Pada boot berikutnya service berjalan otomatis tanpa login desktop.
Jangan menjalankan `devi_autostart.sh`, bringup asli, atau adapter manual
bersamaan dengan service ini. Service baru belum terbukti aktif hanya karena
file installer tersedia; periksa `active (running)` dan log prosesnya.

Service juga memakai koneksi Web otomatis dari
[bringup.yaml](src/brin_devi_fleet_adapter/config/bringup.yaml):

```yaml
server_uri: ws://192.168.0.218:8000/_internal
```

Saat Devi menyala, Nav2 dan auto pose berjalan, supervisor menunggu core
RMF, lalu adapter terhubung ke Web API laptop. Client WebSocket mencoba
koneksi ulang bila API belum tersedia atau koneksinya terputus. Laptop
tetap perlu menjalankan API, core RMF dan dashboard menurut bagian 9
[README laptop](../laptop/readme.md). Tidak perlu lagi memulai bringup Web
manual di Devi untuk operasi harian.

Untuk beralih sekali dari sesi Web foreground yang lama, parkirkan robot
di lokasi auto pose, hentikan terminal bringup manual dengan **Ctrl-C** dan
tunggu seluruh prosesnya berhenti. Kemudian di terminal Devi:

```bash
sudo systemctl enable --now devi_robot.service
systemctl status devi_robot.service --no-pager -l
journalctl -b -u devi_robot.service -n 100 --no-pager -l
```

Cari log `Registered devi in Devi` dan
`BroadcastClient successfully connected` dengan URI laptop. Koneksi Web
dapat diperiksa di `http://192.168.0.218:8000/fleets/Devi/state`.
Jika IP laptop berubah, perbarui `server_uri` pada konfigurasi dan restart
service setelah robot diam di titik parkir.

Untuk menonaktifkan koneksi Web pada startup, isi `server_uri: ""` pada
konfigurasi dan restart service. Nav2/preflight tetap berjalan seperti biasa.

Untuk diagnosis foreground **hanya ketika service dan bringup lama berhenti**:

```bash
cd /home/devi/rmf-integration
bash tools/devi.bash bringup rviz:=false
```

Perintah ini menjalankan stack yang sama. `rviz:=true` membuka RViz lokal
Devi pada domain `73`; tool initial pose lokal memakai `/initialpose`.
Alamat Web bawaan diambil dari `bringup.yaml`; argumen `server_uri:=ws://...`
dapat dipakai untuk mengganti alamat pada satu sesi foreground.

Keyboard teleop lama memakai `pynput`/X11. Saat boot tanpa desktop, node itu
keluar karena tidak ada `DISPLAY`; driver, joystick dan twist mux tetap
berjalan. Jika perlu kendali keyboard, buka terminal **di desktop Devi**
setelah login dan jalankan node aslinya dengan environment D0 bagian 5:

```bash
ros2 run devi_teleop teleop_key_node --ros-args \
  -r __node:=teleop_key_node -r /key_vel:=/devi/cmd_vel_key
```

Jangan menjalankan keyboard kedua jika sudah ada. Prosedur kendali manual
dan E-stop tetap mengikuti penerimaan operator; node keyboard desktop ini
tidak diperlukan untuk start Nav2 atau registrasi RMF.

## 4. Laptop: core dan pemeriksaan pose otomatis

Build overlay laptop setelah pembaruan kode ini, kemudian mulai tepat satu
core. Jika core profil yang sama sudah aktif, gunakan core itu.

```bash
cd /mnt/UbuntuData/rmf-integration
bash tools/integration.bash laptop build
bash tools/integration.bash laptop core traffic_profile:=gedungWS_0 rviz:=true
```

Preset bawaan `gedungWS_0` adalah `devi_rmf.rviz`. Fixed Frame **`map`**,
display **Shared gedungWS_0 map from Devi** memakai `/devi/map`.
AMCL memakai pose parkir otomatis saat aktif. Periksa bahwa lokasi dan arah
robot pada peta sesuai posisi fisik dan scan. Jika perlu koreksi, gunakan
**2D Pose Estimate**, klik lokasi fisik dan tarik arah hadapnya. Pada preset
ini tool tersebut mengirim ke **`/devi/initialpose`**. Pose manual ini hanya
mengoreksi sesi yang berjalan; startup berikutnya kembali memakai pose parkir.

Untuk menginisialisasi **Husky**, ubah **Tool Properties → 2D Pose Estimate
→ Topic → Value** menjadi `/a200_1060/initialpose`, atau gunakan preset
`husky_rmf.rviz`. Kembalikan ke `/devi/initialpose` sebelum klik untuk Devi.
Tool **2D Nav Goal** lama adalah milik Husky; gunakan task RMF untuk Devi.

Devi tampil sebagai marker fleet (nama, posisi dan arah), radius **0,55 m**.
Preset mempunyai grup **Devi sensors and Nav2** dan **Husky sensors and Nav2**.
Grup Devi menampilkan model robot, filtered laser, kedua costmap, footprint,
pose/covariance AMCL, partikel dan jalur Nav2. Raw laser, received plan dan
jejak odometri tersedia sebagai display opsional yang dapat dicentang.

Relay visualisasi hanya berlangganan data domain `73`, kemudian meneruskannya
ke domain `0` pada `/devi/viz/*`. Frame pengamatan mendapat awalan `devi/`,
misalnya `devi/odom`, `devi/base_link`, `devi/rplidar_link`; frame `map`
tetap dipakai bersama. Koordinat, isi sensor dan timestamp asli dipertahankan.
TF/sensor yang dipakai controller di domain `73` tidak diubah.

| Tampilan | Topic laptop domain 0 |
| --- | --- |
| Semua fleet terdaftar | `/fleet_markers` dari `/fleet_states` |
| Laser filtered / raw | `/devi/viz/scan`, `/devi/viz/scan_raw` |
| Global / local costmap | `/devi/viz/global_costmap/costmap`, `/devi/viz/local_costmap/costmap` |
| Footprint | `/devi/viz/global_costmap/footprint`, `/devi/viz/local_costmap/footprint` |
| Pose / partikel AMCL | `/devi/viz/amcl_pose`, `/devi/viz/particle_cloud` |
| Plan global / local / smoothed | `/devi/viz/plan`, `/devi/viz/local_plan`, `/devi/viz/plan_smoothed` |
| Odometri / model robot | `/devi/viz/odometry`, `/devi/viz/robot_description` |
| TF khusus RViz, kedua robot | `/rmf_visualization/tf`, `/rmf_visualization/tf_static` |

Map `/devi/map` tetap diteruskan oleh bridge initial pose yang sudah ada.
Costmap Nav2 Devi mengirim snapshot penuh; relay memakai snapshot tersebut.
Jalur plan baru muncul setelah Nav2 menerbitkan plan untuk navigasi, bukan
setiap kali initial pose diberikan. Marker fleet baru muncul setelah adapter
benar-benar mendaftarkan robot; scan/costmap dapat tampil lebih dahulu.

Jika hanya ingin membuka ulang RViz dengan core versi baru tetap aktif,
tutup RViz lama lalu jalankan **di laptop**:

```bash
cd /mnt/UbuntuData/rmf-integration
bash tools/integration.bash laptop view
```

Perintah `view` memakai visualizer dan node TF yang sudah dimulai core;
tidak memulai core, adapter, Nav2 atau node visualizer kedua.

## 5. Pemeriksaan dan bukti registrasi

Di Devi, sementara service dan core hidup:

```bash
cd /home/devi/rmf-integration
bash tools/devi.bash inspect
bash tools/devi.bash preflight
journalctl -u devi_robot.service -n 150 --no-pager
```

Pada beberapa detik awal, AMCL menunggu map, scan dan odometri. Sesudah
lokalisasi otomatis dan core siap, hasil yang diperlukan:
**`nav2_ready: true`, `accepted: true`, `errors: []`**, lalu log
**`Registered devi in Devi`**. Pose harus dekat graph RMF; pemberian pose
jauh dari graph tidak memaksa registrasi. Baca JSON preflight; exit launch
sendiri tidak membuktikan penerimaan. Jangan memulai adapter kedua.
Field `robot_registered: false` pada JSON preflight menunjukkan pemeriksaan
itu tidak mendaftarkan robot. Bukti registrasi berasal dari log adapter dan
`/fleet_states`, bukan field tersebut.

Di terminal ROS laptop yang environment domain `0`-nya sudah disiapkan
menurut README laptop:

```bash
timeout 20s ros2 topic echo /fleet_states rmf_fleet_msgs/msg/FleetState
timeout 8s ros2 param get /brin_devi_fleet_adapter use_sim_time
```

Cari `name: Devi`, robot `devi`, lantai `L1`, pose sesuai dan waktu `False`.
Husky muncul dalam pesan fleet `HuskyA200` yang terpisah. `--once` bisa hanya
mengambil salah satunya; exit `124` monitor berarti durasi pengamatan habis.

Untuk pemeriksaan Nav2 asli di terminal **D0**:

```bash
source /opt/ros/humble/setup.bash
source /home/devi/devi_ws/install/local_setup.bash
export ROS_DOMAIN_ID=73 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 param get /map_server yaml_filename
ros2 param get /amcl set_initial_pose
ros2 param get /amcl always_reset_initial_pose
ros2 param get /amcl initial_pose.x
ros2 param get /amcl initial_pose.y
ros2 param get /amcl initial_pose.yaw
ros2 param get /local_costmap/local_costmap robot_radius
ros2 param get /global_costmap/global_costmap robot_radius
ros2 lifecycle get /bt_navigator
```

Map harus berakhir `maps/gedungWS_0_rmf.yaml`, set initial pose **True**,
reset initial pose **True**, pose `[19.423, -28.2408, 1.83415]`, kedua
radius **0.55**, navigator `active [3]`.
Pemeriksaan parameter ini tidak mengirim goal.

## 6. Konfigurasi yang dipakai

[bringup.yaml](src/brin_devi_fleet_adapter/config/bringup.yaml) mencatat radius
dan penerimaan operator. Setiap start, wrapper membaca parameter AMCL/Nav2
asli lalu menghasilkan file di **`devi/log/bringup_runtime/`**:

| File | Isi |
| --- | --- |
| `amcl.yaml` | Peta bersama, waktu nyata, initial pose parkir otomatis setiap start |
| `nav2.yaml` | Parameter Devi asli dengan kedua costmap memakai radius 0,55 m |
| `integration.yaml` | Map bersama, transformasi identitas, penerimaan operator |
| `fleet.yaml` | Fleet Devi dengan radius RMF 0,55 m |

Canonical map `gedungWS_0_rmf.yaml` memakai origin `[0, -33.65, 0]` dan
resolusi `0.05`, sama dengan bundle RMF/Husky. Karena gambar dan koordinat
map yang dipakai sama, transformasi Nav2↔RMF adalah identitas. Initial pose
tetap harus menunjukkan lokasi fisik robot dengan benar. Ini berbeda dari
file `gedungWS_0.yaml` dengan origin SLAM asli.

Digest profil bersama:

```text
ff44d7a33b01732e6c277b523c40ae5c7ef6c011dab83b259e5db44daef9f221
```

Helper `inspect`, `preflight` dan adapter manual memilih file runtime di
atas bila tersedia. File dasar `config/devi.yaml` dan `fleet_config.yaml`
tetap menyimpan konfigurasi setup lama `workshop_l_1` yang dispatch-nya
terkunci. Keduanya bukan konfigurasi operasional bringup baru.

## 7. Task dari laptop

Setelah registrasi dan lokalisasi diverifikasi, buka console di laptop:

```bash
bash tools/integration.bash laptop task
```

Atau pilih tujuan/robot langsung:

```bash
bash tools/integration.bash laptop task --list-waypoints
bash tools/integration.bash laptop task --robot devi --places ws_p1 --dry-run
bash tools/integration.bash laptop task --robot devi --places ws_p1
bash tools/integration.bash laptop task --bid --places ws_p1
```

`ws_p1` adalah contoh tujuan. `--dry-run` tidak mengirim task; perintah tanpa
flag itu dapat menggerakkan robot. Bidding membiarkan RMF memilih robot
yang memenuhi syarat, termasuk Husky. Respons, ID booking dan cancel ada di
bagian 7 [README laptop](../laptop/readme.md). CLI lama
`brin_husky_hardware send_task` hanya untuk Husky.

## 8. Berhenti dan pemulihan

Selesaikan/batalkan task dan konfirmasi robot diam sebelum menghentikan
stack. Untuk menghentikan seluruh bringup Devi:

```bash
sudo systemctl stop devi_robot.service
```

Start berikutnya memakai kembali pose parkir yang dikonfigurasi. Perintah `stop` tidak
menonaktifkan startup boot; `disable` dipakai bila memang ingin membatalkannya.
Menghentikan core/SSH bukan E-stop. Hentikan core laptop terakhir setelah
operasi robot dihentikan.

Untuk kembali ke startup lama, hentikan service, pindahkan override
`/etc/systemd/system/devi_robot.service.d/rmf-integration.conf` ke backup,
jalankan `sudo systemctl daemon-reload`, dan pulihkan entry desktop dari
backup installer. Jangan menjalankan desktop lama dan service baru bersamaan.
Source underlay tidak perlu dipulihkan karena tidak ditimpa.

| Gejala | Periksa |
| --- | --- |
| Map tidak muncul di laptop | Service, node `devi_initial_pose_bridge`, `/devi/map` domain `0` |
| Menunggu AMCL/TF | Parameter `set_initial_pose`, `initial_pose.*`, map/scan/odom; koreksi manual bila lokasi fisik berbeda |
| Husky menerima initial pose, Devi tidak | Periksa topic tool RViz yang sedang dipilih; target Devi harus `/devi/initialpose`, target Husky `/a200_1060/initialpose` |
| Digest kosong padahal core laptop aktif | Periksa kedua sisi memuat profil DDS unicast; restart proses yang belum memuat perubahan, lalu uji koneksi dua arah |
| `accepted: false` | JSON `errors`, core tunggal, digest, lifecycle, kedekatan graph |
| Radius/map lama | Service/launch lama masih berjalan atau wrapper baru belum aktif |
| Fleet ada, marker belum ada | Display `/fleet_markers`, visualizer, Fixed Frame `map` dan lantai `L1` |
| Laser/costmap ada, tetapi tidak tergambar | Grup Devi aktif; TF `/rmf_visualization/tf*`, frame `devi/*` dan Fixed Frame `map` |
| Preflight lulus, adapter terus mencoba | Cari error launch pada journal; supervisor terbaru menghilangkan argumen `server_uri` bila kosong |
| Service `devi_config` gagal | Override baru belum dipasang/reload oleh installer |

`ros2 topic list` hanya membuktikan endpoint terdaftar, bukan bahwa pesan
AMCL sudah diterima. Preflight exit `2` menyatakan syarat belum terpenuhi.
Jika AMCL dan map→base_link belum tersedia, beberapa lifecycle Nav2 masih
menunggu lokalisasi. Untuk koreksi manual dari laptop, klik untuk Devi hanya setelah topic
tool diperiksa; penggantian target ke Husky dalam sesi RViz tetap berlaku
sampai operator menggantinya kembali.

Untuk kembali ke mode manual, ubah `localization: manual_initial_pose` pada
[bringup.yaml](src/brin_devi_fleet_adapter/config/bringup.yaml), lalu restart
service setelah robot diam. Wrapper akan membuat `set_initial_pose: false`
dan menghapus pose awal dari parameter AMCL runtime. Nilai auto pose tersimpan
di source dan dapat dipakai lagi dengan `localization: automatic_initial_pose`.

Nilai baterai/mekanis fleet masih perkiraan; battery drain dan perjalanan
charger otomatis dinonaktifkan. Responsive wait dan recovery mundur adapter
tetap dinonaktifkan. Web/telemetry dan traffic fisik bersama belum diuji
end-to-end. [Hasil setup awal](SETUP_RESULT_2026-11-02.md) adalah catatan
historis sebelum perubahan bringup ini.

[Pemulihan initial pose dan DDS](INITIAL_POSE_RECOVERY_2026-11-03.md)
mencatat penerimaan pose AMCL, preflight lulus, registrasi Devi, dan kedua
fleet yang teramati di laptop setelah profil DDS permanen diterapkan.

[Auto pose 4 November](AUTO_POSE_RESULT_2026-11-04.md) mencatat implementasi
pose parkir otomatis yang menggantikan kebutuhan initial pose manual Devi.
[Web otomatis saat boot](WEB_BOOT_RESULT_2026-11-04.md) mencatat alamat API
bawaan, hasil pengujian, dan aktivasi service untuk koneksi Web permanen.

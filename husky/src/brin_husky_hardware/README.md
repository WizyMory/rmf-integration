# Integrasi satu Husky A200 fisik dengan BRIN RMF

> Untuk arsitektur terbaru dengan **RMF pusat di laptop** dan **Nav2 serta
> fleet adapter di Husky**, gunakan
> `src/brin_husky_distributed/README.md` dan launch paket
> `brin_husky_distributed`. Instruksi di bawah adalah jalur satu-komputer
> sebelumnya; jangan jalankan kedua jalur bersamaan.

Panduan ini untuk Husky fisik `a200_1060` di area BRIN lantai `L1`. Di RMF,
robot tersebut bernama `husky_0`. Laptop menjalankan RMF, jembatan TF, dan
preflight; Husky tetap menjalankan driver Clearpath, satu map server, AMCL,
dan Nav2 miliknya sendiri. Paket ini **tidak** menjalankan Gazebo, Nav2 kedua,
AMCL kedua, atau map server kedua. Jangan menjalankan launch simulasi bersamaan
dalam ROS domain yang sama.

Status saat panduan ini ditulis: paket sudah dibangun dan diuji di workspace,
tetapi koneksi dan gerak robot fisik **belum** diuji dari sini. Perintah di
bawah harus dijalankan dan dicatat hasilnya oleh operator di lokasi.

## 1. Siapkan Husky fisik

Pastikan baterai cukup, area uji bebas orang/halangan, kendali manual dan
emergency stop dapat dijangkau operator, serta mekanisme penghentian motor
telah diuji sesuai prosedur keselamatan setempat. Mulai dengan batas kecepatan
rendah pada Nav2 onboard. Jangan menjadikan preflight software sebagai pengganti
uji emergency stop. Periksa juga behavior tree/recovery Nav2 onboard sebelum
memberikan goal; paket ini menonaktifkan recovery mundur otomatis milik adapter
simulasi, tetapi Nav2 onboard dapat memiliki recovery sendiri.

Pada terminal **robot**, periksa lingkungan dan komponen yang sudah hidup:

```bash
printenv ROS_DISTRO ROS_DOMAIN_ID RMW_IMPLEMENTATION
ros2 topic list
ros2 action list -t
ros2 lifecycle get /a200_1060/bt_navigator
ros2 control list_controllers -c /a200_1060/controller_manager
ros2 param get /a200_1060/map_server yaml_filename
ros2 topic echo /a200_1060/scan --once --field header
ros2 topic echo /a200_1060/platform/odom/filtered --once
ros2 topic echo /a200_1060/sensors/imu_0/data --once --field header
ros2 topic info /a200_1060/tf -v
ros2 topic info /a200_1060/nav/tf -v
ros2 topic info /a200_1060/tf_static -v
ros2 topic echo /a200_1060/platform/emergency_stop --once
```

`ros2 control list_controllers` tanpa `-c` mencari controller manager global
yang tidak ada pada robot ini dan bisa terus menunggu. Yang diperlukan ialah
`platform_velocity_controller` berstatus `active`, `bt_navigator` aktif,
action `/a200_1060/navigate_to_pose` tersedia, dan scan/odom/IMU/TF terus
terbit. Bila topik emergency stop tidak menerbitkan pesan, ikuti pemeriksaan
hardware Clearpath setempat; jangan menganggap ketiadaan pesan berarti aman.

Peta yang dimuat Nav2 harus peta okupansi BRIN L1 untuk profil rute yang akan
dipilih di laptop. Samanya lokasi fisik saja belum membuktikan peta cocok.
Periksa YAML yang dimuat map server, posisi/orientasi asal, resolusi, ukuran,
dan **isi piksel** peta melalui RViz bersama scan. Setel initial pose AMCL
sesuai posisi fisik yang benar dan pastikan pose stabil. Jangan menambah offset
adapter, menggeser koordinat graph, atau mengaktifkan `allow_unknown` secara
global untuk menutupi ketidakcocokan peta. Robot harus bisa mencapai waypoint
graf dari posisi awalnya.

## 2. Siapkan laptop sistem utama

Laptop dan Husky harus saling terjangkau pada LAN ROS 2, menggunakan ROS 2
Humble, `ROS_DOMAIN_ID=0`, `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, dan
`ROS_LOCALHOST_ONLY=0`. Sinkronkan jam laptop dan robot (misalnya dengan NTP);
preflight mensyaratkan data dan TF baru dengan batas usia 2 detik. Periksa
`CYCLONEDDS_URI` di kedua mesin: konfigurasi yang mengunci discovery hanya ke
loopback akan membuat topik robot tidak terlihat. Jangan menyunting `/opt/ros`.

Di terminal **laptop**, muat overlay yang terpasang dan bangun paket fisik:

```bash
source /opt/ros/humble/setup.bash
source /mnt/UbuntuData/clearpath_ws/install/setup.bash
source /mnt/UbuntuData/BRIN_ws/install/setup.bash
cd /mnt/UbuntuData/rmf_ws
export COLCON_HOME="$PWD/.colcon"
export ROS_LOG_DIR="$PWD/log/ros"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export COLCON_EXTENSION_BLOCKLIST=colcon_core.shell.ros_domain_id
colcon build --symlink-install --packages-select brin_husky_hardware
source install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=0
ros2 topic list | rg a200_1060
```

Jika lokasi overlay berbeda, ganti path dengan path instalasi sebenarnya.
Jalankan perintah berikutnya dari terminal yang sudah men-*source* overlay
ini. Pastikan laptop melihat topik robot sebelum memulai RMF. Bila memakai
firewall atau beberapa antarmuka jaringan, verifikasi discovery dan lalu lintas
DDS dua arah; daftar topik saja belum menjamin pesan dan action berhasil.

Periksa [`config/husky_0.yaml`](config/husky_0.yaml). Konfigurasi awal
menggunakan `/a200_1060/scan`, odometri terfilter platform, IMU, dan TF dari
`/a200_1060/tf`, `/a200_1060/nav/tf`, serta `/a200_1060/tf_static`.
Jika publisher nyata memakai topik lain, ubah **hanya** konfigurasi paket
hardware ini; jangan mengubah file simulasi. Nama frame fisik `odom`,
`base_link`, dan sensor akan disalin sebagai `husky_0/odom`,
`husky_0/base_link`, dan `husky_0/*` pada `/tf` bersama; `map` tetap global.

## 3. Jalankan preflight tanpa menggerakkan robot

Pastikan tidak ada proses RMF schedule/dispatcher/building map server lain
di domain 0. Jalankan launch dengan dispatch **mati** (nilai bawaan):

```bash
ros2 launch brin_husky_hardware hardware.launch.py traffic_profile:=brin_0
```

Launch ini menyalakan jembatan TF sementara, memeriksa robot, lalu berhenti.
Cari keluaran JSON dengan `"accepted": true` dan `"errors": []`; jangan
hanya mengandalkan exit code shell `ros2 launch`. Pemeriksaan mencakup geometri
peta terhadap profil BRIN, umur pesan scan/odom/IMU dan TF, hubungan frame
laser/IMU, kedekatan pose ke graf maksimal 1 m, controller aktif, lifecycle
Nav2, action NavigateToPose, dan tidak adanya otoritas TF/RMF ganda. Ini
**tidak** membandingkan seluruh piksel peta dan **tidak** menguji gerak motor.
Jika gagal, perbaiki penyebab yang tertulis pada `errors` dan ulangi preflight.

Profil lain hanya boleh dipilih jika peta dan rute fisik cocok dengannya:

```bash
ros2 launch brin_husky_hardware hardware.launch.py traffic_profile:=banyak_simpangan
```

Catat JSON preflight, path YAML map onboard, daftar controller, action Nav2,
publisher TF, serta peta/scan di RViz sebagai bukti. Jangan meneruskan hanya
karena terminal berhenti tanpa error yang terlihat.

## 4. Uji gerak bertahap

Pertama, tanpa RMF, gunakan RViz/Nav2 onboard untuk mengirim goal pendek yang
aman pada peta yang sama. Operator harus mengukur perpindahan nyata dari pose
atau odometri, memastikan hasil action sukses, dan menguji penghentian manual.
Goal di posisi awal saja hanya membuktikan konektivitas, bukan navigasi.

Setelah preflight lulus dan gerak Nav2 mandiri aman, mulai RMF dari **laptop**:

```bash
ros2 launch brin_husky_hardware hardware.launch.py \
  traffic_profile:=brin_0 enable_dispatch:=true
```

Launch mengulang preflight; RMF baru dinyalakan jika lolos. Biarkan terminal
ini berjalan. `server_uri` kosong secara bawaan; dashboard Web tidak diperlukan
untuk menjalankan CLI. Di terminal laptop kedua dengan overlay/env yang sama,
periksa `/fleet_states`, lalu pilih waypoint graf yang benar-benar terjangkau
dan cukup jauh untuk mengamati perpindahan. Contoh di bawah memakai `ws_p0`
**hanya jika** waypoint itu cocok dengan peta, profil, dan ruang uji:

```bash
ros2 topic echo /fleet_states --once
ros2 run brin_husky_hardware send_task --robot husky_0 --places ws_p0
```

Simpan ID task dari respons. Pantau pose TF, Nav2 action, gerak nyata, dan
status akhir RMF. Respons penerimaan task bukan bukti selesai. Untuk uji
pembatalan, kirim task yang membuat robot bergerak, kemudian batalkan
**sewaktu bergerak**:

```bash
ros2 run brin_husky_hardware send_task --cancel TASK_ID
```

Pastikan goal Nav2 berhenti, kecepatan nol, dan status RMF bukan sukses palsu.
CLI paket hardware memakai wall time; jangan memakai CLI `send_task` simulasi
yang memakai simulation time. Uji shared-route traffic hanya setelah robot
kedua diintegrasikan serta divalidasi tersendiri; paket ini baru mengaktifkan
satu Husky fisik.

Urutan penerimaan: preflight fisik lulus → gerak Nav2 mandiri → gerak task RMF
terukur → pembatalan task saat bergerak → traffic bersama. Tidak ada tahap
gerak fisik yang boleh dinyatakan lulus tanpa log dan observasi nyata.

## Jika ada masalah

| Gejala | Pemeriksaan pertama |
| --- | --- |
| Topik `a200_1060` tidak terlihat di laptop | LAN, domain 0, Cyclone DDS, `ROS_LOCALHOST_ONLY`, `CYCLONEDDS_URI`, firewall, dan jam kedua mesin. |
| `ros2 control` terus menunggu | Gunakan `-c /a200_1060/controller_manager`; pastikan controller aktif. |
| TF `map → husky_0/base_link` hilang | Cek publisher `/a200_1060/tf` dan `/a200_1060/nav/tf`, nilai `tf_topics` pada config hardware, serta lokalisasi AMCL. |
| Data/TF dinilai usang | Sinkronkan jam; cek frekuensi dan timestamp scan, odom, IMU, TF. |
| Geometri peta tidak cocok | Cocokkan map YAML/image onboard dengan profil `brin_0` atau `banyak_simpangan`; jangan membuat offset koordinat. |
| Pose terlalu jauh dari graf | Periksa initial pose AMCL, peta fisik, dan profil graf sebelum menggerakkan robot. |
| Nav2/action tidak tersedia | Cek lifecycle `bt_navigator`, action namespaced, dan log Nav2 onboard. |
| Otoritas TF/RMF ganda | Matikan instance jembatan atau RMF lain di domain yang sama; jangan menjalankan simulasi bersamaan. |

Detail arsitektur dan batas penerimaan juga ada pada
`docs/HUSKY_HARDWARE.md` dan checkpoint `IMPLEMENTATION_STATUS.md` di
checkout workspace.

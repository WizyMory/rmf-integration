# Husky fisik: RMF pusat di laptop, Nav2 dan fleet adapter di robot

Paket ini diselaraskan dengan hasil integrasi laptop dalam
`src/rmf_ws.tar.xz`. Untuk Husky fisik `a200_1060`, nama RMF-nya `husky_0`.

| Komputer | Proses yang dijalankan |
| --- | --- |
| Laptop utama | Satu RMF schedule, task dispatcher, building map server, pengumum identitas peta/graph, dan CLI task. |
| Husky | Driver Clearpath dan lidar, satu AMCL/Nav2/map server, jembatan TF fisik, preflight, serta satu fleet adapter. |

Tidak ada Gazebo atau `/clock` simulasi. `server_uri` tetap kosong kecuali
operator secara terpisah mengaktifkan RMF Web. **Jangan** menjalankan
`brin_husky_hardware hardware.launch.py` bersamaan: launch lama memulai RMF
core dan adapter pada satu mesin, sehingga akan menggandakan proses.
Putusnya koneksi laptop/DDS **tidak menjamin** goal Nav2 yang sudah diterima
berhenti; operator tetap harus siap menggunakan kendali manual/E-stop fisik.

## Siapkan kedua mesin

Keduanya harus memakai Humble, domain 0, RMW Cyclone DDS, LAN dua arah, dan
jam tersinkron (preflight membatasi usia data/TF menjadi 2 detik). Jangan
memakai konfigurasi CycloneDDS localhost dari simulasi. Pada tiap terminal:

```bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=0
printenv ROS_DISTRO ROS_DOMAIN_ID RMW_IMPLEMENTATION ROS_LOCALHOST_ONLY CYCLONEDDS_URI
```

Pastikan `/a200_1060/scan`, `/a200_1060/map`,
`/a200_1060/navigate_to_pose`, dan layanan controller manager terlihat dari
laptop. Bila topik terlihat tetapi pesan/action tidak sampai, periksa
discovery DDS, firewall, antarmuka LAN, dan sinkronisasi jam. Jangan menanam
IP atau path mesin lain dalam source.

Gunakan overlay Clearpath dan Open-RMF Humble yang benar pada masing-masing
mesin. Laptop membutuhkan `brin_rmf_maps`, `brin_husky_fleet_adapter`,
`brin_husky_hardware`, `brin_husky_distributed`, dan RMF core. Husky
membutuhkan keempat paket BRIN tersebut untuk peta/graph dan kode adapter,
serta runtime Python `rmf_adapter`; Nav2 saja tidak cukup. Arsip operator
menyertakan `husky_nav2` dan `hokuyo_bringup` pada workspace robot. Paket
tersebut tidak disalin ke source simulasi di laptop. Jika belum terpasang di
Husky, instal/build dari source robot yang telah diuji operator; jangan
menyalakan driver Hokuyo kedua bila `/a200_1060/scan` sudah ada.

Contoh pada **laptop** (sesuaikan path overlay yang nyata):

```bash
source /opt/ros/humble/setup.bash
source /mnt/UbuntuData/clearpath_ws/install/local_setup.bash
source /mnt/UbuntuData/BRIN_ws/install/local_setup.bash
cd /mnt/UbuntuData/rmf_ws
export COLCON_HOME="$PWD/.colcon" ROS_LOG_DIR="$PWD/log/ros"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export COLCON_EXTENSION_BLOCKLIST=colcon_core.shell.ros_domain_id
colcon build --symlink-install --packages-select \
  brin_rmf_maps brin_husky_fleet_adapter brin_husky_hardware brin_husky_distributed
source install/local_setup.bash
```

Pada **Husky**, source `/etc/clearpath/setup.bash`, overlay ROS/Nav2 dan
Open-RMF yang terpasang, kemudian build paket BRIN di
`/home/husky/rmf_ws`. Salinan `brin_rmf_maps` di workspace ini dapat dibangun
tanpa Ignition: plugin Gazebo hanya dibangun bila Ignition tersedia. File
peta dan graph tetap sama dengan arsip laptop. Pastikan `ros2 pkg prefix
brin_rmf_maps` berhasil di kedua mesin.

Package `brin_husky_distributed` dan preflight `brin_husky_hardware` di
workspace Husky ini telah diselaraskan dengan arsip laptop. Salin ulang kedua
package itu bila Husky lain masih memakai versi sebelumnya. Jangan menyalin
`build/`, `install/`, atau `log/`. Pada **terminal Husky**:

```bash
source /etc/clearpath/setup.bash
source /home/husky/ros2_ws/install/setup.bash
cd /home/husky/rmf_ws
source install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=0
colcon build --symlink-install --packages-select \
  brin_rmf_maps brin_husky_fleet_adapter brin_husky_hardware brin_husky_distributed
source install/setup.bash
ros2 pkg prefix brin_rmf_maps
ros2 pkg prefix brin_husky_distributed
python3 -c 'import rmf_adapter; print("RMF Python runtime tersedia")'
```

Jika overlay RMF/ROS pada Husky berada di path lain, source path yang benar
sebelum build. Artefak `build/`, `install/`, dan `log/` memuat path spesifik
mesin dan harus dibuat ulang secara lokal.

## Pilih satu profil dan periksa robot

Profil bawaan `banyak_simpangan` mengikuti Nav2 di arsip Husky. `brin_0`
boleh dipilih hanya jika map fisik yang dijalankan memang cocok. Kedua launch
membaca `brin_rmf_maps/maps/traffic_profiles.yaml` sehingga building map,
graph, dan map Nav2 berasal dari satu entri. Laptop mengumumkan SHA-256 atas
nama profil, building YAML, graph, map YAML dan PNG; preflight robot menolak
profil atau versi aset yang berbeda. **Ini belum membandingkan piksel map
server yang sedang aktif.** Periksa peta dan scan di RViz, lalu set initial
pose AMCL sesuai posisi robot sebenarnya.

Untuk aset dalam arsip ini, digest `banyak_simpangan` adalah
`20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7`;
digest `brin_0` adalah
`c011d4539511dbd02e1123b5369947916208880438c8a896e577abb2b8b92072`.
Keduanya cocok dengan file peta/graph di workspace Husky ini. Bila aset
diubah, digest akan berubah dan harus sama pada kedua mesin.

Konfigurasi TF ada di [`config/husky_0.yaml`](config/husky_0.yaml). Arsip
Nav2 operator menerbitkan TF navigasi di `/a200_1060/nav/tf`; bridge hanya
menyalin sumber ini serta `/a200_1060/tf_static` ke `/tf` bersama sebagai
`map → husky_0/odom → husky_0/base_link`. Jangan juga merelay
`/a200_1060/tf` dari EKF platform: dua penerbit `odom → base_link` dapat
menimbulkan konflik. Adapter memakai action Nav2 dan jalur kecepatan fisik
namespaced, tidak memerintah `/cmd_vel` global. Konfigurasi fleet fisik
[`config/fleet_config.yaml`](config/fleet_config.yaml) hanya memuat `husky_0`,
membatasi perencanaan kecepatan sesuai Nav2 arsip (0,20 m/s; 0,35 rad/s),
dan memakai `finishing_request: nothing` agar tidak otomatis menuju charger
yang belum divalidasi. Tinjau kembali nilai tersebut di lokasi.

## Urutan aman

1. Di laptop, jalankan satu RMF core:

   ```bash
   ros2 launch brin_husky_distributed laptop.launch.py traffic_profile:=banyak_simpangan
   ```

   Pada terminal laptop kedua, cek bahwa `/brin_hardware/profile_digest`
   menerbitkan nilai dan topic robot terlihat. Pengumuman ini bukan perintah
   gerak; preflight Husky akan mencocokkannya dengan aset lokal.

2. Di Husky, biarkan Nav2 onboard yang sudah berjalan. Cek controller dengan
   `ros2 control list_controllers -c /a200_1060/controller_manager` dan
   lifecycle dengan `ros2 lifecycle get /a200_1060/bt_navigator`.
   Jika memakai `husky_nav2` dari arsip tetapi belum hidup, pilih
   `start_nav2:=true` saat menjalankan launch di bawah. Gunakan
   `start_hokuyo:=true` **hanya** jika lidar belum memiliki publisher.

3. Dengan operator siap pada joystick/E-stop, jalankan preflight tanpa
   dispatch di Husky. Bila Nav2 sudah hidup, gunakan bawaan berikut:

   ```bash
   ros2 launch brin_husky_distributed robot.launch.py \
     traffic_profile:=banyak_simpangan enable_dispatch:=false
   ```

   Bila Nav2 belum hidup dan `husky_nav2` terpasang, tambahkan
   `start_nav2:=true` (dan `start_hokuyo:=true` hanya bila perlu). Launch
   memberi waktu 180 detik untuk map, sensor, AMCL dan action siap; kirim
   initial pose melalui RViz. Preflight memeriksa tepat satu RMF core laptop,
   identitas profil yang sama, TF/sensor segar, map geometry, kedekatan pose
   dengan graph, controller aktif, dan Nav2 siap. Cari JSON
   `"accepted": true`, `"errors": []`. Launch akan berhenti setelahnya;
   jangan menilai lulus hanya dari exit code `ros2 launch`.

4. Uji goal Nav2 pendek **tanpa fleet adapter**, amati perpindahan fisik
   terukur, dan uji penghentian. Bila Nav2 tadi dijalankan dalam launch
   preflight, jalankan `husky_nav2 navigation.launch.py` secara terpisah
   untuk uji ini, lalu hentikan sebelum launch robot berikutnya. Jangan
   menyalakan dua AMCL/Nav2/map server.

5. Setelah peta, lokalisasi, E-stop, preflight, dan uji Nav2 diterima,
   jalankan fleet adapter di Husky:

   ```bash
   ros2 launch brin_husky_distributed robot.launch.py \
     traffic_profile:=banyak_simpangan enable_dispatch:=true
   ```

   Tambahkan `start_nav2:=true` hanya bila Nav2 tidak berjalan terpisah.
   Preflight diulang; adapter dimulai hanya setelah lolos. Pada terminal
   laptop kedua dengan overlay yang sama:

   ```bash
   ros2 topic echo /fleet_states --once
   ros2 run brin_husky_hardware send_task --robot husky_0 --places ws_p0
   ```

   `ws_p0` hanyalah contoh: pilih waypoint aman dan cukup jauh untuk
   membuktikan gerak, bukan goal pada posisi awal. Simpan ID task, amati
   hasil action serta perubahan pose nyata. Setelah task bergerak, uji
   pembatalan dengan `ros2 run brin_husky_hardware send_task --cancel TASK_ID`.

Tidak ada run fisik yang dilakukan oleh workspace laptop ini. Hasil build
dan unit test tidak membuktikan koneksi DDS, lokalisasi, gerak, penghentian,
atau task selesai. Simpan log preflight dan hasil gerak di lokasi sebelum
melanjutkan traffic bersama robot kedua.

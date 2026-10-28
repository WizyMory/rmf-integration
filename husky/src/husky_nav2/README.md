# Husky A200-1060: Hokuyo + AMCL + Nav2

Paket ini memakai bringup Clearpath yang otomatis berjalan di robot:

```text
encoder -> /a200_1060/platform/odom ---+
                                        +-> EKF navigasi -> /a200_1060/nav/odom/filtered
IMU -> /a200_1060/sensors/imu_0/data -+                -> odom -> base_link

Hokuyo -> /a200_1060/scan -> AMCL -> map -> odom
map PNG -> map_server -> /a200_1060/map
robot_state_publisher -> /a200_1060/tf -> wheel_tf_relay -> /a200_1060/nav/tf
Nav2 -> /a200_1060/cmd_vel_nav -> velocity_smoother
     -> /a200_1060/cmd_vel -> twist_mux -> controller Husky
```

EKF bawaan Clearpath tetap berjalan untuk platform. EKF paket ini memakai
`/a200_1060/nav/tf` khusus Nav2, karena EKF bawaan hanya berlangganan
encoder pada konfigurasi live yang diperiksa. Static TF sensor tetap dari
`/a200_1060/tf_static`. Jalankan hanya satu penerbit `map -> odom` pada
topic TF navigasi. Jangan jalankan SLAM Toolbox bersamaan dengan AMCL.
`wheel_tf_relay` bawaan paket hanya meneruskan empat transform roda. Transform
platform `odom -> base_link` sengaja tidak diteruskan agar tidak bertabrakan
dengan transform dari EKF navigasi.
Local costmap mengirim full grid 100 × 100 secara periodik agar RViz yang
dibuka belakangan tidak berhenti pada status `No map received`. Global costmap
tetap memakai update incremental karena ukurannya jauh lebih besar.
Rentang tinggi obstacle scan diatur 0–2 m; tanpa batas atas ini, nilai default
source adalah 0 m sehingga titik Hokuyo pada ketinggian 0,485 m tersaring dari
costmap. Observasi dipertahankan 0,2 detik untuk menoleransi jitter singkat.

## Map

`maps/banyak_simpangan_nav2.yaml` memakai metadata dari
`src/banyak_simpangan_nav2.candidate.yaml`: resolusi
`0.049412520154504355 m/piksel`, origin `[0, -189.89231495376023, 0]`.
PNG disalin tanpa diubah dari `src/banyak_simpangan_nav2.png`. Warna abu-abu
205 dipertahankan sebagai `unknown`, putih 254/255 sebagai `free`, hitam
sebagai `occupied`. Planner dilarang masuk area `unknown`.

Laporan `src/banyak_simpangan_occupancy_report.json` memvalidasi footprint
sekitar 1.10 × 0.76 m dengan padding 0.02 m terhadap jalur yang ditentukan.
Geometri dan posisi map tetap perlu dibandingkan dengan scan Hokuyo di lokasi
sebelum mengirim goal.

## Build

Node platform Clearpath tetap memakai FastDDS. Paket navigasi dan RViz secara
default memakai CycloneDDS, yang tetap dapat berkomunikasi melalui DDS tetapi
menghindari error alokasi history FastDDS saat costmap besar dikirim. Discovery
dari proses yang baru hidup bisa memerlukan beberapa detik:

```bash
source /etc/clearpath/setup.bash
source /home/husky/ros2_ws/install/setup.bash
cd /home/husky/rmf_ws
colcon build --symlink-install --packages-select hokuyo_bringup husky_nav2
source install/setup.bash
```

## Jalankan bertahap

Pastikan platform sudah hidup. Paket ini secara default menjalankan driver
Hokuyo dan static TF lidar (`start_hokuyo:=true`). Jika `/a200_1060/scan`
sudah memiliki publisher dari bringup lain, gunakan `start_hokuyo:=false`
agar dua driver tidak mengakses sensor yang sama.

1. Uji map dan AMCL tanpa Nav2 penggerak:

   ```bash
   ros2 launch husky_nav2 navigation.launch.py navigation:=false
   ```

   Mode ini hanya menjalankan EKF, map_server, AMCL, dan Hokuyo. Local dan
   global costmap belum tersedia karena server navigasi sengaja tidak dimulai.

2. Buka RViz paket ini di terminal kedua. Launch ini penting karena TF
   navigasi berada pada `/a200_1060/nav/tf`, bukan TF platform:

   ```bash
   source /etc/clearpath/setup.bash
   source /home/husky/ros2_ws/install/setup.bash
   source /home/husky/rmf_ws/install/setup.bash
   ros2 launch husky_nav2 rviz.launch.py
   ```

   Jangan jalankan relay seluruh `/a200_1060/tf`; relay roda terfilter sudah
   dimulai otomatis oleh `navigation.launch.py`. Berikan `2D Pose Estimate`;
   tool RViz tersebut sudah diarahkan ke `/a200_1060/initialpose`. AMCL baru
   menerbitkan `map -> odom` setelah menerima pose awal. Pastikan scan sejajar
   dengan dinding dan pose tetap masuk akal ketika Husky digerakkan dengan
   joystick.

3. Setelah lokalisasi stabil, hentikan launch tahap pertama dan jalankan:

   ```bash
   ros2 launch husky_nav2 navigation.launch.py
   ```

   Berikan `2D Pose Estimate` sekali lagi setelah launch baru hidup.
   Manajer Nav2 mulai sekitar 12 detik setelah launch agar map dan AMCL siap.
   Planner menunggu TF `map -> odom` dari AMCL sebelum aktif sepenuhnya;
   pesan `Please set the initial pose` selama menunggu adalah normal.

4. Berikan goal pendek di area bebas pada `/a200_1060/navigate_to_pose`.
   Uji dalam area kosong terlebih dahulu dengan joystick dan emergency stop
   tersedia. Kecepatan awal dibatasi `0.20 m/s` linear dan `0.35 rad/s`
   angular. Tekan Ctrl-C untuk menghentikan launch.

Jika tetap memakai RViz manual, remap TF dan topic pose berikut:

```bash
ros2 run rviz2 rviz2 --ros-args \
  -r /tf:=/a200_1060/nav/tf \
  -r /tf_static:=/a200_1060/tf_static \
  -r /initialpose:=/a200_1060/initialpose \
  -r /goal_pose:=/a200_1060/goal_pose
```

## Overlay jalur RMF di RViz

Setelah paket versi ini dibangun dan overlay-nya di-source, perintah berikut
otomatis menampilkan graph `brin_0` berwarna cyan pada peta Nav2:

```bash
ros2 launch husky_nav2 rviz.launch.py
```

Launch RViz memulai satu publisher marker statis pada
`/a200_1060/rviz/rmf_graph_markers`, dengan `use_sim_time:=false` dan frame
`map`. Koordinat meter dibaca langsung dari exported graph
`brin_rmf_maps/nav_graphs/simulation.yaml`, sesuai entri profil `brin_0`
di `maps/traffic_profiles.yaml`. Nama file graph ini tidak menentukan clock;
publisher tetap memakai waktu nyata. Tidak ada offset atau
transform tambahan. Reverse lane digambar sebagai satu garis; overlay ini
menunjukkan geometri jalur, bukan arah, penutupan lane, atau reservasi traffic.

Untuk penggunaan `brin_0`, berikan peta Nav2 yang sama secara eksplisit.
Launch navigasi masih memiliki default peta lama `banyak_simpangan_nav2.yaml`;
gunakan perintah berikut sebagai pasangan overlay `brin_0`:

```bash
RMF_NAV_MAP="$(ros2 pkg prefix brin_rmf_maps)/share/brin_rmf_maps/maps/brin_0.yaml"
test -f "$RMF_NAV_MAP" && \
ros2 launch husky_nav2 navigation.launch.py \
  map:="$RMF_NAV_MAP" use_sim_time:=false start_hokuyo:=false
```

Perintah ini mengasumsikan scan Hokuyo sudah berjalan, seperti alur operator.
Di terminal kedua, jalankan `ros2 launch husky_nav2 rviz.launch.py`.
Untuk integrasi RMF, berikan `traffic_profile:=brin_0` pada
`brin_husky_distributed laptop.launch.py` di laptop dan
`brin_husky_distributed robot.launch.py` di Husky; default kedua launch
integrasi tersebut masih `banyak_simpangan`. Pemilihan profil ini tidak
mengaktifkan dispatch dengan sendirinya.

Profil graph harus sama dengan peta Nav2. Jika memakai kembali peta
`banyak_simpangan.yaml`, pilih overlay-nya secara eksplisit:

```bash
ros2 launch husky_nav2 rviz.launch.py traffic_profile:=banyak_simpangan
```

Untuk mematikan publisher dan display graph:

```bash
ros2 launch husky_nav2 rviz.launch.py show_rmf_graph:=false
```

Display `/schedule_markers` dan `/fleet_markers` juga tersedia otomatis.
Keduanya menunggu publisher visualizer RMF; launch RViz ini tidak memulai
RMF core, visualizer jadwal, atau fleet adapter. Graph statis tetap terlihat
ketika RMF belum berjalan. Rute yang dijadwalkan memerlukan RMF core,
fleet adapter, visualizer jadwal dan itinerary aktif. Launch
`brin_husky_distributed laptop.launch.py` saat ini belum memulai visualizer;
bila core sudah hidup, jalankan visualizer pada laptop di terminal terpisah:

```bash
ros2 run rmf_visualization_schedule schedule_visualizer_node --ros-args \
  -p use_sim_time:=false -p initial_map_name:=L1
ros2 run rmf_visualization_fleet_states fleetstates_visualizer_node --ros-args \
  -p use_sim_time:=false -p initial_map_name:=L1 -p HuskyA200_radius:=0.70
```

Masing-masing perintah berjalan terus, sehingga gunakan satu terminal untuk
setiap visualizer. Jalankan hanya visualizer yang belum hidup. Topic absolut
tersebut harus terlihat dari mesin RViz melalui koneksi DDS yang sudah dipakai
integrasi. Publisher graph lokal tidak memerlukan koneksi ke laptop.

Publisher tambahan hanya mengirim satu `MarkerArray` dengan QoS Reliable /
Transient Local, sehingga RViz yang terhubung belakangan tetap menerima graph.
Ia tidak mengirim goal, kecepatan, TF, map, costmap atau obstacle simulasi.
Kesalahan profil/file graph dilaporkan oleh proses publisher; tidak ada handler
yang mematikan Nav2 atau RViz ketika publisher gagal. Tambahan beban berasal
dari satu node kecil dan rendering garis di RViz. Overlay yang terlihat cocok
belum membuktikan lokalisasi, jadwal, atau gerak robot sudah benar.

Perubahan ini berada pada snapshot `husky/src/husky_nav2`; paket simulasi
laptop tetap menggunakan visualisasinya sendiri. Build dan deployment di
Husky dilakukan terpisah sesuai panduan repository. Skrip
`tools/integration.bash husky build` hanya memilih empat paket integrasi dan
belum membangun `husky_nav2`. Untuk membangun tambahan ini pada clone robot,
gunakan underlay Humble/Clearpath yang sama seperti build Nav2 yang bekerja,
lalu dari root repository:

```bash
colcon --log-base husky/log build --base-paths husky/src \
  --build-base husky/build --install-base husky/install --symlink-install \
  --packages-select brin_rmf_maps husky_nav2
source husky/install/local_setup.bash
ros2 pkg prefix husky_nav2
```

Prefix terakhir harus menunjuk ke `husky/install/husky_nav2` pada clone ini.
Jangan menyalin direktori build/install dari laptop ke robot.

Pemeriksaan topic yang berguna:

```bash
ros2 topic echo /a200_1060/nav/odom/filtered --once --field header
ros2 topic echo /a200_1060/scan --once --field header
ros2 topic info /a200_1060/cmd_vel --verbose
ros2 lifecycle get /a200_1060/amcl
ros2 lifecycle get /a200_1060/controller_server
ros2 run tf2_ros tf2_echo odom laser_frame --ros-args \
  -r /tf:=/a200_1060/nav/tf \
  -r /tf_static:=/a200_1060/tf_static
```

`navigation:=false` tetap menjalankan map_server dan AMCL untuk uji
lokalisasi. `autostart:=false` tersedia untuk debug lifecycle manual.

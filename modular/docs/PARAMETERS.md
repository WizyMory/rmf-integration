# Referensi parameter robot.yaml

Versi schema `1`. Path relatif dihitung dari direktori `robot.yaml`. Nilai
`null` berarti belum diketahui, bukan nilai default yang boleh dipakai untuk
dispatch. Semua proses fisik memakai waktu nyata.

## Identitas dan RMF

| Parameter | Arti / contoh | Cara memperoleh |
| --- | --- | --- |
| `robot.name` | Nama RMF unik, misalnya `robot_01` | Pilihan operator, huruf/angka/underscore |
| `robot.fleet` | Nama fleet unik per adapter, misalnya `Robot01Fleet` | Jangan memakai fleet yang dikelola adapter lain |
| `rmf.domain_id` | Domain core, sering `0` | Environment/service core |
| `rmf.rmw` | Cyclone/Fast DDS pada proses RMF | Samakan dengan deployment core yang telah diuji |
| `rmf.localhost_only` | `false` untuk LAN; `true` hanya uji satu host | Jangan true untuk core pada komputer lain |
| `rmf.cyclonedds_uri` | `file:///absolute/path/config.xml`, atau kosong | Profil DDS integrasi yang ditinjau |
| `rmf.fastdds_profiles_file` | Path XML Fast DDS, atau kosong | Profil Fast DDS integrasi |
| `rmf.discovery_server` | String ROS_DISCOVERY_SERVER, atau kosong | Setup discovery server yang memang dipakai |
| `rmf.web_uri` | `ws://CORE_IP:8000/_internal`, `wss://...`, atau kosong | Endpoint internal adapter Web API, bukan URL browser `:3000` |
| `rmf.nav_graph` | Export navigation graph Traffic Editor | Salin dari bundle core canonical |
| `rmf.building_map` | Building map RMF, `.building.yaml` | Salin dari bundle core canonical |
| `rmf.level` | Nama level pada graph, misalnya `L1` | Key di `levels` pada nav graph |
| `rmf.home_waypoint` | Waypoint bernama, `is_charger: true` | Vertex canonical yang valid untuk inisialisasi RMF |
| `rmf.profile_topic` | Topic digest String dari komputer utama | Core BRIN: `/brin_hardware/profile_digest` |
| `rmf.expected_profile_digest` | SHA256 64 karakter | Baca publisher core; own-core memakai hasil `pin-assets` |

`home_waypoint` adalah syarat registrasi Humble. Jangan mengira label charger
berarti robot mampu docking: versi ini menolak docking dan menonaktifkan
finishing charger/battery drain. Bila graph belum memiliki metadata charger,
pemilik site harus memperbarui bundle canonical dan digest seluruh perangkat
secara terkoordinasi sebelum robot ditambahkan.

`pin-assets` mengunci hash lokal dari building map, nav graph, map YAML dan
image. Ia bukan algoritme digest BRIN. Isi `expected_profile_digest` dengan
nilai yang benar-benar diterbitkan core yang dipakai.

## Domain, action, topic dan frame Nav2

| Parameter | Arti | Catatan |
| --- | --- | --- |
| `nav2.domain_id` | Domain Nav2 asli robot | Boleh berbeda dari domain RMF |
| `nav2.rmw` | RMW Nav2 yang sudah bekerja | Diterapkan hanya pada proses gateway |
| `nav2.localhost_only` | Batasi gateway ke localhost | Umumnya false; true untuk tes lokal |
| `nav2.cyclonedds_uri` | Profil Cyclone khusus domain robot | Kosong bila default discovery memang bekerja |
| `nav2.fastdds_profiles_file` | XML Fast DDS robot | Ditentukan eksplisit, tidak mewarisi profil RMF |
| `nav2.discovery_server` | Discovery server Nav2 asli | Jangan dikosongkan jika driver/Nav2 membutuhkannya |
| `navigate_action` | Nama action absolut | `/robot_01/navigate_to_pose`; tipe NavigateToPose |
| `bt_navigator_node` | Node navigator absolut | `/robot_01/bt_navigator` untuk render transit |
| `map_topic` | OccupancyGrid | Subscriber reliable/transient-local |
| `scan_topic` | LaserScan | Subscriber sensor-data/best-effort |
| `odom_topic` | Odometry | Subscriber sensor-data/best-effort |
| `tf_topic`, `tf_static_topic` | Topic TF asli | Dapat berupa `/tf`, `/tf_static` atau topic privat |
| `map_frame`, `base_frame` | Frame localization | Tanpa slash awal; bukan nama topic |
| `map_yaml` | Metadata peta Nav2 aktif | Resolution/origin diperiksa terhadap map message |
| `lifecycle_nodes` | Daftar node wajib active | Hanya node lifecycle; jangan masukkan robot_state_publisher |
| `max_data_age` | Batas data/TF, detik | Default template 2; data masa depan lebih dari 0,5 s ditolak |
| `max_graph_distance` | Batas merge/registrasi, meter | Default template 1; jangan dipakai menutupi alignment salah |
| `update_hz` | Poll/position update adapter, Hz | 1–20; template 5 |
| `action_timeout` | Timeout acknowledgement goal, detik | 1–120; bukan timeout durasi task |
| `planner_id`, `controller_id` | ID plugin pada BT transit | Contoh GridBased/FollowPath; bukan nama class plugin |
| `final_orientation_only` | Transit tanpa syarat yaw | false sampai setup BT dan graph ditinjau |
| `transit_xy_tolerance` | Toleransi XY transit, meter | Samakan dengan goal checker robot |
| `transit_params_confirmed` | Penerimaan pemuatan fragmen BT | Manusia mengonfirmasi launch Nav2 benar-benar memuatnya |

Isi `lifecycle_nodes` sesuai robot. Bila Nav2 memakai lokalisasi non-AMCL,
hapus `/amcl` dari daftar dan tambahkan lifecycle localizer yang relevan bila
ada. TF map→base tetap wajib. Node opsional seperti behavior_server,
velocity_smoother boleh ditambahkan jika memang merupakan syarat robot.

Gateway memakai proses terpisah dengan `multiprocessing.spawn`. Ia tidak
membuka REST/TCP listener baru atau mem-publish TF. `CYCLONEDDS_URI`, domain,
RMW dan discovery server diatur terpisah untuk induk RMF dan anak Nav2;
environment service robot yang lain tidak diubah.

## Dimensi dan batas gerak

| Parameter | Satuan | Makna |
| --- | --- | --- |
| `geometry.footprint_radius` | m | Lingkaran konservatif yang mencakup footprint nyata |
| `geometry.vicinity_radius` | m | Radius vicinity traffic, minimal footprint_radius |
| `motion.linear_speed` | m/s | Batas kecepatan linear untuk estimasi RMF |
| `motion.linear_acceleration` | m/s² | Batas akselerasi linear untuk estimasi RMF |
| `motion.angular_speed` | rad/s | Batas kecepatan putar untuk estimasi RMF |
| `motion.angular_acceleration` | rad/s² | Batas akselerasi putar untuk estimasi RMF |
| `motion.reversible` | boolean | Versi ini hanya mendukung false |

Untuk robot persegi panjang berpusat di `base_link`, radius konservatif dapat
dihitung dari jarak titik footprint terjauh, bukan hanya setengah lebarnya.
Pertimbangkan offset `base_link`, bumper dan payload aktual. Nilai RMF tidak
mengubah footprint/collision checker Nav2; keduanya perlu konsisten.

## Transformasi Nav2–RMF

```text
RMF.x   = cos(yaw) * Nav2.x - sin(yaw) * Nav2.y + alignment.x
RMF.y   = sin(yaw) * Nav2.x + cos(yaw) * Nav2.y + alignment.y
RMF.yaw = wrap(Nav2.yaw + alignment.yaw)
```

`alignment.x/y` dalam meter; `alignment.yaw` dalam radian. Transformasi
kebalikannya dipakai untuk goal Nav2. Tidak ada TF tambahan yang diterbitkan.
Identity `[0,0,0]` hanya benar bila koordinat kedua peta memang sama. Gunakan
beberapa titik kontrol fisik yang tersebar untuk mengonfirmasi kalibrasi;
jangan mengarang offset dari satu titik ketika orientasi peta berbeda.

## Baterai dan commissioning

`battery.mode: none` berarti belum ada telemetri. `battery_state` membaca
`sensor_msgs/msg/BatteryState.percentage` dalam rentang 0–1 ketika `present`
true. `voltage` membaca `std_msgs/msg/Float32.data` dan menggunakan
`(V-empty_voltage)/(full_voltage-empty_voltage)`, dibatasi 0–1. Ini estimasi
linear, bukan model SoC tervalidasi untuk semua kimia baterai. Data lebih tua
dari 10 detik tidak dikirim sebagai pembaruan SoC.

Empat flag commissioning hanya diberi true setelah bukti tersedia:

- `alignment_confirmed`: peta/koordinat/heading sudah diperiksa secara fisik.
- `footprint_confirmed`: dimensi aktual dan profil traffic benar.
- `nav2_motion_tested`: Nav2 asli berhasil bergerak, mencapai goal dan cancel.
- `operation_accepted`: operator menerima integrasi ini untuk uji task.

Parameter ini tidak menggantikan kemampuan stop/E-stop perangkat keras.

## Audit baca-saja di robot baru

Jalankan dalam terminal yang sudah memakai domain/RMW Nav2 asli. Jangan
menyetel domain yang berbeda pada service robot untuk mengikuti contoh:

```bash
hostname -I
env | rg '^(ROS_DISTRO|ROS_DOMAIN_ID|RMW_IMPLEMENTATION|ROS_LOCALHOST_ONLY|CYCLONEDDS_URI|ROS_DISCOVERY_SERVER)='
timeout 8s ros2 node list --no-daemon --spin-time 2
timeout 8s ros2 topic list -t
timeout 8s ros2 action list -t
timeout 8s ros2 lifecycle nodes

# Ganti namespace sesuai robot:
timeout 8s ros2 action info /robot_01/navigate_to_pose
timeout 8s ros2 lifecycle get /robot_01/bt_navigator
timeout 8s ros2 param get /robot_01/bt_navigator use_sim_time
timeout 8s ros2 param dump /robot_01/controller_server
timeout 8s ros2 topic echo /robot_01/odometry/filtered --once --qos-reliability best_effort
```

Jika `rg` tidak tersedia, gunakan `grep -E` untuk pemeriksaan environment.
Parameter controller berbeda antara RPP, DWB, MPPI dan controller lain;
identifikasi batas yang benar dari plugin/velocity smoother yang aktif.

Saat meminta bantuan mengisi profil, kirim nama robot/fleet, domain/RMW kedua
sisi, output audit di atas, path map/graph canonical, ukuran footprint,
batas motion dan jenis baterai. Password/private key tidak diperlukan.

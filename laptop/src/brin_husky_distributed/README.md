# Husky fisik: RMF pusat di laptop, Nav2 dan fleet adapter di robot

Paket ini mengadaptasi `brin_husky_distributed` dari arsip operator
`rmf_ws_husky.tar.xz` menjadi jalur dua-komputer tanpa mengubah launch atau
isi file simulasi. Untuk Husky fisik `a200_1060`, nama RMF-nya `husky_0`.

| Komputer | Proses yang dijalankan |
| --- | --- |
| Laptop utama | Satu RMF schedule, task dispatcher, building map server, pengumum identitas peta/graph, dan CLI task. |
| Husky | Driver Clearpath dan lidar, satu AMCL/Nav2/map server, jembatan TF fisik, preflight, serta satu fleet adapter. |

Tidak ada Gazebo atau `/clock` simulasi. `server_uri` tetap kosong kecuali
operator secara terpisah mengaktifkan RMF Web. Jalur API waktu nyata dan
koneksi LAN adapter onboard dijelaskan di [WEB.md](WEB.md). **Jangan** menjalankan
`brin_husky_hardware hardware.launch.py` bersamaan: launch lama memulai RMF
core dan adapter pada satu mesin, sehingga akan menggandakan proses.
Putusnya koneksi laptop/DDS **tidak menjamin** goal Nav2 yang sudah diterima
berhenti; operator tetap harus siap menggunakan kendali manual/E-stop fisik.

## Siapkan kedua mesin

Gunakan [panduan deployment repository](../../../docs/DEPLOYMENT.md) sebagai
alur utama: clone commit yang sama, build `laptop/src` pada laptop dan
`husky/src` pada Husky, tanpa menimpa workspace lama atau menyalin artefak
build antar mesin. Skrip `tools/integration.bash` menyiapkan overlay dan
environment proses integrasi saja.

Kedua sisi memakai Humble, domain 0, waktu nyata dan LAN dua arah. Jam harus
sinkron; preflight membatasi usia data/TF menjadi 2 detik. Default skrip adalah
Cyclone DDS dengan profil Wi-Fi/peer eksplisit per target. Native adapter
diagnostik lulus tiga kali berturut-turut dan uji DDS pulang-pergi lulus;
lihat status repository untuk batas hasil. Middleware service Clearpath tidak
diubah. Jangan gunakan konfigurasi localhost simulasi.

Laptop membutuhkan RMF core dan empat paket integrasi; Husky membutuhkan
paket integrasi serta runtime Python `rmf_adapter`. Nav2 saja tidak cukup.
Driver Hokuyo/UM7 dan konfigurasi Nav2 berasal dari robot, bukan simulasi.
API/protokol/IP/port/parameter Hokuyo yang sudah bekerja tidak boleh diubah.

Sebelum mengaktifkan adapter fisik, pastikan scan, map, NavigateToPose,
lokalisasi, controller dan TF sesuai. Aktivasi Nav2 serta bridge harus
disetujui operator. Jangan menyalakan driver atau controller duplikat.
Bagian berikut menjelaskan profil dan penerimaan fisik, bukan bukti
deployment maupun gerak sudah berhasil.

## Pilih satu profil dan periksa robot

Profil bawaan `banyak_simpangan` mengikuti Nav2 di arsip Husky. `brin_0`
boleh dipilih hanya jika map fisik yang dijalankan memang cocok. Kedua launch
membaca `brin_rmf_maps/maps/traffic_profiles.yaml` sehingga building map,
graph, dan map Nav2 berasal dari satu entri. Laptop mengumumkan SHA-256 atas
nama profil, building YAML, graph, map YAML dan PNG; preflight robot menolak
profil atau versi aset yang berbeda. **Ini belum membandingkan piksel map
server yang sedang aktif.** Periksa peta dan scan di RViz, lalu set initial
pose AMCL sesuai posisi robot sebenarnya.

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

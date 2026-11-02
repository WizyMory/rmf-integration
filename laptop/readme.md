# Laptop — panduan uji operasional Open-RMF dan Husky

Lokasi: `/mnt/UbuntuData/rmf-integration/laptop/readme.md`.
Jalankan perintah dari root `/mnt/UbuntuData/rmf-integration`, bukan dari `laptop/src`.
Panduan pasangan: [README Husky](../husky/readme.md).

Profil map baru `gedungWS_0` memakai graph dan map Nav2 yang diselaraskan
dengan resolusi SLAM 0.05 m/pixel. Pilih pada core:

```bash
bash tools/integration.bash laptop core traffic_profile:=gedungWS_0 rviz:=true
```

Biarkan core ini berjalan sebelum preflight atau adapter Husky dijalankan.
Core menyediakan tiga node RMF dan pengumuman digest profil yang diperiksa
oleh preflight. Jangan membuka core kedua untuk profil yang sama.

Husky harus memilih `traffic_profile:=gedungWS_0` dan map Nav2
`gedungWS_0_rmf.yaml` pada sesi yang sama. Lihat
[catatan profil gedungWS](../docs/GEDUNGWS_0_2026-10-30.md).
Digest profil `gedungWS_0` yang terpasang di kedua perangkat:
`ff44d7a33b01732e6c277b523c40ae5c7ef6c011dab83b259e5db44daef9f221`.

Konfigurasi uji 2 November 2026: radius footprint RMF `0.55 m`, footprint
Nav2 `x=±0.45, y=±0.30 m`, dan inflation radius local/global `0.35 m`.
Source serta instalasi kedua perangkat sudah diselaraskan; gunakan launch
baru untuk memuat nilai ini. Lihat [laporan footprint dan inflation](../docs/FOOTPRINT_INFLATION_2026-11-02.md).

Kecepatan diperbarui pada 29 Oktober 2026: target linear **0.5 m/s** dan
angular **0.5 rad/s**, pada Nav2 simulasi laptop dan konfigurasi robot Husky.
Batas velocity smoother dan fleet RMF sudah diselaraskan, termasuk workspace
lama `rmf_ws`. Konfigurasi baru dimuat pada launch berikutnya; pembaruan ini
tidak menjalankan robot. Lihat [rincian perubahan kecepatan](../docs/SPEED_UPDATE_2026-10-29.md).

## Pembaruan map `brin_0` — 29 Oktober 2026

Edit `src/brin_rmf_maps/maps/brin_0.building.yaml` sudah diregenerasi menjadi
graph RMF, occupancy Nav2, spawn dan mesh dinding, lalu dibuild pada laptop
dan Husky, termasuk workspace lama `rmf_ws`. Masing-masing workspace lulus
21 tes map; digest profil terpasang sama pada kedua perangkat.
Lihat [laporan pembaruan map](../docs/MAP_UPDATE_2026-10-29.md).

Untuk memakai hasil edit ini, jalankan core di L1 dengan profil eksplisit:

```bash
bash tools/integration.bash laptop core traffic_profile:=brin_0 rviz:=true
```

Pakai `traffic_profile:=brin_0` juga pada preflight dan adapter Husky, serta
`maps/brin_0.yaml` untuk map Nav2. Contoh `banyak_simpangan` pada prosedur di
bawah adalah profil lain; ganti nama profil/map secara konsisten untuk sesi
`brin_0`. Saat deployment tidak ada core/Nav2/adapter aktif; runtime dan uji
gerak tidak dijalankan oleh proses pembaruan ini.

## 1. Batas uji dan keselamatan

Laptop menjalankan RMF core, RViz beserta visualizer traffic/fleet, CLI task,
dan opsional RMF Web. Robot menjalankan sensor, Nav2 dan fleet adapter.
Identitas: namespace `/a200_1060`, robot RMF
`husky_0`, fleet `HuskyA200`, lantai `L1`, profil `banyak_simpangan`.

Komunikasi dan deployment sudah diuji; **gerak Nav2, task RMF, pembatalan saat
bergerak dan Web end-to-end belum dinyatakan lulus**. Panduan ini adalah
prosedur penerimaan lapangan, bukan pernyataan robot sudah aman bergerak.

Pembaruan RViz 28 Oktober 2026 sudah dideploy dan dibuild di kedua perangkat:
empat paket berhasil dibuild dan 56 tes lulus pada masing-masing perangkat.
Opsi launch dan aset terpasang sudah diperiksa; tampilan saat robot bergerak
belum diuji langsung. Lihat [laporan deployment RViz](../docs/RVIZ_DEPLOYMENT_2026-10-28.md).

- Tahap A–B tidak mengirim goal. Tahap C mencakup uji goal Nav2 fisik;
  tahap F dan G dapat mengirim task RMF. Semua tahap gerak memerlukan operator
  lokal, area kosong, joystick dan E-stop fisik yang sudah diuji.
- Jangan mengubah API/protokol/IP/port/parameter Hokuyo, UM7, controller,
  jaringan, TF atau batas kecepatan untuk membuat pengujian terlihat lulus.
- Jangan jalankan Gazebo, SLAM, core RMF kedua, launch hardware monolitik,
  atau adapter kedua bersamaan dengan jalur ini.
- Jangan gunakan `/clock` atau `use_sim_time:=true`. Seluruh sistem fisik
  memakai waktu nyata. Jam kedua komputer harus sinkron.
- Putusnya SSH, DDS, API, Ctrl-C, atau timeout CLI **bukan E-stop** dan tidak
  menjamin goal yang telah diterima Nav2 berhenti.

## 2. Persiapan setiap terminal laptop

Buka terminal baru. Salin blok ini pada **L2 dan setiap terminal ROS manual**.
Helper di L1/L3 menyiapkan environment anak prosesnya sendiri, tetapi tetap
harus dijalankan dari root repository. L4 memakai environment dashboard khusus
pada tahap G dan tidak memerlukan blok ROS ini.

```bash
cd /mnt/UbuntuData/rmf-integration
source /opt/ros/humble/setup.bash
source /mnt/UbuntuData/clearpath_ws/install/local_setup.bash
source /mnt/UbuntuData/BRIN_ws/install/local_setup.bash
source /mnt/UbuntuData/rmf-integration/laptop/install/local_setup.bash
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$PWD/laptop/src/brin_husky_distributed/config/cyclonedds_lan.xml"
export ROS_LOG_DIR="$PWD/laptop/log/ros"
unset ROS_DISCOVERY_SERVER
```

Unset discovery server berlaku untuk LAN biasa yang sudah diaudit. Jika
memakai discovery server khusus, hentikan dan tinjau konfigurasi dahulu.
Sourcing tidak boleh dilakukan setelah export domain karena overlay lama
dapat mengembalikan domain `42`. Jangan mengubah `.bashrc` atau service.
Skrip `tools/integration.bash` menyiapkan environment anak prosesnya sendiri;
menjalankan skrip itu tidak menyiapkan shell terminal lain.
Helper juga memulihkan prioritas overlay repository bila shell mewarisi
workspace ROS lama. Untuk perintah ROS manual, tetap periksa prefix paket
sebelum melanjutkan; sourcing saja belum membuktikan overlay yang dipilih benar.

Pemeriksaan baca-saja:

```bash
git rev-parse HEAD
ros2 pkg prefix brin_husky_distributed
bash tools/integration.bash laptop profile traffic_profile:=gedungWS_0
ip -4 route get 192.168.0.120
timeout 8s ros2 node list --no-daemon --spin-time 3
```

Prefix integrasi harus dari `.../rmf-integration/laptop/install/`. Bandingkan
commit dan digest dengan operator Husky. Digest aset saat deployment:
`20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7`.
Kesamaan digest tidak membuktikan peta cocok dengan ruangan sebenarnya.
Profil DDS laptop memilih `wlp9s0`, peer robot `192.168.0.120`. Jika IP atau
interface berubah, jangan mengubah routing/driver secara coba-coba.

## 3. Arti L1–L4, H0–H4 dan urutan A–G

**Huruf dan angka terminal bukan urutan langkah.** `L` berarti terminal di
laptop dan `H` berarti terminal di Husky. Angka hanya membedakan jendela
terminal yang dipakai untuk proses berbeda. Khusus `L1 (terminal)`, jangan
tertukar dengan `L1 (lantai)`: keduanya tidak berhubungan.

L2 dan terminal ROS manual harus lebih dahulu menjalankan blok environment
pada bagian 2. Terminal yang menjalankan proses foreground dibiarkan terbuka.
Perintah pemeriksaan yang selesai sendiri dapat dijalankan berulang di L2.

| Terminal | Fungsi | Kapan ditutup |
| --- | --- | --- |
| **L1** | Satu RMF core dan, dengan `rviz:=true`, RViz serta tiga visualizer | Paling akhir, atau sekali diganti secara terkontrol saat pindah ke Web |
| **L2** | Terminal diagnostik dan CLI: DDS, status, task dan cancel | Setelah seluruh pengujian selesai |
| **L3** | API RMF Web, hanya pada tahap G | Setelah sesi Web selesai |
| **L4** | Dashboard RMF Web, hanya pada tahap G | Setelah sesi Web selesai |
| **H0** | Terminal diagnostik Husky; perintahnya ada di README Husky | Setelah seluruh pengujian selesai |
| **H1** | Driver Hokuyo, hanya bila belum ada driver yang berjalan | Setelah pengujian dan hanya jika driver dimulai oleh sesi ini |
| **H2** | Nav2/AMCL/map server, bila belum berjalan | Setelah adapter berhenti dan robot aman |
| **H3** | Peran RViz untuk initial pose dan observasi; dapat dipenuhi RViz laptop di L1 | RViz terpisah hanya jika RViz L1 tidak dipakai |
| **H4** | Preflight, lalu satu fleet adapter | Adapter dihentikan sebelum Nav2/core |

`A` sampai `G` adalah **tahap waktu yang dikerjakan dari atas ke bawah**.
Tahap berikutnya memakai proses yang masih hidup dari tahap sebelumnya; bukan
berarti semua terminal menjalankan perintah baru secara bersamaan.

| Tahap | Laptop | Husky | Syarat untuk lanjut |
| --- | --- | --- | --- |
| **A — mulai** | Buka **L1**, jalankan satu RMF core dengan `rviz:=true` dan biarkan hidup. Buka **L2** untuk cek core. | Buka **H0**, siapkan environment dan lakukan pemeriksaan awal. | Tepat satu core, waktu nyata, profil/digest kedua mesin cocok. |
| **B — komunikasi tanpa gerak** | Di **L2**, jalankan requester DDS; **L1 tetap hidup**. | Di **H0**, jalankan responder DDS lalu native adapter check. | Kedua DDS endpoint dan native check exit `0` serta menyatakan lulus. |
| **C — siapkan robot** | **L1 tetap hidup**; gunakan RViz yang sudah terbuka untuk observasi dan initial pose. | Periksa/aktifkan berurutan **H1** sensor → **H2** Nav2; gunakan RViz laptop untuk peran **H3**, lalu uji goal Nav2 pendek tanpa adapter. | Sensor, map, lokalisasi, lifecycle/action, gerak Nav2 dan penghentian diterima operator. |
| **D — preflight** | **L1 tetap hidup**; jangan kirim task. | Jalankan preflight di **H4**. Perintah ini selesai sendiri; **H1/H2** tetap hidup. | JSON memuat `accepted: true` dan `errors: []`. |
| **E — daftar robot** | Di **L2**, tunggu dan periksa `/fleet_states`; **L1 tetap hidup**. | Setelah D lulus, gunakan kembali **H4** untuk satu adapter dan biarkan hidup. | `HuskyA200/husky_0` terlihat dengan pose/level yang masuk akal. |
| **F — uji task** | Di **L2**, kirim tepat satu task, tunggu hasil, lalu lakukan uji cancel terkontrol terpisah. | **H4**, **H2**, dan bila diperlukan **H1** tetap hidup; operator mengawasi robot dan E-stop. | Gerak, status akhir dan penghentian telah diamati secara fisik. |
| **G — Web opsional** | Setelah F selesai dan robot diam: hentikan adapter, lalu core lama. Jalankan **L3** API → **L1** core pengganti ber-URI API → **H4** adapter pengganti → **L4** dashboard. | Jalankan kembali adapter di **H4** dengan URI API laptop yang sama. | Hanya satu core dan satu adapter; CLI/cancel sudah diterima lebih dahulu. |

Jadi alur minimumnya adalah `A → B → C → D → E → F`. Tahap `G` opsional
dan merupakan **pergantian sesi**, bukan proses tambahan di samping core dan
adapter lama. Jangan lanjut ke huruf berikutnya bila syarat pada baris saat ini
belum lulus.

Hubungan proses saat task berjalan dapat dibaca seperti ini:

```text
Tahap F (CLI):  L2 task → L1 core/dispatcher ↔ H4 adapter → H2 Nav2 → robot
Sensor:                                             H1 lidar → H2 Nav2
Observasi:        RViz L1 (atau H3 terpisah); L2/H0 memeriksa status

Tahap G (Web):  L4 dashboard → L3 API → L1 core ↔ H4 adapter → H2 Nav2
```

Jadi L2 atau L4 tidak mengendalikan motor secara langsung. H4 menerjemahkan
task RMF menjadi action Nav2; H2 yang menangani navigasi robot. H1 menyediakan
scan, sedangkan H0 terutama untuk pemeriksaan dan observasi.

### Tahap A — L1: satu RMF core dan RViz otomatis

Jika core dari sesi lain masih aktif, identifikasi pemiliknya; jangan memulai
core kedua atau menghentikan proses yang tidak dikenal.

Di terminal laptop L1, dari root repository:

```bash
cd /mnt/UbuntuData/rmf-integration
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan rviz:=true
```

Tidak perlu menjalankan visualizer atau menambah display RViz satu per satu.
Perintah ini menjalankan satu core, tiga visualizer RMF, dan RViz dengan
preset Husky fisik. Driver, Nav2 dan adapter tetap dijalankan di Husky sesuai
tahap berikutnya. RViz ini memenuhi peran H3; tidak perlu membuka RViz kedua
di robot. Untuk core tanpa GUI dan tanpa visualizer, hilangkan `rviz:=true`.

| Layer RViz | Topic | Kapan tersedia |
| --- | --- | --- |
| Peta Nav2 | `/a200_1060/map` | Map server Nav2 aktif |
| Scan Hokuyo | `/a200_1060/scan` | Driver lidar aktif dan TF navigasi tersedia |
| Lane, waypoint dan nama lokasi | `/map_markers` | Adapter memublikasikan `/nav_graphs` |
| Posisi fleet | `/fleet_markers` | Robot terdaftar dan adapter mengirim `/fleet_states` |
| Rencana perjalanan RMF | `/schedule_markers` | Schedule memiliki itinerary pada lantai L1 |
| Jalur Nav2 | `/a200_1060/plan` | Planner Nav2 menerbitkan jalur |

Tampilan memakai **Fixed Frame `map`**, filter lantai **`L1`**, dan
`use_sim_time:=false`. Peta/scan dapat diperiksa sebelum adapter aktif;
lane dan fleet marker yang belum muncul pada tahap A–D tidak langsung berarti
RViz gagal. Marker fleet mengikuti posisi yang dilaporkan adapter, sedangkan
schedule marker menunjukkan rencana RMF. Zoom pada peta untuk melihat robot
dan label waypoint.

Jika core sudah berjalan tanpa opsi RViz, biarkan core itu hidup. Pada satu
terminal laptop tambahan dengan environment bagian 2 dan prefix paket yang
benar, jalankan visualisasi saja:

```bash
ros2 launch brin_husky_distributed visualization.launch.py
```

Launch tersebut tidak memulai core atau adapter kedua. Jangan menjalankannya
bersamaan dengan visualisasi yang sudah dimulai melalui `rviz:=true` di L1.
Panduan preset ada pada [README paket](src/brin_husky_distributed/README.md).

Biarkan proses di L1 hidup. Di terminal L2 yang sudah memakai environment
bagian 2, jalankan pemeriksaan berikut:

```bash
timeout 8s ros2 node list --no-daemon --spin-time 3
timeout 8s ros2 topic echo /brin_hardware/profile_digest std_msgs/msg/String \
  --once --qos-durability transient_local --qos-reliability reliable
timeout 8s ros2 param get /rmf_traffic_schedule_primary use_sim_time
```

Harus ada tepat satu `rmf_traffic_schedule_primary`, `rmf_task_dispatcher`,
`building_map_server`, dan pengumum profil. `use_sim_time` harus `False`.

## 4. Tahap B — uji komunikasi tanpa gerak

Mulai di L2, lalu minta operator menjalankan responder Husky dalam 30 detik:

```bash
timeout --signal=INT --kill-after=3s 35s python3 tools/dds_roundtrip.py \
  --role laptop --session operasional_01 --timeout 30
```

Perintah pasangan ada di README Husky. Kedua endpoint harus exit `0` dan
`passed: true`; laptop menerima minimal tiga balasan. Gunakan session yang
sama untuk satu pasangan, dan session baru untuk uji berikutnya.

Dengan L1 tetap berjalan, operator menjalankan `native_adapter_check.py` di
Husky. Harus `native_adapter_connected_to_schedule: true` **dan exit 0**.
JSON sukses lalu crash/timeout bukan lulus. Uji ini tidak mendaftarkan robot,
tidak membuat fleet palsu, dan tidak membuktikan kesiapan Nav2.

## 5. Tahap C–E — tunggu penerimaan fisik dari operator Husky

Jangan kirim task sebelum operator menyatakan semua berikut lulus:

- Sensor nyata segar, controller aktif, map benar dan scan selaras dengan map.
- Lokalisasi AMCL/initial pose benar; action dan lifecycle Nav2 siap.
- Preflight mengeluarkan `accepted: true` dan `errors: []`.
- Uji Nav2 pendek tanpa adapter, serta penghentian, sudah diterima di lokasi.
- Tidak ada task lama/tertunda yang tidak diketahui; operator siap jika
  registrasi adapter membuat task yang sudah antre segera dapat dieksekusi.

Tahap C dan D dikerjakan operator menurut README Husky. Setelah operator
menyatakan keduanya lulus dan mengaktifkan **satu** adapter pada tahap E,
jalankan di L2:

```bash
timeout 8s ros2 topic echo /fleet_states rmf_fleet_msgs/msg/FleetState --once
timeout 8s ros2 param get /brin_husky_fleet_adapter use_sim_time
```

Harus terlihat `HuskyA200` dengan robot `husky_0`, pose dan level yang masuk
akal; bukan daftar robot kosong. Log Husky harus mencatat
`Registered husky_0 in HuskyA200`. Parameter waktu harus `False`.

Pada build Husky yang sudah dideploy, adapter menonaktifkan responsive wait
dan menahan jalur yang belum memiliki task ID. Sebelum task pertama,
pastikan `task_id` kosong, robot tetap diam dan log Husky memuat
`responsive wait disabled`. Task yang sudah antre tetap harus ditinjau
operator. Catatan guard dan pemeriksaan action client ada pada README Husky.

## 6. Tahap F — uji task terminal, DAPAT MENGGERAKKAN ROBOT

Lakukan hanya setelah tahap E diterima. Pilih tujuan dari profil yang sama
dengan core RMF yang sedang berjalan,
di peta yang telah divalidasi operator. Tujuan harus aman, dapat dicapai, dan
cukup berbeda dari posisi awal untuk membuktikan perpindahan. Jangan mengira
waypoint bernama charger berarti docking fisik sudah tersedia.

```bash
RMF_TEST_PROFILE=gedungWS_0
bash tools/integration.bash laptop profile traffic_profile:="$RMF_TEST_PROFILE"
RMF_TEST_PLACE="$(bash tools/integration.bash laptop waypoint traffic_profile:="$RMF_TEST_PROFILE")"
test -n "$RMF_TEST_PLACE"
```

Pemilih menampilkan waypoint bernama dari graph profil itu, lalu menerima
nomor atau nama yang tercantum. Jika nilai kosong atau pemilih gagal,
berhenti. Daftar waypoint belum membuktikan lokasi aman; operator tetap
menyetujui tujuan sebelum uji. Untuk peta lain, ubah hanya
`RMF_TEST_PROFILE` agar sama dengan profil core. Uji pertama menargetkan robot
langsung:

```bash
timeout --signal=INT --kill-after=3s 40s ros2 run brin_husky_hardware send_task \
  --robot husky_0 --places "$RMF_TEST_PLACE" --timeout 30
```

Catat respons lengkap dan **ID task/booking**, bukan `request_id` API. Respons
diterima hanya berarti request dijawab; belum berarti robot bergerak/selesai.
Amati posisi fisik, feedback/hasil Nav2 dan status akhir RMF. `task_id` kosong
pada fleet state saja juga bukan bukti sukses: gagal/cancel dapat berakhir idle.
SOC `0.95` saat ini nilai konfigurasi, bukan pembacaan baterai asli.

Jika CLI timeout, **jangan langsung mengirim ulang**: request mungkin sudah
diterima robot. Periksa status dan koordinasikan dengan operator dahulu.
Jangan menjalankan dua contoh task sekaligus.

Setelah uji langsung selesai, uji dispatcher secara terpisah, satu task:

```bash
timeout --signal=INT --kill-after=3s 40s ros2 run brin_husky_hardware send_task \
  --places "$RMF_TEST_PLACE" --timeout 30
```

### Pembatalan terkontrol

Lakukan pada task uji berikutnya yang memang disiapkan untuk pengujian cancel.
Operator tetap siap pada E-stop; bukan percobaan kehilangan jaringan.

```bash
read -r -p 'ID task aktif yang akan dibatalkan: ' RMF_TASK_ID
test -n "$RMF_TASK_ID"
timeout --signal=INT --kill-after=3s 40s ros2 run brin_husky_hardware send_task \
  --cancel "$RMF_TASK_ID" --timeout 30
```

Jika ID kosong, jangan lanjut. Tunggu status pembatalan dan pastikan robot
benar-benar berhenti. Bila gerak tidak aman atau cancel tidak efektif, gunakan
E-stop fisik, bukan pengulangan CLI. Catat jeda berhenti dan hasil action.

## 7. Tahap G (opsional) — uji RMF Web setelah CLI lulus

Panduan versi runtime: [WEB.md](src/brin_husky_distributed/WEB.md).
Backend/dashboard belum diuji end-to-end pada robot. Gunakan LAN pengujian
terpercaya; jangan membuka API ke internet atau menonaktifkan firewall.

Tahap ini mengganti sesi CLI, bukan menambah proses pada sesi lama. Sebelum
beralih ke Web, selesaikan/batalkan task, pastikan robot diam, hentikan adapter
Husky di H4, lalu Ctrl-C core lama di L1. Jangan membuat core kedua. Urutan
start yang benar adalah **L3 API → L1 core pengganti → H4 adapter pengganti →
L4 dashboard**.
Di L3 yang sudah memakai environment bagian 2, set:

```bash
export BRIN_LAPTOP_IP=192.168.0.218
export RMF_WEB_ROOT=/mnt/UbuntuData/rmf-web
```

L3 — API, dibiarkan berjalan:

```bash
bash tools/integration.bash laptop web \
  web_root:="$RMF_WEB_ROOT" runtime_dir:="$PWD/laptop/log/rmf_web_real" \
  api_host:="$BRIN_LAPTOP_IP" public_url:="http://$BRIN_LAPTOP_IP:8000"
```

L1 — core pengganti, memakai IP laptop (bukan Husky/localhost):

```bash
export BRIN_LAPTOP_IP=192.168.0.218
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan \
  server_uri:="ws://$BRIN_LAPTOP_IP:8000/_internal" rviz:=true
```

Minta operator menjalankan adapter pengganti dengan URI yang sama menurut
README Husky; preflight tetap berlaku. L4 — dashboard runtime yang sudah ada:

```bash
export BRIN_LAPTOP_IP=192.168.0.218 RMF_WEB_ROOT=/mnt/UbuntuData/rmf-web
export PATH="$RMF_WEB_ROOT/.brin-tools/node-v16.20.2-linux-x64/bin:$RMF_WEB_ROOT/.brin-tools/pnpm/node_modules/.bin:$PATH"
export HOST=127.0.0.1 PORT=3000 BROWSER=none
export REACT_APP_RMF_SERVER="http://$BRIN_LAPTOP_IP:8000"
export REACT_APP_TRAJECTORY_SERVER=ws://localhost:8006
cd "$RMF_WEB_ROOT"
pnpm --filter rmf-dashboard run start:react
```

Jangan gunakan `pnpm start` yang dapat memulai backend tambahan. Runtime harus
sesuai commit pinned di WEB.md; jangan upgrade dependensi saat uji fisik.
Buka `http://localhost:3000`; docs API `http://192.168.0.218:8000/docs`.
Pilih **lantai L1** → HuskyA200 → husky_0 → Patrol → satu putaran ke tujuan
aman. Label L1 pada dashboard adalah nama lantai, bukan terminal laptop L1.
Adapter hanya mendukung Patrol untuk tahap ini. Dengan `rviz:=true`, schedule
visualizer juga menjalankan trajectory server pada port bawaan 8006 di laptop.
Jika visualisasi dinonaktifkan, server ini tidak dimulai oleh core. Masalah
overlay trajectory bukan otomatis bukti fleet adapter terputus. Verifikasi
task benar-benar selesai di lapangan.

## 8. Penghentian dan penanganan kegagalan

1. Hentikan pengiriman task. Batalkan task aktif bila aman, tunggu robot diam.
2. Operator Husky menghentikan adapter terlebih dahulu. Jangan menganggap
   menutup terminal menjamin gerak berhenti; konfirmasi fisik tetap wajib.
3. Operator menghentikan launch Nav2/sensor yang dimulai khusus sesi uji jika
   diperlukan. Jangan menghentikan Clearpath, UM7, SSH atau jaringan.
4. Ctrl-C dashboard/API, lalu core laptop; RViz dan visualizer yang berada
   dalam launch core ikut dihentikan. Jika memakai launch visualisasi
   terpisah, hentikan terminal itu juga. Pastikan proses uji berakhir.
5. Jika robot tidak aman kapan pun, gunakan E-stop lebih dahulu. Jangan
   melepaskannya sebelum task/goal aktif dan sumber perintah ditinjau.

| Gejala | Tindakan aman |
| --- | --- |
| Node tak terlihat | Periksa environment terminal/domain 0, URI Wi-Fi dan IP; jangan ubah service platform |
| SSH timeout | Tidak berarti ROS berhenti; minta pemeriksaan lokal Husky, jangan restart Wi-Fi saat uji |
| Native check gagal | Pertahankan satu core, periksa DDS dan exit code; jangan anggap node list cukup |
| Fleet kosong/robot belum terdaftar | Tinjau preflight, Nav2 dan TF pada Husky; jangan buat pose/fleet palsu |
| Lane/fleet marker kosong | Periksa publisher `/nav_graphs` dan isi `/fleet_states`; adapter harus aktif sesuai tahap E |
| Opsi `rviz` tidak dikenal | Periksa prefix paket; jalankan helper repository agar workspace lama tidak mengalahkan overlay integrasi |
| Peta/scan belum terlihat di RViz | Periksa H1/H2 dan TF navigasi yang sudah dipakai; jangan menambah bridge atau TF statik tebakan |
| Request ditolak/timeout | Simpan respons, cek waypoint dan status sebelum retry |
| Gerak menyimpang/scan tidak cocok | E-stop, hentikan tahap gerak; jangan ubah parameter sensor/TF secara coba-coba |

## 9. Catatan penerimaan

Simpan tanggal, commit kedua mesin, profil/digest, hasil DDS/native/preflight,
nama tujuan, ID task, respons, hasil Nav2, pose awal/akhir, durasi berhenti,
hasil cancel dan hasil Web. Tandai setiap tahap **LULUS / GAGAL / BELUM DIUJI**.
Jangan menyamakan lulus komunikasi dengan lulus operasi fisik.

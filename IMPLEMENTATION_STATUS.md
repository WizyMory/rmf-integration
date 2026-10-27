# Rebuild correction map `brin_0` — 27 Oktober 2026

File yang ditunjuk pengguna berada di `laptop/src/brin_rmf_maps`, sedangkan
correction sebelumnya hanya dibuat di workspace asal `/mnt/UbuntuData/rmf_ws`.
Snapshot repository ini masih memuat policy lama dan correction hash
`c73927fc...`. Policy kedua snapshot lokal (`laptop` dan `husky`) sekarang
memakai known-area polygon lantai 29 untuk `brin_0`, sama dengan
`banyak_simpangan`. Kedua profil diregenerasi dan divalidasi pada masing-masing
snapshot. Building YAML, reference PNG, graph, sensor dan parameter robot
tidak diubah. Report banyak-simpangan hanya berubah pada hash shared policy.

Hasil: polygon kiri atas berisi 62.120 sel, tidak menyisakan sel unknown,
semua sel non-dinding free dan dinding Traffic Editor tetap occupied.
Tambahan correction dari map lama adalah 50.488 unknown-to-free dan 184
reference-occupied-to-free di area yang disetujui. Occupancy dan correction
mask kedua snapshot byte-identik dengan hasil workspace asal dan file install
laptop. Hash occupancy baru `798047169b11697f648975506cbfdb4e02058a65c21da0ace8a18e9358fed04e`;
hash correction `149ee663ddfe46a8ceeb1f6175078152d7b14e4f3c408585d38c766f5002a76d`.
Empat validasi profil/snapshot exit 0: 294 lane lolos, nol blocked lane,
mismatch mask, unexpected pixel atau dinding tidak occupied; reachability utuh.

Perintah generasi, dari root repository, untuk setiap `target=laptop|husky`
dan `profile=brin_0|banyak_simpangan` (`graph=1.yaml` atau
`banyak_simpangan.yaml` sesuai profil):

```bash
python3 "$target/src/brin_rmf_maps/tools/generate_nav2_occupancy.py" --package "$target/src/brin_rmf_maps" --nav2-config laptop/src/brin_husky_nav2/config/nav2.yaml --building "$profile.building.yaml" --graph "$graph" --output-prefix "$profile"
python3 "$target/src/brin_rmf_maps/tools/validate_nav2_occupancy.py" --package "$target/src/brin_rmf_maps" --nav2-config laptop/src/brin_husky_nav2/config/nav2.yaml --building "$profile.building.yaml" --graph "$graph" --output-prefix "$profile"
```

Build/test dari `laptop/`, dengan overlay Humble, Clearpath, BRIN; environment
`COLCON_HOME=$PWD/.colcon`, `ROS_LOG_DIR=$PWD/log/ros`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, dan
`COLCON_EXTENSION_BLOCKLIST=colcon_core.shell.ros_domain_id`:

```bash
colcon build --symlink-install --packages-select brin_rmf_maps --cmake-force-configure
source install/local_setup.bash
colcon test --packages-select brin_rmf_maps --event-handlers console_direct+
colcon test-result --test-result-base build/brin_rmf_maps --verbose
colcon test-result --verbose
python3 -m pytest -q ../husky/src/brin_rmf_maps/test src/brin_husky_distributed/test/test_distributed.py --tb=short
```

Build berhasil; 21 test map laptop lolos, hasil colcon 22 test termasuk wrapper
CTest, tanpa error/failure/skip. Tes map snapshot Husky dan resolusi profil
distribusi pada laptop: 25 lolos. Digest `brin_0` source laptop, install laptop
dan snapshot Husky cocok:
`02b22edc67c190dfed1a7bcff28c87c5cfceb6306561a85570998dc6cbb5f8ab`.
Digest banyak-simpangan tetap `20ec559a...`, sama dengan deployment sebelumnya.
Log tersedia di `laptop/log/validation/map_correction_*`.

Tidak ada SSH/deployment, restart proses aktif, goal, task atau uji gerak.
Snapshot `husky/src` yang diperbarui belum diterapkan ke komputer robot;
penggunaan profil `brin_0` pada kedua mesin memerlukan deployment map yang
sama dan preflight ulang. Pembaruan ini menerima aset peta dan build lokal;
penerimaan runtime/fisik di bawah tetap memiliki batas yang tercatat.

# Status integrasi fisik — 21 Oktober 2026

## Pembaruan: source sudah dipush dan dideploy

Release `6882ca8` sudah dipush ke GitHub dan dibangun terpisah pada laptop
dan Husky. Keduanya berhasil empat paket; uji native adapter pascadeployment
lulus tiga kali dan DDS pulang-pergi lulus. Robot memakai clone baru, bukan
menimpa workspace hardware lama. Tidak ada dispatch, task, atau gerak.
Detail lokasi, hasil, batas verifikasi dan cara memperbarui robot tanpa
menyalin kredensial ada di [hasil deployment](docs/DEPLOYMENT_RESULT_2026-10-21.md).
Bagian berikut merupakan riwayat verifikasi sebelum deployment tersebut.

## Hasil terbaru tahap komunikasi, sampai 15:32 WIB

Profil akhir untuk proses integrasi adalah Cyclone DDS dengan interface Wi-Fi
eksplisit dan peer LAN di `config/cyclonedds_lan.xml` masing-masing target.
Laptop `wlp9s0` → peer `.120`; Husky `wlp2s0` → peer `.218`. Skrip default
memakai profil repository tersebut, bukan URI localhost simulasi. DDS service
Clearpath tetap tidak diubah. Tidak ada deployment source ke robot atau push.

- Native adapter diagnostik Husky ke core laptop hasil build repository:
  **3 proses berturut-turut berhasil dan exit 0**, sekitar 15:26:30–15:26:32.
- DDS dua arah dengan profil yang sama, session `cyclone_wifi_20261021`:
  laptop menerima 3 balasan cocok; Husky menerima/membalas 3 pesan; keduanya
  exit 0. Tidak ada robot/fleet palsu, task atau goal dibuat.
- Versi awal diagnostik start/stop cepat pernah crash saat teardown setelah
  koneksi berhasil. Uji diperbaiki: `Adapter.make` sudah memutar executor
  sementara untuk menyiapkan writer/mirror; tidak perlu background executor.
  Referensi implementasi yang ditinjau: Humble `Adapter::Implementation::make`
  pada `rmf_fleet_adapter/src/rmf_fleet_adapter/agv/Adapter.cpp`.
- Fast DDS sebelumnya pernah lulus, namun pengulangan koneksi native tidak
  konsisten. Keberhasilan satu kali itu bukan alasan menyatakan stabil.
- SSH sempat timeout pada banner/key exchange. Tiga koneksi standar/opsi
  sementara kemudian berhasil. Opsi `IPQoS=none` dipakai pada beberapa uji,
  tetapi hubungan sebab-akibat belum dibuktikan; konfigurasi SSH tidak diubah.
- Output operator 15:21:26 mengonfirmasi metric 700, route laptop via Wi-Fi,
  SSH active, load average 0,98. Neighbor Wi-Fi kedua mesin cocok. Ping kecil
  dan 1400-byte tanpa fragmentasi masing-masing 8/8 berhasil, bukan jaminan
  tidak ada gangguan Wi-Fi jangka panjang.
- Pembacaan laptop selama 7 detik: IMU 134 pesan, odom 326 pesan; usia terakhir
  sekitar -0,04 detik; kedua controller `active`. Ini pembacaan, bukan perintah.
- Tes guard alat deployment/diagnostik: 24 lulus. Tes integrasi terpilih:
  laptop 69 lulus, source snapshot Husky diuji pada laptop 69 lulus.
- Verifikasi akhir gabungan laptop + guard: **93 lulus**. Build ulang empat
  paket laptop berhasil dan XML terpasang di share paket. Skrip default
  repository (URI file laptop, bukan XML inline) berhasil menjalankan core;
  probe native memakai isi file XML Husky dari repository berhasil dan exit 0.
  Route akhir tetap laptop via Wi-Fi dan Hokuyo via USB `.15`.
- Saat Ctrl-C terakhir launcher melaporkan `This event loop is already running`.
  Pemeriksaan proses sesudahnya tidak menemukan executable core diagnostik
  tersisa; ini tetap dicatat sebagai masalah penghentian launcher, bukan
  diklaim sebagai exit launch yang bersih. Tidak ada service robot dihentikan.

Koneksi komunikasi telah dibuktikan dalam uji terbatas, **bukan** fleet fisik
siap menerima task. Nav2/map/scan belum aktif pada audit terakhir; belum ada
preflight fisik lulus, registrasi robot, task/pembatalan bergerak atau Web
end-to-end. Semua core diagnostik laptop dihentikan setelah uji, bukan service
produksi yang dibiarkan aktif. Lihat [panduan deployment](docs/DEPLOYMENT.md).

## Jejak tahap awal komunikasi, 14:53–15:15 WIB

Repository ini menjadi sumber utama untuk push GitHub dan deployment
terpisah ke laptop/Husky. Belum ada push GitHub atau deployment source
repository ke workspace aktif robot. Panduan: [DEPLOYMENT.md](docs/DEPLOYMENT.md).

Perubahan fisik yang disetujui dan dilakukan operator:

- Metric USB Hokuyo 500 menjadi 700; alamat tetap `192.168.0.15/24` dan
  host route sensor `.10/32` metric 50. Verifikasi SSH 14:59 WIB menunjukkan
  profil tersimpan 700, route laptop via Wi-Fi dan sensor tetap USB.
- Instalasi runtime RMF: 25 paket baru, tanpa upgrade/penghapusan. Import
  `rmf_adapter`, `rmf_fleet_msgs`, `rmf_task_msgs` berhasil di Husky.

Tidak ada perubahan API/protokol/IP/port/parameter driver Hokuyo, UM7,
Clearpath, controller, EKF, TF, safety, NAT atau firewall oleh tahap ini.
Driver Hokuyo sudah dibuktikan operator tersambung ke perangkat `L2201993`
dan streaming pada 14:35 WIB; timeout `nc` sebelumnya bukan alasan mengubahnya.

Bukti komunikasi (uji terbatas, bukan operasi fleet):

| Pemeriksaan | Hasil |
| --- | --- |
| Graph domain 0 dari laptop | Node Clearpath, UM7, EKF/controller robot terlihat |
| Pengumuman profil laptop dibaca Husky | Digest `20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7` diterima |
| Native adapter Husky ke schedule laptop | Berhasil; Husky mendaftarkan query update 1 dan schedule laptop mencatat query 1 |
| DDS request/reply, session `link_20261021_a` | Laptop menerima 3 balasan cocok; Husky menerima dan membalas 3 pesan; kedua endpoint lulus |
| Goal, task dan robot yang didaftarkan oleh uji | Tidak ada |

Uji memakai domain 0 dan Fast DDS pada proses integrasi saja; lingkungan
service platform tidak diubah. Core pertama berjalan maksimal 120 detik dan
berhenti karena batas waktu; pesan SIGINT saat penghentian bukan kegagalan
koneksi schedule. Source adapter/preflight/bridge dan konfigurasi fleet robot
yang diperiksa cocok checksum dengan snapshot.

Pada pemeriksaan 14:59 WIB, map/scan Nav2 dan action NavigateToPose belum
terlihat, demikian pula layanan lifecycle bt_navigator. Hanya action kamera
yang terdaftar. Karena itu belum ada preflight fisik lulus, robot terdaftar
di fleet, `/fleet_states` fisik, task Nav2/RMF selesai, atau uji Web end-to-end.
Jangan menyamakan koneksi adapter diagnostik dengan kesiapan navigasi.

Artefak baru: skrip build/run `tools/integration.bash`, uji DDS dan native
adapter, serta tes guard offline. Skrip build hanya memilih empat paket
integrasi; run robot tidak memulai Nav2/Hokuyo otomatis dan dispatch terkunci
secara default. Build laptop langsung dari `laptop/src` repository berhasil
empat paket. CMake memperingatkan pytest tidak ditemukan untuk tes CMake map;
itu bukan bukti tes map sudah dijalankan. Tes guard tool: 20 lulus.

## Riwayat jaringan fisik, 14:09–14:13 WIB (bukan konfigurasi terbaru)

SSH IPv4 pulih setelah operator, mengikuti instruksi sesi ini, mengubah
alamat profil USB Hokuyo dari `192.168.0.15/24` menjadi
`192.168.0.15/32` dan menerapkannya hanya ke interface USB. Rute sensor
`192.168.0.10/32` tetap dipertahankan. Clearpath, controller, dan UM7 tidak
direstart. Ping Hokuyo berhasil, tetapi TCP 10940 masih timeout setelah
sempat berhasil sebelum penerapan profil. Task gerak belum dijalankan.
Detail bukti, batas verifikasi, dan rollback ada di
[catatan pemulihan jaringan](docs/HOKUYO_NETWORK_RECOVERY.md).

Bagian berikut adalah checkpoint awal source/build sebelum audit SSH dan
perbaikan jaringan fisik tersebut; bukan deskripsi lengkap runtime terbaru.

## Checkpoint awal implementasi snapshot

Implementasi di snapshot menggunakan RMF pusat di laptop serta Nav2 dan fleet
adapter onboard di satu Husky. Perubahan sesi ini terbatas pada
`brin_husky_distributed` di kedua snapshot dan dokumentasi repository.
Tidak ada perubahan driver Hokuyo/UM7, TF, EKF, controller, atau batas gerak.
Konfigurasi endpoint LAN Web disiapkan atas persetujuan pengguna; tidak ada
perubahan jaringan aktif, SSH, deployment, task fisik, atau goal Nav2.

## Hasil lokal

| Pemeriksaan | Hasil |
| --- | --- |
| Perbandingan source laptop/Husky sebelum perubahan | Adapter, hardware bridge/preflight, dan aset map sama; Nav2 robot memakai konfigurasi fisiknya sendiri |
| Build Humble snapshot laptop | 4 paket berhasil |
| Build Humble snapshot Husky pada laptop | 4 paket berhasil |
| Tes terpilih laptop | 69 lulus |
| Tes terpilih Husky | 69 lulus |
| API config dengan runtime rmf-web Humble yang terpasang | Import/config berhasil; server tidak dimulai |
| Console `profile_info` hasil instalasi kedua snapshot | Berhasil; 20 tujuan bernama pada L1, digest profil sama |
| Pembacaan argumen launch laptop, robot, Web | Berhasil; tidak menjalankan node robot |
| PNG map Nav2 Husky vs bundle RMF | SHA-256 sama; metadata geometri/threshold sama |

Paket build: `brin_rmf_maps`, `brin_husky_fleet_adapter`,
`brin_husky_hardware`, `brin_husky_distributed`. Artefak verifikasi terpisah
berada di `/tmp/brin-sim-to-real.3JbgLe/{laptop,husky}/`.

Tes terpilih mencakup direktori `brin_husky_distributed/test`,
`brin_husky_hardware/test`, serta `test_command.py` dan
`test_escape_geometry.py` pada fleet adapter. Pemeriksaan meliputi gate
preflight, task/pembatalan, endpoint robot vs localhost, waktu nyata API,
penerusan URI ke dispatcher/adapter, dan daftar waypoint profil.
`ROS_LOG_DIR` diarahkan ke direktori verifikasi karena home read-only pada
sandbox; percobaan tes awal gagal membuat log sebelum ini disetel.

## Belum dibuktikan di lapangan

Build snapshot Husky di laptop bukan build pada komputer robot. Belum ada
verifikasi LAN/DDS dua arah, runtime RMF onboard, driver sensor aktif, scan
selaras dengan peta fisik, lokalisasi stabil, goal Nav2 bergerak, task terminal
selesai, pembatalan ketika bergerak, maupun task browser selesai.

Langkah berikutnya adalah deployment paket yang berubah ke workspace nyata
setelah mendapat persetujuan deployment. Gunakan IP LAN laptop yang sebenarnya
untuk API dan `server_uri`, lalu ikuti penerimaan bertahap pada
[README paket](laptop/src/brin_husky_distributed/README.md) dan
[panduan Web](laptop/src/brin_husky_distributed/WEB.md). Map dan parameter fisik
tetap perlu ditinjau operator sebelum gerak. SOC masih nilai tetap 0,95.

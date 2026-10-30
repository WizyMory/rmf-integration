# Deployment repository: laptop dan Husky

`rmf-integration` menjadi sumber utama. Source laptop dan Husky dipisahkan;
hasil build tidak disalin antar komputer. Push GitHub dan deployment tidak
otomatis dilakukan oleh skrip. Gunakan commit yang sama pada kedua mesin.

## Batas perubahan

- Skrip hanya membangun/menjalankan empat paket integrasi: `brin_rmf_maps`,
  `brin_husky_fleet_adapter`, `brin_husky_hardware`, `brin_husky_distributed`.
- Tidak memasang paket OS, menggunakan SSH/sudo, mengubah jaringan/service,
  mengirim task/goal, atau mengubah file Hokuyo, UM7, Clearpath, EKF, TF/safety.
- Mode `preflight` dan `adapter` mengaktifkan bridge TF integrasi yang sudah
  ada (frame `husky_0`), bukan mengubah konfigurasi TF platform. Aktivasi ini
  harus ditinjau/disetujui sebelum run pada robot fisik.
- Nav2 dan Hokuyo tidak dinyalakan otomatis. Operator menyiapkannya dengan
  konfigurasi robot yang sudah bekerja; jangan membuat node/controller ganda.
- Mode `adapter` dapat menerima task setelah robot terdaftar. Karena itu
  dibutuhkan penerimaan fisik dan persetujuan dispatch, bukan sekadar flag.
  Launch tetap memerlukan preflight; tidak ada bypass keselamatan.

## 1. Persiapan kedua komputer

Setelah repository tersedia di GitHub, clone pada masing-masing mesin ke
direktori terpisah dari workspace lama. Checkout commit yang sama dan catat
`git rev-parse HEAD`. Jangan menimpa `/mnt/UbuntuData/rmf_ws` atau
`/home/husky/rmf_ws`. Jalankan perintah berikut dari root clone repository.
Jangan salin hasil build, `.env`, key SSH, password, atau log sensor ke GitHub.

Underlay bawaan sesuai komputer yang diaudit:

| Target | File setup sebelum overlay repository |
| --- | --- |
| laptop | `/opt/ros/humble/setup.bash`, `/mnt/UbuntuData/clearpath_ws/install/local_setup.bash`, `/mnt/UbuntuData/BRIN_ws/install/local_setup.bash` |
| husky | `/opt/ros/humble/setup.bash`, `/etc/clearpath/setup.bash`, `/home/husky/ros2_ws/install/local_setup.bash` |

Untuk lokasi underlay RMF berbeda, set `BRIN_RMF_UNDERLAY` ke file setup yang
benar. Gunakan terminal baru, tanpa overlay simulasi. Skrip berhenti bila
runtime tidak tersedia; tidak melakukan instalasi diam-diam. Tinjau warning
colcon jika paket integrasi juga ada di underlay. Overlay repository harus
memiliki prioritas saat run, bukan paket workspace lama.

Prasyarat RMF Husky telah dipasang operator pada 21 Oktober 2026 dengan:

```bash
sudo apt-get install --no-install-recommends \
  ros-humble-rmf-fleet-adapter-python \
  ros-humble-rmf-fleet-msgs ros-humble-rmf-task-msgs
```

Ini catatan prasyarat, bukan instalasi otomatis. Adapter native versi `2.1.8`;
transaksi robot menambah 25 paket tanpa upgrade/penghapusan paket lain.
Jangan menambahkan `apt upgrade` atau `autoremove` ke deployment integrasi.

## 2. Build hanya target mesin tersebut

Laptop:

```bash
bash tools/integration.bash laptop build
bash tools/integration.bash laptop profile traffic_profile:=banyak_simpangan
```

Husky, setelah deployment disetujui:

```bash
bash tools/integration.bash husky build
bash tools/integration.bash husky profile traffic_profile:=banyak_simpangan
```

Artefak berada di `<target>/build`, `<target>/install`, `<target>/log` dan
diabaikan Git. Jangan membangun kedua `src` dalam satu pencarian colcon atau
menyalin artefak laptop ke robot. Tidak perlu membangun ulang `hokuyo_bringup`
atau `husky_nav2` untuk perubahan komunikasi ini. Bandingkan digest kedua
`profile`; profil bawaan `banyak_simpangan` pada L1. Kesamaan digest bukan
bukti peta cocok dengan lokasi robot sebenarnya.

## 3. Jalankan RMF core laptop

Pastikan tidak ada core/adapter lain. Jangan menjalankan launch simulasi atau
hardware monolitik bersamaan. Di terminal laptop:

```bash
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan
```

Skrip menetapkan domain `0`, `ROS_LOCALHOST_ONLY=0`, Cyclone DDS dan waktu nyata
khusus proses integrasi, setelah sourcing. Shell induk dan service Clearpath
tidak diubah. Default memakai profil `config/cyclonedds_lan.xml` milik target:

| Target | Interface DDS | Peer LAN |
| --- | --- | --- |
| laptop | `wlp9s0` | Husky `192.168.0.120` |
| husky | `wlp2s0` | laptop `192.168.0.218` |

Profil memakai SPDP multicast serta peer unicast, participant index otomatis
dengan rentang maksimum 40. Ini konfigurasi proses komunikasi, **bukan** IP
interface, driver sensor atau DDS service platform. Jika IP/interface berubah,
tinjau profil di Git sebelum deployment. Pemilihan interface mengikuti
[dokumentasi Cyclone DDS 0.10.5](https://cyclonedds.io/docs/cyclonedds/0.10.5/config/cyclonedds_specifics.html).

Skrip sengaja tidak mewarisi `CYCLONEDDS_URI` simulasi; override yang disengaja
memakai `BRIN_RMF_CYCLONEDDS_URI`. `BRIN_RMF_RMW` dapat mengganti RMW, tetapi
perlu uji ulang. Jalur Fast DDS pernah berhasil lalu gagal pada pengulangan;
bukan default yang dipilih untuk alur ini. Jangan gunakan profil localhost.
Discovery server warisan yang belum ditinjau ditolak. Core foreground; Ctrl-C
menghentikan core terminal itu, bukan service robot. Jangan membuat dua core.

## 4. Verifikasi komunikasi tanpa gerak

Pada terminal diagnostik masing-masing mesin, source underlay sesuai tabel
dan `<target>/install/local_setup.bash`, lalu **setelah sourcing**:

```bash
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
unset ROS_DISCOVERY_SERVER
export ROS_LOG_DIR=/tmp/rmf-link-diagnostic
```

Pilih **satu** baris URI sesuai terminal, dari root clone repository:

```bash
# Laptop saja
export CYCLONEDDS_URI="file://$PWD/laptop/src/brin_husky_distributed/config/cyclonedds_lan.xml"
```

```bash
# Husky saja
export CYCLONEDDS_URI="file://$PWD/husky/src/brin_husky_distributed/config/cyclonedds_lan.xml"
```

Unset discovery server hanya untuk jalur LAN biasa yang telah diaudit.
Uji ini tidak membutuhkan sensor/Nav2 dan tidak membuktikan kesiapan gerak.
Mulai pasangan DDS dalam rentang 30 detik, laptop lebih dahulu:

```bash
# Terminal laptop
timeout --signal=INT --kill-after=3s 35s python3 tools/dds_roundtrip.py \
  --role laptop --session penerimaan_01 --timeout 30
```

```bash
# Terminal Husky
timeout --signal=INT --kill-after=3s 25s python3 tools/dds_roundtrip.py \
  --role robot --session penerimaan_01 --timeout 20
```

Keduanya harus `passed: true`; laptop menerima minimal 3 balasan. Gunakan
session berbeda tiap pengujian. Hanya topic diagnostik
`/brin_link_check/<session>/request` dan `/reply` bertipe `std_msgs/String`;
tidak menggunakan topic kontrol, task API, atau action Nav2.

Dengan tepat satu core laptop aktif, pada Husky:

```bash
timeout --signal=INT --kill-after=3s 25s python3 tools/native_adapter_check.py
```

Lulus jika `native_adapter_connected_to_schedule: true` **dan exit code 0**.
JSON sukses lalu crash/timeout bukan kelulusan. Runtime RMF asli
mendaftarkan query schedule, **bukan robot/fleet palsu**. Ini belum membuktikan
robot terdaftar atau status `/fleet_states` fisik tersedia.

Alat diagnostik hanya memanggil `Adapter.make`, yang pada implementasi Humble
memutar executor sementara sampai writer/mirror schedule siap. Tidak perlu
menyalakan background executor untuk uji koneksi. Versi awal uji pernah crash
saat teardown setelah start/stop cepat; versi repository diperbaiki dan lulus
tiga proses berurutan pada Husky. Ini bukan perubahan lifecycle adapter fisik.

## 5. Aktivasi adapter fisik berikutnya

Tahap ini belum dijalankan dalam uji komunikasi. Memerlukan persetujuan
aktivasi Nav2/bridge, operator siap pada E-stop, scan nyata, peta yang sesuai,
AMCL dan initial pose benar. Jangan mengarang pose, TF, atau status robot.

Setelah operator menyiapkan Nav2/sensor yang sudah bekerja, pada Husky:

```bash
bash tools/integration.bash husky preflight traffic_profile:=banyak_simpangan
```

Preflight tidak mengirim goal; menolak data hilang/stale, konflik TF, Nav2
belum aktif, core ganda atau digest berbeda. Cari JSON `accepted: true` dan
`errors: []`, bukan hanya exit code launch. Jika gagal, tinjau penyebabnya.

Hanya setelah penerimaan fisik selesai dan dispatch diizinkan:

```bash
BRIN_ENABLE_DISPATCH=1 bash tools/integration.bash husky adapter \
  traffic_profile:=banyak_simpangan
```

Periksa robot `husky_0` dalam fleet `HuskyA200`, pose/status nyata, dan tidak
ada adapter ganda. Task terminal, pembatalan saat bergerak dan task browser
memerlukan penerimaan berikutnya; tidak dikirim oleh skrip ini. Untuk Web
lihat [panduan Web](../laptop/src/brin_husky_distributed/WEB.md).

## Jaringan dan rollback

Perubahan yang telah diterapkan operator: metric USB `500` menjadi `700`.
Profil `ddd9b820-1753-3bc6-9609-2d58cba97bc5` tetap memakai `.15/24` dan
route sensor `.10/32` metric 50. Wi-Fi metric 600 memenangkan route laptop.

```bash
ip -4 route get 192.168.0.218 from 192.168.0.120
ip -4 route get 192.168.0.10
```

Harus menunjukkan `wlp2s0` untuk laptop dan `enx00e04ca286d9` untuk Hokuyo.
API, protokol, IP/port dan parameter driver Hokuyo tidak boleh diubah.
`hokuyo-nat.service` tidak diubah. Persistensi routing setelah reboot belum
diuji; jangan reboot robot sebagai bagian uji ini tanpa persetujuan.

Rollback metric ke 500 akan mengembalikan konflik dan risiko putus SSH.
Hanya lakukan dari konsol lokal dengan persetujuan, bukan rollback remote
otomatis. Jangan restart NetworkManager/Wi-Fi. Rollback kode: hentikan proses
integrasi foreground, checkout commit sebelumnya pada clone bersih, build
ulang target itu. Jangan reset destruktif workspace lama. Tinjau transaksi apt
sebelum rollback paket OS; jangan menghapus dependensi bersama/autoremove.

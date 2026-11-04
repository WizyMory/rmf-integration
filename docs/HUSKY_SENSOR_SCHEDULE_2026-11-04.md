# Husky: penerimaan sensor dan koneksi schedule, 4 November 2026

Preflight operator menolak `No IMU from physical robot` meskipun topic
`/a200_1060/sensors/imu_0/data` terdaftar. Pendaftaran topic saja tidak
membuktikan pesan diterima: subscriber juga membuat nama topic terlihat.

Pengamat lokal robot selama 12 detik menunjukkan:

| Pemeriksaan | Cyclone DDS integrasi | Fast DDS native |
| --- | --- | --- |
| Sampel IMU | 0 | 230, umur terakhir sekitar 0.002 s |
| Sampel odometri | 533 | 574, umur terakhir sekitar 0.002 s |
| Nav2 lifecycle get_state | active | Tidak mendapat balasan |
| Controller list | Tidak mendapat balasan | Kedua controller active |

UM7 dan service sensor aktif. Pengamat Cyclone reliable juga tidak menerima
IMU. Satu preflight sesudah perbaikan IMU menerima IMU tetapi tidak menerima
odometri; log operator berikutnya berhasil melewati seluruh gate. Jalur
sensor lintas implementasi DDS pada sesi ini tidak konsisten. Mengganti
seluruh RMW integrasi belum terverifikasi untuk layanan Nav2.

Perbaikan menggunakan `brin_husky_hardware.sensor_source` sebagai subprocess
Fast DDS untuk membaca IMU dan odometri fisik. Bridge utama tetap Cyclone.
Pesan dibawa melalui pipe CDR/base64, mempertahankan field sensor,
covariance, frame asli dan timestamp. Bridge menerapkan prefix frame seperti
sebelumnya. Tidak ada timestamp baru atau sampel tiruan. Jika pembaca
berhenti, tidak ada sampel yang diteruskan; preflight tetap menolak data
hilang atau usang. Proses child dibersihkan saat bridge berhenti.

Satu preflight kemudian menerima kedua sensor tetapi tidak menerima subtree
TF statis IMU melalui Cyclone. Pemeriksaan native membuktikan transform
`base_link -> imu_0_base_link -> imu_0_link` tersedia pada
`/a200_1060/tf_static`. Worker kini juga menerima topic fisik tersebut dengan
QoS transient local reliable, mempertahankan semua batch dari setiap writer,
lalu meneruskannya melalui fungsi merge TF bridge yang sudah ada. Sumber,
geometri dan authority transform tetap sama; tidak ada transform buatan.

Launcher fisik pada snapshot laptop dan Husky mengatur
`sensor_source_rmw=rmw_fastrtps_cpp`. Driver, konfigurasi Clearpath/UM7,
topic/aturan TF, domain ROS, Nav2 dan gate keselamatan tidak diubah. Reader
default pada bridge standalone tetap langsung melalui RMW proses tersebut.

Masalah berikutnya pada log operator adalah 60 kali kegagalan schedule
sesudah preflight accepted. Core laptop terverifikasi aktif dengan Cyclone
DDS dan domain 0. Endpoint schedule terlihat dari robot. Adapter memberi
waktu discovery satu detik per percobaan dan membuat client baru setelah
gagal. Probe native tanpa fleet berhasil, sedangkan probe context gabungan
dengan urutan awal tidak konsisten. Dengan context C++ diinisialisasi dahulu
dan discovery 15 detik, probe HardwareFleetNode asli menyelesaikan handshake
dalam sekitar 9.5 detik. Adapter fisik kini memakai urutan tersebut dan
maksimal enam percobaan 15 detik.

Probe hanya membuat schedule mirror; tidak ada fleet atau robot yang
didaftarkan, task dikirim, atau goal/kecepatan diterbitkan oleh validasi ini.
Uji dispatch penuh tetap dilakukan operator. Perintah adapter tetap sama:

```bash
export BRIN_LAPTOP_IP=192.168.0.218
BRIN_ENABLE_DISPATCH=1 bash tools/integration.bash husky adapter \
  traffic_profile:=gedungWS_0 \
  server_uri:="ws://$BRIN_LAPTOP_IP:8000/_internal"
```

Build paket hardware/distributed dilakukan pada overlay laptop dan Husky.
Tes terarah laptop: 31 lulus. Tes hardware/distributed Husky lulus 64 kasus
sesudah deployment. Preflight final di robot melaporkan `errors: []` dan
`accepted: true`, dengan pose sekitar `(25.55, -24.76)`. Bridge berhenti
bersih setelah preflight tanpa dispatch. Tes awal lengkap laptop lulus 104; pengulangan
tes RViz terpisah menemukan edit bersamaan pada `devi_rmf.rviz` yang tidak
terkait perbaikan ini. File RViz tersebut dipertahankan dan tidak disertakan
dalam commit perbaikan.

Hasil preflight final dan log tersimpan pada
`husky/log/validation/sensor_schedule_20261104/` di kedua clone perangkat.
Backup deployment robot berada di folder yang sama. Tidak ada restart
service platform/sensor atau perubahan domain Devi.

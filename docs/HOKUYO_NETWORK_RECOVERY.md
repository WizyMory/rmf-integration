# Pemulihan jaringan Husky dan Hokuyo — 21 Oktober 2026

## Keadaan terbaru: metric USB 700, driver Hokuyo bekerja

Riwayat `/32` dan timeout TCP di bawah bukan konfigurasi/rekomendasi terbaru.
Pada 14:35 WIB operator menjalankan driver Hokuyo yang tersambung ke perangkat
`L2201993` dan streaming. API, protokol, IP/port dan konfigurasi driver tidak
boleh diubah untuk pekerjaan integrasi ini. Tidak perlu power-cycle berdasarkan
capture lama tersebut.

Sesudah audit kembali menunjukkan USB `.15/24` metric 500 dan route laptop
salah, operator menyetujui/menerapkan hanya perubahan metric USB menjadi 700:

```bash
sudo nmcli connection modify uuid ddd9b820-1753-3bc6-9609-2d58cba97bc5 ipv4.route-metric 700
sudo nmcli device reapply enx00e04ca286d9
```

Pada 14:59 WIB profil tersimpan `.15/24`, host route `.10/32` metric 50,
metric USB 700. Laptop `.218` melalui Wi-Fi `wlp2s0`; Hokuyo `.10` tetap USB
`enx00e04ca286d9`, source `.15`. SSH IPv4, request/reply DDS dua arah dan koneksi
native adapter RMF ke schedule laptop berhasil setelah perubahan ini.
Persistensi setelah reboot belum diuji. Jangan restart jaringan/robot.
Rollback metric ke 500 mengembalikan konflik SSH; hanya dengan persetujuan
melalui konsol lokal. NAT lama tidak diubah. Detail deployment/verifikasi
ada di [DEPLOYMENT.md](DEPLOYMENT.md).

## Catatan historis sebelum driver terbukti bekerja

Scope yang disetujui: perbaikan jaringan minimal setelah audit baca-saja.
Tidak ada deployment ROS, build di robot, perubahan controller/TF, atau goal
gerak. Perubahan profil sistem memerlukan sudo lokal; operator menjalankan
dua perintah NetworkManager yang diberikan, lalu agen memverifikasi hasil
melalui SSH. Tidak ada password yang diminta melalui chat.

## Penyebab SSH terputus

Profil `Wired connection 2`, UUID
`ddd9b820-1753-3bc6-9609-2d58cba97bc5`, terikat ke adapter Realtek
`enx00e04ca286d9` (MAC `00:e0:4c:a2:86:d9`). Profil memakai
`192.168.0.15/24`, metric 500, tanpa gateway, dan `never-default=yes`.
Wi-Fi robot memakai `192.168.0.120/24`, metric 600. Keduanya menghasilkan
connected route ke `192.168.0.0/24`; rute USB memenangkan lookup ke laptop.

Bukti sebelum perubahan, 14:07 WIB:

```text
192.168.0.218 from 192.168.0.120 dev enx00e04ca286d9
```

Ini salah interface untuk balasan SSH. SSH IPv4 timeout sebelum autentikasi.
Akses pemeliharaan berhasil melalui IPv6 link-local Wi-Fi robot dengan
verifikasi host key tetap memakai identitas `192.168.0.120`.

## Perubahan yang diterapkan operator

```bash
sudo nmcli connection modify uuid ddd9b820-1753-3bc6-9609-2d58cba97bc5 ipv4.addresses '192.168.0.15/32'
sudo nmcli device reapply enx00e04ca286d9
```

Hanya prefix alamat USB yang berubah. Host route sensor yang sudah ada
(`192.168.0.10/32`, metric 50), metric profil 500, gateway kosong,
`never-default=yes`, Wi-Fi, dan interface `enp1s0` dipertahankan.
Profil tersimpan memakai `/32`; persistensi setelah reboot belum diuji.

Bukti sesudah perubahan, 14:09 WIB:

```text
192.168.0.218 from 192.168.0.120 dev wlp2s0
192.168.0.10 dev enx00e04ca286d9 src 192.168.0.15
```

## Verifikasi dan batas hasil

- Beberapa koneksi SSH IPv4 baru berhasil selama 14:09–14:13 WIB.
- Ping robot ke laptop berhasil 2/2; ping Hokuyo setelah perubahan 3/3,
  tanpa loss, RTT sekitar 0,68 ms.
- TCP 10940 berhasil satu kali pada 14:08 WIB sebelum penerapan profil,
  tetapi percobaan sesudahnya timeout, termasuk ketika source socket
  secara eksplisit di-bind ke `192.168.0.15`. Tidak ada perintah protokol
  lidar yang dikirim pada pemeriksaan tersebut. Penyebab TCP belum dipastikan.
- Controller `joint_state_broadcaster` dan `platform_velocity_controller`
  tetap `active`. Data UM7 sekitar 19,1 Hz dan odometri terfilter sekitar
  48,2 Hz diterima oleh pengamat lokal robot pada 14:10 WIB.
- PID `clearpath-platform.service` tetap 1688, sensor tetap 1690, dan relay
  TF tetap 1647. Tidak ada restart service oleh perbaikan ini.
- Pengamatan DDS Fast di laptop selama enam detik pada 14:10 WIB belum
  menerima IMU/odom atau balasan daftar controller. Pengiriman DDS lintas
  komputer belum boleh dinyatakan pulih.
- `hokuyo-nat.service` tidak diubah. Unit lama menunjuk
  `enx00e04c3e1f30`, berbeda dari interface aktual. Kebutuhan forwarding
  Orin perlu ditinjau sebelum service/aturan NAT itu diubah.

## Tindak lanjut capture TCP, 14:16–14:19 WIB

Capture dari konsol lokal yang diberikan operator mencatat dua SYN dari
`192.168.0.15:33496` ke `192.168.0.10:10940`, tanpa SYN-ACK atau RST
yang terlihat pada interface USB selama delapan detik. Capture tidak
kehilangan paket menurut statistik tcpdump. Ini menunjukkan SYN telah
mencapai titik capture keluar USB; bukan bukti bahwa paket pasti diterima
dan diproses sensor.

Pemeriksaan SSH berikutnya mengonfirmasi rute laptop tetap Wi-Fi dan
Hokuyo tetap USB. Ping sensor masih berhasil 2/2. Tidak ada koneksi TCP
10940 atau proses URG/Hokuyo/Nav2 yang ditemukan pada Husky. Link adapter
`r8152` adalah 100 Mb/s Full Duplex, dengan counter RX/TX error dan drop
nol pada saat dibaca. Ini belum menyingkirkan semua kemungkinan masalah
perangkat, firmware, kabel, filter, atau klien dari komputer lain.

`ufw.service` melaporkan active, tetapi `/etc/ufw/ufw.conf` berisi
`ENABLED=no`; service active tidak boleh disamakan dengan pembuktian bahwa
firewall UFW memblokir sensor. Tidak ada firewall/offload/NAT yang diubah.
Tidak ada SYN-ACK yang terlihat pada capture USB, sehingga menonaktifkan
firewall global bukan perbaikan yang didukung bukti ini.

Pemulihan SSH sudah diverifikasi; TCP sensor belum lulus. Power-cycle sensor
atau perubahan hardware lain memerlukan persetujuan terpisah, dengan
pasokan daya sensor dapat dipisahkan dari Husky/UM7. Jangan melakukan
factory reset/IP reset atau reboot seluruh robot untuk percobaan ini.

## Rollback terbatas

Nilai awal `ipv4.addresses` adalah `192.168.0.15/24`. Mengembalikannya dan
melakukan reapply USB mengembalikan keadaan awal, termasuk konflik subnet
dan risiko putus SSH IPv4. Karena itu rollback harus dilakukan dari konsol
lokal atau akses IPv6 pemeliharaan, dengan rute pemulihan SSH yang ditinjau
terlebih dahulu. Jangan restart NetworkManager atau Wi-Fi untuk rollback
perubahan profil USB ini.

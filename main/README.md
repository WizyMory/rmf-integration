# Komputer utama — Open-RMF core

Core utama berjalan pada **`rslab@192.168.0.141`**, hostname `rfm-pc`,
alias SSH `komputer-utama`. Workspace: `/home/rslab/rmf-integration`.
Saat boot, core, Web API dan dashboard dimulai sebagai layanan pengguna.
Desktop `rslab` masuk otomatis dan membuka RViz serta Chrome Guest untuk
dashboard. Laptop `192.168.0.218` tetap dapat dipakai untuk observasi dan CLI.
Panduan lengkap: [bringup otomatis](BOOT_BRINGUP_2026-11-09.md).

Web: **http://192.168.0.141:3000**. API: **http://192.168.0.141:8000**.

Dashboard menyediakan baterai hardware (SOC/voltase) dan **New Task → Patrol**
dengan pilihan waypoint, putaran, bidding otomatis atau robot tertentu.
Devi memakai estimasi linear 15–25 V. Petunjuk build, hasil deployment dan
batas pengujian: [update Web 10 November](WEB_UPDATE_2026-11-10.md).

| Komputer | Peran |
| --- | --- |
| Komputer utama `.141` | Satu core RMF, Web API/dashboard, publisher visualisasi, RViz dan browser desktop |
| Laptop `.218` | RViz, observasi dan CLI task sesuai penerimaan operator |
| Husky `.120` | Sensor, Nav2, bridge dan adapter yang sudah ada |
| Devi `.237` | Nav2 domain `73`, gateway lokal dan adapter RMF domain `0` yang sudah ada |

Core memakai domain **`0`**, **Cyclone DDS**, **waktu nyata**, profil
**`gedungWS_0`**, lantai **`L1`**. Interface khusus proses RMF pada server
adalah `enp7s0`. Konfigurasi IP, routing, firewall dan service hardware
tidak diatur oleh launcher ini.

Digest aset yang dipakai pada kedua komputer:

```text
dff016256abf2c1c0482212c97272f7cb36fc49dbbd4794185196e61afa8dd99
```

## Mengakses dan memeriksa

```bash
ssh komputer-utama
cd /home/rslab/rmf-integration
systemctl --user status brin-rmf-core.service --no-pager -l
bash tools/main.bash status
journalctl --user -u brin-rmf-core.service -n 80 --no-pager
```

`healthy: true` memerlukan tepat satu dari setiap node core, satu publisher
digest, digest sesuai aset terpasang dan building map yang berhasil dimuat.
Kolom `fleets` melaporkan fleet yang benar-benar diterima selama observasi;
daftar kosong menunjukkan registrasi robot belum teramati. Pemeriksaan ini
tidak mengirim task atau goal Nav2.

Layanan pengguna `brin-rmf-core.service` dijalankan tanpa jendela RViz.
RViz dibuka terpisah oleh `brin-rmf-rviz.service` setelah desktop siap;
`brin-rmf-browser.service` membuka dashboard yang dilayani pada port `3000`.
Layanan di-enable dan lingering pengguna `rslab` diaktifkan agar layanan
dapat mulai saat boot dan tetap berjalan setelah logout. Persistensi reboot
perlu diverifikasi pada reboot terjadwal; migrasi tidak me-reboot komputer.

```bash
systemctl --user stop brin-rmf-core.service
systemctl --user start brin-rmf-core.service
```

Hentikan core setelah task aktif diselesaikan/dibatalkan dan robot dipastikan
diam oleh operator. Launcher mengunci instance lokal dan memeriksa graph ROS
sebelum startup untuk menolak core yang sudah ditemukan di LAN.

## Source dan build

Server membangun source integrasi laptop ke `main/build` dan `main/install`.
`main/src/brin_rmf_maps` memasang aset otoritatif dari
`laptop/src/brin_rmf_maps` tanpa membangun plugin simulator Gazebo.
Snapshot laptop/Husky dan workspace hardware tidak ditimpa.

Prasyarat Ubuntu 22.04/ROS 2 Humble:

```bash
bash main/install-dependencies.bash --check
sudo bash main/install-dependencies.bash --install
bash tools/main.bash build
bash tools/main.bash profile traffic_profile:=gedungWS_0
```

Skrip dependensi menolak transaksi yang mengganti atau menghapus paket
terpasang. Core RMF dan adapter native memakai versi `2.1.8`, message
internal `3.0.4`. Paket apt Humble pada server menyediakan building map tools
`1.6.3` dan RMW Cyclone `1.3.5`; laptop memakai masing-masing `1.6.2` dan
`1.3.4`. Digest aset, building map dan koneksi native schedule diperiksa
secara terpisah.

Untuk debugging foreground setelah menghentikan layanan:

```bash
bash tools/main.bash core traffic_profile:=gedungWS_0
```

Untuk RViz langsung pada desktop komputer utama, tambahkan `rviz:=true`.
Core default sudah mengirim marker dan TF observasi untuk RViz di laptop.

## RViz dan CLI dari laptop

Dengan core utama tetap berjalan, dari terminal laptop:

```bash
cd /mnt/UbuntuData/rmf-integration
export BRIN_RMF_CYCLONEDDS_URI="file://$PWD/main/config/cyclonedds_laptop.xml"
bash tools/integration.bash laptop view
```

Perintah ini membuka RViz saja. Gunakan publisher observasi milik core utama;
pertahankan tepat satu schedule dan dispatcher. Profil observasi terpisah
`main/config/cyclonedds_laptop.xml` memakai interface laptop `wlp9s0` dan
mencantumkan peer core `.141` secara langsung, serta Husky/Devi. Gunakan
export yang sama untuk terminal CLI laptop. Profil LAN lama tetap tersedia.
Tiga proses observasi baru dan koneksi native lulus dengan profil ini;
lihat [hasil build dan pengujian](BUILD_TEST_RESULT_2026-11-09.md).

Console task tersedia pada komputer utama:

```bash
cd /home/rslab/rmf-integration
bash tools/main.bash task
```

Console laptop tetap tersedia dengan `bash tools/integration.bash laptop task`.
Registrasi fleet, kesiapan Nav2, pose nyata, dan penerimaan operator tetap
diperiksa sebelum pengiriman task. Migrasi ini tidak mengirim task, goal,
cancel, initial pose atau perintah hardware.

## Endpoint adapter dan Web

Discovery core memakai peer Husky `.120` dan Devi `.237`. Publisher multicast
dan handshake native LAN tetap aktif. Konfigurasi Nav2 Devi domain `73`
dipertahankan.

Web memakai checkout Humble `e2861c292bb27014435452e74faa825ecb0e8d91`
di `/home/rslab/rmf-web`, virtualenv baru dan build dashboard produksi pada
`main/log/web/dashboard`. API memakai waktu nyata dan database terpisah
`main/log/rmf_web_real/api.sqlite3`. Tidak ada kompilasi dashboard saat boot.

`brin-rmf-core.service` menghubungkan dispatcher ke
`ws://192.168.0.141:8000/_internal`. Adapter Devi kini memakai endpoint yang
sama setelah perbaikan koneksi Web, dengan Nav2 dan sensor tetap berjalan.
Posisi robot dan metadata task diterima dari telemetry native; lihat
[hasil perbaikan data Web](WEB_DATA_RESULT_2026-11-09.md). Keberhasilan
registrasi dan telemetry tidak membuktikan penerimaan gerak robot.

## Kembali ke core laptop

Setelah operator memastikan kedua robot diam, hentikan dan disable layanan
core utama sebelum memulai core laptop:

```bash
systemctl --user disable --now brin-rmf-core.service
```

Lalu ikuti [panduan laptop](../laptop/readme.md) untuk memulai tepat satu core.
Source, konfigurasi dan hasil build laptop sebelumnya tetap tersedia.

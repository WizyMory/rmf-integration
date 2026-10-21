# Hasil push dan deployment — 21 Oktober 2026

Deployment dilakukan atas permintaan operator sesudah tahap audit dan uji
komunikasi. Ini deployment source/build terpisah, bukan aktivasi operasi
robot atau pemasangan service autostart.

## Release dan lokasi

- GitHub: `https://github.com/WizyMory/rmf-integration`, branch `main`.
- Commit source yang dipush dan dibangun:
  `6882ca821ba25126ba32db7f8f4d8866731d4afe`.
- Laptop: `/mnt/UbuntuData/rmf-integration`, hanya target `laptop` dibangun.
- Husky: clone baru `/home/husky/rmf-integration`, hanya target `husky`
  dibangun langsung di robot. Workspace lama tidak ditimpa.
- Commit dokumentasi sesudah release hanya mencatat hasil ini; tidak mengubah
  source paket yang dibangun. Kedua checkout disinkronkan setelah pencatatan.

Husky belum memiliki kredensial untuk fetch HTTPS repository ini. Karena itu
commit dikirim sebagai **Git bundle melalui SSH**, diverifikasi dan di-clone
di robot; origin tetap URL GitHub di atas. Tidak ada token/private key laptop
disalin. Pembaruan berikutnya perlu akses GitHub robot sendiri atau bundle
dari laptop; jangan menganggap `git pull` di robot sudah terautentikasi.

## Hasil verifikasi

| Pemeriksaan | Hasil |
| --- | --- |
| Push release dan pembacaan ulang HEAD GitHub | Cocok dengan `6882ca8` |
| Build di laptop | 4 paket berhasil |
| Build langsung di Husky | 4 paket berhasil |
| Prefix empat paket di Husky | Semua dari `/home/husky/rmf-integration/husky/install/` |
| Import modul adapter Husky | Dari `husky/build/brin_husky_hardware`, symlink install clone baru |
| Digest profil kedua mesin | Sama: `20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7` |
| Native adapter hasil deployment → core laptop | 3 proses berurutan berhasil, exit 0 |
| Pengumuman profil laptop → Husky | Diterima melalui DDS |
| DDS session `deploy_6882ca8` | Laptop menerima 3 balasan cocok; Husky menerima/membalas 3 pesan; keduanya exit 0 |
| Tes gabungan laptop | 93 lulus |
| Tes guard offline pada Husky | 24 lulus |
| Checksum Hokuyo di workspace robot lama | Cocok dengan snapshot; parameter/launch tidak berubah |
| Route Husky ke laptop | `wlp2s0` |
| Route Husky ke Hokuyo | `enx00e04ca286d9`, source `192.168.0.15` |

Empat paket: `brin_rmf_maps`, `brin_husky_fleet_adapter`,
`brin_husky_hardware`, `brin_husky_distributed`. Tidak ada hasil build laptop
disalin ke robot. CMake/unit test seluruh repository bukan cakupan kelulusan
93/24 di atas; daftar tes terpilih ada di status implementasi.

Komunikasi RMF diuji pada domain 0, Cyclone DDS, waktu nyata dan profil Wi-Fi
per target. Beberapa koneksi SSH IPv4 timeout sebelum menjalankan perintah;
jalur IPv6 link-local dengan host key yang sama digunakan untuk uji akhir.
**Data DDS tetap IPv4** sesuai profil peer, bukan tunnel SSH. Gangguan SSH
intermiten belum boleh dianggap sepenuhnya terselesaikan.

## Yang tidak dilakukan

Tidak mengubah jaringan/service pada tahap deployment ini; tidak menyalakan
Nav2, Hokuyo, controller, bridge TF fisik, atau adapter dispatch. Tidak ada
task, goal atau kecepatan dikirim, dan tidak ada robot/fleet palsu dibuat.
Core laptop hanya dijalankan sementara untuk verifikasi, lalu dihentikan.
Tidak mengubah shell startup atau menyiapkan service autostart.

Registrasi `husky_0`, preflight fisik, lokalisasi, navigasi, task terminal,
pembatalan saat bergerak, dan RMF Web end-to-end belum diuji. Deployment kode
yang berhasil tidak sama dengan robot siap beroperasi mandiri.

## Pemakaian setelah deployment

Di laptop, dari root repository:

```bash
bash tools/integration.bash laptop profile
bash tools/integration.bash laptop core traffic_profile:=banyak_simpangan
```

Di Husky, dari `/home/husky/rmf-integration`:

```bash
bash tools/integration.bash husky profile
```

Preflight/dispatch berikutnya mengikuti [DEPLOYMENT.md](DEPLOYMENT.md) dan
memerlukan penerimaan fisik serta persetujuan aktivasi bridge/Nav2. Jangan
menambahkan service auto-run atau melewati gate untuk sekadar membuat robot
terlihat online. Rollback kode dapat menggunakan checkout release sebelumnya
pada clone terpisah; workspace hardware lama tetap tersedia.

# Bringup otomatis komputer utama — 9 November 2026

Pembaruan setelah tahap bringup: koneksi telemetry Devi dan data Web task
telah dipulihkan. Lihat [hasil perbaikan data Web](WEB_DATA_RESULT_2026-11-09.md).

## Perilaku saat boot

1. User manager `rslab` tersedia melalui lingering. Unit network menunggu
   interface `enp7s0` memiliki alamat `192.168.0.141`, maksimum 90 detik.
2. `brin-rmf.target` memulai satu RMF core, Web API dan dashboard produksi.
3. GDM masuk otomatis sebagai `rslab`.
4. Entri GNOME autostart mengimpor environment display sesi yang baru,
   lalu memulai RViz dan browser. RViz menunggu core sehat; browser menunggu
   API dan dashboard menghasilkan HTTP 200.

Core memakai profil `gedungWS_0`, domain `0`, Cyclone DDS dan waktu nyata.
RViz memakai preset laptop yang sudah ada dengan remap observasi yang sama.
Publisher visualisasi tetap dimiliki core. GUI tidak membuat schedule,
dispatcher atau publisher visualisasi kedua.

Chrome memakai sesi **Guest** dan direktori aplikasi khusus
`/home/rslab/.local/share/brin-rmf-browser`. Sesi ini tidak menyimpan login
atau kredensial. Penyimpanan password dan profil Chrome pribadi tidak diubah.

## Layanan dan URL

| Unit | Fungsi |
| --- | --- |
| `brin-rmf.target` | Kelompok bringup backend; enabled pada default user target |
| `brin-rmf-network.service` | Menunggu alamat LAN tersedia; tidak mengubah konfigurasi jaringan |
| `brin-rmf-core.service` | Satu schedule/dispatcher/map/profile dan visualisasi, tanpa GUI |
| `brin-rmf-web-api.service` | API pada `192.168.0.141:8000`, waktu nyata |
| `brin-rmf-dashboard.service` | Dashboard produksi pada `192.168.0.141:3000` |
| `brin-rmf-rviz.service` | Executable RViz langsung pada desktop |
| `brin-rmf-browser.service` | Jendela Chrome Guest untuk dashboard |

Dashboard: **http://192.168.0.141:3000**.
API: **http://192.168.0.141:8000**.
Trajectory WebSocket dari core: **ws://192.168.0.141:8006**.
Dispatcher terhubung ke **ws://192.168.0.141:8000/_internal**.

GUI dimulai oleh `/home/rslab/.config/autostart/brin-rmf.desktop`.
Environment `DISPLAY`, `XAUTHORITY` dan Wayland diambil dari sesi desktop
saat login; nomor display tidak di-hardcode dalam unit.

## Menjalankan dan memeriksa

```bash
ssh komputer-utama
cd /home/rslab/rmf-integration
systemctl --user status brin-rmf.target brin-rmf-core.service \
  brin-rmf-web-api.service brin-rmf-dashboard.service \
  brin-rmf-rviz.service brin-rmf-browser.service --no-pager -l
bash tools/main.bash status
```

Untuk membuka GUI kembali pada desktop yang sudah login:

```bash
bash main/desktop-start.bash
```

Pemanggilan ulang menggunakan unit yang sama sehingga tidak membuat
instance core, API atau browser kedua. GUI yang sudah ditutup dibuka kembali.

Log:

```bash
journalctl --user -u brin-rmf-core.service -u brin-rmf-web-api.service \
  -u brin-rmf-dashboard.service -u brin-rmf-rviz.service \
  -u brin-rmf-browser.service -b --no-pager -n 100
```

Untuk menghentikan GUI saja:

```bash
systemctl --user stop brin-rmf-rviz.service brin-rmf-browser.service
```

Setelah operator memastikan robot diam dan task selesai, seluruh bringup
dapat dihentikan dengan `systemctl --user stop brin-rmf.target`.
Unit backend dan GUI memiliki `PartOf=brin-rmf.target`. Start backend kembali
dengan `systemctl --user start brin-rmf.target`, lalu jalankan
`bash main/desktop-start.bash` untuk membuka GUI di sesi desktop.

## Instalasi dan pembangunan ulang

Script source:

- `main/install-bringup.bash`: memasang dan enable user units serta GNOME
  autostart; backup file yang diganti disimpan pada `main/log/bringup-backup-*`.
- `main/enable-desktop-autologin.bash`: pengaturan GDM sebagai root, sudah
  dijalankan operator melalui sudo. Backup awal:
  `/etc/gdm3/custom.conf.brin-rmf-backup-20261109T073418Z`.
- `main/web/install-runtime.bash`: membuat virtualenv khusus memakai 41
  versi dependensi runtime yang cocok dengan Web Humble laptop.
- `main/web/build-dashboard.bash`: membangun workspace Web pada komputer
  utama menggunakan Node 16.20.2 dan pnpm runtime yang sudah disiapkan.

Checkout Web: `/home/rslab/rmf-web`, revision
`e2861c292bb27014435452e74faa825ecb0e8d91`.
Source dan dependensi Web yang sudah bekerja disalin dari laptop, virtualenv
dibuat ulang, dan dashboard produksi dibangun pada komputer utama.
Kompilasi tidak dijalankan setiap boot.

Untuk memperbarui runtime/build secara terencana:

```bash
cd /home/rslab/rmf-integration
bash main/web/install-runtime.bash
bash main/web/build-dashboard.bash
bash main/install-bringup.bash
```

Database dan cache API baru: `main/log/rmf_web_real/`.
Database/history laptop tetap tersedia pada workspace laptop.

## Hasil pemeriksaan

- Build dashboard produksi berhasil pada komputer utama.
- Core sehat: satu schedule, dispatcher, building map server dan announcer;
  profil `gedungWS_0`, lantai `L1`, digest sesuai source laptop.
- Dashboard `/` dan route aplikasi `/tasks`: HTTP `200`.
- API `/fleets` dan `/building_map`: HTTP `200`.
- Gambar peta dari cache API: HTTP `200`, **14.392 byte**.
- Socket.IO WebSocket `/socket.io/?EIO=4&transport=websocket`: HTTP `101`.
- Trajectory WebSocket port `8006`: HTTP `101`.
- API menerima koneksi dispatcher pada `/_internal`.
- Jendela `RMF Dashboard` dan RViz teramati pada desktop `rslab`.
- Pemanggilan autostart dua kali mempertahankan PID aplikasi/core yang sama;
  `startup-audit.json` mencatat `autostart_idempotent: true`.
- Pada pemeriksaan akhir, fleet `Devi` dengan robot `devi` diterima melalui ROS.
- Daftar fleet pada Web API masih kosong pada pembacaan terakhir. Deteksi
  ROS dan koneksi Web onboard merupakan pemeriksaan terpisah; konfigurasi
  endpoint Web robot belum diterapkan oleh pekerjaan pada komputer utama ini.
- GDM `AutomaticLoginEnable=true`, `AutomaticLogin=rslab`; lingering aktif.
- Seluruh target/unit backend enabled; GUI dipicu GNOME autostart.

Pengujian dilakukan pada sesi desktop yang sedang berjalan; **reboot fisik
belum dilakukan**. Tidak ada task, goal, cancel atau initial pose dikirim.
Deteksi fleet melalui ROS tidak membuktikan penerimaan task/gerak.
Endpoint Web pada adapter robot belum diubah
oleh bringup komputer utama; endpoint baru adalah `.141:8000/_internal`.

## Catatan RViz

RViz sempat berhenti dengan segfault `-11` selama pengujian. Satu kejadian
terjadi saat penghentian terkontrol, dan operator mengonfirmasi sempat
menutup jendela RViz pada kejadian sebelumnya. Launcher ROS sebelumnya tetap keluar
sukses setelah proses RViz gagal sehingga unit tidak memulai ulang GUI.

Bringup sekarang menjalankan executable RViz langsung, dengan parameter
dan remap observasi yang sama. Systemd dapat mendeteksi exit/crash dan
`Restart=on-failure` memulai ulang GUI. Instance baru teramati aktif setelah
perubahan. Penyebab native segfault belum dipastikan; pemulihan proses
tidak dinyatakan sebagai perbaikan bug native RViz. Untuk menutup RViz
secara terencana, gunakan `systemctl --user stop brin-rmf-rviz.service`.

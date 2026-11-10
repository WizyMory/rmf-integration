# Hasil migrasi RMF core — 9 November 2026

## Hasil

RMF core aktif pada `rslab@192.168.0.141`, hostname `rfm-pc`, workspace
`/home/rslab/rmf-integration`. Layanan pengguna `brin-rmf-core.service`
berstatus `active/running`, di-enable, dengan `Linger=yes`.
Snapshot pemeriksaan kestabilan: `MainPID=7006`, `NRestarts=0`.

Core menjalankan tepat satu schedule, dispatcher, building map server, dan
profile announcer. Publisher visualisasi dan TF observasi dijalankan tanpa
jendela RViz. ROS domain `0`, Cyclone DDS, waktu nyata, profil `gedungWS_0`,
lantai `L1`.

## Audit dan penerapan

- Laptop dan komputer utama dibandingkan sebelum perubahan. Target adalah
  Ubuntu 22.04.5 / ROS 2 Humble / x86_64, RAM 32 GB dan 20 CPU logis.
- Target awal belum memiliki dependensi RMF, Git atau colcon; belum ada core
  aktif pada kedua komputer. Operator memasang dependensi menggunakan
  `main/install-dependencies.bash --install` melalui sudo lokal. Simulasi
  awal apt menunjukkan 123 paket baru, tanpa upgrade/penghapusan.
- Source empat paket integrasi dibangun pada komputer utama; seluruhnya
  berhasil, total waktu build 4,86 detik. Build/install laptop tidak disalin.
- Server memasang aset peta laptop melalui wrapper `main/src/brin_rmf_maps`;
  plugin simulator tidak dibangun. Source dan konfigurasi robot tetap
  tersedia pada snapshot masing-masing.
- Profil DDS baru hanya untuk proses RMF server: interface `enp7s0`, peer
  Husky `.120` dan Devi `.237`. Konfigurasi IP, route, firewall, Nav2,
  sensor dan kontrol TF platform tidak diubah.
- Laptop tetap memakai profil DDS sebelumnya dan interface `wlp9s0`,
  `192.168.0.218`, untuk akses ke core server.

## Verifikasi

| Pemeriksaan | Hasil |
| --- | --- |
| Build source pada target | 4/4 paket berhasil |
| Syntax Bash/Python/XML, launch description, unit systemd | Lulus |
| Tidak ada core sebelum aktivasi | `core_absent: true` |
| Digest source laptop dan aset terpasang server | Identik |
| Status dari server | `healthy: true`, seluruh node core tepat satu |
| Status dari laptop melalui LAN | `healthy: true`, digest dan building map diterima |
| Building map | `gedungWS_0`, level `L1`, gambar PNG 14.392 byte termuat |
| Adapter native diagnostik dari laptop ke schedule server | `native_adapter_connected_to_schedule: true`, exit 0 |
| Launcher core kedua pada server | Ditolak oleh lock, exit 2 |
| Stabilitas layanan saat pemeriksaan | Aktif, 0 restart |
| Task/goal/robot diagnostik | 0 task, 0 goal; tidak mendaftarkan robot/fleet palsu |

Digest:

```text
a5c392a4a4446542b69b08d0bb44d8824e8ee081c955f7bc1cee3b795e4294be
```

Core dan adapter native server memakai versi `2.1.8`, message internal
`3.0.4`, sama dengan versi laptop. Server memakai paket apt Humble building
map tools `1.6.3` dan RMW Cyclone `1.3.5`; laptop memakai `1.6.2` dan `1.3.4`.
Koneksi native, digest dan pemuatan building map lulus pada kombinasi ini.

## Batas hasil

Fleet robot belum teramati pada jendela pemeriksaan. Penerimaan ini
membuktikan core dan komunikasi laptop–server, belum membuktikan registrasi,
preflight atau gerak fisik Husky/Devi. Domain Nav2 Devi tetap `73`.
Tidak ada task, goal, cancel, initial pose atau perintah hardware dikirim.

Layanan di-enable dan lingering aktif; reboot sengaja tidak dilakukan.
Uji setelah reboot dan uji robot dilakukan pada sesi operator berikutnya.

Runtime Web API/dashboard dan endpoint Web adapter dikelola terpisah;
migrasi core ini belum memindahkan runtime tersebut. Endpoint lama pada
konfigurasi Devi masih `ws://192.168.0.218:8000/_internal`.

Perubahan RViz lokal yang sudah ada sebelum migrasi
(`laptop/src/brin_husky_distributed/rviz/devi_rmf.rviz`) dipertahankan dan
ikut pada salinan source. Source awal repository:
`fedc98f13965cbc3454acbeddae594aee384540b`, ditambah berkas migrasi yang
tercatat pada working tree. Panduan operasi: [README](README.md).

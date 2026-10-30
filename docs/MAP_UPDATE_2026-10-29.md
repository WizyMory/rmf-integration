# Pembaruan map `brin_0` pada laptop dan Husky — 29 Oktober 2026

Sumber pembaruan adalah edit pengguna pada
`laptop/src/brin_rmf_maps/maps/brin_0.building.yaml`, SHA-256
`9fb10da067b2b56fec597ff242d5eab4bd6292824e483de84524370d2888fcb5`.
File referensi asli di `laptop/src/maps/brin_0/` tidak diubah.

## Hasil regenerasi

- Traffic Editor: 664 vertex, 293 lane, 418 dinding dan 16 definisi pintu.
  Dibanding versi sebelumnya, dua segmen dinding dan satu definisi pintu
  `lab_robot` dihapus; jalur dan vertex di area awal robot diperbarui.
- Graph RMF `nav_graphs/1.yaml` dan `nav_graphs/simulation.yaml` diregenerasi:
  214 vertex graph dan 586 lane berarah. Graph `simulation.yaml` tetap
  menghapus event pintu sesuai kebijakan operasional yang sudah ada.
- `maps/spawns.yaml`, `maps/generation_manifest.json`, mesh dinding
  `models/brin_0_L1/meshes/wall_1.obj`, occupancy dan correction mask diperbarui.
  Berkas world hasil generator identik sehingga tidak perlu diganti.
- Generator occupancy memakai footprint fisik yang sudah ada, termasuk
  padding: 1,14 × 0,80 m. Seluruh 293 lane diterima. Validasi independen
  menemukan nol pixel tak sesuai derivasi, nol mismatch correction mask,
  nol sel dinding struktural yang kehilangan status occupied, dan tidak ada
  lane terblokir. Reachability waypoint wajib tetap diterima.
- Area bebas `husky_0`–`ws_p0` yang sudah disetujui tetap mengikuti policy
  repository. Workspace lama Husky masih membawa policy versi sebelumnya;
  policy map tersebut diselaraskan dengan bundle yang divalidasi.
- Satu tes duplicate spawn diperbaiki agar memilih spawn berdasarkan nama,
  bukan indeks vertex tetap `17`, karena urutan graph berubah setelah edit.
  Logika produksi deteksi spawn tidak diubah.

## Deployment dan build

Hanya 13 file map/test/policy yang masuk bundle deployment. File sebelumnya
dibackup dan SHA-256 sebelum penulisan diperiksa lagi untuk mendeteksi edit
bersamaan. Snapshot laptop dan Husky pada kedua clone menerima bundle sama;
konfigurasi build khusus robot dipertahankan.

| Perangkat | Workspace yang dibuild dan diuji | Hasil |
| --- | --- | --- |
| Laptop | `/mnt/UbuntuData/rmf-integration/laptop` | Build berhasil; 21 tes pytest lulus |
| Laptop | `/mnt/UbuntuData/rmf_ws` | Build berhasil; 21 tes pytest lulus |
| Husky | `/home/husky/rmf-integration/husky` | Build berhasil; 21 tes pytest lulus |
| Husky | `/home/husky/rmf_ws` | Build berhasil; 21 tes pytest lulus |

`colcon test-result` pada setiap paket melaporkan 22 hasil, nol error,
failure atau skip: 21 kasus pytest dan satu hasil CTest pembungkus.
Build hanya memilih `brin_rmf_maps`; tidak membuild ulang driver atau Nav2.

Verifikasi dari environment bersih memilih prefix paket pada workspace
masing-masing dan membandingkan 12 aset map terpasang terhadap manifest
bundle. File tes tidak diinstal. Keempat instalasi cocok.

Digest profil `brin_0` terpasang pada keempat workspace:

```text
98eb87adba50e6f61d0c88d71bea75c1171904c9429c1a090f1dc86b3388ffe5
```

SHA-256 image Nav2 `brin_0_nav2.png`:

```text
f873045234c18d982d9f1905cd008954bfb2f2f1237acdcf4298b53fa37a3f2e
```

Profil `banyak_simpangan` tidak diregenerasi; digest tetap
`20ec559a4457173006fece1eb435e1dc60f054b355c1c7d3c8c6fd2a8ea00fe7`.
Laporan aktif default adalah `maps/occupancy_report.json`; berkas historis
`maps/brin_0_occupancy_report.json` tidak diperbarui.

## Pemakaian

Laptop:

```bash
bash tools/integration.bash laptop core traffic_profile:=brin_0 rviz:=true
```

Husky: pada terminal yang sudah disiapkan sesuai README, gunakan
`.../share/brin_rmf_maps/maps/brin_0.yaml` sebagai argumen `map` Nav2,
serta `traffic_profile:=brin_0` pada preflight dan adapter. Default launch
integrasi tetap `banyak_simpangan`, sehingga pemilihan eksplisit diperlukan.
Jangan mencampur graph `brin_0` dengan occupancy profil lainnya.

Tidak ada core RMF, Nav2 atau fleet adapter aktif saat pemeriksaan deployment.
Tidak ada runtime navigasi yang dinyalakan, goal yang dikirim atau uji gerak
yang dilakukan. Map baru dimuat pada peluncuran berikutnya. Parameter
inflation, controller, footprint, TF, sensor, jaringan dan waktu robot tidak
diubah. Pengujian gerak fisik tetap memerlukan sesi operator.

## Bukti dan backup

Direktori bukti permanen pada masing-masing clone:

- Laptop: `laptop/log/validation/map_update_brin0_20261029/`.
- Husky: `husky/log/validation/map_update_brin0_20261029/`.

Direktori tersebut menyimpan log build/test, verifikasi instalasi,
manifest bundle, rencana deployment dan `backup/` per target. Bukti
regenerasi serta validasi independen tersedia pada direktori bukti laptop.
Staging dan backup awal berada di
`/tmp/brin-map-update-20261029-jm5z2akg/` pada kedua perangkat.

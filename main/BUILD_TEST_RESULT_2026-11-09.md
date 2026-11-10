# Build ulang dan uji RMF core — 9 November 2026

## Hasil build dan runtime

Empat paket dibangun ulang pada komputer utama `rslab@192.168.0.141`
dengan `bash tools/main.bash build`: **4 berhasil, 2,24 detik**.
Paket: `brin_rmf_maps`, `brin_husky_fleet_adapter`, `brin_husky_hardware`,
dan `brin_husky_distributed`.

Sebelum restart, layanan dispatcher diperiksa melalui `/get_dispatches`:
daftar aktif dan riwayat task terdistribusi kosong; tidak ada fleet
teramati. Core kemudian dimulai ulang melalui systemd dan kembali sehat.
Status akhir: `active/running`, `enabled`, `MainPID=8939`, `NRestarts=0`
(tidak ada restart otomatis; satu restart manual merupakan bagian uji).

| Uji | Hasil |
| --- | --- |
| Core setelah restart | `healthy: true`, tepat satu dari keempat node core |
| Waktu nyata | `use_sim_time=false` pada schedule, dispatcher, building map server dan profile announcer |
| Building map service | `gedungWS_0`, level `L1`, gambar 14.392 byte |
| Digest profil | Sama dengan laptop dan source otoritatif |
| Query state dispatcher | Sukses; antrean kosong |
| DDS request/reply laptop–server | Lulus, 3 balasan unik diterima pada kedua endpoint |
| Native RMF laptop → schedule server | Tersambung, exit 0; tidak mendaftarkan robot/fleet |
| Guard core ganda lokal | Launcher ditolak, exit 2 |
| Guard core yang sudah ada di graph LAN | Terdeteksi, exit 2 sesuai rancangan |
| CLI target Devi dan bidding | Dry-run lulus, `request_published=false` |
| Observasi laptop dengan peer langsung `.141` | 3/3 proses baru `healthy: true` |

Core dibiarkan aktif setelah pengujian. Tidak ada task, goal Nav2, cancel,
initial pose, atau perintah hardware dikirim. Reboot dan gerak fisik robot
tidak diuji; fleet robot belum teramati selama pemeriksaan ini.

## Pengujian source

Perintah pada komputer utama, setelah setup Humble dan overlay main:

```bash
python3 -m pytest laptop/src/brin_husky_distributed/test \
  laptop/src/brin_rmf_maps/test -q
```

Hasil pada source/preset yang dipakai: **97 lulus, 2 gagal dari 99 uji**.
Kedua kegagalan berasal dari preset RViz pengguna yang sudah berubah
sebelum migrasi dan sengaja dipertahankan:

1. `test_gedung_default_rviz_accepts_manual_pose_for_devi_and_keeps_custom_presets`:
   tool initial pose menunjuk `/a200_1060/initialpose` (Husky), sedangkan
   preset referensi mengharapkan `/devi/initialpose`.
2. `test_combined_preset_contains_real_devi_layers_and_preserves_husky`:
   tampilan `Devi global costmap` dinonaktifkan, sedangkan preset referensi
   mengharapkannya aktif.

Kedua uji tersebut diulang pada salinan diagnostik terpisah dengan preset
referensi dari repository HEAD: **2 lulus**. Preset aktif pengguna tidak
ditimpa dan ekspektasi uji tidak diubah. Hasil suite pada preset aktif tetap
97 lulus / 2 gagal; hasil referensi tidak menggantikannya.

## Discovery laptop setelah migrasi

DDS request/reply dan koneksi native berhasil memakai profil lama, tetapi
satu proses observasi baru tidak menemukan core dalam jendela 5 detik.
Profil lama belum mencantumkan IP core baru `.141` secara langsung.

Profil tambahan `main/config/cyclonedds_laptop.xml` dibuat untuk proses
observasi/CLI laptop: interface `wlp9s0`, peer `.141`, `.120`, `.237`.
Tiga proses baru berturut-turut berhasil menerima semua node core, digest
dan building map menggunakan profil ini. Koneksi native RMF juga lulus.
Pengaturan OS, profil lama dan konfigurasi robot tidak diganti.

Gunakan dari terminal laptop:

```bash
cd /mnt/UbuntuData/rmf-integration
export BRIN_RMF_CYCLONEDDS_URI="file://$PWD/main/config/cyclonedds_laptop.xml"
bash tools/integration.bash laptop view
```

## Bukti pengujian

Log dan JUnit berada pada `main/log/trial-20261109/` di komputer utama dan
salinan workspace laptop. Artefak ini diabaikan Git:

- `unit-tests.xml`, `unit-tests.log`: 99 uji pada source/preset aktif.
- `rviz-baseline-tests.xml`, `rviz-baseline-tests.log`: dua uji pada preset referensi.
- `before-restart.json`, `after-restart.json`: layanan ROS, parameter waktu
  nyata, building map dan state dispatcher sebelum/sesudah restart.
- `core-status.json`, `service-state.txt`: core dan layanan systemd.
- `dds-main.json`, `dds-laptop.json`, `native-laptop.log`: komunikasi LAN.
- `status-laptop.json`: observasi 5 detik yang gagal dengan profil lama.
- `status-laptop-direct-peer-1.json` sampai `-3.json`: observasi yang lulus
  dengan peer langsung `.141` (tersimpan pada workspace laptop).
- `local-core-guard.log`, `lan-core-guard.json`: penolakan core ganda.
- `cli-devi-dry-run.json`, `cli-bidding-dry-run.json`: payload tanpa publikasi request.

Pada alat `dds_roundtrip.py`, endpoint server memakai label peran `robot`
untuk fungsi echo diagnostik; proses tersebut berjalan di `rfm-pc` dan
tidak berhubungan dengan kontrol robot fisik.

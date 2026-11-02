# Hasil setup Devi — 2 November 2026

Target: `devi@192.168.0.237`, hostname `devi-nuc`, Ubuntu 22.04.5,
x86_64, ROS 2 Humble. Workspace integrasi `/home/devi/rmf-integration`;
underlay Nav2 `/home/devi/devi_ws` tetap dipertahankan.

| Pemeriksaan | Hasil |
| --- | --- |
| SSH key dan identitas host | Berhasil |
| Runtime native `rmf_adapter` | Terpasang, versi paket 2.1.8 |
| Cyclone DDS | Dipasang operator; 7 paket baru, 0 upgrade/penghapusan |
| Build di Devi | `brin_devi_fleet_adapter` berhasil dibangun |
| Tes gabungan di laptop | 78 lulus |
| Tes paket Devi di robot sebelum penyalinan repo lengkap | 53 lulus, 1 dilewati karena snapshot laptop belum ada |
| Nav2 domain 73 | Action tersedia; lima lifecycle utama aktif |
| Scan, odometri, AMCL, TF | Terbaca; `nav2_ready: true`, `nav2_errors: []` |
| Native adapter Devi → schedule laptop | Berhasil dengan Cyclone DDS di kedua sisi |
| Service Nav2 melalui pipe → Fast DDS | UUID goal yang tidak ada mendapat status UNKNOWN |
| Pengumuman profil laptop → Devi | Digest cocok |
| Sepuluh file underlay yang diaudit | SHA-256 tetap cocok |
| Registrasi robot / goal / task | Tidak dilakukan |
| Dispatch | Tetap terkunci; penerimaan fisik belum selesai |

Digest profil `gedungWS_0`:

```text
ff44d7a33b01732e6c277b523c40ae5c7ef6c011dab83b259e5db44daef9f221
```

Hasil `link-check` pada jalur akhir:

```json
{
  "native_adapter_connected_to_schedule": true,
  "nav2_action_available": true,
  "nav2_action_service_responded_to_unknown_goal": true,
  "nav2_context_domain": 73,
  "rmf_observer_context_domain": 0,
  "nav2_rmw": "rmw_fastrtps_cpp",
  "rmf_rmw": "rmw_cyclonedds_cpp",
  "robot_registered": false,
  "goals_sent": 0
}
```

Saat core laptop aktif, pemeriksaan akhir memiliki `nav2_ready: true`,
digest cocok, dan hanya melaporkan `Devi/RMF map alignment has not been
confirmed`. Konfirmasi footprint dan penerimaan operasi juga belum diisi.
`accepted: false` adalah hasil yang diharapkan sebelum commissioning,
bukan kegagalan yang dilewati untuk mendaftarkan robot.

Uji sementara native Fast DDS → schedule Cyclone menemukan kegagalan
deserialisasi `Invalid rmf_traffic_msgs/ScheduleQuerySpacetime type [0]`.
Pemisahan dua proses menghindari jalur tersebut: RMF tetap Cyclone/domain 0,
Nav2 tetap Fast DDS/domain 73, dihubungkan pipe privat onboard. Tidak ada
file konfigurasi DDS, domain Nav2, jaringan, atau sistem Husky yang diganti.

Core laptop hanya diaktifkan sementara untuk pengujian dan dihentikan
setelahnya. Driver, Nav2, map server, TF platform, controller, konfigurasi
hardware/safety, shell startup, dan service autostart tidak diubah.
Tidak ada fleet palsu, gerak fisik, pengujian docking, telemetri baterai RMF,
atau penerimaan traffic bersama Husky. Kalibrasi antar peta dan verifikasi
ukuran robot tetap harus dilakukan di lokasi sebelum operasi.

Source dan riwayat Git dikirim lewat SSH yang telah disetujui. Build dilakukan
di robot; artefak laptop tidak disalin. Snapshot `reference` tidak disebarkan
kembali ke `devi_ws`. Konfigurasi/paket laptop dan Husky tidak dimodifikasi;
perubahan di luar `devi/` hanya runner baru serta dokumentasi repository.

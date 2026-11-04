# Koneksi Web otomatis saat boot Devi — 4 November 2026

## Perubahan

Bringup membaca default `server_uri` dari
`devi/src/brin_devi_fleet_adapter/config/bringup.yaml`:

```yaml
server_uri: ws://192.168.0.218:8000/_internal
```

Service yang sudah terpasang menjalankan `tools/devi.bash bringup rviz:=false`,
sehingga startup berikutnya otomatis meneruskan alamat tersebut ke supervisor
dan native fleet adapter. Tidak diperlukan override unit systemd baru.
Argumen `server_uri:=ws://...` tetap dapat mengganti alamat untuk satu sesi;
nilai konfigurasi kosong menonaktifkan Web pada startup berikutnya.

Alamat divalidasi sebelum proses adapter dimulai: harus WebSocket `ws/wss`
dan memakai alamat LAN laptop, dengan port valid. Loopback, unspecified,
credentials di URI dan fragment ditolak.

Nav2, auto pose `[19.423, -28.2408, 0, 1.83415]`, radius 0,55 m, parameter
hardware, TF controller dan profil DDS tetap dipertahankan. Native RMF
tetap Cyclone/domain 0 dan Nav2 tetap Fast DDS/domain 73.

Client RMF yang terpasang mempunyai handler open/close/fail serta loop
koneksi ulang pada `rmf_websocket/BroadcastClient.cpp`. Ketika core sudah
tersedia tetapi API belum hidup, client mencoba kembali. Pemeriksaan ini
tidak menghentikan API untuk menguji gangguan saat robot sedang dipakai.

## Bukti sebelum aktivasi service

- Service `enabled`, tetapi `inactive` karena sesi Web sebelumnya memakai
  bringup foreground dengan argumen Web eksplisit.
- API `192.168.0.218:8000` dan dashboard `127.0.0.1:3000` aktif di laptop.
- Dari Devi, `/fleets/Devi/state` dapat dibaca dan memuat robot `devi` dari
  sesi manual, status idle dan task ID kosong.
- **95 tes Devi lulus di laptop dan 95 tes lulus di robot**.
- Build paket Devi berhasil.
- `bringup.launch.py --show-args` menampilkan default URI persis di atas.
- Verifier underlay sebelum/sesudah pemasangan: **10 file asli utuh**.
- Manifest 7 file overlay diverifikasi pada robot.
- Backup: `devi/log/web_boot_backup_20261104_104336/before_update.tar.gz`.
- Manifest: `devi/log/web_boot_update_manifest.json`.

## Aktivasi dan pemeriksaan akhir

Operator diminta memarkirkan Devi pada pose awal, menghentikan bringup
foreground dengan Ctrl-C, lalu menjalankan:

```bash
sudo systemctl enable --now devi_robot.service
```

SSH memerlukan password sudo yang dimasukkan langsung di robot. Operator
telah mengaktifkan service; bukti setelah aktivasi:

- Service **enabled, active/running**, MainPID `11603`, `NRestarts=0`,
  mulai pada **10:44:54 WIB**.
- Hanya satu bringup berjalan, sebagai child systemd. Command parent hanya
  `bringup rviz:=false`, tanpa URI CLI; supervisor menerima default dari
  konfigurasi: `--server-uri ws://192.168.0.218:8000/_internal`.
- Pada **10:44:56**, AMCL mencatat pose startup otomatis
  `19.423 -28.241 1.834`. Koreksi manual yang teramati baru terjadi kemudian,
  mulai 10:46:11; startup itu sendiri sudah menerapkan auto pose.
- Pada **10:45:58**, native client mencatat
  `BroadcastClient successfully connected to uri: [ws://192.168.0.218:8000/_internal]`.
- Pada **10:46:00**, adapter mencatat `Registered devi in Devi`.
- Web API `/fleets/Devi/state` mengembalikan robot `devi`, map `L1`, dengan
  state berumur **0,437 detik** saat diperiksa. Status saat itu `working`,
  task ID `patrol.dispatch-0`; task itu tidak dibuat oleh pengujian ini.
- Preflight sesudah aktivasi menghasilkan `nav2_ready: true`,
  `accepted: true`, `errors: []`; kelima lifecycle Nav2 aktif dan digest
  core cocok dengan profil gedungWS_0.

Dengan demikian service yang dipakai saat boot sudah terbukti memuat alamat
Web otomatis dan mengirim state baru ke API. Tidak dilakukan reboot komputer
tambahan atau pemutusan API untuk pengujian gangguan pada sesi ini.

Tidak ada goal/task yang dikirim dalam pengujian ini. Panduan operasional
terbaru tersedia di [README Devi](README.md) dan
[README laptop bagian 9](../laptop/readme.md#9-web-opsional-setelah-penerimaan-cli).

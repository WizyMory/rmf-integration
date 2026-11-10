# Pemulihan posisi robot dan metadata task Web — 9 November 2026

## Hasil

Dashboard pada **http://192.168.0.141:3000** menerima state robot dan task
dari adapter native. Browser uji menampilkan marker robot pada peta `L1`.
Tabel task menampilkan pelaksana `devi`, start time dan end time untuk
riwayat yang dipulihkan.

API terakhir mencantumkan fleet `Devi` dan `HuskyA200`. Perbaikan konfigurasi
robot pada pekerjaan ini diterapkan pada Devi; koneksi Husky yang teramati
datang langsung dari `.120` dan tidak memerlukan deployment oleh pekerjaan ini.

## Penyebab

Adapter Devi masih memakai `ws://192.168.0.218:8000/_internal`, sementara
Web API sudah dipindah ke `.141`. Kanal ROS `/fleet_states` dan dispatch
tetap bekerja, sehingga ROS mengetahui posisi dan penugasan robot, tetapi
Web belum menerima `fleet_state_update`, `task_state_update` dan task log.

Contoh sebelum perbaikan: ROS menugaskan `patrol.dispatch-0`/`-1` kepada
`Devi/devi`, sedangkan REST Web masih menunjukkan `queued`,
`assigned_to: null`, start `0` dan finish `null`. API `/fleets` kosong.

## Perubahan dan penerapan

- Default `config/bringup.yaml` Devi menunjuk `.141`.
- `prepare_startup` menyimpan endpoint terpilih pada `web_server_uri` di
  runtime integration. Launch adapter memakai field tersebut, sehingga
  retry dari supervisor yang masih memiliki argumen `.218` menggunakan
  endpoint baru. Tanpa field tersebut, argumen launch tetap berlaku.
- Source robot dibandingkan dengan snapshot sebelum perubahan; tujuh file
  code/config/test dibackup dan diperbarui. Parameter fisik startup tetap sama.
- Untuk memulihkan antrean status native, digunakan relay sementara pada
  endpoint lama di laptop. Relay hanya menerima empat jenis update telemetry
  dari IP Devi dan meneruskannya ke API `.141`. Pesan asli disimpan untuk audit.
- Relay telah berhenti. Adapter baru terhubung langsung dari `.237` ke
  `.141`; timestamp posisi terus bertambah setelah relay berhenti.
- Hanya proses `fleet_adapter` dimulai ulang saat data native menunjukkan
  `idle`, task ID kosong, data segar dan seluruh riwayat task berstatus terminal,
  setelah operator mengonfirmasi robot diam dan task selesai.

PID adapter `5131` diganti `8681`. PID supervisor `4677`, service utama
`4174`, Nav2, map server, AMCL, controller, BT navigator, RPLidar, filter scan,
initial-pose bridge dan visualization bridge dipastikan tetap sama.
Hash runtime AMCL, Nav2 dan fleet configuration tetap sama. Runtime
integration hanya mendapat field endpoint Web.

Backup robot:

```text
/home/devi/rmf-integration/devi/log/web-endpoint-20261109T081914Z
```

## Riwayat task yang dipulihkan

Waktu berikut berasal dari `TaskState` native, zona **Asia/Jakarta (WIB)**:

| Task | Status | Pelaksana | Start | End |
| --- | --- | --- | --- | --- |
| `patrol.dispatch-0` | completed | `Devi/devi` | 14:56:25.903 | 14:57:04.736 |
| `patrol.dispatch-1` | completed | `Devi/devi` | 15:01:41.118 | 15:02:34.936 |
| `patrol.dispatch-2` | canceled | `Devi/devi` | 15:05:26.528 | 15:05:48.059 |

Kolom end mengikuti `unix_millis_finish_time` dari SDK. Pada task yang masih
berjalan, field ini merupakan estimasi finish dan dapat berubah. Tabel di
atas berisi riwayat dengan status terminal. Tidak ada waktu atau pose buatan
ditambahkan untuk mengisi placeholder.

## Verifikasi

| Pemeriksaan | Hasil |
| --- | --- |
| Build paket integrasi Devi pada robot | 1 paket berhasil, 1,35 detik |
| Regression test Devi pada environment robot | 100 lulus |
| Parameter `server_uri` adapter berjalan | `ws://192.168.0.141:8000/_internal` |
| Koneksi native ke API | WebSocket langsung dari IP `.237` diterima |
| Freshness setelah relay berhenti | Timestamp robot bertambah dalam pengamatan 3 detik |
| Pose robot | Data map `L1`, x/y/yaw tersedia dari adapter |
| Fleet yang diterima API | `Devi`, `HuskyA200` |
| Data tiga task lama | Status, pelaksana, start dan end terisi |
| Browser halaman task | Sel pelaksana berisi `devi`; sel waktu berisi jam lokal |
| Browser halaman peta | Canvas 3D termuat, stream Devi diterima, marker robot terlihat |
| Error runtime pada browser peta uji | Tidak teramati |
| Task/goal/cancel/initial pose dikirim oleh agent | 0 |

Peta memakai renderer canvas 3D, sehingga pemeriksaan elemen SVG saja tidak
menjadi indikator marker. Screenshot dari halaman browser uji tersendiri:
[peta sesudah pemulihan](log/web-diagnostics/map-render.png).

Bukti di `main/log/web-diagnostics/`: `before.json`, `after.json`,
`recovered-native-updates.jsonl`, `map-render-check.json`, `map-render.png`
dan `tasks-dom.html`. Bukti restart/test robot juga disimpan pada
`devi/log/web-endpoint-restart.json` dan `devi/log/web-endpoint-tests.xml`.

## Pemakaian dan batas hasil

Refresh dashboard dengan **Ctrl+F5**, pilih level **L1**, lalu periksa peta
dan tabel task. Data robot yang belum tersambung tidak dibuat secara sintetis.
Field khusus tipe task lain, misalnya cart/pickup pada task patrol, tidak
memiliki nilai bila memang tidak dikirim dalam request/telemetry.

SOC `0,95` masih berasal dari konfigurasi adapter, sesuai implementasi
sebelumnya; pekerjaan ini tidak menambahkan pembacaan baterai hardware.
Tidak ada pengiriman task fisik baru oleh agent. Perbaikan diuji dengan
telemetry berjalan serta riwayat task asli yang sudah dibuat operator.

Perbaikan ini tidak me-restart Nav2/sensor, mengubah domain Nav2 Devi `73`,
map alignment, footprint, initial pose, controller, TF platform, atau
pengaturan keselamatan robot.

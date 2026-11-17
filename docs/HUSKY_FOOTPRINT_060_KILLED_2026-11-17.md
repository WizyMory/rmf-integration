# Husky: footprint 0.60 dan diagnosis task killed — 17 November 2026

Pembaruan ini menggantikan nilai footprint 0.65 yang diterapkan sebelumnya
pada hari yang sama. Nilai yang diminta operator:

| Pengaturan | Nilai |
| --- | --- |
| Radius footprint RMF HuskyA200 | 0.60 m |
| Polygon Nav2 local/global | x=±0.50 m, y=±0.35 m (1.00 × 0.70 m) |
| Inflation radius local/global | 0.40 m |
| Footprint padding | Tetap 0.02 m |
| Vicinity RMF | Tetap 0.80 m |

Source fisik Husky, snapshot kedua clone, fleet distributed fisik, serta
bundle `gedungWS_0` laptop/Husky/komputer-utama disamakan. Runtime auto
bringup dihasilkan dari konfigurasi Nav2 yang terpasang. Parameter sensor,
TF, BT, kecepatan, recovery dan batas kegagalan tidak diubah. Nav2 simulasi
laptop dan ukuran fleet Devi tetap seperti sebelumnya.

Salinan kanonik pada paket Devi di repository diperbarui karena ikut
menghitung digest profil bersama. Perangkat Devi terakhir tidak terjangkau
(`No route to host`), sehingga salinan onboard belum dapat disamakan. Saat
robot Devi kembali online, bundle tersebut perlu disinkronkan sebelum
preflight. Konfigurasi footprint Devi sendiri bukan target perubahan ini.

Validasi sapuan footprint pada occupancy `gedungWS_0` menghasilkan ukuran
1.04 × 0.74 m termasuk padding, tanpa lane terhalang dan tanpa perubahan
pixel/graph. Radius dalam polygon termasuk padding adalah 0.37 m, sehingga
inflation 0.40 m memenuhi batas radius dalam tersebut. Ini menyelesaikan
ketidakcocokan konfigurasi sebelumnya (inflation 0.35 < radius dalam 0.42),
belum membuktikan hilangnya semua collision saat robot bergerak.

## Mengapa task killed

Task terakhir yang diperiksa adalah `patrol.dispatch-1`, aktif pada fase
`Go to [place:dpn_ws1]`. Log robot menunjukkan rangkaian berikut:

1. RPP controller berulang kali mendeteksi `collision ahead`.
2. Controller melaporkan `Controller patience exceeded` atau
   `Failed to make progress`; NavigateToPose berakhir dengan status 6 (ABORTED).
3. Adapter menghitung kegagalan goal Nav2 dan melakukan replan/retry.
4. Pada 10:14:16 WIB, adapter mencatat:
   `killing RMF task patrol.dispatch-1 after 5 Nav2 failures; return waypoint 6`.
5. RMF Web menyimpan status `killed` dengan label
   `Nav2 navigation failed 5 times` dan
   `Safe escape assessment required before return`.

Task killed sebelumnya `0ecd3e6d-dc9b-433b-92d0-b3f8a1b780d5` memiliki label
yang sama. Ini adalah kill yang diminta adapter setelah batas kegagalan,
bukan bukti proses robot mendapat SIGKILL atau OS membunuh prosesnya.
Service auto bringup masih aktif dan tidak restart saat kejadian terbaru.

Konfigurasi yang dipakai: `max_goal_failures: 5`, `retry_delay: 5.0` dan
controller `failure_tolerance: 0.3`. Penghitung kegagalan dipertahankan
sepanjang task; pada kode saat ini keberhasilan goal antara hanya menandai
arrival, sementara reset penghitung terjadi saat task berubah. Karena itu
lima kegagalan tidak harus berurutan pada satu waypoint untuk memicu kill.

Pada Husky fisik, recovery `_start_escape()` melaporkan kebutuhan intervensi
operator. BackUp otomatis belum diterima untuk perangkat fisik. Setelah kill,
recovery tidak menjalankan manuver mundur otomatis dan robot didecommission
melalui penanganan kegagalan. Perubahan footprint ini mempertahankan handler
tersebut. Memperbesar batas retry atau menonaktifkan collision detection tidak
dilakukan sebagai bagian diagnosis.

Penyebab langsung kill telah dibuktikan oleh kode, log dan label task Web.
Sumber obstacle yang memicu setiap collision (obstacle fisik, scan, sisa
costmap atau lokalisasi) belum dibuktikan dari log ini. Perubahan ukuran
footprint dapat mengubah hasil pemeriksaan clearance; uji gerak baru tetap
diperlukan untuk memastikan collision berulang berkurang.

## Deployment dan verifikasi

Build maps/distributed laptop dan komputer-utama, serta overlay Husky dan
Nav2/maps/distributed workspace lama Husky berhasil. Tes maps, distributed
dan auto bringup lokal lulus 74 kasus. Core dan auto bringup Husky dimuat
ulang mengikuti persetujuan restart layanan yang telah diberikan operator.
Tidak ada task/goal yang dikirim oleh diagnosis atau deployment ini.

Parameter live local/global dibaca melalui layanan ROS GetParameters dan
sesuai tabel. File fleet runtime memuat radius 0.60. Startup pukul 10:25 WIB
mencatat preflight `errors: []`, `accepted: true`, registrasi `husky_0`, dan
koneksi Web berhasil. Telemetri kemudian segar, idle dan tanpa issue aktif.
Tidak ada warning inflation-versus-inscribed pada startup konfigurasi baru.

Digest baru:
`15a18726cd898a873b2bda6aa2ecdf344ede56c0a84c41109628214863341dbd`.

Log, backup, API task state/log, parameter live dan rencana patch disimpan di
`husky/log/validation/footprint_060_20261117/` pada clone laptop dan Husky,
serta `main/log/validation/footprint_060_20261117/` pada komputer-utama.

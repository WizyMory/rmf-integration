# Pemeriksaan collision Nav2 — sesi 14:34–14:45 WIB, 28 Oktober 2026

Pemeriksaan dilakukan dengan membaca log robot, source controller yang
dipilih overlay, dan lima scan pasif sesudah Nav2 dihentikan. Tidak ada
goal, perubahan TF, atau aktivasi navigasi selama pemeriksaan.

## Temuan log

| Kejadian | Jumlah |
| --- | ---: |
| `RegulatedPurePursuitController detected collision ahead!` | 406 |
| `Controller patience exceeded` | 67 |
| `Failed to make progress` | 3 |
| Permintaan clear local costmap | 49 |
| Percobaan recovery Spin / Wait / BackUp | 12 / 12 / 12 |
| Goal Nav2 sukses / gagal | 9 / 5 |

Adapter pertama-tama mengirim lintasan berisi 14 waypoint. Goal ke-6 gagal,
kemudian empat lintasan pengganti berisi 10 waypoint masing-masing gagal
pada goal ke-2. Sesudah kegagalan kelima, adapter melaporkan perlu intervensi
operator. Ini menunjukkan kegagalan berulang pada bagian lintasan tertentu;
log tidak mencatat pose target dan sel costmap pemicu setiap collision.

Controller berjalan pada 15 Hz dengan `failure_tolerance: 0.3`. Banyak
peringatan berasal dari pengulangan pemeriksaan kondisi yang sama, sehingga
406 pesan tidak berarti terdapat 406 obstacle berbeda. Ada 32 peringatan
loop controller terlambat dan dua scan ditolak karena timestamp mendahului
cache TF. Itu belum cukup untuk menyimpulkan gangguan timing sebagai akar
penyebab seluruh kejadian.

## Arti collision pada controller yang dipakai

Overlay memilih RPP dan costmap dari `/home/husky/ros2_ws/install`, dengan
source RPP versi 1.1.18, branch Humble, commit
`476d9e8d15892869c32a23252c2500196412e3a5`. Fungsi `inCollision` memeriksa
footprint pada posisi sekarang dan proyeksi gerak, termasuk rotasi, terhadap
cost lethal. Mekanisme ini sesuai dengan
[source RPP Humble](https://github.com/ros-navigation/navigation2/blob/humble/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp).

Local costmap memakai obstacle layer dari scan dan inflation layer; static
layer hanya ada pada global costmap. Karena itu warna inflation yang lebar
saja tidak membuktikan penyebab pesan collision. Sel obstacle dari scan,
jejak obstacle lama, transformasi waktunya, serta ruang gerak footprint
harus dibedakan dengan data saat kejadian.

Footprint dikonfigurasi 1,10 × 0,76 m dengan padding 0,02 m: ukuran efektif
sekitar 1,14 × 0,80 m dan jarak pusat ke sudut sekitar 0,70 m. Selisih nominal
antara inflation 0,425 m dan radius inscribed 0,40 m hanya 0,025 m, lebih
kecil daripada satu sel local costmap 0,05 m. Gradien cost yang sempit dapat
memengaruhi kedekatan jalur ke obstacle, tetapi pengaruhnya pada kegagalan
sesi ini belum terbukti tanpa rekaman costmap dan pose.

## Pemeriksaan scan sesudah sesi

Lima scan berisi 1.081 jarak valid per scan. Jarak terdekat sekitar 1,63 m;
tidak ditemukan endpoint di dalam footprint padded, kotak dekat robot
±0,80 × ±0,65 m, atau sweep maju 0,20 m yang diperiksa. TF sensor yang
diterima adalah `base_link → laser_frame`, translasi `[0.265, 0, 0.485]`
dan rotasi identitas, sesuai konfigurasi lidar.

Hasil ini tidak menunjukkan self-hit pada sampel tersebut. Namun sampel
diambil sesudah Nav2 berhenti dan tidak membuktikan kondisi saat collision.
Pengguna melaporkan area tampak kosong; obstacle semu/stale tetap merupakan
kemungkinan yang perlu dibuktikan dengan rekaman local costmap raw, footprint,
scan, TF navigasi, global plan dan collision arc saat warning berikutnya.

Nav2 dihentikan operator sekitar 14:45 sehingga parameter runtime dan
costmap saat kejadian tidak dapat dibaca kembali. Log tidak cukup untuk
menentukan sel spesifik yang memicu collision atau menyimpulkan bahwa
mengecilkan inflation akan menyelesaikan masalah.

## Status konfigurasi

Saat pemeriksaan pertama, file konfigurasi robot dan snapshot berisi local
dan global inflation 0,425. Nilai runtime sesi sebelumnya tidak diambil
sebelum proses berhenti. Atas instruksi pengguna berikutnya, kedua nilai
dikembalikan ke **0,45** pada source Nav2 fisik dan snapshot Husky di kedua
perangkat. Symlink konfigurasi terpasang dan checksum sudah diverifikasi.
Konfigurasi simulasi laptop tetap 0,65. Tidak ada restart Nav2 atau perubahan
perilaku recovery yang diterapkan dalam tahap pengembalian nilai ini.

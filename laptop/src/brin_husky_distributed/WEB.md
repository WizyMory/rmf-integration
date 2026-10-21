# RMF Web untuk satu Husky fisik

RMF core dan Web API/dashboard berjalan di laptop. Task browser masuk melalui
ROS 2 task API, lalu adapter di Husky mengeksekusinya melalui Nav2. Adapter
mengirim posisi dan status task ke API melalui WebSocket LAN.

## Prasyarat

Gunakan checkout `open-rmf/rmf-web` Humble pada commit
`e2861c292bb27014435452e74faa825ecb0e8d91`. Checkout laptop yang diperiksa
berada di `/mnt/UbuntuData/rmf-web`, dengan Python 3.10 dalam `.venv`, Node
16.20.2 dan pnpm 8.15.9 pada `.brin-tools`. Launcher memeriksa commit dan
keberadaan runtime; tidak menginstal dependensi atau mengubah checkout.
Instalasi baru mengikuti [README versi tersebut](https://github.com/open-rmf/rmf-web/tree/e2861c292bb27014435452e74faa825ecb0e8d91).

Source overlay Humble/RMF dan gunakan environment DDS fisik sesuai README
paket pada semua terminal. Jangan memakai launcher API dari workspace
simulasi: script tersebut memaksa simulation time. Launcher baru menggunakan
`RMF_SERVER_USE_SIM_TIME=false`, `use_sim_time:=false`, dan database terpisah.
Hentikan API simulasi sebelum memakai port yang sama.

Alamat bind API dipilih operator. Tidak ada perubahan firewall, routing,
atau driver oleh launcher. Endpoint internal ditujukan untuk LAN pengujian
terpercaya; konfigurasi autentikasi bawaan checkout tetap berlaku.

## Laptop

Ganti `192.168.0.XXX` dengan **IP LAN laptop**, bukan IP robot, pada setiap
terminal yang memerlukan variabel berikut:

```bash
export BRIN_LAPTOP_IP=192.168.0.XXX
export RMF_WEB_ROOT=/mnt/UbuntuData/rmf-web
```

Terminal API, setelah overlay di-source:

```bash
ros2 launch brin_husky_distributed web.launch.py \
  web_root:="$RMF_WEB_ROOT" runtime_dir:="$PWD/log/rmf_web_real" \
  api_host:="$BRIN_LAPTOP_IP" public_url:="http://$BRIN_LAPTOP_IP:8000"
```

`api_host` bawaan `127.0.0.1` untuk pemeriksaan lokal. Isi IP laptop agar
adapter Husky dapat terhubung. SQLite/cache disimpan di `runtime_dir`.
Zona waktu scheduler `Asia/Jakarta`; OS dan browser harus sesuai.

Terminal dashboard, memakai runtime yang sudah terpasang di laptop:

```bash
export PATH="$RMF_WEB_ROOT/.brin-tools/node-v16.20.2-linux-x64/bin:$RMF_WEB_ROOT/.brin-tools/pnpm/node_modules/.bin:$PATH"
export HOST=127.0.0.1 PORT=3000 BROWSER=none
export REACT_APP_RMF_SERVER="http://$BRIN_LAPTOP_IP:8000"
export REACT_APP_TRAJECTORY_SERVER=ws://localhost:8006
cd "$RMF_WEB_ROOT"
pnpm --filter rmf-dashboard run start:react
```

Gunakan `start:react` agar hanya dashboard yang dimulai; `pnpm start` dapat
memulai backend tambahan. Resource dashboard laptop saat diperiksa sudah
memilih L1. Peta berasal dari building map server RMF. Overlay trajectory
port 8006 opsional dan belum dimulai oleh paket ini; posisi fleet dan status
task tetap dikirim melalui API.

Terminal RMF core:

```bash
ros2 launch brin_husky_distributed laptop.launch.py \
  traffic_profile:=banyak_simpangan \
  server_uri:="ws://$BRIN_LAPTOP_IP:8000/_internal"
```

URI diteruskan ke dispatcher agar kegagalan alokasi task terlihat di Web.
Buka `http://localhost:3000` di browser laptop; API docs ada di
`http://IP_LAPTOP:8000/docs`.

## Husky

Setelah preflight dan gerak Nav2 fisik pada README diterima, isi IP laptop
yang sama pada terminal Husky:

```bash
export BRIN_LAPTOP_IP=192.168.0.XXX
ros2 launch brin_husky_distributed robot.launch.py \
  traffic_profile:=banyak_simpangan enable_dispatch:=true \
  server_uri:="ws://$BRIN_LAPTOP_IP:8000/_internal"
```

Launch robot menolak URI loopback/unspecified karena `localhost` di Husky
berarti Husky sendiri. `start_nav2` dan `start_hokuyo` mengikuti README;
jangan menggandakan proses yang sudah hidup. Robot memerlukan RMF Python
runtime, tetapi tidak memerlukan instalasi API/dashboard.

## Task dan penerimaan

Pilih **L1**, **HuskyA200**, dan **husky_0**. Gunakan **Patrol**, satu putaran,
ke waypoint yang sudah diuji pada peta fisik. Patrol satu tujuan adalah
perintah menuju waypoint. UI versi ini masih menampilkan jenis task lain;
adapter hanya mendukung Patrol. Browser memakai dispatcher untuk memilih
satu Husky ini.

Lihat identitas aset dan nama tujuan tanpa koneksi robot:

```bash
ros2 run brin_husky_distributed profile_info --traffic-profile banyak_simpangan
```

Dari terminal laptop, termasuk tanpa Web:

```bash
ros2 run brin_husky_hardware send_task --places NAMA_WAYPOINT
ros2 run brin_husky_hardware send_task --robot husky_0 --places NAMA_WAYPOINT
ros2 run brin_husky_hardware send_task --cancel TASK_ID
```

Perintah pertama menguji dispatcher; kedua menargetkan robot langsung.
Respons diterima belum berarti selesai. Catat ID task, gerak nyata, hasil
Nav2, dan status akhir RMF/Web. SOC 0,95 masih nilai konfigurasi, bukan
pembacaan baterai asli. Waypoint charger belum menyediakan docking fisik.

Penerimaan lapangan: preflight lulus → gerak Nav2 mandiri → task CLI bergerak
dan selesai → pembatalan saat bergerak → task browser bergerak dan selesai.
Uji kehilangan/recovery Web juga diperlukan. Putusnya Web/DDS tidak menjamin
penghentian goal Nav2. Belum ada uji gerak fisik dari repository snapshot ini.

Referensi: [konfigurasi API Humble](https://github.com/open-rmf/rmf-web/blob/e2861c292bb27014435452e74faa825ecb0e8d91/packages/api-server/README.md).

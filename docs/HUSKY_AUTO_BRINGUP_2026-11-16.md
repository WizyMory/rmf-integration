# Husky auto bringup — 16 November 2026

Service user `brin-husky-bringup.service` sudah dipasang dan enabled di Husky.
`loginctl` melaporkan `Linger=yes`, sehingga startup tidak bergantung pada
login desktop atau SSH. Service juga sudah dijalankan dan diuji langsung;
robot tidak direboot oleh deployment ini.

Urutan startup:

1. Temukan proses/topic fisik yang sudah ada dan ambil lock tunggal.
2. Jalankan `hokuyo_bringup` bila belum ada publisher scan. Tunggu scan segar.
3. Jalankan satu `husky_nav2 navigation.launch.py` dengan map
   `gedungWS_0_rmf.yaml`, waktu nyata dan `start_hokuyo:=false`.
4. AMCL memuat pose parkir `x=25.885`, `y=-27.303`, `z=0.0`,
   `yaw=-2.877 rad` di frame `map`. Tunggu pose, map dan lifecycle Nav2 aktif.
5. Tunggu core domain 0 dan digest map yang sesuai dari komputer-utama.
6. Jalankan launcher adapter fisik yang sudah ada. Preflight tetap wajib
   accepted sebelum adapter aktif. Jika preflight/adapter gagal, supervisor
   mencoba lagi dengan satu launch adapter saja; Hokuyo/Nav2 tetap hidup.

Web telemetry memakai `ws://192.168.0.141:8000/_internal`. Komputer-utama
menjalankan core tunggal; laptop tetap untuk CLI/RViz. Startup tidak mengirim
task atau goal. Pose otomatis mengasumsikan robot dinyalakan pada posisi
parkir fisik tersebut. Jika posisi parkir berubah, sesuaikan konfigurasi atau
koreksi initial pose di RViz sebelum mengirim task.

Konfigurasi source:

```text
/home/husky/rmf-integration/husky/src/brin_husky_autostart/config/bringup.yaml
```

Supervisor membaca konfigurasi Nav2 yang terpasang dari
`/home/husky/rmf_ws/install/husky_nav2/share/husky_nav2/config/nav2_params.yaml`
dan menghasilkan salinan runtime di `husky/log/bringup_runtime/nav2_startup.yaml`.
Hanya field inisialisasi AMCL yang ditambahkan/diubah pada salinan itu.
Parameter sensor, EKF, TF dan costmap underlay tetap dipertahankan.
`initial_pose`, `set_initial_pose` dan `always_reset_initial_pose` dipakai
untuk inisialisasi saat startup; supervisor tidak mengirim initialpose berulang.

Pose yang diminta berjarak 1.081 m dari graph RMF. Operator secara eksplisit
menyetujui batas startup 1.25 m untuk preflight dan pencocokan lane pada
16 November. `hardware_startup.yaml` dan `fleet_startup.yaml` menerapkan
`max_graph_distance=1.25` dan `max_merge_lane_distance=1.25`. File hardware
manual dan fleet kanonik tidak diubah. Digest preflight tetap mengacu bundle
map/graph/fleet kanonik; override lokal ini dicatat pada `prepared.json`.
Launcher menerima `startup_fleet_config` hanya bila seluruh field fleet
lain identik dengan baseline, dan jarak berada di rentang 1.00–1.25 m.

Kontrol di Husky:

```bash
systemctl --user status brin-husky-bringup.service
journalctl --user -u brin-husky-bringup.service -f
systemctl --user stop brin-husky-bringup.service
systemctl --user start brin-husky-bringup.service
```

Hentikan service sebelum memakai launch Hokuyo/Nav2/adapter manual. Untuk
mematikan auto startup tanpa mengubah service Clearpath:

```bash
systemctl --user disable --now brin-husky-bringup.service
```

Build/update hanya paket baru:

```bash
cd /home/husky/rmf-integration
bash tools/husky_bringup.bash build
bash tools/husky_bringup.bash prepare
```

`prepare` menulis konfigurasi saja, dan ditolak jika supervisor sedang
memegang lock. Setelah edit konfigurasi, hentikan service, jalankan prepare
jika diperlukan, lalu start kembali. Installer `bash husky/systemd/install.bash`
memasang unit dan enable saat boot; installer tidak menjalankannya langsung.

Hasil validasi live:

- Build paket berhasil; 15 tes baru lulus di laptop dan Husky.
- Upaya supervisor kedua ditolak: `Husky boot supervisor already running`.
- Stop/start service membersihkan proses miliknya dan memulai ulang satu stack.
- AMCL mencatat `Setting pose ... 25.885 -27.303 -2.877`.
- Nav2 aktif; preflight di startup final melaporkan `errors: []`, `accepted: true`.
- Adapter terhubung ke Web komputer-utama dan mencatat `Registered husky_0 in HuskyA200`.
- Unit aktif dan enabled, `NRestarts=0`, `Linger=yes` saat verifikasi.
- Tidak ada task/goal yang dikirim; uji power cycle belum dilakukan.

Log dan backup deployment berada di
`husky/log/validation/auto_bringup_20261116/` pada clone laptop dan Husky.

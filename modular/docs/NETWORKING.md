# Komunikasi satu LAN dan jaringan Wi-Fi berbeda

RMF pada komputer utama berkomunikasi dengan adapter melalui DDS. WebSocket
adapter ke Web API hanya jalur Web telemetry; koneksi WebSocket saja belum
membuktikan traffic schedule dan task DDS bekerja.

## Satu LAN

Core dan proses induk adapter memakai domain RMF yang sama dan DDS yang sudah
diuji. Robot Nav2 boleh memakai domain/RMW lain karena gateway berjalan lokal.
`rmf.localhost_only` harus false untuk core pada komputer lain.

Periksa dari robot tanpa mengubah route atau firewall:

```bash
# Ganti dengan IP core yang nyata:
CORE_ADDRESS=192.168.0.141
ip route get "$CORE_ADDRESS"
ping -c 3 -W 2 "$CORE_ADDRESS"
timeout 5s nc -vz -w 3 "$CORE_ADDRESS" 8000
```

Ping/port 8000 tidak membuktikan DDS dua arah; gunakan preflight untuk
discovery, profil/core, lalu run untuk handshake RMF native. SSH hanya alat
administrasi; task tidak diangkut melalui sesi SSH.

## Wi-Fi / hotspot berbeda

Dua device sama-sama punya internet tidak otomatis saling mempunyai route.
Untuk hotspot dengan NAT/CGNAT, gunakan jaringan overlay/VPN routed yang
disediakan operator, atau router antar-subnet yang benar. Setelah routing
tersedia, DDS memerlukan discovery dan jalur data dua arah melalui interface
tersebut. Modul tidak membuat VPN atau mengubah konfigurasi jaringan robot.

Urutan penerapan:

1. Operator menyediakan alamat VPN/routed yang dapat dijangkau dua arah.
2. Verifikasi `ip route get`, SSH dan endpoint API menggunakan alamat tersebut.
3. Siapkan profil DDS khusus **proses RMF**, dengan peer unicast jika jaringan
   tidak membawa multicast discovery.
4. Pakai domain RMF sama pada core dan semua adapter; Nav2 lokal tetap memakai
   konfigurasi aslinya.
5. Isi Web URI dengan alamat VPN/routed core yang sama bila Web diaktifkan.
6. Jalankan inspect, preflight dan handshake adapter sebelum task operator.

Contoh XML Cyclone DDS untuk ditinjau pada robot, sesuaikan dengan versi
Cyclone yang terpasang dan ganti kedua placeholder:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain id="any">
    <General>
      <NetworkInterfaceAddress>ROBOT_VPN_IP</NetworkInterfaceAddress>
      <AllowMulticast>false</AllowMulticast>
    </General>
    <Discovery>
      <ParticipantIndex>auto</ParticipantIndex>
      <MaxAutoParticipantIndex>40</MaxAutoParticipantIndex>
      <Peers>
        <Peer Address="CORE_VPN_IP"/>
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

Pada core, gunakan profil pasangannya: interface lokal core dan peer alamat
robot. Untuk lebih dari satu robot, daftar peer mencakup seluruh anggota
yang perlu berkomunikasi. Profil harus tersedia pada masing-masing device:

```yaml
rmf:
  domain_id: 0
  rmw: rmw_cyclonedds_cpp
  localhost_only: false
  cyclonedds_uri: file:///absolute/path/to/reviewed/rmf_vpn.xml
  web_uri: ws://CORE_VPN_IP:8000/_internal
```

`NetworkInterfaceAddress` tersedia pada versi Cyclone Humble yang digunakan
integrasi ini; versi yang memakai `Interfaces/NetworkInterface` dapat
memerlukan sintaks lain. Periksa schema versi lokal sebelum memuat XML.
Jangan mengganti profil DDS Clearpath/Nav2 hanya untuk menghubungkan RMF.

VPN yang hanya membawa TCP, firewall yang memblokir DDS, atau NAT tanpa
routing data tetap dapat membuat node terlihat tetapi handshake gagal.
Port DDS bergantung domain/participant/transport; audit firewall sesuai
profil yang dipilih, bukan membuka semua port atau mengekspos DDS publik.

Wi-Fi rumah/hotspot dan VPN yang saling memakai subnet sama juga bisa
mengacaukan route. Periksa route efektif, termasuk host route sensor.
Perubahan route, interface sensor atau firewall harus ditinjau pemilik
robot. Paket modular ini tidak melakukan perubahan itu.

## Batas operasional

Penundaan jaringan memengaruhi update jadwal dan task. Sensor/TF/Nav2 tetap
lokal; adapter meminta cancel ketika readiness yang dipantaunya hilang.
Discovery DDS dan timeout software tidak menjamin stop seketika pada
putus jaringan/adapter crash. Tetap gunakan watchdog motor, E-stop dan
prosedur keselamatan asli robot. Uji koneksi lintas jaringan dan pemulihan
secara terpisah sebelum operasi bersama beberapa robot.

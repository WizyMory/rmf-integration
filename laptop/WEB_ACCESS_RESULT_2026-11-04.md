# RMF Web LAN dan akses internet — 4 November 2026

## Implementasi

- `tools/dashboard.bash lan`: dashboard pengembangan pada `0.0.0.0:3000`,
  API dan trajectory menunjuk IP laptop `192.168.0.218`.
- `tools/web_public.bash prepare`: salinan dashboard produksi dengan API,
  Socket.IO, dan trajectory pada origin browser yang sama. Tidak mengedit
  checkout `rmf-web` atau memulai ulang API/core/robot.
- `tools/web_public.bash start EMAIL`: Nginx tanpa root dengan binding
  `127.0.0.1:8088`, serta Protected Quick Tunnel dengan `--allowed-mail`.
  Login berupa kode sekali pakai ke email yang diizinkan. Source dan
  log runtime disimpan di `laptop/log/rmf_web_public/` yang diabaikan Git.
- Gambar peta dari REST dan Socket.IO diarahkan melalui `/api/cache/`;
  browser internet tidak perlu mengakses IP LAN untuk memuat peta.
- `/_internal` dan `/api/_internal` diblokir pada gateway. Adapter tetap
  memakai `ws://192.168.0.218:8000/_internal` melalui LAN.

Runtime dipatok: `rmf-web e2861c292bb27014435452e74faa825ecb0e8d91`,
Node `16.20.2`, cloudflared `2026.10.7`, SHA256
`1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872`,
image resmi Nginx dengan digest
`sha256:0e52bd054126cdc040b1276c0af347aeb02a41b9cfe305d6094767ac30e97949`.

## Hasil pemeriksaan

- Build produksi: `Compiled successfully`.
- Syntax Bash/Python, `nginx -t`, `git diff --check`: lulus.
- Unit pemeriksaan URL gambar peta: delapan kasus lulus, termasuk URL LAN,
  query string, URL gateway, data URI, blob, dan URL tidak valid.
- Dari komputer Devi: dashboard LAN dan `GET /fleets` HTTP `200`;
  handshake WebSocket API dan trajectory HTTP `101`.
- Melalui gateway lokal: fleet dan building map HTTP `200`; URL cache
  telah diubah dan PNG peta berhasil dimuat, 14.392 byte.
- Enam variasi path menuju endpoint adapter, termasuk encoding dan slash
  ganda: HTTP `404`.
- Melalui gateway lokal: Socket.IO dan trajectory WebSocket HTTP `101`.
- HTML produksi dan dua script utamanya HTTP `200`, script terkompresi gzip.
- Dari URL internet tanpa sesi: `/`, `/api/fleets`, Socket.IO polling, dan
  `/trajectory` seluruhnya HTTP `302` ke `login.trycloudflare.com`.
- Percobaan upgrade WebSocket langsung tanpa sesi mendapat HTTP `500`,
  tanpa koneksi WebSocket terbuka. Percobaan HTTP biasa pada rute terkait
  mengarah ke login. WebSocket internet setelah login memerlukan uji browser.

Sesi awal aktif pukul 11:21 WIB. URL sementara sesi awal:
`https://washer-republican-applies-tablets.trycloudflare.com`.
Alamat ini berubah ketika tunnel dibuat ulang; alamat sesi aktif berada
di `laptop/log/rmf_web_public/public_url.txt`.

## Penerimaan yang masih diperlukan

Login kode email oleh operator, tampilan peta/fleet setelah login, dan
WebSocket melalui internet belum diverifikasi pada saat laporan dibuat.
Operator diminta menguji dari Chrome, bila memungkinkan melalui data
seluler. Tidak ada task, goal, cancel, atau perintah gerak yang dikirim
selama pemeriksaan ini.

Protected Quick Tunnel merupakan akses sementara untuk percobaan.
Untuk hostname tetap, gunakan domain sendiri dengan Cloudflare Tunnel
dan Cloudflare Access. Login gateway membatasi akses seluruh aplikasi;
akun dashboard bawaan belum memisahkan peran operator/pengamat.

Referensi: [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[Access untuk domain tetap](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/),
[proxy WebSocket Nginx](https://nginx.org/en/docs/http/websocket.html).

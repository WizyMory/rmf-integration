```bash
sudo ip addr add 192.168.0.15/32 dev enx00e04ca286d9
```
```bash
sudo ip route replace 192.168.0.10/32 dev enx00e04ca286d9 src 192.168.0.15
```
```bash
ip route get 192.168.0.10
```
```bash
ping -I enx00e04ca286d9 -c 4 192.168.0.10
```
```bash
ros2 launch hokuyo_bringup hokuyo_bringup.launch.py
```
```bash
nmcli device status
ip route get 192.168.0.10
ping -c 4 192.168.0.10
```
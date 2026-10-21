# Open-RMF and Husky Integration

This repository contains source-code snapshots
from two different ROS 2 computers.

## Systems

1. laptop/src
   Source code from the development laptop.
   Original: /mnt/UbuntuData/rmf_ws/src
   Purpose: Open-RMF and simulation.

2. husky/src
   Source code from the physical Husky robot.
   Original: /home/husky/rmf_ws/src
   Robot SSH: husky@192.168.0.120
   Purpose: Nav2, sensors, and hardware.

## Rules

- Use ROS 2 Humble compatibility.
- Compare both systems before modifying integration code.
- Never assume simulation and hardware
  use identical configurations.
- Physical Husky must use real time,
  not simulation time.
- Preserve existing working configurations.
- Never overwrite robot-specific parameters
  without reviewing them.
- Do not execute robot deployment or SSH
  commands without explicit user approval.
- Do not modify hardware, network, TF,
  or safety settings without confirmation.
- Explain changes affecting both computers.
- Treat laptop/src and husky/src as snapshots.
  They are not automatically deployed.

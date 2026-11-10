# Open-RMF and Husky Integration

This repository contains source-code snapshots
and integration overlays from three different ROS 2 computers.

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

3. devi/src
   Integration overlay for the physical Devi robot.
   Robot workspace: /home/devi/rmf-integration
   Existing Nav2 underlay: /home/devi/devi_ws
   Robot SSH: devi@192.168.0.237
   Preserve Devi Nav2 domain 73; native RMF uses domain 0.
   devi/reference contains read-only audited underlay snapshots.
   Web telemetry uses ws://192.168.0.141:8000/_internal on komputer-utama.
   Prepared integration.web_server_uri takes priority over a cached launch URI.

4. main/
   RMF core role on komputer-utama, hostname rfm-pc.
   SSH: rslab@192.168.0.141 (alias komputer-utama).
   Workspace: /home/rslab/rmf-integration.
   Ubuntu 22.04 / ROS 2 Humble; native RMF domain 0, real time.
   tools/main.bash builds shared laptop integration source into main/install.
   main/src/brin_rmf_maps installs the laptop map assets without Gazebo.
   Primary core is the user service brin-rmf-core.service.
   Boot bringup: brin-rmf.target starts core, Web API and production dashboard.
   GNOME autostart main/desktop-start.bash opens RViz and a Chrome Guest window.
   Web: http://192.168.0.141:3000; API: http://192.168.0.141:8000.
   Desktop autologin rslab is configured by the operator.
   Use laptop for CLI/RViz; stop the main core before running a laptop core.

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

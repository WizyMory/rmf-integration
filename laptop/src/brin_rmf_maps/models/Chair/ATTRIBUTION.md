# Chair model

- Source: the installed ROS 2 Humble `rmf_demos_assets` package,
  `models/Chair`
- Upstream project: Open-RMF `rmf_demos`
- Author recorded in `model.config`: Cole Biesemeyer / Open Robotics
- Description: generic hospital chair
- License: Apache License 2.0, as declared by `rmf_demos_assets`

The mesh and texture files are copied from the installed workspace source. The
visual and collision URIs in `model.sdf` use the local `model://Chair` resource
so the simulation does not depend on a Fuel cache or network connection.

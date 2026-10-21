"""Conservative collision checks against a fresh Nav2 local costmap."""
import math


LETHAL_OR_INSCRIBED = 253


def _cost_at(costmap, x, y):
    meta = costmap.metadata
    if meta.resolution <= 0 or meta.size_x <= 0 or meta.size_y <= 0:
        return None
    origin = meta.origin
    yaw = math.atan2(2*(origin.orientation.w*origin.orientation.z
                        + origin.orientation.x*origin.orientation.y),
                     1-2*(origin.orientation.y**2+origin.orientation.z**2))
    dx, dy = x-origin.position.x, y-origin.position.y
    gx = (dx*math.cos(yaw)+dy*math.sin(yaw))/meta.resolution
    gy = (-dx*math.sin(yaw)+dy*math.cos(yaw))/meta.resolution
    col, row = math.floor(gx), math.floor(gy)
    if not (0 <= col < meta.size_x and 0 <= row < meta.size_y):
        return None
    index = row*meta.size_x+col
    if index >= len(costmap.data):
        return None
    return int(costmap.data[index])


def _clear(costmap, x, y):
    cost = _cost_at(costmap, x, y)
    return cost is not None and cost < LETHAL_OR_INSCRIBED


def rear_sweep_clear(costmap, pose, distance,
                     half_length=0.57, half_width=0.40):
    """Check the newly swept rear corridor; Nav2 checks the full footprint."""
    if distance <= 0:
        return False
    resolution = float(costmap.metadata.resolution)
    if resolution <= 0:
        return False
    x, y, yaw = pose
    forward = (math.cos(yaw), math.sin(yaw))
    left = (-forward[1], forward[0])
    stride = resolution/2
    lateral = math.ceil(2*half_width/stride)
    steps = math.ceil(distance/stride)
    for step in range(steps+1):
        behind = half_length+distance*step/steps
        for j in range(lateral+1):
            side = -half_width+2*half_width*j/lateral
            if not _clear(costmap,
                          x-behind*forward[0]+side*left[0],
                          y-behind*forward[1]+side*left[1]):
                return False
    return True


def turn_space_clear(costmap, pose, radius=0.70):
    """Require room for the circumscribed footprint before normal navigation."""
    resolution = float(costmap.metadata.resolution)
    if resolution <= 0 or radius <= 0:
        return False
    steps = math.ceil(2*radius/(resolution/2))
    for i in range(steps+1):
        dx = -radius+2*radius*i/steps
        for j in range(steps+1):
            dy = -radius+2*radius*j/steps
            if dx*dx+dy*dy <= radius*radius:
                if not _clear(costmap, pose[0]+dx, pose[1]+dy):
                    return False
    return True

"""Rigid coordinate conversion inside the adapter; never publish TF."""
import math


class MapAlignment:
    def __init__(self, settings):
        if settings.get('confirmed') is not True:
            raise ValueError('Devi/RMF map alignment has not been confirmed')
        self.x, self.y, self.yaw = (settings.get(key) for key in ('x', 'y', 'yaw'))
        if not all(type(v) in (int, float) and math.isfinite(v)
                   for v in (self.x, self.y, self.yaw)):
            raise ValueError('Map alignment requires finite x, y, yaw (metres/radians)')
        self.c, self.s = math.cos(self.yaw), math.sin(self.yaw)

    def to_rmf(self, pose):
        x, y, yaw = pose
        return [self.c*x - self.s*y + self.x,
                self.s*x + self.c*y + self.y, self.wrap(yaw + self.yaw)]

    def to_nav2(self, pose):
        x, y, yaw = pose
        x, y = x - self.x, y - self.y
        return [self.c*x + self.s*y, -self.s*x + self.c*y,
                self.wrap(yaw - self.yaw)]

    @staticmethod
    def wrap(angle):
        return math.atan2(math.sin(angle), math.cos(angle))


def require_commissioning(settings):
    MapAlignment(settings['map_alignment'])
    for name in ('footprint_confirmed', 'operation_accepted'):
        if settings['commissioning'].get(name) is not True:
            raise ValueError('Devi commissioning is pending: ' + name)

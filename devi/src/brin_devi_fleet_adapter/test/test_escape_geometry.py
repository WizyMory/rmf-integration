"""A stale, unknown, or obstructed costmap must never authorize BackUp."""
from nav2_msgs.msg import Costmap
from brin_devi_fleet_adapter.escape_geometry import (
    rear_sweep_clear, turn_space_clear)


def grid():
    costmap = Costmap()
    costmap.metadata.resolution = 0.05
    costmap.metadata.size_x = costmap.metadata.size_y = 120
    costmap.metadata.origin.position.x = -3.0
    costmap.metadata.origin.position.y = -3.0
    costmap.data = [0]*14400
    return costmap


def block(costmap, x, y, cost):
    column = int((x+3)/0.05)
    row = int((y+3)/0.05)
    costmap.data[row*120+column] = cost


def test_rear_sweep_rejects_lethal_unknown_and_out_of_bounds():
    for cost in (253, 254, 255):
        costmap = grid()
        block(costmap, -0.7, 0, cost)
        assert not rear_sweep_clear(costmap, (0, 0, 0), 0.20)
    assert rear_sweep_clear(grid(), (0, 0, 0), 0.20)
    assert not rear_sweep_clear(grid(), (-2.8, 0, 0), 0.20)


def test_front_obstacle_does_not_mask_a_clear_rear_corridor():
    costmap = grid()
    block(costmap, 0.55, 0, 253)
    assert rear_sweep_clear(costmap, (0, 0, 0), 0.20)


def test_turn_check_detects_side_obstacle_even_if_reverse_sweep_is_free():
    costmap = grid()
    block(costmap, -0.5, 0.5, 254)
    assert rear_sweep_clear(costmap, (0, 0, 0), 0.20)
    assert not turn_space_clear(costmap, (0, 0, 0))


def test_rear_sweep_uses_robot_heading():
    import math
    costmap = grid()
    block(costmap, 0, -0.7, 254)
    assert not rear_sweep_clear(costmap, (0, 0, math.pi/2), 0.20)
    assert rear_sweep_clear(costmap, (0, 0, 0), 0.20)

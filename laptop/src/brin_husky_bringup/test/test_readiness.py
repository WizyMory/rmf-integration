from types import SimpleNamespace
from brin_husky_bringup.wait_for_controllers import controllers_ready


def test_readiness_requires_both_active_controllers():
    def state(name, value):
        return SimpleNamespace(name=name, state=value)
    joint = state('joint_state_broadcaster', 'active')
    assert not controllers_ready([])
    assert not controllers_ready([joint])
    assert not controllers_ready([joint, state('platform_velocity_controller', 'inactive')])
    assert controllers_ready([joint, state('platform_velocity_controller', 'active')])

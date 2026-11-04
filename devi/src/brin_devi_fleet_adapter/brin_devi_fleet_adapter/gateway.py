"""Private local pipe between RMF/Cyclone and the existing Nav2/Fast DDS.

Only the Nav2 child initializes Fast DDS. The optional map/manual-pose relay
is separate from motion commands. No TCP listener or TF publisher is created.
"""
from concurrent.futures import Future
import multiprocessing
import os
import signal
import threading
import time
from types import SimpleNamespace


class GoalHandle:
    def __init__(self, gateway, request_id, feedback):
        self.gateway, self.request_id, self.feedback = gateway, request_id, feedback
        self.accepted = False
        self.result = Future()

    def get_result_async(self):
        return self.result

    def cancel_goal_async(self):
        return self.gateway.request('cancel', goal_id=self.request_id)


class ActionProxy:
    def __init__(self, gateway, supported=True):
        self.gateway, self.supported = gateway, supported

    def server_is_ready(self):
        return self.supported and self.gateway.fresh and self.gateway.state.get('nav2_ready', False)

    def send_goal_async(self, goal, feedback_callback=None):
        if not self.supported:
            raise RuntimeError('Devi automatic BackUp is disabled')
        future, request_id = self.gateway.prepare_request()
        self.gateway.goals[request_id] = GoalHandle(self.gateway, request_id, feedback_callback)
        self.gateway.send({'op': 'goal', 'id': request_id, 'goal': goal})
        return future


class LifecycleProxy:
    def __init__(self, gateway):
        self.gateway = gateway

    def service_is_ready(self):
        return self.gateway.fresh

    def call_async(self, _request):
        future = Future()
        state = self.gateway.state.get('lifecycle', {}).get('bt_navigator')
        future.set_result(SimpleNamespace(current_state=SimpleNamespace(id=state)))
        return future


class StopProxy:
    def __init__(self, gateway):
        self.gateway = gateway

    def publish(self, message):
        if any(getattr(vector, axis) != 0. for vector in (message.linear, message.angular)
               for axis in ('x', 'y', 'z')):
            raise ValueError('The Devi gateway accepts only zero velocity stops')
        self.gateway.send({'op': 'stop'})


class Nav2Gateway:
    def __init__(self, settings, allow_commands=False, allow_initial_pose=False, relay_map=False):
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=nav2_worker,
            args=(child, settings, allow_commands, allow_initial_pose, relay_map), name='devi_nav2_gateway')
        self.process.start()
        child.close()
        self.allow_commands = allow_commands
        self.allow_initial_pose = allow_initial_pose
        self.pending, self.goals = {}, {}
        self.sequence = 0
        self.state, self.received_at = {}, 0.
        self.map_message = None
        self.closed = False

    @property
    def fresh(self):
        return self.process.is_alive() and time.monotonic() - self.received_at <= 2.

    def prepare_request(self):
        self.sequence += 1
        future = Future()
        self.pending[self.sequence] = future
        return future, self.sequence

    def send(self, message):
        if message['op'] == 'initial_pose' and not getattr(self, 'allow_initial_pose', False):
            raise RuntimeError('Manual initial pose is not enabled on this gateway')
        if message['op'] in ('goal', 'cancel', 'stop') and not self.allow_commands:
            raise RuntimeError('Read-only Devi diagnostic cannot command Nav2')
        self.connection.send(message)

    def request(self, operation, **values):
        future, request_id = self.prepare_request()
        self.send({'op': operation, 'id': request_id, **values})
        return future

    def poll(self):
        try:
            for _ in range(100):
                if not self.connection.poll():
                    break
                message = self.connection.recv()
                kind, request_id = message['kind'], message.get('id')
                if kind == 'state':
                    self.state, self.received_at = message['state'], message['observed_at']
                elif kind == 'map':
                    self.map_message = message['value']
                elif kind == 'feedback':
                    handle = self.goals.get(request_id)
                    if handle and handle.feedback:
                        handle.feedback(message['value'])
                elif kind == 'result':
                    handle = self.goals.pop(request_id, None)
                    if handle and not handle.result.done():
                        handle.result.set_result(message['value'])
                else:
                    future = self.pending.pop(request_id, None)
                    if kind == 'error' and future is None:
                        handle = self.goals.pop(request_id, None)
                        if handle and not handle.result.done():
                            handle.result.set_exception(RuntimeError(message['error']))
                        continue
                    if future is None or future.done():
                        continue
                    if kind == 'error':
                        future.set_exception(RuntimeError(message['error']))
                    elif kind == 'accepted':
                        handle = self.goals[request_id]
                        handle.accepted = message['accepted']
                        future.set_result(handle)
                    else:
                        future.set_result(message['value'])
        except (EOFError, BrokenPipeError, OSError):
            self.received_at = 0.

    def close(self):
        if self.closed:
            return
        self.closed = True
        # systemd and ros2 launch can both send SIGINT to this process group.
        # Keep a second signal from interrupting the bounded child cleanup.
        main_thread = threading.current_thread() is threading.main_thread()
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN) if main_thread else None
        try:
            try:
                self.connection.send({'op': 'close'})
            except (BrokenPipeError, OSError):
                pass
            self.process.join(timeout=4.)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2.)
        finally:
            self.connection.close()
            if main_thread:
                signal.signal(signal.SIGINT, previous)


def nav2_worker(connection, settings, allow_commands, allow_initial_pose=False, relay_map=False):
    # A fresh spawned interpreter is required: RMW is selected per process.
    # The parent owns shutdown through the pipe. Keep this ROS context alive
    # during group SIGINT so owned goals can still be cancelled in finally.
    # SIGTERM remains available for the parent's bounded terminate fallback.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_fastrtps_cpp'
    os.environ['ROS_DOMAIN_ID'] = '73'
    import uuid
    import rclpy
    from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
    from nav2_msgs.action import NavigateToPose
    from rclpy.signals import SignalHandlerOptions
    from .preflight import Inspection
    rclpy.init(args=[], domain_id=73, signal_handler_options=SignalHandlerOptions.NO)
    node = Inspection(settings, node_name='devi_nav2_observer_' + str(os.getpid()))
    result_client = node.create_client(NavigateToPose.Impl.GetResultService,
                                      '/navigate_to_pose/_action/get_result')
    initial_pose_publisher = (node.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
                              if allow_initial_pose else None)
    last_map = None
    goals = {}
    closing, moved_goal = False, False
    zero_publisher, zero_until = None, 0.

    def send(message):
        try:
            connection.send(message)
        except (BrokenPipeError, OSError):
            pass

    def stop():
        nonlocal zero_publisher, zero_until
        if zero_publisher is None:
            zero_publisher = node.create_publisher(Twist, '/devi/cmd_vel_nav_raw', 10)
        zero_until = time.monotonic() + 0.3
        zero_publisher.publish(Twist())

    def reply(future, request_id):
        try:
            send({'kind': 'reply', 'id': request_id, 'value': future.result()})
        except Exception as exc:
            send({'kind': 'error', 'id': request_id, 'error': str(exc)})

    def accepted(future, request_id):
        nonlocal moved_goal
        try:
            handle = future.result()
            send({'kind': 'accepted', 'id': request_id, 'accepted': handle.accepted})
            if not handle.accepted:
                return
            moved_goal = True
            goals[request_id] = handle
            if closing:
                handle.cancel_goal_async()
                stop()

            def finished(result):
                goals.pop(request_id, None)
                try:
                    send({'kind': 'result', 'id': request_id, 'value': result.result()})
                except Exception as exc:
                    send({'kind': 'error', 'id': request_id, 'error': str(exc)})
            handle.get_result_async().add_done_callback(finished)
        except Exception as exc:
            send({'kind': 'error', 'id': request_id, 'error': str(exc)})

    next_state = 0.
    try:
        while rclpy.ok() and not closing:
            node.poll()
            now = time.monotonic()
            if zero_publisher is not None and now < zero_until:
                zero_publisher.publish(Twist())
            if now >= next_state:
                send({'kind': 'state', 'state': node.report(), 'observed_at': now})
                next_state = now + 0.2
            if relay_map and 'map' in node.messages and node.messages['map'] is not last_map:
                last_map = node.messages['map']
                send({'kind': 'map', 'value': last_map})
            for _ in range(100):
                if not connection.poll():
                    break
                message = connection.recv()
                operation, request_id = message['op'], message.get('id')
                if operation == 'close':
                    closing = True
                    break
                if operation == 'initial_pose':
                    if initial_pose_publisher is None:
                        continue
                    from .initial_pose_bridge import validate_initial_pose
                    try:
                        validate_initial_pose(message['pose'])
                        initial_pose_publisher.publish(message['pose'])
                    except ValueError as exc:
                        node.get_logger().error(str(exc))
                    continue
                if operation in ('goal', 'cancel', 'stop') and not allow_commands:
                    send({'kind': 'error', 'id': request_id, 'error': 'Read-only Nav2 gateway'})
                elif operation == 'query_result':
                    request = NavigateToPose.Impl.GetResultService.Request()
                    request.goal_id.uuid = list(uuid.uuid4().bytes)
                    result_client.call_async(request).add_done_callback(
                        lambda f, i=request_id: reply(f, i))
                elif operation == 'goal':
                    node.action.send_goal_async(message['goal'],
                        feedback_callback=lambda value, i=request_id: send(
                            {'kind': 'feedback', 'id': i, 'value': value})).add_done_callback(
                                lambda f, i=request_id: accepted(f, i))
                elif operation == 'cancel':
                    handle = goals.get(message['goal_id'])
                    if handle is None:
                        send({'kind': 'error', 'id': request_id, 'error': 'Goal is not owned by Devi adapter'})
                    else:
                        handle.cancel_goal_async().add_done_callback(
                            lambda f, i=request_id: reply(f, i))
                elif operation == 'stop':
                    stop()
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        closing = True
        for handle in list(goals.values()):
            handle.cancel_goal_async()
        if moved_goal:
            stop()
        deadline = time.monotonic() + (2. if allow_commands else 0.)
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if zero_publisher is not None and time.monotonic() < zero_until:
                zero_publisher.publish(Twist())
        node.destroy_node()
        rclpy.try_shutdown()
        connection.close()

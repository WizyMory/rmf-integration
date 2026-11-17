"""Local IPC boundary: RMF and Nav2 may use different ROS domains and RMWs."""
import multiprocessing
import os
import signal
import time

from .config import environment


class Gateway:
    def __init__(self, config, allow_commands=False):
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=worker, args=(child, config, allow_commands),
                                       name='nav2_'+config['robot']['name'])
        self.process.start()
        child.close()
        self.allow_commands = allow_commands
        self.state, self.received_at = {}, 0.

    @property
    def fresh(self):
        return self.process.is_alive() and time.monotonic()-self.received_at < 2.

    def send(self, operation, **values):
        if operation in ('goal', 'cancel') and not self.allow_commands:
            raise RuntimeError('Read-only gateway cannot send or cancel goals')
        self.connection.send({'op': operation, **values})

    def poll(self):
        events = []
        try:
            for _ in range(100):
                if not self.connection.poll():
                    break
                message = self.connection.recv()
                if message['kind'] == 'state':
                    self.state, self.received_at = message['state'], time.monotonic()
                else:
                    events.append(message)
        except (EOFError, OSError):
            self.received_at = 0.
        return events

    def close(self):
        try:
            self.send('close')
        except (BrokenPipeError, OSError):
            pass
        # Drain pending reports/results while the child cancels its owned goal.
        deadline = time.monotonic()+4
        while self.process.is_alive() and time.monotonic() < deadline:
            self.poll()
            self.process.join(timeout=.05)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=3)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
        self.connection.close()


def worker(connection, config, allow_commands):
    # No ROS/RMF import above this line: RMW is selected separately per process.
    for key, value in environment(config['nav2']).items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    import math
    from pathlib import Path
    import yaml
    import rclpy
    from rclpy.action import ActionClient, get_action_server_names_and_types_by_node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from rcl_interfaces.srv import GetParameters
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid, Odometry
    from sensor_msgs.msg import BatteryState, LaserScan
    from std_msgs.msg import Float32
    from tf2_ros import Buffer, TransformListener, TransformException

    nav = config['nav2']
    rclpy.init(args=['--ros-args', '-r', '/tf:='+nav['tf_topic'],
                     '-r', '/tf_static:='+nav['tf_static_topic']],
                domain_id=nav['domain_id'], signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('nav2_observer_'+config['robot']['name'])
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    messages, goals, pending, cancel_on_accept = {}, {}, set(), set()
    closing, close_deadline = False, 0.
    action = ActionClient(node, NavigateToPose, nav['navigate_action'])
    subscriptions = []
    def keep(key, message):
        messages[key] = (message, time.monotonic())
    durable = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
    for name, message_type, qos in [('map', OccupancyGrid, durable),
                                  ('scan', LaserScan, qos_profile_sensor_data),
                                  ('odom', Odometry, qos_profile_sensor_data)]:
        subscriptions.append(node.create_subscription(message_type, nav[name+'_topic'],
            lambda message, key=name: keep(key, message), qos))
    battery = config['battery']
    if battery['mode'] != 'none':
        subscriptions.append(node.create_subscription(
            BatteryState if battery['mode'] == 'battery_state' else Float32,
            battery['topic'], lambda message: keep('battery', message), qos_profile_sensor_data))
    lifecycle = {name: {'client': node.create_client(GetState, name+'/get_state'),
                       'future': None, 'sent': 0., 'value': None, 'at': 0.,
                       'params': node.create_client(GetParameters, name+'/get_parameters'),
                       'param_future': None, 'param_sent': 0., 'param_at': 0., 'sim': None}
                 for name in nav['lifecycle_nodes']}
    metadata = yaml.safe_load(Path(nav['map_yaml']).read_text())

    def emit(message):
        connection.send(message)

    def report():
        errors, pose = [], None
        now = time.monotonic()
        for key in ('map', 'scan', 'odom'):
            if key not in messages:
                errors.append('No data: '+nav[key+'_topic'])
            elif key != 'map':
                message, at = messages[key]
                age = (node.get_clock().now().nanoseconds/1e9-message.header.stamp.sec
                       - message.header.stamp.nanosec/1e9)
                if not -.5 <= age <= nav['max_data_age'] or now-at > nav['max_data_age']:
                    errors.append('Stale data: '+key)
        if 'map' in messages:
            info = messages['map'][0].info
            q = info.origin.orientation
            yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            actual = [info.resolution, info.origin.position.x, info.origin.position.y, yaw]
            expected = [metadata['resolution'], *metadata['origin']]
            if any(abs(a-b)>1e-5 for a, b in zip(actual, expected)):
                errors.append('Active map geometry differs from configured map YAML')
            if messages['map'][0].header.frame_id != nav['map_frame']:
                errors.append('Map frame differs from nav2.map_frame')
        try:
            transform = buffer.lookup_transform(nav['map_frame'], nav['base_frame'], rclpy.time.Time())
            age = (node.get_clock().now().nanoseconds/1e9-transform.header.stamp.sec
                   - transform.header.stamp.nanosec/1e9)
            if not -.5 <= age <= nav['max_data_age']:
                errors.append('Localization TF is stale')
            t, q = transform.transform.translation, transform.transform.rotation
            pose = [t.x, t.y, math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))]
        except TransformException:
            errors.append('Missing TF: '+nav['map_frame']+' -> '+nav['base_frame'])
        for name, state in lifecycle.items():
            if state['value'] != 3 or now-state['at'] > 4:
                errors.append('Lifecycle not active/fresh: '+name)
            if state['sim'] is not False or now-state['param_at'] > 6:
                errors.append('use_sim_time not confirmed false: '+name)
        servers = 0
        for name, namespace in node.get_node_names_and_namespaces():
            try:
                servers += sum(a == nav['navigate_action'] for a, _ in
                    get_action_server_names_and_types_by_node(node, name, namespace))
            except Exception:
                pass
        if servers != 1 or not action.server_is_ready():
            errors.append('Expected exactly one NavigateToPose server, found '+str(servers))
        soc = None
        if 'battery' in messages and now-messages['battery'][1] < 10:
            message = messages['battery'][0]
            if battery['mode'] == 'battery_state':
                value = float(message.percentage)
                if message.present and math.isfinite(value) and 0 <= value <= 1:
                    soc = value
            else:
                value = float(message.data)
                if math.isfinite(value) and value > 0:
                    soc = max(0., min(1., (value-battery['empty_voltage'])/
                                     (battery['full_voltage']-battery['empty_voltage'])))
        return {'nav2_ready': not errors, 'pose': pose, 'errors': errors, 'battery_soc': soc,
                'lifecycle': {k: v['value'] for k, v in lifecycle.items()}, 'action_servers': servers}

    def result(future, request_id):
        goals.pop(request_id, None)
        cancel_on_accept.discard(request_id)
        try:
            emit({'kind': 'result', 'id': request_id, 'status': future.result().status})
        except Exception as exc:
            emit({'kind': 'error', 'id': request_id, 'error': str(exc)})

    def accepted(future, request_id):
        pending.discard(request_id)
        try:
            handle = future.result()
            emit({'kind': 'accepted', 'id': request_id, 'accepted': handle.accepted})
            if handle.accepted:
                goals[request_id] = handle
                handle.get_result_async().add_done_callback(lambda f: result(f, request_id))
                if closing or request_id in cancel_on_accept:
                    handle.cancel_goal_async()
        except Exception as exc:
            emit({'kind': 'error', 'id': request_id, 'error': str(exc)})

    def cancel(request_id):
        cancel_on_accept.add(request_id)
        if request_id in goals:
            goals[request_id].cancel_goal_async()

    def poll_lifecycle():
        now = time.monotonic()
        for state in lifecycle.values():
            future = state['future']
            if future is not None and future.done():
                try:
                    state['value'], state['at'] = future.result().current_state.id, now
                except Exception:
                    state['value'] = None
                state['future'] = None
            if state['future'] is not None and now-state['sent'] > 2:
                state['future'].cancel()
                state['future'], state['value'] = None, None
            if state['future'] is None and now-state['sent'] > 1 and state['client'].service_is_ready():
                state['future'] = state['client'].call_async(GetState.Request())
                state['sent'] = now
            future = state['param_future']
            if future is not None and future.done():
                try:
                    value = future.result().values[0]
                    state['sim'] = value.bool_value if value.type == 1 else None
                    state['param_at'] = now
                except Exception:
                    state['sim'] = None
                state['param_future'] = None
            if state['param_future'] is not None and now-state['param_sent'] > 2:
                state['param_future'].cancel()
                state['param_future'], state['sim'] = None, None
            if state['param_future'] is None and now-state['param_sent'] > 2 and state['params'].service_is_ready():
                state['param_future'] = state['params'].call_async(GetParameters.Request(names=['use_sim_time']))
                state['param_sent'] = now

    next_report, latest = 0., {'nav2_ready': False}
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.03)
            poll_lifecycle()
            if time.monotonic() >= next_report:
                latest = report()
                emit({'kind': 'state', 'state': latest})
                next_report = time.monotonic()+.25
                if not latest['nav2_ready'] and allow_commands:
                    for request_id in list(goals)+list(pending):
                        cancel(request_id)
            while connection.poll():
                message = connection.recv()
                operation, request_id = message['op'], message.get('id')
                if operation == 'close':
                    closing, close_deadline = True, time.monotonic()+2
                    for owned in list(goals)+list(pending):
                        cancel(owned)
                elif operation in ('goal', 'cancel'):
                    if not allow_commands:
                        emit({'kind': 'error', 'id': request_id, 'error': 'Read-only worker'})
                        continue
                    if operation == 'cancel':
                        cancel(request_id)
                    elif closing or not latest['nav2_ready'] or goals or pending:
                        emit({'kind': 'accepted', 'id': request_id, 'accepted': False})
                    else:
                        goal = NavigateToPose.Goal()
                        goal.pose.header.frame_id = nav['map_frame']
                        goal.pose.header.stamp = node.get_clock().now().to_msg()
                        x, y, yaw = message['pose']
                        goal.pose.pose.position.x, goal.pose.pose.position.y = float(x), float(y)
                        goal.pose.pose.orientation.z = math.sin(yaw/2)
                        goal.pose.pose.orientation.w = math.cos(yaw/2)
                        goal.behavior_tree = message.get('behavior_tree', '')
                        pending.add(request_id)
                        def feedback(message, i=request_id):
                            remaining = message.feedback.estimated_time_remaining
                            emit({'kind': 'feedback', 'id': i,
                                  'remaining': remaining.sec+remaining.nanosec/1e9})
                        action.send_goal_async(goal, feedback_callback=feedback).add_done_callback(
                            lambda f, i=request_id: accepted(f, i))
            if closing and (not goals and not pending or time.monotonic() > close_deadline):
                break
    except (EOFError, BrokenPipeError, OSError):
        pass
    except Exception as exc:
        try:
            emit({'kind': 'fatal', 'error': str(exc)})
        except (BrokenPipeError, OSError):
            pass
    finally:
        for request_id in list(goals):
            try:
                cancel(request_id)
            except Exception:
                pass
        deadline = time.monotonic()+1
        while rclpy.ok() and (goals or pending) and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        node.destroy_node()
        rclpy.try_shutdown()
        connection.close()

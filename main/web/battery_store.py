"""Read-only battery telemetry cache, shared by the ROS reader and HTTP threads."""
import json
import math
import threading
import time


class BatteryStore:
    def __init__(self):
        self.samples = {}
        self.lock = threading.Lock()

    def receive(self, payload):
        try:
            data = json.loads(payload)
            if not all(isinstance(data.get(k), str) and data[k] for k in ('fleet', 'robot', 'source')):
                return
            for key in ('soc', 'voltage', 'age_seconds'):
                value = data.get(key)
                if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                    return
            if data.get('soc') is not None and not 0 <= data['soc'] <= 1:
                return
            with self.lock:
                self.samples[(data['fleet'], data['robot'])] = (data, time.monotonic())
        except (ValueError, TypeError, AttributeError):
            return

    def snapshot(self):
        now = time.monotonic()
        with self.lock:
            result = []
            for data, received in self.samples.values():
                value = dict(data)
                age = data.get('age_seconds')
                value['age_seconds'] = age + now-received if age is not None else None
                value['stale'] = bool(data.get('stale', True) or age is None
                                      or value['age_seconds'] > 10.)
                if value['stale']:
                    value['soc'] = value['voltage'] = None
                result.append(value)
        return {'robots': result}


class RosBatteryReader:
    def __init__(self, store):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from std_msgs.msg import String
        self.context = Context()
        rclpy.init(args=[], context=self.context, domain_id=0)
        self.node = rclpy.create_node('brin_dashboard_batteries', context=self.context)
        self.subscription = self.node.create_subscription(
            String, '/brin/battery_states', lambda msg: store.receive(msg.data), 10)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()

    def close(self):
        self.executor.shutdown(timeout_sec=2.)
        self.thread.join(timeout=2.)
        self.node.destroy_node()
        self.context.try_shutdown()

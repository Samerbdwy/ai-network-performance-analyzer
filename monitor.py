import os
import time
import sqlite3
import socket
import threading
import ipaddress
from datetime import datetime
from ping3 import ping

class NetworkMonitor:
    def __init__(self, db_path="data/metrics.db"):
        self.db_path = db_path
        self.running = False
        self.thread = None
        self.targets = []  # EMPTY - user must add targets
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                target_name TEXT,
                target_ip TEXT,
                latency REAL,
                packet_loss REAL
            )
        ''')
        conn.commit()
        conn.close()
    
    def resolve_target(self, target):
        """Resolve a hostname or IP string to an IP address."""
        if not target or not str(target).strip():
            raise ValueError('Target must be a non-empty IP address or hostname.')

        try:
            return socket.gethostbyname(target.strip())
        except socket.gaierror as e:
            raise ValueError(f'Unable to resolve target: {target}') from e

    def _compute_jitter(self, latencies):
        """Compute average absolute latency variation between sequential probes."""
        if len(latencies) < 2:
            return 0.0

        differences = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]
        return sum(differences) / len(differences)

    def ping_target(self, target, count=5, timeout=2, interval=0.5):
        """Ping a target and return a structured performance summary."""
        resolved_ip = self.resolve_target(target)
        latencies = []
        lost = 0

        for _ in range(count):
            try:
                response = ping(resolved_ip, timeout=timeout)
                if response is not None:
                    latencies.append(response * 1000)
                else:
                    lost += 1
            except Exception:
                lost += 1

            time.sleep(interval)

        packet_loss = round((lost / count) * 100, 2)
        success_count = count - lost

        if success_count:
            avg_latency = round(sum(latencies) / success_count, 2)
            jitter = round(self._compute_jitter(latencies), 2)
            min_latency = round(min(latencies), 2)
            max_latency = round(max(latencies), 2)
        else:
            avg_latency = 0.0
            jitter = 0.0
            min_latency = 0.0
            max_latency = 0.0

        try:
            ip_obj = ipaddress.ip_address(resolved_ip)
            target_type = 'local network' if ip_obj.is_private or ip_obj.is_loopback else 'internet'
        except Exception:
            target_type = 'unknown'

        return {
            "target": target,
            "ip": resolved_ip,
            "target_type": target_type,
            "probe_count": count,
            "success_count": success_count,
            "avg_latency": avg_latency,
            "min_latency": min_latency,
            "max_latency": max_latency,
            "jitter": jitter,
            "packet_loss": packet_loss,
            "success_rate": round(100.0 - packet_loss, 2)
        }

    def scan_all(self):
        """Scan all targets and return results"""
        results = []
        for target in self.targets:
            stats = self.ping_target(target["ip"])
            results.append({
                "name": target["name"],
                "ip": stats["ip"],
                **stats
            })
        return results
    
    def add_target(self, name, ip):
        """Add a target to monitor"""
        self.targets.append({"name": name, "ip": ip})
    
    def remove_target(self, name):
        """Remove a target"""
        self.targets = [t for t in self.targets if t["name"] != name]
    
    def save_metrics(self):
        """Save current metrics to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for target in self.targets:
            stats = self.ping_target(target["ip"], count=10)
            cursor.execute('''
                INSERT INTO metrics (timestamp, target_name, target_ip, latency, packet_loss)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), target["name"], stats["ip"], 
                  stats["avg_latency"], stats["packet_loss"]))

        conn.commit()
        conn.close()
    
    def get_history(self, target_name=None, hours=24):
        """Get historical data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if target_name:
            cursor.execute('''
                SELECT timestamp, latency, packet_loss FROM metrics 
                WHERE target_name = ? AND timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp
            ''', (target_name, hours))
        else:
            cursor.execute('''
                SELECT timestamp, target_name, latency, packet_loss FROM metrics 
                WHERE timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp
            ''', (hours,))
        
        data = cursor.fetchall()
        conn.close()
        return data
    
    def start_background_monitoring(self, interval=60):
        """Start background monitoring thread"""
        self.running = True
        
        def monitor_loop():
            while self.running:
                self.save_metrics()
                time.sleep(interval)
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
    
    def stop_monitoring(self):
        self.running = False
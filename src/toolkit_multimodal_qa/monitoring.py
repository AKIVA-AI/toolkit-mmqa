"""Monitoring and health checks for Multimodal Dataset QA"""
from datetime import datetime
from typing import Dict, Any


class HealthCheck:
    @staticmethod
    def check_system() -> Dict[str, Any]:
        try:
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}


class Metrics:
    def __init__(self):
        self.metrics = {"datasets_checked": 0, "issues_found": 0}
    
    def record_check(self, issues: int = 0):
        self.metrics["datasets_checked"] += 1
        self.metrics["issues_found"] += issues
    
    def get_metrics(self) -> Dict[str, Any]:
        return {**self.metrics, "timestamp": datetime.utcnow().isoformat()}


_metrics = Metrics()


def get_metrics() -> Dict[str, Any]:
    return _metrics.get_metrics()


def get_health_status() -> Dict[str, Any]:
    return {"system": HealthCheck.check_system(), "metrics": get_metrics()}


"""
Structured JSON Logging Engine (FLS-129).
Provides schema-validated JSON log event emission with redaction of sensitive credentials.
"""

import json
import logging
import datetime
from typing import Dict, Any, Optional, List

SENSITIVE_KEYS = {"password", "secret", "token", "auth", "credit_card", "cvv"}

class StructuredLogger:
    """
    Emits structured, high-cardinality machine-readable JSON logs for operations & audit.
    """
    def __init__(self, name: str = "flashsale.engine"):
        self.name = name
        self.logger = logging.getLogger(name)
        self._captured_logs: List[Dict[str, Any]] = []

    def _redact_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, dict):
                cleaned[k] = self._redact_payload(v)
            else:
                cleaned[k] = v
        return cleaned

    def log(
        self,
        level: str,
        event: str,
        message: str,
        sku_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload = {
            "timestamp": timestamp,
            "level": level.upper(),
            "event": event,
            "logger": self.name,
            "message": message,
        }
        if sku_id:
            payload["sku_id"] = sku_id
        if user_id:
            payload["user_id"] = user_id
        if trace_id:
            payload["trace_id"] = trace_id
        if data:
            payload["data"] = self._redact_payload(data)

        self._captured_logs.append(payload)
        json_line = json.dumps(payload)

        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(json_line)
        return payload

    def info(self, event: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log("INFO", event, message, **kwargs)

    def warning(self, event: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log("WARNING", event, message, **kwargs)

    def error(self, event: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log("ERROR", event, message, **kwargs)

    def get_captured_logs(self) -> List[Dict[str, Any]]:
        return list(self._captured_logs)

    def clear_captured_logs(self) -> None:
        self._captured_logs.clear()

global_structured_logger = StructuredLogger()

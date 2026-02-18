"""
Audit trail logging
"""
from datetime import datetime
from typing import Optional
import json
from pathlib import Path


class AuditLog:
    """
    Maintains an audit trail of user actions
    """
    
    def __init__(self, log_path: str = "data/audit_log.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_action(
        self,
        action: str,
        user: str,
        details: dict,
        timestamp: Optional[datetime] = None
    ):
        """Log an action to the audit trail"""
        if timestamp is None:
            timestamp = datetime.now()
        
        log_entry = {
            'timestamp': timestamp.isoformat(),
            'action': action,
            'user': user,
            'details': details
        }
        
        # Append to log file
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def log_finding_override(
        self,
        finding_id: str,
        unit_number: str,
        rule_name: str,
        user: str,
        status: str,
        notes: str
    ):
        """Log a finding override action"""
        self.log_action(
            action='finding_override',
            user=user,
            details={
                'finding_id': finding_id,
                'unit_number': unit_number,
                'rule_name': rule_name,
                'new_status': status,
                'notes': notes
            }
        )
    
    def log_data_load(
        self,
        source: str,
        file_name: str,
        user: str,
        records_loaded: int
    ):
        """Log a data load action"""
        self.log_action(
            action='data_load',
            user=user,
            details={
                'source': source,
                'file_name': file_name,
                'records_loaded': records_loaded
            }
        )
    
    def log_export(
        self,
        export_type: str,
        user: str,
        record_count: int
    ):
        """Log an export action"""
        self.log_action(
            action='export',
            user=user,
            details={
                'export_type': export_type,
                'record_count': record_count
            }
        )
    
    def get_recent_logs(self, limit: int = 100) -> list:
        """Get recent log entries"""
        if not self.log_path.exists():
            return []
        
        logs = []
        with open(self.log_path, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        
        # Return most recent entries
        return logs[-limit:]

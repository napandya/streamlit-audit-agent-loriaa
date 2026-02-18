"""
Database persistence layer (optional DuckDB/SQLite)
"""
import duckdb
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from models.unit import Unit, RecurringTransaction, AuditFinding
from config import settings


class Database:
    """
    Optional database persistence using DuckDB
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.conn = None
        
        if settings.USE_DATABASE:
            self._init_database()
    
    def _init_database(self):
        """Initialize database and create tables"""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        self.conn = duckdb.connect(self.db_path)
        
        # Create tables
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables"""
        if not self.conn:
            return
        
        # Units table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS units (
                unit_id VARCHAR PRIMARY KEY,
                unit_number VARCHAR,
                resident_name VARCHAR,
                is_employee_unit BOOLEAN,
                lease_start DATE,
                lease_end DATE,
                base_rent DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Transactions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id VARCHAR PRIMARY KEY,
                unit_id VARCHAR,
                unit_number VARCHAR,
                category VARCHAR,
                subcategory VARCHAR,
                amount DECIMAL(10,2),
                month DATE,
                description VARCHAR,
                source VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Findings table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                finding_id VARCHAR PRIMARY KEY,
                unit_id VARCHAR,
                unit_number VARCHAR,
                rule_id VARCHAR,
                rule_name VARCHAR,
                severity VARCHAR,
                month DATE,
                delta DECIMAL(10,2),
                explanation TEXT,
                status VARCHAR,
                notes TEXT,
                created_at TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by VARCHAR
            )
        """)
    
    def save_units(self, units: List[Unit]):
        """Save units to database"""
        if not self.conn:
            return
        
        for unit in units:
            self.conn.execute("""
                INSERT OR REPLACE INTO units 
                (unit_id, unit_number, resident_name, is_employee_unit, lease_start, lease_end, base_rent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                unit.unit_id,
                unit.unit_number,
                unit.resident_name,
                unit.is_employee_unit,
                unit.lease_start,
                unit.lease_end,
                unit.base_rent
            ))
    
    def save_transactions(self, transactions: List[RecurringTransaction]):
        """Save transactions to database"""
        if not self.conn:
            return
        
        for txn in transactions:
            self.conn.execute("""
                INSERT OR REPLACE INTO transactions
                (transaction_id, unit_id, unit_number, category, subcategory, amount, month, description, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                txn.transaction_id,
                txn.unit_id,
                txn.unit_number,
                txn.category,
                txn.subcategory,
                txn.amount,
                txn.month,
                txn.description,
                txn.source
            ))
    
    def save_findings(self, findings: List[AuditFinding]):
        """Save findings to database"""
        if not self.conn:
            return
        
        for finding in findings:
            self.conn.execute("""
                INSERT OR REPLACE INTO findings
                (finding_id, unit_id, unit_number, rule_id, rule_name, severity, month, delta, 
                 explanation, status, notes, created_at, reviewed_at, reviewed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                finding.finding_id,
                finding.unit_id,
                finding.unit_number,
                finding.rule_id,
                finding.rule_name,
                finding.severity,
                finding.month,
                finding.delta,
                finding.explanation,
                finding.status,
                finding.notes,
                finding.created_at,
                finding.reviewed_at,
                finding.reviewed_by
            ))
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

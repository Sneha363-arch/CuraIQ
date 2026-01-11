from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Iterable, Optional
from math import radians, sin, cos, sqrt, atan2

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.types import TypeDecorator, TEXT
from werkzeug.security import check_password_hash, generate_password_hash
import re
import os
from werkzeug.utils import secure_filename

# Import predictor
try:
    from predictor import get_predictor
    predictor_available = True
except ImportError:
    predictor_available = False
    print("Warning: Predictor module not available. Using fallback predictions.")


class JSONEncoded(TypeDecorator):
    impl = TEXT

    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Optional[str], dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///triage.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

db = SQLAlchemy(app)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    def verify_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "name": self.name,
        }


class Patient(db.Model, TimestampMixin):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(32))
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(32), nullable=False)
    location = db.Column(db.String(255))
    diagnosis_id = db.Column(db.Integer, db.ForeignKey("diagnoses.id", ondelete="CASCADE"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "patient_name": self.patient_name,
            "email": self.email,
            "phone": self.phone,
            "age": self.age,
            "gender": self.gender,
            "location": self.location,
            "diagnosis_id": self.diagnosis_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model, TimestampMixin):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(
        db.Integer, db.ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    patient_name = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(32), nullable=False)  # approved, rejected, corrected
    approval_type = db.Column(db.String(32))  # online, offline (only for approved)
    doctor_name = db.Column(db.String(255))
    read = db.Column(db.Boolean, default=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "diagnosis_id": self.diagnosis_id,
            "patient_name": self.patient_name,
            "message": self.message,
            "notification_type": self.notification_type,
            "approval_type": self.approval_type,
            "doctor_name": self.doctor_name,
            "read": self.read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Diagnosis(db.Model, TimestampMixin):
    __tablename__ = "diagnoses"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(32), nullable=False)
    location = db.Column(db.String(255))
    duration = db.Column(db.String(64))
    temperature = db.Column(db.String(32))
    symptoms = db.Column(JSONEncoded, default=list)
    medical_history = db.Column(db.Text)
    diagnosis = db.Column(db.String(255), default="Dengue Fever")
    confidence = db.Column(db.Integer, default=80)
    severity = db.Column(db.String(32), default="moderate")
    status = db.Column(db.String(32), default="pending")
    doctor_notes = db.Column(db.Text)
    verified_by = db.Column(db.String(255))
    platelet_count = db.Column(db.Float)
    wbc_count = db.Column(db.Float)
    rbc_count = db.Column(db.Float)
    all_probabilities = db.Column(JSONEncoded, default=list)
    patient_email = db.Column(db.String(255))
    patient_phone = db.Column(db.String(32))
    patient_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "patient_name": self.patient_name,
            "age": self.age,
            "gender": self.gender,
            "location": self.location,
            "duration": self.duration,
            "temperature": self.temperature,
            "symptoms": self.symptoms or [],
            "medical_history": self.medical_history,
            "diagnosis": self.diagnosis,
            "confidence": self.confidence,
            "severity": self.severity,
            "status": self.status,
            "doctor_notes": self.doctor_notes,
            "verified_by": self.verified_by,
            "platelet_count": self.platelet_count,
            "wbc_count": self.wbc_count,
            "rbc_count": self.rbc_count,
            "all_probabilities": self.all_probabilities or [],
            "patient_email": self.patient_email,
            "patient_phone": self.patient_phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Prescription(db.Model, TimestampMixin):
    __tablename__ = "prescriptions"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(255), nullable=False)
    medications = db.Column(JSONEncoded, default=dict)
    instructions = db.Column(db.Text)
    status = db.Column(db.String(32), default="pending")
    dispensed_at = db.Column(db.DateTime)
    dispensed_by = db.Column(db.String(255))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "patient_name": self.patient_name,
            "medications": self.medications or {},
            "instructions": self.instructions,
            "status": self.status,
            "dispensed_at": self.dispensed_at.isoformat() if self.dispensed_at else None,
            "dispensed_by": self.dispensed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class InventoryItem(db.Model, TimestampMixin):
    __tablename__ = "inventory"

    id = db.Column(db.Integer, primary_key=True)
    drug_name = db.Column(db.String(255), nullable=False)
    generic_name = db.Column(db.String(255))
    batch_number = db.Column(db.String(128))
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(32), default="tablets")
    price = db.Column(db.Float, default=0.0)
    expiry_date = db.Column(db.String(64))
    manufacturer = db.Column(db.String(255))
    reorder_level = db.Column(db.Integer, default=10)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "drug_name": self.drug_name,
            "generic_name": self.generic_name,
            "batch_number": self.batch_number,
            "quantity": self.quantity,
            "unit": self.unit,
            "price": self.price,
            "expiry_date": self.expiry_date,
            "manufacturer": self.manufacturer,
            "reorder_level": self.reorder_level,
        }


class CollaborationMessage(db.Model, TimestampMixin):
    __tablename__ = "collaboration_messages"

    id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(
        db.Integer, db.ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    sender_role = db.Column(db.String(64), nullable=False)
    sender_name = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "diagnosis_id": self.diagnosis_id,
            "sender_role": self.sender_role,
            "sender_name": self.sender_name,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================
# PHARMACEUTICAL SUPPLY CHAIN MODELS
# ============================================

class Pharmacy(db.Model, TimestampMixin):
    __tablename__ = "pharmacies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    license_number = db.Column(db.String(100), unique=True)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(20))
    latitude = db.Column(db.Numeric(10, 8))
    longitude = db.Column(db.Numeric(11, 8))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    owner_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "license_number": self.license_number,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "pincode": self.pincode,
            "latitude": float(self.latitude) if self.latitude else None,
            "longitude": float(self.longitude) if self.longitude else None,
            "phone": self.phone,
            "email": self.email,
            "owner_name": self.owner_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Pharmacist(db.Model, TimestampMixin):
    __tablename__ = "pharmacists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id", ondelete="SET NULL"))
    license_number = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "pharmacy_id": self.pharmacy_id,
            "license_number": self.license_number,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Manufacturer(db.Model, TimestampMixin):
    __tablename__ = "manufacturers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    license_number = db.Column(db.String(100), unique=True)
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    country = db.Column(db.String(100), default="India")
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    website = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "license_number": self.license_number,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Product(db.Model, TimestampMixin):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey("manufacturers.id", ondelete="SET NULL"))
    product_name = db.Column(db.String(255), nullable=False)
    generic_name = db.Column(db.String(255))
    drug_class = db.Column(db.String(100))
    form = db.Column(db.String(50))  # tablet, syrup, injection, etc.
    strength = db.Column(db.String(100))  # 500mg, 10ml, etc.
    unit = db.Column(db.String(50), default="tablets")
    barcode = db.Column(db.String(100))
    hsn_code = db.Column(db.String(50))
    schedule = db.Column(db.String(10))  # H, H1, X, etc.
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "manufacturer_id": self.manufacturer_id,
            "product_name": self.product_name,
            "generic_name": self.generic_name,
            "drug_class": self.drug_class,
            "form": self.form,
            "strength": self.strength,
            "unit": self.unit,
            "barcode": self.barcode,
            "hsn_code": self.hsn_code,
            "schedule": self.schedule,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PharmacyInventory(db.Model, TimestampMixin):
    __tablename__ = "pharmacy_inventory"

    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    batch_number = db.Column(db.String(100))
    lot_number = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=0, nullable=False)
    unit = db.Column(db.String(50), default="tablets")
    price = db.Column(db.Numeric(10, 2))
    expiry_date = db.Column(db.Date)
    supplier_name = db.Column(db.String(255))
    received_date = db.Column(db.Date)
    min_stock_level = db.Column(db.Integer, default=10)
    max_stock_level = db.Column(db.Integer, default=1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pharmacy_id": self.pharmacy_id,
            "product_id": self.product_id,
            "batch_number": self.batch_number,
            "lot_number": self.lot_number,
            "quantity": self.quantity,
            "unit": self.unit,
            "price": float(self.price) if self.price else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "supplier_name": self.supplier_name,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "min_stock_level": self.min_stock_level,
            "max_stock_level": self.max_stock_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PrescriptionItem(db.Model, TimestampMixin):
    __tablename__ = "prescription_items"

    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    generic_name = db.Column(db.String(255))
    dosage = db.Column(db.String(100))
    frequency = db.Column(db.String(100))
    duration_days = db.Column(db.Integer)
    quantity = db.Column(db.Integer, nullable=False)
    instructions = db.Column(db.Text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prescription_id": self.prescription_id,
            "product_name": self.product_name,
            "generic_name": self.generic_name,
            "dosage": self.dosage,
            "frequency": self.frequency,
            "duration_days": self.duration_days,
            "quantity": self.quantity,
            "instructions": self.instructions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Dispensation(db.Model, TimestampMixin):
    __tablename__ = "dispensations"

    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    pharmacist_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id", ondelete="SET NULL"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    batch_number = db.Column(db.String(100))
    lot_number = db.Column(db.String(100))
    expiry_date = db.Column(db.Date)
    quantity_dispensed = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2))
    status = db.Column(db.String(32), default="dispensed")
    notes = db.Column(db.Text)
    dispensed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prescription_id": self.prescription_id,
            "pharmacist_id": self.pharmacist_id,
            "pharmacy_id": self.pharmacy_id,
            "product_id": self.product_id,
            "batch_number": self.batch_number,
            "lot_number": self.lot_number,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "quantity_dispensed": self.quantity_dispensed,
            "price": float(self.price) if self.price else None,
            "status": self.status,
            "notes": self.notes,
            "dispensed_at": self.dispensed_at.isoformat() if self.dispensed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DemandSignal(db.Model, TimestampMixin):
    __tablename__ = "demand_signals"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    region = db.Column(db.String(100))
    demand_quantity = db.Column(db.Integer, nullable=False)
    signal_date = db.Column(db.Date, nullable=False)
    signal_type = db.Column(db.String(50), default="prescription")
    source = db.Column(db.String(50))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "region": self.region,
            "demand_quantity": self.demand_quantity,
            "signal_date": self.signal_date.isoformat() if self.signal_date else None,
            "signal_type": self.signal_type,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class StockoutEvent(db.Model, TimestampMixin):
    __tablename__ = "stockout_events"

    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id", ondelete="SET NULL"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    region = db.Column(db.String(100))
    stockout_date = db.Column(db.Date, nullable=False)
    duration_days = db.Column(db.Integer)
    impact_score = db.Column(db.Numeric(5, 2))
    resolved_at = db.Column(db.DateTime)
    status = db.Column(db.String(32), default="active")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pharmacy_id": self.pharmacy_id,
            "product_id": self.product_id,
            "region": self.region,
            "stockout_date": self.stockout_date.isoformat() if self.stockout_date else None,
            "duration_days": self.duration_days,
            "impact_score": float(self.impact_score) if self.impact_score else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SupplyChainAlert(db.Model, TimestampMixin):
    __tablename__ = "supply_chain_alerts"

    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"))
    region = db.Column(db.String(100))
    severity = db.Column(db.String(32), default="medium")
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default="active")
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at = db.Column(db.DateTime)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "product_id": self.product_id,
            "region": self.region,
            "severity": self.severity,
            "message": self.message,
            "status": self.status,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProductPriorityScore(db.Model, TimestampMixin):
    __tablename__ = "product_priority_scores"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    region = db.Column(db.String(100))
    urgency_score = db.Column(db.Numeric(5, 2), nullable=False)
    demand_score = db.Column(db.Numeric(5, 2))
    stockout_score = db.Column(db.Numeric(5, 2))
    disease_score = db.Column(db.Numeric(5, 2))
    expiry_risk_score = db.Column(db.Numeric(5, 2))
    capacity_score = db.Column(db.Numeric(5, 2))
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "region": self.region,
            "urgency_score": float(self.urgency_score) if self.urgency_score else None,
            "demand_score": float(self.demand_score) if self.demand_score else None,
            "stockout_score": float(self.stockout_score) if self.stockout_score else None,
            "disease_score": float(self.disease_score) if self.disease_score else None,
            "expiry_risk_score": float(self.expiry_risk_score) if self.expiry_risk_score else None,
            "capacity_score": float(self.capacity_score) if self.capacity_score else None,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }


class FollowUp(db.Model, TimestampMixin):
    __tablename__ = "follow_ups"

    id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(
        db.Integer, db.ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    patient_name = db.Column(db.String(255), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "diagnosis_id": self.diagnosis_id,
            "patient_name": self.patient_name,
            "scheduled_date": self.scheduled_date.isoformat()
            if self.scheduled_date
            else None,
            "notes": self.notes,
        }


active_tokens: Dict[str, int] = {}


def auth_required(roles: Optional[Iterable[str]] = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            auth_header = request.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]

            user_id = active_tokens.get(token)
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401

            user = db.session.get(User, user_id)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401

            if roles:
                role_set = set(roles)
                if user.role not in role_set:
                    return jsonify({"error": "Forbidden"}), 403

            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def init_db() -> None:
    import os
    import sqlite3
    
    # Check if database exists and needs migration
    db_path = "instance/triage.db"
    if os.path.exists(db_path):
        try:
            # Try to query to check if new columns exist
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(diagnoses)")
            columns = [col[1] for col in cursor.fetchall()]
            conn.close()
            
            # Check if new columns are missing
            new_columns = ['platelet_count', 'wbc_count', 'rbc_count', 'all_probabilities', 'patient_email', 'patient_phone', 'patient_user_id']
            missing_columns = [col for col in new_columns if col not in columns]
            
            if missing_columns:
                print(f"Database needs migration. Adding columns to diagnoses: {missing_columns}")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                for col in missing_columns:
                    if col == 'all_probabilities':
                        cursor.execute(f"ALTER TABLE diagnoses ADD COLUMN {col} TEXT")
                    elif col in ['patient_email', 'patient_phone']:
                        cursor.execute(f"ALTER TABLE diagnoses ADD COLUMN {col} TEXT")
                    elif col == 'patient_user_id':
                        cursor.execute(f"ALTER TABLE diagnoses ADD COLUMN {col} INTEGER")
                    else:
                        cursor.execute(f"ALTER TABLE diagnoses ADD COLUMN {col} REAL")
                conn.commit()
                conn.close()
                print("Diagnoses migration completed successfully")
            
            # Check patients table for user_id column
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(patients)")
            patient_columns = [col[1] for col in cursor.fetchall()]
            if 'user_id' not in patient_columns:
                print("Adding user_id column to patients table")
                cursor.execute("ALTER TABLE patients ADD COLUMN user_id INTEGER")
                conn.commit()
                print("Patients migration completed successfully")
            
            # Check for unique constraint on patients.email and remove it if exists
            # (Email should not be unique in patients table - multiple patients can have same email)
            try:
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='patients'")
                table_sql = cursor.fetchone()
                if table_sql and table_sql[0]:
                    # Check if there's a unique constraint on email
                    if 'UNIQUE' in table_sql[0].upper() and 'email' in table_sql[0].lower():
                        print("Warning: Unique constraint found on patients.email. This may cause registration issues.")
                        print("Consider removing the unique constraint if patients should be able to share emails.")
            except Exception as e:
                print(f"Could not check for unique constraints: {e}")
            
            # Check notifications table for approval_type column
            cursor.execute("PRAGMA table_info(notifications)")
            notification_columns = [col[1] for col in cursor.fetchall()]
            if 'approval_type' not in notification_columns:
                print("Adding approval_type column to notifications table")
                cursor.execute("ALTER TABLE notifications ADD COLUMN approval_type TEXT")
                conn.commit()
                print("Notifications migration completed successfully")
            conn.close()
        except Exception as e:
            print(f"Migration error: {e}. Recreating database...")
            # If migration fails, backup and recreate
            if os.path.exists(db_path):
                backup_path = db_path + ".backup"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(db_path, backup_path)
                print(f"Old database backed up to {backup_path}")
    
    try:
        # Create all tables - SQLAlchemy will handle schema updates
        db.create_all()
        
        # Execute additional SQL schema for pharmaceutical tables
        try:
            import sqlite3
            db_path = "instance/triage.db"
            if os.path.exists("database_schema.sql"):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                with open("database_schema.sql", "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                    # Execute statements that don't conflict with SQLAlchemy
                    statements = [s.strip() for s in schema_sql.split(";") if s.strip() and not s.strip().startswith("--")]
                    for statement in statements:
                        # Skip CREATE TABLE statements (handled by SQLAlchemy), but execute indexes and triggers
                        if statement.upper().startswith("CREATE INDEX") or statement.upper().startswith("CREATE TRIGGER"):
                            try:
                                cursor.execute(statement)
                            except sqlite3.OperationalError as e:
                                if "already exists" not in str(e).lower():
                                    print(f"Warning executing statement: {e}")
                conn.commit()
                conn.close()
                print("Additional database schema (indexes, triggers) applied successfully")
        except Exception as schema_error:
            print(f"Warning: Could not apply additional schema: {schema_error}")
    except Exception as e:
        print(f"Warning: Database initialization issue: {e}")
        import traceback
        traceback.print_exc()

    if not User.query.first():
        users = [
            {
                "email": "doctor@hospital.com",
                "password": "password123",
                "role": "doctor",
                "name": "Dr. Arjun Mehta",
            },
            {
                "email": "clinician@example.com",
                "password": "password123",
                "role": "clinician",
                "name": "Dr. Riya Sharma",
            },
            {
                "email": "chemist@example.com",
                "password": "password123",
                "role": "chemist",
                "name": "Sneha Desai",
            },
        ]

        for data in users:
            user = User(
                email=data["email"],
                password_hash=generate_password_hash(data["password"]),
                role=data["role"],
                name=data["name"],
            )
            db.session.add(user)

    if not Diagnosis.query.first():
        demo_cases = [
            Diagnosis(
                patient_name="Rahul Verma",
                age=32,
                gender="male",
                location="Mumbai",
                duration="3",
                temperature="102.4",
                symptoms=["High Fever", "Headache", "Body Pain"],
                medical_history="No chronic conditions",
                diagnosis="Dengue Fever",
                confidence=88,
                severity="moderate",
            ),
            Diagnosis(
                patient_name="Pooja Patel",
                age=27,
                gender="female",
                location="Bengaluru",
                duration="2",
                temperature="101.2",
                symptoms=["High Fever", "Rash", "Fatigue"],
                medical_history="Seasonal allergies",
                diagnosis="Viral Fever",
                confidence=75,
                severity="mild",
            ),
            Diagnosis(
                patient_name="Mohit Singh",
                age=45,
                gender="male",
                location="Delhi",
                duration="4",
                temperature="103.5",
                symptoms=["High Fever", "Chills", "Joint Pain"],
                medical_history="Hypertension",
                diagnosis="Malaria",
                confidence=91,
                severity="critical",
                status="pending",
            ),
        ]
        db.session.add_all(demo_cases)

    if not Prescription.query.first():
        prescriptions = [
            Prescription(
                patient_name="Rahul Verma",
                medications={
                    "Paracetamol 500mg": "1 tablet every 6 hours",
                    "ORS Solution": "200ml after each loose motion",
                },
                instructions="Monitor temperature twice daily",
                status="pending",
            ),
            Prescription(
                patient_name="Aisha Khan",
                medications={
                    "Azithromycin 500mg": "1 tablet daily for 3 days",
                    "Vitamin C": "1 tablet daily",
                },
                instructions="Take antibiotics after meals",
                status="pending",
            ),
        ]
        db.session.add_all(prescriptions)

    if not InventoryItem.query.first():
        inventory = [
            InventoryItem(
                drug_name="Paracetamol 500mg",
                generic_name="Acetaminophen",
                batch_number="PCM-2025-01",
                quantity=240,
                unit="tablets",
                price=1.5,
                expiry_date="2026-06-30",
                manufacturer="MediCare Labs",
                reorder_level=100,
            ),
            InventoryItem(
                drug_name="Azithromycin 500mg",
                generic_name="Azithromycin",
                batch_number="AZI-2024-09",
                quantity=80,
                unit="tablets",
                price=12.0,
                expiry_date="2025-12-31",
                manufacturer="HealWell Pharmaceuticals",
                reorder_level=50,
            ),
            InventoryItem(
                drug_name="ORS Powder",
                generic_name="Oral Rehydration Salts",
                batch_number="ORS-2025-02",
                quantity=60,
                unit="sachets",
                price=5.0,
                expiry_date="2027-02-15",
                manufacturer="HydraMix Labs",
                reorder_level=40,
            ),
        ]
        db.session.add_all(inventory)

    db.session.commit()


with app.app_context():
    init_db()


def create_token(user: User) -> str:
    token = secrets.token_urlsafe(32)
    active_tokens[token] = user.id
    return token


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = data.get("name") or ""
    role = data.get("role", "doctor")
    license_number = data.get("license_number", "")
    specialization = data.get("specialization", "")
    
    # Patient-specific fields
    age = data.get("age")
    gender = data.get("gender")
    phone = data.get("phone")
    location = data.get("location")

    if not email or not password or not name:
        return jsonify({"error": "Email, password, and name are required"}), 400

    # For patient role, require additional fields
    if role == "patient":
        if not age or not gender:
            return jsonify({"error": "Age and gender are required for patient registration"}), 400
        # Validate location is provided (required for patient registration)
        if not location or location.strip() == "":
            return jsonify({"error": "Location is required for patient registration"}), 400
        # Validate age is a valid integer
        try:
            age_int = int(age)
            if age_int <= 0 or age_int > 150:
                return jsonify({"error": "Age must be between 1 and 150"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Age must be a valid number"}), 400
        # Validate gender
        if gender.lower() not in ["male", "female", "other"]:
            return jsonify({"error": "Gender must be male, female, or other"}), 400
    
    # For pharmacist/chemist role, require license and pharmacy info
    if role in ["pharmacist", "chemist"]:
        if not license_number:
            return jsonify({"error": "License number is required for pharmacist registration"}), 400
        if not location:
            return jsonify({"error": "Pharmacy location is required for pharmacist registration"}), 400

    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "User with this email already exists. Please login instead."}), 400

    # If patient, check if patient record with this email already exists
    existing_patient = None
    if role == "patient":
        existing_patient = Patient.query.filter_by(email=email).first()
        if existing_patient:
            # If patient exists and already has a user_id, email is already registered
            if existing_patient.user_id:
                return jsonify({"error": "This email is already registered. Please login instead."}), 400
            # If patient exists but has no user_id (orphaned record), we'll link it to the new user

    # Create new user
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        name=name,
    )
    db.session.add(user)
    db.session.flush()  # Get user.id
    
    # If patient, create or update patient record
    if role == "patient":
        try:
            if existing_patient:
                # Update existing orphaned patient record with new user_id
                existing_patient.user_id = user.id
                existing_patient.patient_name = name  # Update name if changed
                existing_patient.phone = phone.strip() if phone and phone.strip() else existing_patient.phone
                existing_patient.age = int(age)  # Update age
                existing_patient.gender = gender.lower()  # Update gender
                existing_patient.location = location.strip() if location else existing_patient.location
                # Don't need to add, just update
            else:
                # Create new patient record
                patient = Patient(
                    patient_name=name,  # Use the name from registration
                    email=email,
                    phone=phone.strip() if phone and phone.strip() else None,
                    age=int(age),  # Already validated above, guaranteed to be valid int
                    gender=gender.lower(),  # Normalize gender to lowercase
                    location=location.strip() if location else None,  # Location is required, but handle edge cases
                    user_id=user.id,
                )
                db.session.add(patient)
            db.session.flush()  # Ensure patient is saved before commit
        except Exception as e:
            db.session.rollback()
            print(f"Error creating/updating patient record: {e}")
            import traceback
            traceback.print_exc()
            # Check if it's a unique constraint error
            if "UNIQUE constraint" in str(e) or "unique constraint" in str(e).lower():
                return jsonify({"error": "This email is already registered. Please login instead."}), 400
            return jsonify({"error": f"Failed to create patient record: {str(e)}"}), 500
    
    # If pharmacist/chemist, create pharmacist and pharmacy records
    if role in ["pharmacist", "chemist"]:
        try:
            # Check if pharmacist with this license already exists
            existing_pharmacist = Pharmacist.query.filter_by(license_number=license_number).first()
            if existing_pharmacist and existing_pharmacist.user_id:
                return jsonify({"error": "A pharmacist with this license number already exists"}), 400
            
            # Create or find pharmacy
            pharmacy = None
            if location:
                # Try to find existing pharmacy by location
                pharmacy = Pharmacy.query.filter_by(address=location.strip()).first()
                if not pharmacy:
                    # Create new pharmacy
                    pharmacy = Pharmacy(
                        name=f"{name}'s Pharmacy",
                        address=location.strip(),
                        city=location.split(",")[0].strip() if "," in location else location.strip(),
                        owner_name=name,
                        is_active=True,
                    )
                    db.session.add(pharmacy)
                    db.session.flush()
            
            # Create pharmacist record
            if existing_pharmacist:
                # Update existing pharmacist
                existing_pharmacist.user_id = user.id
                existing_pharmacist.name = name
                existing_pharmacist.phone = phone.strip() if phone and phone.strip() else existing_pharmacist.phone
                existing_pharmacist.email = email
                if pharmacy:
                    existing_pharmacist.pharmacy_id = pharmacy.id
            else:
                pharmacist = Pharmacist(
                    user_id=user.id,
                    pharmacy_id=pharmacy.id if pharmacy else None,
                    license_number=license_number,
                    name=name,
                    phone=phone.strip() if phone and phone.strip() else None,
                    email=email,
                    is_active=True,
                )
                db.session.add(pharmacist)
            db.session.flush()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating pharmacist record: {e}")
            import traceback
            traceback.print_exc()
            if "UNIQUE constraint" in str(e) or "unique constraint" in str(e).lower():
                return jsonify({"error": "A pharmacist with this license number or email already exists"}), 400
            return jsonify({"error": f"Failed to create pharmacist record: {str(e)}"}), 500
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error committing registration: {e}")
        import traceback
        traceback.print_exc()
        # Check if it's a unique constraint error
        error_str = str(e).lower()
        if "unique constraint" in error_str or "duplicate" in error_str:
            if "email" in error_str:
                return jsonify({"error": "This email is already registered. Please login instead."}), 400
            return jsonify({"error": "A record with this information already exists. Please login instead."}), 400
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

    token = create_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role")

    user: Optional[User] = User.query.filter_by(email=email).first()
    if not user or not user.verify_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    if role and user.role != role:
        return jsonify({"error": "Role mismatch"}), 403

    token = create_token(user)
    return jsonify({"token": token, "user": user.to_dict()})


@app.route("/api/auth/me", methods=["GET"])
@auth_required()
def current_user():
    return jsonify({"user": g.current_user.to_dict()})


@app.route("/api/patient/me", methods=["GET"])
@auth_required(roles=["patient"])
def patient_current():
    """Get current patient's profile with patient record"""
    user = g.current_user
    patient = Patient.query.filter_by(user_id=user.id).first()
    if not patient:
        return jsonify({"error": "Patient record not found"}), 404
    
    return jsonify({
        "user": user.to_dict(),
        "patient": patient.to_dict()
    })


@app.route("/api/patient/diagnoses", methods=["GET"])
@auth_required(roles=["patient"])
def patient_diagnoses():
    """Get all diagnoses for the logged-in patient"""
    user = g.current_user
    diagnoses = Diagnosis.query.filter_by(patient_user_id=user.id).order_by(Diagnosis.created_at.desc()).all()
    return jsonify([d.to_dict() for d in diagnoses])


@app.route("/api/diagnoses", methods=["GET"])
def list_diagnoses():
    status = request.args.get("status")
    query = Diagnosis.query
    if status:
        query = query.filter_by(status=status)

    diagnoses = query.order_by(Diagnosis.created_at.desc()).all()
    return jsonify([d.to_dict() for d in diagnoses])


@app.route("/api/diagnoses", methods=["POST"])
@auth_required(roles=["patient", "clinician", "doctor"])
def create_diagnosis():
    data = request.get_json() or {}
    required_fields = ["patient_name", "age", "gender"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return (
            jsonify({"error": f"Missing required fields: {', '.join(missing)}"}),
            400,
        )
    
    # Get current user (can be patient or clinician)
    current_user = g.current_user
    patient_record = Patient.query.filter_by(user_id=current_user.id).first() if current_user.role == "patient" else None

    # Use ML model to predict diagnosis and severity
    predicted_diagnosis = "Viral fever"
    predicted_confidence = 75
    predicted_severity = "moderate"
    all_probabilities = []
    
    if predictor_available:
        try:
            predictor = get_predictor()
            
            # Check if medical_history contains text that needs NLP parsing
            medical_history = data.get("medical_history", "")
            parsed_data = {}
            if medical_history:
                parsed_data = predictor.parse_text_input(medical_history)
            
            # Prepare data for prediction (merge parsed data with form data)
            # Build symptoms array from checkboxes if not provided as array
            symptoms_list = data.get("symptoms", [])
            if not symptoms_list or not isinstance(symptoms_list, list):
                symptoms_list = []
                if data.get("headache"): symptoms_list.append("Headache")
                if data.get("joint_pain"): symptoms_list.append("Joint Pain")
                if data.get("leg_pain"): symptoms_list.append("Leg Pain")
                if data.get("muscle_pain"): symptoms_list.append("Muscle Pain")
                if data.get("rash"): symptoms_list.append("Rash")
                if data.get("nausea_vomiting"): symptoms_list.append("Nausea/Vomiting")
                if data.get("vomiting"): symptoms_list.append("Vomiting")
                if data.get("bleeding"): symptoms_list.append("Bleeding")
                if data.get("fatigue"): symptoms_list.append("Fatigue")
                if data.get("cough"): symptoms_list.append("Cough")
                if data.get("chills"): symptoms_list.append("Chills")
                if data.get("sweating"): symptoms_list.append("Sweating")
                if data.get("loss_of_appetite"): symptoms_list.append("Loss of Appetite")
            
            prediction_data = {
                "temperature": data.get("temperature_c") or data.get("temperature") or parsed_data.get("temperature"),
                "duration": data.get("fever_duration_days") or data.get("duration") or parsed_data.get("duration"),
                "symptoms": symptoms_list or parsed_data.get("symptoms", []),
                "platelet_count": data.get("platelet_count") or parsed_data.get("platelet_count"),
                "wbc_count": data.get("wbc_count") or parsed_data.get("wbc_count"),
                "rbc_count": data.get("rbc_count") or parsed_data.get("rbc_count"),
                # Additional parameters for enhanced prediction
                "pulse_bpm": data.get("pulse_bpm"),
                "bp_systolic": data.get("bp_systolic"),
                "bp_diastolic": data.get("bp_diastolic"),
                "resp_rate": data.get("resp_rate"),
                "spo2": data.get("spo2"),
                "hematocrit": data.get("hematocrit"),
                "ast": data.get("ast"),
                "alt": data.get("alt"),
                "hemoglobin": data.get("hemoglobin"),
                "headache": data.get("headache"),
                "joint_pain": data.get("joint_pain"),
                "leg_pain": data.get("leg_pain"),
                "muscle_pain": data.get("muscle_pain"),
                "rash": data.get("rash"),
                "nausea_vomiting": data.get("nausea_vomiting"),
                "vomiting": data.get("vomiting"),
                "bleeding": data.get("bleeding"),
                "fatigue": data.get("fatigue"),
                "cough": data.get("cough"),
                "chills": data.get("chills"),
                "sweating": data.get("sweating"),
                "loss_of_appetite": data.get("loss_of_appetite"),
                "comorbidity_diabetes": data.get("comorbidity_diabetes"),
                "comorbidity_bp": data.get("comorbidity_bp"),
                "comorbidity_heart": data.get("comorbidity_heart"),
                "comorbidity_kidney": data.get("comorbidity_kidney"),
                "comorbidity_liver": data.get("comorbidity_liver"),
                "comorbidity_immuno": data.get("comorbidity_immuno"),
            }
            
            fever_type, severity, confidence, probabilities = predictor.predict(prediction_data)
            predicted_diagnosis = fever_type
            predicted_severity = severity
            predicted_confidence = int(confidence * 100)  # Convert to percentage
            all_probabilities = probabilities
        except Exception as e:
            print(f"Prediction error: {e}")
            import traceback
            traceback.print_exc()
            # Use fallback values if prediction fails

    # Always use patient_name from form data (data["patient_name"])
    patient_name = data["patient_name"]
    patient_email = data.get("patient_email") or (patient_record.email if patient_record else current_user.email if current_user.role == "patient" else None)
    patient_phone = data.get("patient_phone") or (patient_record.phone if patient_record else None)
    patient_age = int(data["age"])
    patient_gender = data["gender"]
    patient_location = data.get("location") or (patient_record.location if patient_record else None)

    # Build symptoms list from checkboxes if needed
    symptoms_list = data.get("symptoms", [])
    if not symptoms_list or not isinstance(symptoms_list, list):
        symptoms_list = []
        if data.get("headache"): symptoms_list.append("Headache")
        if data.get("joint_pain"): symptoms_list.append("Joint Pain")
        if data.get("leg_pain"): symptoms_list.append("Leg Pain")
        if data.get("muscle_pain"): symptoms_list.append("Muscle Pain")
        if data.get("rash"): symptoms_list.append("Rash")
        if data.get("nausea_vomiting"): symptoms_list.append("Nausea/Vomiting")
        if data.get("vomiting"): symptoms_list.append("Vomiting")
        if data.get("bleeding"): symptoms_list.append("Bleeding")
        if data.get("fatigue"): symptoms_list.append("Fatigue")
        if data.get("cough"): symptoms_list.append("Cough")
        if data.get("chills"): symptoms_list.append("Chills")
        if data.get("sweating"): symptoms_list.append("Sweating")
        if data.get("loss_of_appetite"): symptoms_list.append("Loss of Appetite")

    diagnosis = Diagnosis(
        patient_name=patient_name,
        age=patient_age,
        gender=patient_gender,
        location=patient_location,
        duration=data.get("fever_duration_days") or data.get("duration"),
        temperature=data.get("temperature_c") or data.get("temperature"),
        symptoms=symptoms_list,
        medical_history=data.get("medical_history"),
        diagnosis=predicted_diagnosis,
        confidence=predicted_confidence,
        severity=predicted_severity,
        status=data.get("status", "pending"),
        platelet_count=data.get("platelet_count"),
        wbc_count=data.get("wbc_count"),
        rbc_count=data.get("rbc_count"),
        all_probabilities=all_probabilities,
        patient_email=patient_email,
        patient_phone=patient_phone,
        patient_user_id=current_user.id if current_user.role == "patient" else None,
    )
    db.session.add(diagnosis)
    db.session.flush()  # Get diagnosis.id

    # Update or create patient record only if user is a patient
    if current_user.role == "patient":
        if patient_record:
            # Update existing patient record
            patient_record.diagnosis_id = diagnosis.id
            if data.get("location"):
                patient_record.location = data.get("location")
        else:
            # Create new patient record
            patient = Patient(
                patient_name=patient_name,
                email=patient_email,
                phone=patient_phone,
                age=patient_age,
                gender=patient_gender,
                location=patient_location,
                diagnosis_id=diagnosis.id,
                user_id=current_user.id,
            )
            db.session.add(patient)
    
    db.session.commit()

    return jsonify(diagnosis.to_dict()), 201


@app.route("/api/extract-lab-data", methods=["POST"])
def extract_lab_data():
    """Extract lab values from uploaded PDF or image file"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    try:
        # Read file content
        file_content = file.read()
        filename = file.filename.lower()
        
        extracted_data = {}
        text_content = ""
        
        # Handle PDF files
        if filename.endswith('.pdf'):
            try:
                import pdfplumber
                import io
                pdf_file = io.BytesIO(file_content)
                with pdfplumber.open(pdf_file) as pdf:
                    text_content = ""
                    for page in pdf.pages:
                        text_content += page.extract_text() or ""
            except ImportError:
                return jsonify({"error": "PDF processing library not installed. Please install pdfplumber."}), 500
            except Exception as e:
                return jsonify({"error": f"Error reading PDF: {str(e)}"}), 500
        
        # Handle image files
        elif filename.endswith(('.jpg', '.jpeg', '.png')):
            try:
                from PIL import Image
                import pytesseract
                import io
                image = Image.open(io.BytesIO(file_content))
                text_content = pytesseract.image_to_string(image)
            except ImportError:
                return jsonify({"error": "OCR library not installed. Please install pytesseract and Pillow."}), 500
            except Exception as e:
                return jsonify({"error": f"Error processing image: {str(e)}"}), 500
        else:
            return jsonify({"error": "Unsupported file type. Please upload PDF, JPG, or PNG."}), 400
        
        # Extract lab values using regex patterns
        text_lower = text_content.lower()
        
        # Extract platelet count
        platelet_patterns = [
            r'platelet[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:k|×10[³3]|/μl|/ul)',
            r'plt[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            r'platelet\s+count[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        ]
        for pattern in platelet_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).replace(',', '')
                extracted_data['platelet_count'] = float(value)
                break
        
        # Extract WBC count
        wbc_patterns = [
            r'wbc[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:k|×10[³3]|/μl|/ul)',
            r'white\s+blood\s+cell[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            r'total\s+wbc[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        ]
        for pattern in wbc_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).replace(',', '')
                extracted_data['wbc_count'] = float(value)
                break
        
        # Extract RBC count
        rbc_patterns = [
            r'rbc[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:×10[⁶6]|million)',
            r'red\s+blood\s+cell[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            r'total\s+rbc[^:]*[:]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        ]
        for pattern in rbc_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).replace(',', '')
                extracted_data['rbc_count'] = float(value)
                break
        
        # Extract Hemoglobin
        hb_patterns = [
            r'hemoglobin[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*(?:g/dl|g/dL|gm%)',
            r'hb[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*(?:g/dl|g/dL)',
            r'hgb[^:]*[:]?\s*(\d+(?:\.\d+)?)',
        ]
        for pattern in hb_patterns:
            match = re.search(pattern, text_lower)
            if match:
                extracted_data['hemoglobin'] = float(match.group(1))
                break
        
        # Extract Hematocrit
        hct_patterns = [
            r'hematocrit[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*%',
            r'hct[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*%',
            r'pcv[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*%',
        ]
        for pattern in hct_patterns:
            match = re.search(pattern, text_lower)
            if match:
                extracted_data['hematocrit'] = float(match.group(1))
                break
        
        # Extract AST
        ast_patterns = [
            r'ast[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*(?:u/l|IU/L)',
            r'sgot[^:]*[:]?\s*(\d+(?:\.\d+)?)',
        ]
        for pattern in ast_patterns:
            match = re.search(pattern, text_lower)
            if match:
                extracted_data['ast'] = float(match.group(1))
                break
        
        # Extract ALT
        alt_patterns = [
            r'alt[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*(?:u/l|IU/L)',
            r'sgpt[^:]*[:]?\s*(\d+(?:\.\d+)?)',
        ]
        for pattern in alt_patterns:
            match = re.search(pattern, text_lower)
            if match:
                extracted_data['alt'] = float(match.group(1))
                break
        
        # Extract Temperature (if present)
        temp_patterns = [
            r'temperature[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*[°]?[fc]',
            r'temp[^:]*[:]?\s*(\d+(?:\.\d+)?)\s*[°]?[fc]',
        ]
        for pattern in temp_patterns:
            match = re.search(pattern, text_lower)
            if match:
                temp = float(match.group(1))
                if temp > 50:  # Likely Fahrenheit
                    extracted_data['temperature'] = temp
                    extracted_data['temperature_c'] = (temp - 32) * 5 / 9
                else:  # Likely Celsius
                    extracted_data['temperature_c'] = temp
                    extracted_data['temperature'] = (temp * 9 / 5) + 32
                break
        
        return jsonify({
            "success": True,
            "extracted_data": extracted_data,
            "raw_text_preview": text_content[:500] if text_content else "No text extracted"
        }), 200
        
    except Exception as e:
        print(f"Error extracting lab data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500


@app.route("/api/diagnoses/<int:diagnosis_id>", methods=["GET"])
def get_diagnosis(diagnosis_id: int):
    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        return jsonify({"error": "Diagnosis not found"}), 404
    return jsonify(diagnosis.to_dict())


@app.route("/api/diagnoses/<int:diagnosis_id>", methods=["PATCH"])
@auth_required(roles=["doctor", "clinician"])
def update_diagnosis(diagnosis_id: int):
    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        return jsonify({"error": "Diagnosis not found"}), 404

    data = request.get_json() or {}
    allowed_fields = {
        "status",
        "doctor_notes",
        "verified_by",
        "diagnosis",
        "confidence",
        "severity",
    }

    for field, value in data.items():
        if field in allowed_fields:
            setattr(diagnosis, field, value)

    if "verified_by" not in data and "status" in data:
        diagnosis.verified_by = g.current_user.email
        
        # Create notification based on status
        if data.get("status") == "rejected":
            notification = Notification(
                diagnosis_id=diagnosis_id,
                patient_name=diagnosis.patient_name,
                message=data.get("doctor_notes", f"Your diagnosis has been reviewed by {g.current_user.name}. Please consult with a healthcare provider for further evaluation."),
                notification_type="rejected",
                doctor_name=g.current_user.name,
            )
            db.session.add(notification)
        elif data.get("status") == "corrected":
            notification = Notification(
                diagnosis_id=diagnosis_id,
                patient_name=diagnosis.patient_name,
                message=data.get("doctor_notes", f"Dr. {g.current_user.name} has reviewed and updated your diagnosis. Please review the updated information."),
                notification_type="corrected",
                doctor_name=g.current_user.name,
            )
            db.session.add(notification)

    db.session.commit()
    return jsonify(diagnosis.to_dict())


@app.route("/api/diagnoses/<int:diagnosis_id>", methods=["DELETE"])
@auth_required(roles=["doctor"])
def delete_diagnosis(diagnosis_id: int):
    """Delete a diagnosis (used when doctor accepts/approves)"""
    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        return jsonify({"error": "Diagnosis not found"}), 404

    data = request.get_json() or {}
    approval_type = data.get("approval_type", "online")  # Default to online
    
    # Create notification message based on approval type
    if approval_type == "offline":
        message = f"Your diagnosis has been approved by {g.current_user.name} for offline consultation. Please visit the healthcare facility for in-person treatment. Your health records have been verified and you are ready for treatment."
    else:
        message = f"Your diagnosis has been approved by {g.current_user.name} for online consultation. Your health records have been verified and you are ready for treatment. Please follow up with your healthcare provider remotely."

    # Create notification for patient
    notification = Notification(
        diagnosis_id=diagnosis_id,
        patient_name=diagnosis.patient_name,
        message=message,
        notification_type="approved",
        approval_type=approval_type,
        doctor_name=g.current_user.name,
    )
    db.session.add(notification)

    # Mark as verified and set verified_by before deleting for potential audit trail
    diagnosis.status = "verified"
    diagnosis.verified_by = g.current_user.email
    if not diagnosis.doctor_notes:
        diagnosis.doctor_notes = "Case approved and removed from system"
    db.session.commit()
    
    # Now delete it (removes from pending list)
    db.session.delete(diagnosis)
    db.session.commit()
    return jsonify({"message": "Case approved and removed successfully"}), 200


@app.route("/api/doctors/stats", methods=["GET"])
@auth_required(roles=["doctor"])
def doctor_stats():
    """Get statistics for the logged-in doctor"""
    doctor_email = g.current_user.email
    
    # Get all diagnoses verified/rejected/corrected by this doctor
    verified_by_doctor = Diagnosis.query.filter_by(verified_by=doctor_email).all()
    
    # Get pending cases (not yet reviewed by any doctor)
    pending = Diagnosis.query.filter_by(status="pending").count()
    
    # Get verified today (approved cases are deleted, so count corrected as verified today)
    today = datetime.utcnow().date()
    verified_today = sum(
        1 for d in verified_by_doctor 
        if d.updated_at and d.updated_at.date() == today and (d.status == "corrected" or d.status == "verified")
    )
    
    # Get critical cases in pending
    critical = Diagnosis.query.filter_by(status="pending", severity="CV").count()
    
    # Get rejected cases by this doctor
    rejected = Diagnosis.query.filter_by(verified_by=doctor_email, status="rejected").count()
    
    # Calculate accuracy (corrected + verified vs rejected)
    # Note: Approved cases are deleted, so we count corrected as successful reviews
    corrected_count = sum(1 for d in verified_by_doctor if d.status == "corrected")
    verified_count = sum(1 for d in verified_by_doctor if d.status == "verified")
    total_reviewed = corrected_count + verified_count + rejected
    accuracy = round(((corrected_count + verified_count) / total_reviewed * 100) if total_reviewed > 0 else 0)
    
    return jsonify({
        "pendingReviews": pending,
        "verifiedToday": verified_today,
        "criticalCases": critical,
        "accuracyRate": accuracy,
        "totalVerified": len(verified_by_doctor),
        "rejected": rejected,
    })


@app.route("/api/messages/<int:diagnosis_id>", methods=["GET"])
@auth_required(roles=["doctor", "clinician"])
def list_messages(diagnosis_id: int):
    messages = (
        CollaborationMessage.query.filter_by(diagnosis_id=diagnosis_id)
        .order_by(CollaborationMessage.created_at.asc())
        .all()
    )
    return jsonify([m.to_dict() for m in messages])


@app.route("/api/messages", methods=["POST"])
@auth_required(roles=["doctor", "clinician"])
def create_message():
    data = request.get_json() or {}
    diagnosis_id = data.get("diagnosis_id")
    message_text = (data.get("message") or "").strip()

    if not diagnosis_id or not message_text:
        return jsonify({"error": "diagnosis_id and message are required"}), 400

    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        return jsonify({"error": "Diagnosis not found"}), 404

    message = CollaborationMessage(
        diagnosis_id=diagnosis_id,
        sender_role=g.current_user.role,
        sender_name=g.current_user.name,
        message=message_text,
    )

    db.session.add(message)
    db.session.commit()
    return jsonify(message.to_dict()), 201


@app.route("/api/followups", methods=["POST"])
@auth_required(roles=["doctor", "clinician"])
def schedule_follow_up():
    data = request.get_json() or {}
    diagnosis_id = data.get("diagnosis_id")
    hours = int(data.get("hours_ahead", 8))
    notes = data.get("notes") or "Automated follow-up for severe case"

    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        return jsonify({"error": "Diagnosis not found"}), 404

    follow_up = FollowUp(
        diagnosis_id=diagnosis.id,
        patient_name=diagnosis.patient_name,
        scheduled_date=datetime.utcnow() + timedelta(hours=hours),
        notes=notes,
    )

    db.session.add(follow_up)
    db.session.commit()
    return jsonify(follow_up.to_dict()), 201


@app.route("/api/prescriptions", methods=["GET"])
@auth_required(roles=["chemist", "pharmacist"])
def list_prescriptions():
    status = request.args.get("status")
    query = Prescription.query
    if status:
        query = query.filter_by(status=status)
    prescriptions = query.order_by(Prescription.created_at.desc()).all()
    
    # Include prescription items if available
    result = []
    for p in prescriptions:
        p_dict = p.to_dict()
        # Get prescription items
        items = PrescriptionItem.query.filter_by(prescription_id=p.id).all()
        p_dict["items"] = [item.to_dict() for item in items]
        result.append(p_dict)
    
    return jsonify(result)


@app.route("/api/prescriptions/<int:prescription_id>", methods=["PATCH"])
@auth_required(roles=["chemist", "pharmacist"])
def update_prescription(prescription_id: int):
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404

    data = request.get_json() or {}
    status = data.get("status")
    if status not in {"dispensed", "partial", "pending"}:
        return jsonify({"error": "Invalid status"}), 400

    prescription.status = status
    prescription.dispensed_at = datetime.utcnow()
    prescription.dispensed_by = g.current_user.email
    db.session.commit()

    return jsonify(prescription.to_dict())


@app.route("/api/prescriptions/<int:prescription_id>", methods=["GET"])
@auth_required(roles=["chemist", "pharmacist", "doctor"])
def get_prescription(prescription_id: int):
    """Get prescription details with items"""
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404
    
    result = prescription.to_dict()
    # Get prescription items
    items = PrescriptionItem.query.filter_by(prescription_id=prescription.id).all()
    result["items"] = [item.to_dict() for item in items]
    
    return jsonify(result)


@app.route("/api/inventory", methods=["GET"])
@auth_required(roles=["chemist", "pharmacist"])
def list_inventory():
    """Get inventory - supports both old InventoryItem and new PharmacyInventory"""
    user = g.current_user
    
    # Try to get pharmacist's pharmacy
    pharmacist = Pharmacist.query.filter_by(user_id=user.id).first()
    if pharmacist and pharmacist.pharmacy_id:
        # Use new PharmacyInventory system
        items = PharmacyInventory.query.filter_by(pharmacy_id=pharmacist.pharmacy_id).all()
        result = []
        for item in items:
            item_dict = item.to_dict()
            # Get product details
            product = Product.query.get(item.product_id)
            if product:
                item_dict["product"] = product.to_dict()
            result.append(item_dict)
        return jsonify(result)
    else:
        # Fallback to old InventoryItem system
        items = InventoryItem.query.order_by(InventoryItem.drug_name.asc()).all()
        return jsonify([item.to_dict() for item in items])


@app.route("/api/inventory", methods=["POST"])
@auth_required(roles=["chemist"])
def add_inventory_item():
    data = request.get_json() or {}
    required = ["drug_name", "quantity", "unit"]
    missing = [field for field in required if not data.get(field)]
    if missing:
        return (
            jsonify({"error": f"Missing required fields: {', '.join(missing)}"}),
            400,
        )

    item = InventoryItem(
        drug_name=data["drug_name"],
        generic_name=data.get("generic_name"),
        batch_number=data.get("batch_number"),
        quantity=int(data.get("quantity", 0)),
        unit=data.get("unit", "tablets"),
        price=float(data.get("price", 0)),
        expiry_date=data.get("expiry_date"),
        manufacturer=data.get("manufacturer"),
        reorder_level=int(data.get("reorder_level", 10)),
    )
    db.session.add(item)
    db.session.commit()

    return jsonify(item.to_dict()), 201


# ============================================
# PHARMACIST SPECIFIC APIs
# ============================================

@app.route("/api/pharmacist/pharmacy", methods=["GET"])
@auth_required(roles=["pharmacist", "chemist"])
def get_pharmacist_pharmacy():
    """Get pharmacist's pharmacy information"""
    user = g.current_user
    pharmacist = Pharmacist.query.filter_by(user_id=user.id).first()
    if not pharmacist:
        return jsonify({"error": "Pharmacist record not found"}), 404
    
    result = pharmacist.to_dict()
    if pharmacist.pharmacy_id:
        pharmacy = Pharmacy.query.get(pharmacist.pharmacy_id)
        if pharmacy:
            result["pharmacy"] = pharmacy.to_dict()
    
    return jsonify(result)


@app.route("/api/pharmacies/nearby", methods=["GET"])
def get_nearby_pharmacies():
    """Get nearby pharmacies based on location"""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius_km = request.args.get("radius", default=10, type=float)
    
    if not lat or not lng:
        return jsonify({"error": "Latitude and longitude are required"}), 400
    
    # Get all active pharmacies
    pharmacies = Pharmacy.query.filter_by(is_active=True).all()
    
    # Calculate distance and filter
    nearby = []
    for pharmacy in pharmacies:
        if pharmacy.latitude and pharmacy.longitude:
            # Haversine formula
            R = 6371  # Earth radius in km
            lat1, lon1 = radians(lat), radians(lng)
            lat2, lon2 = radians(float(pharmacy.latitude)), radians(float(pharmacy.longitude))
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            if distance <= radius_km:
                pharm_dict = pharmacy.to_dict()
                pharm_dict["distance_km"] = round(distance, 2)
                nearby.append(pharm_dict)
    
    # Sort by distance
    nearby.sort(key=lambda x: x["distance_km"])
    return jsonify(nearby[:20])  # Return top 20 nearest


@app.route("/api/products", methods=["GET"])
def list_products():
    """Get list of all products"""
    search = request.args.get("search", "")
    manufacturer_id = request.args.get("manufacturer_id", type=int)
    
    query = Product.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            (Product.product_name.ilike(f"%{search}%")) |
            (Product.generic_name.ilike(f"%{search}%"))
        )
    if manufacturer_id:
        query = query.filter_by(manufacturer_id=manufacturer_id)
    
    products = query.order_by(Product.product_name.asc()).limit(100).all()
    result = []
    for product in products:
        p_dict = product.to_dict()
        manufacturer = Manufacturer.query.get(product.manufacturer_id)
        if manufacturer:
            p_dict["manufacturer"] = manufacturer.to_dict()
        result.append(p_dict)
    
    return jsonify(result)


@app.route("/api/dispense", methods=["POST"])
@auth_required(roles=["pharmacist", "chemist"])
def dispense_medication():
    """Dispense medication from prescription"""
    data = request.get_json() or {}
    prescription_id = data.get("prescription_id")
    items = data.get("items", [])  # Array of {product_id, quantity, batch_number, lot_number, expiry_date}
    
    if not prescription_id or not items:
        return jsonify({"error": "Prescription ID and items are required"}), 400
    
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404
    
    user = g.current_user
    pharmacist = Pharmacist.query.filter_by(user_id=user.id).first()
    if not pharmacist or not pharmacist.pharmacy_id:
        return jsonify({"error": "Pharmacist pharmacy not found"}), 404
    
    dispensations = []
    for item_data in items:
        product_id = item_data.get("product_id")
        quantity = item_data.get("quantity")
        batch_number = item_data.get("batch_number")
        lot_number = item_data.get("lot_number")
        expiry_date = item_data.get("expiry_date")
        
        if not product_id or not quantity:
            continue
        
        # Check inventory
        inventory = PharmacyInventory.query.filter_by(
            pharmacy_id=pharmacist.pharmacy_id,
            product_id=product_id,
            batch_number=batch_number
        ).first()
        
        if not inventory or inventory.quantity < quantity:
            return jsonify({"error": f"Insufficient inventory for product {product_id}"}), 400
        
        # Get product price
        price = inventory.price if inventory.price else 0.0
        
        # Create dispensation record
        expiry = None
        if expiry_date:
            try:
                expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            except:
                pass
        
        dispensation = Dispensation(
            prescription_id=prescription_id,
            pharmacist_id=user.id,
            pharmacy_id=pharmacist.pharmacy_id,
            product_id=product_id,
            batch_number=batch_number,
            lot_number=lot_number,
            expiry_date=expiry,
            quantity_dispensed=quantity,
            price=price,
            status="dispensed",
            dispensed_at=datetime.utcnow()
        )
        db.session.add(dispensation)
        dispensations.append(dispensation)
        
        # Decrement inventory
        inventory.quantity -= quantity
        inventory.updated_at = datetime.utcnow()
        
        # Create demand signal
        pharmacy = Pharmacy.query.get(pharmacist.pharmacy_id)
        demand_signal = DemandSignal(
            product_id=product_id,
            region=pharmacy.city if pharmacy else None,
            demand_quantity=quantity,
            signal_date=datetime.utcnow().date(),
            signal_type="dispensation",
            source="pharmacy"
        )
        db.session.add(demand_signal)
    
    # Update prescription status
    prescription.status = "dispensed"
    prescription.dispensed_at = datetime.utcnow()
    prescription.dispensed_by = user.email
    
    db.session.commit()
    
    return jsonify({
        "message": "Medication dispensed successfully",
        "dispensations": [d.to_dict() for d in dispensations]
    }), 201


@app.route("/api/pharmacist/alerts", methods=["GET"])
@auth_required(roles=["pharmacist", "chemist"])
def get_pharmacist_alerts():
    """Get stock alerts for pharmacist's pharmacy"""
    user = g.current_user
    pharmacist = Pharmacist.query.filter_by(user_id=user.id).first()
    if not pharmacist or not pharmacist.pharmacy_id:
        return jsonify({"error": "Pharmacist pharmacy not found"}), 404
    
    # Get low stock items
    inventory = PharmacyInventory.query.filter_by(pharmacy_id=pharmacist.pharmacy_id).all()
    low_stock = [item for item in inventory if item.quantity <= item.min_stock_level]
    
    # Get stockout events
    stockouts = StockoutEvent.query.filter_by(
        pharmacy_id=pharmacist.pharmacy_id,
        status="active"
    ).all()
    
    # Get supply chain alerts
    alerts = SupplyChainAlert.query.filter_by(
        status="active"
    ).all()
    
    return jsonify({
        "low_stock": [item.to_dict() for item in low_stock],
        "stockouts": [s.to_dict() for s in stockouts],
        "alerts": [a.to_dict() for a in alerts]
    })


@app.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    diagnoses = Diagnosis.query.all()
    total = len(diagnoses)
    pending = sum(1 for d in diagnoses if d.status == "pending")
    verified = sum(1 for d in diagnoses if d.status == "verified")

    disease_count: Dict[str, int] = {}
    severity_count: Dict[str, int] = {}
    region_temp: Dict[str, Dict[str, float]] = {}

    for d in diagnoses:
        disease = d.diagnosis or "Unknown"
        disease_count[disease] = disease_count.get(disease, 0) + 1

        severity = d.severity or "unknown"
        severity_count[severity] = severity_count.get(severity, 0) + 1

        if d.location and d.temperature:
            try:
                temp = float(d.temperature)
            except ValueError:
                continue

            info = region_temp.setdefault(d.location, {"sum": 0.0, "count": 0})
            info["sum"] += temp
            info["count"] += 1

    disease_distribution = [
        {"name": name, "count": count} for name, count in disease_count.items()
    ]
    severity_distribution = [
        {"name": name, "value": count} for name, count in severity_count.items()
    ]
    temperature_by_region = [
        {"region": region, "avgTemp": round(data["sum"] / data["count"], 1)}
        for region, data in region_temp.items()
        if data["count"]
    ]

    return jsonify(
        {
            "stats": {
                "totalCases": total,
                "pendingCases": pending,
                "verifiedCases": verified,
                "avgResponseTime": "2.5 hrs",
            },
            "diseaseDistribution": disease_distribution,
            "severityDistribution": severity_distribution,
            "temperatureByRegion": temperature_by_region,
        }
    )


@app.route("/api/notifications/<string:patient_name>", methods=["GET"])
def get_patient_notifications(patient_name: str):
    """Get notifications for a patient"""
    notifications = (
        Notification.query.filter_by(patient_name=patient_name)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return jsonify([n.to_dict() for n in notifications])


@app.route("/api/notifications/<int:notification_id>/read", methods=["PATCH"])
def mark_notification_read(notification_id: int):
    """Mark a notification as read"""
    notification = db.session.get(Notification, notification_id)
    if not notification:
        return jsonify({"error": "Notification not found"}), 404
    
    notification.read = True
    db.session.commit()
    return jsonify(notification.to_dict())


@app.route("/api/notifications/<string:patient_name>/old", methods=["DELETE"])
def delete_old_notifications(patient_name: str):
    """Delete old (read) notifications for a patient"""
    try:
        # Delete all read notifications for the patient
        deleted_count = Notification.query.filter_by(
            patient_name=patient_name,
            read=True
        ).delete()
        db.session.commit()
        return jsonify({"message": f"Deleted {deleted_count} old notifications", "deleted": deleted_count}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/trends", methods=["GET"])
def analytics_trends():
    """Get weekly trends data for diseases"""
    from datetime import datetime, timedelta
    
    diagnoses = Diagnosis.query.all()
    
    # Get last 4 weeks of data
    now = datetime.utcnow()
    weeks_data = []
    
    for week_num in range(4):
        week_start = now - timedelta(weeks=4-week_num, days=now.weekday())
        week_end = week_start + timedelta(days=6)
        
        week_diagnoses = [
            d for d in diagnoses 
            if d.created_at and week_start <= d.created_at <= week_end
        ]
        
        week_counts = {
            "dengue": 0,
            "typhoid": 0,
            "viral": 0,
            "malaria": 0,
            "chikungunya": 0
        }
        
        for d in week_diagnoses:
            disease = (d.diagnosis or "").lower()
            if "dengue" in disease:
                week_counts["dengue"] += 1
            elif "typhoid" in disease:
                week_counts["typhoid"] += 1
            elif "malaria" in disease:
                week_counts["malaria"] += 1
            elif "chikungunya" in disease:
                week_counts["chikungunya"] += 1
            else:
                week_counts["viral"] += 1
        
        weeks_data.append({
            "week": f"Week {week_num + 1}",
            **week_counts
        })
    
    # Regional data
    regional_data = {}
    for d in diagnoses:
        if d.location:
            region = d.location
            if region not in regional_data:
                regional_data[region] = {
                    "dengue": 0,
                    "critical": 0
                }
            
            disease = (d.diagnosis or "").lower()
            if "dengue" in disease:
                regional_data[region]["dengue"] += 1
            
            if d.severity == "CV":
                regional_data[region]["critical"] += 1
    
    regional_list = [
        {
            "region": region,
            "dengue": data["dengue"],
            "trend": "up" if data["dengue"] > 10 else "stable",
            "critical": data["critical"]
        }
        for region, data in regional_data.items()
    ]
    
    return jsonify({
        "weeklyData": weeks_data,
        "regionalData": regional_list
    })


@app.route("/api/analytics/disease-increases", methods=["GET"])
def get_disease_increases():
    """Get diseases that are increasing with trend analysis and medicine recommendations"""
    from datetime import datetime, timedelta
    
    diagnoses = Diagnosis.query.all()
    now = datetime.utcnow()
    
    # Get current week (last 7 days)
    current_week_start = now - timedelta(days=7)
    current_week_diagnoses = [
        d for d in diagnoses 
        if d.created_at and d.created_at >= current_week_start
    ]
    
    # Get previous week (7-14 days ago)
    previous_week_start = now - timedelta(days=14)
    previous_week_end = now - timedelta(days=7)
    previous_week_diagnoses = [
        d for d in diagnoses 
        if d.created_at and previous_week_start <= d.created_at < previous_week_end
    ]
    
    # Count diseases for both weeks
    def count_diseases(diagnosis_list):
        counts = {
            "Dengue": 0,
            "Typhoid": 0,
            "Viral Fever": 0,
            "Malaria": 0,
            "Chikungunya": 0
        }
        for d in diagnosis_list:
            disease = (d.diagnosis or "").lower()
            if "dengue" in disease:
                counts["Dengue"] += 1
            elif "typhoid" in disease:
                counts["Typhoid"] += 1
            elif "malaria" in disease:
                counts["Malaria"] += 1
            elif "chikungunya" in disease:
                counts["Chikungunya"] += 1
            else:
                counts["Viral Fever"] += 1
        return counts
    
    current_counts = count_diseases(current_week_diagnoses)
    previous_counts = count_diseases(previous_week_diagnoses)
    
    # Medicine recommendations mapping
    medicine_recommendations = {
        "Dengue": [
            "Paracetamol 500mg",
            "Paracetamol 650mg", 
            "ORS Powder",
            "Dextrose 5%",
            "Platelet Concentrate",
            "IV Fluids"
        ],
        "Typhoid": [
            "Azithromycin 500mg",
            "Ciprofloxacin 500mg",
            "Ceftriaxone Injection",
            "Paracetamol 500mg",
            "ORS Powder"
        ],
        "Malaria": [
            "Chloroquine 250mg",
            "Artemether-Lumefantrine",
            "Quinine",
            "Paracetamol 500mg",
            "Doxycycline"
        ],
        "Viral Fever": [
            "Paracetamol 500mg",
            "Paracetamol Syrup",
            "Ibuprofen 400mg",
            "Vitamin C 500mg",
            "ORS Powder"
        ],
        "Chikungunya": [
            "Paracetamol 500mg",
            "Diclofenac 50mg",
            "Ibuprofen 400mg",
            "Naproxen",
            "Vitamin C 500mg"
        ]
    }
    
    # Calculate increases
    increases = []
    for disease in ["Dengue", "Typhoid", "Viral Fever", "Malaria", "Chikungunya"]:
        current = current_counts.get(disease, 0)
        previous = previous_counts.get(disease, 0)
        
        if current > previous and current > 0:
            increase_percent = ((current - previous) / previous * 100) if previous > 0 else 100
            increases.append({
                "disease": disease,
                "current_week": current,
                "previous_week": previous,
                "increase": current - previous,
                "increase_percent": round(increase_percent, 1),
                "medicines": medicine_recommendations.get(disease, []),
                "tools": ["Thermometer", "Blood Pressure Monitor", "Pulse Oximeter"] if disease in ["Dengue", "Malaria"] else ["Thermometer"]
            })
    
    # Sort by increase percentage
    increases.sort(key=lambda x: x["increase_percent"], reverse=True)
    
    return jsonify({
        "increasing_diseases": increases,
        "current_week_total": sum(current_counts.values()),
        "previous_week_total": sum(previous_counts.values())
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


# app/utils.py
from flask_login import current_user
from app import db
from app.models import ActivityLog

def log_activity(action, details=""):
    """ฟังก์ชันสำหรับบันทึกกิจกรรมของผู้ใช้"""
    if current_user.is_authenticated:
        log = ActivityLog(
            user_id=current_user.id,
            action=action,
            details=details
        )
        db.session.add(log)
        db.session.commit()
# path: backup.py
import json
import datetime
from app import db
from app.models import User, Role, LearningArea, GradeLevel, Course, CourseSection, LearningUnit # Import ทุก Model ที่ต้องการ Backup

def backup_data():
    """
    Queries data from the database and saves it to a timestamped JSON file.
    """
    print("--- Starting database backup... ---")
    
    data_to_backup = {
        'roles': [role.name for role in Role.query.all()],
        'users': [
            {
                'username': u.username,
                'full_name': u.full_name,
                'roles': [r.name for r in u.roles]
            } for u in User.query.all()
        ],
        'learning_areas': [area.name for area in LearningArea.query.all()],
        'grade_levels': [grade.name for grade in GradeLevel.query.all()],
        # คุณสามารถเพิ่ม Model อื่นๆ ที่ต้องการ Backup ได้ในลักษณะเดียวกัน
    }

    # สร้างชื่อไฟล์พร้อมวันเวลาปัจจุบัน
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f'backup_{timestamp}.json'

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data_to_backup, f, ensure_ascii=False, indent=4)
        print(f"SUCCESS: Database backup created successfully at '{filename}'")
    except Exception as e:
        print(f"ERROR: Failed to create backup. Reason: {e}")
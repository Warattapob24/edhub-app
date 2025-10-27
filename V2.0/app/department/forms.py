# path: app/department/forms.py

from flask_wtf import FlaskForm
from wtforms import SubmitField
from wtforms_sqlalchemy.fields import QuerySelectMultipleField
from app.models import User, Role

def get_teachers_in_department(department_id):
    """Helper function to get teachers for a specific department."""
    return User.query.filter_by(learning_area_id=department_id).order_by(User.full_name).all()

class MultiTeacherAssignmentForm(FlaskForm):
    teachers = QuerySelectMultipleField(
        'เลือกครูผู้สอน (เลือกได้หลายคน)',
        get_label='full_name',
        allow_blank=True
    )
    submit = SubmitField('บันทึกการมอบหมาย')

    def __init__(self, department_id, *args, **kwargs):
        super(MultiTeacherAssignmentForm, self).__init__(*args, **kwargs)
        # ตั้งค่า Query แบบไดนามิกตามกลุ่มสาระฯ ของหัวหน้าภาค
        self.teachers.query = User.query.filter_by(learning_area_id=department_id).order_by(User.full_name)
        
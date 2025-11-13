# app/auth/forms.py
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, ValidationError
from wtforms.validators import DataRequired, EqualTo, Length, Email, ValidationError
from wtforms_sqlalchemy.fields import QuerySelectMultipleField
from app.models import Classroom, SubjectGroup, User

class LoginForm(FlaskForm):
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
    remember_me = BooleanField('จดจำฉันไว้ในระบบ')
    submit = SubmitField('เข้าสู่ระบบ')

# Helper functions for InitialSetupForm
def get_subject_groups():
    return SubjectGroup.query.order_by(SubjectGroup.name).all()

def get_classrooms_for_advisors():
    # This might need refinement later to filter by current academic year
    return Classroom.query.order_by(Classroom.name).all()

class InitialSetupForm(FlaskForm):
    # Part 1: Login credentials
    username = StringField('ชื่อผู้ใช้ (Username) ใหม่', validators=[DataRequired(), Length(min=4, max=64)])
    password = PasswordField('รหัสผ่านใหม่', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('ยืนยันรหัสผ่านใหม่', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])

    # Part 2: Personal and assignment info
    job_title = StringField('ตำแหน่ง (เช่น ครูชำนาญการ)', validators=[DataRequired()])
    email = StringField('อีเมล', validators=[DataRequired(), Email()])
    
    # Many-to-Many fields
    member_of_groups = QuerySelectMultipleField('สังกัดกลุ่มสาระการเรียนรู้', 
        query_factory=get_subject_groups, get_label='name')
        
    advised_classrooms = QuerySelectMultipleField('ห้องเรียนในที่ปรึกษา (ถ้ามี)',
        query_factory=get_classrooms_for_advisors, get_label='name')

    submit = SubmitField('บันทึกและเริ่มต้นใช้งาน')

def validate_username(self, username):
        # ตรวจสอบว่า username ไม่ได้เปลี่ยน
        if username.data == current_user.username:
            return  # ถ้าเป็นชื่อเดิมของตัวเอง ไม่ต้องเช็ค

        # ถ้าเปลี่ยนชื่อใหม่ ค่อยเช็คว่าซ้ำหรือไม่
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('ชื่อผู้ใช้นี้มีผู้ใช้งานแล้ว')

def validate_email(self, email):
        # ตรวจสอบว่า email ไม่ได้เปลี่ยน
        if email.data == current_user.email:
            return  # ถ้าเป็นอีเมลเดิมของตัวเอง ไม่ต้องเช็ค

        # ถ้าเปลี่ยนอีเมลใหม่ ค่อยเช็คว่าซ้ำหรือไม่
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email นี้มีผู้ใช้งานแล้ว')
        
class ChangePasswordForm(FlaskForm):
    password = PasswordField('รหัสผ่านใหม่', validators=[DataRequired()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่านใหม่', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    submit = SubmitField('บันทึกรหัสผ่านใหม่')
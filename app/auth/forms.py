# app/auth/forms.py
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
        # Checks if the username exists and does not belong to the current user
        user = User.query.filter(User.username == username.data, User.id != self.user_id).first()
        if user:
            raise ValidationError('ชื่อผู้ใช้นี้มีคนใช้แล้ว กรุณาเลือกชื่ออื่น')

    def validate_email(self, email):
        # Checks if the email exists and does not belong to the current user
        user = User.query.filter(User.email == email.data, User.id != self.user_id).first()
        if user:
             raise ValidationError('อีเมลนี้ถูกใช้ในระบบแล้ว กรุณาใช้อีเมลอื่น')
        
class ChangePasswordForm(FlaskForm):
    password = PasswordField('รหัสผ่านใหม่', validators=[DataRequired()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่านใหม่', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    submit = SubmitField('บันทึกรหัสผ่านใหม่')
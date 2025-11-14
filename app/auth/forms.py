# app/auth/forms.py
from typing import Optional
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, ValidationError
from wtforms.validators import DataRequired, EqualTo, Length, Email, ValidationError, Optional
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

    first_name = StringField('ชื่อจริง', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('นามสกุล', validators=[DataRequired(), Length(max=64)])
    
    # Part 2: Personal and assignment info
    job_title = StringField('ตำแหน่ง (เช่น ครูชำนาญการ)', validators=[DataRequired()])
    email = StringField('อีเมล', validators=[DataRequired(), Email()])
    
    # Many-to-Many fields
    member_of_groups = QuerySelectMultipleField('สังกัดกลุ่มสาระการเรียนรู้', 
        query_factory=get_subject_groups, get_label='name')
        
    advised_classrooms = QuerySelectMultipleField('ห้องเรียนในที่ปรึกษา (ถ้ามี)',
        query_factory=get_classrooms_for_advisors, get_label='name')

    submit = SubmitField('บันทึกและเริ่มต้นใช้งาน')

    def __init__(self, *args, **kwargs):
        # ดึง custom kwarg ของเราออกมาก่อน
        password_required = kwargs.pop('password_required', False)
        super(InitialSetupForm, self).__init__(*args, **kwargs)

        # ตรวจสอบว่าจำเป็นต้องใช้รหัสผ่านหรือไม่
        if password_required:
            # ถ้าจำเป็น (เช่น Admin สร้างให้) ให้เพิ่ม DataRequired() กลับเข้าไป
            self.username.validators.insert(0, DataRequired())
            self.password.validators.insert(0, DataRequired())
            self.password2.validators.insert(0, DataRequired())
        else:
            # ถ้าไม่จำเป็น (เช่น Google Login)
            # Username ยังต้องกรอก (เพราะอาจจะ pre-filled มาจาก email)
            self.username.validators.insert(0, DataRequired())
            # แต่ Password เป็น Optional (ไม่ต้องกรอกก็ได้)
            self.password.validators.insert(0, Optional())
            self.password2.validators.insert(0, Optional())

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

# --- [NEW] สร้างคลาสฟอร์มใหม่สำหรับ Edit Profile ---
class EditProfileForm(FlaskForm):
    # ฟอร์มนี้จะคล้ายกับ InitialSetupForm แต่รหัสผ่านเป็น "Optional"
    
    # ส่วนที่ 1: ข้อมูลส่วนตัว (บังคับกรอก)
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired(), Length(min=4, max=64)])
    first_name = StringField('ชื่อจริง', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('นามสกุล', validators=[DataRequired(), Length(max=64)])
    job_title = StringField('ตำแหน่ง (เช่น ครูชำนาญการ)', validators=[DataRequired()])
    email = StringField('อีเมล', validators=[DataRequired(), Email()])

    # ส่วนที่ 2: รหัสผ่าน (ไม่บังคับ)
    password = PasswordField('รหัสผ่านใหม่ (กรอกเฉพาะเมื่อต้องการเปลี่ยน)', 
                             validators=[Optional(), Length(min=6)])
    password2 = PasswordField('ยืนยันรหัสผ่านใหม่', 
                              validators=[Optional(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])

    # ส่วนที่ 3: การมอบหมาย (เหมือนเดิม)
    member_of_groups = QuerySelectMultipleField('สังกัดกลุ่มสาระการเรียนรู้', 
        query_factory=get_subject_groups, get_label='name')
        
    advised_classrooms = QuerySelectMultipleField('ห้องเรียนในที่ปรึกษา (ถ้ามี)',
        query_factory=get_classrooms_for_advisors, get_label='name')

    submit = SubmitField('บันทึกการเปลี่ยนแปลง')

    # (ใช้ Validate Logic เดียวกับ InitialSetupForm)
    def validate_username(self, username):
        if username.data == current_user.username:
            return
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('ชื่อผู้ใช้นี้มีผู้ใช้งานแล้ว')
        
    def validate_email(self, email):
        if email.data == current_user.email:
            return
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email นี้มีผู้ใช้งานแล้ว')
# --- [END NEW] ---
        
class ChangePasswordForm(FlaskForm):
    # (คลาสนี้เหมือนเดิม ไม่มีการแก้ไข)
    password = PasswordField('รหัสผ่านใหม่', validators=[DataRequired()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่านใหม่', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    submit = SubmitField('บันทึกรหัสผ่านใหม่')
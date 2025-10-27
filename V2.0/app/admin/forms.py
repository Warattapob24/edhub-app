# path: app/admin/forms.py

from flask_wtf import FlaskForm
from wtforms import (StringField, SubmitField, IntegerField, FloatField, 
                     SelectField, TextAreaField, PasswordField)
from wtforms.validators import DataRequired, NumberRange, ValidationError, Length, Email, EqualTo, Optional
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField
from app.models import LearningArea, GradeLevel, Course, User, Role
from wtforms.widgets import ListWidget, CheckboxInput
from app.patched_form_fields import PatchedQuerySelectMultipleField # Import field ที่แก้ไขแล้ว


def get_learning_areas():
    """ดึงข้อมูลกลุ่มสาระฯ ทั้งหมดสำหรับ Dropdown"""
    return LearningArea.query.order_by(LearningArea.name).all()

def get_grade_levels():
    """ดึงข้อมูลระดับชั้นทั้งหมดสำหรับ Dropdown"""
    return GradeLevel.query.order_by('id').all()

def get_roles():
    """A helper function to query all roles for the form."""
    return Role.query.order_by('id').all()

def get_teachers():
    teacher_role = Role.query.filter_by(name='Teacher').first()
    if teacher_role:
        return User.query.filter(User.roles.contains(teacher_role)).order_by(User.full_name)
    return []

class AddUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    full_name = StringField('ชื่อ-นามสกุล', validators=[DataRequired()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired(), EqualTo('password')])
    roles = PatchedQuerySelectMultipleField('บทบาท', query_factory=lambda: Role.query.all(), get_label='name', validators=[DataRequired()])
    learning_area = QuerySelectField('กลุ่มสาระฯ (ถ้ามี)', query_factory=get_learning_areas, get_label='name', allow_blank=True, blank_text='-- ไม่มี --')
    submit = SubmitField('เพิ่มผู้ใช้')

class EditUserForm(FlaskForm):
    username = StringField('Username', render_kw={'readonly': True})
    full_name = StringField('ชื่อ-นามสกุล', validators=[DataRequired()])
    password = PasswordField('รหัสผ่านใหม่ (ถ้าต้องการเปลี่ยน)', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('ยืนยันรหัสผ่านใหม่', validators=[EqualTo('password')])
    roles = PatchedQuerySelectMultipleField('บทบาท', query_factory=lambda: Role.query.all(), get_label='name', validators=[DataRequired()])
    learning_area = QuerySelectField('กลุ่มสาระฯ (ถ้ามี)', query_factory=get_learning_areas, get_label='name', allow_blank=True, blank_text='-- ไม่มี --')
    submit = SubmitField('บันทึกการเปลี่ยนแปลง')

class UserForm(FlaskForm):
    """
    ฟอร์มสำหรับสร้างและแก้ไขผู้ใช้ (Admin, Teacher, etc.)
    """
    full_name = StringField('ชื่อ-นามสกุล', validators=[DataRequired()])
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired()])
    
    password = PasswordField('รหัสผ่านใหม่', validators=[Optional()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่านใหม่', 
        validators=[Optional(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')]
    )

    roles = QuerySelectMultipleField(
        'บทบาท',
        query_factory=get_roles,
        get_label='name',
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )

    learning_area = QuerySelectField(
        'กลุ่มสาระที่สังกัด',
        query_factory=get_learning_areas,
        get_label='name',
        allow_blank=True,
        blank_text='-- ไม่สังกัดกลุ่มสาระ --'
    )

    submit = SubmitField('บันทึกข้อมูล')

    def __init__(self, original_username=None, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('มีชื่อผู้ใช้นี้ในระบบแล้ว กรุณาใช้ชื่ออื่น')

class LearningAreaForm(FlaskForm):
    name = StringField('ชื่อกลุ่มสาระการเรียนรู้', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class CourseForm(FlaskForm):
    course_code = StringField('รหัสวิชา', validators=[DataRequired()])
    name_thai = StringField('ชื่อวิชา (ภาษาไทย)', validators=[DataRequired()])
    credits = FloatField('หน่วยกิต', validators=[DataRequired(), NumberRange(min=0, max=10)])
    semester = SelectField('ภาคเรียนที่เปิดสอน', 
                           choices=[('1', 'ภาคเรียนที่ 1'), ('2', 'ภาคเรียนที่ 2'), ('0', 'สอนทั้งปีการศึกษา')], 
                           validators=[DataRequired()], coerce=int)
    learning_area = QuerySelectField('กลุ่มสาระการเรียนรู้', 
                                     query_factory=get_learning_areas, 
                                     get_label='name', 
                                     allow_blank=False,
                                     validators=[DataRequired()])
    grade_level = QuerySelectField('ระดับชั้น', 
                                   query_factory=get_grade_levels, 
                                   get_label='name', 
                                   allow_blank=False,
                                   validators=[DataRequired()])
    submit = SubmitField('บันทึกรายวิชา')

    def __init__(self, original_course_code=None, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        self.original_course_code = original_course_code

    def validate_course_code(self, course_code):
        if course_code.data != self.original_course_code:
            course = Course.query.filter_by(course_code=course_code.data).first()
            if course:
                raise ValidationError('รหัสวิชานี้มีอยู่แล้วในระบบ กรุณาใช้รหัสอื่น')

class AssessmentDimensionForm(FlaskForm):
    name = StringField('ชื่อเต็มของมิติ', validators=[DataRequired()])
    code = StringField('รหัสย่อ (เช่น K, P, S)', validators=[DataRequired()])
    description = TextAreaField('คำอธิบาย')
    submit = SubmitField('บันทึก')

class CompetencyForm(FlaskForm):
    name = StringField('ชื่อสมรรถนะ', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class DesirableCharacteristicForm(FlaskForm):
    name = StringField('ชื่อคุณลักษณะอันพึงประสงค์', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class AssessmentMethodForm(FlaskForm):
    name = StringField('ชื่อวิธีการวัดผล', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

# --- NEW CLASSROOM FORM ---
class ClassroomForm(FlaskForm):
    name = StringField('ชื่อห้องเรียน', validators=[DataRequired()])
    advisors = PatchedQuerySelectMultipleField(
        'ครูที่ปรึกษา',
        query_factory=get_teachers,
        get_label='full_name',
        allow_blank=True
    )
    submit = SubmitField('บันทึก')

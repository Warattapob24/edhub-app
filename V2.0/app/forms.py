from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectMultipleField, widgets, IntegerField, FloatField, BooleanField, TextAreaField
# แก้ไข: เพิ่ม Optional validator เข้ามา
from wtforms.validators import DataRequired, EqualTo, ValidationError, NumberRange, Optional
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField
from app.models import GradeLevel,User, Role, LearningArea

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    full_name = StringField('Full Name', validators=[DataRequired()])
    password = PasswordField('Password') # Not required for editing
    password2 = PasswordField('Repeat Password', validators=[EqualTo('password')])
    roles = MultiCheckboxField('Roles', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save User')

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.roles.choices = [(r.id, r.name) for r in Role.query.order_by('name').all()]

    def validate_username(self, username):
        # Check if username exists when creating a new user
        # or if the username has changed to one that already exists
        user = User.query.filter_by(username=username.data).first()
        if user is not None and (not hasattr(self, 'obj') or self.obj.id != user.id):
            raise ValidationError('This username is already taken.')
        
def get_grade_levels():
    return GradeLevel.query.order_by('id').all()

def get_learning_areas():
    return LearningArea.query.order_by('name').all()

def get_advisors():
    # ดึงเฉพาะ User ที่มีบทบาทเป็น 'Advisor'
    advisor_role = Role.query.filter_by(name='Advisor').first()
    if advisor_role:
        return User.query.filter(User.roles.contains(advisor_role)).order_by(User.full_name).all()
    return []

class AcademicYearForm(FlaskForm):
    year = IntegerField('ปีการศึกษา (พ.ศ.)', validators=[DataRequired(), NumberRange(min=2500, max=3000)])
    semester = IntegerField('ภาคเรียน', validators=[DataRequired(), NumberRange(min=1, max=3)])
    is_active = BooleanField('เปิดใช้งานอยู่')
    submit = SubmitField('บันทึก')

class GradeLevelForm(FlaskForm):
    name = StringField('ชื่อสายชั้น', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class CourseForm(FlaskForm):
    course_code = StringField('รหัสวิชา', validators=[DataRequired()])
    name_thai = StringField('ชื่อวิชา (ภาษาไทย)', validators=[DataRequired()])
    credits = FloatField('หน่วยกิต', validators=[DataRequired(), NumberRange(min=0, max=5)])
    grade_level = QuerySelectField('ระดับชั้น', query_factory=get_grade_levels, get_label='name', allow_blank=False)
    learning_area = QuerySelectField('กลุ่มสาระการเรียนรู้', query_factory=get_learning_areas, get_label='name', allow_blank=False)
    semester = IntegerField('ภาคเรียนที่เปิดสอน', validators=[DataRequired(), NumberRange(min=0, max=2)], description="ระบุ 1, 2 หรือ 0 หากสอนทั้งปี")
    submit = SubmitField('บันทึก')

class ClassroomForm(FlaskForm):
    name = StringField('ชื่อห้องเรียน (เช่น ห้อง 1, ห้อง EP)', validators=[DataRequired()])
    grade_level = QuerySelectField('สายชั้น', query_factory=get_grade_levels, get_label='name', allow_blank=False)
    advisors = QuerySelectMultipleField('ครูที่ปรึกษา', query_factory=get_advisors, get_label='full_name', widget=widgets.ListWidget(prefix_label=False), option_widget=widgets.CheckboxInput())
    submit = SubmitField('บันทึก')

class LoginForm(FlaskForm):
    """ฟอร์มสำหรับหน้า Login"""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class AssessmentDimensionForm(FlaskForm):
    """ฟอร์มสำหรับเพิ่ม/แก้ไขมิติการประเมิน"""
    name = StringField('ชื่อเต็มของมิติ', validators=[DataRequired()])
    code = StringField('รหัสย่อ (เช่น K, S, A, C)', validators=[DataRequired()])
    description = TextAreaField('คำอธิบาย')
    submit = SubmitField('บันทึก')

# --- เพิ่มฟอร์มสำหรับจัดการหน่วยการเรียนรู้ ---
class LearningUnitForm(FlaskForm):
    title = StringField('ชื่อหน่วยการเรียนรู้', validators=[DataRequired()])
    start_period = IntegerField('คาบที่เริ่มต้น', validators=[Optional()])
    end_period = IntegerField('คาบที่สิ้นสุด', validators=[Optional()])
    learning_standard = TextAreaField('มาตรฐานการเรียนรู้/ตัวชี้วัด', validators=[Optional()])
    learning_objectives = TextAreaField('จุดประสงค์การเรียนรู้', validators=[Optional()])
    core_concepts = TextAreaField('สาระสำคัญ (Concepts)', validators=[Optional()])
    learning_content = TextAreaField('สาระการเรียนรู้ (Content)', validators=[Optional()])
    activities = TextAreaField('กิจกรรมการเรียนรู้', validators=[Optional()])
    media_sources = TextAreaField('สื่อและแหล่งเรียนรู้', validators=[Optional()])

    # ใช้ MultiCheckboxField ที่มีอยู่แล้ว
    competencies = MultiCheckboxField('สมรรถนะสำคัญของผู้เรียน', coerce=int, validators=[Optional()])
    desirable_characteristics = MultiCheckboxField('คุณลักษณะอันพึงประสงค์', coerce=int, validators=[Optional()])
    assessment_methods = MultiCheckboxField('การวัดและประเมินผล', coerce=int, validators=[Optional()])
    
    submit = SubmitField('บันทึกหน่วยการเรียนรู้')
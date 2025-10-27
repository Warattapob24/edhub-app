# path: app/teacher/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, TextAreaField, IntegerField, FloatField, BooleanField, widgets
from wtforms.validators import DataRequired, NumberRange, Optional
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField
from app.models import AssessmentDimension, Competency, AssessmentMethod, DesirableCharacteristic, CompetencySubItem, CharacteristicSubItem, MethodSubItem
from app.patched_form_fields import PatchedQuerySelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput

# Query Factory Functions
def get_all_competencies():
    return Competency.query.all()

def get_all_characteristics():
    return DesirableCharacteristic.query.all()

def get_all_assessment_methods():
    return AssessmentMethod.query.all()

class LearningUnitForm(FlaskForm):
    """Form for creating/editing a learning unit."""
    title = StringField('ชื่อหน่วยการเรียนรู้', validators=[DataRequired()])
    start_period = IntegerField('สอนคาบที่', validators=[Optional(), NumberRange(min=1)])
    end_period = IntegerField('ถึงคาบที่', validators=[Optional(), NumberRange(min=1)])
    learning_standard = TextAreaField('มาตรฐานการเรียนรู้/ตัวชี้วัด', validators=[Optional()], render_kw={"rows": 4})
    learning_objectives = TextAreaField('จุดประสงค์การเรียนรู้', validators=[Optional()], render_kw={"rows": 4})
    core_concepts = TextAreaField('สาระสำคัญ', validators=[Optional()], render_kw={"rows": 3})
    learning_content = TextAreaField('สาระการเรียนรู้', validators=[Optional()], render_kw={"rows": 4})
    activities = TextAreaField('กิจกรรมการเรียนรู้', validators=[Optional()], render_kw={"rows": 10})
    media_sources = TextAreaField('สื่อและแหล่งเรียนรู้', validators=[Optional()], render_kw={"rows": 3})
    
    competencies = PatchedQuerySelectMultipleField(
        'สมรรถนะสำคัญของผู้เรียน',
        query_factory=lambda: CompetencySubItem.query.all(),
        get_label='name'
    )

    desirable_characteristics = PatchedQuerySelectMultipleField(
        'คุณลักษณะอันพึงประสงค์',
        query_factory=lambda: CharacteristicSubItem.query.all(),
        get_label='name'
    )

    assessment_methods = PatchedQuerySelectMultipleField(
        'การวัดและประเมินผลการเรียนรู้',
        query_factory=lambda: MethodSubItem.query.all(),
        get_label='name'
    )
    submit = SubmitField('บันทึกหน่วยการเรียนรู้')

class GradeComponentForm(FlaskForm):
    """Form for creating/editing 'grade components' only."""
    name = StringField('ชื่องาน/การวัดผล', validators=[DataRequired()])
    total_max_score = FloatField('คะแนนเต็มรวม', validators=[DataRequired(), NumberRange(min=0.5)])
    
    is_midway_indicator = BooleanField('เป็นตัวชี้วัดระหว่างทาง (หากไม่ผ่าน ไม่ได้เกรด 4)')
    is_critical_indicator = BooleanField('เป็นตัวชี้วัดปลายทาง (ขาดส่งติด "ร")')
    submit = SubmitField('บันทึก')

def get_assessment_dimensions():
    return AssessmentDimension.query.order_by('id').all()

class AssessmentAspectForm(FlaskForm):
    """Form for creating sub-components of a grade component."""
    dimension = QuerySelectField('มิติการประเมิน', query_factory=get_assessment_dimensions, get_label='name', allow_blank=False, validators=[DataRequired()])
    description = StringField('สิ่งที่ต้องการวัด (ถ้ามี)')
    max_score = FloatField('คะแนน', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('เพิ่มองค์ประกอบ')
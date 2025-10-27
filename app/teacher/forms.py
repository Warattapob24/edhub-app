# app/teacher/forms.py (ไฟล์ใหม่)
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class LearningUnitForm(FlaskForm):
    title = StringField('ชื่อหน่วยการเรียนรู้', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('บันทึก')
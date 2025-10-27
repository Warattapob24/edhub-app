# In app/grade_level_head/__init__.py

from flask import Blueprint

bp = Blueprint('grade_level_head', __name__)

from app.grade_level_head import routes
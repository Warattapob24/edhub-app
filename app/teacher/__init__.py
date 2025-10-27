# app/teacher/__init__.py
from flask import Blueprint

bp = Blueprint('teacher', __name__, template_folder='../templates/teacher')

from app.teacher import routes
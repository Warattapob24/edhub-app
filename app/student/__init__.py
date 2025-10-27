# FILE: app/student/__init__.py
from flask import Blueprint

bp = Blueprint('student', __name__, template_folder='templates')

from app.student import routes
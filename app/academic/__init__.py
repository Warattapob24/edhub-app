# FILE: app/academic/__init__.py
from flask import Blueprint

bp = Blueprint('academic', __name__, template_folder='../templates/academic')

from app.academic import routes
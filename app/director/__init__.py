# app/director/__init__.py
from flask import Blueprint

bp = Blueprint('director', __name__, template_folder='templates')

from app.director import routes
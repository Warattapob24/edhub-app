# app/advisor/__init__.py
from flask import Blueprint

bp = Blueprint('advisor', __name__)

from app.advisor import routes
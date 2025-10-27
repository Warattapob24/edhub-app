# app/manager/__init__.py
from flask import Blueprint

bp = Blueprint('manager', __name__)

from app.manager import routes
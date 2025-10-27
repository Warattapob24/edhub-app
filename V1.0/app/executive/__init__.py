# app/executive/__init__.py
from flask import Blueprint

bp = Blueprint('executive', __name__)

from app.executive import routes
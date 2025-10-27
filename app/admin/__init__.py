from flask import Blueprint

# The template_folder is specified relative to the blueprint's folder.
# 'templates' would look inside the 'admin' folder.
# We point it to the main templates folder.
bp = Blueprint('admin', __name__)

from app.admin import routes
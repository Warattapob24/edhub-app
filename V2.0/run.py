# path: run.py

from app import create_app
from seed import seed_data
from backup import backup_data
from restore import restore_data # << เพิ่ม import นี้
import click

app = create_app()

@app.cli.command("seed")
def seed_command():
    """Seeds the database with all initial data required for the app."""
    seed_data()

@app.cli.command("backup")
def backup_command():
    """Creates a JSON backup of the current database."""
    backup_data()

# vv เพิ่มฟังก์ชันนี้เข้าไป vv
@app.cli.command("restore")
@click.argument("filename")
def restore_command(filename):
    """Clears the database and restores data from a JSON backup."""
    restore_data(filename)

if __name__ == "__main__":
    app.run(debug=True)

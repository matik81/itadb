from alembic import command
from alembic.config import Config
from create_reader import main as create_reader

if __name__ == "__main__":
    command.upgrade(Config("alembic.ini"), "head")
    create_reader()

from alembic import context
from sqlalchemy import Connection

connection: Connection = context.config.attributes["connection"]
context.configure(connection=connection)
with context.begin_transaction():
    context.run_migrations()

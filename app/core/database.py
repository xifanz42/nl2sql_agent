from typing import Any

from sqlalchemy import create_engine, inspect, text

from app.config import settings

DATABASE_URL = settings.sqlalchemy_url


class DataBase:
    def __init__(self, url: str | None = None):
        self.engine = create_engine(url or DATABASE_URL)
        self.defult_table_name = "kpi_benchmark"
        self.inspector = inspect(self.engine)

    def get_tables(self) -> list[str]:
        """Get all table names in the database."""
        return self.inspector.get_table_names()

    def get_table_columns(self, table_name: str) -> list[dict[str, Any]]:
        """Get column details for a specific table."""
        return self.inspector.get_columns(table_name)

    def get_primary_keys(self, table_name: str) -> list[str]:
        """Get primary key columns for a specific table."""
        return self.inspector.get_pk_constraint(table_name)["constrained_columns"]

    def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        """Get foreign key constraints for a specific table."""
        return self.inspector.get_foreign_keys(table_name)

    def extract_schema(self) -> str:
        # get table names
        tables = self.get_tables()
        schema_text = "DATABASE SCHEMA\n==============\n\n"

        for table in tables:
            schema_text += f"Table: {table}\n"
            schema_text += "=" * (len(table) + 7) + "\n"

            # get columns & keys
            columns = self.get_table_columns(table)
            primary_keys = self.get_primary_keys(table)
            foreign_keys = {fk["constrained_columns"][0]: fk for fk in self.get_foreign_keys(table)}

            for column in columns:
                column_name = column["name"]
                data_type = str(column["type"])
                nullable = "NULL" if column.get("nullable", True) else "NOT NULL"
                primary = "PRIMARY KEY" if column_name in primary_keys else ""

                # Check if it's a foreign key
                foreign_key_info = ""
                if column_name in foreign_keys:
                    fk = foreign_keys[column_name]
                    foreign_key_info = (
                        f"REFERENCES {fk['referred_table']}({fk['referred_columns'][0]})"
                    )

                schema_text += (
                    f"- {column_name} ({data_type}) {nullable} {primary} {foreign_key_info}\n"
                )

            schema_text += "\n"

        return schema_text

    def get_schema_as_dict(self) -> dict[str, Any]:
        """Extract schema as a structured dictionary."""
        tables = self.get_tables()
        schema_dict = {}

        for table in tables:
            columns = self.get_table_columns(table)
            primary_keys = self.get_primary_keys(table)
            foreign_keys = self.get_foreign_keys(table)

            schema_dict[table] = {
                "columns": columns,
                "primary_keys": primary_keys,
                "foreign_keys": foreign_keys,
            }

        return schema_dict

    def execute_query(self, query: str):
        """Executes a read-only SQL query on the database."""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query))
                return [
                    dict(row) for row in result.mappings()
                ]  # Convert result to dictionary format
        except Exception as e:
            return {"error": str(e)}


class ReadOnlyDataBase(DataBase):
    """Eval-time handle that connects as the least-privilege read-only role.

    The role itself sets ``default_transaction_read_only=on`` and
    ``statement_timeout``; we additionally pin both at the transaction level so
    the guarantee holds even if the role is misconfigured. This is the real
    guardrail for executing model-generated SQL: it is enforced by PostgreSQL,
    not by an application-layer keyword blacklist.
    """

    def __init__(self):
        url = settings.eval_sqlalchemy_url
        if url is None:
            raise RuntimeError(
                "Read-only eval DB is not configured: set EVAL_DATABASE_USER and "
                "EVAL_DATABASE_PASSWORD (see .env.example); bootstrap the role with "
                "scripts/sql/bootstrap_ro_role.sql"
            )
        super().__init__(url)

    def execute_query(self, query: str):
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                result = connection.execute(text(query))
                return [dict(row) for row in result.mappings()]
        except Exception as e:
            return {"error": str(e)}

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from config.settings import BASE_DIR
from src.database import get_engine


SQL_DIRECTORY = BASE_DIR / "sql"

SQL_FILES = [
    SQL_DIRECTORY / "02_create_schemas.sql",
    SQL_DIRECTORY / "03_create_tables.sql",
    SQL_DIRECTORY / "04_merge_cotacoes.sql",
]

def split_sql_batches(sql_content: str) -> list[str]:
    """
    Divide um script SQL Server em lotes separados pela instrução GO.

    A instrução GO é entendida por ferramentas como SSMS, mas não é uma
    instrução nativa executável pelo SQL Server via PyODBC.
    """

    batches = re.split(
        pattern=r"(?im)^\s*GO\s*;?\s*$",
        string=sql_content,
    )

    return [
        batch.strip()
        for batch in batches
        if batch.strip()
    ]


def execute_sql_file(
    connection: Connection,
    file_path: Path,
) -> None:
    """
    Lê e executa todos os lotes de um arquivo SQL.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"Arquivo SQL não encontrado: {file_path}"
        )

    sql_content = file_path.read_text(encoding="utf-8-sig")
    batches = split_sql_batches(sql_content)

    print(f"Executando: {file_path.name}")

    for batch_number, batch in enumerate(batches, start=1):
        connection.exec_driver_sql(batch)

        print(
            f"  Lote {batch_number}/{len(batches)} executado."
        )


def verify_database_structure() -> list[dict[str, str]]:
    """
    Consulta os schemas e tabelas criados pelo projeto.
    """

    query = text(
        """
        SELECT
            SCHEMA_NAME(t.schema_id) AS schema_name,
            t.name AS table_name
        FROM sys.tables AS t
        WHERE SCHEMA_NAME(t.schema_id) IN ('etl', 'dw')
        ORDER BY
            SCHEMA_NAME(t.schema_id),
            t.name;
        """
    )

    engine = get_engine()

    with engine.connect() as connection:
        result = connection.execute(query).mappings().all()

    return [dict(row) for row in result]


def setup_database() -> None:
    """
    Executa os scripts de criação da estrutura do banco.
    """

    engine = get_engine()

    try:
        with engine.begin() as connection:
            for sql_file in SQL_FILES:
                execute_sql_file(
                    connection=connection,
                    file_path=sql_file,
                )

        print()
        print("Estrutura do banco criada com sucesso.")
        print()
        print("Tabelas encontradas:")

        tables = verify_database_structure()

        if not tables:
            print("Nenhuma tabela do projeto foi encontrada.")
            return

        for table in tables:
            print(
                f"  - {table['schema_name']}."
                f"{table['table_name']}"
            )

    except Exception as error:
        print()
        print("Falha ao configurar o banco de dados.")
        print(f"Tipo: {type(error).__name__}")
        print(f"Detalhes: {error}")

        raise


if __name__ == "__main__":
    setup_database()
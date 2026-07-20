from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import (
    DB_AUTH,
    DB_DATABASE,
    DB_DRIVER,
    DB_PASSWORD,
    DB_SERVER,
    DB_TRUST_SERVER_CERTIFICATE,
    DB_USERNAME,
    validate_settings,
)


def build_odbc_connection_string(
    database: str | None = None,
) -> str:
    """
    Monta a string de conexão ODBC com o SQL Server.

    Args:
        database:
            Nome do banco de dados desejado.
            Quando não informado, utiliza DB_DATABASE do arquivo .env.

    Returns:
        String de conexão compatível com o pyodbc.
    """

    selected_database = database or DB_DATABASE

    connection_parts = [
        f"DRIVER={{{DB_DRIVER}}}",
        f"SERVER={DB_SERVER}",
        f"DATABASE={selected_database}",
    ]

    if DB_AUTH == "windows":
        connection_parts.append("Trusted_Connection=yes")

    elif DB_AUTH == "sql":
        connection_parts.extend(
            [
                f"UID={DB_USERNAME}",
                f"PWD={DB_PASSWORD}",
            ]
        )

    else:
        raise ValueError(
            "DB_AUTH deve possuir o valor 'windows' ou 'sql'."
        )

    if DB_TRUST_SERVER_CERTIFICATE:
        connection_parts.append("TrustServerCertificate=yes")

    return ";".join(connection_parts) + ";"


def get_engine(
    database: str | None = None,
) -> Engine:
    """
    Cria e retorna uma engine SQLAlchemy para o SQL Server.

    Args:
        database:
            Nome opcional do banco de dados.

    Returns:
        Engine configurada para conexão com o SQL Server.
    """

    validate_settings()

    odbc_connection_string = build_odbc_connection_string(
        database=database
    )

    encoded_connection_string = quote_plus(
        odbc_connection_string
    )

    connection_url = (
        "mssql+pyodbc:///?odbc_connect="
        f"{encoded_connection_string}"
    )

    engine = create_engine(
        connection_url,
        pool_pre_ping=True,
        fast_executemany=True,
    )

    return engine


def test_database_connection() -> dict[str, Any]:
    """
    Testa a conexão e retorna informações do SQL Server.

    Returns:
        Dicionário com servidor, banco, usuário e versão.
    """

    engine = get_engine()

    query = text(
        """
        SELECT
            @@SERVERNAME AS servidor,
            DB_NAME() AS banco_atual,
            SUSER_SNAME() AS usuario_conectado,
            @@VERSION AS versao_sql_server;
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query).mappings().one()

    return dict(result)


def print_connection_test() -> None:
    """
    Executa o teste e apresenta o resultado no terminal.
    """

    try:
        connection_info = test_database_connection()

        print("Conexão SQLAlchemy realizada com sucesso!")
        print(
            f"Servidor: "
            f"{connection_info['servidor']}"
        )
        print(
            f"Banco atual: "
            f"{connection_info['banco_atual']}"
        )
        print(
            f"Usuário conectado: "
            f"{connection_info['usuario_conectado']}"
        )

        version = str(
            connection_info["versao_sql_server"]
        ).splitlines()[0]

        print(f"Versão: {version}")

    except Exception as error:
        print("Falha na conexão com o SQL Server.")
        print(f"Tipo do erro: {type(error).__name__}")
        print(f"Detalhes: {error}")

        raise


if __name__ == "__main__":
    print_connection_test()
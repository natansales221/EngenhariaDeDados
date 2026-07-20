import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

from config.settings import (
    PROCESSED_DIR,
    validate_settings,
)
from src.database import get_engine


# ============================================================
# DEFINIÇÃO DAS COLUNAS
# ============================================================

PROCESSED_REQUIRED_COLUMNS = [
    "moeda",
    "paridade_compra",
    "paridade_venda",
    "cotacao_compra",
    "cotacao_venda",
    "data_hora_cotacao",
    "tipo_boletim",
    "data_referencia",
    "data_extracao",
    "arquivo_origem",
]

STAGING_COLUMNS = [
    "id_execucao",
    "moeda",
    "paridade_compra",
    "paridade_venda",
    "cotacao_compra",
    "cotacao_venda",
    "data_hora_cotacao",
    "tipo_boletim",
    "data_referencia",
    "data_extracao",
    "arquivo_origem",
]

NUMERIC_COLUMNS = [
    "paridade_compra",
    "paridade_venda",
    "cotacao_compra",
    "cotacao_venda",
]


# ============================================================
# RESULTADO DA CARGA
# ============================================================

@dataclass(frozen=True)
class LoadResult:
    """
    Resultado da carga dos dados no SQL Server.
    """

    id_execucao: int
    processed_file: Path
    staging_row_count: int
    inserted_row_count: int
    updated_row_count: int


# ============================================================
# LOCALIZAÇÃO E LEITURA DO ARQUIVO
# ============================================================

def find_latest_processed_file() -> Path:
    """
    Localiza o CSV mais recente na camada processada.
    """

    processed_files = list(
        PROCESSED_DIR.rglob("*.csv")
    )

    if not processed_files:
        raise FileNotFoundError(
            "Nenhum arquivo processado foi encontrado em: "
            f"{PROCESSED_DIR}"
        )

    return max(
        processed_files,
        key=lambda file_path: file_path.stat().st_mtime,
    )


def read_processed_csv(
    processed_file: Path,
) -> pd.DataFrame:
    """
    Lê e converte os tipos do arquivo processado.
    """

    if not processed_file.exists():
        raise FileNotFoundError(
            f"Arquivo processado não encontrado: {processed_file}"
        )

    dataframe = pd.read_csv(
        processed_file,
        encoding="utf-8-sig",
        dtype={
            "moeda": "string",
            "tipo_boletim": "string",
            "arquivo_origem": "string",
        },
    )

    return dataframe


def validate_processed_schema(
    dataframe: pd.DataFrame,
) -> None:
    """
    Verifica se todas as colunas necessárias estão presentes.
    """

    missing_columns = [
        column
        for column in PROCESSED_REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            "O arquivo processado não possui as colunas: "
            + ", ".join(missing_columns)
        )


def convert_processed_types(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Converte os campos para os tipos esperados no SQL Server.
    """

    converted = dataframe.copy()

    converted["moeda"] = (
        converted["moeda"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    converted["tipo_boletim"] = (
        converted["tipo_boletim"]
        .astype("string")
        .str.strip()
    )

    converted["arquivo_origem"] = (
        converted["arquivo_origem"]
        .astype("string")
        .str.strip()
    )

    for column in NUMERIC_COLUMNS:
        converted[column] = pd.to_numeric(
            converted[column],
            errors="raise",
        )

    converted["data_hora_cotacao"] = pd.to_datetime(
        converted["data_hora_cotacao"],
        errors="raise",
    )

    converted["data_extracao"] = pd.to_datetime(
        converted["data_extracao"],
        errors="raise",
    )

    converted["data_referencia"] = pd.to_datetime(
        converted["data_referencia"],
        errors="raise",
    ).dt.date

    null_columns = [
        column
        for column in PROCESSED_REQUIRED_COLUMNS
        if converted[column].isna().any()
    ]

    if null_columns:
        raise ValueError(
            "Foram encontrados valores nulos nas colunas: "
            + ", ".join(null_columns)
        )

    return converted


# ============================================================
# CONTROLE DA EXECUÇÃO
# ============================================================

def create_execution_record(
    connection: Connection,
    dataframe: pd.DataFrame,
    processed_file: Path,
) -> int:
    """
    Registra o início da execução e retorna seu identificador.
    """

    start_reference = dataframe[
        "data_referencia"
    ].min()

    end_reference = dataframe[
        "data_referencia"
    ].max()

    raw_file = str(
        dataframe["arquivo_origem"].iloc[0]
    )

    query = text(
        """
        INSERT INTO etl.execucao_pipeline
        (
            nome_pipeline,
            status,
            data_inicio_referencia,
            data_fim_referencia,
            quantidade_extraida,
            quantidade_transformada,
            arquivo_raw,
            arquivo_processado
        )
        OUTPUT INSERTED.id_execucao
        VALUES
        (
            :nome_pipeline,
            N'INICIADO',
            :data_inicio_referencia,
            :data_fim_referencia,
            :quantidade_extraida,
            :quantidade_transformada,
            :arquivo_raw,
            :arquivo_processado
        );
        """
    )

    result = connection.execute(
        query,
        {
            "nome_pipeline": "pipeline_ptax",
            "data_inicio_referencia": start_reference,
            "data_fim_referencia": end_reference,
            "quantidade_extraida": len(dataframe),
            "quantidade_transformada": len(dataframe),
            "arquivo_raw": raw_file,
            "arquivo_processado": str(
                processed_file.resolve()
            ),
        },
    )

    return int(result.scalar_one())


def finish_execution_success(
    connection: Connection,
    id_execucao: int,
    inserted_row_count: int,
    updated_row_count: int,
) -> None:
    """
    Atualiza a execução com status de sucesso.
    """

    query = text(
        """
        UPDATE etl.execucao_pipeline
        SET
            data_fim = SYSDATETIME(),
            status = N'SUCESSO',
            quantidade_inserida = :quantidade_inserida,
            quantidade_atualizada = :quantidade_atualizada,
            mensagem_erro = NULL
        WHERE id_execucao = :id_execucao;
        """
    )

    connection.execute(
        query,
        {
            "id_execucao": id_execucao,
            "quantidade_inserida": inserted_row_count,
            "quantidade_atualizada": updated_row_count,
        },
    )


def finish_execution_error(
    connection: Connection,
    id_execucao: int,
    error: Exception,
) -> None:
    """
    Atualiza a execução com status de erro.
    """

    error_message = (
        f"{type(error).__name__}: {error}"
    )

    query = text(
        """
        DELETE FROM etl.stg_cotacao_moeda
        WHERE id_execucao = :id_execucao;

        UPDATE etl.execucao_pipeline
        SET
            data_fim = SYSDATETIME(),
            status = N'ERRO',
            mensagem_erro = :mensagem_erro
        WHERE id_execucao = :id_execucao;
        """
    )

    connection.execute(
        query,
        {
            "id_execucao": id_execucao,
            "mensagem_erro": error_message,
        },
    )


# ============================================================
# CARGA NA STAGING
# ============================================================

def load_to_staging(
    connection: Connection,
    dataframe: pd.DataFrame,
    id_execucao: int,
) -> int:
    """
    Insere os registros processados na tabela de staging.
    """

    staging_dataframe = dataframe.copy()

    staging_dataframe.insert(
        loc=0,
        column="id_execucao",
        value=id_execucao,
    )

    staging_dataframe = staging_dataframe[
        STAGING_COLUMNS
    ]

    staging_dataframe.to_sql(
        name="stg_cotacao_moeda",
        con=connection,
        schema="etl",
        if_exists="append",
        index=False,
        chunksize=1000,
        method=None,
    )

    return len(staging_dataframe)


# ============================================================
# CARGA INCREMENTAL NA TABELA FINAL
# ============================================================

def execute_incremental_load(
    connection: Connection,
    id_execucao: int,
) -> dict[str, int]:
    """
    Executa a procedure de atualização e inserção.
    """

    query = text(
        """
        EXEC etl.usp_carregar_cotacao_moeda
            @id_execucao = :id_execucao;
        """
    )

    result = connection.execute(
        query,
        {
            "id_execucao": id_execucao,
        },
    ).mappings().one()

    return {
        "quantidade_inserida": int(
            result["quantidade_inserida"]
        ),
        "quantidade_atualizada": int(
            result["quantidade_atualizada"]
        ),
    }


# ============================================================
# CARGA PRINCIPAL
# ============================================================

def load_processed_data(
    processed_file: Path | None = None,
) -> LoadResult:
    """
    Executa a carga completa do arquivo processado.
    """

    validate_settings()

    selected_processed_file = (
        processed_file.resolve()
        if processed_file
        else find_latest_processed_file().resolve()
    )

    print(
        "Lendo arquivo processado: "
        f"{selected_processed_file}"
    )

    dataframe = read_processed_csv(
        selected_processed_file
    )

    if dataframe.empty:
        raise ValueError(
            "O arquivo processado está vazio."
        )

    validate_processed_schema(dataframe)

    dataframe = convert_processed_types(
        dataframe
    )

    engine = get_engine()

    id_execucao: int | None = None

    try:
        # O registro inicial é salvo em uma transação própria.
        with engine.begin() as connection:
            id_execucao = create_execution_record(
                connection=connection,
                dataframe=dataframe,
                processed_file=selected_processed_file,
            )

        print(
            f"Execução registrada com ID: {id_execucao}"
        )

        # Staging e carga incremental participam da mesma transação.
        with engine.begin() as connection:
            staging_row_count = load_to_staging(
                connection=connection,
                dataframe=dataframe,
                id_execucao=id_execucao,
            )

            print(
                f"Registros enviados para staging: "
                f"{staging_row_count}"
            )

            load_metrics = execute_incremental_load(
                connection=connection,
                id_execucao=id_execucao,
            )

        inserted_row_count = load_metrics[
            "quantidade_inserida"
        ]

        updated_row_count = load_metrics[
            "quantidade_atualizada"
        ]

        with engine.begin() as connection:
            finish_execution_success(
                connection=connection,
                id_execucao=id_execucao,
                inserted_row_count=inserted_row_count,
                updated_row_count=updated_row_count,
            )

        return LoadResult(
            id_execucao=id_execucao,
            processed_file=selected_processed_file,
            staging_row_count=staging_row_count,
            inserted_row_count=inserted_row_count,
            updated_row_count=updated_row_count,
        )

    except Exception as error:
        if id_execucao is not None:
            with engine.begin() as connection:
                finish_execution_error(
                    connection=connection,
                    id_execucao=id_execucao,
                    error=error,
                )

        raise


# ============================================================
# EXECUÇÃO PELO TERMINAL
# ============================================================

def create_argument_parser() -> argparse.ArgumentParser:
    """
    Configura os argumentos da carga.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Carrega o CSV processado na staging "
            "e na tabela final do SQL Server."
        )
    )

    parser.add_argument(
        "--processed-file",
        type=Path,
        required=False,
        help=(
            "Arquivo CSV processado. "
            "Quando omitido, utiliza o mais recente."
        ),
    )

    return parser


def main() -> None:
    """
    Ponto de entrada da carga.
    """

    parser = create_argument_parser()
    arguments = parser.parse_args()

    try:
        result = load_processed_data(
            processed_file=arguments.processed_file
        )

        print()
        print("Carga concluída com sucesso!")
        print(
            f"ID da execução: "
            f"{result.id_execucao}"
        )
        print(
            f"Registros na staging: "
            f"{result.staging_row_count}"
        )
        print(
            f"Registros inseridos: "
            f"{result.inserted_row_count}"
        )
        print(
            f"Registros atualizados: "
            f"{result.updated_row_count}"
        )

    except Exception as error:
        print()
        print("Falha durante a carga.")
        print(f"Tipo: {type(error).__name__}")
        print(f"Detalhes: {error}")

        raise


if __name__ == "__main__":
    main()
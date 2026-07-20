import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from config.settings import (
    PROCESSED_DIR,
    RAW_DIR,
    REJECTED_DIR,
    create_project_directories,
    validate_settings,
)


# ============================================================
# DEFINIÇÃO DAS COLUNAS
# ============================================================

RAW_REQUIRED_COLUMNS = [
    "moeda",
    "paridadeCompra",
    "paridadeVenda",
    "cotacaoCompra",
    "cotacaoVenda",
    "dataHoraCotacao",
    "tipoBoletim",
    "data_extracao",
]

COLUMN_MAPPING = {
    "paridadeCompra": "paridade_compra",
    "paridadeVenda": "paridade_venda",
    "cotacaoCompra": "cotacao_compra",
    "cotacaoVenda": "cotacao_venda",
    "dataHoraCotacao": "data_hora_cotacao",
    "tipoBoletim": "tipo_boletim",
}

FINAL_COLUMNS = [
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

BUSINESS_KEY_COLUMNS = [
    "moeda",
    "data_hora_cotacao",
    "tipo_boletim",
]

NUMERIC_COLUMNS = [
    "paridade_compra",
    "paridade_venda",
    "cotacao_compra",
    "cotacao_venda",
]


# ============================================================
# RESULTADO DA TRANSFORMAÇÃO
# ============================================================

@dataclass(frozen=True)
class TransformationResult:
    """
    Resultado produzido pela etapa de transformação.
    """

    raw_file: Path
    processed_file: Path
    rejected_file: Path | None
    raw_row_count: int
    processed_row_count: int
    rejected_row_count: int
    duplicate_row_count: int


# ============================================================
# LOCALIZAÇÃO DO ARQUIVO RAW
# ============================================================

def find_latest_raw_file() -> Path:
    """
    Localiza o arquivo CSV mais recente da camada RAW.

    Returns:
        Caminho do arquivo mais recente.

    Raises:
        FileNotFoundError:
            Caso nenhum arquivo CSV seja encontrado.
    """

    raw_files = list(RAW_DIR.rglob("*.csv"))

    if not raw_files:
        raise FileNotFoundError(
            f"Nenhum arquivo CSV encontrado em: {RAW_DIR}"
        )

    return max(
        raw_files,
        key=lambda file_path: file_path.stat().st_mtime,
    )


# ============================================================
# LEITURA E VALIDAÇÃO DO SCHEMA
# ============================================================

def read_raw_csv(raw_file: Path) -> pd.DataFrame:
    """
    Lê o CSV bruto mantendo inicialmente os valores como texto.
    """

    if not raw_file.exists():
        raise FileNotFoundError(
            f"Arquivo RAW não encontrado: {raw_file}"
        )

    return pd.read_csv(
        raw_file,
        dtype="string",
        encoding="utf-8-sig",
    )


def validate_raw_schema(dataframe: pd.DataFrame) -> None:
    """
    Verifica se o arquivo RAW possui todas as colunas esperadas.
    """

    missing_columns = [
        column
        for column in RAW_REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            "O arquivo RAW não possui as colunas obrigatórias: "
            + ", ".join(missing_columns)
        )


# ============================================================
# PADRONIZAÇÃO
# ============================================================

def standardize_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Renomeia e seleciona as colunas utilizadas pelo pipeline.
    """

    standardized = dataframe.rename(
        columns=COLUMN_MAPPING
    ).copy()

    standardized["arquivo_origem"] = ""

    return standardized


def clean_text_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Padroniza valores textuais.
    """

    cleaned = dataframe.copy()

    cleaned["moeda"] = (
        cleaned["moeda"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    cleaned["tipo_boletim"] = (
        cleaned["tipo_boletim"]
        .astype("string")
        .str.strip()
    )

    return cleaned


# ============================================================
# CONVERSÃO DE TIPOS
# ============================================================

def convert_numeric_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Converte as colunas financeiras para valores numéricos.
    """

    converted = dataframe.copy()

    for column in NUMERIC_COLUMNS:
        converted[column] = pd.to_numeric(
            converted[column],
            errors="coerce",
        )

    return converted


def convert_datetime_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Converte as colunas de data e hora.
    """

    converted = dataframe.copy()

    converted["data_hora_cotacao"] = pd.to_datetime(
        converted["data_hora_cotacao"],
        errors="coerce",
    )

    converted["data_extracao"] = pd.to_datetime(
        converted["data_extracao"],
        errors="coerce",
    )

    converted["data_referencia"] = (
        converted["data_hora_cotacao"].dt.date
    )

    return converted


# ============================================================
# VALIDAÇÃO DOS REGISTROS
# ============================================================

def create_rejection_reason_column(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cria a coluna que armazenará os motivos de rejeição.
    """

    validated = dataframe.copy()
    validated["motivo_rejeicao"] = ""

    return validated


def append_rejection_reason(
    dataframe: pd.DataFrame,
    condition: pd.Series,
    reason: str,
) -> None:
    """
    Acrescenta um motivo de rejeição nas linhas indicadas.
    """

    current_reason = dataframe.loc[
        condition,
        "motivo_rejeicao",
    ]

    separator = current_reason.apply(
        lambda value: "; " if value else ""
    )

    dataframe.loc[
        condition,
        "motivo_rejeicao",
    ] = current_reason + separator + reason


def validate_records(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aplica as regras de qualidade nos registros.
    """

    validated = create_rejection_reason_column(
        dataframe
    )

    append_rejection_reason(
        validated,
        validated["moeda"].isna()
        | (validated["moeda"].str.len() != 3),
        "moeda_invalida",
    )

    append_rejection_reason(
        validated,
        validated["tipo_boletim"].isna()
        | (validated["tipo_boletim"] == ""),
        "tipo_boletim_ausente",
    )

    append_rejection_reason(
        validated,
        validated["data_hora_cotacao"].isna(),
        "data_hora_cotacao_invalida",
    )

    append_rejection_reason(
        validated,
        validated["data_extracao"].isna(),
        "data_extracao_invalida",
    )

    for column in NUMERIC_COLUMNS:
        append_rejection_reason(
            validated,
            validated[column].isna(),
            f"{column}_invalida",
        )

        append_rejection_reason(
            validated,
            validated[column].notna()
            & (validated[column] < 0),
            f"{column}_negativa",
        )

    return validated


# ============================================================
# DUPLICIDADES
# ============================================================

def identify_duplicate_records(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separa registros únicos e duplicados.

    Em caso de duplicidade, mantém o registro com a extração
    mais recente.
    """

    ordered = dataframe.sort_values(
        by="data_extracao",
        ascending=True,
        na_position="first",
    ).copy()

    duplicate_mask = ordered.duplicated(
        subset=BUSINESS_KEY_COLUMNS,
        keep="last",
    )

    duplicate_records = ordered.loc[
        duplicate_mask
    ].copy()

    valid_records = ordered.loc[
        ~duplicate_mask
    ].copy()

    if not duplicate_records.empty:
        duplicate_records["motivo_rejeicao"] = (
            duplicate_records["motivo_rejeicao"]
            .apply(
                lambda value: (
                    f"{value}; registro_duplicado"
                    if value
                    else "registro_duplicado"
                )
            )
        )

    return valid_records, duplicate_records


# ============================================================
# CAMINHOS DE SAÍDA
# ============================================================

def build_output_file_paths(
    raw_file: Path,
    transformation_datetime: datetime,
) -> tuple[Path, Path]:
    """
    Gera os caminhos dos arquivos processado e rejeitado.
    """

    relative_directory = (
        transformation_datetime.strftime("%Y/%m/%d")
    )

    processed_directory = (
        PROCESSED_DIR / relative_directory
    )

    rejected_directory = (
        REJECTED_DIR / relative_directory
    )

    processed_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    rejected_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_stem = raw_file.stem

    processed_filename = (
        f"{raw_stem}_processed.csv"
    )

    rejected_filename = (
        f"{raw_stem}_rejected.csv"
    )

    return (
        processed_directory / processed_filename,
        rejected_directory / rejected_filename,
    )


# ============================================================
# GRAVAÇÃO DOS ARQUIVOS
# ============================================================

def save_processed_csv(
    dataframe: pd.DataFrame,
    processed_file: Path,
) -> None:
    """
    Grava o arquivo tratado na camada PROCESSED.
    """

    output = dataframe[FINAL_COLUMNS].copy()

    output.to_csv(
        processed_file,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d %H:%M:%S.%f",
    )


def save_rejected_csv(
    dataframe: pd.DataFrame,
    rejected_file: Path,
) -> None:
    """
    Grava os registros rejeitados.
    """

    dataframe.to_csv(
        rejected_file,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d %H:%M:%S.%f",
    )


# ============================================================
# TRANSFORMAÇÃO PRINCIPAL
# ============================================================

def transform_ptax_data(
    raw_file: Path | None = None,
) -> TransformationResult:
    """
    Executa a transformação completa do arquivo RAW.

    Args:
        raw_file:
            Arquivo que será transformado.
            Quando não informado, utiliza o CSV RAW mais recente.

    Returns:
        Resultado e métricas da transformação.
    """

    validate_settings()
    create_project_directories()

    selected_raw_file = (
        raw_file.resolve()
        if raw_file
        else find_latest_raw_file().resolve()
    )

    print(f"Lendo arquivo RAW: {selected_raw_file}")

    raw_dataframe = read_raw_csv(
        selected_raw_file
    )

    raw_row_count = len(raw_dataframe)

    if raw_dataframe.empty:
        raise ValueError(
            "O arquivo RAW está vazio."
        )

    validate_raw_schema(raw_dataframe)

    transformed = standardize_columns(
        raw_dataframe
    )

    transformed["arquivo_origem"] = (
        selected_raw_file.name
    )

    transformed = clean_text_columns(
        transformed
    )

    transformed = convert_numeric_columns(
        transformed
    )

    transformed = convert_datetime_columns(
        transformed
    )

    validated = validate_records(
        transformed
    )

    invalid_mask = (
        validated["motivo_rejeicao"] != ""
    )

    invalid_records = validated.loc[
        invalid_mask
    ].copy()

    valid_records = validated.loc[
        ~invalid_mask
    ].copy()

    valid_records, duplicate_records = (
        identify_duplicate_records(valid_records)
    )

    rejected_records = pd.concat(
        [
            invalid_records,
            duplicate_records,
        ],
        ignore_index=True,
    )

    transformation_datetime = datetime.now()

    processed_file, rejected_file = (
        build_output_file_paths(
            raw_file=selected_raw_file,
            transformation_datetime=transformation_datetime,
        )
    )

    save_processed_csv(
        dataframe=valid_records,
        processed_file=processed_file,
    )

    final_rejected_file: Path | None = None

    if not rejected_records.empty:
        save_rejected_csv(
            dataframe=rejected_records,
            rejected_file=rejected_file,
        )

        final_rejected_file = rejected_file

    return TransformationResult(
        raw_file=selected_raw_file,
        processed_file=processed_file,
        rejected_file=final_rejected_file,
        raw_row_count=raw_row_count,
        processed_row_count=len(valid_records),
        rejected_row_count=len(rejected_records),
        duplicate_row_count=len(duplicate_records),
    )


# ============================================================
# EXECUÇÃO PELO TERMINAL
# ============================================================

def create_argument_parser() -> argparse.ArgumentParser:
    """
    Configura os argumentos aceitos pelo módulo.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Transforma o CSV RAW da API PTAX, "
            "valida os registros e gera os arquivos "
            "processado e rejeitado."
        )
    )

    parser.add_argument(
        "--raw-file",
        type=Path,
        required=False,
        help=(
            "Caminho do arquivo RAW. "
            "Quando omitido, utiliza o CSV mais recente."
        ),
    )

    return parser


def main() -> None:
    """
    Ponto de entrada da transformação.
    """

    parser = create_argument_parser()
    arguments = parser.parse_args()

    try:
        result = transform_ptax_data(
            raw_file=arguments.raw_file
        )

        print()
        print("Transformação concluída com sucesso!")
        print(f"Arquivo RAW: {result.raw_file}")
        print(
            f"Arquivo processado: "
            f"{result.processed_file}"
        )

        if result.rejected_file:
            print(
                f"Arquivo rejeitado: "
                f"{result.rejected_file}"
            )
        else:
            print("Nenhum registro foi rejeitado.")

        print()
        print("Resumo da transformação:")
        print(
            f"  Registros recebidos: "
            f"{result.raw_row_count}"
        )
        print(
            f"  Registros processados: "
            f"{result.processed_row_count}"
        )
        print(
            f"  Registros rejeitados: "
            f"{result.rejected_row_count}"
        )
        print(
            f"  Registros duplicados: "
            f"{result.duplicate_row_count}"
        )

    except Exception as error:
        print()
        print("Falha durante a transformação.")
        print(f"Tipo: {type(error).__name__}")
        print(f"Detalhes: {error}")

        raise


if __name__ == "__main__":
    main()
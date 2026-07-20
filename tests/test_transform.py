from pathlib import Path

import pandas as pd
import pytest

import src.transform as transform


def create_valid_raw_dataframe() -> pd.DataFrame:
    """
    Cria um DataFrame RAW válido para reutilização nos testes.
    """

    return pd.DataFrame(
        [
            {
                "moeda": "USD",
                "paridadeCompra": "1.0000",
                "paridadeVenda": "1.0000",
                "cotacaoCompra": "5.4000",
                "cotacaoVenda": "5.4100",
                "dataHoraCotacao": (
                    "2026-07-13 10:00:00.000"
                ),
                "tipoBoletim": "Abertura",
                "data_extracao": (
                    "2026-07-20T10:30:00.000"
                ),
            }
        ]
    )


def prepare_dataframe_for_validation(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Executa as etapas anteriores à validação dos registros.
    """

    prepared = transform.standardize_columns(
        dataframe
    )

    prepared = transform.clean_text_columns(
        prepared
    )

    prepared = transform.convert_numeric_columns(
        prepared
    )

    prepared = transform.convert_datetime_columns(
        prepared
    )

    return prepared


def test_validate_raw_schema_success() -> None:
    """
    Um DataFrame com todas as colunas deve ser aceito.
    """

    dataframe = create_valid_raw_dataframe()

    transform.validate_raw_schema(dataframe)


def test_validate_raw_schema_rejects_missing_column() -> None:
    """
    Deve gerar erro quando uma coluna obrigatória não existir.
    """

    dataframe = create_valid_raw_dataframe().drop(
        columns=["cotacaoVenda"]
    )

    with pytest.raises(
        ValueError,
        match="cotacaoVenda",
    ):
        transform.validate_raw_schema(dataframe)


def test_convert_numeric_columns() -> None:
    """
    Deve converter textos numéricos para valores numéricos.
    """

    dataframe = create_valid_raw_dataframe()

    standardized = transform.standardize_columns(
        dataframe
    )

    result = transform.convert_numeric_columns(
        standardized
    )

    assert result["cotacao_compra"].iloc[0] == 5.4
    assert result["cotacao_venda"].iloc[0] == 5.41

    assert pd.api.types.is_numeric_dtype(
        result["cotacao_compra"]
    )


def test_invalid_numeric_value_becomes_null() -> None:
    """
    Um conteúdo numérico inválido deve ser convertido para NaN.
    """

    dataframe = create_valid_raw_dataframe()

    dataframe.loc[
        0,
        "cotacaoCompra",
    ] = "valor_invalido"

    standardized = transform.standardize_columns(
        dataframe
    )

    result = transform.convert_numeric_columns(
        standardized
    )

    assert pd.isna(
        result["cotacao_compra"].iloc[0]
    )


def test_validate_records_identifies_invalid_currency() -> None:
    """
    Uma moeda que não possui três caracteres deve ser rejeitada.
    """

    dataframe = create_valid_raw_dataframe()

    dataframe.loc[0, "moeda"] = "US"

    prepared = prepare_dataframe_for_validation(
        dataframe
    )

    result = transform.validate_records(
        prepared
    )

    rejection_reason = result[
        "motivo_rejeicao"
    ].iloc[0]

    assert "moeda_invalida" in rejection_reason


def test_validate_records_identifies_negative_value() -> None:
    """
    Uma cotação negativa deve ser rejeitada.
    """

    dataframe = create_valid_raw_dataframe()

    dataframe.loc[
        0,
        "cotacaoCompra",
    ] = "-5.40"

    prepared = prepare_dataframe_for_validation(
        dataframe
    )

    result = transform.validate_records(
        prepared
    )

    rejection_reason = result[
        "motivo_rejeicao"
    ].iloc[0]

    assert (
        "cotacao_compra_negativa"
        in rejection_reason
    )


def test_identify_duplicate_records_keeps_latest() -> None:
    """
    Deve manter o registro com a data de extração mais recente.
    """

    dataframe = pd.DataFrame(
        [
            {
                "moeda": "USD",
                "data_hora_cotacao": pd.Timestamp(
                    "2026-07-13 10:00:00"
                ),
                "tipo_boletim": "Abertura",
                "data_extracao": pd.Timestamp(
                    "2026-07-20 10:00:00"
                ),
                "cotacao_compra": 5.40,
                "motivo_rejeicao": "",
            },
            {
                "moeda": "USD",
                "data_hora_cotacao": pd.Timestamp(
                    "2026-07-13 10:00:00"
                ),
                "tipo_boletim": "Abertura",
                "data_extracao": pd.Timestamp(
                    "2026-07-20 11:00:00"
                ),
                "cotacao_compra": 5.50,
                "motivo_rejeicao": "",
            },
        ]
    )

    valid_records, duplicate_records = (
        transform.identify_duplicate_records(
            dataframe
        )
    )

    assert len(valid_records) == 1
    assert len(duplicate_records) == 1

    assert (
        valid_records["cotacao_compra"].iloc[0]
        == 5.50
    )

    assert (
        "registro_duplicado"
        in duplicate_records[
            "motivo_rejeicao"
        ].iloc[0]
    )


def test_transform_ptax_data_end_to_end(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Deve gerar o arquivo processado e separar uma duplicidade
    no arquivo de rejeitados.
    """

    raw_directory = tmp_path / "raw"
    processed_directory = tmp_path / "processed"
    rejected_directory = tmp_path / "rejected"

    raw_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_file = raw_directory / "ptax_test.csv"

    dataframe = pd.DataFrame(
        [
            {
                "moeda": "USD",
                "paridadeCompra": "1.0000",
                "paridadeVenda": "1.0000",
                "cotacaoCompra": "5.4000",
                "cotacaoVenda": "5.4100",
                "dataHoraCotacao": (
                    "2026-07-13 10:00:00.000"
                ),
                "tipoBoletim": "Abertura",
                "data_extracao": (
                    "2026-07-20T10:00:00.000"
                ),
            },
            {
                "moeda": "USD",
                "paridadeCompra": "1.0000",
                "paridadeVenda": "1.0000",
                "cotacaoCompra": "5.5000",
                "cotacaoVenda": "5.5100",
                "dataHoraCotacao": (
                    "2026-07-13 10:00:00.000"
                ),
                "tipoBoletim": "Abertura",
                "data_extracao": (
                    "2026-07-20T11:00:00.000"
                ),
            },
            {
                "moeda": "EUR",
                "paridadeCompra": "1.1000",
                "paridadeVenda": "1.1000",
                "cotacaoCompra": "6.0000",
                "cotacaoVenda": "6.0100",
                "dataHoraCotacao": (
                    "2026-07-13 10:00:00.000"
                ),
                "tipoBoletim": "Abertura",
                "data_extracao": (
                    "2026-07-20T10:00:00.000"
                ),
            },
        ]
    )

    dataframe.to_csv(
        raw_file,
        index=False,
        encoding="utf-8-sig",
    )

    monkeypatch.setattr(
        transform,
        "RAW_DIR",
        raw_directory,
    )

    monkeypatch.setattr(
        transform,
        "PROCESSED_DIR",
        processed_directory,
    )

    monkeypatch.setattr(
        transform,
        "REJECTED_DIR",
        rejected_directory,
    )

    monkeypatch.setattr(
        transform,
        "validate_settings",
        lambda: None,
    )

    monkeypatch.setattr(
        transform,
        "create_project_directories",
        lambda: None,
    )

    result = transform.transform_ptax_data(
        raw_file=raw_file
    )

    assert result.raw_row_count == 3
    assert result.processed_row_count == 2
    assert result.rejected_row_count == 1
    assert result.duplicate_row_count == 1

    assert result.processed_file.exists()
    assert result.rejected_file is not None
    assert result.rejected_file.exists()

    processed_dataframe = pd.read_csv(
        result.processed_file,
        encoding="utf-8-sig",
    )

    rejected_dataframe = pd.read_csv(
        result.rejected_file,
        encoding="utf-8-sig",
    )

    assert len(processed_dataframe) == 2
    assert len(rejected_dataframe) == 1

    processed_usd = processed_dataframe.loc[
        processed_dataframe["moeda"] == "USD"
    ]

    assert (
        processed_usd["cotacao_compra"].iloc[0]
        == 5.50
    )

    assert (
        "registro_duplicado"
        in rejected_dataframe[
            "motivo_rejeicao"
        ].iloc[0]
    )


def test_find_latest_raw_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Deve retornar o arquivo RAW modificado mais recentemente.
    """

    raw_directory = tmp_path / "raw"

    first_directory = raw_directory / "2026" / "07" / "19"
    second_directory = raw_directory / "2026" / "07" / "20"

    first_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    second_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    first_file = first_directory / "first.csv"
    second_file = second_directory / "second.csv"

    first_file.write_text(
        "teste",
        encoding="utf-8",
    )

    second_file.write_text(
        "teste",
        encoding="utf-8",
    )

    first_file.touch()

    import time

    time.sleep(0.01)
    second_file.touch()

    monkeypatch.setattr(
        transform,
        "RAW_DIR",
        raw_directory,
    )

    result = transform.find_latest_raw_file()

    assert result == second_file
from datetime import date, datetime

import pandas as pd
import pytest

import src.extract as extract


class DummySession:
    """
    Sessão fictícia utilizada para evitar chamadas reais à API.
    """

    def __enter__(self):
        return self

    def __exit__(
        self,
        exception_type,
        exception_value,
        traceback,
    ):
        return False


def test_format_ptax_date() -> None:
    """
    Deve converter YYYY-MM-DD para o formato M/D/YYYY.
    """

    result = extract.format_ptax_date(
        date(2026, 7, 13)
    )

    assert result == "7/13/2026"


def test_validate_date_range_accepts_valid_period() -> None:
    """
    Um período válido não deve gerar erro.
    """

    extract.validate_date_range(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )


def test_validate_date_range_rejects_invalid_period() -> None:
    """
    A data inicial não pode ser posterior à data final.
    """

    with pytest.raises(
        ValueError,
        match="data inicial não pode ser maior",
    ):
        extract.validate_date_range(
            start_date=date(2026, 7, 31),
            end_date=date(2026, 7, 1),
        )


def test_add_extraction_metadata() -> None:
    """
    Deve adicionar moeda e data de extração sem alterar
    o registro original.
    """

    original_records = [
        {
            "cotacaoCompra": 5.40,
            "cotacaoVenda": 5.41,
        }
    ]

    extraction_datetime = datetime(
        2026,
        7,
        20,
        10,
        30,
        45,
        123000,
    )

    result = extract.add_extraction_metadata(
        records=original_records,
        currency="USD",
        extraction_datetime=extraction_datetime,
    )

    assert len(result) == 1
    assert result[0]["moeda"] == "USD"
    assert result[0]["cotacaoCompra"] == 5.40
    assert result[0]["cotacaoVenda"] == 5.41

    assert (
        result[0]["data_extracao"]
        == "2026-07-20T10:30:45.123"
    )

    # Confirma que o objeto original não foi modificado.
    assert "moeda" not in original_records[0]
    assert "data_extracao" not in original_records[0]


def test_request_currency_data_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Deve interpretar corretamente uma resposta válida da API.
    """

    expected_records = [
        {
            "paridadeCompra": 1.0,
            "paridadeVenda": 1.0,
            "cotacaoCompra": 5.40,
            "cotacaoVenda": 5.41,
            "dataHoraCotacao": "2026-07-13 10:00:00.000",
            "tipoBoletim": "Abertura",
        }
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "value": expected_records
            }

    class FakeSession:
        def __init__(self) -> None:
            self.received_url = None
            self.received_params = None
            self.received_timeout = None

        def get(
            self,
            url,
            params,
            timeout,
        ):
            self.received_url = url
            self.received_params = params
            self.received_timeout = timeout

            return FakeResponse()

    fake_session = FakeSession()

    result = extract.request_currency_data(
        session=fake_session,
        currency="USD",
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 17),
    )

    assert result == expected_records

    assert (
        "CotacaoMoedaPeriodo"
        in fake_session.received_url
    )

    assert (
        fake_session.received_params["@moeda"]
        == "'USD'"
    )

    assert (
        fake_session.received_params["@dataInicial"]
        == "'7/13/2026'"
    )

    assert (
        fake_session.received_params[
            "@dataFinalCotacao"
        ]
        == "'7/17/2026'"
    )


def test_extract_ptax_data_creates_raw_csv(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Deve executar a extração utilizando dados simulados e
    gerar o arquivo CSV na camada RAW.
    """

    temporary_raw_directory = tmp_path / "raw"

    monkeypatch.setattr(
        extract,
        "RAW_DIR",
        temporary_raw_directory,
    )

    monkeypatch.setattr(
        extract,
        "validate_settings",
        lambda: None,
    )

    monkeypatch.setattr(
        extract,
        "create_project_directories",
        lambda: None,
    )

    monkeypatch.setattr(
        extract,
        "create_http_session",
        lambda: DummySession(),
    )

    def fake_request_currency_data(
        session,
        currency,
        start_date,
        end_date,
    ):
        return [
            {
                "paridadeCompra": 1.0,
                "paridadeVenda": 1.0,
                "cotacaoCompra": 5.40,
                "cotacaoVenda": 5.41,
                "dataHoraCotacao": (
                    "2026-07-13 10:00:00.000"
                ),
                "tipoBoletim": "Abertura",
            }
        ]

    monkeypatch.setattr(
        extract,
        "request_currency_data",
        fake_request_currency_data,
    )

    result = extract.extract_ptax_data(
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 17),
        currencies=["USD", "EUR"],
    )

    assert result.row_count == 2
    assert result.raw_file.exists()

    assert result.requested_currencies == (
        "USD",
        "EUR",
    )

    assert result.currencies_with_data == (
        "USD",
        "EUR",
    )

    dataframe = pd.read_csv(
        result.raw_file,
        encoding="utf-8-sig",
    )

    assert len(dataframe) == 2

    assert list(dataframe.columns) == (
        extract.RAW_COLUMNS
    )

    assert set(dataframe["moeda"]) == {
        "USD",
        "EUR",
    }
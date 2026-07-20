import argparse
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import (
    API_BASE_URL,
    API_MAX_ATTEMPTS,
    API_TIMEOUT_SECONDS,
    CURRENCIES,
    RAW_DIR,
    create_project_directories,
    validate_settings,
)


# Colunas retornadas pela API PTAX.
# As colunas "moeda" e "data_extracao" são metadados técnicos
# adicionados pelo nosso pipeline.
RAW_COLUMNS = [
    "moeda",
    "paridadeCompra",
    "paridadeVenda",
    "cotacaoCompra",
    "cotacaoVenda",
    "dataHoraCotacao",
    "tipoBoletim",
    "data_extracao",
]


class TransientAPIError(requests.RequestException):
    """
    Erro temporário da API que permite nova tentativa.

    Exemplos:
    - HTTP 429: excesso de requisições;
    - HTTP 500, 502, 503 e 504: falhas temporárias do servidor.
    """


@dataclass(frozen=True)
class ExtractionResult:
    """
    Resultado produzido pela etapa de extração.
    """

    raw_file: Path
    row_count: int
    requested_currencies: tuple[str, ...]
    currencies_with_data: tuple[str, ...]
    extraction_datetime: datetime


def parse_iso_date(value: str) -> date:
    """
    Converte uma data no formato YYYY-MM-DD em date.

    Args:
        value: Data recebida pela linha de comando.

    Returns:
        Objeto date.

    Raises:
        argparse.ArgumentTypeError:
            Quando o valor não estiver no formato esperado.
    """

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()

    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Data inválida: {value}. "
            "Utilize o formato YYYY-MM-DD."
        ) from error


def validate_date_range(
    start_date: date,
    end_date: date,
) -> None:
    """
    Valida o período solicitado para a extração.
    """

    if start_date > end_date:
        raise ValueError(
            "A data inicial não pode ser maior que a data final."
        )


def format_ptax_date(value: date) -> str:
    """
    Converte uma data para o formato aceito pela API PTAX.

    A API espera mês/dia/ano.

    Exemplo:
        2026-07-13 -> 7/13/2026
    """

    return f"{value.month}/{value.day}/{value.year}"


def get_ptax_endpoint() -> str:
    """
    Retorna o endpoint utilizado na consulta por período.
    """

    base_url = API_BASE_URL.rstrip("/")

    return (
        f"{base_url}/CotacaoMoedaPeriodo"
        "("
        "moeda=@moeda,"
        "dataInicial=@dataInicial,"
        "dataFinalCotacao=@dataFinalCotacao"
        ")"
    )


def create_http_session() -> requests.Session:
    """
    Cria uma sessão HTTP reutilizável.
    """

    session = requests.Session()

    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": (
                "EngenhariaDeDados-PTAX-ETL/1.0"
            ),
        }
    )

    return session


@retry(
    retry=retry_if_exception_type(
        (
            requests.Timeout,
            requests.ConnectionError,
            TransientAPIError,
        )
    ),
    stop=stop_after_attempt(API_MAX_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=2,
        max=10,
    ),
    reraise=True,
)
def request_currency_data(
    session: requests.Session,
    currency: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """
    Consulta os boletins de uma moeda em determinado período.

    A função realiza novas tentativas apenas para erros considerados
    temporários, como timeout, falha de conexão, HTTP 429 e HTTP 5xx.
    """

    endpoint = get_ptax_endpoint()

    params = {
        "@moeda": f"'{currency}'",
        "@dataInicial": (
            f"'{format_ptax_date(start_date)}'"
        ),
        "@dataFinalCotacao": (
            f"'{format_ptax_date(end_date)}'"
        ),
        "$format": "json",
    }

    response = session.get(
        url=endpoint,
        params=params,
        timeout=API_TIMEOUT_SECONDS,
    )

    if response.status_code == 429:
        raise TransientAPIError(
            "A API retornou HTTP 429: excesso de requisições."
        )

    if response.status_code >= 500:
        raise TransientAPIError(
            "A API apresentou uma falha temporária. "
            f"HTTP {response.status_code}."
        )

    response.raise_for_status()

    payload = response.json()

    records = payload.get("value")

    if records is None:
        raise ValueError(
            "A resposta da API não contém a propriedade 'value'."
        )

    if not isinstance(records, list):
        raise TypeError(
            "A propriedade 'value' da API não é uma lista."
        )

    return records


def add_extraction_metadata(
    records: list[dict[str, Any]],
    currency: str,
    extraction_datetime: datetime,
) -> list[dict[str, Any]]:
    """
    Acrescenta metadados técnicos aos registros extraídos.

    Os valores originais retornados pela API não são alterados.
    """

    enriched_records: list[dict[str, Any]] = []

    for record in records:
        enriched_record = {
            "moeda": currency,
            **record,
            "data_extracao": extraction_datetime.isoformat(
                timespec="milliseconds"
            ),
        }

        enriched_records.append(enriched_record)

    return enriched_records


def build_raw_file_path(
    start_date: date,
    end_date: date,
    extraction_datetime: datetime,
) -> Path:
    """
    Gera o caminho do arquivo CSV bruto.

    Estrutura:
        data/raw/ano/mes/dia/arquivo.csv
    """

    destination_directory = (
        RAW_DIR
        / extraction_datetime.strftime("%Y")
        / extraction_datetime.strftime("%m")
        / extraction_datetime.strftime("%d")
    )

    destination_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        "ptax_raw_"
        f"{start_date:%Y%m%d}_"
        f"{end_date:%Y%m%d}_"
        f"{extraction_datetime:%Y%m%d_%H%M%S}.csv"
    )

    return destination_directory / filename


def save_raw_csv(
    records: list[dict[str, Any]],
    file_path: Path,
) -> None:
    """
    Salva os registros extraídos em CSV.
    """

    dataframe = pd.DataFrame.from_records(records)

    dataframe = dataframe.reindex(
        columns=RAW_COLUMNS
    )

    dataframe.to_csv(
        file_path,
        index=False,
        encoding="utf-8-sig",
    )


def extract_ptax_data(
    start_date: date,
    end_date: date,
    currencies: Sequence[str] | None = None,
) -> ExtractionResult:
    """
    Executa a extração das cotações PTAX.

    Args:
        start_date:
            Data inicial do período.

        end_date:
            Data final do período.

        currencies:
            Lista opcional de moedas.
            Quando não informada, utiliza CURRENCIES do .env.

    Returns:
        Informações sobre o arquivo CSV gerado.
    """

    validate_settings()
    create_project_directories()
    validate_date_range(start_date, end_date)

    selected_currencies = tuple(
        currency.strip().upper()
        for currency in (currencies or CURRENCIES)
        if currency.strip()
    )

    if not selected_currencies:
        raise ValueError(
            "Nenhuma moeda foi informada para extração."
        )

    extraction_datetime = datetime.now()

    all_records: list[dict[str, Any]] = []
    currencies_with_data: list[str] = []

    with create_http_session() as session:
        for currency in selected_currencies:
            print(f"Extraindo moeda {currency}...")

            records = request_currency_data(
                session=session,
                currency=currency,
                start_date=start_date,
                end_date=end_date,
            )

            print(
                f"  {currency}: {len(records)} registros encontrados."
            )

            if not records:
                continue

            currencies_with_data.append(currency)

            enriched_records = add_extraction_metadata(
                records=records,
                currency=currency,
                extraction_datetime=extraction_datetime,
            )

            all_records.extend(enriched_records)

    if not all_records:
        raise RuntimeError(
            "A API não retornou registros para o período "
            "e as moedas solicitadas."
        )

    raw_file = build_raw_file_path(
        start_date=start_date,
        end_date=end_date,
        extraction_datetime=extraction_datetime,
    )

    save_raw_csv(
        records=all_records,
        file_path=raw_file,
    )

    return ExtractionResult(
        raw_file=raw_file,
        row_count=len(all_records),
        requested_currencies=selected_currencies,
        currencies_with_data=tuple(currencies_with_data),
        extraction_datetime=extraction_datetime,
    )


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Configura os argumentos aceitos pelo módulo.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Extrai cotações da API PTAX do Banco Central "
            "e salva os dados em CSV na camada RAW."
        )
    )

    parser.add_argument(
        "--start-date",
        required=True,
        type=parse_iso_date,
        help="Data inicial no formato YYYY-MM-DD.",
    )

    parser.add_argument(
        "--end-date",
        required=True,
        type=parse_iso_date,
        help="Data final no formato YYYY-MM-DD.",
    )

    parser.add_argument(
        "--currencies",
        nargs="+",
        required=False,
        help=(
            "Moedas que serão extraídas. "
            "Exemplo: --currencies USD EUR GBP"
        ),
    )

    return parser


def main() -> None:
    """
    Ponto de entrada para execução pelo terminal.
    """

    parser = create_argument_parser()
    arguments = parser.parse_args()

    try:
        result = extract_ptax_data(
            start_date=arguments.start_date,
            end_date=arguments.end_date,
            currencies=arguments.currencies,
        )

        print()
        print("Extração concluída com sucesso!")
        print(f"Arquivo RAW: {result.raw_file}")
        print(f"Total de registros: {result.row_count}")
        print(
            "Moedas solicitadas: "
            + ", ".join(result.requested_currencies)
        )
        print(
            "Moedas com dados: "
            + ", ".join(result.currencies_with_data)
        )

    except Exception as error:
        print()
        print("Falha durante a extração.")
        print(f"Tipo: {type(error).__name__}")
        print(f"Detalhes: {error}")

        raise


if __name__ == "__main__":
    main()
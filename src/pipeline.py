import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime

from config.settings import (
    CURRENCIES,
    create_project_directories,
    validate_settings,
)
from src.extract import (
    ExtractionResult,
    extract_ptax_data,
    parse_iso_date,
)
from src.load import (
    LoadResult,
    load_processed_data,
)
from src.logger import get_logger
from src.transform import (
    TransformationResult,
    transform_ptax_data,
)


PIPELINE_NAME = "pipeline_ptax"

logger = get_logger(PIPELINE_NAME)


@dataclass(frozen=True)
class PipelineResult:
    """
    Resultado consolidado da execução completa do pipeline.
    """

    start_date: date
    end_date: date
    started_at: datetime
    finished_at: datetime
    extraction: ExtractionResult
    transformation: TransformationResult
    load: LoadResult

    @property
    def duration_seconds(self) -> float:
        """
        Retorna a duração total do pipeline em segundos.
        """

        return (
            self.finished_at - self.started_at
        ).total_seconds()


def validate_pipeline_period(
    start_date: date,
    end_date: date,
) -> None:
    """
    Valida o período solicitado para o pipeline.
    """

    if start_date > end_date:
        raise ValueError(
            "A data inicial não pode ser maior que a data final."
        )

    if end_date > date.today():
        raise ValueError(
            "A data final não pode estar no futuro."
        )


def run_pipeline(
    start_date: date,
    end_date: date,
    currencies: list[str] | None = None,
) -> PipelineResult:
    """
    Executa o pipeline completo de cotações PTAX.

    Etapas:
        1. Extração;
        2. Transformação;
        3. Carga no SQL Server.
    """

    validate_settings()
    create_project_directories()

    validate_pipeline_period(
        start_date=start_date,
        end_date=end_date,
    )

    selected_currencies = [
        currency.strip().upper()
        for currency in (
            currencies or CURRENCIES
        )
        if currency.strip()
    ]

    started_at = datetime.now()

    logger.info("=" * 70)
    logger.info("Pipeline iniciado")
    logger.info(
        "Período solicitado: %s até %s",
        start_date,
        end_date,
    )
    logger.info(
        "Moedas selecionadas: %s",
        ", ".join(selected_currencies),
    )

    try:
        # ====================================================
        # EXTRAÇÃO
        # ====================================================

        logger.info("[1/3] Iniciando extração")

        extraction_result = extract_ptax_data(
            start_date=start_date,
            end_date=end_date,
            currencies=selected_currencies,
        )

        logger.info(
            "Extração concluída: %s registros",
            extraction_result.row_count,
        )

        logger.info(
            "Arquivo RAW gerado: %s",
            extraction_result.raw_file,
        )

        # ====================================================
        # TRANSFORMAÇÃO
        # ====================================================

        logger.info("[2/3] Iniciando transformação")

        transformation_result = transform_ptax_data(
            raw_file=extraction_result.raw_file
        )

        logger.info(
            "Transformação concluída: "
            "%s válidos, %s rejeitados e %s duplicados",
            transformation_result.processed_row_count,
            transformation_result.rejected_row_count,
            transformation_result.duplicate_row_count,
        )

        logger.info(
            "Arquivo processado gerado: %s",
            transformation_result.processed_file,
        )

        if transformation_result.rejected_file:
            logger.warning(
                "Arquivo de rejeitados gerado: %s",
                transformation_result.rejected_file,
            )

        # ====================================================
        # CARGA
        # ====================================================

        logger.info("[3/3] Iniciando carga")

        load_result = load_processed_data(
            processed_file=(
                transformation_result.processed_file
            )
        )

        logger.info(
            "Carga concluída: execução %s",
            load_result.id_execucao,
        )

        logger.info(
            "Carga incremental: "
            "%s inseridos e %s atualizados",
            load_result.inserted_row_count,
            load_result.updated_row_count,
        )

        finished_at = datetime.now()

        pipeline_result = PipelineResult(
            start_date=start_date,
            end_date=end_date,
            started_at=started_at,
            finished_at=finished_at,
            extraction=extraction_result,
            transformation=transformation_result,
            load=load_result,
        )

        logger.info(
            "Pipeline concluído com sucesso em %.2f segundos",
            pipeline_result.duration_seconds,
        )

        logger.info(
            "Resumo: extraídos=%s, transformados=%s, "
            "rejeitados=%s, inseridos=%s, atualizados=%s",
            extraction_result.row_count,
            transformation_result.processed_row_count,
            transformation_result.rejected_row_count,
            load_result.inserted_row_count,
            load_result.updated_row_count,
        )

        logger.info("=" * 70)

        return pipeline_result

    except Exception:
        finished_at = datetime.now()

        duration = (
            finished_at - started_at
        ).total_seconds()

        logger.exception(
            "Pipeline encerrado com erro após %.2f segundos",
            duration,
        )

        logger.info("=" * 70)

        raise


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Define os argumentos aceitos pelo pipeline.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Executa o pipeline completo de cotações PTAX: "
            "extração, transformação e carga no SQL Server."
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
            "Moedas que serão processadas. "
            "Exemplo: --currencies USD EUR GBP"
        ),
    )

    return parser


def main() -> None:
    """
    Ponto de entrada da execução pelo terminal.
    """

    parser = create_argument_parser()
    arguments = parser.parse_args()

    try:
        run_pipeline(
            start_date=arguments.start_date,
            end_date=arguments.end_date,
            currencies=arguments.currencies,
        )

    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
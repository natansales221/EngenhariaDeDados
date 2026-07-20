import os
from pathlib import Path
from dotenv import load_dotenv


# DIRETÓRIOS DO PROJETO

# Localiza a pasta raiz
BASE_DIR = Path(__file__).resolve().parents[1]

# Variáveis do arquivo .env
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


# CONFIGURAÇÕES DE LOG

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).strip().upper()

LOG_MAX_BYTES = int(
    os.getenv(
        "LOG_MAX_BYTES",
        "5000000",
    )
)

LOG_BACKUP_COUNT = int(
    os.getenv(
        "LOG_BACKUP_COUNT",
        "5",
    )
)


# CONFIGURAÇÕES DA API

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata",
)

CURRENCIES = [
    currency.strip().upper()
    for currency in os.getenv("CURRENCIES", "USD,EUR,GBP").split(",")
    if currency.strip()
]

API_TIMEOUT_SECONDS = int(
    os.getenv("API_TIMEOUT_SECONDS", "30")
)

API_MAX_ATTEMPTS = int(
    os.getenv("API_MAX_ATTEMPTS", "3")
)

# CONFIGURAÇÕES DO SQL

DB_SERVER = os.getenv("DB_SERVER", r"(localdb)\MSSQLLocalDB")
DB_DATABASE = os.getenv("DB_DATABASE", "EngenhariaDeDados")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_AUTH = os.getenv("DB_AUTH", "windows").strip().lower()

DB_USERNAME = os.getenv("DB_USERNAME", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DB_TRUST_SERVER_CERTIFICATE = (
    os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes").strip().lower()
    in {"yes", "true", "1"}
)

# DIRETÓRIOS

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REJECTED_DIR = BASE_DIR / "data" / "rejected"
LOG_DIR = BASE_DIR / "logs"


def create_project_directories() -> None:
    directories = [
        RAW_DIR,
        PROCESSED_DIR,
        REJECTED_DIR,
        LOG_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def validate_settings() -> None:

    required_settings = {
        "API_BASE_URL": API_BASE_URL,
        "DB_SERVER": DB_SERVER,
        "DB_DATABASE": DB_DATABASE,
        "DB_DRIVER": DB_DRIVER,
        "DB_AUTH": DB_AUTH,
    }

    missing_settings = [
        setting_name
        for setting_name, setting_value in required_settings.items()
        if not setting_value
    ]

    if missing_settings:
        missing_text = ", ".join(missing_settings)

        raise ValueError(
            f"Configurações obrigatórias não preenchidas: {missing_text}"
        )

    if DB_AUTH not in {"windows", "sql"}:
        raise ValueError(
            "DB_AUTH deve possuir o valor 'windows' ou 'sql'."
        )

    if DB_AUTH == "sql" and not DB_USERNAME:
        raise ValueError(
            "DB_USERNAME é obrigatório quando DB_AUTH=sql."
        )

    if DB_AUTH == "sql" and not DB_PASSWORD:
        raise ValueError(
            "DB_PASSWORD é obrigatório quando DB_AUTH=sql."
        )
    
    if API_TIMEOUT_SECONDS <= 0:
            raise ValueError(
            "API_TIMEOUT_SECONDS deve ser maior que zero."
        )

    if API_MAX_ATTEMPTS <= 0:
        raise ValueError(
            "API_MAX_ATTEMPTS deve ser maior que zero."
        )

    invalid_currencies = [
        currency
        for currency in CURRENCIES
        if len(currency) != 3 or not currency.isalpha()
    ]

    if invalid_currencies:
        raise ValueError(
            "Códigos de moeda inválidos: "
            + ", ".join(invalid_currencies)
        )

    valid_log_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if LOG_LEVEL not in valid_log_levels:
        raise ValueError(
            "LOG_LEVEL inválido. Valores aceitos: "
            + ", ".join(sorted(valid_log_levels))
        )

    if LOG_MAX_BYTES <= 0:
        raise ValueError(
            "LOG_MAX_BYTES deve ser maior que zero."
        )

    if LOG_BACKUP_COUNT < 0:
        raise ValueError(
            "LOG_BACKUP_COUNT não pode ser negativo."
        )
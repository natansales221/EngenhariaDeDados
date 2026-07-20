SET NOCOUNT ON;
SET XACT_ABORT ON;
GO


-- CONTROLE DAS EXECUÇÕES

IF OBJECT_ID(N'etl.execucao_pipeline', N'U') IS NULL
BEGIN
    CREATE TABLE etl.execucao_pipeline
    (
        id_execucao              BIGINT IDENTITY(1,1) NOT NULL,
        nome_pipeline            NVARCHAR(100) NOT NULL,

        data_inicio              DATETIME2(3) NOT NULL
            CONSTRAINT DF_execucao_data_inicio
            DEFAULT SYSDATETIME(),

        data_fim                 DATETIME2(3) NULL,

        status                   NVARCHAR(20) NOT NULL,

        data_inicio_referencia   DATE NULL,
        data_fim_referencia      DATE NULL,

        quantidade_extraida      INT NOT NULL
            CONSTRAINT DF_execucao_qtd_extraida
            DEFAULT 0,

        quantidade_transformada  INT NOT NULL
            CONSTRAINT DF_execucao_qtd_transformada
            DEFAULT 0,

        quantidade_rejeitada     INT NOT NULL
            CONSTRAINT DF_execucao_qtd_rejeitada
            DEFAULT 0,

        quantidade_inserida      INT NOT NULL
            CONSTRAINT DF_execucao_qtd_inserida
            DEFAULT 0,

        quantidade_atualizada    INT NOT NULL
            CONSTRAINT DF_execucao_qtd_atualizada
            DEFAULT 0,

        arquivo_raw              NVARCHAR(500) NULL,
        arquivo_processado       NVARCHAR(500) NULL,
        mensagem_erro            NVARCHAR(MAX) NULL,

        CONSTRAINT PK_execucao_pipeline
            PRIMARY KEY CLUSTERED (id_execucao),

        CONSTRAINT CK_execucao_pipeline_status
            CHECK
            (
                status IN
                (
                    N'INICIADO',
                    N'SUCESSO',
                    N'ERRO'
                )
            )
    );
END;
GO


-- STAGING

IF OBJECT_ID(N'etl.stg_cotacao_moeda', N'U') IS NULL
BEGIN
    CREATE TABLE etl.stg_cotacao_moeda
    (
        id_staging          BIGINT IDENTITY(1,1) NOT NULL,
        id_execucao         BIGINT NOT NULL,

        moeda               CHAR(3) NOT NULL,

        paridade_compra     DECIMAL(19,8) NOT NULL,
        paridade_venda      DECIMAL(19,8) NOT NULL,
        cotacao_compra      DECIMAL(19,8) NOT NULL,
        cotacao_venda       DECIMAL(19,8) NOT NULL,

        data_hora_cotacao   DATETIME2(0) NOT NULL,
        tipo_boletim        NVARCHAR(50) NOT NULL,
        data_referencia     DATE NOT NULL,

        data_extracao       DATETIME2(3) NOT NULL,
        arquivo_origem      NVARCHAR(500) NOT NULL,

        data_carga          DATETIME2(3) NOT NULL
            CONSTRAINT DF_stg_cotacao_data_carga
            DEFAULT SYSDATETIME(),

        CONSTRAINT PK_stg_cotacao_moeda
            PRIMARY KEY CLUSTERED (id_staging),

        CONSTRAINT FK_stg_cotacao_execucao
            FOREIGN KEY (id_execucao)
            REFERENCES etl.execucao_pipeline (id_execucao)
    );
END;
GO


IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE
        name = N'IX_stg_cotacao_id_execucao'
        AND object_id = OBJECT_ID(N'etl.stg_cotacao_moeda')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_stg_cotacao_id_execucao
        ON etl.stg_cotacao_moeda (id_execucao);
END;
GO


-- TABELA FINAL

IF OBJECT_ID(N'dw.fato_cotacao_moeda', N'U') IS NULL
BEGIN
    CREATE TABLE dw.fato_cotacao_moeda
    (
        id_cotacao          BIGINT IDENTITY(1,1) NOT NULL,

        moeda               CHAR(3) NOT NULL,

        paridade_compra     DECIMAL(19,8) NOT NULL,
        paridade_venda      DECIMAL(19,8) NOT NULL,
        cotacao_compra      DECIMAL(19,8) NOT NULL,
        cotacao_venda       DECIMAL(19,8) NOT NULL,

        data_hora_cotacao   DATETIME2(0) NOT NULL,
        tipo_boletim        NVARCHAR(50) NOT NULL,
        data_referencia     DATE NOT NULL,

        data_extracao       DATETIME2(3) NOT NULL,
        arquivo_origem      NVARCHAR(500) NOT NULL,

        data_insercao       DATETIME2(3) NOT NULL
            CONSTRAINT DF_fato_cotacao_data_insercao
            DEFAULT SYSDATETIME(),

        data_atualizacao    DATETIME2(3) NULL,

        CONSTRAINT PK_fato_cotacao_moeda
            PRIMARY KEY CLUSTERED (id_cotacao),

        CONSTRAINT UQ_fato_cotacao_chave_negocio
            UNIQUE
            (
                moeda,
                data_hora_cotacao,
                tipo_boletim
            )
    );
END;
GO


IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE
        name = N'IX_fato_cotacao_moeda_data'
        AND object_id = OBJECT_ID(N'dw.fato_cotacao_moeda')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_fato_cotacao_moeda_data
        ON dw.fato_cotacao_moeda
        (
            moeda,
            data_referencia
        )
        INCLUDE
        (
            cotacao_compra,
            cotacao_venda,
            tipo_boletim
        );
END;
GO
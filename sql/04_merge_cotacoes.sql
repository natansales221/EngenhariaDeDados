SET NOCOUNT ON;
SET XACT_ABORT ON;
GO


CREATE OR ALTER PROCEDURE etl.usp_carregar_cotacao_moeda
    @id_execucao BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM etl.execucao_pipeline
        WHERE id_execucao = @id_execucao
    )
    BEGIN
        THROW 50001, 'Execução do pipeline não encontrada.', 1;
    END;

    DECLARE
        @quantidade_inserida INT = 0,
        @quantidade_atualizada INT = 0;


    -- ========================================================
    -- ATUALIZA REGISTROS QUE JÁ EXISTEM E FORAM ALTERADOS
    -- ========================================================

    UPDATE destino
    SET
        destino.paridade_compra = origem.paridade_compra,
        destino.paridade_venda = origem.paridade_venda,
        destino.cotacao_compra = origem.cotacao_compra,
        destino.cotacao_venda = origem.cotacao_venda,
        destino.data_referencia = origem.data_referencia,
        destino.data_extracao = origem.data_extracao,
        destino.arquivo_origem = origem.arquivo_origem,
        destino.data_atualizacao = SYSDATETIME()

    FROM dw.fato_cotacao_moeda AS destino

    INNER JOIN etl.stg_cotacao_moeda AS origem
        ON origem.moeda = destino.moeda
        AND origem.data_hora_cotacao = destino.data_hora_cotacao
        AND origem.tipo_boletim = destino.tipo_boletim

    WHERE origem.id_execucao = @id_execucao

    AND
    (
           destino.paridade_compra <> origem.paridade_compra
        OR destino.paridade_venda <> origem.paridade_venda
        OR destino.cotacao_compra <> origem.cotacao_compra
        OR destino.cotacao_venda <> origem.cotacao_venda
        OR destino.data_referencia <> origem.data_referencia
    );

    SET @quantidade_atualizada = @@ROWCOUNT;


    -- ========================================================
    -- INSERE REGISTROS QUE AINDA NÃO EXISTEM
    -- ========================================================

    INSERT INTO dw.fato_cotacao_moeda
    (
        moeda,
        paridade_compra,
        paridade_venda,
        cotacao_compra,
        cotacao_venda,
        data_hora_cotacao,
        tipo_boletim,
        data_referencia,
        data_extracao,
        arquivo_origem
    )
    SELECT
        origem.moeda,
        origem.paridade_compra,
        origem.paridade_venda,
        origem.cotacao_compra,
        origem.cotacao_venda,
        origem.data_hora_cotacao,
        origem.tipo_boletim,
        origem.data_referencia,
        origem.data_extracao,
        origem.arquivo_origem

    FROM etl.stg_cotacao_moeda AS origem

    WHERE origem.id_execucao = @id_execucao

    AND NOT EXISTS
    (
        SELECT 1
        FROM dw.fato_cotacao_moeda AS destino

        WHERE destino.moeda = origem.moeda
        AND destino.data_hora_cotacao = origem.data_hora_cotacao
        AND destino.tipo_boletim = origem.tipo_boletim
    );

    SET @quantidade_inserida = @@ROWCOUNT;


    -- ========================================================
    -- LIMPA A STAGING DA EXECUÇÃO
    -- ========================================================

    DELETE FROM etl.stg_cotacao_moeda
    WHERE id_execucao = @id_execucao;


    -- ========================================================
    -- RETORNA AS MÉTRICAS PARA O PYTHON
    -- ========================================================

    SELECT
        @quantidade_inserida AS quantidade_inserida,
        @quantidade_atualizada AS quantidade_atualizada;
END;
GO
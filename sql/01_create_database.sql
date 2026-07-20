USE master;
GO

IF DB_ID('EngenhariaDeDados') IS NULL
BEGIN
    CREATE DATABASE EngenhariaDeDados;
    PRINT 'Banco EngenhariaDeDados criado com sucesso.';
END
ELSE
BEGIN
    PRINT 'O banco EngenhariaDeDados já existe.';
END;
GO
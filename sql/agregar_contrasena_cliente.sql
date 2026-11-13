/* ============================================================
   Portal de clientes
   ------------------------------------------------------------
   Agrega UNA sola columna a la tabla CLIENTE para que el cliente
   pueda iniciar sesión. No se modifica ninguna otra tabla.

   Ejecutar una sola vez sobre la base VetPepePepito.
   ============================================================ */

USE [VetPepePepito];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.CLIENTE')
      AND name = 'Contrasena'
)
BEGIN
    ALTER TABLE [dbo].[CLIENTE]
        ADD [Contrasena] [nvarchar](100) NULL;
END
GO

/* Los clientes que ya existían quedan con Contrasena = NULL.
   La primera vez que entren, el portal les pedirá crear su
   contraseña (se valida con su cédula). */
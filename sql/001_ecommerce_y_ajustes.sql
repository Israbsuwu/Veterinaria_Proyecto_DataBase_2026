/* ============================================================
   VetPepePepito - Migración 001
   Arquitectura dual: ERP interno + E-commerce
   ------------------------------------------------------------
   Cambios:
   1. CLIENTE.IdUsuario  -> FK nullable a USUARIO (solicitado)
   2. PRODUCTO.IdConcepto -> completa la herencia de CONCEPTO_FACTURABLE
   3. PAGO.IdSesion nullable -> permite cobros online sin sesión de caja
   4. VENTA.Origen ('POS' | 'Web') -> distingue ventas internas y e-commerce
   5. Roles Cajero / Cliente Web + permisos base
   6. Índices de rendimiento + vistas de stock
   ------------------------------------------------------------
   El script es idempotente: puede ejecutarse varias veces.
   ============================================================ */
USE VetPepePepito;
GO
SET XACT_ABORT ON;
BEGIN TRANSACTION;
GO

/* 1. ROLES -------------------------------------------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.ROL WHERE NombreRol = 'Cajero')
    INSERT INTO dbo.ROL (NombreRol, Descripcion)
    VALUES ('Cajero', 'Punto de venta, caja e inventario');

IF NOT EXISTS (SELECT 1 FROM dbo.ROL WHERE NombreRol = 'Cliente Web')
    INSERT INTO dbo.ROL (NombreRol, Descripcion)
    VALUES ('Cliente Web', 'Acceso al portal e-commerce de clientes');
GO

/* 2. PERMISOS BASE ------------------------------------------ */
INSERT INTO dbo.PERMISO (Codigo, Descripcion)
SELECT v.Codigo, v.Descripcion
FROM (VALUES
    ('citas.ver',              'Ver agenda de reservas y citas'),
    ('citas.gestionar',        'Crear, confirmar y cancelar citas'),
    ('triaje.gestionar',       'Gestionar atenciones y triaje'),
    ('expedientes.ver',        'Consultar expedientes clínicos'),
    ('expedientes.editar',     'Registrar consultas, recetas y preventivos'),
    ('clientes.gestionar',     'Gestionar clientes y mascotas'),
    ('inventario.ver',         'Consultar inventario y lotes'),
    ('inventario.gestionar',   'Registrar entradas, salidas y ajustes'),
    ('compras.gestionar',      'Registrar compras a proveedores'),
    ('caja.abrir',             'Abrir sesión de caja'),
    ('caja.cerrar',            'Cerrar sesión de caja'),
    ('ventas.crear',           'Registrar ventas y cobros'),
    ('ventas.anular',          'Anular ventas'),
    ('catalogo.gestionar',     'Gestionar productos, servicios y precios'),
    ('reportes.ver',           'Consultar reportes y tablero'),
    ('tienda.comprar',         'Comprar en la tienda en línea'),
    ('tienda.reservar',        'Solicitar citas en línea')
) AS v (Codigo, Descripcion)
WHERE NOT EXISTS (SELECT 1 FROM dbo.PERMISO p WHERE p.Codigo = v.Codigo);
GO

/* Administrador: todos los permisos */
INSERT INTO dbo.ROL_PERMISO (IdRol, IdPermiso)
SELECT r.IdRol, p.IdPermiso
FROM dbo.ROL r CROSS JOIN dbo.PERMISO p
WHERE r.NombreRol = 'Administrador'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.ROL_PERMISO rp
      WHERE rp.IdRol = r.IdRol AND rp.IdPermiso = p.IdPermiso);

/* Veterinario: flujo clínico */
INSERT INTO dbo.ROL_PERMISO (IdRol, IdPermiso)
SELECT r.IdRol, p.IdPermiso
FROM dbo.ROL r CROSS JOIN dbo.PERMISO p
WHERE r.NombreRol = 'Veterinario'
  AND p.Codigo IN ('citas.ver','citas.gestionar','triaje.gestionar',
                   'expedientes.ver','expedientes.editar','clientes.gestionar',
                   'inventario.ver','reportes.ver')
  AND NOT EXISTS (
      SELECT 1 FROM dbo.ROL_PERMISO rp
      WHERE rp.IdRol = r.IdRol AND rp.IdPermiso = p.IdPermiso);

/* Cajero: caja, ventas e inventario */
INSERT INTO dbo.ROL_PERMISO (IdRol, IdPermiso)
SELECT r.IdRol, p.IdPermiso
FROM dbo.ROL r CROSS JOIN dbo.PERMISO p
WHERE r.NombreRol = 'Cajero'
  AND p.Codigo IN ('citas.ver','clientes.gestionar','inventario.ver',
                   'inventario.gestionar','compras.gestionar','caja.abrir',
                   'caja.cerrar','ventas.crear','ventas.anular','reportes.ver')
  AND NOT EXISTS (
      SELECT 1 FROM dbo.ROL_PERMISO rp
      WHERE rp.IdRol = r.IdRol AND rp.IdPermiso = p.IdPermiso);

/* Cliente Web: tienda */
INSERT INTO dbo.ROL_PERMISO (IdRol, IdPermiso)
SELECT r.IdRol, p.IdPermiso
FROM dbo.ROL r CROSS JOIN dbo.PERMISO p
WHERE r.NombreRol = 'Cliente Web'
  AND p.Codigo IN ('tienda.comprar','tienda.reservar')
  AND NOT EXISTS (
      SELECT 1 FROM dbo.ROL_PERMISO rp
      WHERE rp.IdRol = r.IdRol AND rp.IdPermiso = p.IdPermiso);
GO

/* 3. CLIENTE.IdUsuario (solicitado) ------------------------- */
IF COL_LENGTH('dbo.CLIENTE', 'IdUsuario') IS NULL
    ALTER TABLE dbo.CLIENTE ADD IdUsuario INT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CLIENTE_USUARIO')
    ALTER TABLE dbo.CLIENTE
        ADD CONSTRAINT FK_CLIENTE_USUARIO
        FOREIGN KEY (IdUsuario) REFERENCES dbo.USUARIO (IdUsuario);
GO

/* Un usuario de e-commerce solo puede representar a un cliente */
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'UX_CLIENTE_IdUsuario'
                 AND object_id = OBJECT_ID('dbo.CLIENTE'))
    CREATE UNIQUE INDEX UX_CLIENTE_IdUsuario
        ON dbo.CLIENTE (IdUsuario)
        WHERE IdUsuario IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_CLIENTE_Correo'
                 AND object_id = OBJECT_ID('dbo.CLIENTE'))
    CREATE INDEX IX_CLIENTE_Correo ON dbo.CLIENTE (Correo);
GO

/* 4. PRODUCTO.IdConcepto (herencia Concepto Facturable) ----- */
IF COL_LENGTH('dbo.PRODUCTO', 'IdConcepto') IS NULL
    ALTER TABLE dbo.PRODUCTO ADD IdConcepto INT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_PRODUCTO_CONCEPTO')
    ALTER TABLE dbo.PRODUCTO
        ADD CONSTRAINT FK_PRODUCTO_CONCEPTO
        FOREIGN KEY (IdConcepto) REFERENCES dbo.CONCEPTO_FACTURABLE (IdConcepto);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'UX_PRODUCTO_IdConcepto'
                 AND object_id = OBJECT_ID('dbo.PRODUCTO'))
    CREATE UNIQUE INDEX UX_PRODUCTO_IdConcepto
        ON dbo.PRODUCTO (IdConcepto)
        WHERE IdConcepto IS NOT NULL;
GO

/* Vincular productos existentes con su concepto de venta por nombre */
UPDATE p
SET p.IdConcepto = c.IdConcepto
FROM dbo.PRODUCTO p
INNER JOIN dbo.CONCEPTO_FACTURABLE c
    ON c.Nombre = p.Nombre AND c.TipoConcepto = 'Producto'
WHERE p.IdConcepto IS NULL
  AND NOT EXISTS (SELECT 1 FROM dbo.PRODUCTO x WHERE x.IdConcepto = c.IdConcepto);
GO

/* 5. PAGO.IdSesion nullable (cobros e-commerce) ------------- */
DECLARE @fkPagoSesion SYSNAME;
SELECT @fkPagoSesion = fk.name
FROM sys.foreign_keys fk
WHERE fk.parent_object_id = OBJECT_ID('dbo.PAGO')
  AND fk.referenced_object_id = OBJECT_ID('dbo.SESION_CAJA');

IF @fkPagoSesion IS NOT NULL
BEGIN
    DECLARE @sqlDropFk NVARCHAR(MAX) =
        N'ALTER TABLE dbo.PAGO DROP CONSTRAINT ' + QUOTENAME(@fkPagoSesion);
    EXEC sp_executesql @sqlDropFk;
END

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.PAGO')
             AND name = 'IdSesion' AND is_nullable = 0)
    ALTER TABLE dbo.PAGO ALTER COLUMN IdSesion INT NULL;

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_PAGO_SESION')
    ALTER TABLE dbo.PAGO
        ADD CONSTRAINT FK_PAGO_SESION
        FOREIGN KEY (IdSesion) REFERENCES dbo.SESION_CAJA (IdSesion);
GO

/* 6. VENTA.Origen ------------------------------------------ */
IF COL_LENGTH('dbo.VENTA', 'Origen') IS NULL
    ALTER TABLE dbo.VENTA
        ADD Origen NVARCHAR(20) NOT NULL
            CONSTRAINT DF_VENTA_Origen DEFAULT 'POS';
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_VENTA_Origen')
    ALTER TABLE dbo.VENTA
        ADD CONSTRAINT CK_VENTA_Origen CHECK (Origen IN ('POS', 'Web'));
GO

/* 7. ÍNDICES DE RENDIMIENTO -------------------------------- */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RESERVA_FechaIni' AND object_id = OBJECT_ID('dbo.RESERVA'))
    CREATE INDEX IX_RESERVA_FechaIni ON dbo.RESERVA (FechaIni, Estado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ATENCION_Estado' AND object_id = OBJECT_ID('dbo.ATENCION'))
    CREATE INDEX IX_ATENCION_Estado ON dbo.ATENCION (Estado, FechaLleg);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LOTE_Vencimiento' AND object_id = OBJECT_ID('dbo.LOTE'))
    CREATE INDEX IX_LOTE_Vencimiento ON dbo.LOTE (FechaVenc, Estado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MOV_Lote' AND object_id = OBJECT_ID('dbo.MOVIMIENTO_INVENTARIO'))
    CREATE INDEX IX_MOV_Lote ON dbo.MOVIMIENTO_INVENTARIO (IdLote, FechaMov);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_VENTA_Fecha' AND object_id = OBJECT_ID('dbo.VENTA'))
    CREATE INDEX IX_VENTA_Fecha ON dbo.VENTA (FechaVenta, Estado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_VENTA_Cliente' AND object_id = OBJECT_ID('dbo.VENTA'))
    CREATE INDEX IX_VENTA_Cliente ON dbo.VENTA (IdCliente);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_PAGO_Sesion' AND object_id = OBJECT_ID('dbo.PAGO'))
    CREATE INDEX IX_PAGO_Sesion ON dbo.PAGO (IdSesion);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_NOTIF_Estado' AND object_id = OBJECT_ID('dbo.NOTIFICACION'))
    CREATE INDEX IX_NOTIF_Estado ON dbo.NOTIFICACION (Estado, FechaProg);
GO

/* 8. VISTAS DE APOYO --------------------------------------- */
CREATE OR ALTER VIEW dbo.VW_STOCK_PRODUCTO
AS
SELECT
    p.IdProducto,
    p.Nombre,
    p.UnidadMedida,
    p.ControlVenc,
    p.StockMin,
    p.IdCategoria,
    c.Nombre AS Categoria,
    p.IdConcepto,
    ISNULL(SUM(CASE m.TipoMov
                    WHEN 'Entrada' THEN m.Cantidad
                    WHEN 'Salida'  THEN -m.Cantidad
                    WHEN 'Ajuste'  THEN m.Cantidad
                    ELSE 0 END), 0) AS Stock
FROM dbo.PRODUCTO p
LEFT JOIN dbo.CATEGORIA c ON c.IdCategoria = p.IdCategoria
LEFT JOIN dbo.LOTE l ON l.IdProducto = p.IdProducto
LEFT JOIN dbo.MOVIMIENTO_INVENTARIO m ON m.IdLote = l.IdLote
GROUP BY p.IdProducto, p.Nombre, p.UnidadMedida, p.ControlVenc,
         p.StockMin, p.IdCategoria, c.Nombre, p.IdConcepto;
GO

CREATE OR ALTER VIEW dbo.VW_LOTE_STOCK
AS
SELECT
    l.IdLote,
    l.CodigoLote,
    l.FechaVenc,
    l.FechaIng,
    l.Estado,
    l.IdProducto,
    p.Nombre AS Producto,
    p.ControlVenc,
    ISNULL(SUM(CASE m.TipoMov
                    WHEN 'Entrada' THEN m.Cantidad
                    WHEN 'Salida'  THEN -m.Cantidad
                    WHEN 'Ajuste'  THEN m.Cantidad
                    ELSE 0 END), 0) AS StockLote
FROM dbo.LOTE l
INNER JOIN dbo.PRODUCTO p ON p.IdProducto = l.IdProducto
LEFT JOIN dbo.MOVIMIENTO_INVENTARIO m ON m.IdLote = l.IdLote
GROUP BY l.IdLote, l.CodigoLote, l.FechaVenc, l.FechaIng, l.Estado,
         l.IdProducto, p.Nombre, p.ControlVenc;
GO

/* 9. DATOS DE DEMOSTRACIÓN -------------------------------- */
DECLARE @idRolCliente INT = (SELECT IdRol FROM dbo.ROL WHERE NombreRol = 'Cliente Web');
DECLARE @idRolCajero  INT = (SELECT IdRol FROM dbo.ROL WHERE NombreRol = 'Cajero');

IF NOT EXISTS (SELECT 1 FROM dbo.USUARIO WHERE Correo = 'cliente@pepe.com')
    INSERT INTO dbo.USUARIO (Nombre, Apellido, Telefono, Correo, Contrasena, Estado, IdRol)
    VALUES ('Quevedo', 'Garay', '8123-4567', 'cliente@pepe.com', '123456', 'Activo', @idRolCliente);

IF NOT EXISTS (SELECT 1 FROM dbo.USUARIO WHERE Correo = 'caja@pepe.com')
    INSERT INTO dbo.USUARIO (Nombre, Apellido, Telefono, Correo, Contrasena, Estado, IdRol)
    VALUES ('Caja', 'Principal', '5555-5555', 'caja@pepe.com', '123456', 'Activo', @idRolCajero);

/* Enlazar el cliente de prueba con su usuario de tienda */
UPDATE c
SET c.IdUsuario = u.IdUsuario
FROM dbo.CLIENTE c
INNER JOIN dbo.USUARIO u ON u.Correo = 'cliente@pepe.com'
WHERE c.IdCliente = 1
  AND c.IdUsuario IS NULL;

/* Stock inicial del lote de ejemplo (el lote existía sin movimientos) */
IF NOT EXISTS (SELECT 1 FROM dbo.MOVIMIENTO_INVENTARIO m
               INNER JOIN dbo.LOTE l ON l.IdLote = m.IdLote
               WHERE l.CodigoLote = 'LT-RAB-2026')
   AND EXISTS (SELECT 1 FROM dbo.LOTE WHERE CodigoLote = 'LT-RAB-2026')
   AND EXISTS (SELECT 1 FROM dbo.USUARIO WHERE IdUsuario = 1)
    INSERT INTO dbo.MOVIMIENTO_INVENTARIO (TipoMov, Cantidad, Motivo, IdLote, IdUsuario)
    SELECT 'Entrada', 10, 'Carga inicial de inventario (migración)',
           l.IdLote, 1
    FROM dbo.LOTE l
    WHERE l.CodigoLote = 'LT-RAB-2026';
GO

COMMIT TRANSACTION;
GO

PRINT 'Migración 001 aplicada correctamente.';
GO

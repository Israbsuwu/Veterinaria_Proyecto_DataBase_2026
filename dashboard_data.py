"""
Consultas y operaciones del panel de administración.

La base de demostración y el dump del proyecto usan nombres de columna
distintos (por ejemplo FechaVencimiento/FechaVenc o PrecioVenta/Precio).
Aquí se detectan en tiempo de ejecución para que el panel funcione con las
dos sin tocar el esquema.
"""

from datetime import date, datetime, timedelta

import pyodbc


# ---------------------------------------------------------------------------
# Utilidades de esquema
# ---------------------------------------------------------------------------

def _columnas(cursor, tabla):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, (tabla,))
    return {str(fila[0]).lower(): str(fila[0]) for fila in cursor.fetchall()}


def _col(columnas, *nombres, **kwargs):
    for nombre in nombres:
        if nombre.lower() in columnas:
            return columnas[nombre.lower()]
    return kwargs.get('default')


def _es_identidad(cursor, tabla, columna):
    cursor.execute(
        "SELECT COLUMNPROPERTY(OBJECT_ID(?), ?, 'IsIdentity')",
        (tabla, columna),
    )
    fila = cursor.fetchone()
    return bool(fila[0]) if fila else False


def _seguro(cursor, errores, etiqueta, funcion):
    try:
        return funcion()
    except pyodbc.Error as exc:
        errores.append(f'{etiqueta}: {exc.args[-1] if exc.args else exc}')
        return []


def _texto(valor, respaldo='—'):
    valor = '' if valor is None else str(valor).strip()
    return valor or respaldo


def _entero(valor):
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _decimal(valor):
    if valor is None:
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Expresiones compartidas
# ---------------------------------------------------------------------------

def _contexto(cursor):
    producto = _columnas(cursor, 'PRODUCTO')
    categoria = _columnas(cursor, 'CATEGORIA')
    lote = _columnas(cursor, 'LOTE')
    movimiento = _columnas(cursor, 'MOVIMIENTO_INVENTARIO')
    concepto = _columnas(cursor, 'CONCEPTO_FACTURABLE')

    nombre_propio = _col(producto, 'Nombre')
    precio = _col(concepto, 'PrecioVenta', 'Precio', default='CAST(NULL AS decimal(10,2))')

    if nombre_propio:
        # Esquema del proyecto: el nombre vive en PRODUCTO.
        nombre_expr = 'P.Nombre'
        join_concepto = f"""
            OUTER APPLY (
                SELECT TOP 1 CF.{precio} AS Precio
                FROM CONCEPTO_FACTURABLE CF
                WHERE UPPER(CF.TipoConcepto) = 'PRODUCTO'
                  AND CF.Nombre = P.Nombre
                ORDER BY CF.IdConcepto
            ) CF
        """
    else:
        # Base de demostración: el nombre y el precio vienen del concepto
        # facturable con el mismo IdProducto.
        nombre_expr = 'CF.Nombre'
        join_concepto = 'LEFT JOIN CONCEPTO_FACTURABLE CF ON CF.IdConcepto = P.IdProducto'

    return {
        'producto': producto,
        'categoria': categoria,
        'lote': lote,
        'movimiento': movimiento,
        'concepto': concepto,
        'nombre_expr': nombre_expr,
        'join_concepto': join_concepto,
        'precio_expr': f'CF.{precio}',
        'unidad': _col(producto, 'UnidadMedida', default="'UND'"),
        'controla': _col(producto, 'ControlaVencimiento', 'ControlVenc', default='CAST(1 AS bit)'),
        'minimo': _col(producto, 'StockMinimo', 'StockMin', default='0'),
        'fecha_venc': _col(lote, 'FechaVencimiento', 'FechaVenc', default='FechaVencimiento'),
        'fecha_ing': _col(lote, 'FechaIngreso', 'FechaIng', default='FechaIngreso'),
        'tipo_mov': _col(movimiento, 'TipoMovimiento', 'TipoMov', default='TipoMovimiento'),
        'cant_mov': _col(movimiento, 'Cantidad', default='Cantidad'),
        'fecha_mov': _col(movimiento, 'FechaMovimiento', 'FechaMov', default='FechaMovimiento'),
        'id_mov': _col(movimiento, 'IdMovimiento', 'IdMov', default='IdMovimiento'),
        'id_compra': _col(_columnas(cursor, 'COMPRA'), 'IdCompra', default='IdCompra'),
        'num_doc': _col(_columnas(cursor, 'COMPRA'), 'NumeroDocumento', 'NumDoc', default='NumeroDocumento'),
        'fecha_compra': _col(_columnas(cursor, 'COMPRA'), 'FechaCompra', default='FechaCompra'),
        'costo_compra': _col(_columnas(cursor, 'DETALLE_COMPRA'), 'CostoUnitario', 'CostoUnit', default='CostoUnitario'),
        'fac_venta': _col(_columnas(cursor, 'VENTA'), 'NumeroFactura', 'Factura', default='NumeroFactura'),
        'fecha_venta': _col(_columnas(cursor, 'VENTA'), 'FechaVenta', default='FechaVenta'),
        'precio_venta': _col(_columnas(cursor, 'DETALLE_VENTA'), 'PrecioUnitario', 'PrecioUnit', default='PrecioUnitario'),
        'fecha_ini': _col(_columnas(cursor, 'RESERVA'), 'FechaHoraInicio', 'FechaIni', default='FechaHoraInicio'),
        'fecha_fin': _col(_columnas(cursor, 'RESERVA'), 'FechaHoraFin', 'FechaFin', default='FechaHoraFin'),
        'canal': _col(_columnas(cursor, 'RESERVA'), 'CanalOrigen', 'Canal', default='Canal'),
        'motivo': _col(_columnas(cursor, 'RESERVA'), 'MotivoSolicitud', 'Motivo', default='Motivo'),
        'metodo_pago': _col(_columnas(cursor, 'PAGO'), 'MetodoPago', 'Metodo', default='MetodoPago'),
    }


# ---------------------------------------------------------------------------
# Secciones de lectura
# ---------------------------------------------------------------------------

def _productos(cursor, ctx):
    sql = f"""
        SELECT P.IdProducto,
               P.IdCategoria,
               {ctx['nombre_expr']} AS Nombre,
               CAT.Nombre AS Categoria,
               P.{ctx['unidad']} AS Unidad,
               P.{ctx['controla']} AS ControlaVencimiento,
               P.{ctx['minimo']} AS StockMinimo,
               CAST(ISNULL(SUM(CASE
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'ENTRADA' THEN M.{ctx['cant_mov']}
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'SALIDA' THEN -M.{ctx['cant_mov']}
                   ELSE 0 END), 0) AS int) AS Stock,
               COUNT(DISTINCT L.IdLote) AS Lotes,
               MIN(L.{ctx['fecha_venc']}) AS ProximoVencimiento,
               {ctx['precio_expr']} AS Precio,
               MAX(CF.Descripcion) AS Descripcion
        FROM PRODUCTO P
        LEFT JOIN CATEGORIA CAT ON CAT.IdCategoria = P.IdCategoria
        LEFT JOIN LOTE L ON L.IdProducto = P.IdProducto
        LEFT JOIN MOVIMIENTO_INVENTARIO M ON M.IdLote = L.IdLote
        {ctx['join_concepto']}
        GROUP BY P.IdProducto, P.IdCategoria, {ctx['nombre_expr']}, CAT.Nombre,
                 P.{ctx['unidad']}, P.{ctx['controla']}, P.{ctx['minimo']},
                 {ctx['precio_expr']}
        ORDER BY P.IdProducto
    """
    cursor.execute(sql)
    productos = []
    for fila in cursor.fetchall():
        stock = _entero(fila.Stock)
        minimo = _entero(fila.StockMinimo)
        if stock <= 0:
            estado, clase = 'Agotado', 'danger'
        elif stock <= minimo:
            estado, clase = 'Stock bajo', 'warn'
        else:
            estado, clase = 'Disponible', 'ok'
        productos.append({
            'id': _entero(fila.IdProducto),
            'id_categoria': _entero(fila.IdCategoria),
            'nombre': _texto(fila.Nombre, f'Producto #{_entero(fila.IdProducto)}'),
            'categoria': _texto(fila.Categoria, 'Sin categoría'),
            'unidad': _texto(fila.Unidad, 'UND'),
            'controla_vencimiento': bool(fila.ControlaVencimiento),
            'minimo': minimo,
            'stock': stock,
            'lotes': _entero(fila.Lotes),
            'precio': _decimal(fila.Precio),
            'descripcion': _texto(fila.Descripcion, ''),
            'proximo_vencimiento': fila.ProximoVencimiento,
            'estado': estado,
            'clase': clase,
        })
    return productos


def cargar_catalogo(cursor):
    """Productos y categorías para la tienda y la sección de productos."""
    ctx = _contexto(cursor)
    productos = _productos(cursor, ctx)

    agrupadas = {}
    for producto in productos:
        nombre = producto['categoria']
        if nombre not in agrupadas:
            agrupadas[nombre] = {'nombre': nombre, 'productos': 0}
        agrupadas[nombre]['productos'] += 1

    categorias = sorted(agrupadas.values(), key=lambda c: c['nombre'].lower())
    return {'productos': productos, 'categorias': categorias}


def _lotes(cursor, ctx, hoy):
    sql = f"""
        SELECT L.IdLote, L.CodigoLote,
               L.{ctx['fecha_venc']} AS FechaVencimiento,
               L.{ctx['fecha_ing']} AS FechaIngreso,
               L.Estado,
               P.IdProducto,
               {ctx['nombre_expr']} AS Producto,
               CAT.Nombre AS Categoria,
               CAST(ISNULL(SUM(CASE
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'ENTRADA' THEN M.{ctx['cant_mov']}
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'SALIDA' THEN -M.{ctx['cant_mov']}
                   ELSE 0 END), 0) AS int) AS StockLote
        FROM LOTE L
        INNER JOIN PRODUCTO P ON P.IdProducto = L.IdProducto
        LEFT JOIN CATEGORIA CAT ON CAT.IdCategoria = P.IdCategoria
        LEFT JOIN MOVIMIENTO_INVENTARIO M ON M.IdLote = L.IdLote
        {ctx['join_concepto']}
        WHERE L.{ctx['fecha_venc']} IS NOT NULL
        GROUP BY L.IdLote, L.CodigoLote, L.{ctx['fecha_venc']},
                 L.{ctx['fecha_ing']}, L.Estado, P.IdProducto,
                 {ctx['nombre_expr']}, CAT.Nombre
        ORDER BY L.{ctx['fecha_venc']} ASC
    """
    cursor.execute(sql)
    lotes = []
    for fila in cursor.fetchall():
        vence = fila.FechaVencimiento
        dias = (vence - hoy).days if vence else None
        if dias is None:
            estado, clase = 'Sin fecha', 'muted'
        elif dias < 0:
            estado, clase = 'Vencido', 'danger'
        elif dias <= 30:
            estado, clase = 'Vence en 30 días', 'danger'
        elif dias <= 90:
            estado, clase = 'Vence en 90 días', 'warn'
        elif dias <= 365:
            estado, clase = 'Este año', 'info'
        else:
            estado, clase = 'Vigente', 'ok'
        lotes.append({
            'id': _entero(fila.IdLote),
            'codigo': _texto(fila.CodigoLote),
            'producto': _texto(fila.Producto, f'Producto #{_entero(fila.IdProducto)}'),
            'categoria': _texto(fila.Categoria, 'Sin categoría'),
            'ingreso': fila.FechaIngreso,
            'vence': vence,
            'dias': dias,
            'stock': _entero(fila.StockLote),
            'estado_bd': _texto(fila.Estado, '—'),
            'estado': estado,
            'clase': clase,
            'filtro': ('vencido' if dias is not None and dias < 0 else
                       '30' if dias is not None and dias <= 30 else
                       '90' if dias is not None and dias <= 90 else
                       '180' if dias is not None and dias <= 180 else
                       '365' if dias is not None and dias <= 365 else 'lejano'),
        })
    return lotes


def _citas(cursor, ctx):
    sql = f"""
        SELECT R.IdReserva,
               R.{ctx['fecha_ini']} AS FechaHoraInicio,
               R.{ctx['fecha_fin']} AS FechaHoraFin,
               R.{ctx['canal']} AS Canal,
               R.{ctx['motivo']} AS Motivo,
               R.Estado,
               C.IdCliente, C.Nombre AS ClienteNombre, C.Apellido AS ClienteApellido,
               C.Telefono,
               M.IdMascota, M.Nombre AS Mascota, M.Especie, M.Raza,
               V.IdVeterinario, U.Nombre AS VetNombre, U.Apellido AS VetApellido
        FROM RESERVA R
        INNER JOIN CLIENTE C ON C.IdCliente = R.IdCliente
        LEFT JOIN MASCOTA M ON M.IdMascota = R.IdMascota
        LEFT JOIN VETERINARIO V ON V.IdVeterinario = R.IdVeterinario
        LEFT JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        ORDER BY R.{ctx['fecha_ini']} DESC
    """
    cursor.execute(sql)
    ahora = datetime.now()
    citas = []
    for fila in cursor.fetchall():
        estado = _texto(fila.Estado, 'PROGRAMADA').upper()
        if estado == 'PROGRAMADA':
            clase = 'warn'
        elif estado == 'ATENDIDA':
            clase = 'ok'
        elif estado == 'CANCELADA':
            clase = 'danger'
        else:
            clase = 'info'
        inicio = fila.FechaHoraInicio
        citas.append({
            'id': _entero(fila.IdReserva),
            'inicio': inicio,
            'fin': fila.FechaHoraFin,
            'canal': _texto(fila.Canal, '—'),
            'motivo': _texto(fila.Motivo, 'Sin motivo'),
            'estado': estado,
            'clase': clase,
            'cliente_id': _entero(fila.IdCliente),
            'cliente': _texto(f"{fila.ClienteNombre or ''} {fila.ClienteApellido or ''}"),
            'telefono': _texto(fila.Telefono),
            'mascota_id': _entero(fila.IdMascota),
            'mascota': _texto(fila.Mascota, 'Sin mascota'),
            'especie': _texto(fila.Especie, '—'),
            'raza': _texto(fila.Raza, '—'),
            'veterinario': _texto(f"{fila.VetNombre or ''} {fila.VetApellido or ''}".strip(), 'Por asignar'),
            'pasada': bool(inicio and inicio < ahora and estado == 'PROGRAMADA'),
        })
    return citas


def _proveedores(cursor, ctx):
    sql = f"""
        SELECT PR.IdProveedor, PR.Nombre, PR.Telefono, PR.Correo, PR.Direccion, PR.Estado,
               COUNT(DISTINCT CO.{ctx['id_compra']}) AS Compras,
               ISNULL(SUM(DC.Cantidad * DC.{ctx['costo_compra']}), 0) AS TotalComprado,
               MAX(CO.{ctx['fecha_compra']}) AS UltimaCompra
        FROM PROVEEDOR PR
        LEFT JOIN COMPRA CO ON CO.IdProveedor = PR.IdProveedor
        LEFT JOIN DETALLE_COMPRA DC ON DC.{ctx['id_compra']} = CO.{ctx['id_compra']}
        GROUP BY PR.IdProveedor, PR.Nombre, PR.Telefono, PR.Correo, PR.Direccion, PR.Estado
        ORDER BY Compras DESC, PR.Nombre
    """
    cursor.execute(sql)
    return [{
        'id': _entero(f.IdProveedor),
        'nombre': _texto(f.Nombre),
        'telefono': _texto(f.Telefono),
        'correo': _texto(f.Correo),
        'direccion': _texto(f.Direccion),
        'estado': _texto(f.Estado, 'ACTIVO').upper(),
        'compras': _entero(f.Compras),
        'total': _decimal(f.TotalComprado),
        'ultima': f.UltimaCompra,
    } for f in cursor.fetchall()]


def _compras(cursor, ctx):
    sql = f"""
        SELECT TOP 12 CO.{ctx['id_compra']} AS IdCompra,
               CO.{ctx['num_doc']} AS NumeroDocumento,
               CO.{ctx['fecha_compra']} AS FechaCompra,
               CO.Estado,
               PR.Nombre AS Proveedor,
               (SELECT ISNULL(SUM(DC.Cantidad * DC.{ctx['costo_compra']}), 0)
                FROM DETALLE_COMPRA DC
                WHERE DC.{ctx['id_compra']} = CO.{ctx['id_compra']}) AS Total
        FROM COMPRA CO
        INNER JOIN PROVEEDOR PR ON PR.IdProveedor = CO.IdProveedor
        ORDER BY CO.{ctx['fecha_compra']} DESC
    """
    cursor.execute(sql)
    return [{
        'id': _entero(f.IdCompra),
        'documento': _texto(f.NumeroDocumento),
        'fecha': f.FechaCompra,
        'estado': _texto(f.Estado, '—').upper(),
        'proveedor': _texto(f.Proveedor),
        'total': _decimal(f.Total),
    } for f in cursor.fetchall()]


def _facturas(cursor, ctx):
    sql = f"""
        SELECT V.IdVenta,
               V.{ctx['fac_venta']} AS NumeroFactura,
               V.{ctx['fecha_venta']} AS FechaVenta,
               V.Estado,
               C.IdCliente, C.Nombre AS ClienteNombre, C.Apellido AS ClienteApellido,
               C.Cedula,
               U.Nombre AS VendedorNombre, U.Apellido AS VendedorApellido,
               (SELECT ISNULL(SUM(DV.Cantidad * DV.{ctx['precio_venta']}), 0)
                FROM DETALLE_VENTA DV WHERE DV.IdVenta = V.IdVenta) AS Total,
               (SELECT ISNULL(SUM(P.Monto), 0)
                FROM PAGO P WHERE P.IdVenta = V.IdVenta) AS Pagado,
               (SELECT TOP 1 P.{ctx['metodo_pago']}
                FROM PAGO P WHERE P.IdVenta = V.IdVenta
                ORDER BY P.FechaPago) AS Metodo,
               (SELECT ISNULL(SUM(DV.Cantidad), 0)
                FROM DETALLE_VENTA DV WHERE DV.IdVenta = V.IdVenta) AS Unidades,
               (SELECT COUNT(*)
                FROM DETALLE_VENTA DV WHERE DV.IdVenta = V.IdVenta) AS Lineas
        FROM VENTA V
        INNER JOIN CLIENTE C ON C.IdCliente = V.IdCliente
        LEFT JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        ORDER BY V.{ctx['fecha_venta']} DESC
    """
    cursor.execute(sql)
    facturas = []
    for f in cursor.fetchall():
        total = _decimal(f.Total)
        pagado = _decimal(f.Pagado)
        estado = _texto(f.Estado, '—').upper()
        if estado == 'PAGADA' or (total and pagado >= total):
            clase = 'ok'
        elif estado == 'ANULADA':
            clase = 'danger'
        else:
            clase = 'warn'
        facturas.append({
            'id': _entero(f.IdVenta),
            'numero': _texto(f.NumeroFactura),
            'fecha': f.FechaVenta,
            'estado': estado,
            'clase': clase,
            'cliente_id': _entero(f.IdCliente),
            'cliente': _texto(f"{f.ClienteNombre or ''} {f.ClienteApellido or ''}"),
            'cedula': _texto(f.Cedula),
            'vendedor': _texto(f"{f.VendedorNombre or ''} {f.VendedorApellido or ''}".strip(), '—'),
            'total': total,
            'pagado': pagado,
            'saldo': round(total - pagado, 2),
            'metodo': _texto(f.Metodo, '—').upper(),
            'unidades': _entero(f.Unidades),
            'lineas': _entero(f.Lineas),
        })
    return facturas


def _clientes(cursor, ctx):
    columnas = _columnas(cursor, 'CLIENTE')
    notif = _col(columnas, 'AceptaNotificaciones', 'AceptaNotif')
    notif_expr = f'C.{notif}' if notif else 'CAST(0 AS bit)'
    sql = f"""
        SELECT C.IdCliente, C.Nombre, C.Apellido, C.Cedula, C.Telefono,
               C.Correo, C.Direccion, {notif_expr} AS AceptaNotificaciones,
               (SELECT COUNT(*) FROM MASCOTA M WHERE M.IdCliente = C.IdCliente) AS Mascotas,
               (SELECT COUNT(*) FROM VENTA V WHERE V.IdCliente = C.IdCliente) AS Compras,
               (SELECT ISNULL(SUM(DV.Cantidad * DV.{ctx['precio_venta']}), 0)
                FROM VENTA V
                INNER JOIN DETALLE_VENTA DV ON DV.IdVenta = V.IdVenta
                WHERE V.IdCliente = C.IdCliente) AS Total
        FROM CLIENTE C
        ORDER BY C.Nombre, C.Apellido
    """
    cursor.execute(sql)
    return [{
        'id': _entero(f.IdCliente),
        'nombre': _texto(f.Nombre),
        'apellido': _texto(f.Apellido),
        'cedula': _texto(f.Cedula),
        'telefono': _texto(f.Telefono),
        'correo': _texto(f.Correo),
        'direccion': _texto(f.Direccion),
        'notificaciones': bool(f.AceptaNotificaciones),
        'mascotas': _entero(f.Mascotas),
        'compras': _entero(f.Compras),
        'total': _decimal(f.Total),
    } for f in cursor.fetchall()]


def _equipo(cursor):
    columnas = _columnas(cursor, 'USUARIO')
    fecha = _col(columnas, 'FechaRegistro', 'FechaReg')
    fecha_expr = f'U.{fecha}' if fecha else 'CAST(NULL AS datetime2)'
    cursor.execute(f"""
        SELECT U.IdUsuario, U.Nombre, U.Apellido, U.Correo, U.Telefono, U.Estado,
               R.NombreRol, {fecha_expr} AS FechaRegistro
        FROM USUARIO U
        LEFT JOIN ROL R ON R.IdRol = U.IdRol
        ORDER BY R.NombreRol, U.Nombre, U.Apellido
    """)
    return [{
        'id': _entero(f.IdUsuario),
        'nombre': _texto(f.Nombre),
        'apellido': _texto(f.Apellido),
        'correo': _texto(f.Correo),
        'telefono': _texto(f.Telefono),
        'estado': _texto(f.Estado, '—').upper(),
        'rol': _texto(f.NombreRol, 'Sin rol'),
        'registro': f.FechaRegistro,
    } for f in cursor.fetchall()]


def _ventas_por_mes(cursor, ctx, hoy):
    cursor.execute(f"""
        SELECT CONVERT(char(7), V.{ctx['fecha_venta']}, 126) AS Mes,
               COUNT(DISTINCT V.IdVenta) AS Facturas,
               ISNULL(SUM(DV.Cantidad * DV.{ctx['precio_venta']}), 0) AS Total
        FROM VENTA V
        INNER JOIN DETALLE_VENTA DV ON DV.IdVenta = V.IdVenta
        WHERE V.{ctx['fecha_venta']} >= DATEADD(month, -5,
              DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
        GROUP BY CONVERT(char(7), V.{ctx['fecha_venta']}, 126)
        ORDER BY Mes
    """)
    encontrados = {str(f.Mes): ( _entero(f.Facturas), _decimal(f.Total) )
                   for f in cursor.fetchall()}

    meses = []
    anio, mes = hoy.year, hoy.month
    for _ in range(6):
        clave = f'{anio:04d}-{mes:02d}'
        facturas, total = encontrados.get(clave, (0, 0.0))
        meses.append({'clave': clave, 'etiqueta': _MESES[mes - 1] + f' {anio}',
                      'facturas': facturas, 'total': total})
        mes -= 1
        if mes == 0:
            mes, anio = 12, anio - 1
    meses.reverse()
    maximo = max([m['total'] for m in meses] + [1.0])
    for m in meses:
        m['pct'] = round((m['total'] / maximo) * 100, 1)
    return meses


_MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
          'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _metodos_pago(cursor, ctx):
    cursor.execute(f"""
        SELECT {ctx['metodo_pago']} AS Metodo,
               COUNT(*) AS Pagos,
               ISNULL(SUM(Monto), 0) AS Total
        FROM PAGO
        GROUP BY {ctx['metodo_pago']}
        ORDER BY Total DESC
    """)
    filas = cursor.fetchall()
    total_general = sum(_decimal(f.Total) for f in filas) or 1
    return [{
        'metodo': _texto(f.Metodo, 'Otro').upper(),
        'pagos': _entero(f.Pagos),
        'total': _decimal(f.Total),
        'pct': round((_decimal(f.Total) / total_general) * 100, 1),
    } for f in filas]


def _top_productos(cursor, ctx):
    cursor.execute(f"""
        SELECT TOP 6 CF.Nombre AS Producto,
               SUM(DV.Cantidad) AS Unidades,
               SUM(DV.Cantidad * DV.{ctx['precio_venta']}) AS Total
        FROM DETALLE_VENTA DV
        INNER JOIN CONCEPTO_FACTURABLE CF ON CF.IdConcepto = DV.IdConcepto
        GROUP BY CF.Nombre
        ORDER BY Unidades DESC
    """)
    filas = cursor.fetchall()
    maximo = max([_entero(f.Unidades) for f in filas] + [1])
    return [{
        'nombre': _texto(f.Producto),
        'unidades': _entero(f.Unidades),
        'total': _decimal(f.Total),
        'pct': round((_entero(f.Unidades) / maximo) * 100, 1),
    } for f in filas]


# ---------------------------------------------------------------------------
# Lectura principal
# ---------------------------------------------------------------------------

def cargar_dashboard(cursor):
    hoy = date.today()
    errores = []

    ctx = _contexto(cursor)

    productos = _seguro(cursor, errores, 'Inventario', lambda: _productos(cursor, ctx))
    lotes = _seguro(cursor, errores, 'Vencimientos', lambda: _lotes(cursor, ctx, hoy))
    citas = _seguro(cursor, errores, 'Citas', lambda: _citas(cursor, ctx))
    proveedores = _seguro(cursor, errores, 'Proveedores', lambda: _proveedores(cursor, ctx))
    compras = _seguro(cursor, errores, 'Compras', lambda: _compras(cursor, ctx))
    facturas = _seguro(cursor, errores, 'Facturas', lambda: _facturas(cursor, ctx))
    clientes = _seguro(cursor, errores, 'Clientes', lambda: _clientes(cursor, ctx))
    equipo = _seguro(cursor, errores, 'Equipo', lambda: _equipo(cursor))
    ventas_mes = _seguro(cursor, errores, 'Ventas por mes',
                         lambda: _ventas_por_mes(cursor, ctx, hoy))
    metodos = _seguro(cursor, errores, 'Métodos de pago',
                      lambda: _metodos_pago(cursor, ctx))
    top_productos = _seguro(cursor, errores, 'Más vendidos',
                            lambda: _top_productos(cursor, ctx))

    stock_bajo = [p for p in productos if p['clase'] in ('warn', 'danger')]
    agotados = [p for p in productos if p['clase'] == 'danger']
    stock_total = sum(p['stock'] for p in productos)
    lotes_vencidos = [l for l in lotes if l['dias'] is not None and l['dias'] < 0]
    lotes_90 = [l for l in lotes if l['dias'] is not None and 0 <= l['dias'] <= 90]
    lotes_365 = [l for l in lotes if l['dias'] is not None and 0 <= l['dias'] <= 365]

    citas_programadas = [c for c in citas if c['estado'] == 'PROGRAMADA']
    citas_atendidas = [c for c in citas if c['estado'] == 'ATENDIDA']
    citas_canceladas = [c for c in citas if c['estado'] == 'CANCELADA']
    citas_hoy = [c for c in citas if c['inicio'] and c['inicio'].date() == hoy]
    citas_pasadas = [c for c in citas_programadas if c['pasada']]

    total_facturado = sum(f['total'] for f in facturas)
    total_pagado = sum(f['pagado'] for f in facturas)
    ticket = (total_facturado / len(facturas)) if facturas else 0

    hoy_dt = datetime.combine(hoy, datetime.min.time())
    hace_30 = hoy_dt - timedelta(days=30)
    facturas_30 = [f for f in facturas if f['fecha'] and f['fecha'] >= hace_30]
    ingresos_30 = sum(f['total'] for f in facturas_30)

    proveedores_activos = [p for p in proveedores if p['estado'] == 'ACTIVO']
    personal_activo = [e for e in equipo if e['estado'] == 'ACTIVO']

    # Productos con menos cobertura (stock / mínimo), útiles para el resumen.
    riesgo = sorted(productos, key=lambda p: (
        0 if p['stock'] <= 0 else 1,
        (p['stock'] / p['minimo']) if p['minimo'] else p['stock'],
        p['nombre'],
    ))[:8]

    # Citas programadas más cercanas; si todas quedaron en el pasado,
    # se muestran las últimas de todos modos.
    proximas = sorted(citas_programadas, key=lambda c: c['inicio'] or datetime.max)[:6]

    kpis = {
        'productos': len(productos),
        'stock_total': stock_total,
        'stock_bajo': len(stock_bajo),
        'agotados': len(agotados),
        'lotes': len(lotes),
        'lotes_90': len(lotes_90),
        'lotes_365': len(lotes_365),
        'lotes_vencidos': len(lotes_vencidos),
        'citas': len(citas),
        'citas_programadas': len(citas_programadas),
        'citas_hoy': len(citas_hoy),
        'citas_atendidas': len(citas_atendidas),
        'citas_pasadas': len(citas_pasadas),
        'facturas': len(facturas),
        'facturado': total_facturado,
        'pagado': total_pagado,
        'ticket': ticket,
        'facturas_30': len(facturas_30),
        'ingresos_30': ingresos_30,
        'proveedores': len(proveedores),
        'proveedores_activos': len(proveedores_activos),
        'clientes': len(clientes),
        'personal': len(equipo),
        'personal_activo': len(personal_activo),
        'mascotas': sum(c['mascotas'] for c in clientes),
        'categorias': len({p['categoria'] for p in productos}),
        'roles': len({e['rol'] for e in equipo if e['rol'] not in ('Sin rol', '—')}),
    }

    return {
        'hoy': hoy,
        'generado': datetime.now(),
        'kpis': kpis,
        'productos': productos,
        'lotes': lotes,
        'citas': citas,
        'proveedores': proveedores,
        'compras': compras,
        'facturas': facturas,
        'clientes': clientes,
        'equipo': equipo,
        'ventas_mes': ventas_mes,
        'metodos': metodos,
        'top_productos': top_productos,
        'riesgo': riesgo,
        'proximas_citas': proximas,
        'lotes_proximos': lotes[:8],
        'categorias_stock': _categorias(productos),
        'errores': errores,
    }


def panel_vacio(mensaje):
    """Estructura mínima para poder mostrar el panel aunque falle la conexión."""
    kpis = {clave: 0 for clave in (
        'productos', 'stock_total', 'stock_bajo', 'agotados', 'lotes',
        'lotes_90', 'lotes_365', 'lotes_vencidos', 'citas', 'citas_programadas',
        'citas_hoy', 'citas_atendidas', 'citas_pasadas', 'facturas',
        'facturado', 'pagado', 'ticket', 'facturas_30', 'ingresos_30',
        'proveedores', 'proveedores_activos', 'clientes', 'personal',
        'personal_activo', 'mascotas', 'categorias', 'roles',
    )}
    return {
        'hoy': date.today(),
        'generado': datetime.now(),
        'kpis': kpis,
        'productos': [], 'lotes': [], 'citas': [], 'proveedores': [],
        'compras': [], 'facturas': [], 'clientes': [], 'equipo': [],
        'ventas_mes': [], 'metodos': [], 'top_productos': [],
        'riesgo': [], 'proximas_citas': [], 'lotes_proximos': [],
        'categorias_stock': [], 'errores': [mensaje],
    }


def _categorias(productos):
    agrupadas = {}
    for p in productos:
        fila = agrupadas.setdefault(p['categoria'], {'id': p.get('id_categoria'),
                                                     'nombre': p['categoria'],
                                                     'productos': 0, 'stock': 0,
                                                     'bajo': 0})
        fila['productos'] += 1
        fila['stock'] += max(p['stock'], 0)
        if p['clase'] in ('warn', 'danger'):
            fila['bajo'] += 1
    filas = sorted(agrupadas.values(), key=lambda x: x['stock'], reverse=True)
    maximo = max([f['stock'] for f in filas] + [1])
    for fila in filas:
        fila['pct'] = round((fila['stock'] / maximo) * 100, 1)
    return filas


# ---------------------------------------------------------------------------
# Detalle de factura y operaciones de escritura
# ---------------------------------------------------------------------------

def obtener_factura(cursor, id_venta):
    ctx = _contexto(cursor)

    cursor.execute(f"""
        SELECT V.IdVenta, V.{ctx['fac_venta']} AS NumeroFactura,
               V.{ctx['fecha_venta']} AS FechaVenta, V.Estado,
               C.Nombre AS ClienteNombre, C.Apellido AS ClienteApellido,
               C.Cedula, C.Correo, C.Telefono, C.Direccion,
               U.Nombre AS VendedorNombre, U.Apellido AS VendedorApellido
        FROM VENTA V
        INNER JOIN CLIENTE C ON C.IdCliente = V.IdCliente
        LEFT JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        WHERE V.IdVenta = ?
    """, (id_venta,))
    factura = cursor.fetchone()
    if factura is None:
        return None

    cursor.execute(f"""
        SELECT CF.Nombre AS Concepto, CF.TipoConcepto,
               DV.Cantidad, DV.{ctx['precio_venta']} AS Precio
        FROM DETALLE_VENTA DV
        LEFT JOIN CONCEPTO_FACTURABLE CF ON CF.IdConcepto = DV.IdConcepto
        WHERE DV.IdVenta = ?
        ORDER BY CF.Nombre
    """, (id_venta,))
    lineas = [{
        'concepto': _texto(f.Concepto, 'Concepto sin nombre'),
        'tipo': _texto(f.TipoConcepto, '—'),
        'cantidad': _entero(f.Cantidad),
        'precio': _decimal(f.Precio),
        'subtotal': round(_entero(f.Cantidad) * _decimal(f.Precio), 2),
    } for f in cursor.fetchall()]

    cursor.execute(f"""
        SELECT P.FechaPago, P.Monto,
               P.{ctx['metodo_pago']} AS Metodo, P.Referencia
        FROM PAGO P
        WHERE P.IdVenta = ?
        ORDER BY P.FechaPago
    """, (id_venta,))
    pagos = [{
        'fecha': p.FechaPago.isoformat(sep=' ') if p.FechaPago else '',
        'monto': _decimal(p.Monto),
        'metodo': _texto(p.Metodo, '—').upper(),
        'referencia': _texto(p.Referencia, ''),
    } for p in cursor.fetchall()]

    total = round(sum(l['subtotal'] for l in lineas), 2)
    pagado = round(sum(p['monto'] for p in pagos), 2)
    return {
        'id': _entero(factura.IdVenta),
        'numero': _texto(factura.NumeroFactura),
        'fecha': factura.FechaVenta.isoformat(sep=' ') if factura.FechaVenta else '',
        'estado': _texto(factura.Estado, '—').upper(),
        'cliente': {
            'nombre': _texto(f"{factura.ClienteNombre or ''} {factura.ClienteApellido or ''}"),
            'cedula': _texto(factura.Cedula, ''),
            'correo': _texto(factura.Correo, ''),
            'telefono': _texto(factura.Telefono, ''),
            'direccion': _texto(factura.Direccion, ''),
        },
        'vendedor': _texto(f"{factura.VendedorNombre or ''} {factura.VendedorApellido or ''}".strip(), '—'),
        'lineas': lineas,
        'pagos': pagos,
        'total': total,
        'pagado': pagado,
        'saldo': round(total - pagado, 2),
    }


def registrar_movimiento(cursor, id_lote, tipo, cantidad, motivo, id_usuario):
    tipo = (tipo or '').strip().upper()
    if tipo not in ('ENTRADA', 'SALIDA'):
        raise ValueError('El tipo de movimiento debe ser ENTRADA o SALIDA.')
    if cantidad <= 0:
        raise ValueError('La cantidad debe ser mayor que cero.')

    ctx = _contexto(cursor)
    cursor.execute(f"""
        SELECT L.IdLote, L.CodigoLote, {ctx['nombre_expr']} AS Producto,
               CAST(ISNULL(SUM(CASE
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'ENTRADA' THEN M.{ctx['cant_mov']}
                   WHEN UPPER(M.{ctx['tipo_mov']}) = 'SALIDA' THEN -M.{ctx['cant_mov']}
                   ELSE 0 END), 0) AS int) AS Stock
        FROM LOTE L
        INNER JOIN PRODUCTO P ON P.IdProducto = L.IdProducto
        LEFT JOIN MOVIMIENTO_INVENTARIO M ON M.IdLote = L.IdLote
        {ctx['join_concepto']}
        WHERE L.IdLote = ?
        GROUP BY L.IdLote, L.CodigoLote, {ctx['nombre_expr']}
    """, (id_lote,))
    lote = cursor.fetchone()
    if lote is None:
        raise ValueError('El lote seleccionado no existe.')

    stock_actual = _entero(lote.Stock)
    if tipo == 'SALIDA' and cantidad > stock_actual:
        raise ValueError(f'No puedes retirar {cantidad} unidades: el lote solo tiene '
                         f'{stock_actual} disponibles.')

    movimiento = _columnas(cursor, 'MOVIMIENTO_INVENTARIO')
    campos = ['IdLote', 'IdUsuario', ctx['fecha_mov'], ctx['tipo_mov'],
              ctx['cant_mov'], 'Motivo']
    marcas = ['?', '?', 'GETDATE()', '?', '?', '?']
    parametros = [id_lote, id_usuario, tipo, cantidad, motivo or 'Ajuste desde el panel']

    col_id = ctx['id_mov']
    if not _es_identidad(cursor, 'MOVIMIENTO_INVENTARIO', col_id):
        cursor.execute(f"SELECT ISNULL(MAX({col_id}), 0) + 1 FROM MOVIMIENTO_INVENTARIO")
        campos.insert(0, col_id)
        marcas.insert(0, '?')
        parametros.insert(0, cursor.fetchone()[0])

    # IdDetalleVenta es opcional; si existe se deja en NULL.
    cursor.execute(f"""
        INSERT INTO MOVIMIENTO_INVENTARIO ({', '.join(campos)})
        VALUES ({', '.join(marcas)})
    """, parametros)
    return {
        'lote': _texto(lote.CodigoLote),
        'producto': _texto(lote.Producto),
        'tipo': tipo,
        'cantidad': cantidad,
        'stock_anterior': stock_actual,
        'stock_nuevo': stock_actual + cantidad if tipo == 'ENTRADA' else stock_actual - cantidad,
    }


def crear_proveedor(cursor, datos):
    nombre = (datos.get('nombre') or '').strip()
    if len(nombre) < 3:
        raise ValueError('El nombre del proveedor debe tener al menos 3 caracteres.')

    cursor.execute("SELECT COUNT(*) FROM PROVEEDOR WHERE Nombre = ?", (nombre,))
    if cursor.fetchone()[0]:
        raise ValueError('Ya existe un proveedor con ese nombre.')

    proveedor = _columnas(cursor, 'PROVEEDOR')
    identificador = _col(proveedor, 'IdProveedor', default='IdProveedor')
    campos = ['Nombre', 'Telefono', 'Correo', 'Direccion', 'Estado']
    marcas = ['?', '?', '?', '?', "'ACTIVO'"]
    parametros = [
        nombre,
        (datos.get('telefono') or '').strip() or None,
        (datos.get('correo') or '').strip() or None,
        (datos.get('direccion') or '').strip() or None,
    ]

    if not _es_identidad(cursor, 'PROVEEDOR', identificador):
        cursor.execute(f"SELECT ISNULL(MAX({identificador}), 0) + 1 FROM PROVEEDOR")
        campos.insert(0, identificador)
        marcas.insert(0, '?')
        parametros.insert(0, cursor.fetchone()[0])

    cursor.execute(f"""
        INSERT INTO PROVEEDOR ({', '.join(campos)})
        VALUES ({', '.join(marcas)})
    """, parametros)
    return nombre


def actualizar_estado_cita(cursor, id_reserva, estado):
    estado = (estado or '').strip().upper()
    permitidos = ('PROGRAMADA', 'ATENDIDA', 'CANCELADA')
    if estado not in permitidos:
        raise ValueError('Estado de cita no válido.')

    cursor.execute("SELECT IdReserva, Estado FROM RESERVA WHERE IdReserva = ?", (id_reserva,))
    cita = cursor.fetchone()
    if cita is None:
        raise ValueError('La cita ya no existe.')

    cursor.execute("UPDATE RESERVA SET Estado = ? WHERE IdReserva = ?",
                   (estado, id_reserva))
    return {'anterior': _texto(cita.Estado, '—').upper(), 'nuevo': estado}


def crear_producto(cursor, datos):
    """Crea un producto vendible en las dos variantes de esquema del proyecto.

    Base demo: PRODUCTO.IdProducto comparte valor con CONCEPTO_FACTURABLE.IdConcepto.
    Base real: PRODUCTO tiene Nombre propio e IdProducto es IDENTITY; el precio
    vive en CONCEPTO_FACTURABLE y se enlaza por nombre.
    """
    nombre = (datos.get('nombre') or '').strip()
    descripcion = (datos.get('descripcion') or '').strip()
    unidad = (datos.get('unidad') or 'UNIDAD').strip().upper()
    try:
        id_categoria = int(datos.get('id_categoria') or 0)
        stock_minimo = int(datos.get('stock_minimo') or 0)
        precio = float(datos.get('precio') or 0)
    except (TypeError, ValueError):
        raise ValueError('Los datos numéricos del producto no son válidos.')

    if len(nombre) < 3:
        raise ValueError('El nombre del producto debe tener al menos 3 caracteres.')
    if len(nombre) > 150:
        raise ValueError('El nombre del producto no puede superar los 150 caracteres.')
    if descripcion and len(descripcion) > 255:
        raise ValueError('La descripción no puede superar los 255 caracteres.')
    if not unidad:
        raise ValueError('Indica la unidad de medida del producto.')
    if precio <= 0:
        raise ValueError('El precio de venta debe ser mayor que cero.')
    if stock_minimo < 0:
        raise ValueError('El stock mínimo no puede ser negativo.')

    cursor.execute("SELECT COUNT(*) FROM CATEGORIA WHERE IdCategoria = ?", (id_categoria,))
    if not cursor.fetchone()[0]:
        raise ValueError('La categoría seleccionada no existe.')

    concepto = _columnas(cursor, 'CONCEPTO_FACTURABLE')
    precio_col = _col(concepto, 'PrecioVenta', 'Precio')
    if not precio_col:
        raise ValueError('La tabla de conceptos no tiene una columna de precio reconocible.')

    campos = ['TipoConcepto', 'Nombre']
    parametros = ['PRODUCTO', nombre]
    if 'descripcion' in concepto:
        campos.append('Descripcion')
        parametros.append(descripcion or None)
    campos.append(precio_col)
    parametros.append(precio)
    if 'estado' in concepto:
        campos.append('Estado')
        parametros.append('ACTIVO')

    id_concepto_col = _col(concepto, 'IdConcepto', default='IdConcepto')
    if _es_identidad(cursor, 'CONCEPTO_FACTURABLE', id_concepto_col):
        cursor.execute(f"""
            INSERT INTO CONCEPTO_FACTURABLE ({', '.join(campos)})
            OUTPUT INSERTED.{id_concepto_col}
            VALUES ({', '.join(['?'] * len(campos))})
        """, parametros)
        id_concepto = int(cursor.fetchone()[0])
    else:
        cursor.execute(f"SELECT ISNULL(MAX({id_concepto_col}), 0) + 1 FROM CONCEPTO_FACTURABLE")
        id_concepto = int(cursor.fetchone()[0])
        cursor.execute(f"""
            INSERT INTO CONCEPTO_FACTURABLE ({id_concepto_col}, {', '.join(campos)})
            VALUES (?, {', '.join(['?'] * len(campos))})
        """, [id_concepto] + parametros)

    producto = _columnas(cursor, 'PRODUCTO')
    nombre_col = _col(producto, 'Nombre')
    control_col = _col(producto, 'ControlaVencimiento', 'ControlVenc')
    minimo_col = _col(producto, 'StockMinimo', 'StockMin')
    id_producto_col = _col(producto, 'IdProducto', default='IdProducto')
    if not control_col or not minimo_col:
        raise ValueError('La tabla de productos no tiene las columnas esperadas.')

    campos_prod = []
    parametros_prod = []
    if nombre_col:
        campos_prod.append(nombre_col)
        parametros_prod.append(nombre)
    campos_prod.extend([control_col, minimo_col, 'IdCategoria', 'UnidadMedida'])
    parametros_prod.extend([1 if datos.get('controla_vencimiento') else 0,
                            stock_minimo, id_categoria, unidad])

    if _es_identidad(cursor, 'PRODUCTO', id_producto_col):
        cursor.execute(f"""
            INSERT INTO PRODUCTO ({', '.join(campos_prod)})
            OUTPUT INSERTED.{id_producto_col}
            VALUES ({', '.join(['?'] * len(campos_prod))})
        """, parametros_prod)
        id_producto = int(cursor.fetchone()[0])
    else:
        if nombre_col:
            cursor.execute(f"SELECT ISNULL(MAX({id_producto_col}), 0) + 1 FROM PRODUCTO")
            id_producto = int(cursor.fetchone()[0])
        else:
            # La base demo exige que PRODUCTO.IdProducto sea el mismo del concepto.
            id_producto = id_concepto
        cursor.execute(f"""
            INSERT INTO PRODUCTO ({id_producto_col}, {', '.join(campos_prod)})
            VALUES (?, {', '.join(['?'] * len(campos_prod))})
        """, [id_producto] + parametros_prod)

    # Registro opcional de costo de compra (oferta del proveedor) usando tablas existentes.
    costo_raw = datos.get('costo_compra')
    id_proveedor_raw = datos.get('id_proveedor')
    id_usuario = datos.get('id_usuario')
    costo_compra = None
    if costo_raw not in (None, ''):
        try:
            costo_compra = float(costo_raw)
        except (TypeError, ValueError):
            raise ValueError('El costo de compra no es válido.')
        if costo_compra < 0:
            raise ValueError('El costo de compra no puede ser negativo.')

    if costo_compra is not None and costo_compra > 0 and id_proveedor_raw:
        try:
            id_proveedor = int(id_proveedor_raw)
        except (TypeError, ValueError):
            raise ValueError('El proveedor seleccionado no es válido.')

        cursor.execute("SELECT COUNT(*) FROM PROVEEDOR WHERE IdProveedor = ?", (id_proveedor,))
        if not cursor.fetchone()[0]:
            raise ValueError('El proveedor seleccionado no existe.')
        if not id_usuario:
            raise ValueError('No se pudo identificar el usuario para registrar el costo de compra.')

        compra = _columnas(cursor, 'COMPRA')
        id_compra_col = _col(compra, 'IdCompra', default='IdCompra')
        if _es_identidad(cursor, 'COMPRA', id_compra_col):
            # Variante poco común; se intenta OUTPUT.
            cursor.execute(f"""
                INSERT INTO COMPRA (IdProveedor, IdUsuario, FechaCompra, NumeroDocumento, Estado)
                OUTPUT INSERTED.{id_compra_col}
                VALUES (?, ?, ?, ?, ?)
            """, (id_proveedor, id_usuario, datetime.now(),
                  f'OFERTA-P{id_producto}-{int(datetime.now().timestamp())}', 'RECIBIDA'))
            id_compra = int(cursor.fetchone()[0])
        else:
            cursor.execute(f"SELECT ISNULL(MAX({id_compra_col}), 0) + 1 FROM COMPRA")
            id_compra = int(cursor.fetchone()[0])
            cursor.execute(f"""
                INSERT INTO COMPRA ({id_compra_col}, IdProveedor, IdUsuario, FechaCompra, NumeroDocumento, Estado)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id_compra, id_proveedor, id_usuario, datetime.now(),
                  f'OFERTA-P{id_producto}', 'RECIBIDA'))

        detalle = _columnas(cursor, 'DETALLE_COMPRA')
        id_detalle_col = _col(detalle, 'IdDetalleCompra', default='IdDetalleCompra')
        if _es_identidad(cursor, 'DETALLE_COMPRA', id_detalle_col):
            cursor.execute(f"""
                INSERT INTO DETALLE_COMPRA (IdCompra, IdProducto, Cantidad, CostoUnitario)
                OUTPUT INSERTED.{id_detalle_col}
                VALUES (?, ?, ?, ?)
            """, (id_compra, id_producto, 1, costo_compra))
            id_detalle = int(cursor.fetchone()[0])
        else:
            cursor.execute(f"SELECT ISNULL(MAX({id_detalle_col}), 0) + 1 FROM DETALLE_COMPRA")
            id_detalle = int(cursor.fetchone()[0])
            cursor.execute(f"""
                INSERT INTO DETALLE_COMPRA ({id_detalle_col}, IdCompra, IdProducto, Cantidad, CostoUnitario)
                VALUES (?, ?, ?, ?, ?)
            """, (id_detalle, id_compra, id_producto, 1, costo_compra))

    return {'producto_id': id_producto, 'concepto_id': id_concepto, 'nombre': nombre}
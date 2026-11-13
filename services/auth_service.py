"""Servicio de autenticación y gestión de cuentas."""
from __future__ import annotations

from typing import Any

from config import Config
from db import BusinessError, fetch_all, fetch_one, insert_returning, transaction
from security import hash_password, is_hashed, verify_password


def _sync_session(user: dict[str, Any]) -> dict[str, Any]:
    cliente_id = None
    if user["rol"] == Config.ROLE_CLIENT:
        cliente_id = ensure_client_profile(user)
    return {
        "id": user["IdUsuario"],
        "nombre": user["Nombre"],
        "apellido": user.get("Apellido", ""),
        "correo": user["Correo"],
        "rol": user["rol"],
        "cliente_id": cliente_id,
        "veterinario_id": user.get("IdVeterinario"),
    }


def ensure_client_profile(user: dict[str, Any]) -> int:
    """Garantiza que todo usuario Cliente Web tenga una fila en CLIENTE."""
    cliente = fetch_one("SELECT IdCliente FROM CLIENTE WHERE IdUsuario = ?", (user["IdUsuario"],))
    if cliente:
        return int(cliente["IdCliente"])

    cliente = fetch_one(
        "SELECT IdCliente FROM CLIENTE WHERE IdUsuario IS NULL AND UPPER(Correo) = UPPER(?)",
        (user["Correo"],),
    )
    if cliente:
        with transaction() as cur:
            cur.execute(
                "UPDATE CLIENTE SET IdUsuario = ? WHERE IdCliente = ?",
                (user["IdUsuario"], cliente["IdCliente"]),
            )
        return int(cliente["IdCliente"])

    cedula = f"WEB-{int(user['IdUsuario']):06d}"
    with transaction() as cur:
        return insert_returning(
            cur,
            """
            INSERT INTO CLIENTE (Nombre, Apellido, Cedula, Telefono, Correo, AceptaNotif, IdUsuario)
            OUTPUT INSERTED.IdCliente
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                user["Nombre"],
                user.get("Apellido", ""),
                cedula,
                user.get("Telefono"),
                user["Correo"],
                user["IdUsuario"],
            ),
        )


def authenticate(correo: str, password: str, expected_role: str | None = None) -> dict[str, Any]:
    correo = (correo or "").strip()
    if not correo or not password:
        raise BusinessError("Ingresa tu correo y contraseña.")

    row = fetch_one(
        """
        SELECT U.IdUsuario, U.Nombre, U.Apellido, U.Telefono, U.Correo, U.Contrasena,
               U.Estado, U.IdRol, R.NombreRol,
               (SELECT TOP 1 IdVeterinario FROM VETERINARIO V
                 WHERE V.IdUsuario = U.IdUsuario AND V.Estado = 'Activo') AS IdVeterinario
        FROM USUARIO U
        INNER JOIN ROL R ON R.IdRol = U.IdRol
        WHERE U.Correo = ?
        """,
        (correo,),
    )
    if not row:
        raise BusinessError("Correo o contraseña incorrectos.")
    if row["Estado"] != "Activo":
        raise BusinessError("La cuenta está inactiva. Contacta al administrador.")
    if not verify_password(row["Contrasena"], password):
        raise BusinessError("Correo o contraseña incorrectos.")

    if expected_role == "staff" and row["NombreRol"] == Config.ROLE_CLIENT:
        raise BusinessError("Esta cuenta es de cliente. Ingresa por la tienda en línea.")
    if expected_role == "client" and row["NombreRol"] != Config.ROLE_CLIENT:
        raise BusinessError("Esta cuenta es del personal de la clínica. Usa el acceso interno.")

    # Migra contraseñas planas heredadas a un hash seguro al iniciar sesión
    if not is_hashed(row["Contrasena"]):
        with transaction() as cur:
            cur.execute(
                "UPDATE USUARIO SET Contrasena = ? WHERE IdUsuario = ?",
                (hash_password(password), row["IdUsuario"]),
            )

    row["rol"] = row["NombreRol"]
    return _sync_session(row)


def register_client(data: dict[str, Any]) -> dict[str, Any]:
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    cedula = (data.get("cedula") or "").strip()
    correo = (data.get("correo") or "").strip()
    password = data.get("contrasena") or data.get("password") or ""
    telefono = (data.get("telefono") or "").strip() or None
    direccion = (data.get("direccion") or "").strip() or None

    if not all([nombre, apellido, cedula, correo, password]):
        raise BusinessError("Nombre, apellido, cédula, correo y contraseña son obligatorios.")
    if len(password) < 6:
        raise BusinessError("La contraseña debe tener al menos 6 caracteres.")

    if fetch_one("SELECT 1 AS x FROM USUARIO WHERE Correo = ?", (correo,)):
        raise BusinessError("Ese correo ya tiene una cuenta registrada.")

    role = fetch_one("SELECT IdRol FROM ROL WHERE NombreRol = ?", (Config.ROLE_CLIENT,))
    if not role:
        raise BusinessError("No existe el rol Cliente Web. Ejecuta la migración 001.")

    existing = fetch_one(
        "SELECT IdCliente, IdUsuario, UPPER(ISNULL(Correo,'')) AS CorreoActual FROM CLIENTE WHERE Cedula = ?",
        (cedula,),
    )
    if existing and existing["IdUsuario"]:
        raise BusinessError("Esa cédula ya tiene una cuenta de tienda. Inicia sesión o recupera tu contraseña.")
    if existing and existing["CorreoActual"] and existing["CorreoActual"] != correo.upper():
        raise BusinessError(
            "La cédula ya está registrada con otro correo. Acércate a la clínica para actualizar tus datos."
        )

    with transaction() as cur:
        user_id = insert_returning(
            cur,
            """
            INSERT INTO USUARIO (Nombre, Apellido, Telefono, Correo, Contrasena, Estado, IdRol)
            OUTPUT INSERTED.IdUsuario
            VALUES (?, ?, ?, ?, ?, 'Activo', ?)
            """,
            (nombre, apellido, telefono, correo, hash_password(password), role["IdRol"]),
        )

        if existing:
            cliente_id = int(existing["IdCliente"])
            cur.execute(
                """
                UPDATE CLIENTE
                SET IdUsuario = ?, Correo = COALESCE(NULLIF(Correo, ''), ?),
                    Telefono = COALESCE(NULLIF(Telefono, ''), ?),
                    Direccion = COALESCE(NULLIF(Direccion, ''), ?)
                WHERE IdCliente = ?
                """,
                (user_id, correo, telefono, direccion, cliente_id),
            )
        else:
            cliente_id = insert_returning(
                cur,
                """
                INSERT INTO CLIENTE (Nombre, Apellido, Cedula, Telefono, Correo, Direccion, AceptaNotif, IdUsuario)
                OUTPUT INSERTED.IdCliente
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (nombre, apellido, cedula, telefono, correo, direccion, user_id),
            )

    return {
        "id": user_id,
        "nombre": nombre,
        "apellido": apellido,
        "correo": correo,
        "rol": Config.ROLE_CLIENT,
        "cliente_id": cliente_id,
    }


def create_client_account(cliente_id: int, correo: str, password: str) -> dict[str, Any]:
    correo = (correo or "").strip()
    if not correo or not password:
        raise BusinessError("Correo y contraseña son obligatorios.")
    if len(password) < 6:
        raise BusinessError("La contraseña debe tener al menos 6 caracteres.")

    cliente = fetch_one("SELECT * FROM CLIENTE WHERE IdCliente = ?", (cliente_id,))
    if not cliente:
        raise BusinessError("Cliente no encontrado.", 404)
    if cliente["IdUsuario"]:
        raise BusinessError("Ese cliente ya tiene una cuenta de tienda vinculada.")

    role = fetch_one("SELECT IdRol FROM ROL WHERE NombreRol = ?", (Config.ROLE_CLIENT,))
    with transaction() as cur:
        user_id = insert_returning(
            cur,
            """
            INSERT INTO USUARIO (Nombre, Apellido, Telefono, Correo, Contrasena, Estado, IdRol)
            OUTPUT INSERTED.IdUsuario
            VALUES (?, ?, ?, ?, ?, 'Activo', ?)
            """,
            (
                cliente["Nombre"],
                cliente["Apellido"],
                cliente["Telefono"],
                correo,
                hash_password(password),
                role["IdRol"],
            ),
        )
        cur.execute("UPDATE CLIENTE SET IdUsuario = ? WHERE IdCliente = ?", (user_id, cliente_id))

    return {"usuario_id": user_id, "cliente_id": cliente_id, "correo": correo}


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    row = fetch_one("SELECT Contrasena FROM USUARIO WHERE IdUsuario = ?", (user_id,))
    if not row:
        raise BusinessError("Usuario no encontrado.", 404)
    if not verify_password(row["Contrasena"], current_password):
        raise BusinessError("La contraseña actual no es correcta.")
    if len(new_password or "") < 6:
        raise BusinessError("La nueva contraseña debe tener al menos 6 caracteres.")
    with transaction() as cur:
        cur.execute(
            "UPDATE USUARIO SET Contrasena = ? WHERE IdUsuario = ?",
            (hash_password(new_password), user_id),
        )


def list_users() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT U.IdUsuario, U.Nombre, U.Apellido, U.Correo, U.Telefono,
               U.Estado, U.FechaReg, R.NombreRol, V.IdVeterinario, V.NumRegistro
        FROM USUARIO U
        INNER JOIN ROL R ON R.IdRol = U.IdRol
        LEFT JOIN VETERINARIO V ON V.IdUsuario = U.IdUsuario
        ORDER BY U.Nombre, U.Apellido
        """
    )


def create_staff_user(data: dict[str, Any]) -> dict[str, Any]:
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    correo = (data.get("correo") or "").strip()
    password = data.get("contrasena") or data.get("password") or ""
    rol_nombre = (data.get("rol") or "").strip()
    telefono = (data.get("telefono") or "").strip() or None

    if not all([nombre, apellido, correo, password, rol_nombre]):
        raise BusinessError("Nombre, apellido, correo, contraseña y rol son obligatorios.")
    if len(password) < 6:
        raise BusinessError("La contraseña debe tener al menos 6 caracteres.")
    if rol_nombre == Config.ROLE_CLIENT:
        raise BusinessError("Las cuentas de cliente se crean desde la tienda o desde la ficha del cliente.")
    if rol_nombre not in Config.STAFF_ROLES:
        raise BusinessError("Rol inválido.")
    if fetch_one("SELECT 1 AS x FROM USUARIO WHERE Correo = ?", (correo,)):
        raise BusinessError("Ese correo ya está registrado.")

    role = fetch_one("SELECT IdRol FROM ROL WHERE NombreRol = ?", (rol_nombre,))
    if not role:
        raise BusinessError("El rol indicado no existe.")

    with transaction() as cur:
        user_id = insert_returning(
            cur,
            """
            INSERT INTO USUARIO (Nombre, Apellido, Telefono, Correo, Contrasena, Estado, IdRol)
            OUTPUT INSERTED.IdUsuario
            VALUES (?, ?, ?, ?, ?, 'Activo', ?)
            """,
            (nombre, apellido, telefono, correo, hash_password(password), role["IdRol"]),
        )
        if rol_nombre == Config.ROLE_VET:
            num_registro = (data.get("num_registro") or f"VET-{user_id:04d}").strip()
            cur.execute(
                """
                INSERT INTO VETERINARIO (NumRegistro, Estado, IdUsuario)
                VALUES (?, 'Activo', ?)
                """,
                (num_registro, user_id),
            )
    return {"id": user_id, "correo": correo, "rol": rol_nombre}


def set_user_state(usuario_id: int, estado: str) -> None:
    if estado not in ("Activo", "Inactivo"):
        raise BusinessError("Estado de usuario inválido.")
    with transaction() as cur:
        cur.execute("UPDATE USUARIO SET Estado = ? WHERE IdUsuario = ?", (estado, usuario_id))
        cur.execute("UPDATE VETERINARIO SET Estado = ? WHERE IdUsuario = ?", (estado, usuario_id))


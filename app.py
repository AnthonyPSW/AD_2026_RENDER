from flask import Flask, jsonify, request
from flask_cors import CORS
from contextlib import closing
import os
import certifi
import pytds
import threading

app = Flask(__name__)
CORS(app)

product_lock = threading.Lock()


# ==========================================
# CONEXIÓN A AZURE SQL SERVER
# ==========================================

def getConnection():
    return pytds.connect(
        server=os.environ["DB_SERVER"],
        database=os.environ["DB_DATABASE"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=int(os.getenv("DB_PORT", "1433")),
        cafile=certifi.where(),
        validate_host=True,
        row_strategy=pytds.namedtuple_row_strategy,
        timeout=30
    )


# ==========================================
# PROBAR CONEXIÓN
# ==========================================

@app.route("/test-db", methods=["GET"])
def test_db():
    try:
        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT DB_NAME() AS database_name")
                database = cursor.fetchone()[0]

        return jsonify({
            "mensaje": "Conexion exitosa",
            "base_datos": database
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


# ==========================================
# OBTENER TODOS LOS PRODUCTOS
# ==========================================

@app.route("/api/products", methods=["GET"])
def get_products():
    try:
        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:

                cursor.execute("""
                    SELECT ID, names, price, stock
                    FROM PRODUCTS_VW
                """)

                products = []

                for row in cursor.fetchall():
                    products.append({
                        "ID": row.ID,
                        "NOMBRE": row.names,
                        "PRECIO": float(row.price) if row.price is not None else None,
                        "STOCK": row.stock
                    })

        return jsonify(products), 200

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


# ==========================================
# OBTENER PRODUCTO POR ID
# ==========================================

@app.route("/api/products/<int:id>", methods=["GET"])
def get_product(id):
    try:
        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:

                cursor.execute("""
                    SELECT ID, names, price, stock
                    FROM PRODUCTS_VW
                    WHERE ID = %s
                """, (id,))

                row = cursor.fetchone()

        if row:
            return jsonify({
                "ID": row.ID,
                "NOMBRE": row.names,
                "PRECIO": float(row.price) if row.price is not None else None,
                "STOCK": row.stock
            }), 200

        return jsonify({
            "mensaje": "Producto no encontrado"
        }), 404

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


# ==========================================
# CREAR PRODUCTO
# ==========================================

@app.route("/api/products", methods=["POST"])
def create_product():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "mensaje": "No existen datos validos"
            }), 400

        nombre = data.get("nombre")
        precio = data.get("precio")
        stock = data.get("stock")

        if not nombre or precio is None or stock is None:
            return jsonify({
                "mensaje": "Faltan datos requeridos"
            }), 400

        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:

                cursor.execute(
                    "EXEC PRODUCTS_INSERT_SP %s, %s, %s",
                    (nombre, precio, stock)
                )

                conn.commit()

        return jsonify({
            "mensaje": "Producto creado exitosamente"
        }), 201

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


# ==========================================
# ACTUALIZAR PRODUCTO SIN CONTROLES
# ==========================================

@app.route("/api/products", methods=["PUT"])
def update_product():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "error": "sin data"
            }), 400

        campos = ("ID", "names", "price", "stock")

        if any(data.get(campo) is None for campo in campos):
            return jsonify({
                "error": "Faltan datos requeridos"
            }), 400

        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:

                cursor.execute("""
                    UPDATE PRODUCTS
                    SET names = %s,
                        price = %s,
                        stock = %s
                    WHERE ID = %s
                """, (
                    data["names"],
                    data["price"],
                    data["stock"],
                    data["ID"]
                ))

                if cursor.rowcount == 0:
                    conn.rollback()
                    return jsonify({
                        "msj": "registro no encontrado"
                    }), 404

                conn.commit()

        return jsonify({
            "mensaje": "Producto actualizado exitosamente"
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "Error al actualizar",
            "error": str(e)
        }), 500


# ==========================================
# ACTUALIZAR PRODUCTO CON BLOQUEO
# ==========================================

@app.route("/api/products/lock", methods=["POST"])
def lock_product():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "error": "sin data"
            }), 400

        campos = ("ID", "names", "price", "stock")

        if any(data.get(campo) is None for campo in campos):
            return jsonify({
                "error": "Faltan datos requeridos"
            }), 400

        # Bloqueo local al proceso de Python
        with product_lock:

            print("Entra al bloqueo")

            with closing(getConnection()) as conn:
                with closing(conn.cursor()) as cursor:

                    cursor.execute("""
                        UPDATE PRODUCTS
                        SET names = %s,
                            price = %s,
                            stock = %s
                        WHERE ID = %s
                    """, (
                        data["names"],
                        data["price"],
                        data["stock"],
                        data["ID"]
                    ))

                    if cursor.rowcount == 0:
                        conn.rollback()
                        return jsonify({
                            "msj": "registro no encontrado"
                        }), 404

                    conn.commit()

            print("Sale del bloqueo")

        return jsonify({
            "mensaje": "Producto actualizado con bloqueo exitosamente"
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "Error al bloquear",
            "error": str(e)
        }), 500


# ==========================================
# ACTUALIZAR PRODUCTO CON VERSIONADO
# CONTROL DE CONCURRENCIA OPTIMISTA
# ==========================================

@app.route("/api/products/version", methods=["PUT"])
def update_version():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "error": "sin data"
            }), 400

        campos = ("ID", "names", "price", "stock", "version")

        if any(data.get(campo) is None for campo in campos):
            return jsonify({
                "error": "Faltan datos requeridos"
            }), 400

        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:

                cursor.execute("""
                    UPDATE PRODUCTS
                    SET names = %s,
                        price = %s,
                        stock = %s,
                        version = version + 1
                    WHERE ID = %s
                      AND version = %s
                """, (
                    data["names"],
                    data["price"],
                    data["stock"],
                    data["ID"],
                    data["version"]
                ))

                if cursor.rowcount == 0:

                    conn.rollback()

                    cursor.execute("""
                        SELECT version
                        FROM PRODUCTS
                        WHERE ID = %s
                    """, (data["ID"],))

                    row = cursor.fetchone()

                    if row:
                        producto_actual = {
                            "id": data["ID"],
                            "version": row.version
                        }

                        return jsonify({
                            "msj": "Producto ya actualizado por otro usuario",
                            "error": producto_actual
                        }), 409

                    return jsonify({
                        "msj": "registro no encontrado"
                    }), 404

                conn.commit()

        return jsonify({
            "mensaje": "Producto actualizado exitosamente",
            "version": data["version"] + 1
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "Error al actualizar",
            "error": str(e)
        }), 500


def enviar_correo_brevo(total_productos):
    api_key = os.getenv("BREVO_API_KEY")
    remitente = os.getenv("EMAIL_REMITENTE")
    destino = os.getenv("EMAIL_DESTINO")

    if not all((api_key, remitente, destino)):
        raise RuntimeError("Falta configurar Brevo en las variables de entorno")

    payload = {
        "sender": {"name": "Práctica Aplicaciones Distribuidas", "email": remitente},
        "to": [{"email": destino}],
        "subject": "Procesamiento de productos finalizado",
        "textContent": (
            "El procesamiento finalizó correctamente.\n"
            f"Total de productos registrados: {total_productos}.\n"
            "Origen: API Flask desplegada en Render."
        ),
    }
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if response.status_code != 201:
        raise RuntimeError(f"Brevo rechazó la solicitud (HTTP {response.status_code})")

    respuesta = response.json()
    return respuesta.get("messageId")


@app.route("/api/procesar", methods=["POST"])
def procesar_productos_y_notificar():
    clave_esperada = os.getenv("PROCESS_API_KEY", "")
    clave_recibida = request.headers.get("X-API-Key", "")

    if not clave_esperada:
        return jsonify({"mensaje": "Falta configurar PROCESS_API_KEY"}), 503
    if not hmac.compare_digest(clave_recibida, clave_esperada):
        return jsonify({"mensaje": "No autorizado"}), 401

    try:
        with closing(getConnection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT COUNT(*) FROM PRODUCTS_VW")
                total_productos = int(cursor.fetchone()[0])
    except Exception:
        app.logger.exception("Fallo durante la consulta de productos")
        return jsonify({
            "procesamiento": "error",
            "mensaje": "No se pudo consultar Azure SQL"
        }), 500

    try:
        message_id = enviar_correo_brevo(total_productos)
    except (requests.RequestException, RuntimeError, ValueError):
        app.logger.exception("Falló la solicitud de correo a Brevo")
        return jsonify({
            "procesamiento": "finalizado",
            "total_productos": total_productos,
            "notificacion": "error",
            "mensaje": "La consulta terminó, pero Brevo no aceptó el correo"
        }), 502

    return jsonify({
        "procesamiento": "finalizado",
        "total_productos": total_productos,
        "notificacion": "aceptada_por_brevo",
        "messageId": message_id,
    }), 200



# ==========================================
# INICIAR APLICACIÓN
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False
    )
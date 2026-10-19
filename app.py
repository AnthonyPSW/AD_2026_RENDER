from flask import Flask, jsonify, request
import os
import certifi
import pytds


app = Flask(__name__)
CORS(app)

def getConnection():
    return pytds.connect(
        server=os.environ["DB_SERVER"],
        database=os.environ["DB_DATABASE"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=int(os.getenv("DB_PORT", "1433")),
        cafile= certifi.where(),
        validate_host=True,
    )

@app.route("/test-db", methods=["GET"])
def test_db():
    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("SELECT DB_NAME()")
        database = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "mensaje": "Conexion exitosa",
            "base_datos": database
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


@app.route("/api/products", methods=["GET"])
def get_products():
    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("""SELECT ID, names, price, stock FROM PRODUCTS_VW""")
        products = []  

        for row in cursor.fetchall():
            products.append ({
                "ID": row.ID,
                "NOMBRE": row.names,
                "PRECIO": row.price,
                "STOCK": row.stock
            } )
        cursor.close()
        conn.close()
        return jsonify(products), 200

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500


@app.route("/api/products/<int:id>", methods=["GET"])
def get_product(id):
    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("""SELECT ID, names, price, stock FROM PRODUCTS_VW WHERE ID = ?""", (id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:    
            return jsonify({
                "ID": row.ID,
                "NOMBRE": row.names,
                "PRECIO": row.price,
                "STOCK": row.stock
            }
            ),200
        return jsonify({"mensaje": "Producto no encontrado"}), 404

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

@app.route("/api/products", methods=["POST"])

def create_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"mensaje": "No existen datos validos"}), 400
        nombre = data.get("nombre")
        precio = data.get("precio")
        stock = data.get("stock")
        if not nombre or precio is None or stock is None:
            return jsonify({"mensaje": "Faltan datos requeridos"}), 400

        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("EXEC PRODUCTS_INSERT_SP ?, ?, ?", (nombre, precio, stock))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Producto creado exitosamente"}), 201

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500



##update sin controles

@app.route("/api/products", methods=["PUT"])
def update_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "sin data"}), 400
        conn = getConnection()
        cursor = conn.cursor()
        
        time.sleep(5) # Simula un retraso de 5 segundos
        cursor.execute("UPDATE PRODUCTS SET names = ?, price = ?, stock = ? WHERE ID = ?", 
                       (data.get("names"), data.get("price"), data.get("stock"), data.get("ID")))
        
        if cursor.rowcount == 0:
           conn.rollback()
           cursor.close()
           conn.close()
           return jsonify({"msj": "registro no encontrado"}), 404
       
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"mensaje": "Producto actualizado exitosamente"}), 200
    except Exception as e:
        return jsonify({
            "mensaje": "Error al actualizar",
            "error": str(e)
        }), 500

import threading
product_lock = threading.Lock()
@app.route("/api/products/lock", methods=["POST"])
def lock_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "sin data"}), 400
        with product_lock:
            print("Entra al bloqueo")
            conn = getConnection()
            cursor = conn.cursor()
            cursor.execute("UPDATE PRODUCTS SET names = ?, price = ?, stock = ? WHERE ID = ?",
                           (data.get("names"), data.get("price"), data.get("stock"), data.get("ID")))
            if cursor.rowcount == 0:
                conn.rollback()
                cursor.close()
                conn.close()
                return jsonify({"msj": "registro no encontrado"}), 404
            conn.commit()
            cursor.close()
            conn.close()
            print("Sale del bloqueo")
           
        return jsonify({"mensaje": "Producto bloqueado exitosamente"}), 200
    except Exception as e:
        return jsonify({
            "mensaje": "Error al bloquear",
            "error": str(e)
        }), 500

@app.route("/api/products/version", methods=["PUT"])
def update_version():
    try:
        data= request.get_json()
        if not data:
            return jsonify({"error": "sin data"}), 400
        
        if data.get("version") is None:
            return jsonify({"error": "versión no proporcionada"}), 400
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("UPDATE PRODUCTS SET names = ?, price = ?, stock = ?, version = version + 1 WHERE ID = ? AND version = ?", 
                       (data.get("names"), data.get("price"), data.get("stock"), data.get("ID"), data.get("version")))
        
        if cursor.rowcount == 0:
            cursor.execute("SELECT version FROM PRODUCTS WHERE ID = ?", (data.get("ID"),))
            row = cursor.fetchone()
            conn.rollback()
            cursor.close()
            conn.close()
            if row:
                producto_actual = {
                    "id" : data.get("ID"),
                    "version": row.version
                }
                return jsonify({
                    "msj" : "Ya actuazalizado por otro usuario",
                    "error": producto_actual
                })
            else:
                return jsonify({"msj": "registro no encontrado"}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"mensaje": "Producto actualizado exitosamente"}), 200
    except Exception as e:
        return jsonify({
            "mensaje": "Error al actualizar",
            "error": str(e)
        }), 500
    

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=5000, debug=True)
"""
scripts/webhook.py
==================
Webhook HTTP que n8n llama al terminar cada flujo RPA.
Ejecuta pipeline.py --solo-nuevos y retorna el resultado.

Iniciar:
  source venv_datos/bin/activate
  python scripts/webhook.py

Ejecutar como servicio (ver instrucciones abajo).
Puerto: 5000
"""

import subprocess
import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# Ruta del proyecto
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE, "logs", "pipeline.log")
PYTHON = os.path.join(BASE, "venv_datos", "bin", "python")
PIPELINE = os.path.join(BASE, "transform", "pipeline.py")

# Log del webhook
logging.basicConfig(
    filename=os.path.join(BASE, "logs", "webhook.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


@app.route("/health", methods=["GET"])
def health():
    """Verificar que el webhook está activo."""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/ejecutar-pipeline", methods=["POST"])
def ejecutar_pipeline():
    """
    n8n llama este endpoint al terminar un flujo RPA.
    Responde inmediatamente y ejecuta pipeline.py en segundo plano.
    """
    data = request.get_json(silent=True) or {}
    indicador = data.get("indicador", "TODOS")

    logging.info(f"Pipeline iniciado por webhook. Indicador: {indicador}")

    # Comando a ejecutar
    if indicador != "TODOS":
        cmd = [PYTHON, PIPELINE, "--indicador", indicador]
    else:
        cmd = [PYTHON, PIPELINE, "--solo-nuevos"]

    # Ejecutar en segundo plano — responde inmediatamente a n8n
    import threading

    def ejecutar_en_background():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=BASE
            )
            with open(LOG_PATH, "a") as f:
                f.write(f"\n[{datetime.now()}] Ejecutado por webhook\n")
                f.write(result.stdout)
                if result.stderr:
                    f.write(result.stderr)
            if result.returncode == 0:
                logging.info(f"Pipeline completado OK. Indicador: {indicador}")
            else:
                logging.error(f"Pipeline falló. stderr: {result.stderr[:200]}")
        except Exception as e:
            logging.error(f"Error en background: {str(e)}")

    hilo = threading.Thread(target=ejecutar_en_background, daemon=True)
    hilo.start()

    # Responde inmediatamente a n8n
    return jsonify({
        "status": "ok",
        "indicador": indicador,
        "timestamp": datetime.now().isoformat(),
        "mensaje": "Pipeline iniciado en segundo plano"
    }), 200


@app.route("/estado", methods=["GET"])
def estado():
    """Retorna las últimas 20 líneas del log del pipeline."""
    try:
        with open(LOG_PATH, "r") as f:
            lineas = f.readlines()
        return jsonify({
            "status": "ok",
            "ultimas_lineas": lineas[-20:]
        })
    except FileNotFoundError:
        return jsonify({"status": "ok", "ultimas_lineas": []})


if __name__ == "__main__":
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    print("Webhook iniciado en http://0.0.0.0:5000")
    print(f"Base: {BASE}")
    print(f"Pipeline: {PIPELINE}")
    app.run(host="0.0.0.0", port=5000, debug=False)
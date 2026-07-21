import os
from flask import Flask, render_template, request

app = Flask(__name__)

def formatear_clp(valor):
    """Formatea un número a moneda chilena CLP (ej: $ 1.000.000)"""
    return f"$ {round(valor):,.0f}".replace(",", ".")

@app.route("/", methods=["GET", "POST"])
def index():
    resultado = None
    monto_inicial_val = ""
    plazo_val = ""
    tipo_plazo_val = "meses"
    tasa_val = ""
    ipc_manual_val = ""

    if request.method == "POST":
        try:
            monto_str = request.form.get("monto_inicial", "0").replace(".", "").replace("$", "").strip()
            monto_inicial = float(monto_str)
            
            plazo = int(request.form.get("plazo", 0))
            tipo_plazo = request.form.get("tipo_plazo", "meses")
            tasa = float(request.form.get("tasa", 0.0))
            ipc_acumulado = float(request.form.get("ipc_manual", 0.0) or 0.0)

            monto_inicial_val = request.form.get("monto_inicial", "")
            plazo_val = request.form.get("plazo", "")
            tipo_plazo_val = tipo_plazo
            tasa_val = request.form.get("tasa", "")
            ipc_manual_val = request.form.get("ipc_manual", "")

            total_meses = plazo * 12 if tipo_plazo == "años" else plazo

            if monto_inicial <= 0 or total_meses <= 0 or tasa < 0:
                raise ValueError("Los valores ingresados deben ser mayores a cero.")

            # 1. Interés compuesto normal periodo a periodo
            capital_actual = monto_inicial
            interes_acumulado = 0.0
            tabla_desglose = []

            for i in range(1, total_meses + 1):
                capital_inicial_periodo = capital_actual
                interes_periodo = capital_actual * (tasa / 100.0)
                
                capital_actual += interes_periodo
                interes_acumulado += interes_periodo

                tabla_desglose.append({
                    "periodo": f"Mes {i}",
                    "capital_inicial": formatear_clp(capital_inicial_periodo),
                    "interes_ganado": formatear_clp(interes_periodo),
                    "interes_acumulado": formatear_clp(interes_acumulado),
                    "saldo_pre_ipc": formatear_clp(capital_actual)
                })

            # 2. Aplicación del IPC acumulado sobre (Monto Inicial + Intereses)
            monto_con_intereses = capital_actual
            monto_reajuste_ipc = monto_con_intereses * (ipc_acumulado / 100.0)
            monto_final = monto_con_intereses + monto_reajuste_ipc

            resultado = {
                "monto_inicial": formatear_clp(monto_inicial),
                "plazo": f"{plazo} {tipo_plazo}",
                "tasa": f"{tasa}% por periodo",
                "ipc_acumulado": f"{ipc_acumulado:.2f}% (acumulado periodo)",
                "subtotal_intereses": formatear_clp(interes_acumulado),
                "monto_con_intereses": formatear_clp(monto_con_intereses),
                "reajuste_ipc_monto": formatear_clp(monto_reajuste_ipc),
                "monto_final": formatear_clp(monto_final),
                "total_ganancia": formatear_clp(interes_acumulado + monto_reajuste_ipc),
                "tipo_periodo": "Periodo (Mes)",
                "tabla_desglose": tabla_desglose
            }

        except Exception as e:
            resultado = {"error": f"Ocurrió un error al procesar el cálculo: {str(e)}"}

    return render_template(
        "index.html",
        resultado=resultado,
        monto_inicial=monto_inicial_val,
        plazo=plazo_val,
        tipo_plazo=tipo_plazo_val,
        tasa=tasa_val,
        ipc_manual=ipc_manual_val
    )

if __name__ == "__main__":
    app.run(debug=True)
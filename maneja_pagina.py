import os
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta  # O cálculo manual de meses
from flask import Flask, render_template, request

app = Flask(__name__)

# Credenciales de la API del Banco Central (leídas desde entorno o con respaldo local)
BC_USER = os.getenv("BC_USER", "s.bustamantemunoz@gmail.com")
BC_PASS = os.getenv("BC_PASS", "$2a$10$OT19LOAZ5QD57PJqhLBIOu0xLDvtC56E5pILvWLC195.ApA1T1Pmq")

# Serie oficial de Variación Mensual del IPC (Base 2023=100)
SERIE_IPC_VAR = "F073.IPC.VAR.Z.2023.M"

def obtener_ipc_mes(fecha_str):
    """
    Consulta el IPC mensual a la API del Banco Central para una fecha 'YYYY-MM'.
    Devuelve la variación en porcentaje (%) o 0.0 si falla o no hay datos.
    """
    if not fecha_str or not BC_PASS:
        return 0.0

    try:
        dt = datetime.strptime(fecha_str, "%Y-%m")
        first_date = dt.strftime("%Y-%m-01")
        last_date = dt.strftime("%Y-%m-28")

        # Evitar consultar fechas futuras
        now = datetime.now()
        if dt.year > now.year or (dt.year == now.year and dt.month > now.month):
            return 0.0

        params = {
            'user': BC_USER,
            'pass': BC_PASS,
            'firstdate': first_date,
            'lastdate': last_date,
            'timeseries': SERIE_IPC_VAR,
            'function': 'GetSeries'
        }

        url = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("Codigo") == 0:
                obs = data.get("Series", {}).get("Obs", [])
                if obs and len(obs) > 0:
                    val_str = obs[0].get("value")
                    if val_str and val_str != "ND":
                        return float(val_str)
            else:
                print(f"Respuesta API BC: {data.get('Descripcion')}")

    except Exception as e:
        print(f"Error consultando la API del Banco Central: {e}")
        
    return 0.0

def formatear_clp(valor):
    """Formatea un número a moneda chilena CLP (ej: $ 1.000.000)"""
    return f"$ {valore_redondeado(valor):,.0f}".replace(",", ".")

def valore_redondeado(val):
    return round(val, 0)

@app.route("/", methods=["GET", "POST"])
def index():
    resultado = None
    monto_inicial_val = ""
    plazo_val = ""
    tipo_plazo_val = "meses"
    tasa_val = ""
    fecha_inicio_val = ""

    if request.method == "POST":
        try:
            # Limpiar el formato de montos con puntos si el usuario los envía
            monto_str = request.form.get("monto_inicial", "0").replace(".", "").replace("$", "").strip()
            monto_inicial = float(monto_str)
            
            plazo = int(request.form.get("plazo", 0))
            tipo_plazo = request.form.get("tipo_plazo", "meses")
            tasa = float(request.form.get("tasa", 0.0))
            fecha_inicio = request.form.get("fecha_inicio", "").strip()

            monto_inicial_val = request.form.get("monto_inicial", "")
            plazo_val = request.form.get("plazo", "")
            tipo_plazo_val = tipo_plazo
            tasa_val = request.form.get("tasa", "")
            fecha_inicio_val = fecha_inicio

            # Normalizar plazo a meses para el cálculo interno
            total_meses = plazo * 12 if tipo_plazo == "años" else plazo

            if monto_inicial <= 0 or total_meses <= 0 or tasa < 0:
                raise ValueError("Los valores ingresados deben ser mayores a cero.")

            # Preparar fecha inicial para el desglose con IPC
            current_date = None
            if fecha_inicio:
                current_date = datetime.strptime(fecha_inicio, "%Y-%m")

            capital_actual = monto_inicial
            interes_acumulado = 0.0
            tabla_desglose = []

            for i in range(1, total_meses + 1):
                capital_inicial_periodo = capital_actual
                
                # Obtener IPC real si hay fecha seleccionada
                ipc_porcentaje = 0.0
                if current_date:
                    fecha_str_consulta = current_date.strftime("%Y-%m")
                    ipc_porcentaje = obtener_ipc_mes(fecha_str_consulta)

                # Calcular interés del periodo (ajustado opcionalmente por IPC si deseas sumarlo al capital o tasa)
                # Aplicamos la tasa de interés compuesta sobre el capital actual
                interes_periodo = capital_actual * (tasa / 100.0)
                
                # Si el IPC aplica como reajuste al capital o se muestra en la tabla:
                # (Aquí sumamos el interés clásico, y guardamos el IPC para la trazabilidad de la tabla)
                capital_actual += interes_periodo
                interes_acumulado += interes_periodo

                # Etiqueta de periodo para la tabla
                nombre_periodo = f"Mes {i}"

                tabla_desglose.append({
                    "periodo": nombre_periodo,
                    "capital_inicial": formatear_clp(capital_inicial_periodo),
                    "ipc_aplicado": f"{ipc_porcentaje:.2f}%" if fecha_inicio else None,
                    "interes_ganado": formatear_clp(interes_periodo),
                    "interes_acumulado": formatear_clp(interes_acumulado),
                    "saldo_final": formatear_clp(capital_actual)
                })

                # Incrementar mes para la siguiente iteración
                if current_date:
                    current_date = current_date + relativedelta(months=1) if 'relativedelta' in globals() else current_date.replace(day=1) + relativedelta(months=1) if 'relativedelta' in globals() else current_date

            resultado = {
                "monto_inicial": formatear_clp(monto_inicial),
                "plazo": f"{plazo} {tipo_plazo}",
                "tasa": f"{tasa}% por periodo",
                "monto_final": formatear_clp(capital_actual),
                "total_intereses": formatear_clp(interes_acumulado),
                "tipo_periodo": "Periodo (Mes)",
                "tabla_desglose": tabla_desglose
            }

        except Exception as e:
            resultado = {"error": f"Ocurrió un error al procesar el cálculo: {str_error(e)}"}

    return render_template(
        "index.html",
        resultado=resultado,
        monto_inicial=monto_inicial_val,
        plazo=plazo_val,
        tipo_plazo=tipo_plazo_val,
        tasa=tasa_val,
        fecha_inicio=fecha_inicio_val
    )

def str_error(e):
    return str(e)

if __name__ == "__main__":
    app.run(debug=True)
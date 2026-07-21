import os
from datetime import datetime
from flask import Flask, render_template, request
import bcchapi

app = Flask(__name__)

def obtener_ipc_bcch(fecha_inicio):
    """
    Obtiene la variación mensual del IPC desde fecha_inicio hasta la actualidad
    usando la API del Banco Central de Chile.
    """
    user = os.environ.get('BCCH_USER')
    password = os.environ.get('BCCH_PWD')

    if not user or not password:
        return None, "Faltan las credenciales de la API del Banco Central (BCCH_USER y BCCH_PWD)."

    try:
        siete = bcchapi.Siete(user, password)
        f_desde = fecha_inicio.strftime('%Y-%m-01')
        f_hasta = datetime.now().strftime('%Y-%m-%d')

        # Serie oficial de Variación Mensual del IPC
        df = siete.cuadro(
            series=["F073.IPC.VAR.Z.2023.M"],
            nombres=["ipc_var"],
            desde=f_desde,
            hasta=f_hasta
        )

        variaciones = []
        for index, row in df.iterrows():
            variaciones.append({
                'periodo': index.strftime('%m-%Y'),
                'ipc_pct': float(row['ipc_var'])
            })

        return variaciones, None

    except Exception as e:
        return None, f"Error al conectar con la API del Banco Central: {str(e)}"


@app.route('/', methods=['GET', 'POST'])
def index():
    monto_inicial = ""
    plazo = ""
    tipo_plazo = "meses"
    tasa = ""
    fecha_inicio_str = ""
    resultado = None

    if request.method == 'POST':
        try:
            monto_texto = request.form.get('monto_inicial', '').replace('.', '')
            monto_inicial = float(monto_texto) if monto_texto else 0.0
            
            plazo = int(request.form.get('plazo', 0))
            tipo_plazo = request.form.get('tipo_plazo', 'meses')
            tasa = float(request.form.get('tasa', 0))
            fecha_inicio_str = request.form.get('fecha_inicio', '')

            if monto_inicial <= 0 or plazo <= 0 or tasa <= 0:
                resultado = {"error": "Por favor, ingrese valores mayores a cero en todos los campos requeridos."}
            else:
                tasa_decimal = tasa / 100
                desglose = []
                capital_actual = monto_inicial
                
                # --- CONSULTA DE IPC SI SE INGRESA FECHA DE INICIO ---
                datos_ipc = []
                error_ipc = None
                if fecha_inicio_str:
                    f_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m')
                    datos_ipc, error_ipc = obtener_ipc_bcch(f_inicio)

                if error_ipc:
                    resultado = {"error": error_ipc}
                else:
                    # --- GENERACIÓN DEL DESGLOSE MES A MES / AÑO A AÑO ---
                    for periodo in range(1, plazo + 1):
                        # 1. Obtener IPC del periodo correspondiente si existe
                        ipc_mes_pct = 0.0
                        if datos_ipc and (periodo - 1) < len(datos_ipc):
                            ipc_mes_pct = datos_ipc[periodo - 1]['ipc_pct']
                        
                        # 2. Reajuste por IPC sobre el capital inicial del periodo
                        monto_reajustado_ipc = capital_actual * (1 + (ipc_mes_pct / 100))
                        
                        # 3. Cálculo de interés sobre el monto reajustado
                        interes_periodo = monto_reajustado_ipc * tasa_decimal
                        saldo_final = monto_reajustado_ipc + interes_periodo
                        interes_acumulado = saldo_final - monto_inicial

                        desglose.append({
                            "periodo": periodo,
                            "capital_inicial": f"$ {int(round(capital_actual)):,}".replace(",", "."),
                            "ipc_aplicado": f"{ipc_mes_pct}%" if fecha_inicio_str else "N/A",
                            "interes_ganado": f"$ {int(round(interes_periodo)):,}".replace(",", "."),
                            "saldo_final": f"$ {int(round(saldo_final)):,}".replace(",", "."),
                            "interes_acumulado": f"$ {int(round(interes_acumulado)):,}".replace(",", ".")
                        })
                        capital_actual = saldo_final

                    monto_final = capital_actual
                    total_intereses = monto_final - monto_inicial

                    resultado = {
                        "monto_inicial": f"$ {int(monto_inicial):,}".replace(",", "."),
                        "plazo": f"{plazo} {tipo_plazo}",
                        "tasa": f"{tasa}%",
                        "monto_final": f"$ {int(round(monto_final)):,}".replace(",", "."),
                        "total_intereses": f"$ {int(round(total_intereses)):,}".replace(",", "."),
                        "tipo_periodo": "Mes" if tipo_plazo == "meses" else "Año",
                        "tabla_desglose": desglose
                    }
                
            monto_inicial = request.form.get('monto_inicial', '')

        except ValueError:
            resultado = {"error": "Error al procesar los datos. Verifique los números ingresados."}

    return render_template('index.html', 
                           monto_inicial=monto_inicial, 
                           plazo=plazo, 
                           tipo_plazo=tipo_plazo, 
                           tasa=tasa, 
                           fecha_inicio=fecha_inicio_str,
                           resultado=resultado)

if __name__ == '__main__':
    app.run(debug=True)
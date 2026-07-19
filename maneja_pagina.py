from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    monto_inicial = ""
    plazo = ""
    tipo_plazo = "meses"
    tasa = ""
    resultado = None

    if request.method == 'POST':
        try:
            monto_texto = request.form.get('monto_inicial', '').replace('.', '')
            monto_inicial = float(monto_texto) if monto_texto else 0.0
            
            plazo = int(request.form.get('plazo', 0))
            tipo_plazo = request.form.get('tipo_plazo', 'meses')
            tasa = float(request.form.get('tasa', 0))

            if monto_inicial <= 0 or plazo <= 0 or tasa <= 0:
                resultado = {"error": "Por favor, ingrese valores mayores a cero en todos los campos."}
            else:
                tasa_decimal = tasa / 100
                
                # --- GENERACIÓN DEL DESGLOSE MES A MES / AÑO A AÑO ---
                desglose = []
                capital_actual = monto_inicial
                
                for periodo in range(1, plazo + 1):
                    interes_periodo = capital_actual * tasa_decimal
                    saldo_final = capital_actual + interes_periodo
                    interes_acumulado = saldo_final - monto_inicial
                    
                    desglose.append({
                        "periodo": periodo,
                        "capital_inicial": f"$ {int(round(capital_actual)):,}".replace(",", "."),
                        "interes_ganado": f"$ {int(round(interes_periodo)):,}".replace(",", "."),
                        "saldo_final": f"$ {int(round(saldo_final)):,}".replace(",", "."),
                        "interes_acumulado": f"$ {int(round(interes_acumulado)):,}".replace(",", ".")
                    })
                    capital_actual = saldo_final
                # -----------------------------------------------------

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
                           resultado=resultado)

if __name__ == '__main__':
    app.run(debug=True)
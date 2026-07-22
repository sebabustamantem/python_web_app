import os
from datetime import datetime
from typing import Any, Dict, List
import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request

app = Flask(__name__)

CSV_FILE = "ipc_historico.csv"


class IPCService:
    """Servicio de extracción del porcentaje IPC Mensual desde el SII."""

    BASE_URL = "https://www.sii.cl/valores_y_fechas/utm/utm{year}.htm"
    TARGET_COL_INDEX = 4  # Columna IPC Mensual

    MONTHS_MAP = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        })

    def fetch_ipc_series(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as err:
            raise ValueError(f"Formato de fecha inválido (use YYYY-MM-DD): {err}")

        years = range(start_dt.year, end_dt.year + 1)
        all_records: List[Dict[str, Any]] = []

        for year in years:
            records = self._scrape_mensual_ipc(year)
            all_records.extend(records)

        if not all_records:
            return []

        df = pd.DataFrame(all_records)
        mask = (df["fecha_dt"] >= start_dt) & (df["fecha_dt"] <= end_dt)
        filtered_df = df.loc[mask].sort_values(by="fecha_dt")

        result: List[Dict[str, Any]] = []
        for _, row in filtered_df.iterrows():
            result.append({
                "fecha": row["fecha_dt"].strftime("%Y-%m-%d"),
                "valor": float(row["valor"]),
            })

        return result

    def _scrape_mensual_ipc(self, year: int) -> List[Dict[str, Any]]:
        url = self.BASE_URL.format(year=year)
        records: List[Dict[str, Any]] = []

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 404:
                return records

            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", {"id": "myTable"}) or soup.find("table")

            if not table:
                return records

            tbody = table.find("tbody") or table
            for row in tbody.find_all("tr"):
                cols = row.find_all(["td", "th"])

                if len(cols) <= self.TARGET_COL_INDEX:
                    continue

                col_mes = cols[0].get_text(strip=True).lower()

                if col_mes in self.MONTHS_MAP:
                    month_num = self.MONTHS_MAP[col_mes]
                    raw_val = cols[self.TARGET_COL_INDEX].get_text(strip=True)

                    if not raw_val or raw_val in ["-", "N/A", ""]:
                        continue

                    clean_val = (
                        raw_val.replace(",", ".")
                        .replace("%", "")
                        .replace("\xa0", "")
                        .strip()
                    )

                    try:
                        valor_float = float(clean_val)
                        records.append({
                            "fecha_dt": datetime(year, month_num, 1),
                            "valor": valor_float,
                        })
                    except ValueError:
                        continue

        except requests.exceptions.RequestException as err:
            print(f"[WARN] Error al consultar datos del año {year}: {err}")

        return records


ipc_service = IPCService()


def guardar_en_csv(nuevos_registros: List[Dict[str, Any]]) -> None:
    """Guarda o actualiza la serie de IPC en un archivo CSV local."""
    if not nuevos_registros:
        return

    df_nuevos = pd.DataFrame(nuevos_registros)

    if os.path.exists(CSV_FILE):
        df_existente = pd.read_csv(CSV_FILE)
        df_combinado = pd.concat([df_existente, df_nuevos]).drop_duplicates(subset=["fecha"], keep="last")
    else:
        df_combinado = df_nuevos

    df_combinado.sort_values(by="fecha", inplace=True)
    df_combinado.to_csv(CSV_FILE, index=False)


def restar_meses(dt: datetime, meses: int) -> datetime:
    """Resta N meses a un objeto datetime."""
    ano = dt.year
    mes = dt.month - meses

    while mes <= 0:
        mes += 12
        ano -= 1

    return datetime(ano, mes, 1)


def sumar_un_mes(dt: datetime) -> datetime:
    """Suma exactamente 1 mes a un objeto datetime."""
    nuevo_mes = dt.month % 12 + 1
    nuevo_ano = dt.year + (dt.month // 12)
    return dt.replace(year=nuevo_ano, month=nuevo_mes)


def formatear_clp(valor: float) -> str:
    return f"$ {round(valor):,.0f}".replace(",", ".")


@app.route("/", methods=["GET", "POST"])
def index():
    resultado = None
    monto_inicial_val = ""
    plazo_val = ""
    tipo_plazo_val = "meses"
    tasa_val = ""

    if request.method == "POST":
        try:
            monto_str = request.form.get("monto_inicial", "0").replace(".", "").replace("$", "").strip()
            monto_inicial = float(monto_str)
            
            plazo = int(request.form.get("plazo", 0))
            tipo_plazo = request.form.get("tipo_plazo", "meses")
            tasa = float(request.form.get("tasa", 0.0))

            monto_inicial_val = request.form.get("monto_inicial", "")
            plazo_val = request.form.get("plazo", "")
            tipo_plazo_val = tipo_plazo
            tasa_val = request.form.get("tasa", "")

            total_meses = plazo * 12 if tipo_plazo == "años" else plazo

            if monto_inicial <= 0 or total_meses <= 0 or tasa < 0:
                raise ValueError("Los valores ingresados deben ser mayores a cero.")

            # CÁLCULO AUTOMÁTICO DE FECHAS SEGÚN EL PLAZO
            dt_actual = datetime.now()
            dt_inicio = restar_meses(dt_actual, total_meses)
            
            start_date_str = dt_inicio.strftime("%Y-%m-01")
            end_date_str = dt_actual.strftime("%Y-%m-28")

            # Scraping dinámico desde el SII
            registros_ipc = ipc_service.fetch_ipc_series(start_date_str, end_date_str)
            guardar_en_csv(registros_ipc)

            # Mapa { "YYYY-MM": valor_ipc }
            ipc_dict = {reg["fecha"][:7]: reg["valor"] for reg in registros_ipc}

            capital_actual = monto_inicial
            total_intereses = 0.0
            total_reajuste_ipc = 0.0
            tabla_desglose = []
            
            current_date = dt_inicio

            for i in range(1, total_meses + 1):
                capital_inicial_periodo = capital_actual
                
                # 1. Interés ganado en el mes
                interes_periodo = capital_actual * (tasa / 100.0)
                monto_con_interes = capital_actual + interes_periodo

                # 2. Reajuste por IPC obtenido o 0.0 por defecto
                clave = current_date.strftime("%Y-%m")
                ipc_porcentaje = ipc_dict.get(clave, 0.0)

                reajuste_ipc_periodo = monto_con_interes * (ipc_porcentaje / 100.0)
                
                capital_actual = monto_con_interes + reajuste_ipc_periodo
                
                total_intereses += interes_periodo
                total_reajuste_ipc += reajuste_ipc_periodo

                tabla_desglose.append({
                    "periodo": current_date.strftime("%b %Y").capitalize(),
                    "capital_inicial": formatear_clp(capital_inicial_periodo),
                    "interes_ganado": formatear_clp(interes_periodo),
                    "monto_mas_interes": formatear_clp(monto_con_interes),
                    "ipc_aplicado": f"{ipc_porcentaje:.2f}%",
                    "reajuste_ipc": formatear_clp(reajuste_ipc_periodo),
                    "saldo_final": formatear_clp(capital_actual)
                })

                current_date = sumar_un_mes(current_date)

            resultado = {
                "monto_inicial": formatear_clp(monto_inicial),
                "plazo": f"{plazo} {tipo_plazo}",
                "tasa": f"{tasa}% por periodo",
                "rango_fechas": f"{dt_inicio.strftime('%b %Y').capitalize()} - {dt_actual.strftime('%b %Y').capitalize()}",
                "subtotal_intereses": formatear_clp(total_intereses),
                "total_reajuste_ipc": formatear_clp(total_reajuste_ipc),
                "monto_final": formatear_clp(capital_actual),
                "ganancia_total": formatear_clp(total_intereses + total_reajuste_ipc),
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
        tasa=tasa_val
    )


if __name__ == "__main__":
    app.run(debug=True)
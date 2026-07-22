import base64
import os
from datetime import datetime
from typing import Any, Dict, List
import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request

app = Flask(__name__)

CSV_FILE = "ipc_historico.csv"

# Configuración de GitHub desde variables de entorno
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Ej: "usuario/repositorio"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

MESES_ESP = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}


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
                        fecha_str = f"{year}-{month_num:02d}"
                        records.append({
                            "fecha": fecha_str,
                            "valor": valor_float,
                        })
                    except ValueError:
                        continue

        except requests.exceptions.RequestException as err:
            print(f"[WARN] Error al consultar datos del año {year}: {err}")

        return records


ipc_service = IPCService()


def cargar_ipc_local() -> Dict[str, float]:
    """Carga el diccionario { 'YYYY-MM': valor } desde el archivo CSV local si existe."""
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, dtype={"fecha": str})
            return dict(zip(df["fecha"], df["valor"]))
        except Exception as e:
            print(f"[WARN] Error al leer CSV local: {e}")
    return {}


def actualizar_csv_y_github(nuevos_registros: List[Dict[str, Any]]) -> None:
    """Actualiza el CSV local y, si existen credenciales, realiza un commit a GitHub."""
    if not nuevos_registros:
        return

    df_nuevos = pd.DataFrame(nuevos_registros)

    if os.path.exists(CSV_FILE):
        df_existente = pd.read_csv(CSV_FILE, dtype={"fecha": str})
        df_combinado = pd.concat([df_existente, df_nuevos]).drop_duplicates(subset=["fecha"], keep="last")
    else:
        df_combinado = df_nuevos

    df_combinado.sort_values(by="fecha", inplace=True)
    df_combinado.to_csv(CSV_FILE, index=False)
    print(f"[INFO] Archivo {CSV_FILE} actualizado en disco.")

    # Sincronización automática con GitHub via API
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url_github = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_FILE}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
            }

            # 1. Obtener el SHA actual del archivo en GitHub
            res = requests.get(url_github, headers=headers)
            sha = res.json().get("sha") if res.status_code == 200 else None

            # 2. Codificar el nuevo contenido del CSV en Base64
            with open(CSV_FILE, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("utf-8")

            data = {
                "message": "Update ipc_historico.csv con nuevos datos [auto-commit]",
                "content": content_b64,
                "branch": GITHUB_BRANCH,
            }
            if sha:
                data["sha"] = sha

            # 3. Hacer el commit vía PUT
            put_res = requests.put(url_github, headers=headers, json=data)
            if put_res.status_code in [200, 201]:
                print("[SUCCESS] ¡CSV actualizado exitosamente en GitHub!")
            else:
                print(f"[ERROR] Error actualizando en GitHub: {put_res.status_code} - {put_res.text}")

        except Exception as e:
            print(f"[WARN] Excepción al sincronizar con GitHub: {e}")


def obtener_ipc_meses_requeridos(lista_meses: List[str]) -> Dict[str, float]:
    """
    1. Revisa qué meses están en el CSV.
    2. Si faltan meses, consulta al SII únicamente los años faltantes.
    3. Guarda los nuevos hallazgos en el CSV y GitHub.
    """
    ipc_map = cargar_ipc_local()
    meses_faltantes = [m for m in lista_meses if m not in ipc_map]

    if not meses_faltantes:
        print("[CACHE] Todos los meses requeridos se obtuvieron del CSV local.")
        return ipc_map

    # Identificar los años que requieren consulta al SII
    anios_faltantes = set(int(m.split("-")[0]) for m in meses_faltantes)
    nuevos_registros = []

    print(f"[WEB SCRAPING] Faltan meses en caché. Consultando SII para los años: {anios_faltantes}")

    for anio in anios_faltantes:
        registros_anio = ipc_service._scrape_mensual_ipc(anio)
        nuevos_registros.extend(registros_anio)
        for reg in registros_anio:
            ipc_map[reg["fecha"]] = reg["valor"]

    if nuevos_registros:
        actualizar_csv_y_github(nuevos_registros)

    return ipc_map


def restar_meses(dt: datetime, meses: int) -> datetime:
    ano = dt.year
    mes = dt.month - meses
    while mes <= 0:
        mes += 12
        ano -= 1
    return datetime(ano, mes, 1)


def sumar_un_mes(dt: datetime) -> datetime:
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

            # Cálculo automático de fechas según el plazo
            dt_actual = datetime.now()
            dt_inicio = restar_meses(dt_actual, total_meses)

            # Generar lista de strings 'YYYY-MM' requeridos
            meses_requeridos = []
            curr = dt_inicio
            for _ in range(total_meses):
                meses_requeridos.append(curr.strftime("%Y-%m"))
                curr = sumar_un_mes(curr)

            # Estrategia CSV / Web Scraping inteligente
            ipc_dict = obtener_ipc_meses_requeridos(meses_requeridos)

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

                # 2. Reajuste por IPC obtenido del CSV/SII (0.0 por defecto si no existe)
                clave = current_date.strftime("%Y-%m")
                ipc_porcentaje = ipc_dict.get(clave, 0.0)

                reajuste_ipc_periodo = monto_con_interes * (ipc_porcentaje / 100.0)
                
                capital_actual = monto_con_interes + reajuste_ipc_periodo
                
                total_intereses += interes_periodo
                total_reajuste_ipc += reajuste_ipc_periodo

                nombre_mes = MESES_ESP[current_date.month]
                periodo_espanol = f"{nombre_mes} {current_date.year}"

                tabla_desglose.append({
                    "periodo": periodo_espanol,
                    "capital_inicial": formatear_clp(capital_inicial_periodo),
                    "interes_ganado": formatear_clp(interes_periodo),
                    "monto_mas_interes": formatear_clp(monto_con_interes),
                    "ipc_aplicado": f"{ipc_porcentaje:.2f}%",
                    "reajuste_ipc": formatear_clp(reajuste_ipc_periodo),
                    "saldo_final": formatear_clp(capital_actual)
                })

                current_date = sumar_un_mes(current_date)

            rango_fechas_str = f"{MESES_ESP[dt_inicio.month]} {dt_inicio.year} - {MESES_ESP[dt_actual.month]} {dt_actual.year}"

            resultado = {
                "monto_inicial": formatear_clp(monto_inicial),
                "plazo": f"{plazo} {tipo_plazo}",
                "tasa": f"{tasa}% por periodo",
                "rango_fechas": rango_fechas_str,
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
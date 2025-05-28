# app/adapters/report_fetcher_adapter.py
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Optional
from urllib.parse import urljoin
from app.config import settings
from app.core.schemas import ReportDetails
from pydantic import HttpUrl

# --- Constantes ---
TOREX_BASE_URL = "https://torexgold.com" # Para construir URLs absolutas si son relativas

def _parse_report_name_details(report_name: str, report_url: str) -> Optional[schemas.ReportDetails]:
    """
    Intenta extraer año y trimestre del nombre del informe o URL.
    Ejemplos de nombres:
    "Torex Gold Reports First Quarter 2023 Results" -> 2023, Q1
    "Torex Gold Announces Record Full Year and Fourth Quarter 2022 Financial Results" -> 2022, Q4 / FY
    "TXG-Q3-2021-Financial-Statements.pdf" -> 2021, Q3
    """
    year_match = re.search(r'(20[2-9][0-9])', report_name + " " + report_url) # Años 2020-2099
    if not year_match:
        return None
    year = int(year_match.group(1))

    quarter = "Unknown"
    name_lower = report_name.lower()
    url_lower = report_url.lower()
    
    # Buscar trimestres
    if "first quarter" in name_lower or "q1" in name_lower or "-q1-" in url_lower or "_q1_" in url_lower:
        quarter = "Q1"
    elif "second quarter" in name_lower or "q2" in name_lower or "-q2-" in url_lower or "_q2_" in url_lower:
        quarter = "Q2"
    elif "third quarter" in name_lower or "q3" in name_lower or "-q3-" in url_lower or "_q3_" in url_lower:
        quarter = "Q3"
    elif "fourth quarter" in name_lower or "q4" in name_lower or "-q4-" in url_lower or "_q4_" in url_lower:
        quarter = "Q4"
    
    # Buscar año completo (Full Year)
    if "full year" in name_lower or "year-end" in name_lower or "annual report" in name_lower or "-fy-" in url_lower:
        quarter = "FY" # Si es FY, podría haber también un Q4, priorizar FY si ambos están.
        if "fourth quarter" in name_lower and "full year" in name_lower : # Si dice "Q4 and Full Year", es un informe de Q4 que también sirve de FY
             quarter = "Q4" # O podríamos crear dos entradas, una para Q4 y otra para FY si el contenido lo justifica.
                            # Para simplificar, si dice "Q4 and Full Year", lo tomamos como Q4, y el YTD será el anual.
                            # O, si el informe es claramente un "Annual Report", entonces FY.

    # Si es un informe anual y no se detectó un trimestre específico, es FY.
    # A veces los informes anuales no dicen "Q4".
    if quarter == "Unknown" and ("annual" in name_lower or "year-end" in name_lower):
        quarter = "FY"
        
    # Si aún es Unknown, intentar con expresiones regulares más genéricas sobre el nombre del PDF
    if quarter == "Unknown":
        q_match_url = re.search(r'[_-](q[1-4])[_-]', url_lower)
        if q_match_url:
            quarter = q_match_url.group(1).upper()

    if quarter == "Unknown":
        print(f"Advertencia: No se pudo determinar el trimestre para: {report_name} ({report_url}). Se omite.")
        return None # O marcar como "Unknown" y manejarlo después

    # Validar el URL
    try:
        valid_url = HttpUrl(report_url)
    except Exception:
        print(f"Advertencia: URL inválido {report_url}. Se omite.")
        return None

    return schemas.ReportDetails(
        report_name=report_name.strip(),
        report_url=valid_url,
        year=year,
        quarter=quarter
    )

def fetch_financial_report_urls(start_year: int, end_year: int) -> List[schemas.ReportDetails]:
    """
    Obtiene los URLs de los informes financieros de Torex Gold para un rango de años.
    Intenta parsear el año y trimestre del nombre/URL del informe.
    """
    report_details_list: List[schemas.ReportDetails] = []
    try:
        response = requests.get(settings.TOREX_REPORTS_URL, timeout=15)
        response.raise_for_status() # Lanza una excepción para códigos de error HTTP
    except requests.RequestException as e:
        print(f"Error al acceder a {settings.TOREX_REPORTS_URL}: {e}")
        return report_details_list

    soup = BeautifulSoup(response.content, 'html.parser')

    # La estructura del sitio de Torex Gold puede cambiar.
    # Esta es una suposición basada en una inspección típica de sitios de inversores.
    # Se buscan enlaces (<a>) que contengan ".pdf" en su href y texto relacionado con informes.
    
    # Intenta encontrar secciones o divs que probablemente contengan los informes
    # Esto es muy dependiente de la estructura actual del sitio.
    # Ejemplo: buscar elementos que contengan 'Financial Statements', 'MD&A', 'Press Release'
    # y luego dentro de ellos buscar los PDFs.

    # Un enfoque más general: buscar todos los enlaces a PDF y luego filtrar por texto.
    links = soup.find_all('a', href=True)
    
    processed_urls = set()

    for link in links:
        href = link['href']
        link_text = link.get_text(strip=True)

        if not href.lower().endswith(".pdf"):
            continue # Solo nos interesan los PDFs

        # Construir URL absoluto si es relativo
        absolute_url = urljoin(TOREX_BASE_URL, href)
        
        if absolute_url in processed_urls:
            continue
        processed_urls.add(absolute_url)

        # Filtrar por palabras clave en el texto del enlace o en el propio URL
        # Palabras clave comunes: "Financial Statements", "MD&A", "Report", "Results", "Quarter", "Annual"
        # También filtrar por el rango de años
        # Este filtro es crucial y puede necesitar ajuste.
        text_to_search = (link_text + " " + href).lower()
        
        # Verificar si el texto del enlace o el URL contienen algún año del rango deseado
        year_in_text = False
        for year_to_check in range(start_year, end_year + 1):
            if str(year_to_check) in text_to_search:
                year_in_text = True
                break
        
        if not year_in_text:
            continue # El año no está en el rango o no se menciona

        # Palabras clave para identificar que es un informe financiero o de resultados
        keywords = ["financial statement", "financial report", "results", "md&a", "management discussion", "earnings report"]
        is_relevant_report = any(keyword in text_to_search for keyword in keywords)
        
        # Evitar PDFs genéricos como "presentation", "fact sheet" a menos que explícitamente digan "results"
        negative_keywords = ["presentation", "fact sheet", "notice of meeting", "circular"]
        if any(neg_keyword in text_to_search for neg_keyword in negative_keywords) and not "results" in text_to_search:
            # Si es una presentación pero dice "Q1 Results Presentation", podría ser útil, pero por ahora lo excluimos
            # para enfocarnos en los estados financieros formales.
            # print(f"Omitiendo (posiblemente no es informe financiero principal): {link_text} ({absolute_url})")
            continue

        if is_relevant_report:
            details = _parse_report_name_details(link_text if link_text else href.split('/')[-1], absolute_url)
            if details and start_year <= details.year <= end_year:
                # Evitar duplicados por nombre, año y trimestre (aunque la URL ya es única)
                is_duplicate = any(
                    d.report_name == details.report_name and d.year == details.year and d.quarter == details.quarter 
                    for d in report_details_list
                )
                if not is_duplicate:
                    report_details_list.append(details)
                    print(f"Informe encontrado: Año {details.year}, Trimestre {details.quarter}, Nombre: {details.report_name}, URL: {details.report_url}")
                else:
                    print(f"Informe duplicado (nombre/año/trimestre) omitido: {details.report_name}")

    print(f"Total de informes únicos parseados del sitio: {len(report_details_list)}")
    # Podríamos ordenar los informes por año y trimestre
    report_details_list.sort(key=lambda r: (r.year, r.quarter))
    return report_details_list


def download_pdf_content(report_url: str) -> Optional[bytes]:
    """
    Descarga el contenido de un PDF desde una URL.
    """
    try:
        response = requests.get(report_url, timeout=30) # Timeout más largo para PDFs
        response.raise_for_status()
        if 'application/pdf' in response.headers.get('Content-Type', '').lower():
            return response.content
        else:
            print(f"Error: El contenido de {report_url} no es un PDF. Content-Type: {response.headers.get('Content-Type')}")
            return None
    except requests.RequestException as e:
        print(f"Error al descargar el PDF {report_url}: {e}")
        return None

# Ejemplo de uso (para pruebas locales)
if __name__ == "__main__":
    print(f"Buscando informes entre {settings.START_YEAR} y {settings.END_YEAR} en {settings.TOREX_REPORTS_URL}")
    found_reports = fetch_financial_report_urls(start_year=settings.START_YEAR, end_year=settings.END_YEAR)
    if found_reports:
        print(f"\n--- Informes Encontrados ({len(found_reports)}) ---")
        for rep in found_reports:
            print(f"Año: {rep.year}, Trimestre: {rep.quarter}, Nombre: {rep.report_name}, URL: {rep.report_url}")
        
        # Probar descarga de un PDF
        # if len(found_reports) > 0:
        #     print(f"\nIntentando descargar: {found_reports[0].report_url}")
        #     pdf_bytes = download_pdf_content(str(found_reports[0].report_url))
        #     if pdf_bytes:
        #         print(f"PDF descargado, tamaño: {len(pdf_bytes)} bytes.")
        #         # Guardar para inspección (opcional)
        #         # with open("test_report.pdf", "wb") as f:
        #         #     f.write(pdf_bytes)
        #         # print("PDF guardado como test_report.pdf")
        #     else:
        #         print("Fallo al descargar el PDF.")

    else:
        print("No se encontraron informes.")


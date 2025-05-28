# app/adapters/report_fetcher_adapter.py
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Optional, Dict, Tuple, Set
from urllib.parse import urljoin, urlparse

from config import settings
from core import schemas 
from pydantic import HttpUrl, ValidationError

TOREX_BASE_URL = "https://torexgold.com" 

# Tipos de documentos que queremos específicamente
DOC_TYPE_MDA = "MDA"
DOC_TYPE_FS = "FS" 
DOC_TYPE_PRESENTATION = "PRESENTATION"
DOC_TYPE_OTHER = "OTHER" # Para clasificación inicial si no es uno de los de arriba

# Mapeo de patrones a tipos de documentos y trimestres
# Los patrones deben ser en minúsculas
PATTERNS_FS = [
    r"financial statement", r"\bfs\b", r"interim financial statements", 
    r"consolidated financial statements", r"financials", r"financials.pdf"
]
PATTERNS_MDA = [
    r"md&a", r"management discussion", r"management's discussion", r"mda.pdf"
]
PATTERNS_PRESENTATION = [
    r"presentation", r"investor presentation", r"earnings call presentation",
    # Asegurarse que sea de resultados si solo dice "presentation"
    # Esto se refina más adelante con palabras clave de resultados
]

PATTERNS_Q1 = [r"first quarter", r"\bq1\b(?!\d)", r"[_-]q1[_-]", r"march 31", r"q1-\d{4}"]
PATTERNS_Q2 = [r"second quarter", r"\bq2\b(?!\d)", r"[_-]q2[_-]", r"june 30", r"q2-\d{4}"]
PATTERNS_Q3 = [r"third quarter", r"\bq3\b(?!\d)", r"[_-]q3[_-]", r"september 30", r"q3-\d{4}"]
PATTERNS_Q4 = [r"fourth quarter", r"\bq4\b(?!\d)", r"[_-]q4[_-]", r"december 31", r"q4-\d{4}"]
PATTERNS_FY = [r"full year", r"year-end", r"annual report", r"\bfy\b", r"[_-]fy[_-]", r"annual financial statements", r"annual mda"]


def _is_valid_url(url_string: str) -> bool:
    try:
        HttpUrl(url_string)
        return True
    except ValidationError:
        return False

def _parse_report_name_details(report_name_from_link: str, report_url_str: str) -> Optional[Tuple[schemas.ReportDetails, str]]:
    """
    Intenta extraer año, trimestre y TIPO de documento.
    Retorna una tupla: (ReportDetails, doc_type_string) o None si no es válido.
    """
    text_search_content = (report_name_from_link + " " + report_url_str).lower()

    # 1. Determinar Año
    year = None
    year_match = re.search(r'(20[1-9][0-9])', text_search_content) 
    if year_match:
        year = int(year_match.group(1))
    else:
        return None # No se puede determinar el año, documento no válido para nuestros fines

    # 2. Determinar Tipo de Documento
    doc_type = DOC_TYPE_OTHER
    if any(re.search(p, text_search_content) for p in PATTERNS_FS):
        doc_type = DOC_TYPE_FS
    elif any(re.search(p, text_search_content) for p in PATTERNS_MDA):
        doc_type = DOC_TYPE_MDA
    elif any(re.search(p, text_search_content) for p in PATTERNS_PRESENTATION):
        # Para presentaciones, ser más estrictos: deben mencionar resultados o un trimestre/año
        if "results" in text_search_content or \
           "earnings" in text_search_content or \
           "financial" in text_search_content or \
           re.search(r"q[1-4]", text_search_content) or \
           str(year) in text_search_content:
            doc_type = DOC_TYPE_PRESENTATION
    
    if doc_type == DOC_TYPE_OTHER: # Si no es uno de los tipos principales, no nos interesa
        return None

    # 3. Determinar Trimestre (Q1, Q2, Q3, Q4, o FY)
    quarter = "Unknown"
    is_fy_report = any(re.search(p, text_search_content) for p in PATTERNS_FY)
    
    found_q_specific = None
    if any(re.search(p, text_search_content) for p in PATTERNS_Q1): found_q_specific = "Q1"
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q2): found_q_specific = "Q2"
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q3): found_q_specific = "Q3"
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q4): found_q_specific = "Q4"

    if is_fy_report:
        quarter = "FY" # Si es un informe anual explícito, lo marcamos como FY.
                       # Los documentos de Q4 a menudo son también los anuales.
                       # Si un documento es "Q4 y Anual", se clasificará como Q4 y luego como FY.
                       # En este caso, para simplificar, si detecta FY, es FY.
                       # Si detecta Q4 y también FY, priorizaremos FY si es FS o MDA anual.
                       # Para el objetivo de 3 docs/trimestre, trataremos FY como un "super Q4".
                       # El sitio de Torex lista "Fourth Quarter and Full-Year Report"
                       # Para estos, los documentos FS, MDA, Pres son los de Q4/FY.
        if found_q_specific == "Q4": # Es un Q4 que también es el anual
            quarter = "Q4" # Lo tratamos como Q4, y se asumirá que contiene datos anuales.
    elif found_q_specific:
        quarter = found_q_specific
    
    if quarter == "Unknown":
        return None # No se puede determinar el trimestre.

    # Crear el objeto ReportDetails
    try:
        report_url_obj = HttpUrl(report_url_str)
    except ValidationError:
        return None

    report_name = report_name_from_link.strip() if report_name_from_link else report_url_str.split('/')[-1]
    
    # Ajuste: Si es un Q4 y el nombre indica "Full-Year", reflejar esto en el nombre para claridad.
    if quarter == "Q4" and is_fy_report and "full-year" not in report_name.lower() and "annual" not in report_name.lower():
        report_name = f"{report_name} (FY {year})"


    details = schemas.ReportDetails(
        report_name=report_name,
        report_url=report_url_obj,
        year=year,
        quarter=quarter # Será Q1, Q2, Q3, Q4. El Q4 puede ser también el anual.
    )
    return details, doc_type

def fetch_financial_report_urls(start_year: int, end_year: int) -> List[schemas.ReportDetails]:
    """
    Obtiene URLs de informes financieros, intentando seleccionar FS, MD&A y Presentation por trimestre.
    """
    all_candidate_reports_with_type: List[Tuple[schemas.ReportDetails, str]] = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(settings.TOREX_REPORTS_URL, timeout=30, headers=headers)
        response.raise_for_status() 
    except requests.RequestException as e:
        print(f"Error al acceder a {settings.TOREX_REPORTS_URL}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', href=True)
    processed_urls_in_initial_scan: Set[HttpUrl] = set()

    for link in links:
        href = link['href']
        link_text = link.get_text(strip=True)

        if not href.lower().endswith(".pdf"):
            continue 

        parsed_href = urlparse(href)
        if not parsed_href.scheme or not parsed_href.netloc: 
            absolute_url_str = urljoin(settings.TOREX_REPORTS_URL, href) 
        else:
            absolute_url_str = href
        
        if not _is_valid_url(absolute_url_str):
            continue
        
        try: # Convertir a HttpUrl para el set y para evitar duplicados por normalización de Pydantic
            abs_url_obj = HttpUrl(absolute_url_str)
            if abs_url_obj in processed_urls_in_initial_scan:
                continue
            processed_urls_in_initial_scan.add(abs_url_obj)
        except ValidationError:
            continue # Ya se validó con _is_valid_url, pero por si acaso.
        
        # Filtro primario por año
        year_in_link = False
        for year_to_check in range(start_year, end_year + 1):
            if str(year_to_check) in (link_text.lower() + " " + absolute_url_str.lower()):
                year_in_link = True
                break
        if not year_in_link:
            continue
        
        parsed_info = _parse_report_name_details(link_text, absolute_url_str)
        if parsed_info:
            details, doc_type = parsed_info
            # Solo considerar si el año está en rango y el tipo es uno de los deseados (FS, MDA, PRESENTATION)
            if start_year <= details.year <= end_year and doc_type in [DOC_TYPE_FS, DOC_TYPE_MDA, DOC_TYPE_PRESENTATION]:
                all_candidate_reports_with_type.append((details, doc_type))

    # Lógica de Selección: Para cada (año, trimestre), queremos 1 FS, 1 MD&A, 1 Presentación si existen.
    # Usar un diccionario para almacenar los mejores candidatos por tipo para cada período.
    # Clave: (year, quarter), Valor: { "FS": ReportDetails, "MDA": ReportDetails, "PRESENTATION": ReportDetails }
    selected_reports_by_period: Dict[Tuple[int, str], Dict[str, schemas.ReportDetails]] = {}

    # Ordenar candidatos para procesamiento predecible (ej. por nombre de informe, aunque URL debería ser único)
    all_candidate_reports_with_type.sort(key=lambda x: (x[0].year, x[0].quarter, x[1], x[0].report_name))

    for details, doc_type in all_candidate_reports_with_type:
        period_key = (details.year, details.quarter)
        
        if period_key not in selected_reports_by_period:
            selected_reports_by_period[period_key] = {}

        # Si no tenemos ya un documento de este tipo para este período, o si este es "mejor" (no implementado, se toma el primero)
        if doc_type not in selected_reports_by_period[period_key]:
            selected_reports_by_period[period_key][doc_type] = details
        # Aquí se podría añadir lógica si se encuentra un PDF "mejor" del mismo tipo (ej. no provisional)
        # Por ahora, se toma el primero que se clasifica así para el período.

    # Construir la lista final a partir de los seleccionados
    final_list: List[schemas.ReportDetails] = []
    added_urls_to_final: Set[HttpUrl] = set() # Para asegurar URLs únicas en la salida final

    sorted_periods_for_output = sorted(selected_reports_by_period.keys())

    for period_key in sorted_periods_for_output:
        docs_for_period = selected_reports_by_period[period_key]
        
        if DOC_TYPE_FS in docs_for_period:
            report = docs_for_period[DOC_TYPE_FS]
            if report.report_url not in added_urls_to_final:
                final_list.append(report)
                added_urls_to_final.add(report.report_url)
        
        if DOC_TYPE_MDA in docs_for_period:
            report = docs_for_period[DOC_TYPE_MDA]
            if report.report_url not in added_urls_to_final:
                final_list.append(report)
                added_urls_to_final.add(report.report_url)

        if DOC_TYPE_PRESENTATION in docs_for_period:
            report = docs_for_period[DOC_TYPE_PRESENTATION]
            if report.report_url not in added_urls_to_final:
                final_list.append(report)
                added_urls_to_final.add(report.report_url)
                
    final_list.sort(key=lambda r: (r.year, r.quarter, r.report_name))
    
    print(f"Fetcher (Altamente Selectivo): Total de informes seleccionados: {len(final_list)}")
    # for r in final_list:
    #     print(f"  - {r.year} {r.quarter} - {r.report_name} ({r.report_url})")
    return final_list


def download_pdf_content(report_url: str) -> Optional[bytes]:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(report_url, timeout=45, headers=headers, allow_redirects=True) 
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type:
            if len(response.content) < 1000: 
                print(f"Warning: PDF at {report_url} is very small ({len(response.content)} bytes). May be invalid or empty.")
            return response.content
        else:
            print(f"Error: El contenido de {report_url} no es un PDF. Content-Type: {content_type}")
            return None
    except requests.exceptions.Timeout:
        print(f"Error: Timeout al descargar el PDF {report_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar el PDF {report_url}: {e}")
        return None

if __name__ == "__main__": # Para pruebas locales
    print(f"Probando fetcher altamente selectivo para años: {settings.START_YEAR} a {settings.END_YEAR}")
    found_reports = fetch_financial_report_urls(start_year=settings.START_YEAR, end_year=settings.END_YEAR)
    if found_reports:
        print(f"\n--- Informes Seleccionados ({len(found_reports)}) ---")
        # Contar por año y trimestre
        from collections import Counter
        counts_per_period = Counter((r.year, r.quarter) for r in found_reports)
        for period, count in sorted(counts_per_period.items()):
            print(f"Periodo: {period[0]}-{period[1]}, Documentos: {count}")

        print("\nDetalle:")
        for rep_idx, rep in enumerate(found_reports):
            print(f"{rep_idx+1}. Año: {rep.year}, Trimestre: {rep.quarter}, Nombre: {rep.report_name}, URL: {rep.report_url}")
        
        # ... (código de prueba de descarga opcional) ...
    else:
        print("No se encontraron informes con los criterios altamente selectivos.")

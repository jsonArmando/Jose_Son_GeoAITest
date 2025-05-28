# app/adapters/report_fetcher_adapter.py - VERSIÓN MEJORADA
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Optional, Dict, Tuple, Set
from urllib.parse import urljoin, urlparse
from collections import defaultdict, Counter
import logging

from config import settings
from core import schemas 
from pydantic import HttpUrl, ValidationError

# Configurar logging
logger = logging.getLogger(__name__)

TOREX_BASE_URL = "https://torexgold.com" 

# Tipos de documentos que queremos específicamente
DOC_TYPE_MDA = "MDA"
DOC_TYPE_FS = "FS" 
DOC_TYPE_PRESENTATION = "PRESENTATION"
DOC_TYPE_OTHER = "OTHER"

# PATRONES MEJORADOS - Más amplios y flexibles
PATTERNS_FS = [
    r"financial statement", r"\bfs\b", r"interim financial statements", 
    r"consolidated financial statements", r"financials", r"financials.pdf",
    # NUEVOS PATRONES AGREGADOS:
    r"financial report", r"quarterly report", r"interim report",
    r"consolidated statements", r"quarterly statements", r"quarterly financials"
]

PATTERNS_MDA = [
    r"md&a", r"management discussion", r"management's discussion", r"mda.pdf",
    # NUEVOS PATRONES AGREGADOS:
    r"management report", r"quarterly discussion", r"discussion and analysis",
    r"management analysis", r"quarterly analysis", r"interim discussion"
]

PATTERNS_PRESENTATION = [
    r"presentation", r"investor presentation", r"earnings call presentation",
    # NUEVOS PATRONES AGREGADOS:
    r"earnings presentation", r"quarterly presentation", r"investor slides",
    r"earnings slides", r"results presentation", r"quarterly slides"
]

# PATRONES DE TRIMESTRE MEJORADOS
PATTERNS_Q1 = [
    r"first quarter", r"\bq1\b(?!\d)", r"[_\-\s]q1[_\-\s]", r"march 31", 
    r"q1[\-_]\d{4}", r"q1\s\d{4}", r"1st quarter", r"quarter 1"
]
PATTERNS_Q2 = [
    r"second quarter", r"\bq2\b(?!\d)", r"[_\-\s]q2[_\-\s]", r"june 30", 
    r"q2[\-_]\d{4}", r"q2\s\d{4}", r"2nd quarter", r"quarter 2"
]
PATTERNS_Q3 = [
    r"third quarter", r"\bq3\b(?!\d)", r"[_\-\s]q3[_\-\s]", r"september 30", 
    r"q3[\-_]\d{4}", r"q3\s\d{4}", r"3rd quarter", r"quarter 3"
]
PATTERNS_Q4 = [
    r"fourth quarter", r"\bq4\b(?!\d)", r"[_\-\s]q4[_\-\s]", r"december 31", 
    r"q4[\-_]\d{4}", r"q4\s\d{4}", r"4th quarter", r"quarter 4"
]
PATTERNS_FY = [
    r"full year", r"year[\-_]end", r"annual report", r"\bfy\b", r"[_\-]fy[_\-]", 
    r"annual financial statements", r"annual mda", r"full[\-_]year", r"year[\-_]ended"
]

def _is_valid_url(url_string: str) -> bool:
    try:
        HttpUrl(url_string)
        return True
    except ValidationError:
        return False

def _parse_report_name_details(report_name_from_link: str, report_url_str: str, debug_mode: bool = False) -> Optional[Tuple[schemas.ReportDetails, str]]:
    """
    Versión mejorada: más flexible y con mejor logging
    """
    text_search_content = (report_name_from_link + " " + report_url_str).lower()
    
    if debug_mode:
        logger.debug(f"Analizando: '{report_name_from_link}' | URL: '{report_url_str}'")
        logger.debug(f"Contenido de búsqueda: '{text_search_content}'")

    # 1. Determinar Año
    year = None
    year_match = re.search(r'(20[1-9][0-9])', text_search_content) 
    if year_match:
        year = int(year_match.group(1))
        if debug_mode:
            logger.debug(f"Año encontrado: {year}")
    else:
        if debug_mode:
            logger.debug("❌ No se encontró año válido")
        return None

    # 2. Determinar Tipo de Documento - LÓGICA MEJORADA
    doc_type = DOC_TYPE_OTHER
    doc_type_debug = []
    
    if any(re.search(p, text_search_content) for p in PATTERNS_FS):
        doc_type = DOC_TYPE_FS
        doc_type_debug.append("Matched FS patterns")
    elif any(re.search(p, text_search_content) for p in PATTERNS_MDA):
        doc_type = DOC_TYPE_MDA
        doc_type_debug.append("Matched MDA patterns")
    elif any(re.search(p, text_search_content) for p in PATTERNS_PRESENTATION):
        # CAMBIO PRINCIPAL: ELIMINAR FILTRO RESTRICTIVO
        # La lógica anterior era demasiado restrictiva para presentations
        doc_type = DOC_TYPE_PRESENTATION
        doc_type_debug.append("Matched PRESENTATION patterns")
        
        # OPCIONAL: Mantener una versión más suave del filtro
        # Solo rechazar si claramente NO es una presentación de resultados
        if debug_mode:
            extra_check_results = {
                "results": "results" in text_search_content,
                "earnings": "earnings" in text_search_content, 
                "financial": "financial" in text_search_content,
                "quarterly": "quarterly" in text_search_content,
                "investor": "investor" in text_search_content,
                "quarter_pattern": bool(re.search(r"q[1-4]", text_search_content)),
                "year_in_text": str(year) in text_search_content
            }
            logger.debug(f"Presentation extra checks: {extra_check_results}")
    
    if doc_type == DOC_TYPE_OTHER:
        if debug_mode:
            logger.debug(f"❌ No coincide con patrones de documento. Checks: {doc_type_debug}")
        return None

    # 3. Determinar Trimestre - LÓGICA MEJORADA
    quarter = "Unknown"
    quarter_debug = []
    
    # Primero verificar patrones específicos de trimestre
    found_q_specific = None
    if any(re.search(p, text_search_content) for p in PATTERNS_Q1):
        found_q_specific = "Q1"
        quarter_debug.append("Matched Q1 patterns")
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q2):
        found_q_specific = "Q2"
        quarter_debug.append("Matched Q2 patterns")
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q3):
        found_q_specific = "Q3"
        quarter_debug.append("Matched Q3 patterns")
    elif any(re.search(p, text_search_content) for p in PATTERNS_Q4):
        found_q_specific = "Q4"
        quarter_debug.append("Matched Q4 patterns")
    
    # Verificar patrones de año completo
    is_fy_report = any(re.search(p, text_search_content) for p in PATTERNS_FY)
    if is_fy_report:
        quarter_debug.append("Matched FY patterns")
    
    # Lógica de decisión para trimestre
    if found_q_specific:
        quarter = found_q_specific
        # Si también es FY y es Q4, mantenerlo como Q4 (datos anuales incluidos)
        if is_fy_report and found_q_specific == "Q4":
            quarter_debug.append("Q4 with FY data")
    elif is_fy_report:
        # Es un reporte anual sin trimestre específico
        quarter = "FY"
    
    if quarter == "Unknown":
        if debug_mode:
            logger.debug(f"❌ No se pudo determinar trimestre. Checks: {quarter_debug}")
        return None

    if debug_mode:
        logger.debug(f"✅ Clasificado como: {doc_type} - {quarter} - {year}")
        logger.debug(f"Doc type checks: {doc_type_debug}")
        logger.debug(f"Quarter checks: {quarter_debug}")

    # 4. Crear el objeto ReportDetails
    try:
        report_url_obj = HttpUrl(report_url_str)
    except ValidationError:
        if debug_mode:
            logger.debug(f"❌ URL inválida: {report_url_str}")
        return None

    report_name = report_name_from_link.strip() if report_name_from_link else report_url_str.split('/')[-1]
    
    # Mejorar nombre si es Q4 con datos anuales
    if quarter == "Q4" and is_fy_report and "full-year" not in report_name.lower():
        report_name = f"{report_name} (Q4 & FY {year})"

    details = schemas.ReportDetails(
        report_name=report_name,
        report_url=report_url_obj,
        year=year,
        quarter=quarter
    )
    
    return details, doc_type

def fetch_financial_report_urls(start_year: int, end_year: int, debug_mode: bool = False) -> List[schemas.ReportDetails]:
    """
    Versión mejorada con mejor logging y análisis
    """
    if debug_mode:
        logger.setLevel(logging.DEBUG)
    
    logger.info(f"🔍 Iniciando búsqueda de reportes para años {start_year}-{end_year}")
    
    all_candidate_reports_with_type: List[Tuple[schemas.ReportDetails, str]] = []
    
    # 1. Obtener contenido de la página
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(settings.TOREX_REPORTS_URL, timeout=30, headers=headers)
        response.raise_for_status()
        logger.info(f"✅ Página obtenida exitosamente: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"❌ Error al acceder a {settings.TOREX_REPORTS_URL}: {e}")
        return []

    # 2. Parsear enlaces
    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', href=True)
    logger.info(f"📄 Encontrados {len(links)} enlaces totales")
    
    pdf_links = [link for link in links if link['href'].lower().endswith(".pdf")]
    logger.info(f"📄 Filtrados {len(pdf_links)} enlaces PDF")
    
    processed_urls_in_initial_scan: Set[HttpUrl] = set()
    classification_stats = Counter()

    # 3. Procesar cada enlace PDF
    for link in pdf_links:
        href = link['href']
        link_text = link.get_text(strip=True)
        
        # Construir URL absoluta
        parsed_href = urlparse(href)
        if not parsed_href.scheme or not parsed_href.netloc: 
            absolute_url_str = urljoin(settings.TOREX_REPORTS_URL, href) 
        else:
            absolute_url_str = href
        
        if not _is_valid_url(absolute_url_str):
            classification_stats['invalid_url'] += 1
            continue
        
        # Evitar duplicados
        try:
            abs_url_obj = HttpUrl(absolute_url_str)
            if abs_url_obj in processed_urls_in_initial_scan:
                classification_stats['duplicate_url'] += 1
                continue
            processed_urls_in_initial_scan.add(abs_url_obj)
        except ValidationError:
            classification_stats['url_validation_error'] += 1
            continue
        
        # Filtro rápido por año (antes de procesamiento completo)
        year_in_link = False
        for year_to_check in range(start_year, end_year + 1):
            if str(year_to_check) in (link_text.lower() + " " + absolute_url_str.lower()):
                year_in_link = True
                break
        
        if not year_in_link:
            classification_stats['year_not_in_range'] += 1
            continue
        
        # Intentar clasificar
        parsed_info = _parse_report_name_details(link_text, absolute_url_str, debug_mode)
        if parsed_info:
            details, doc_type = parsed_info
            if start_year <= details.year <= end_year and doc_type in [DOC_TYPE_FS, DOC_TYPE_MDA, DOC_TYPE_PRESENTATION]:
                all_candidate_reports_with_type.append((details, doc_type))
                classification_stats[f'classified_{doc_type}'] += 1
            else:
                classification_stats['out_of_scope'] += 1
        else:
            classification_stats['classification_failed'] += 1

    logger.info(f"📊 Estadísticas de clasificación: {dict(classification_stats)}")
    logger.info(f"📋 Candidatos válidos encontrados: {len(all_candidate_reports_with_type)}")

    # 4. Lógica de Selección Mejorada
    # Agrupar por período y tipo
    selected_reports_by_period: Dict[Tuple[int, str], Dict[str, schemas.ReportDetails]] = {}
    duplicate_detection: Dict[str, List[Tuple[schemas.ReportDetails, str]]] = defaultdict(list)
    
    # Detectar posibles duplicados primero
    for details, doc_type in all_candidate_reports_with_type:
        key = f"{details.year}_{details.quarter}_{doc_type}"
        duplicate_detection[key].append((details, doc_type))
    
    # Procesar selección
    for key, candidates in duplicate_detection.items():
        if len(candidates) > 1:
            logger.warning(f"⚠️ Múltiples candidatos para {key}: {[c[0].report_name for c in candidates]}")
            # Seleccionar el primero por ahora, podría mejorarse con heurísticas
            selected_candidate = candidates[0]
        else:
            selected_candidate = candidates[0]
        
        details, doc_type = selected_candidate
        period_key = (details.year, details.quarter)
        
        if period_key not in selected_reports_by_period:
            selected_reports_by_period[period_key] = {}
        
        selected_reports_by_period[period_key][doc_type] = details

    # 5. Construir lista final
    final_list: List[schemas.ReportDetails] = []
    added_urls_to_final: Set[HttpUrl] = set()
    
    # Estadísticas finales
    periods_with_complete_set = 0
    periods_missing_docs = []
    
    for period_key in sorted(selected_reports_by_period.keys()):
        year, quarter = period_key
        docs_for_period = selected_reports_by_period[period_key]
        
        # Agregar documentos encontrados
        docs_added_for_period = 0
        for doc_type in [DOC_TYPE_FS, DOC_TYPE_MDA, DOC_TYPE_PRESENTATION]:
            if doc_type in docs_for_period:
                report = docs_for_period[doc_type]
                if report.report_url not in added_urls_to_final:
                    final_list.append(report)
                    added_urls_to_final.add(report.report_url)
                    docs_added_for_period += 1
        
        # Estadísticas por período
        if docs_added_for_period == 3:
            periods_with_complete_set += 1
        elif docs_added_for_period < 3:
            missing_types = []
            for doc_type in [DOC_TYPE_FS, DOC_TYPE_MDA, DOC_TYPE_PRESENTATION]:
                if doc_type not in docs_for_period:
                    missing_types.append(doc_type)
            
            periods_missing_docs.append({
                'period': f"{year}-{quarter}",
                'found': docs_added_for_period,
                'missing': missing_types
            })

    # 6. Reportar resultados
    final_list.sort(key=lambda r: (r.year, r.quarter, r.report_name))
    
    expected_periods = (end_year - start_year + 1) * 4  # 4 trimestres por año
    expected_total_docs = expected_periods * 3  # 3 tipos por trimestre
    
    logger.info(f"📈 RESUMEN FINAL:")
    logger.info(f"   • Períodos esperados: {expected_periods}")
    logger.info(f"   • Documentos esperados: {expected_total_docs}")
    logger.info(f"   • Documentos encontrados: {len(final_list)}")
    logger.info(f"   • Períodos completos (3 docs): {periods_with_complete_set}")
    logger.info(f"   • Períodos incompletos: {len(periods_missing_docs)}")
    
    if periods_missing_docs and debug_mode:
        logger.debug(f"📋 PERÍODOS INCOMPLETOS:")
        for missing in periods_missing_docs:
            logger.debug(f"   • {missing['period']}: {missing['found']}/3 docs, faltan: {missing['missing']}")
    
    success_rate = (len(final_list) / expected_total_docs) * 100 if expected_total_docs > 0 else 0
    logger.info(f"   • Tasa de éxito: {success_rate:.1f}%")
    
    return final_list

def download_pdf_content(report_url: str) -> Optional[bytes]:
    """Sin cambios - mantener función original"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(report_url, timeout=45, headers=headers, allow_redirects=True) 
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type:
            if len(response.content) < 1000: 
                logger.warning(f"PDF at {report_url} is very small ({len(response.content)} bytes)")
            return response.content
        else:
            logger.error(f"Content at {report_url} is not PDF. Content-Type: {content_type}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Timeout downloading PDF {report_url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading PDF {report_url}: {e}")
        return None

if __name__ == "__main__":
    # Configurar logging para pruebas
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print(f"🧪 PROBANDO FETCHER MEJORADO")
    print(f"Años: {settings.START_YEAR} a {settings.END_YEAR}")
    
    # Ejecutar con debug habilitado
    found_reports = fetch_financial_report_urls(
        start_year=settings.START_YEAR, 
        end_year=settings.END_YEAR,
        debug_mode=True
    )
    
    if found_reports:
        print(f"\n📋 REPORTES ENCONTRADOS ({len(found_reports)}):")
        
        # Agrupar por año y trimestre para análisis
        by_period = defaultdict(list)
        for rep in found_reports:
            by_period[f"{rep.year}-{rep.quarter}"].append(rep)
        
        for period in sorted(by_period.keys()):
            reports_in_period = by_period[period]
            print(f"\n🗓️ {period}: {len(reports_in_period)} documentos")
            for rep in reports_in_period:
                print(f"   📄 {rep.report_name}")
        
        # Resumen por tipo
        type_counts = Counter()
        for rep in found_reports:
            # Inferir tipo basado en nombre (aproximado)
            name_lower = rep.report_name.lower()
            if any(pattern in name_lower for pattern in ['fs', 'financial statement', 'financials']):
                type_counts['FS'] += 1
            elif any(pattern in name_lower for pattern in ['md&a', 'mda', 'discussion']):
                type_counts['MDA'] += 1
            elif any(pattern in name_lower for pattern in ['presentation', 'slides']):
                type_counts['PRESENTATION'] += 1
            else:
                type_counts['OTHER'] += 1
        
        print(f"\n📊 DISTRIBUCIÓN POR TIPO:")
        for doc_type, count in type_counts.items():
            print(f"   • {doc_type}: {count}")
            
        if len(found_reports) < 12:  # Asumiendo 1 año de prueba
            print(f"\n⚠️ TODAVÍA FALTAN DOCUMENTOS:")
            print(f"   • Esperados: 12 (4 trimestres × 3 tipos)")
            print(f"   • Encontrados: {len(found_reports)}")
            print(f"   • Faltantes: {12 - len(found_reports)}")
            print(f"\n💡 Ejecutar el diagnóstico detallado para identificar el problema específico")
        else:
            print(f"\n✅ ÉXITO: Se encontraron todos los documentos esperados!")
            
    else:
        print("❌ No se encontraron reportes")
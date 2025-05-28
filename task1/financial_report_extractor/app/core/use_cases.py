# app/core/use_cases.py
from sqlalchemy.orm import Session
from app.adapters import db_adapter, report_fetcher_adapter, ai_processing_adapter
from app.core import schemas, ai_prompts
from app.config import settings
from typing import List, Tuple, Optional, Dict, Any
import time

def _calculate_accuracy_score(llm_result: schemas.LLMFullExtractionResult) -> float:
    """
    Calcula un puntaje de precisión basado en la completitud de los datos extraídos.
    """
    total_expected_fields = 0
    found_and_valid_fields = 0

    # Contar campos esperados en Operational Highlights
    expected_op_metrics_names = set(ai_prompts.EXPECTED_OPERATIONAL_METRICS)
    total_expected_fields += len(expected_op_metrics_names) * 2 # quarter_value y ytd_value

    # Contar campos esperados en Financial Highlights
    expected_fin_metrics_names = set(ai_prompts.EXPECTED_FINANCIAL_METRICS)
    total_expected_fields += len(expected_fin_metrics_names) * 2

    # Añadir campos de detalles del informe (año, trimestre)
    total_expected_fields += 2 # year, quarter

    # Validar detalles del informe
    if llm_result.report_details_inferred:
        if llm_result.report_details_inferred.get("year") and llm_result.report_details_inferred.get("year") != "Not found":
            found_and_valid_fields += 1
        if llm_result.report_details_inferred.get("quarter") and llm_result.report_details_inferred.get("quarter") != "Not found":
            found_and_valid_fields += 1
    
    # Validar Operational Highlights
    for item in llm_result.operational_highlights:
        if item.metric_name in expected_op_metrics_names:
            if item.quarter_value and item.quarter_value != "Not found":
                found_and_valid_fields += 1
            if item.ytd_value and item.ytd_value != "Not found":
                found_and_valid_fields += 1
    
    # Validar Financial Highlights
    for item in llm_result.financial_highlights:
        if item.metric_name in expected_fin_metrics_names:
            if item.quarter_value and item.quarter_value != "Not found":
                found_and_valid_fields += 1
            if item.ytd_value and item.ytd_value != "Not found":
                found_and_valid_fields += 1

    if total_expected_fields == 0:
        return 0.0 # Evitar división por cero

    accuracy = (found_and_valid_fields / total_expected_fields) * 100
    return round(accuracy, 2)

def _standardize_llm_output(
    llm_result: schemas.LLMFullExtractionResult, 
    original_report_details: schemas.ReportDetails
) -> schemas.StandardizedExtractionOutput:
    """
    Convierte la salida del LLM (schemas.LLMFullExtractionResult) a la estructura
    schemas.StandardizedExtractionOutput, incluyendo el cálculo del score de precisión.
    Usa original_report_details si el LLM no pudo inferir año/trimestre.
    """
    accuracy_score = _calculate_accuracy_score(llm_result)
    
    # Usar detalles inferidos por LLM si están, sino los originales del scraper
    year_to_use = original_report_details.year
    quarter_to_use = original_report_details.quarter

    if llm_result.report_details_inferred:
        inferred_year = llm_result.report_details_inferred.get("year")
        inferred_quarter = llm_result.report_details_inferred.get("quarter")
        if isinstance(inferred_year, int) and inferred_year > 1900 : # Validar año inferido
             year_to_use = inferred_year
        if isinstance(inferred_quarter, str) and inferred_quarter not in ["Not found", "Unknown", ""]:
             quarter_to_use = inferred_quarter


    standardized_report_details = schemas.ReportDetails(
        report_name=original_report_details.report_name, # Mantener nombre original
        report_url=original_report_details.report_url,   # Mantener URL original
        year=year_to_use,
        quarter=quarter_to_use
    )

    op_highlights = [
        schemas.MetricItem(metric_name=item.metric_name, quarter_value=item.quarter_value, ytd_value=item.ytd_value)
        for item in llm_result.operational_highlights
    ]
    fin_highlights = [
        schemas.MetricItem(metric_name=item.metric_name, quarter_value=item.quarter_value, ytd_value=item.ytd_value)
        for item in llm_result.financial_highlights
    ]

    return schemas.StandardizedExtractionOutput(
        report_details=standardized_report_details,
        operational_highlights=op_highlights,
        financial_highlights=fin_highlights,
        accuracy_score=accuracy_score,
        raw_llm_output=llm_result.model_dump() # Guardar el modelo Pydantic como dict
    )


def orchestrate_report_extraction_process(db: Session, start_year: int, end_year: int) -> schemas.TriggerExtractionResponse:
    """
    Orquesta el proceso completo:
    1. Obtiene URLs de informes.
    2. Para cada informe:
        a. Descarga PDF.
        b. Procesa con IA.
        c. Estandariza y calcula score.
        d. Guarda en DB.
    """
    print(f"Iniciando proceso de extracción para años: {start_year}-{end_year}")
    
    # 1. Obtener URLs de informes
    report_infos_from_web = report_fetcher_adapter.fetch_financial_report_urls(start_year, end_year)
    
    if not report_infos_from_web:
        return schemas.TriggerExtractionResponse(
            message="No se encontraron informes en el sitio web para el rango de años especificado.",
            reports_identified_count=0,
            report_urls_found=[]
        )

    # Crear/actualizar entradas en la DB para los informes encontrados
    db_reports_to_process: List[db_adapter.FinancialReport] = []
    for report_detail_from_web in report_infos_from_web:
        # report_detail_from_web es schemas.ReportDetails
        # db_adapter.create_financial_report espera schemas.ReportDetails
        db_report_entry = db_adapter.create_financial_report(db, report_detail_from_web)
        db_reports_to_process.append(db_report_entry)

    print(f"{len(db_reports_to_process)} informes registrados/actualizados en la DB para procesamiento.")

    # 2. Procesar cada informe (esto podría ser asíncrono en una app real)
    # Por ahora, lo haremos síncrono uno por uno.
    for db_report in db_reports_to_process:
        if db_report.extraction_status == "SUCCESS" and db_report.accuracy_score is not None and db_report.accuracy_score > 80: # Ejemplo de umbral para no reprocesar
            print(f"Informe {db_report.report_name} ya procesado con éxito. Omitiendo.")
            continue

        print(f"\nProcesando informe: {db_report.report_name} (ID: {db_report.id}, URL: {db_report.report_url})")
        db_adapter.update_financial_report_status(db, db_report.id, "PROCESSING")

        # 2a. Descargar PDF
        pdf_bytes = report_fetcher_adapter.download_pdf_content(str(db_report.report_url))
        if not pdf_bytes:
            error_msg = f"Fallo al descargar PDF: {db_report.report_url}"
            print(error_msg)
            db_adapter.update_financial_report_status(db, db_report.id, "FAILED", error_msg)
            continue
        
        print(f"PDF descargado ({len(pdf_bytes)} bytes). Iniciando procesamiento AI...")

        # 2b. Procesar con IA
        # Simular un pequeño delay para no saturar la API de Gemini si son muchos informes
        time.sleep(1) # Quitar en producción o si se manejan cuotas de API adecuadamente

        llm_extraction_result, raw_llm_response, ai_error_msg = ai_processing_adapter.process_pdf_with_ai(pdf_bytes, db_report.report_name)
        
        if ai_error_msg or not llm_extraction_result:
            full_error_msg = f"Error en AI: {ai_error_msg if ai_error_msg else 'Resultado de LLM vacío.'}"
            print(full_error_msg)
            # Guardar la respuesta cruda del LLM si hubo un error pero se obtuvo algo
            if raw_llm_response:
                 db_report.raw_extracted_data = raw_llm_response # Actualizar directamente el objeto db_report
                 db.commit() # Guardar el raw_extracted_data
            db_adapter.update_financial_report_status(db, db_report.id, "FAILED", full_error_msg)
            continue
        
        print("Procesamiento AI completado. Estandarizando y calculando score...")
        # 2c. Estandarizar y calcular score
        # Necesitamos los detalles originales del informe (nombre, url, año, trimestre) para la estandarización
        original_report_details_for_std = schemas.ReportDetails(
            report_name=db_report.report_name,
            report_url=db_report.report_url, # Convertir a HttpUrl si es necesario, pero ya debería serlo
            year=db_report.year,
            quarter=db_report.quarter
        )
        standardized_data = _standardize_llm_output(llm_extraction_result, original_report_details_for_std)
        
        print(f"Datos estandarizados. Score de precisión: {standardized_data.accuracy_score}%")
        
        # 2d. Guardar en DB
        db_adapter.save_extracted_data_to_db(db, db_report.id, standardized_data)
        print(f"Informe {db_report.report_name} procesado y guardado.")

    return schemas.TriggerExtractionResponse(
        message=f"Proceso de extracción completado para {len(db_reports_to_process)} informes.",
        reports_identified_count=len(report_infos_from_web),
        report_urls_found=[r.report_url for r in report_infos_from_web]
    )


def get_report_data_by_id(db: Session, report_id: int) -> Optional[schemas.ExtractedReportDataResponse]:
    """Obtiene los datos extraídos de un informe específico."""
    db_report = db_adapter.get_financial_report_by_id(db, report_id)
    if not db_report:
        return None

    # Convertir los datos de la DB (modelos SQLAlchemy) a esquemas Pydantic para la respuesta API
    op_highlights_db = db_report.operational_highlights
    fin_highlights_db = db_report.financial_highlights

    op_items = [
        schemas.MetricItem(
            metric_name=item.metric_name,
            quarter_value=item.quarter_value,
            ytd_value=item.year_to_date_value
        ) for item in op_highlights_db
    ]
    fin_items = [
        schemas.MetricItem(
            metric_name=item.metric_name,
            quarter_value=item.quarter_value,
            ytd_value=item.year_to_date_value
        ) for item in fin_highlights_db
    ]

    return schemas.ExtractedReportDataResponse(
        id=db_report.id,
        report_name=db_report.report_name,
        report_url=db_report.report_url, # Pydantic validará si es HttpUrl
        year=db_report.year,
        quarter=db_report.quarter,
        extraction_status=db_report.extraction_status,
        accuracy_score=db_report.accuracy_score,
        operational_highlights=op_items,
        financial_highlights=fin_items,
        raw_extracted_data=db_report.raw_extracted_data, # Esto ya es un dict/JSON
        error_message=db_report.error_message
    )

def get_all_reports_summary(db: Session) -> schemas.AllReportsSummaryResponse:
    """Obtiene un resumen de todos los informes en la base de datos."""
    stats = db_adapter.get_reports_summary_stats(db)
    all_db_reports = db_adapter.get_all_financial_reports(db, limit=500) # Limitar por si hay demasiados

    report_summaries = [
        schemas.ReportSummaryItem(
            id=db_r.id,
            report_name=db_r.report_name,
            year=db_r.year,
            quarter=db_r.quarter,
            status=db_r.extraction_status,
            accuracy=db_r.accuracy_score
        ) for db_r in all_db_reports
    ]
    
    return schemas.AllReportsSummaryResponse(
        total_reports_in_db=stats["total_reports_in_db"],
        reports_processed_successfully=stats["reports_processed_successfully"],
        reports_failed=stats["reports_failed"],
        average_accuracy=stats["average_accuracy"],
        reports=report_summaries
    )


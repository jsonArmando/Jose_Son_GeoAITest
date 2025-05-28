# app/core/use_cases.py
from sqlalchemy.orm.session import Session as DBSessionType 
from typing import List, Tuple, Optional, Dict, Any, Type
import time
from collections import defaultdict 
from pydantic import HttpUrl # <--- ASEGÚRATE QUE ESTA LÍNEA ESTÉ PRESENTE Y CORRECTA

from adapters import db_adapter, report_fetcher_adapter, ai_processing_adapter
from core import schemas, ai_prompts 
from config import settings

def _calculate_accuracy_score(llm_result: schemas.LLMFullExtractionResult) -> float:
    total_expected_fields = 0
    found_and_valid_fields = 0

    expected_op_metrics_names = set(ai_prompts.EXPECTED_OPERATIONAL_METRICS)
    total_expected_fields += len(expected_op_metrics_names) * 2 

    expected_fin_metrics_names = set(ai_prompts.EXPECTED_FINANCIAL_METRICS)
    total_expected_fields += len(expected_fin_metrics_names) * 2

    total_expected_fields += 2 # year, quarter for report_details

    if llm_result.report_details_inferred:
        year_val = llm_result.report_details_inferred.year 
        if year_val is not None and str(year_val).strip().lower() not in ["not found", ""]:
            found_and_valid_fields += 1
        
        quarter_val = llm_result.report_details_inferred.quarter
        if quarter_val is not None and str(quarter_val).strip().lower() not in ["not found", ""]:
            found_and_valid_fields += 1
    
    for item in llm_result.operational_highlights:
        if item.metric_name in expected_op_metrics_names:
            if item.quarter_value is not None and str(item.quarter_value).strip().lower() != "not found":
                found_and_valid_fields += 1
            if item.ytd_value is not None and str(item.ytd_value).strip().lower() != "not found":
                found_and_valid_fields += 1
    
    for item in llm_result.financial_highlights:
        if item.metric_name in expected_fin_metrics_names:
            if item.quarter_value is not None and str(item.quarter_value).strip().lower() != "not found":
                found_and_valid_fields += 1
            if item.ytd_value is not None and str(item.ytd_value).strip().lower() != "not found":
                found_and_valid_fields += 1

    if total_expected_fields == 0:
        return 0.0

    accuracy = (found_and_valid_fields / total_expected_fields) * 100
    return round(accuracy, 2)

def _standardize_llm_output(
    llm_result: schemas.LLMFullExtractionResult, 
    original_report_details: schemas.ReportDetails 
) -> schemas.StandardizedExtractionOutput:
    accuracy_score = _calculate_accuracy_score(llm_result)
    
    year_to_use = original_report_details.year
    quarter_to_use = original_report_details.quarter

    if llm_result.report_details_inferred:
        inferred_year_val = llm_result.report_details_inferred.year
        if inferred_year_val is not None:
            try:
                inferred_year_int = int(inferred_year_val) 
                if inferred_year_int > 1900: 
                    year_to_use = inferred_year_int
            except (ValueError, TypeError):
                pass 

        inferred_quarter_val = llm_result.report_details_inferred.quarter
        if isinstance(inferred_quarter_val, str) and inferred_quarter_val.strip().lower() not in ["not found", "unknown", ""]:
             quarter_to_use = inferred_quarter_val.upper()

    standardized_report_details = schemas.ReportDetails(
        report_name=original_report_details.report_name,
        report_url=original_report_details.report_url, 
        year=year_to_use,
        quarter=quarter_to_use
    )

    op_highlights = [
        schemas.MetricItem(metric_name=item.metric_name, quarter_value=str(item.quarter_value), ytd_value=str(item.ytd_value))
        for item in llm_result.operational_highlights
    ]
    fin_highlights = [
        schemas.MetricItem(metric_name=item.metric_name, quarter_value=str(item.quarter_value), ytd_value=str(item.ytd_value))
        for item in llm_result.financial_highlights
    ]

    return schemas.StandardizedExtractionOutput(
        report_details=standardized_report_details,
        operational_highlights=op_highlights,
        financial_highlights=fin_highlights,
        accuracy_score=accuracy_score,
        raw_llm_output=llm_result.model_dump()
    )


def orchestrate_report_extraction_process(
    session_factory: Type[DBSessionType], 
    start_year: int, 
    end_year: int
) -> None: 
    db: DBSessionType = session_factory() 
    try:
        print(f"BG TASK: Iniciando proceso de extracción para años: {start_year}-{end_year}")
        
        report_infos_from_web = report_fetcher_adapter.fetch_financial_report_urls(start_year, end_year)
        
        if not report_infos_from_web:
            print("BG TASK: No se encontraron informes en el sitio web.")
            db.close() 
            return

        for report_detail_from_web in report_infos_from_web:
            db_adapter.create_financial_report(db, report_detail_from_web)
        db.commit() 
        
        pending_reports = db_adapter.get_pending_financial_reports(db)
        print(f"BG TASK: {len(pending_reports)} informes marcados como PENDIENTES para procesamiento.")

        for db_report in pending_reports: 
            if not (start_year <= db_report.year <= end_year):
                continue

            print(f"\nBG TASK: Procesando informe: {db_report.report_name} (ID: {db_report.id}, URL: {db_report.report_url})")
            
            db_adapter.update_financial_report_status(db, db_report.id, "PROCESSING")
            db.commit() 

            pdf_bytes = report_fetcher_adapter.download_pdf_content(str(db_report.report_url)) 
            if not pdf_bytes:
                error_msg = f"Fallo al descargar PDF: {db_report.report_url}"
                print(f"BG TASK: {error_msg}")
                db_adapter.update_financial_report_status(db, db_report.id, "FAILED", error_msg)
                db.commit()
                continue
            
            print(f"BG TASK: PDF descargado ({len(pdf_bytes)} bytes). Iniciando procesamiento AI...")
            
            llm_extraction_result, raw_llm_response, ai_error_msg = ai_processing_adapter.process_pdf_with_ai(pdf_bytes, db_report.report_name)
            
            if ai_error_msg or not llm_extraction_result:
                full_error_msg = f"Error en AI: {ai_error_msg if ai_error_msg else 'Resultado de LLM vacío o inválido.'}"
                print(f"BG TASK: {full_error_msg}")
                
                report_to_update = db_adapter.get_financial_report_by_id(db, db_report.id)
                if report_to_update: 
                    if raw_llm_response:
                        report_to_update.raw_extracted_data = raw_llm_response
                    report_to_update.extraction_status = "FAILED"
                    report_to_update.error_message = full_error_msg
                    db.add(report_to_update) 
                    db.commit()
                else:
                    print(f"BG TASK: No se pudo encontrar el informe ID {db_report.id} para actualizar el error.")
                continue 
            
            print("BG TASK: Procesamiento AI completado. Estandarizando y calculando score...")
            
            try:
                report_url_for_schema_obj = HttpUrl(str(db_report.report_url))
            except Exception as val_err:
                print(f"BG TASK: URL inválida desde DB para informe ID {db_report.id}: {db_report.report_url}. Usando placeholder. Error: {val_err}")
                report_url_for_schema_obj = HttpUrl("http://example.com/invalid_db_url")

            original_report_details_for_std = schemas.ReportDetails(
                report_name=db_report.report_name,
                report_url=report_url_for_schema_obj, 
                year=db_report.year,
                quarter=db_report.quarter
            )
            standardized_data = _standardize_llm_output(llm_extraction_result, original_report_details_for_std)
            
            print(f"BG TASK: Datos estandarizados. Score de precisión: {standardized_data.accuracy_score}%")
            
            db_adapter.save_extracted_data_to_db(db, db_report.id, standardized_data)
            db.commit() 
            print(f"BG TASK: Informe {db_report.report_name} procesado y guardado.")

        print(f"BG TASK: Proceso de extracción completado.")
    except Exception as e:
        import traceback
        print(f"BG TASK: Error catastrófico durante la orquestación: {e}\n{traceback.format_exc()}")
        db.rollback() 
    finally:
        db.close() 


def get_report_data_by_id(db: DBSessionType, report_id: int) -> Optional[schemas.ExtractedReportDataResponse]:
    db_report = db_adapter.get_financial_report_by_id(db, report_id)
    if not db_report:
        return None

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
    
    try:
        report_url_str_for_response = str(db_report.report_url)
        # Pydantic en ExtractedReportDataResponse validará si es HttpUrl
    except Exception:
        report_url_str_for_response = "http://example.com/invalid-db-url"


    return schemas.ExtractedReportDataResponse(
        id=db_report.id,
        report_name=db_report.report_name,
        report_url=report_url_str_for_response, 
        year=db_report.year,
        quarter=db_report.quarter,
        extraction_status=db_report.extraction_status,
        accuracy_score=db_report.accuracy_score,
        operational_highlights=op_items,
        financial_highlights=fin_items,
        raw_extracted_data=db_report.raw_extracted_data,
        error_message=db_report.error_message
    )

def get_formatted_annual_table(db: DBSessionType, year: int) -> Optional[schemas.AnnualReportTableResponse]:
    reports_for_year = db.query(db_adapter.FinancialReport).filter(
        db_adapter.FinancialReport.year == year,
        db_adapter.FinancialReport.extraction_status.in_(["SUCCESS", "PARTIAL_SUCCESS"]) 
    ).order_by(db_adapter.FinancialReport.quarter).all()

    if not reports_for_year:
        print(f"No se encontraron informes procesados para el año {year} para generar tabla anual.")
        return None

    op_data_by_metric = defaultdict(lambda: {"Q1": "Not found", "Q2": "Not found", "Q3": "Not found", "Q4": "Not found", "FY": "Not found"})
    fin_data_by_metric = defaultdict(lambda: {"Q1": "Not found", "Q2": "Not found", "Q3": "Not found", "Q4": "Not found", "FY": "Not found"})

    report_id_to_quarter_map = {r.id: r.quarter for r in reports_for_year}
    report_ids_for_year = list(report_id_to_quarter_map.keys())

    all_op_highlights = db.query(db_adapter.OperationalHighlight).filter(db_adapter.OperationalHighlight.report_id.in_(report_ids_for_year)).all()
    all_fin_highlights = db.query(db_adapter.FinancialHighlight).filter(db_adapter.FinancialHighlight.report_id.in_(report_ids_for_year)).all()

    for oh in all_op_highlights:
        quarter = report_id_to_quarter_map.get(oh.report_id)
        if quarter and quarter in ["Q1", "Q2", "Q3", "Q4"]:
            op_data_by_metric[oh.metric_name][quarter] = oh.quarter_value
            if quarter == "Q4" and oh.year_to_date_value and oh.year_to_date_value.lower() != "not found":
                op_data_by_metric[oh.metric_name]["FY"] = oh.year_to_date_value

    for fh in all_fin_highlights:
        quarter = report_id_to_quarter_map.get(fh.report_id)
        if quarter and quarter in ["Q1", "Q2", "Q3", "Q4"]:
            fin_data_by_metric[fh.metric_name][quarter] = fh.quarter_value
            if quarter == "Q4" and fh.year_to_date_value and fh.year_to_date_value.lower() != "not found":
                fin_data_by_metric[fh.metric_name]["FY"] = fh.year_to_date_value
    
    fy_report = next((r for r in reports_for_year if r.quarter == "FY"), None)
    if fy_report:
        fy_op_highlights = db.query(db_adapter.OperationalHighlight).filter(db_adapter.OperationalHighlight.report_id == fy_report.id).all()
        fy_fin_highlights = db.query(db_adapter.FinancialHighlight).filter(db_adapter.FinancialHighlight.report_id == fy_report.id).all()
        for oh in fy_op_highlights:
            if oh.quarter_value and oh.quarter_value.lower() != "not found":
                 op_data_by_metric[oh.metric_name]["FY"] = oh.quarter_value
        for fh in fy_fin_highlights:
            if fh.quarter_value and fh.quarter_value.lower() != "not found":
                 fin_data_by_metric[fh.metric_name]["FY"] = fh.quarter_value

    op_table = []
    for metric_name in ai_prompts.EXPECTED_OPERATIONAL_METRICS:
        data = op_data_by_metric[metric_name]
        op_table.append(schemas.TableRow(metric_name=metric_name, q1_value=data["Q1"], q2_value=data["Q2"], q3_value=data["Q3"], q4_value=data["Q4"], annual_value=data["FY"]))

    fin_table = []
    for metric_name in ai_prompts.EXPECTED_FINANCIAL_METRICS:
        data = fin_data_by_metric[metric_name]
        fin_table.append(schemas.TableRow(metric_name=metric_name, q1_value=data["Q1"], q2_value=data["Q2"], q3_value=data["Q3"], q4_value=data["Q4"], annual_value=data["FY"]))
        
    return schemas.AnnualReportTableResponse(year=year, operational_table=op_table, financial_table=fin_table)


def get_all_reports_summary(db: DBSessionType) -> schemas.AllReportsSummaryResponse:
    stats = db_adapter.get_reports_summary_stats(db)
    all_db_reports = db.query(db_adapter.FinancialReport).order_by(
        db_adapter.FinancialReport.year.desc(), 
        db_adapter.FinancialReport.quarter.desc(), 
        db_adapter.FinancialReport.report_name
    ).limit(500).all()

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

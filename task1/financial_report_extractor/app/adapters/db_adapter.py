# app/adapters/db_adapter.py
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, JSON, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.sql import func # Para timestamps automáticos

from app.config import settings # Importa la configuración de la aplicación (DATABASE_URL)
from app.core import schemas # Importa los esquemas Pydantic para validación y tipado
from typing import List, Optional, Dict, Any

# --- Configuración de SQLAlchemy ---
DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modelos SQLAlchemy (Tablas de la Base de Datos) ---

class FinancialReport(Base):
    """
    Modelo para la tabla 'financial_reports'.
    Almacena información sobre cada informe financiero procesado o por procesar.
    """
    __tablename__ = "financial_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    report_name = Column(String, index=True, nullable=False)
    report_url = Column(String, unique=True, nullable=False) # URL del informe PDF
    year = Column(Integer, index=True, nullable=False)
    quarter = Column(String, index=True, nullable=False) # Ej: "Q1", "Q2", "FY" (Full Year)
    
    extraction_status = Column(String, default="PENDING", nullable=False) # Ej: PENDING, PROCESSING, SUCCESS, PARTIAL_SUCCESS, FAILED
    accuracy_score = Column(Float, nullable=True) # Puntaje de 0 a 100
    
    # Almacena la respuesta cruda del LLM o datos intermedios para auditoría o reprocesamiento
    raw_extracted_data = Column(JSON, nullable=True) 
    error_message = Column(Text, nullable=True) # Para registrar errores durante el procesamiento

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relaciones con las tablas de métricas
    operational_highlights = relationship("OperationalHighlight", back_populates="report", cascade="all, delete-orphan")
    financial_highlights = relationship("FinancialHighlight", back_populates="report", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FinancialReport(id={self.id}, name='{self.report_name}', year={self.year}, quarter='{self.quarter}')>"

class OperationalHighlight(Base):
    """
    Modelo para la tabla 'operational_highlights'.
    Almacena las métricas operativas extraídas para cada informe.
    """
    __tablename__ = "operational_highlights"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("financial_reports.id"), nullable=False) # Clave foránea a financial_reports
    
    metric_name = Column(String, nullable=False)
    # Guardamos como String para permitir "Not found" u otros marcadores.
    # La conversión a numérico se haría en la lógica de la aplicación si es necesario.
    quarter_value = Column(String, nullable=True) 
    year_to_date_value = Column(String, nullable=True)
    
    # Podría ser útil para diferenciar si esta métrica pertenece a un resumen anual vs trimestral directamente en la tabla
    # is_annual_summary_metric = Column(Boolean, default=False) 

    report = relationship("FinancialReport", back_populates="operational_highlights")

    def __repr__(self):
        return f"<OperationalHighlight(report_id={self.report_id}, metric='{self.metric_name}', q_value='{self.quarter_value}')>"

class FinancialHighlight(Base):
    """
    Modelo para la tabla 'financial_highlights'.
    Almacena las métricas financieras extraídas para cada informe.
    """
    __tablename__ = "financial_highlights"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("financial_reports.id"), nullable=False) # Clave foránea a financial_reports

    metric_name = Column(String, nullable=False)
    quarter_value = Column(String, nullable=True)
    year_to_date_value = Column(String, nullable=True)
    
    # is_annual_summary_metric = Column(Boolean, default=False)

    report = relationship("FinancialReport", back_populates="financial_highlights")

    def __repr__(self):
        return f"<FinancialHighlight(report_id={self.report_id}, metric='{self.metric_name}', q_value='{self.quarter_value}')>"


# --- Función para crear todas las tablas en la base de datos ---
def create_db_tables():
    """
    Crea todas las tablas definidas en los modelos SQLAlchemy si no existen.
    Se llama generalmente al inicio de la aplicación.
    """
    Base.metadata.create_all(bind=engine)

# --- Funciones de Interacción con la Base de Datos (CRUD Simplificado) ---

def get_db():
    """
    Generador de dependencias para obtener una sesión de base de datos.
    Usado por FastAPI para inyectar la sesión en los endpoints.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Operaciones para FinancialReport
def create_financial_report(db: Session, report_data: schemas.ReportDetails) -> FinancialReport:
    """Crea un nuevo registro de informe financiero si no existe uno con la misma URL."""
    db_report = db.query(FinancialReport).filter(FinancialReport.report_url == str(report_data.report_url)).first()
    if db_report:
        # Actualizar estado a PENDING si se vuelve a disparar la extracción para un reporte existente
        db_report.extraction_status = "PENDING"
        db_report.accuracy_score = None
        db_report.raw_extracted_data = None
        db_report.error_message = None
        # Limpiar métricas antiguas asociadas si se va a reprocesar
        db.query(OperationalHighlight).filter(OperationalHighlight.report_id == db_report.id).delete()
        db.query(FinancialHighlight).filter(FinancialHighlight.report_id == db_report.id).delete()
        
        db.commit()
        db.refresh(db_report)
        return db_report

    db_report = FinancialReport(
        report_name=report_data.report_name,
        report_url=str(report_data.report_url), # Asegurar que HttpUrl se convierte a string
        year=report_data.year,
        quarter=report_data.quarter,
        extraction_status="PENDING"
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def get_financial_report_by_id(db: Session, report_id: int) -> Optional[FinancialReport]:
    """Obtiene un informe financiero por su ID."""
    return db.query(FinancialReport).filter(FinancialReport.id == report_id).first()

def get_all_financial_reports(db: Session, skip: int = 0, limit: int = 100) -> List[FinancialReport]:
    """Obtiene todos los informes financieros con paginación."""
    return db.query(FinancialReport).offset(skip).limit(limit).all()

def get_pending_financial_reports(db: Session) -> List[FinancialReport]:
    """Obtiene todos los informes financieros pendientes de procesar."""
    return db.query(FinancialReport).filter(FinancialReport.extraction_status == "PENDING").all()


def update_financial_report_status(db: Session, report_id: int, status: str, error_msg: Optional[str] = None) -> Optional[FinancialReport]:
    """Actualiza el estado de extracción de un informe."""
    db_report = get_financial_report_by_id(db, report_id)
    if db_report:
        db_report.extraction_status = status
        if error_msg:
            db_report.error_message = error_msg
        db_report.updated_at = func.now() # Actualizar timestamp
        db.commit()
        db.refresh(db_report)
    return db_report

def save_extracted_data_to_db(db: Session, report_id: int, extracted_data: schemas.StandardizedExtractionOutput):
    """
    Guarda los datos extraídos (métricas, score, raw_data) para un informe.
    """
    db_report = get_financial_report_by_id(db, report_id)
    if not db_report:
        # Esto no debería ocurrir si el flujo es correcto
        print(f"Error: Reporte con ID {report_id} no encontrado para guardar datos extraídos.")
        return

    # Limpiar métricas antiguas si existen (en caso de reprocesamiento)
    db.query(OperationalHighlight).filter(OperationalHighlight.report_id == report_id).delete()
    db.query(FinancialHighlight).filter(FinancialHighlight.report_id == report_id).delete()
    db.commit() # Aplicar el delete

    # Guardar nuevas métricas operativas
    for oh_item in extracted_data.operational_highlights:
        db_oh = OperationalHighlight(
            report_id=report_id,
            metric_name=oh_item.metric_name,
            quarter_value=str(oh_item.quarter_value) if oh_item.quarter_value is not None else None,
            year_to_date_value=str(oh_item.ytd_value) if oh_item.ytd_value is not None else None
        )
        db.add(db_oh)

    # Guardar nuevas métricas financieras
    for fh_item in extracted_data.financial_highlights:
        db_fh = FinancialHighlight(
            report_id=report_id,
            metric_name=fh_item.metric_name,
            quarter_value=str(fh_item.quarter_value) if fh_item.quarter_value is not None else None,
            year_to_date_value=str(fh_item.ytd_value) if fh_item.ytd_value is not None else None
        )
        db.add(db_fh)

    # Actualizar el informe principal
    db_report.accuracy_score = extracted_data.accuracy_score
    db_report.raw_extracted_data = extracted_data.raw_llm_output
    db_report.extraction_status = "SUCCESS" # O "PARTIAL_SUCCESS" si el score es bajo
    if extracted_data.accuracy_score < 50: # Umbral de ejemplo
         db_report.extraction_status = "PARTIAL_SUCCESS"
    db_report.error_message = None # Limpiar errores previos si la extracción fue exitosa
    db_report.updated_at = func.now()

    db.commit()
    db.refresh(db_report)
    print(f"Datos extraídos guardados para el informe ID {report_id} con score {db_report.accuracy_score}%.")


def get_reports_summary_stats(db: Session) -> Dict[str, Any]:
    """Calcula estadísticas resumidas sobre los informes."""
    total_reports = db.query(FinancialReport).count()
    successful_reports = db.query(FinancialReport).filter(
        FinancialReport.extraction_status.in_(["SUCCESS", "PARTIAL_SUCCESS"])
    ).count()
    failed_reports = db.query(FinancialReport).filter(FinancialReport.extraction_status == "FAILED").count()
    
    avg_accuracy_query = db.query(func.avg(FinancialReport.accuracy_score)).filter(FinancialReport.accuracy_score.isnot(None))
    avg_accuracy_result = avg_accuracy_query.scalar()
    
    return {
        "total_reports_in_db": total_reports,
        "reports_processed_successfully": successful_reports,
        "reports_failed": failed_reports,
        "average_accuracy": round(avg_accuracy_result, 2) if avg_accuracy_result is not None else None
    }

# Nota: En una aplicación más grande, estas funciones CRUD estarían mejor organizadas,
# posiblemente en clases Repositorio dedicadas para cada modelo.
# Para esta implementación simplificada, se mantienen juntas.

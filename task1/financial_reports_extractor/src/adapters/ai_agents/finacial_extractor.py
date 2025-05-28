"""
AI Financial Data Extraction Agent
Multi-modal AI agent for extracting financial data from documents
"""

import asyncio
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import PyMuPDF as fitz  # pymupdf
import pdfplumber
import camelot
import pandas as pd
from PIL import Image
import pytesseract
import openai
from anthropic import AsyncAnthropic

from ...domain.ports import AIExtractionPort, LoggingPort, CachePort
from ...domain.value_objects import (
    FinancialMetrics, 
    AIExtractionConfiguration, 
    ExtractionContext
)


class MultiModalFinancialExtractor(AIExtractionPort):
    """
    Extractor multi-modal que combina múltiples técnicas:
    - OCR para texto e imágenes
    - Extracción de tablas
    - Procesamiento con múltiples modelos de IA
    - Validación cruzada
    """
    
    def __init__(
        self,
        openai_api_key: str,
        anthropic_api_key: Optional[str] = None,
        cache: Optional[CachePort] = None,
        logger: Optional[LoggingPort] = None
    ):
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
        self.anthropic_client = AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else None
        self.cache = cache
        self.logger = logger
        
        # Templates de prompts especializados
        self.extraction_prompts = {
            'quarterly': self._get_quarterly_extraction_prompt(),
            'annual': self._get_annual_extraction_prompt(),
            'general': self._get_general_extraction_prompt()
        }
        
        # Configuración OCR
        pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
    
    async def extract_financial_data(
        self,
        file_path: str,
        context: ExtractionContext,
        config: AIExtractionConfiguration
    ) -> FinancialMetrics:
        """
        Extrae datos financieros usando aproximación multi-modal
        """
        try:
            # 1. Verificar caché si está habilitado
            if self.cache and config.cache_responses:
                cached_result = await self._get_cached_extraction(file_path, context)
                if cached_result:
                    return cached_result
            
            # 2. Extraer contenido del documento
            document_content = await self._extract_document_content(file_path, config)
            
            # 3. Procesar con IA principal
            primary_extraction = await self._extract_with_primary_model(
                document_content, context, config
            )
            
            # 4. Validación cruzada con modelo secundario (si está disponible)
            if config.use_multiple_models and self.anthropic_client:
                secondary_extraction = await self._extract_with_secondary_model(
                    document_content, context, config
                )
                # Combinar resultados
                final_metrics = await self._merge_extractions(
                    primary_extraction, secondary_extraction, context
                )
            else:
                final_metrics = primary_extraction
            
            # 5. Post-procesamiento y validación
            validated_metrics = await self._post_process_metrics(final_metrics, context)
            
            # 6. Guardar en caché si está habilitado
            if self.cache and config.cache_responses:
                await self._cache_extraction(file_path, context, validated_metrics, config.cache_ttl_hours)
            
            if self.logger:
                await self.logger.log_info(
                    "Extracción financiera completada",
                    context={
                        'file_path': file_path,
                        'confidence': validated_metrics.extraction_confidence,
                        'completeness': validated_metrics.get_completeness_score()
                    }
                )
            
            return validated_metrics
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en extracción financiera",
                    error=e,
                    context={'file_path': file_path}
                )
            raise
    
    async def _extract_document_content(
        self, 
        file_path: str, 
        config: AIExtractionConfiguration
    ) -> Dict[str, Any]:
        """
        Extrae contenido completo del documento usando múltiples métodos
        """
        content = {
            'text': '',
            'tables': [],
            'images': [],
            'metadata': {}
        }
        
        try:
            # 1. Extraer texto principal
            content['text'] = await self._extract_text_content(file_path, config)
            
            # 2. Extraer tablas si está habilitado
            if config.process_tables:
                content['tables'] = await self._extract_tables(file_path)
            
            # 3. Procesar imágenes si está habilitado
            if config.process_images:
                content['images'] = await self._process_document_images(file_path, config)
            
            # 4. Extraer metadatos del documento
            content['metadata'] = await self._extract_document_metadata(file_path)
            
            return content
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error extrayendo contenido del documento",
                    error=e,
                    context={'file_path': file_path}
                )
            raise
    
    async def _extract_text_content(
        self, 
        file_path: str, 
        config: AIExtractionConfiguration
    ) -> str:
        """
        Extrae texto del PDF usando múltiples bibliotecas
        """
        text_content = ""
        
        try:
            # Método 1: PyMuPDF (rápido y eficiente)
            with fitz.open(file_path) as pdf_doc:
                for page_num in range(min(pdf_doc.page_count, config.max_pages_per_document)):
                    page = pdf_doc[page_num]
                    text_content += page.get_text() + "\n\n"
            
            # Si el texto extraído es muy poco, intentar con OCR
            if len(text_content.strip()) < 100 and config.use_ocr:
                text_content = await self._extract_text_with_ocr(file_path, config)
            
            return text_content
            
        except Exception as e:
            # Fallback: Intentar con pdfplumber
            if self.logger:
                await self.logger.log_warning(
                    "Error con PyMuPDF, intentando con pdfplumber",
                    error=e
                )
            
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages[:config.max_pages_per_document]:
                        page_text = page.extract_text()
                        if page_text:
                            text_content += page_text + "\n\n"
                
                return text_content
                
            except Exception as e2:
                if self.logger:
                    await self.logger.log_warning(
                        "Error con pdfplumber, usando texto vacío",
                        error=e2
                    )
                return ""
    
    async def _extract_text_with_ocr(
        self, 
        file_path: str, 
        config: AIExtractionConfiguration
    ) -> str:
        """
        Extrae texto usando OCR en las páginas del PDF
        """
        try:
            # Convertir PDF a imágenes
            pdf_doc = fitz.open(file_path)
            ocr_text = ""
            
            for page_num in range(min(pdf_doc.page_count, config.max_pages_per_document)):
                # Convertir página a imagen
                page = pdf_doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom para mejor OCR
                img_data = pix.tobytes("png")
                
                # Aplicar OCR
                img = Image.open(io.BytesIO(img_data))
                page_text = pytesseract.image_to_string(
                    img, 
                    lang='+'.join(config.ocr_languages),
                    config='--psm 6'  # Uniform block of text
                )
                
                ocr_text += page_text + "\n\n"
            
            pdf_doc.close()
            return ocr_text
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error en extracción OCR",
                    error=e
                )
            return ""
    
    async def _extract_tables(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extrae tablas del PDF usando Camelot
        """
        tables_data = []
        
        try:
            # Usar Camelot para extracción de tablas
            tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
            
            for i, table in enumerate(tables):
                if table.parsing_report['accuracy'] > 50:  # Solo tablas con buena precisión
                    table_data = {
                        'table_index': i,
                        'page': table.parsing_report['page'],
                        'accuracy': table.parsing_report['accuracy'],
                        'data': table.df.to_dict('records'),
                        'headers': table.df.columns.tolist(),
                        'shape': table.df.shape
                    }
                    tables_data.append(table_data)
            
            # Fallback: Intentar con flavor 'stream' si no se encontraron tablas
            if not tables_data:
                tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
                for i, table in enumerate(tables):
                    table_data = {
                        'table_index': i,
                        'page': 1,  # Stream no proporciona página específica
                        'accuracy': 70,  # Asumir precisión razonable
                        'data': table.df.to_dict('records'),
                        'headers': table.df.columns.tolist(),
                        'shape': table.df.shape
                    }
                    tables_data.append(table_data)
            
            return tables_data
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error extrayendo tablas",
                    error=e
                )
            return []
    
    async def process_document_images(
        self, 
        file_path: str, 
        config: AIExtractionConfiguration
    ) -> List[Dict[str, Any]]:
        """
        Procesa imágenes del documento para extraer información adicional
        """
        images_data = []
        
        try:
            pdf_doc = fitz.open(file_path)
            
            for page_num in range(min(pdf_doc.page_count, config.max_pages_per_document)):
                page = pdf_doc[page_num]
                
                # Extraer imágenes de la página
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    # Extraer imagen
                    xref = img[0]
                    pix = fitz.Pixmap(pdf_doc, xref)
                    
                    if pix.n - pix.alpha < 4:  # Solo procesar imágenes RGB/GRAY
                        img_data = pix.tobytes("png")
                        
                        # Aplicar OCR a la imagen
                        img_pil = Image.open(io.BytesIO(img_data))
                        ocr_text = pytesseract.image_to_string(img_pil)
                        
                        if ocr_text.strip():  # Solo si encontramos texto
                            image_info = {
                                'page': page_num + 1,
                                'image_index': img_index,
                                'ocr_text': ocr_text.strip(),
                                'size': (pix.width, pix.height),
                                'has_financial_data': self._contains_financial_data(ocr_text)
                            }
                            images_data.append(image_info)
                    
                    pix = None  # Liberar memoria
            
            pdf_doc.close()
            return images_data
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error procesando imágenes del documento",
                    error=e
                )
            return []
    
    def _contains_financial_data(self, text: str) -> bool:
        """
        Verifica si el texto contiene datos financieros
        """
        financial_indicators = [
            r'\$[\d,]+',  # Cantidades en dólares
            r'\b\d+\.\d+\b',  # Números decimales
            r'\b(revenue|income|profit|loss|assets|liabilities|equity)\b',  # Términos financieros
            r'\b(million|billion|thousand)\b',  # Magnitudes
            r'\%',  # Porcentajes
        ]
        
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in financial_indicators)
    
    async def _extract_with_primary_model(
        self, 
        content: Dict[str, Any], 
        context: ExtractionContext, 
        config: AIExtractionConfiguration
    ) -> FinancialMetrics:
        """
        Extrae datos usando el modelo principal (OpenAI)
        """
        try:
            # Seleccionar prompt apropiado
            prompt_template = self._select_extraction_prompt(context.document_type)
            
            # Preparar contexto
            extraction_prompt = prompt_template.format(
                company_name=context.company_name,
                reporting_period=context.reporting_period,
                fiscal_year=context.fiscal_year,
                document_text=content['text'][:15000],  # Limitar texto para el contexto
                tables_summary=self._summarize_tables(content.get('tables', [])),
                expected_currency=context.expected_currency
            )
            
            response = await self.openai_client.chat.completions.create(
                model=config.model_name,
                messages=[{"role": "user", "content": extraction_prompt}],
                response_format={"type": "json_object"},
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )
            
            # Parsear respuesta JSON
            extraction_data = json.loads(response.choices[0].message.content)
            
            # Convertir a FinancialMetrics
            return self._parse_extraction_response(extraction_data, context)
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en extracción con modelo principal",
                    error=e
                )
            raise
    
    async def _extract_with_secondary_model(
        self, 
        content: Dict[str, Any], 
        context: ExtractionContext, 
        config: AIExtractionConfiguration
    ) -> FinancialMetrics:
        """
        Extrae datos usando modelo secundario (Anthropic Claude)
        """
        if not self.anthropic_client:
            raise ValueError("Cliente Anthropic no configurado")
        
        try:
            prompt_template = self._select_extraction_prompt(context.document_type)
            
            extraction_prompt = prompt_template.format(
                company_name=context.company_name,
                reporting_period=context.reporting_period,
                fiscal_year=context.fiscal_year,
                document_text=content['text'][:15000],
                tables_summary=self._summarize_tables(content.get('tables', [])),
                expected_currency=context.expected_currency
            )
            
            response = await self.anthropic_client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                messages=[{"role": "user", "content": extraction_prompt}]
            )
            
            # Parsear respuesta (Claude puede no devolver JSON puro)
            response_text = response.content[0].text
            
            # Extraer JSON de la respuesta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                extraction_data = json.loads(json_match.group())
                return self._parse_extraction_response(extraction_data, context)
            else:
                raise ValueError("No se pudo extraer JSON de la respuesta de Claude")
                
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en extracción con modelo secundario",
                    error=e
                )
            raise
    
    def _select_extraction_prompt(self, document_type: str) -> str:
        """
        Selecciona el prompt apropiado según el tipo de documento
        """
        if 'quarterly' in document_type.lower():
            return self.extraction_prompts['quarterly']
        elif 'annual' in document_type.lower():
            return self.extraction_prompts['annual']
        else:
            return self.extraction_prompts['general']
    
    def _get_quarterly_extraction_prompt(self) -> str:
        """
        Prompt especializado para reportes trimestrales
        """
        return """
        Eres un experto analista financiero. Extrae los siguientes datos del reporte trimestral de {company_name} para el período {reporting_period}:

        DOCUMENTO:
        {document_text}

        TABLAS IDENTIFICADAS:
        {tables_summary}

        Extrae las siguientes métricas financieras (en {expected_currency}):

        INGRESOS:
        - Revenue (ingresos totales)
        - Net revenue (ingresos netos)
        - Gross revenue (ingresos brutos)

        RENTABILIDAD:
        - Net income (utilidad neta)
        - Gross profit (utilidad bruta)
        - Operating income (utilidad operativa)
        - EBITDA
        - EBIT

        BALANCE:
        - Total assets (activos totales)
        - Total liabilities (pasivos totales)
        - Shareholders equity (patrimonio)
        - Cash and cash equivalents (efectivo y equivalentes)

        FLUJO DE CAJA:
        - Operating cash flow (flujo operativo)
        - Free cash flow (flujo libre)
        - Investing cash flow (flujo de inversión)
        - Financing cash flow (flujo de financiamiento)

        POR ACCIÓN:
        - Earnings per share (utilidad por acción)
        - Book value per share (valor libro por acción)
        - Dividends per share (dividendos por acción)

        RATIOS:
        - Debt to equity ratio
        - Current ratio
        - Return on equity (ROE)
        - Return on assets (ROA)

        Responde en formato JSON con esta estructura exacta:
        {{
            "revenue": valor_numerico_o_null,
            "net_income": valor_numerico_o_null,
            "ebitda": valor_numerico_o_null,
            "total_assets": valor_numerico_o_null,
            "extraction_confidence": 0.0_a_1.0,
            "currency": "{expected_currency}",
            "reporting_period": "{reporting_period}",
            "source_pages": [numeros_de_pagina],
            "extraction_method": "ai_gpt4",
            "notes": "observaciones_importantes"
        }}

        INSTRUCCIONES:
        - Usa valores numéricos sin comas ni símbolos de moneda
        - Si no encuentras un valor, usa null
        - La confianza debe reflejar qué tan seguros están los datos
        - Incluye todas las métricas encontradas, no solo las principales
        - Los valores deben estar en la unidad base (ej: si dice "million", multiplica por 1,000,000)
        """
    
    def _get_annual_extraction_prompt(self) -> str:
        """
        Prompt especializado para reportes anuales
        """
        return """
        Eres un experto analista financiero. Extrae datos del reporte anual de {company_name} para el año fiscal {fiscal_year}:

        DOCUMENTO:
        {document_text}

        TABLAS:
        {tables_summary}

        Extrae TODAS las métricas financieras disponibles incluyendo comparaciones año a año.

        Responde en formato JSON con estructura completa incluyendo:
        - Todas las métricas del estado de resultados
        - Balance general completo
        - Estado de flujos de efectivo
        - Ratios financieros calculados
        - Métricas por acción
        - Comparaciones con período anterior si están disponibles

        Formato de respuesta:
        {{
            "revenue": valor,
            "net_income": valor,
            "total_assets": valor,
            "shareholders_equity": valor,
            "operating_cash_flow": valor,
            "extraction_confidence": 0.0_a_1.0,
            "currency": "{expected_currency}",
            "fiscal_year": {fiscal_year},
            "extraction_method": "ai_comprehensive",
            "completeness_score": 0.0_a_1.0
        }}
        """
    
    def _get_general_extraction_prompt(self) -> str:
        """
        Prompt general para documentos no clasificados
        """
        return """
        Analiza este documento financiero y extrae todas las métricas disponibles:

        DOCUMENTO:
        {document_text}

        Identifica el tipo de documento y extrae las métricas financieras más relevantes.

        Responde en JSON con las métricas encontradas y un nivel de confianza para cada una.
        """
    
    def _summarize_tables(self, tables: List[Dict[str, Any]]) -> str:
        """
        Crea un resumen de las tablas encontradas
        """
        if not tables:
            return "No se encontraron tablas estructuradas."
        
        summary = f"Se encontraron {len(tables)} tablas:\n\n"
        
        for i, table in enumerate(tables[:3]):  # Limitar a 3 tablas
            summary += f"Tabla {i+1} (Página {table.get('page', 'N/A')}):\n"
            summary += f"- Dimensiones: {table.get('shape', 'N/A')}\n"
            summary += f"- Precisión: {table.get('accuracy', 'N/A')}%\n"
            
            # Incluir algunas filas de muestra
            data = table.get('data', [])
            if data:
                summary += f"- Muestra de datos: {str(data[:2])}\n"
            summary += "\n"
        
        return summary
    
    def _parse_extraction_response(
        self, 
        data: Dict[str, Any], 
        context: ExtractionContext
    ) -> FinancialMetrics:
        """
        Convierte la respuesta de IA a objeto FinancialMetrics
        """
        try:
            return FinancialMetrics(
                # Métricas de ingresos
                revenue=self._safe_decimal_conversion(data.get('revenue')),
                gross_revenue=self._safe_decimal_conversion(data.get('gross_revenue')),
                net_revenue=self._safe_decimal_conversion(data.get('net_revenue')),
                
                # Métricas de rentabilidad
                net_income=self._safe_decimal_conversion(data.get('net_income')),
                gross_profit=self._safe_decimal_conversion(data.get('gross_profit')),
                operating_income=self._safe_decimal_conversion(data.get('operating_income')),
                ebitda=self._safe_decimal_conversion(data.get('ebitda')),
                ebit=self._safe_decimal_conversion(data.get('ebit')),
                
                # Métricas de balance
                total_assets=self._safe_decimal_conversion(data.get('total_assets')),
                total_liabilities=self._safe_decimal_conversion(data.get('total_liabilities')),
                shareholders_equity=self._safe_decimal_conversion(data.get('shareholders_equity')),
                cash_and_equivalents=self._safe_decimal_conversion(data.get('cash_and_equivalents')),
                
                # Métricas de flujo de caja
                operating_cash_flow=self._safe_decimal_conversion(data.get('operating_cash_flow')),
                investing_cash_flow=self._safe_decimal_conversion(data.get('investing_cash_flow')),
                financing_cash_flow=self._safe_decimal_conversion(data.get('financing_cash_flow')),
                free_cash_flow=self._safe_decimal_conversion(data.get('free_cash_flow')),
                
                # Métricas por acción
                earnings_per_share=self._safe_decimal_conversion(data.get('earnings_per_share')),
                book_value_per_share=self._safe_decimal_conversion(data.get('book_value_per_share')),
                dividends_per_share=self._safe_decimal_conversion(data.get('dividends_per_share')),
                
                # Ratios
                debt_to_equity_ratio=self._safe_decimal_conversion(data.get('debt_to_equity_ratio')),
                current_ratio=self._safe_decimal_conversion(data.get('current_ratio')),
                return_on_equity=self._safe_decimal_conversion(data.get('return_on_equity')),
                return_on_assets=self._safe_decimal_conversion(data.get('return_on_assets')),
                
                # Metadatos
                extraction_confidence=float(data.get('extraction_confidence', 0.5)),
                extraction_method=data.get('extraction_method', 'ai_extraction'),
                source_page_numbers=data.get('source_pages', []),
                currency=data.get('currency', context.expected_currency),
                reporting_period=data.get('reporting_period', context.reporting_period),
                fiscal_year_end=str(context.fiscal_year)
            )
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error parseando respuesta de extracción",
                    error=e,
                    context={'data': data}
                )
            raise
    
    def _safe_decimal_conversion(self, value: Any) -> Optional[Decimal]:
        """
        Convierte un valor a Decimal de forma segura
        """
        if value is None or value == "":
            return None
        
        try:
            # Limpiar el valor si es string
            if isinstance(value, str):
                # Remover comas, espacios, símbolos de moneda
                cleaned = re.sub(r'[,$\s]', '', value)
                # Manejar paréntesis como números negativos
                if cleaned.startswith('(') and cleaned.endswith(')'):
                    cleaned = '-' + cleaned[1:-1]
                value = cleaned
            
            return Decimal(str(value))
            
        except (InvalidOperation, ValueError, TypeError):
            return None
    
    async def _merge_extractions(
        self, 
        primary: FinancialMetrics, 
        secondary: FinancialMetrics,
        context: ExtractionContext
    ) -> FinancialMetrics:
        """
        Combina resultados de múltiples modelos para mayor precisión
        """
        # Lógica de combinación: priorizar el valor con mayor confianza
        # o hacer promedio si las confianzas son similares
        
        merged_data = {}
        
        # Campos numéricos a combinar
        numeric_fields = [
            'revenue', 'net_income', 'ebitda', 'total_assets',
            'shareholders_equity', 'operating_cash_flow', 'gross_profit'
        ]
        
        for field in numeric_fields:
            primary_val = getattr(primary, field)
            secondary_val = getattr(secondary, field)
            
            if primary_val is not None and secondary_val is not None:
                # Si ambos modelos encontraron el valor, usar el promedio
                merged_data[field] = (primary_val + secondary_val) / 2
            elif primary_val is not None:
                merged_data[field] = primary_val
            elif secondary_val is not None:
                merged_data[field] = secondary_val
            else:
                merged_data[field] = None
        
        # La confianza es el promedio de ambos modelos
        confidence = (primary.extraction_confidence + secondary.extraction_confidence) / 2
        
        # Crear nuevo objeto con valores combinados
        return FinancialMetrics(
            **merged_data,
            extraction_confidence=confidence,
            extraction_method="multi_model_consensus",
            currency=primary.currency,
            reporting_period=primary.reporting_period
        )
    
    async def _post_process_metrics(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> FinancialMetrics:
        """
        Post-procesa y valida las métricas extraídas
        """
        # Validaciones básicas de consistencia
        validation_issues = []
        
        # Validar que assets = liabilities + equity (aproximadamente)
        if (metrics.total_assets and metrics.total_liabilities and 
            metrics.shareholders_equity):
            expected_assets = metrics.total_liabilities + metrics.shareholders_equity
            asset_diff = abs(metrics.total_assets - expected_assets)
            if asset_diff > (metrics.total_assets * Decimal('0.05')):  # 5% tolerance
                validation_issues.append("Balance sheet equation doesn't balance")
        
        # Reducir confianza si hay problemas de validación
        adjusted_confidence = metrics.extraction_confidence
        if validation_issues:
            adjusted_confidence *= 0.8  # Reducir confianza en 20%
        
        # Crear métricas ajustadas
        return FinancialMetrics(
            # Copiar todos los campos existentes
            revenue=metrics.revenue,
            net_income=metrics.net_income,
            ebitda=metrics.ebitda,
            total_assets=metrics.total_assets,
            shareholders_equity=metrics.shareholders_equity,
            operating_cash_flow=metrics.operating_cash_flow,
            # ... (otros campos)
            
            # Ajustar confianza
            extraction_confidence=adjusted_confidence,
            extraction_method=metrics.extraction_method + "_validated",
            currency=metrics.currency,
            reporting_period=metrics.reporting_period
        )
    
    async def classify_document_type(
        self, 
        file_path: str, 
        config: AIExtractionConfiguration
    ) -> str:
        """
        Clasifica el tipo de documento usando IA
        """
        try:
            # Extraer las primeras páginas para clasificación
            text_sample = await self._extract_text_sample(file_path, pages=2)
            
            classification_prompt = f"""
            Clasifica este documento financiero según su contenido:

            TEXTO DEL DOCUMENTO:
            {text_sample[:2000]}

            Clasifica como UNO de estos tipos:
            - quarterly_report: Reporte trimestral (Q1, Q2, Q3, Q4)
            - annual_report: Reporte anual (10-K, Annual Report)
            - interim_report: Reporte intermedio
            - press_release: Comunicado de prensa de resultados
            - presentation: Presentación para inversionistas
            - proxy_statement: Declaración proxy
            - unknown: No se puede determinar

            Responde SOLO con el tipo de documento, sin explicación adicional.
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": classification_prompt}],
                temperature=0.1,
                max_tokens=50
            )
            
            return response.choices[0].message.content.strip().lower()
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error clasificando documento, usando 'unknown'",
                    error=e
                )
            return 'unknown'
    
    async def _extract_text_sample(self, file_path: str, pages: int = 2) -> str:
        """
        Extrae una muestra de texto para clasificación rápida
        """
        try:
            with fitz.open(file_path) as pdf_doc:
                text = ""
                for page_num in range(min(pages, pdf_doc.page_count)):
                    page = pdf_doc[page_num]
                    text += page.get_text()
                return text
        except:
            return ""
    
    # Métodos de caché
    async def _get_cached_extraction(
        self, 
        file_path: str, 
        context: ExtractionContext
    ) -> Optional[FinancialMetrics]:
        """
        Obtiene extracción desde caché si existe
        """
        if not self.cache:
            return None
        
        cache_key = f"extraction:{hashlib.md5(file_path.encode()).hexdigest()}:{context.fiscal_year}"
        cached_data = await self.cache.get(cache_key)
        
        if cached_data:
            # Reconstruir FinancialMetrics desde datos cacheados
            return FinancialMetrics(**cached_data)
        
        return None
    
    async def _cache_extraction(
        self, 
        file_path: str, 
        context: ExtractionContext, 
        metrics: FinancialMetrics,
        ttl_hours: int
    ) -> None:
        """
        Guarda extracción en caché
        """
        if not self.cache:
            return
        
        cache_key = f"extraction:{hashlib.md5(file_path.encode()).hexdigest()}:{context.fiscal_year}"
        cache_data = metrics.to_dict()  # Convertir a diccionario serializable
        
        await self.cache.set(
            cache_key, 
            cache_data, 
            expiration_seconds=ttl_hours * 3600
        )
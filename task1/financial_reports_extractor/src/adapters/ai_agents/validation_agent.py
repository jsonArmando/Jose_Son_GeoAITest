"""
AI Validation Agent
Intelligent validation system for financial data using multiple validation strategies
"""

import asyncio
import statistics
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any, Optional, Tuple
import openai
import httpx

from ...domain.ports import ValidationPort, LoggingPort, CachePort
from ...domain.value_objects import (
    FinancialMetrics, 
    ValidationResult, 
    ExtractionContext
)
from ...domain.entities import FinancialDocument


class IntelligentValidationAgent(ValidationPort):
    """
    Agente de validación inteligente que combina:
    - Validación basada en reglas
    - Validación con IA
    - Validación cruzada con fuentes externas
    - Análisis de consistencia histórica
    """
    
    def __init__(
        self,
        openai_api_key: str,
        external_apis: Optional[Dict[str, str]] = None,
        cache: Optional[CachePort] = None,
        logger: Optional[LoggingPort] = None
    ):
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
        self.external_apis = external_apis or {}
        self.cache = cache
        self.logger = logger
        
        # Thresholds para validación
        self.validation_thresholds = {
            'min_confidence_score': 0.7,
            'max_variance_percentage': 25.0,  # 25% variance allowed
            'balance_sheet_tolerance': 0.02,  # 2% tolerance for balance equation
            'reasonable_bounds': {
                'revenue_growth_yearly': (-50, 200),  # -50% to +200%
                'profit_margin': (-100, 100),  # -100% to +100%
                'debt_to_equity': (0, 10),  # 0 to 10x
                'current_ratio': (0, 20)  # 0 to 20x
            }
        }
        
        # Validation rules engine
        self.validation_rules = [
            self._validate_balance_sheet_equation,
            self._validate_profit_margins,
            self._validate_financial_ratios,
            self._validate_reasonable_bounds,
            self._validate_data_completeness,
            self._validate_internal_consistency
        ]
    
    async def validate_financial_metrics(
        self,
        metrics: FinancialMetrics,
        context: ExtractionContext
    ) -> ValidationResult:
        """
        Valida métricas financieras usando múltiples estrategias
        """
        try:
            validation_results = []
            
            # 1. Validación basada en reglas
            rule_validation = await self._validate_with_rules(metrics, context)
            validation_results.append(('rules', rule_validation))
            
            # 2. Validación con IA
            ai_validation = await self._validate_with_ai(metrics, context)
            validation_results.append(('ai', ai_validation))
            
            # 3. Validación cruzada (si hay APIs externas)
            if self.external_apis:
                cross_validation = await self._cross_validate_with_external_sources(
                    metrics, context.company_name, context.reporting_period
                )
                validation_results.append(('cross', cross_validation))
            
            # 4. Combinar resultados de validación
            final_result = await self._combine_validation_results(
                validation_results, metrics, context
            )
            
            if self.logger:
                await self.logger.log_info(
                    "Validación completada",
                    context={
                        'company': context.company_name,
                        'period': context.reporting_period,
                        'confidence_score': final_result.confidence_score,
                        'is_valid': final_result.is_valid,
                        'error_count': len(final_result.errors)
                    }
                )
            
            return final_result
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en validación de métricas financieras",
                    error=e,
                    context={'company': context.company_name}
                )
            
            # Retornar resultado con baja confianza en caso de error
            return ValidationResult(
                is_valid=False,
                confidence_score=0.1,
                errors=[f"Error en validación: {str(e)}"],
                validation_method="error_fallback"
            )
    
    async def _validate_with_rules(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> ValidationResult:
        """
        Validación usando reglas de negocio predefinidas
        """
        field_validations = {}
        warnings = []
        errors = []
        validation_messages = []
        
        try:
            # Ejecutar todas las reglas de validación
            for rule in self.validation_rules:
                rule_result = await rule(metrics, context)
                
                # Procesar resultado de la regla
                if rule_result['status'] == 'error':
                    errors.extend(rule_result['messages'])
                elif rule_result['status'] == 'warning':
                    warnings.extend(rule_result['messages'])
                else:
                    validation_messages.extend(rule_result['messages'])
                
                # Registrar validaciones de campos específicos
                field_validations.update(rule_result.get('field_validations', {}))
            
            # Calcular score de confianza basado en errores y warnings
            error_penalty = len(errors) * 0.2
            warning_penalty = len(warnings) * 0.1
            confidence_score = max(0.0, 1.0 - error_penalty - warning_penalty)
            
            return ValidationResult(
                is_valid=len(errors) == 0,
                confidence_score=confidence_score,
                field_validations=field_validations,
                validation_messages=validation_messages,
                warnings=warnings,
                errors=errors,
                validation_method="rule_based",
                accuracy_score=confidence_score,
                consistency_score=1.0 - (len(warnings) * 0.1),
                completeness_score=metrics.get_completeness_score()
            )
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                confidence_score=0.0,
                errors=[f"Error en validación por reglas: {str(e)}"],
                validation_method="rule_based_error"
            )
    
    async def _validate_balance_sheet_equation(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida la ecuación fundamental: Assets = Liabilities + Equity
        """
        if not all([metrics.total_assets, metrics.total_liabilities, metrics.shareholders_equity]):
            return {
                'status': 'warning',
                'messages': ['Balance sheet components incomplete'],
                'field_validations': {}
            }
        
        calculated_assets = metrics.total_liabilities + metrics.shareholders_equity
        difference = abs(metrics.total_assets - calculated_assets)
        tolerance = metrics.total_assets * Decimal(str(self.validation_thresholds['balance_sheet_tolerance']))
        
        if difference > tolerance:
            return {
                'status': 'error',
                'messages': [f'Balance sheet equation failed: Assets={metrics.total_assets}, L+E={calculated_assets}'],
                'field_validations': {
                    'total_assets': False,
                    'total_liabilities': False,
                    'shareholders_equity': False
                }
            }
        
        return {
            'status': 'success',
            'messages': ['Balance sheet equation validated'],
            'field_validations': {
                'total_assets': True,
                'total_liabilities': True,
                'shareholders_equity': True
            }
        }
    
    async def _validate_profit_margins(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida márgenes de ganancia y relaciones lógicas
        """
        messages = []
        field_validations = {}
        status = 'success'
        
        # Validar que gross profit <= revenue
        if metrics.revenue and metrics.gross_profit:
            if metrics.gross_profit > metrics.revenue:
                status = 'error'
                messages.append('Gross profit cannot exceed revenue')
                field_validations['gross_profit'] = False
            else:
                field_validations['gross_profit'] = True
        
        # Validar que operating income <= gross profit
        if metrics.gross_profit and metrics.operating_income:
            if metrics.operating_income > metrics.gross_profit:
                status = 'warning'
                messages.append('Operating income exceeds gross profit - verify operating expenses')
                field_validations['operating_income'] = False
            else:
                field_validations['operating_income'] = True
        
        # Validar margenes razonables
        if metrics.revenue and metrics.net_income:
            margin = (metrics.net_income / metrics.revenue) * 100
            if margin < -100 or margin > 100:
                status = 'warning'
                messages.append(f'Unusual profit margin: {margin:.1f}%')
        
        return {
            'status': status,
            'messages': messages,
            'field_validations': field_validations
        }
    
    async def _validate_financial_ratios(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida ratios financieros están en rangos razonables
        """
        messages = []
        field_validations = {}
        status = 'success'
        
        bounds = self.validation_thresholds['reasonable_bounds']
        
        # Validar debt-to-equity ratio
        if metrics.debt_to_equity_ratio:
            min_de, max_de = bounds['debt_to_equity']
            if not (min_de <= float(metrics.debt_to_equity_ratio) <= max_de):
                status = 'warning'
                messages.append(f'Unusual debt-to-equity ratio: {metrics.debt_to_equity_ratio}')
                field_validations['debt_to_equity_ratio'] = False
            else:
                field_validations['debt_to_equity_ratio'] = True
        
        # Validar current ratio
        if metrics.current_ratio:
            min_cr, max_cr = bounds['current_ratio']
            if not (min_cr <= float(metrics.current_ratio) <= max_cr):
                status = 'warning'
                messages.append(f'Unusual current ratio: {metrics.current_ratio}')
                field_validations['current_ratio'] = False
            else:
                field_validations['current_ratio'] = True
        
        return {
            'status': status,
            'messages': messages,
            'field_validations': field_validations
        }
    
    async def _validate_reasonable_bounds(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida que los valores estén en rangos razonables para el tipo de empresa
        """
        messages = []
        status = 'success'
        
        # Validar que los valores no sean negativos donde no deberían serlo
        non_negative_fields = ['revenue', 'total_assets', 'cash_and_equivalents']
        
        for field in non_negative_fields:
            value = getattr(metrics, field)
            if value is not None and value < 0:
                status = 'error'
                messages.append(f'{field} should not be negative: {value}')
        
        # Validar valores extremadamente grandes (posibles errores de unidades)
        if metrics.revenue and metrics.revenue > Decimal('1000000000000'):  # > 1 trillion
            status = 'warning'
            messages.append(f'Revenue seems unusually large: {metrics.revenue} - check units')
        
        return {
            'status': status,
            'messages': messages,
            'field_validations': {}
        }
    
    async def _validate_data_completeness(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida completitud de los datos
        """
        completeness_score = metrics.get_completeness_score()
        
        if completeness_score < 0.3:
            return {
                'status': 'error',
                'messages': [f'Data very incomplete: {completeness_score:.1%} fields populated'],
                'field_validations': {}
            }
        elif completeness_score < 0.6:
            return {
                'status': 'warning', 
                'messages': [f'Data moderately incomplete: {completeness_score:.1%} fields populated'],
                'field_validations': {}
            }
        
        return {
            'status': 'success',
            'messages': [f'Data completeness acceptable: {completeness_score:.1%}'],
            'field_validations': {}
        }
    
    async def _validate_internal_consistency(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> Dict[str, Any]:
        """
        Valida consistencia interna entre diferentes métricas
        """
        messages = []
        status = 'success'
        
        # EBITDA debería ser >= EBIT
        if metrics.ebitda and metrics.ebit:
            if metrics.ebit > metrics.ebitda:
                status = 'error'
                messages.append('EBIT cannot exceed EBITDA')
        
        # Operating income debería ser próximo a EBIT
        if metrics.operating_income and metrics.ebit:
            diff_pct = abs(metrics.operating_income - metrics.ebit) / metrics.ebit * 100
            if diff_pct > 20:  # Más de 20% de diferencia
                status = 'warning'
                messages.append(f'Large difference between Operating Income and EBIT: {diff_pct:.1f}%')
        
        # Free cash flow = Operating CF - CapEx (approximation)
        if metrics.free_cash_flow and metrics.operating_cash_flow:
            if metrics.free_cash_flow > metrics.operating_cash_flow:
                status = 'warning'
                messages.append('Free cash flow exceeds operating cash flow - verify calculation')
        
        return {
            'status': status,
            'messages': messages,
            'field_validations': {}
        }
    
    async def _validate_with_ai(
        self, 
        metrics: FinancialMetrics, 
        context: ExtractionContext
    ) -> ValidationResult:
        """
        Validación usando IA para detectar patrones anómalos
        """
        try:
            validation_prompt = f"""
            Eres un auditor financiero experto. Analiza estas métricas financieras de {context.company_name} para {context.reporting_period} y detecta anomalías:

            MÉTRICAS:
            - Revenue: {metrics.revenue}
            - Net Income: {metrics.net_income}
            - EBITDA: {metrics.ebitda}
            - Total Assets: {metrics.total_assets}
            - Shareholders Equity: {metrics.shareholders_equity}
            - Operating Cash Flow: {metrics.operating_cash_flow}
            - Debt-to-Equity: {metrics.debt_to_equity_ratio}
            - Current Ratio: {metrics.current_ratio}

            CONTEXTO:
            - Company: {context.company_name}
            - Period: {context.reporting_period}
            - Currency: {context.expected_currency}

            Analiza:
            1. ¿Hay relaciones financieras que no tienen sentido?
            2. ¿Los valores están en rangos razonables para una empresa pública?
            3. ¿Hay signos de posibles errores de extracción?
            4. ¿La combinación de métricas es consistente?

            Responde en JSON:
            {{
                "is_valid": true/false,
                "confidence_score": 0.0-1.0,
                "anomalies_detected": ["lista de anomalías"],
                "recommendations": ["lista de recomendaciones"],
                "risk_level": "low/medium/high",
                "explanation": "explicación breve"
            }}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": validation_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000
            )
            
            ai_result = json.loads(response.choices[0].message.content)
            
            return ValidationResult(
                is_valid=ai_result.get('is_valid', True),
                confidence_score=float(ai_result.get('confidence_score', 0.5)),
                validation_messages=ai_result.get('recommendations', []),
                warnings=ai_result.get('anomalies_detected', []),
                validation_method="ai_gpt4",
                accuracy_score=float(ai_result.get('confidence_score', 0.5))
            )
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error en validación con IA",
                    error=e
                )
            
            return ValidationResult(
                is_valid=True,  # Default to valid if AI validation fails
                confidence_score=0.5,
                warnings=["AI validation failed"],
                validation_method="ai_fallback"
            )
    
    async def cross_validate_with_external_sources(
        self,
        metrics: FinancialMetrics,
        company_name: str,
        period: str
    ) -> ValidationResult:
        """
        Validación cruzada con fuentes externas (APIs financieras)
        """
        try:
            # Esta es una implementación ejemplo - en producción usarías APIs reales
            # como Alpha Vantage, Financial Modeling Prep, etc.
            
            external_data = await self._fetch_external_financial_data(
                company_name, period
            )
            
            if not external_data:
                return ValidationResult(
                    is_valid=True,
                    confidence_score=0.5,
                    warnings=["No external data available for cross-validation"],
                    validation_method="cross_validation_no_data"
                )
            
            # Comparar métricas clave
            variance_results = self._compare_with_external_data(metrics, external_data)
            
            # Determinar si las varianzas están en rangos aceptables
            max_variance = self.validation_thresholds['max_variance_percentage']
            high_variance_fields = [
                field for field, variance in variance_results.items() 
                if variance > max_variance
            ]
            
            is_valid = len(high_variance_fields) == 0
            confidence_score = max(0.1, 1.0 - (len(high_variance_fields) * 0.2))
            
            warnings = [
                f"High variance in {field}: {variance:.1f}%" 
                for field, variance in variance_results.items() 
                if variance > max_variance
            ]
            
            return ValidationResult(
                is_valid=is_valid,
                confidence_score=confidence_score,
                warnings=warnings,
                validation_method="cross_validation_external",
                consistency_score=confidence_score
            )
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error en validación cruzada",
                    error=e
                )
            
            return ValidationResult(
                is_valid=True,
                confidence_score=0.5,
                warnings=["Cross-validation failed"],
                validation_method="cross_validation_error"
            )
    
    async def _fetch_external_financial_data(
        self, 
        company_name: str, 
        period: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene datos financieros de APIs externas
        """
        # Ejemplo de implementación - reemplazar con APIs reales
        if 'alpha_vantage' in self.external_apis:
            return await self._fetch_from_alpha_vantage(company_name, period)
        
        if 'financial_modeling_prep' in self.external_apis:
            return await self._fetch_from_fmp(company_name, period)
        
        return None
    
    async def _fetch_from_alpha_vantage(
        self, 
        company_name: str, 
        period: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch data from Alpha Vantage API (ejemplo)
        """
        try:
            api_key = self.external_apis.get('alpha_vantage')
            # Implementación de ejemplo - necesitarías el ticker symbol real
            url = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={company_name}&apikey={api_key}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30)
                data = response.json()
                
                # Procesar y normalizar datos
                return self._normalize_alpha_vantage_data(data)
                
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error fetching from Alpha Vantage",
                    error=e
                )
            return None
    
    def _compare_with_external_data(
        self, 
        metrics: FinancialMetrics, 
        external_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compara métricas extraídas con datos externos
        """
        variance_results = {}
        
        # Mapping de campos internos a externos
        field_mapping = {
            'revenue': 'totalRevenue',
            'net_income': 'netIncome',
            'total_assets': 'totalAssets',
            'shareholders_equity': 'totalShareholderEquity'
        }
        
        for internal_field, external_field in field_mapping.items():
            internal_value = getattr(metrics, internal_field)
            external_value = external_data.get(external_field)
            
            if internal_value and external_value:
                # Calcular varianza porcentual
                variance_pct = abs(
                    (float(internal_value) - float(external_value)) / float(external_value) * 100
                )
                variance_results[internal_field] = variance_pct
        
        return variance_results
    
    async def _combine_validation_results(
        self,
        validation_results: List[Tuple[str, ValidationResult]],
        metrics: FinancialMetrics,
        context: ExtractionContext
    ) -> ValidationResult:
        """
        Combina múltiples resultados de validación en uno final
        """
        all_errors = []
        all_warnings = []
        all_messages = []
        confidence_scores = []
        accuracy_scores = []
        consistency_scores = []
        completeness_scores = []
        
        # Recopilar todos los resultados
        for validation_type, result in validation_results:
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
            all_messages.extend(result.validation_messages)
            confidence_scores.append(result.confidence_score)
            
            if result.accuracy_score:
                accuracy_scores.append(result.accuracy_score)
            if result.consistency_score:
                consistency_scores.append(result.consistency_score)
            if result.completeness_score:
                completeness_scores.append(result.completeness_score)
        
        # Calcular scores combinados
        avg_confidence = statistics.mean(confidence_scores) if confidence_scores else 0.5
        avg_accuracy = statistics.mean(accuracy_scores) if accuracy_scores else None
        avg_consistency = statistics.mean(consistency_scores) if consistency_scores else None
        avg_completeness = statistics.mean(completeness_scores) if completeness_scores else None
        
        # Determinar validez final
        is_valid = len(all_errors) == 0 and avg_confidence >= self.validation_thresholds['min_confidence_score']
        
        return ValidationResult(
            is_valid=is_valid,
            confidence_score=avg_confidence,
            validation_messages=all_messages,
            warnings=list(set(all_warnings)),  # Eliminar duplicados
            errors=list(set(all_errors)),
            validation_method="combined_multi_strategy",
            accuracy_score=avg_accuracy,
            consistency_score=avg_consistency,
            completeness_score=avg_completeness
        )
    
    async def validate_document_consistency(
        self,
        document: FinancialDocument,
        metrics: FinancialMetrics
    ) -> ValidationResult:
        """
        Valida consistencia entre documento y métricas extraídas
        """
        try:
            consistency_checks = []
            
            # Verificar que el período del documento coincida con las métricas
            if metrics.reporting_period and document.get_period_identifier():
                if metrics.reporting_period != document.get_period_identifier():
                    consistency_checks.append(
                        f"Period mismatch: document={document.get_period_identifier()}, "
                        f"metrics={metrics.reporting_period}"
                    )
            
            # Verificar confianza de extracción vs validación del documento
            if document.validation_score > 0:
                score_diff = abs(document.validation_score - metrics.extraction_confidence)
                if score_diff > 0.3:  # 30% difference
                    consistency_checks.append(
                        f"Large confidence discrepancy: doc={document.validation_score:.2f}, "
                        f"extraction={metrics.extraction_confidence:.2f}"
                    )
            
            # Calcular score de consistencia
            consistency_score = max(0.0, 1.0 - (len(consistency_checks) * 0.3))
            
            return ValidationResult(
                is_valid=len(consistency_checks) == 0,
                confidence_score=consistency_score,
                validation_messages=["Document-metrics consistency check completed"],
                warnings=consistency_checks,
                validation_method="document_consistency",
                consistency_score=consistency_score
            )
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en validación de consistencia documento-métricas",
                    error=e
                )
            
            return ValidationResult(
                is_valid=False,
                confidence_score=0.1,
                errors=[f"Consistency validation error: {str(e)}"],
                validation_method="document_consistency_error"
            )
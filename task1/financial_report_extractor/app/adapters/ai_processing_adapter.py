# app/adapters/ai_processing_adapter.py - VERSIÓN MEJORADA CON DIAGNÓSTICO
import google.generativeai as genai
import PyPDF2 
import io
import json
from typing import Optional, Tuple, Dict, Any
import traceback
import time
import logging

from config import settings
from core import ai_prompts, schemas

# Configurar logging específico para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        genai.configure(api_key=settings.GEMINI_API_KEY)
        text_generation_model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("Gemini SDK configurado con gemini-2.0-flash.")
    else:
        logger.error("GEMINI_API_KEY no está configurada. El adaptador AI no funcionará.")
        text_generation_model = None
except Exception as e:
    logger.error(f"Error al configurar Gemini SDK: {e}")
    text_generation_model = None

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Optional[str]:
    """Extrae texto de bytes PDF usando PyPDF2"""
    try:
        pdf_file_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        if pdf_file_reader.is_encrypted:
            try:
                pdf_file_reader.decrypt('')
            except Exception as decrypt_err:
                logger.error(f"PDF está encriptado y no se pudo desencriptar: {decrypt_err}")
                return None

        text_parts = []
        for page_num in range(len(pdf_file_reader.pages)):
            page = pdf_file_reader.pages[page_num]
            page_text = page.extract_text()
            if page_text: 
                text_parts.append(page_text)
        
        if not text_parts:
            logger.warning("PyPDF2 no pudo extraer texto del PDF")
            return None 
        
        full_text = "\n".join(text_parts)
        logger.info(f"Texto extraído exitosamente: {len(full_text)} caracteres, {len(text_parts)} páginas")
        return full_text
        
    except PyPDF2.errors.PdfReadError as e:
        logger.error(f"Error de PyPDF2 al leer el PDF: {e}")
        return None
    except Exception as e: 
        logger.error(f"Error genérico al extraer texto del PDF: {e}")
        return None

def _call_gemini_api_with_retry(prompt: str, expect_json: bool = False, max_retries: int = 3) -> Optional[str]:
    """Llama a la API de Gemini con reintentos y diagnóstico mejorado"""
    
    if not text_generation_model:
        logger.error("Modelo Gemini no inicializado - verificar API Key")
        return None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Intento {attempt + 1}/{max_retries} - Enviando prompt a Gemini (longitud: {len(prompt)} chars)")
            
            # Configuración de generación
            generation_config = genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=8192,  # Límite explícito para evitar respuestas truncadas
            )
            
            # Llamada a la API con timeout
            start_time = time.time()
            response = text_generation_model.generate_content(
                prompt,
                generation_config=generation_config,
                request_options={'timeout': 400}
            )
            end_time = time.time()
            
            logger.info(f"Respuesta recibida en {end_time - start_time:.2f} segundos")
            
            # Diagnóstico detallado de la respuesta
            logger.debug("=== DIAGNÓSTICO DE RESPUESTA GEMINI ===")
            logger.debug(f"Tipo de respuesta: {type(response)}")
            logger.debug(f"Prompt feedback: {response.prompt_feedback}")
            
            # Verificar si hay candidatos
            if not response.candidates or len(response.candidates) == 0:
                logger.error("❌ No hay candidatos en la respuesta")
                if response.prompt_feedback:
                    if hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                        block_reason = response.prompt_feedback.block_reason.name
                        logger.error(f"Prompt bloqueado por: {block_reason}")
                        
                        # Si es un bloqueo de seguridad, no reintentamos
                        if 'SAFETY' in block_reason:
                            return f'{{"error": "Safety block", "reason": "{block_reason}"}}' if expect_json else None
                
                # Reintentar si no es un bloqueo permanente
                if attempt < max_retries - 1:
                    logger.info("Reintentando en 2 segundos...")
                    time.sleep(2)
                    continue
                return None
            
            # Examinar el primer candidato
            candidate = response.candidates[0]
            logger.debug(f"Finish reason: {candidate.finish_reason}")
            logger.debug(f"Safety ratings: {candidate.safety_ratings}")
            
            # Verificar razón de finalización
            if candidate.finish_reason.name not in ["STOP", "MAX_TOKENS"]:
                block_reason = candidate.finish_reason.name
                logger.warning(f"Generación no completó normalmente: {block_reason}")
                
                # Para algunos errores, podemos reintentar
                if block_reason in ["RECITATION", "OTHER"] and attempt < max_retries - 1:
                    logger.info("Reintentando por razón de finalización...")
                    time.sleep(2)
                    continue
                
                return f'{{"error": "Generation issue", "reason": "{block_reason}"}}' if expect_json else None
            
            # Verificar contenido
            if not candidate.content or not candidate.content.parts:
                logger.error("❌ Candidato sin contenido o partes")
                if attempt < max_retries - 1:
                    logger.info("Reintentando por falta de contenido...")
                    time.sleep(2)
                    continue
                return None
            
            # Extraer texto
            content_text = candidate.content.parts[0].text.strip()
            logger.info(f"✅ Contenido extraído exitosamente: {len(content_text)} caracteres")
            logger.debug(f"Primeros 500 caracteres: {content_text[:500]}")
            
            return content_text
            
        except Exception as e:
            logger.error(f"❌ Excepción en intento {attempt + 1}: {e}")
            if hasattr(e, 'grpc_status_code'):
                logger.error(f"gRPC status code: {e.grpc_status_code}")
            
            # Para ciertos errores, no reintentamos
            if "quota" in str(e).lower() or "api key" in str(e).lower():
                logger.error("Error de quota o API key - no reintentando")
                return None
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Backoff exponencial
                logger.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                time.sleep(wait_time)
            else:
                logger.error(f"Todos los intentos fallaron. Último error: {traceback.format_exc()}")
    
    return None

def process_pdf_with_ai(pdf_bytes: bytes, report_name: str) -> Tuple[Optional[schemas.LLMFullExtractionResult], Optional[Dict[str, Any]], Optional[str]]:
    """Procesa PDF con AI incluyendo diagnóstico mejorado"""
    
    logger.info(f"=== INICIANDO PROCESAMIENTO AI PARA: {report_name} ===")
    
    # 1. Extraer texto del PDF
    logger.info("Paso 1: Extrayendo texto del PDF...")
    pdf_text_content = _extract_text_from_pdf_bytes(pdf_bytes)
    if not pdf_text_content:
        error_msg = "Fallo crítico al extraer texto del PDF (PyPDF2 no pudo extraer contenido legible)."
        logger.error(error_msg)
        return None, None, error_msg
    
    # 2. Truncar texto si es necesario
    MAX_TEXT_LENGTH_FOR_PROMPT = 750000 
    if len(pdf_text_content) > MAX_TEXT_LENGTH_FOR_PROMPT:
        logger.warning(f"Texto del PDF ({len(pdf_text_content)} chars) truncado a {MAX_TEXT_LENGTH_FOR_PROMPT} chars")
        pdf_text_content_for_prompt = pdf_text_content[:MAX_TEXT_LENGTH_FOR_PROMPT]
    else:
        pdf_text_content_for_prompt = pdf_text_content
    
    # 3. Generar prompt
    logger.info("Paso 2: Generando prompt de extracción...")
    metric_extraction_prompt = ai_prompts.get_metric_extraction_prompt(pdf_text_content_for_prompt, report_name)
    logger.debug(f"Longitud del prompt: {len(metric_extraction_prompt)} caracteres")
    
    # 4. Llamar a Gemini API
    logger.info("Paso 3: Llamando a Gemini API...")
    raw_llm_metric_response_str = _call_gemini_api_with_retry(metric_extraction_prompt, expect_json=True)

    if not raw_llm_metric_response_str:
        error_msg = "Fallo en la API de Gemini durante la extracción de métricas (respuesta vacía o error de API irrecuperable)."
        logger.error(error_msg)
        return None, None, error_msg

    # 5. Procesar respuesta JSON
    logger.info("Paso 4: Procesando respuesta JSON...")
    logger.debug(f"Respuesta cruda (primeros 1000 chars): {raw_llm_metric_response_str[:1000]}")

    # Limpiar formato markdown si existe
    cleaned_json_str = raw_llm_metric_response_str
    if cleaned_json_str.startswith("```json"):
        cleaned_json_str = cleaned_json_str[7:]
        if cleaned_json_str.endswith("```"):
            cleaned_json_str = cleaned_json_str[:-3]
    cleaned_json_str = cleaned_json_str.strip()

    try:
        # Parsear JSON
        raw_llm_metric_data = json.loads(cleaned_json_str)
        logger.info("JSON parseado exitosamente")

        # Verificar si hay error en la respuesta
        if isinstance(raw_llm_metric_data, dict) and "error" in raw_llm_metric_data:
            error_detail = raw_llm_metric_data.get('reason', 'Error desconocido devuelto por LLM')
            logger.error(f"LLM devolvió error: {error_detail}")
            return None, raw_llm_metric_data, f"LLM error: {error_detail}"
        
        # Validar con Pydantic
        logger.info("Validando datos con Pydantic...")
        llm_result = schemas.LLMFullExtractionResult(**raw_llm_metric_data)
        logger.info("✅ Validación exitosa con Pydantic")
        
        return llm_result, raw_llm_metric_data, None 

    except json.JSONDecodeError as e:
        error_msg = f"Error al decodificar JSON: {e}"
        logger.error(f"{error_msg}\nRespuesta problemática:\n{cleaned_json_str}")
        return None, {"raw_response_on_json_error": cleaned_json_str}, f"JSONDecodeError: {str(e)}"
        
    except Exception as e: 
        error_msg = f"Error al procesar/validar respuesta del LLM: {e}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        raw_data_dict_on_error = {}
        try: 
            raw_data_dict_on_error = json.loads(cleaned_json_str)
        except: 
            raw_data_dict_on_error = {"raw_response_on_validation_error": cleaned_json_str}
        
        return None, raw_data_dict_on_error, error_msg

# Función original para compatibilidad
def _call_gemini_api(prompt: str, expect_json: bool = False) -> Optional[str]:
    """Wrapper para mantener compatibilidad con código existente"""
    return _call_gemini_api_with_retry(prompt, expect_json, max_retries=3)
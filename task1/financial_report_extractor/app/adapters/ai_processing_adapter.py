# app/adapters/ai_processing_adapter.py
import google.generativeai as genai
from app.config import settings
from app.core import ai_prompts, schemas
import json
from typing import Optional, Tuple, Dict, Any
import PyPDF2 # Para extraer texto de PDFs
import io

# --- Configuración del SDK de Gemini ---
try:
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Modelo para generación de texto y análisis.
        # 'gemini-pro' es bueno para tareas de texto.
        # 'gemini-1.5-flash' o 'gemini-1.5-pro' si se necesita mayor capacidad o multimodalidad (no usado aquí directamente para PDF)
        # Para esta tarea, gemini-1.5-flash es una buena opción por velocidad y costo-efectividad.
        text_generation_model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        print("ADVERTENCIA: GEMINI_API_KEY no está configurada. El adaptador AI no funcionará.")
        text_generation_model = None
except Exception as e:
    print(f"Error al configurar Gemini SDK: {e}")
    text_generation_model = None

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Optional[str]:
    """
    Extrae texto de un objeto de bytes de PDF usando PyPDF2.
    """
    try:
        pdf_file_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = []
        for page_num in range(len(pdf_file_reader.pages)):
            page = pdf_file_reader.pages[page_num]
            text.append(page.extract_text())
        return "\n".join(text)
    except Exception as e:
        print(f"Error al extraer texto del PDF con PyPDF2: {e}")
        return None

def _call_gemini_api(prompt: str) -> Optional[str]:
    """
    Función genérica para llamar a la API de Gemini con un prompt.
    """
    if not text_generation_model:
        print("Error: Modelo Gemini no inicializado.")
        return None
    try:
        # Para JSON mode, se puede especificar en generation_config
        # response = text_generation_model.generate_content(prompt, generation_config=genai.types.GenerationConfig(response_mime_type="application/json"))
        # Por ahora, parsearemos el JSON de la respuesta de texto.
        
        # Usando la nueva API para gemini-1.5-flash (o pro)
        chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": chat_history}
        
        # Nota: La API v1beta (usada en las instrucciones originales) es para gemini-pro.
        # Para gemini-1.5-flash, el SDK maneja la llamada directa.
        # Si se usara fetch directamente:
        # apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GEMINI_API_KEY}"
        # response = requests.post(apiUrl, json=payload)
        # result = response.json()
        # text_response = result.get('candidates')[0].get('content').get('parts')[0].get('text')
        
        response = text_generation_model.generate_content(prompt)

        if response.candidates and len(response.candidates) > 0:
            if response.candidates[0].content and response.candidates[0].content.parts:
                 # Asegurarse que no haya errores de "block reason"
                if response.candidates[0].finish_reason.name != "STOP":
                    block_reason = response.candidates[0].finish_reason.name
                    safety_ratings_info = response.candidates[0].safety_ratings
                    print(f"Advertencia: La generación de Gemini fue bloqueada o no completó. Razón: {block_reason}")
                    print(f"Safety Ratings: {safety_ratings_info}")
                    # Si hay prompt_feedback, también es útil
                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                        print(f"Prompt Feedback Block Reason: {response.prompt_feedback.block_reason_message}")
                    return f'{{"error": "Gemini generation blocked or incomplete", "reason": "{block_reason}"}}'
                
                return response.candidates[0].content.parts[0].text
            else: # A veces la respuesta puede estar vacía o mal formada si hay un problema
                print("Advertencia: Respuesta de Gemini no tiene 'content' o 'parts' esperados.")
                print(f"Respuesta completa de Gemini: {response}")
                return None
        else:
            print("Advertencia: Respuesta de Gemini no tiene candidatos válidos.")
            # Imprimir feedback del prompt si está disponible, puede indicar por qué falló (ej. API key inválida)
            if response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}")
            return None

    except Exception as e:
        print(f"Error al llamar a la API de Gemini: {e}")
        # Imprimir detalles de la excepción, podría ser un error de autenticación, cuota, etc.
        if hasattr(e, 'response') and e.response:
            print(f"Detalles del error de API: {e.response.text}")
        return None

def process_pdf_with_ai(pdf_bytes: bytes, report_name: str) -> Tuple[Optional[schemas.LLMFullExtractionResult], Optional[Dict[str, Any]], Optional[str]]:
    """
    Procesa un PDF usando un pipeline de dos pasos con LLMs:
    1. Extrae texto del PDF.
    2. (Opcional Primer LLM Call) Pide al LLM que estructure el texto del PDF (identificar periodo, tablas, etc.).
       Para simplificar, podríamos omitir este y pasar texto crudo al siguiente.
       Pero para robustez, este paso es bueno.
    3. Pide al LLM que extraiga las métricas específicas del texto (estructurado o crudo).

    Retorna:
        - Objeto LLMFullExtractionResult si tiene éxito.
        - Diccionario con la respuesta cruda del LLM de extracción de métricas.
        - Mensaje de error si algo falla.
    """
    # Paso 1: Extraer texto del PDF
    pdf_text_content = _extract_text_from_pdf_bytes(pdf_bytes)
    if not pdf_text_content:
        return None, None, "Fallo al extraer texto del PDF."
    
    # (Opcional) Podríamos truncar el texto si es demasiado largo para el LLM,
    # pero los modelos más nuevos como Gemini 1.5 tienen contextos muy grandes.
    # print(f"Texto extraído del PDF (primeros 1000 caracteres): {pdf_text_content[:1000]}")

    # Paso 2: (Opcional, pero recomendado) Usar LLM para estructurar el contenido del PDF
    # Por ahora, para mantenerlo más simple y directo según la reducción solicitada,
    # vamos a pasar el texto crudo directamente al prompt de extracción de métricas.
    # Si los resultados no son buenos, este paso de pre-procesamiento con LLM sería lo primero a añadir.
    # prompt_estructurador = ai_prompts.get_pdf_structure_extraction_prompt(pdf_text_content)
    # structured_content_json_str = _call_gemini_api(prompt_estructurador)
    # if not structured_content_json_str:
    #     return None, None, "Fallo en el LLM al estructurar el contenido del PDF."
    # print(f"Contenido estructurado por LLM (primeros 500 chars): {structured_content_json_str[:500]}")
    # structured_content_for_metric_extraction = structured_content_json_str
    
    # Usaremos el texto crudo directamente para la extracción de métricas por simplicidad inicial
    # Si el texto es muy largo, podríamos necesitar dividirlo o usar un modelo con ventana de contexto mayor.
    # Gemini 1.5 Flash tiene 1M de tokens, debería ser suficiente para la mayoría de los informes.
    MAX_TEXT_LENGTH_FOR_PROMPT = 750000 # Ajustar según el límite real del modelo y para evitar timeouts/costos excesivos
    if len(pdf_text_content) > MAX_TEXT_LENGTH_FOR_PROMPT:
        print(f"Advertencia: El texto del PDF ({len(pdf_text_content)} chars) es muy largo, truncando a {MAX_TEXT_LENGTH_FOR_PROMPT} chars para el prompt.")
        pdf_text_content_for_prompt = pdf_text_content[:MAX_TEXT_LENGTH_FOR_PROMPT]
    else:
        pdf_text_content_for_prompt = pdf_text_content

    # Paso 3: Usar LLM para extraer las métricas específicas
    metric_extraction_prompt = ai_prompts.get_metric_extraction_prompt(pdf_text_content_for_prompt, report_name)
    
    print(f"\n--- Enviando prompt de extracción de métricas a Gemini para: {report_name} ---")
    # print(f"Prompt (primeros 300 chars): {metric_extraction_prompt[:300]} ... (longitud total: {len(metric_extraction_prompt)})")

    raw_llm_metric_response_str = _call_gemini_api(metric_extraction_prompt)

    if not raw_llm_metric_response_str:
        return None, None, "Fallo en la API de Gemini durante la extracción de métricas (respuesta vacía)."

    # print(f"\nRespuesta cruda del LLM para extracción de métricas:\n{raw_llm_metric_response_str}\n---")

    try:
        # El LLM debería devolver un JSON string. Intentar parsearlo.
        # A veces los LLMs pueden añadir ```json ... ``` o texto explicativo. Intentar limpiarlo.
        if raw_llm_metric_response_str.strip().startswith("```json"):
            raw_llm_metric_response_str = raw_llm_metric_response_str.strip()[7:]
            if raw_llm_metric_response_str.strip().endswith("```"):
                 raw_llm_metric_response_str = raw_llm_metric_response_str.strip()[:-3]
        
        raw_llm_metric_data = json.loads(raw_llm_metric_response_str)

        # Validar con Pydantic si la estructura es la esperada
        # Esto ayuda a asegurar que el LLM está siguiendo el formato de prompt
        llm_result = schemas.LLMFullExtractionResult(**raw_llm_metric_data)
        return llm_result, raw_llm_metric_data, None # Éxito

    except json.JSONDecodeError as e:
        error_msg = f"Error al decodificar JSON de la respuesta del LLM para métricas: {e}. Respuesta recibida: {raw_llm_metric_response_str[:500]}..."
        print(error_msg)
        return None, {"raw_response_on_json_error": raw_llm_metric_response_str}, error_msg
    except Exception as e: # Captura errores de validación Pydantic u otros
        error_msg = f"Error al procesar/validar la respuesta del LLM para métricas: {e}. Data: {raw_llm_metric_response_str[:500]}..."
        print(error_msg)
        # Guardar la respuesta cruda para análisis si falla la validación Pydantic
        # Esto es útil si el LLM no sigue exactamente el schema de LLMFullExtractionResult
        # pero aun así devuelve un JSON.
        try:
            raw_data_on_validation_error = json.loads(raw_llm_metric_response_str)
        except:
            raw_data_on_validation_error = {"raw_response_on_validation_error": raw_llm_metric_response_str}
        return None, raw_data_on_validation_error, error_msg


# Ejemplo de uso (para pruebas locales)
if __name__ == "__main__":
    # Esto requeriría un PDF de ejemplo en bytes.
    # Supongamos que tenemos 'test_report.pdf' descargado por report_fetcher_adapter.py
    try:
        with open("test_report.pdf", "rb") as f:
            sample_pdf_bytes = f.read()
        
        print("Probando procesamiento AI del PDF de ejemplo (test_report.pdf)...")
        extracted_result, raw_output, error = process_pdf_with_ai(sample_pdf_bytes, "Test Report Q1 2023")

        if error:
            print(f"\nError en el procesamiento AI: {error}")
            if raw_output:
                 print(f"Salida cruda del LLM (en error): {json.dumps(raw_output, indent=2)}")
        elif extracted_result:
            print("\n--- Resultado de Extracción AI (Validado por Pydantic) ---")
            print(extracted_result.model_dump_json(indent=2))
            print("\n--- Salida Cruda del LLM (JSON) ---")
            print(json.dumps(raw_output, indent=2))
        else:
            print("\nNo se obtuvo resultado ni error específico del procesamiento AI.")

    except FileNotFoundError:
        print("Archivo 'test_report.pdf' no encontrado. Ejecuta report_fetcher_adapter.py primero para descargarlo o coloca un PDF de prueba.")
    except Exception as e:
        print(f"Ocurrió un error en la prueba: {e}")


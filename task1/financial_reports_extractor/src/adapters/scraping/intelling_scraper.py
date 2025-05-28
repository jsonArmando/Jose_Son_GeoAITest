"""
Intelligent Web Scraping Agent
AI-powered adaptive web scraper for financial documents
"""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse
import aiohttp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import openai

from ...domain.ports import WebScrapingPort, LoggingPort
from ...domain.value_objects import ScrapingConfiguration


class IntelligentWebScrapingAgent(WebScrapingPort):
    """
    Agente inteligente de web scraping que usa IA para adaptarse
    a diferentes estructuras de sitios web
    """
    
    def __init__(
        self,
        openai_api_key: str,
        selenium_hub_url: Optional[str] = None,
        logger: Optional[LoggingPort] = None
    ):
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
        self.selenium_hub_url = selenium_hub_url
        self.logger = logger
        self.session = None
        
        # Cache para patrones aprendidos
        self.learned_patterns = {}
        
        # Selectores comunes para diferentes tipos de sitios
        self.common_selectors = {
            'financial_links': [
                'a[href*="report"]',
                'a[href*="financial"]',
                'a[href*="annual"]',
                'a[href*="quarterly"]',
                'a[href*="interim"]',
                'a[href*="earnings"]',
                'a[href*="investor"]',
                'a[href*=".pdf"]',
                '.financial-report a',
                '.investor-relations a',
                '.annual-report a'
            ],
            'date_selectors': [
                '[class*="date"]',
                '[class*="year"]',
                '[class*="period"]',
                'time',
                '.publication-date',
                '.report-date'
            ]
        }
    
    async def discover_documents(
        self, 
        base_url: str, 
        config: ScrapingConfiguration
    ) -> List[Dict[str, Any]]:
        """
        Descubre documentos financieros usando estrategias adaptativas
        """
        try:
            # 1. Analizar estructura del sitio con IA
            site_analysis = await self._analyze_site_structure(base_url)
            
            # 2. Obtener o generar estrategia de scraping
            scraping_strategy = await self._get_scraping_strategy(base_url, site_analysis, config)
            
            # 3. Ejecutar scraping adaptativo
            documents = await self._execute_adaptive_scraping(base_url, scraping_strategy)
            
            # 4. Filtrar y enriquecer documentos
            filtered_documents = await self._filter_and_enrich_documents(documents, config)
            
            if self.logger:
                await self.logger.log_info(
                    f"Scraping completado: {len(filtered_documents)} documentos encontrados",
                    context={'base_url': base_url, 'total_found': len(documents)}
                )
            
            return filtered_documents
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en descubrimiento de documentos",
                    error=e,
                    context={'base_url': base_url}
                )
            raise
    
    async def _analyze_site_structure(self, base_url: str) -> Dict[str, Any]:
        """
        Analiza la estructura del sitio web usando IA
        """
        try:
            # Obtener HTML de la página principal
            html_content = await self._fetch_page_content(base_url)
            
            # Extraer información estructural
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Preparar contexto para análisis IA
            context = {
                'url': base_url,
                'title': soup.title.string if soup.title else '',
                'navigation_links': [
                    {'text': link.get_text(strip=True), 'href': link.get('href', '')}
                    for link in soup.find_all('a', href=True)[:20]
                ],
                'main_sections': [
                    section.get('class', [''])[0] if section.get('class') else section.name
                    for section in soup.find_all(['section', 'div', 'main'])[:10]
                ],
                'forms': len(soup.find_all('form')),
                'has_javascript': bool(soup.find_all('script')),
                'meta_description': ''
            }
            
            # Buscar meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                context['meta_description'] = meta_desc.get('content', '')
            
            # Analizar con IA
            analysis_prompt = f"""
            Analiza la estructura de este sitio web corporativo para extraer reportes financieros:
            
            URL: {context['url']}
            Título: {context['title']}
            Descripción: {context['meta_description']}
            
            Enlaces principales: {context['navigation_links'][:10]}
            
            Determina:
            1. ¿Dónde están ubicados típicamente los reportes financieros?
            2. ¿Qué patrones de URL usar para encontrar documentos?
            3. ¿Qué selectores CSS serían más efectivos?
            4. ¿Hay paginación o carga dinámica?
            5. ¿Qué estrategia de scraping recomiendas?
            
            Responde en formato JSON con esta estructura:
            {{
                "likely_reports_section": "descripción de dónde buscar",
                "url_patterns": ["patrón1", "patrón2"],
                "css_selectors": ["selector1", "selector2"],
                "navigation_strategy": "descripción de cómo navegar",
                "requires_javascript": true/false,
                "pagination_detected": true/false
            }}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": analysis_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            ai_analysis = response.choices[0].message.content
            return {**context, 'ai_analysis': ai_analysis}
            
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error en análisis IA del sitio, usando estrategia por defecto",
                    error=e
                )
            return {'ai_analysis': '{}', 'fallback': True}
    
    async def _get_scraping_strategy(
        self, 
        base_url: str, 
        site_analysis: Dict[str, Any],
        config: ScrapingConfiguration
    ) -> Dict[str, Any]:
        """
        Obtiene o genera estrategia de scraping basada en análisis
        """
        # Verificar si ya tenemos patrones aprendidos para este dominio
        domain = urlparse(base_url).netloc
        if domain in self.learned_patterns:
            return self.learned_patterns[domain]
        
        # Generar nueva estrategia basada en análisis IA
        try:
            import json
            ai_analysis = json.loads(site_analysis.get('ai_analysis', '{}'))
            
            strategy = {
                'selectors': ai_analysis.get('css_selectors', self.common_selectors['financial_links']),
                'url_patterns': ai_analysis.get('url_patterns', []),
                'requires_selenium': ai_analysis.get('requires_javascript', False),
                'has_pagination': ai_analysis.get('pagination_detected', False),
                'navigation_strategy': ai_analysis.get('navigation_strategy', 'direct_links'),
                'rate_limit_delay': config.delay_between_requests
            }
            
            # Guardar estrategia aprendida
            self.learned_patterns[domain] = strategy
            
            return strategy
            
        except Exception:
            # Estrategia por defecto
            return {
                'selectors': self.common_selectors['financial_links'],
                'url_patterns': ['report', 'financial', 'annual', 'quarterly'],
                'requires_selenium': True,
                'has_pagination': False,
                'navigation_strategy': 'direct_links',
                'rate_limit_delay': config.delay_between_requests
            }
    
    async def _execute_adaptive_scraping(
        self, 
        base_url: str, 
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta scraping adaptativo basado en la estrategia
        """
        documents = []
        
        if strategy.get('requires_selenium', True):
            documents = await self._scrape_with_selenium(base_url, strategy)
        else:
            documents = await self._scrape_with_requests(base_url, strategy)
        
        return documents
    
    async def _scrape_with_selenium(
        self, 
        base_url: str, 
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Scraping usando Selenium para sitios con JavaScript
        """
        driver = None
        try:
            # Configurar WebDriver
            driver = await self._create_webdriver()
            
            # Navegar a la página
            driver.get(base_url)
            
            # Esperar a que cargue
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            documents = []
            
            # Buscar enlaces usando múltiples selectores
            for selector in strategy['selectors']:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        try:
                            link_data = await self._extract_link_data(element, base_url)
                            if link_data and self._is_financial_document(link_data):
                                documents.append(link_data)
                        except Exception as e:
                            continue
                            
                except NoSuchElementException:
                    continue
            
            # Manejar paginación si existe
            if strategy.get('has_pagination', False):
                documents.extend(await self._handle_pagination(driver, strategy))
            
            return documents
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en scraping con Selenium",
                    error=e,
                    context={'base_url': base_url}
                )
            return []
        finally:
            if driver:
                driver.quit()
    
    async def _scrape_with_requests(
        self, 
        base_url: str, 
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Scraping usando requests para sitios estáticos
        """
        try:
            html_content = await self._fetch_page_content(base_url)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            documents = []
            
            # Buscar enlaces usando selectores
            for selector in strategy['selectors']:
                elements = soup.select(selector)
                
                for element in elements:
                    link_data = {
                        'url': urljoin(base_url, element.get('href', '')),
                        'title': element.get_text(strip=True),
                        'text': element.get_text(strip=True)
                    }
                    
                    if self._is_financial_document(link_data):
                        # Enriquecer con información adicional
                        enriched_data = await self._enrich_document_data(element, link_data)
                        documents.append(enriched_data)
            
            return documents
            
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error en scraping con requests",
                    error=e,
                    context={'base_url': base_url}
                )
            return []
    
    async def _create_webdriver(self) -> webdriver.Chrome:
        """
        Crea una instancia de WebDriver configurada
        """
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        if self.selenium_hub_url:
            # Usar Selenium Grid
            driver = webdriver.Remote(
                command_executor=self.selenium_hub_url,
                options=options
            )
        else:
            # Usar driver local
            driver = webdriver.Chrome(options=options)
        
        return driver
    
    async def _extract_link_data(self, element, base_url: str) -> Dict[str, Any]:
        """
        Extrae datos de un elemento de enlace
        """
        try:
            href = element.get_attribute('href')
            text = element.text.strip()
            
            # Buscar información de fecha cercana
            parent = element.find_element(By.XPATH, '..')
            date_info = await self._extract_date_from_context(parent)
            
            return {
                'url': href if href.startswith('http') else urljoin(base_url, href),
                'title': text,
                'text': text,
                'date_info': date_info,
                'source_element': element.tag_name
            }
        except Exception:
            return None
    
    async def _extract_date_from_context(self, context_element) -> Dict[str, Any]:
        """
        Extrae información de fecha del contexto del enlace
        """
        date_patterns = [
            r'\b(20\d{2})\b',  # Año
            r'\b(Q[1-4])\b',   # Trimestre
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b',  # Mes
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # Fecha MM/DD/YYYY
        ]
        
        text = context_element.text
        
        extracted_info = {}
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if pattern == date_patterns[0]:  # Año
                    extracted_info['year'] = int(matches[0])
                elif pattern == date_patterns[1]:  # Trimestre
                    extracted_info['quarter'] = matches[0]
                elif pattern == date_patterns[2]:  # Mes
                    extracted_info['month'] = matches[0]
                elif pattern == date_patterns[3]:  # Fecha completa
                    extracted_info['full_date'] = matches[0]
        
        return extracted_info
    
    def _is_financial_document(self, link_data: Dict[str, Any]) -> bool:
        """
        Determina si un enlace corresponde a un documento financiero
        """
        financial_keywords = [
            'financial', 'report', 'annual', 'quarterly', 'interim',
            'earnings', '10-k', '10-q', 'proxy', 'sec', 'investor',
            'statement', 'balance', 'income', 'cash flow', 'results'
        ]
        
        text_to_check = (
            link_data.get('title', '') + ' ' + 
            link_data.get('text', '') + ' ' + 
            link_data.get('url', '')
        ).lower()
        
        # Verificar palabras clave
        keyword_match = any(keyword in text_to_check for keyword in financial_keywords)
        
        # Verificar extensión de archivo
        file_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx']
        extension_match = any(ext in link_data.get('url', '').lower() for ext in file_extensions)
        
        return keyword_match or extension_match
    
    async def _filter_and_enrich_documents(
        self, 
        documents: List[Dict[str, Any]], 
        config: ScrapingConfiguration
    ) -> List[Dict[str, Any]]:
        """
        Filtra y enriquece documentos encontrados
        """
        enriched_documents = []
        
        for doc in documents:
            # Filtrar por patrones de URL
            if not config.should_process_url(doc['url']):
                continue
            
            # Enriquecer con metadatos adicionales
            enriched_doc = await self._enrich_document_metadata(doc)
            
            if enriched_doc:
                enriched_documents.append(enriched_doc)
        
        # Eliminar duplicados
        unique_documents = self._remove_duplicates(enriched_documents)
        
        return unique_documents
    
    async def _enrich_document_metadata(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Enriquece un documento con metadatos adicionales
        """
        try:
            # Clasificar tipo de documento usando IA
            document_type = await self._classify_document_type(doc)
            
            # Extraer año y trimestre
            year, quarter = self._extract_period_info(doc)
            
            # Generar ID único
            doc_id = hashlib.md5(doc['url'].encode()).hexdigest()
            
            return {
                'id': doc_id,
                'url': doc['url'],
                'title': doc.get('title', ''),
                'type': document_type,
                'year': year,
                'quarter': quarter,
                'filename': self._extract_filename(doc['url']),
                'discovered_at': datetime.utcnow().isoformat(),
                'source_text': doc.get('text', ''),
                'metadata': {
                    'date_info': doc.get('date_info', {}),
                    'source_element': doc.get('source_element', ''),
                    'confidence': 0.8  # Placeholder
                }
            }
        except Exception as e:
            if self.logger:
                await self.logger.log_warning(
                    "Error enriqueciendo metadatos de documento",
                    error=e,
                    context={'url': doc.get('url', 'unknown')}
                )
            return None
    
    async def _classify_document_type(self, doc: Dict[str, Any]) -> str:
        """
        Clasifica el tipo de documento usando IA
        """
        try:
            classification_prompt = f"""
            Clasifica este documento financiero según su título y URL:
            
            Título: {doc.get('title', '')}
            URL: {doc.get('url', '')}
            Texto: {doc.get('text', '')}
            
            Clasifica como uno de estos tipos:
            - quarterly_report: Reporte trimestral (Q1, Q2, Q3, Q4)
            - annual_report: Reporte anual
            - interim_report: Reporte intermedio
            - press_release: Comunicado de prensa
            - presentation: Presentación para inversionistas
            - unknown: No se puede determinar
            
            Responde solo con el tipo sin explicación.
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": classification_prompt}],
                temperature=0.1,
                max_tokens=50
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception:
            return 'unknown'
    
    def _extract_period_info(self, doc: Dict[str, Any]) -> tuple[int, Optional[int]]:
        """
        Extrae información de período (año y trimestre) del documento
        """
        text = (doc.get('title', '') + ' ' + doc.get('url', '')).lower()
        
        # Extraer año
        year_match = re.search(r'\b(20\d{2})\b', text)
        year = int(year_match.group(1)) if year_match else datetime.now().year
        
        # Extraer trimestre
        quarter_match = re.search(r'\bq([1-4])\b', text)
        quarter = int(quarter_match.group(1)) if quarter_match else None
        
        return year, quarter
    
    def _extract_filename(self, url: str) -> str:
        """
        Extrae el nombre del archivo de la URL
        """
        return url.split('/')[-1].split('?')[0]
    
    def _remove_duplicates(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Elimina documentos duplicados basándose en URL
        """
        seen_urls = set()
        unique_docs = []
        
        for doc in documents:
            url = doc['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_docs.append(doc)
        
        return unique_docs
    
    async def _fetch_page_content(self, url: str) -> str:
        """
        Obtiene el contenido de una página web
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            async with self.session.get(url, timeout=30) as response:
                return await response.text()
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error obteniendo contenido de página",
                    error=e,
                    context={'url': url}
                )
            raise
    
    async def download_document(
        self, 
        url: str, 
        destination_path: str
    ) -> Dict[str, Any]:
        """
        Descarga un documento desde una URL
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: {response.reason}")
                
                content = await response.read()
                
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                
                # Escribir archivo
                with open(destination_path, 'wb') as f:
                    f.write(content)
                
                # Calcular hash
                file_hash = hashlib.sha256(content).hexdigest()
                
                return {
                    'file_path': destination_path,
                    'file_size': len(content),
                    'file_hash': file_hash,
                    'content_type': response.headers.get('content-type', ''),
                    'downloaded_at': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            if self.logger:
                await self.logger.log_error(
                    "Error descargando documento",
                    error=e,
                    context={'url': url, 'destination': destination_path}
                )
            raise
    
    async def extract_document_metadata(self, url: str) -> Dict[str, Any]:
        """Extrae metadatos de un documento sin descargarlo"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.head(url) as response:
                return {
                    'url': url,
                    'content_type': response.headers.get('content-type', ''),
                    'content_length': int(response.headers.get('content-length', 0)),
                    'last_modified': response.headers.get('last-modified', ''),
                    'status_code': response.status,
                    'accessible': response.status == 200
                }
        except Exception as e:
            return {
                'url': url,
                'accessible': False,
                'error': str(e)
            }
    
    async def check_url_accessibility(self, url: str) -> bool:
        """Verifica si una URL es accesible"""
        try:
            metadata = await self.extract_document_metadata(url)
            return metadata.get('accessible', False)
        except:
            return False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
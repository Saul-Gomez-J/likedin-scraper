import random
import logging
import urllib.parse
from playwright.sync_api import sync_playwright
from time import sleep
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
import re

load_dotenv()

client = OpenAI()

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista de User-Agents para rotación
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
]

def cargar_cookies(context, archivo_cookies):
    try:
        with open(archivo_cookies, 'r') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        logging.info(f"Cookies cargadas desde {archivo_cookies}")
    except FileNotFoundError:
        logging.error(f"El archivo de cookies '{archivo_cookies}' no fue encontrado.")
    except json.JSONDecodeError:
        logging.error(f"Error al decodificar el archivo de cookies '{archivo_cookies}'.")

def generate_linkedin_search_query(prompt):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": """Eres un generador de URLs de búsqueda avanzada de Google para encontrar perfiles en LinkedIn. Tu objetivo es ayudar al usuario a construir URLs específicas para búsquedas de LinkedIn según sus descripciones en lenguaje natural. Cuando el usuario te proporcione una consulta, debes crear una URL que incluya todos los parámetros de búsqueda mencionados.

            Ejemplo de entradas y salidas:

            1. Entrada: "Quiero encontrar desarrolladores de software en Estados Unidos que hayan estudiado en MIT o Stanford."
            output: site:linkedin.com/in/ "Software Developer" "United States" ("MIT" OR "Stanford")

            2. Entrada: "Busco perfiles en LinkedIn de personas que trabajen en ventas y estén ubicadas en Europa."
            output: site:linkedin.com/in/ "sales" ("France" OR "Germany" OR "Spain" OR "Italy" OR "United Kingdom" OR "Netherlands")

            3. Entrada: "Me gustaría ver perfiles de gerentes de producto con experiencia en la industria tecnológica en California."
            output: site:linkedin.com/in/ "Product Manager" "technology industry" "California"

            4. Entrada: "Encuentra perfiles de ingenieros de datos en Canadá que tengan experiencia con Hadoop y Spark."
            output site:linkedin.com/in/ "Data Engineer" "Canada" ("Hadoop" OR "Spark")

            5. Entrada: "Quiero ver perfiles de personas que hayan trabajado como científicos de datos en Europa y hayan estudiado inteligencia artificial."
            output: site:linkedin.com/in/ "Data Scientist" ("France" OR "Germany" OR "Spain" OR "Italy" OR "United Kingdom") "Artificial Intelligence"

            Recuerda utilizar `site:linkedin.com/in/` al inicio de cada consulta para limitar la búsqueda a perfiles de LinkedIn y utilizar operadores como `OR` para agrupar términos similares. También, agrupa términos dentro de comillas para realizar búsquedas exactas.
            """},
            {"role": "user", "content": f"Generate a LinkedIn search query for: {prompt}"}
        ],
        max_tokens=300,
        temperature=0.5
    )
    return response.choices[0].message.content.strip()

def scrape_google_results(search_query):
    encoded_query = urllib.parse.quote(search_query)
    search_url = f"https://www.google.com/search?q={encoded_query}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = context.new_page()
        links = []
        try:
            page.goto(search_url, timeout=60000)
            page.wait_for_load_state('networkidle')
            sleep(random.uniform(2, 4))  # Espera para cargar completamente

            # Extraer URLs de los resultados de búsqueda
            results = page.query_selector_all('a')
            for result in results:
                href = result.get_attribute('href')
                if href and 'linkedin.com/in/' in href:
                    # Extraer la URL real usando regex
                    match = re.search(r'/url\?q=(https?://[^\&]+)&', href)
                    if match:
                        real_url = urllib.parse.unquote(match.group(1))
                    else:
                        # Si no está en formato de redirección de Google, usar directamente
                        real_url = href
                    # Validar que sea una URL de LinkedIn válida
                    if re.match(r'^https?://(es|www)\.linkedin\.com/in/[A-z0-9\-_%]+/?$', real_url):
                        links.append(real_url)
                        logging.info(f"Perfil encontrado: {real_url}")
                    if len(links) >= 20:
                        break

        except Exception as e:
            logging.error(f"Error al extraer enlaces: {e}")
        finally:
            browser.close()

        return links

def scrape_linkedin_profile(url, archivo_cookies):
    for intento in range(1, 4):  # Intentar 3 veces
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            
            # Cargar cookies antes de crear la página
            cargar_cookies(context, archivo_cookies)
            
            # Depuración: Imprimir las cookies cargadas
            cookies = context.cookies()
            logging.debug(f"Cookies cargadas: {len(cookies)}")
            for cookie in cookies:
                if cookie['name'] == 'li_at':  # Esta es una cookie importante de LinkedIn
                    logging.debug("Cookie de sesión de LinkedIn encontrada")
                    break
            else:
                logging.warning("Advertencia: No se encontró la cookie de sesión de LinkedIn")
            
            page = context.new_page()
            
            try:
                page.goto(url, timeout=60000)
                page.wait_for_load_state('networkidle')
                sleep(random.uniform(2, 5))  # Espera aleatoria

                # Verificar si estamos en la página de inicio de sesión
                if "linkedin.com/login" in page.url:
                    logging.warning(f"No se pudo acceder al perfil {url}. Redirigido a la página de inicio de sesión.")
                    return None

                # Extraer información del perfil
                name_element = page.query_selector('h1')
                position_element = page.query_selector('.top-card-layout__headline')
                location_element = page.query_selector('.top-card-layout__first-subline')

                if not all([name_element, position_element, location_element]):
                    logging.warning(f"No se pudieron encontrar algunos elementos en el perfil {url}.")
                    return None

                name = name_element.inner_text().strip()
                position = position_element.inner_text().strip()
                location = location_element.inner_text().strip()

                # Extraer experiencia laboral
                experience = []
                exp_elements = page.query_selector_all('section#experience-section li')
                for exp in exp_elements[:3]:  # Limitar a las 3 experiencias más recientes
                    title_element = exp.query_selector('.pv-entity__summary-info h3')
                    company_element = exp.query_selector('.pv-entity__secondary-title')
                    if title_element and company_element:
                        title = title_element.inner_text().strip()
                        company = company_element.inner_text().strip()
                        experience.append(f"{title} at {company}")

                # Extraer educación
                education = []
                edu_elements = page.query_selector_all('section#education-section li')
                for edu in edu_elements[:2]:  # Limitar a las 2 educaciones más recientes
                    school_element = edu.query_selector('.pv-entity__school-name')
                    degree_element = edu.query_selector('.pv-entity__degree-name')
                    if school_element and degree_element:
                        school = school_element.inner_text().strip()
                        degree = degree_element.inner_text().strip()
                        education.append(f"{degree} from {school}")

                logging.info(f"Perfil extraído exitosamente: {url}")
                return {
                    "url": url,
                    "name": name,
                    "position": position,
                    "location": location,
                    "experience": experience,
                    "education": education
                }

            except Exception as e:
                logging.error(f"Error al extraer perfil {url} en intento {intento}: {e}. Reintentando...")
                sleep(random.uniform(5, 10))  # Espera antes de reintentar
            finally:
                browser.close()

    logging.error(f"No se pudo extraer el perfil después de 3 intentos: {url}")
    return None

def buscar_y_scrapear(search_query, archivo_cookies):
    linkedin_links = scrape_google_results(search_query)
    if not linkedin_links:
        logging.warning("No se encontraron enlaces de LinkedIn.")
        return []

    linkedin_profiles = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(scrape_linkedin_profile, link, archivo_cookies): link for link in linkedin_links}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                data = future.result()
                if data:
                    linkedin_profiles.append(data)
            except Exception as exc:
                logging.error(f'{url} generó una excepción: {exc}')

    return linkedin_profiles

def main():
    print("LinkedIn Profile Scraper")
    print("\nIntroduce tu búsqueda en lenguaje natural. Nuestro sistema convertirá tu consulta en una búsqueda avanzada de LinkedIn.")
    print("\nEjemplos de búsquedas que puedes realizar:")
    print("- 'Encuentra desarrolladores de software en Estados Unidos que hayan estudiado en MIT o Stanford'")
    print("- 'Busca perfiles de gerentes de ventas en Europa con experiencia en tecnología'")
    print("- 'Quiero ver perfiles de científicos de datos en Canadá con experiencia en inteligencia artificial'")

    user_query = input("\nIntroduce tu búsqueda: ")
    archivo_cookies = 'cookies.json'

    # Verificar si el archivo de cookies existe
    if not os.path.exists(archivo_cookies):
        print(f"Error: El archivo de cookies '{archivo_cookies}' no existe.")
        print("Por favor, ejecuta primero el script 'login_y_guardar_cookies.py' para generar las cookies.")
        return

    if user_query:
        print('Generando consulta de búsqueda avanzada...')
        search_query = generate_linkedin_search_query(user_query)
        print(f"Consulta de búsqueda generada: {search_query}")

        print('Realizando scraping... Esto puede tardar unos minutos.')
        perfiles = buscar_y_scrapear(search_query, archivo_cookies)
        
        if perfiles:
            print(f"Se encontraron {len(perfiles)} perfiles.")
            for perfil in perfiles:
                print(f"\n{perfil['name']}")
                print(f"Posición: {perfil['position']}")
                print(f"Ubicación: {perfil['location']}")
                print(f"URL: {perfil['url']}")
                
                print("Experiencia:")
                for exp in perfil['experience']:
                    print(f"- {exp}")
                
                print("Educación:")
                for edu in perfil['education']:
                    print(f"- {edu}")
                
                print("---")
        else:
            print("No se encontraron perfiles.")
    else:
        print("Por favor, introduce una consulta de búsqueda.")

if __name__ == "__main__":
    main()
import random
import logging
from playwright.sync_api import sync_playwright
from time import sleep
import os
import json

# Configuración de logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista de User-Agents para rotación
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, como Gecko) Version/14.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, como Gecko) Chrome/92.0.4515.107 Safari/537.36'
]

def cargar_cookies(context, archivo_cookies):
    try:
        with open(archivo_cookies, 'r') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        logging.info(f"Cookies cargadas desde {archivo_cookies}")
        
        # Verificar si la cookie 'li_at' está presente
        li_at = next((cookie for cookie in cookies if cookie['name'] == 'li_at'), None)
        if li_at:
            logging.info("Cookie de sesión 'li_at' encontrada.")
        else:
            logging.warning("Cookie de sesión 'li_at' no encontrada.")
        
    except FileNotFoundError:
        logging.error(f"El archivo de cookies '{archivo_cookies}' no fue encontrado.")
    except json.JSONDecodeError:
        logging.error(f"Error al decodificar el archivo de cookies '{archivo_cookies}'.")

def scrape_linkedin_profile(url, archivo_cookies):
    for intento in range(1, 4):  # Intentar 3 veces
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Modo visible para depuración
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            
            # Cargar cookies antes de crear la página
            cargar_cookies(context, archivo_cookies)
            
            page = context.new_page()
            
            try:
                logging.info(f"Intento {intento}: Accediendo a {url}")
                page.goto(url, timeout=120000)  # Aumentar timeout a 120 segundos
                page.wait_for_load_state('networkidle', timeout=120000)
                sleep(random.uniform(2, 5))  # Espera aleatoria
                
                # Capturar una captura de pantalla para depuración
                page.screenshot(path=f"screenshot_intento_{intento}.png")
                
                # Verificar si estamos en la página de inicio de sesión
                if "linkedin.com/login" in page.url:
                    logging.warning(f"No se pudo acceder al perfil {url}. Redirigido a la página de inicio de sesión.")
                    return None
                
                # Extraer información del perfil con selectores actualizados
                name_element = page.query_selector('div.ph5.pb5 > div.display-flex.mt2 ul li')
                position_element = page.query_selector('.text-body-medium')  # Actualiza según inspección
                location_element = page.query_selector('.text-body-small.inline.t-black--light.break-words')  # Actualiza según inspección
                
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
                        experience.append(f"{title} en {company}")
                
                # Extraer educación
                education = []
                edu_elements = page.query_selector_all('section#education-section li')
                for edu in edu_elements[:2]:  # Limitar a las 2 educaciones más recientes
                    school_element = edu.query_selector('.pv-entity__school-name')
                    degree_element = edu.query_selector('.pv-entity__degree-name')
                    if school_element and degree_element:
                        school = school_element.inner_text().strip()
                        degree = degree_element.inner_text().strip()
                        education.append(f"{degree} de {school}")
                
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

def main():
    perfil_url = 'https://es.linkedin.com/in/francisco-monzonis-lucas-b1798111b'
    archivo_cookies = 'cookies.json'
    
    # Verificar si el archivo de cookies existe
    if not os.path.exists(archivo_cookies):
        print(f"Error: El archivo de cookies '{archivo_cookies}' no existe.")
        print("Por favor, ejecuta primero el script 'guardar_cookies.py' para generar las cookies.")
        return
    
    perfil = scrape_linkedin_profile(perfil_url, archivo_cookies)
    if perfil:
        print(f"\nNombre: {perfil['name']}")
        print(f"Posición: {perfil['position']}")
        print(f"Ubicación: {perfil['location']}")
        print(f"URL: {perfil['url']}")
        
        print("Experiencia:")
        for exp in perfil['experience']:
            print(f"- {exp}")
        
        print("Educación:")
        for edu in perfil['education']:
            print(f"- {edu}")
    else:
        print("No se pudo extraer el perfil.")

if __name__ == "__main__":
    main()


# from version_sin_steeamlit import scrape_linkedin_profile, scrape_google_results
# import os

# links =scrape_google_results('site:linkedin.com/in/ "automatizaciones" "España"')

# print(f"links recuperados con EXITO: {links}")
# archivo_cookies = 'cookies.json'



# # for link in links:
# #     profile = scrape_linkedin_profile(link, archivo_cookies)
# #     print(profile)


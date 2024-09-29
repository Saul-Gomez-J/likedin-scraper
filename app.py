import streamlit as st
import random
import logging
from playwright.sync_api import sync_playwright
from time import sleep
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import os
from dotenv import load_dotenv

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
    return response.choices[0].message.content

def scrape_google_results(search_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = context.new_page()
        links = []
        try:
            page.goto(search_url, timeout=60000)
            page.wait_for_load_state('networkidle')

            results = page.query_selector_all('a')
            for result in results:
                href = result.get_attribute('href')
                if href and 'linkedin.com/in/' in href:
                    links.append(href)
                    print(href)
                if len(links) >= 20:
                    break

        except Exception as e:
            st.error(f"Error al extraer enlaces: {e}")
        finally:
            browser.close()

        return links

def scrape_linkedin_profile(url):
    for _ in range(3):  # Intentar 3 veces
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = context.new_page()

            try:
                page.goto(url, timeout=60000)
                page.wait_for_load_state('networkidle')
                sleep(random.uniform(2, 5))  # Espera aleatoria

                name = page.query_selector('h1').inner_text()
                position = page.query_selector('.top-card-layout__headline').inner_text()
                location = page.query_selector('.top-card-layout__first-subline').inner_text()

                # Extraer experiencia laboral
                experience = []
                exp_elements = page.query_selector_all('section#experience-section li')
                for exp in exp_elements[:3]:  # Limitar a las 3 experiencias más recientes
                    title = exp.query_selector('.pv-entity__summary-info h3').inner_text()
                    company = exp.query_selector('.pv-entity__secondary-title').inner_text()
                    experience.append(f"{title} at {company}")

                # Extraer educación
                education = []
                edu_elements = page.query_selector_all('section#education-section li')
                for edu in edu_elements[:2]:  # Limitar a las 2 educaciones más recientes
                    school = edu.query_selector('.pv-entity__school-name').inner_text()
                    degree = edu.query_selector('.pv-entity__degree-name').inner_text()
                    education.append(f"{degree} from {school}")

                return {
                    "url": url,
                    "name": name,
                    "position": position,
                    "location": location,
                    "experience": experience,
                    "education": education
                }

            except Exception as e:
                st.warning(f"Error al extraer perfil {url}: {e}. Reintentando...")
                sleep(random.uniform(5, 10))  # Espera antes de reintentar
            finally:
                browser.close()

    st.error(f"No se pudo extraer el perfil después de 3 intentos: {url}")
    return None

def buscar_y_scrapear(search_query):
    google_search_url = f"https://www.google.com/search?q={search_query}"
    linkedin_links = scrape_google_results(google_search_url)

    linkedin_profiles = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(scrape_linkedin_profile, link): link for link in linkedin_links}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                data = future.result()
                if data:
                    linkedin_profiles.append(data)
            except Exception as exc:
                st.error(f'{url} generó una excepción: {exc}')

    return linkedin_profiles

def main():
    st.title("LinkedIn Profile Scraper")

    st.write("""
    Introduce tu búsqueda en lenguaje natural. Nuestro sistema convertirá tu consulta en una búsqueda avanzada de LinkedIn.
    
    Ejemplos de búsquedas que puedes realizar:
    - "Encuentra desarrolladores de software en Estados Unidos que hayan estudiado en MIT o Stanford"
    - "Busca perfiles de gerentes de ventas en Europa con experiencia en tecnología"
    - "Quiero ver perfiles de científicos de datos en Canadá con experiencia en inteligencia artificial"
    """)

    user_query = st.text_area("Introduce tu búsqueda:", height=100)

    if st.button("Iniciar Scraping"):
        if user_query:
            with st.spinner('Generando consulta de búsqueda avanzada...'):
                search_query = generate_linkedin_search_query(user_query)
                st.info(f"Consulta de búsqueda generada: {search_query}")

            with st.spinner('Realizando scraping... Esto puede tardar unos minutos.'):
                perfiles = buscar_y_scrapear(search_query)
                
                if perfiles:
                    st.success(f"Se encontraron {len(perfiles)} perfiles.")
                    for perfil in perfiles:
                        st.subheader(perfil['name'])
                        st.write(f"**Posición:** {perfil['position']}")
                        st.write(f"**Ubicación:** {perfil['location']}")
                        st.write(f"**URL:** {perfil['url']}")
                        
                        st.write("**Experiencia:**")
                        for exp in perfil['experience']:
                            st.write(f"- {exp}")
                        
                        st.write("**Educación:**")
                        for edu in perfil['education']:
                            st.write(f"- {edu}")
                        
                        st.write("---")
                else:
                    st.warning("No se encontraron perfiles.")
        else:
            st.error("Por favor, introduce una consulta de búsqueda.")

if __name__ == "__main__":
    main()
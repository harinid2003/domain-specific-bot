import os
import re
import uuid
import logging
from bs4 import BeautifulSoup 
from urllib.parse import urlparse
import google.generativeai as genai
from selenium import webdriver 
from selenium.webdriver.chrome.options import Options 
from data_upload import count_tokens, split_text_by_tokens  # Updated import

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def fetch_html_selenium(url, attended_mode=False):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--ignore-certificate-errors")  # <-- Add this
    chrome_options.add_argument("--ignore-ssl-errors")          # <-- Add this
    chrome_options.add_argument("--disable-web-security")       # <-- Add this
    chrome_options.add_argument("--allow-running-insecure-content")  # <-- Add this
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    html = driver.page_source
    driver.quit()
    return html

def extract_content_with_tags(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup.find_all(['script', 'style', 'aside', 'iframe']):
        element.decompose()
    extracted_content = ""
    header = soup.find('header')
    if header:
        header_content = header.get_text(separator=' ', strip=True)
        if header_content:
            extracted_content += f"<header>{header_content}</header>\n\n"
    tags_to_extract = [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'ul', 'ol', 'li', 'table', 'tr', 'th', 'td',
        'a', 'span', 'div', 'img'
    ]
    for element in soup.find_all(tags_to_extract):
        tag_name = element.name
        if tag_name == 'img':
            alt = element.get('alt', '').strip()
            src = element.get('src', '').strip()
            if alt:
                extracted_content += f"<img alt='{alt}' src='{src}' />\n\n"
            elif src:
                extracted_content += f"<img src='{src}' />\n\n"
        elif tag_name == 'a':
            link_text = element.get_text(separator=' ', strip=True)
            href = element.get('href', '').strip()
            if link_text or href:
                extracted_content += f"<a href='{href}'>{link_text}</a>\n\n"
        elif tag_name in ['table', 'tr', 'th', 'td']:
            table_text = element.get_text(separator=' ', strip=True)
            if table_text:
                extracted_content += f"<{tag_name}>{table_text}</{tag_name}>\n\n"
        else:
            content = element.get_text(separator=' ', strip=True)
            if content:
                extracted_content += f"<{tag_name}>{content}</{tag_name}>\n\n"
    footer = soup.find('footer')
    if footer:
        footer_content = footer.get_text(separator=' ', strip=True)
        if footer_content:
            extracted_content += f"<footer>{footer_content}</footer>\n\n"
    return extracted_content

def get_filename_and_structured_content_with_gemini(content, api_key, url):
    """
    Use Gemini to generate both a filename and structured content for the given URL and content.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    prompt = f"""
    I have extracted content from a webpage ({domain}) with HTML tags.
    First, suggest a concise filename (without extension) that reflects the main topic.
    Then, add two newlines and structure the content following these guidelines:

    1. Maintain the hierarchy of headings but convert them to a numbered format (1., 1.1, 1.1.1, etc.)
    2. Organize related paragraphs under their appropriate headings
    3. Format lists properly with bullet points or numbers as appropriate
    4. Improve the connectivity and flow of content
    5. Remove any header and footer content
    6. Make sure paragraphs flow logically
    7. Remove HTML tags
    8. Keep all meaningful content intact
    9. If there is url, mention it in the content and give the url in the content with details about the url

    Start your response with the filename on first line, then two newlines, then the structured content.
    Example format:
    suggested_filename_here

    structured content starts here...

    Here's the content to structure:
    {content}
    """

    response = model.generate_content(prompt)
    response_text = response.text.strip()
    parts = response_text.split('\n\n', 1)
    if len(parts) == 2:
        filename = parts[0].strip()
        structured_text = parts[1].strip()
    else:
        filename = str(uuid.uuid4())[:8]
        structured_text = response_text

    return filename, structured_text

def process_single_url(url, gemini_api_key):
    try:
        raw_html = fetch_html_selenium(url, attended_mode=False)
        extracted_content = extract_content_with_tags(raw_html)

        # Get structured content from Gemini
        suggested_filename, structured_content = get_filename_and_structured_content_with_gemini(
            extracted_content,
            gemini_api_key,
            url
        )

        # Clean up filename for document_id
        safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', suggested_filename)[:50]

        # Prepare data objects and upload immediately
        token_count = count_tokens(structured_content)
        data_objects = []
        doc_uuid = safe_filename

        if token_count > 8000:
            chunks = split_text_by_tokens(structured_content)
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                obj = {
                    "document_id": f"{doc_uuid}_{i + 1}",
                    "url": url,
                    "content": chunk,
                    "chunk_index": i + 1,
                    "total_chunks": total_chunks
                }
                data_objects.append(obj)
        else:
            obj = {
                "document_id": doc_uuid,
                "url": url,
                "content": structured_content,
                "chunk_index": 1,
                "total_chunks": 1
            }
            data_objects.append(obj)

        # Return processed data without uploading
        return {
            'success': True,
            'data_objects': data_objects,
            'url': url
        }

    except Exception as e:
        logging.error(f"Error processing URL {url}: {e}")
        return {
            'success': False,
            'error': str(e)
        }
import requests 
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import re

def get_sitemap_url_from_robots(website_url):
    try:
        robots_url = urljoin(website_url, '/robots.txt')
        response = requests.get(robots_url, timeout=10)
        sitemap_urls = []
        if response.status_code == 200:
            matches = re.findall(r'Sitemap:\s*(.*)', response.text, re.IGNORECASE)
            for match in matches:
                sitemap_urls.append(match.strip())
        return sitemap_urls
    except Exception:
        return []

def try_common_sitemap_locations(website_url):
    common_paths = ['/sitemap.xml', '/page-sitemap.xml']
    sitemap_urls = []
    for path in common_paths:
        try:
            url = urljoin(website_url, path)
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'xml' in content_type or response.text.strip().startswith('<?xml'):
                    try:
                        ET.fromstring(response.content)
                        if ('<urlset' in response.text or
                            '<sitemapindex' in response.text or
                            'xmlns:sitemap' in response.text or
                            'xmlns="http://www.sitemaps.org/' in response.text):
                            sitemap_urls.append(url)
                    except ET.ParseError:
                        continue
        except Exception:
            pass
    return sitemap_urls

def parse_sitemap(sitemap_url, all_urls=None, processed_sitemaps=None, max_depth=10, current_depth=0):
    if all_urls is None:
        all_urls = []
    if processed_sitemaps is None:
        processed_sitemaps = set()
    if current_depth > max_depth or sitemap_url in processed_sitemaps:
        return all_urls, processed_sitemaps
    processed_sitemaps.add(sitemap_url)
    try:
        response = requests.get(sitemap_url, timeout=15)
        if response.status_code != 200:
            return all_urls, processed_sitemaps
        root = ET.fromstring(response.content)
        namespace = ''
        tag = root.tag
        if '}' in tag:
            namespace = tag[0:tag.find('}') + 1]
        if 'sitemapindex' in root.tag:
            for sitemap_elem in root.findall(f".//{namespace}sitemap"):
                loc_elem = sitemap_elem.find(f"{namespace}loc")
                if loc_elem is not None and loc_elem.text:
                    child_sitemap_url = loc_elem.text.strip()
                    all_urls, processed_sitemaps = parse_sitemap(
                        child_sitemap_url, all_urls, processed_sitemaps, max_depth, current_depth + 1
                    )
        elif 'urlset' in root.tag:
            for url_elem in root.findall(f".//{namespace}url"):
                loc_elem = url_elem.find(f"{namespace}loc")
                if loc_elem is not None and loc_elem.text:
                    page_url = loc_elem.text.strip()
                    all_urls.append(page_url)
    except Exception:
        pass
    return all_urls, processed_sitemaps

def process_website(website_url, max_depth=10):
    all_urls = []
    processed_sitemaps = set()
    sitemap_urls = get_sitemap_url_from_robots(website_url)
    if not sitemap_urls:
        sitemap_urls = try_common_sitemap_locations(website_url)
    for sitemap_url in sitemap_urls:
        all_urls, processed_sitemaps = parse_sitemap(
            sitemap_url, all_urls, processed_sitemaps, max_depth=max_depth
        )
    unique_urls = list(set(all_urls))
    return unique_urls, processed_sitemaps
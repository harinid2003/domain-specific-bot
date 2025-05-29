import os
import re
import json
import logging
import warnings
import requests
from api_info import weaviate_api_key, weaviate_url, gemini_api_key
import weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import google.generativeai as genai
from weaviate.collections import Collection
from weaviate.util import generate_uuid5
from tenacity import retry, stop_after_attempt, wait_exponential
from weaviate.classes.init import Auth, AdditionalConfig, Timeout
from weaviate.classes.config import Property, DataType, Configure

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure Gemini API
genai.configure(api_key=gemini_api_key)

# Utility functions
def count_tokens(text):
    """Count approximate tokens by splitting into words"""
    words = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
    return int(len(words) * 1.25)

def split_text_by_tokens(text, max_tokens=2000):
    """Split text into chunks by approximate token count"""
    words = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
    chunks = []
    current_chunk_words = []
    current_token_count = 0

    for word in words:
        token_estimate = 1
        if current_token_count + token_estimate > max_tokens:
            chunk_text = ' '.join(current_chunk_words)
            chunks.append(chunk_text.strip())
            current_chunk_words = [word]
            current_token_count = token_estimate
        else:
            current_chunk_words.append(word)
            current_token_count += token_estimate

    if current_chunk_words:
        chunk_text = ' '.join(current_chunk_words)
        chunks.append(chunk_text.strip())

    return chunks

def generate_gemini_embedding(text):
    """Generate embeddings using Gemini's text-embedding-004 model"""
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="RETRIEVAL_DOCUMENT"
        )
        return result["embedding"]
    except Exception as e:
        logging.error(f"Failed to generate Gemini embedding: {str(e)}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_url_content(url):
    """Fetch content from a URL with retry logic"""
    try:
        response = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        return response.text
    except Exception as e:
        logging.error(f"Failed to fetch URL {url}: {str(e)}")
        raise

# Suppress deprecation warning from weaviate client
warnings.filterwarnings("ignore", category=DeprecationWarning, module="weaviate")
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def connect_to_weaviate():
    """Connect to Weaviate with retry logic"""
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=weaviate_url,
            auth_credentials=weaviate.auth.Auth.api_key(weaviate_api_key),
            headers={
                "X-Google-Api-Key": gemini_api_key
            }
        )
        return client
    except Exception as e:
        logging.error(f"Weaviate connection failed: {str(e)}")
        raise

def sanitize_collection_name(name):
    """Sanitize collection name to meet Weaviate requirements"""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if not sanitized or not sanitized[0].isalpha():
        sanitized = 'Tenant_' + sanitized
    if not sanitized[0].isupper():
        sanitized = sanitized[0].upper() + sanitized[1:]
    return sanitized

def initialize_collection(collection_name: str) -> bool:
    """Initialize a new collection in Weaviate"""
    try:
        client = connect_to_weaviate()
        
        try:
            collection = client.collections.get(collection_name)
            logging.info(f"Collection '{collection_name}' already exists")
            return True
        except weaviate.exceptions.WeaviateCollectionDoesNotExist:
            collection = client.collections.create(
                name=collection_name,
                properties=[
                    {"name": "document_id", "dataType": "text"},
                    {"name": "url", "dataType": "text"},
                    {"name": "content", "dataType": "text"},
                    {"name": "chunk_index", "dataType": "int"},
                    {"name": "total_chunks", "dataType": "int"}
                ],
                vectorizer_config=None  # We'll provide vectors manually
            )
            logging.info(f"Collection '{collection_name}' created successfully!")
            return True
    except Exception as e:
        logging.error(f"Failed to create collection: {str(e)}")
        return False

def upload_single_chunk_to_weaviate(data_object: dict, collection_name: str) -> dict:
    """Upload a single chunk to Weaviate with its embedding"""
    try:
        embedding = generate_gemini_embedding(data_object["content"])
        if embedding is None:
            return {"success": False, "error": "Failed to generate embedding"}

        client = connect_to_weaviate()
        collection = client.collections.get(collection_name)
        
        collection.data.insert(
            properties=data_object,
            vector=embedding
        )
        
        return {"success": True}
        
    except Exception as e:
        logging.error(f"Failed to upload chunk: {str(e)}")
        return {"success": False, "error": str(e)}

def process_urls(urls, tenant_id, collection_name):
    """Process a list of URLs and upload content to Weaviate"""
    for url in urls:
        try:
            logging.info(f"Processing URL: {url}")
            content = fetch_url_content(url)
            chunks = split_text_by_tokens(content)
            total_chunks = len(chunks)

            for i, chunk in enumerate(chunks):
                data_object = {
                    "document_id": f"{tenant_id}_{url}_{i}",
                    "url": url,
                    "content": chunk,
                    "chunk_index": i,
                    "total_chunks": total_chunks
                }
                result = upload_single_chunk_to_weaviate(data_object, collection_name)
                if not result["success"]:
                    logging.error(f"Failed to upload chunk {i} for URL {url}: {result.get('error')}")
        except Exception as e:
            logging.error(f"Error processing URL {url}: {str(e)}")
from flask import Flask, render_template, request, jsonify, Response
import os
import json
import logging
from datetime import datetime, timezone
import time
from instructions import generate_instructions
from api_info import gemini_api_key

# Import modules
from urls import process_website
from scrape import process_single_url
from data_upload import initialize_collection, upload_single_chunk_to_weaviate
import mongodb

app = Flask(__name__, 
    static_folder='static',
    static_url_path='/static',
    template_folder='templates'
)

TENANT_PREFIX = "tenant_"
URLS_PER_MINUTE = 18
DELAY_BETWEEN_URLS = 60 / URLS_PER_MINUTE

def get_collection_name(id):
    return f"{TENANT_PREFIX}{id}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract_urls', methods=['POST'])
def extract_urls():
    website_url = request.json.get('website_url')
    if not website_url:
        return jsonify({'error': 'No website URL provided'}), 400
        
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
    urls, processed_sitemaps = process_website(website_url, max_depth=20)
    return jsonify({'urls': urls, 'processed_sitemaps': list(processed_sitemaps)})

@app.route('/save_user_data', methods=['POST'])
def save_user():
    try:
        logging.info("Received request to save user data.")
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required_fields = [
            'bot_name', 'welcome_message', 'bot_description', 'color_theme',
            'company_name', 'company_address', 'company_description', 'about_us',
            'linkedin', 'facebook', 'terms_url', 'privacy_policy_url', 'pricing_url',
            'contact_email', 'contact_number', 'website_url', 'selected_urls'
        ]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            logging.warning(f"Missing required fields: {', '.join(missing_fields)}")
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        # Generate instructions for the chatbot
        instruction_result = generate_instructions(url=data['website_url'])

        if not instruction_result['success']:
            logging.error(f"Failed to generate instructions: {instruction_result['error']}")
            return jsonify({'error': 'Failed to generate bot instructions'}), 500

        # Prepare MongoDB data with instructions
        mongo_data = {
            "tenant_url": data['website_url'],
            "selected_urls": data['selected_urls'],
            "bot_name": data['bot_name'],
            "welcome_message": data['welcome_message'],
            "bot_description": data['bot_description'],
            "color_theme": data['color_theme'],
            "company_name": data['company_name'],
            "company_address": data['company_address'],
            "company_description": data['company_description'],
            "aboutUs": data['about_us'],
            "linkedIn": data['linkedin'],
            "facebook": data['facebook'],
            "termsUrl": data['terms_url'],
            "privacy_policy_url": data['privacy_policy_url'],
            "pricing_url": data['pricing_url'],
            "contact_email": data['contact_email'],
            "contact_number": data['contact_number'],
            "status": "inactive",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bot_instructions": instruction_result['instructions']  # Add generated instructions
        }
        
        tenant_id = mongodb.insert_tenant(mongo_data)
        if not tenant_id:
            return jsonify({'error': 'Failed to save to MongoDB'}), 500

        # Create collection name with tenant_id
        collection_name = f"tenant_{tenant_id}"
        
        # Initialize Weaviate collection
        if not initialize_collection(collection_name):
            return jsonify({'error': 'Failed to initialize Weaviate collection'}), 500

        logging.info(f"User data saved and collection initialized. tenant_id={tenant_id}")
        
        # Start processing URLs in background
        from threading import Thread
        Thread(target=process_urls_for_tenant, args=(tenant_id,)).start()
        
        return jsonify({
            'success': True,
            'tenant_id': tenant_id,
            'collection_name': collection_name
        })

    except Exception as e:
        logging.error(f"Error in save_user: {str(e)}")
        return jsonify({'error': str(e)}), 500

def process_urls_for_tenant(tenant_id):
    """Process URLs one by one with immediate upload"""
    try:
        tenant_data = mongodb.get_tenant(tenant_id)
        if not tenant_data:
            raise ValueError('Tenant not found')

        selected_urls = tenant_data.get('selected_urls', [])
        collection_name = get_collection_name(str(tenant_id))
        
        logging.info(f"Processing {len(selected_urls)} URLs for tenant_id={tenant_id}")

        results = {}
        successful_uploads = 0

        for i, url in enumerate(selected_urls):
            try:
                if i > 0:
                    time.sleep(DELAY_BETWEEN_URLS)

                # Process single URL
                result = process_single_url(url=url, gemini_api_key=gemini_api_key)
                
                if result.get('success') and 'data_objects' in result:
                    # Upload each chunk individually
                    chunks_uploaded = 0
                    for chunk in result['data_objects']:
                        upload_result = upload_single_chunk_to_weaviate(chunk, collection_name)
                        if upload_result.get('success'):
                            chunks_uploaded += 1
                    
                    if chunks_uploaded > 0:
                        successful_uploads += 1
                        results[url] = {
                            'success': True,
                            'chunks_uploaded': chunks_uploaded
                        }
                        logging.info(f"Processed and uploaded URL ({i+1}/{len(selected_urls)}): {url}")
                    else:
                        results[url] = {
                            'success': False,
                            'error': 'Failed to upload chunks'
                        }
                else:
                    results[url] = {
                        'success': False,
                        'error': result.get('error', 'Processing failed')
                    }

            except Exception as e:
                logging.error(f"Error processing URL {url}: {e}")
                results[url] = {'success': False, 'error': str(e)}

        # Update final status
        status = "active" if successful_uploads > 0 else "inactive"
        mongodb.update_tenant_status(tenant_id, status)
        mongodb.update_tenant_results(tenant_id, results)

        return results

    except Exception as e:
        logging.error(f"Process failed: {str(e)}")
        return {'error': str(e)}

@app.route('/process_urls', methods=['POST'])
def process_urls():
    try:
        data = request.json
        if not data or 'tenant_id' not in data:
            return jsonify({'error': 'No tenant_id provided'}), 400

        tenant_id = data['tenant_id']
        tenant_data = mongodb.get_tenant(tenant_id)
        
        if not tenant_data:
            return jsonify({'error': 'Tenant not found'}), 404

        selected_urls = tenant_data['selected_urls']
        collection_name = get_collection_name(str(tenant_id))
        
        # Initialize collection if it doesn't exist
        if not initialize_collection(collection_name):
            return jsonify({'error': 'Failed to initialize Weaviate collection'}), 500
        
        logging.info(f"Processing {len(selected_urls)} URLs for tenant_id={tenant_id}")

        results = {}
        successful_uploads = 0

        for i, url in enumerate(selected_urls):
            try:
                if i > 0:
                    time.sleep(DELAY_BETWEEN_URLS)

                result = process_single_url(url=url, gemini_api_key=gemini_api_key)
                
                if result.get('success') and 'data_objects' in result:
                    chunks_uploaded = 0
                    for chunk in result['data_objects']:
                        upload_result = upload_single_chunk_to_weaviate(chunk, collection_name)
                        if upload_result.get('success'):
                            chunks_uploaded += 1
                    
                    if chunks_uploaded > 0:
                        successful_uploads += 1
                        results[url] = {
                            'success': True,
                            'chunks_uploaded': chunks_uploaded
                        }
                        logging.info(f"Successfully processed and uploaded URL ({i+1}/{len(selected_urls)}): {url}")
                    else:
                        results[url] = {
                            'success': False,
                            'error': 'Failed to upload chunks'
                        }
                else:
                    results[url] = {
                        'success': False,
                        'error': result.get('error', 'Processing failed')
                    }

            except Exception as e:
                logging.error(f"Error processing URL {url}: {e}")
                results[url] = {'success': False, 'error': str(e)}

        # Update MongoDB status
        status = "active" if successful_uploads > 0 else "inactive"
        mongodb.update_tenant_status(tenant_id, status)
        mongodb.update_tenant_results(tenant_id, results)

        return jsonify({
            'success': successful_uploads > 0,
            'results': results,
            'successful_uploads': successful_uploads,
            'total_urls': len(selected_urls)
        })

    except Exception as e:
        logging.error(f"Process failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/embed_script_by_tenant/<tenant_id>')
def embed_script_by_tenant(tenant_id):
    script_tag = f'<script src="https://yourdomain.com/static/chatbot.js" data-tenant-id="{tenant_id}"></script>'
    return Response(script_tag, mimetype='text/html')

@app.route('/progress_status')
def progress_status():
    return jsonify({
        'progress': 0,
        'processed': 0,
        'total': 0,
        'upload': 0,
        'complete': False
    })

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Only show errors, not every request
    app.run(debug=True, use_reloader=False)  # <--- Add use_reloader=False
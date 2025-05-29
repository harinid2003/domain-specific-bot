# Chatbot Admin Panel

A web-based admin panel for creating, configuring, and deploying AI-powered chatbots tailored to specific company websites. The system scrapes website content, generates chatbot instructions using Gemini, stores data in MongoDB, and manages embeddings in Weaviate for retrieval-augmented generation.

## Features

- **Website URL Extraction:** Extracts all URLs from a website's sitemap or robots.txt.
- **Content Scraping:** Uses Selenium and BeautifulSoup to extract and structure content from selected URLs.
- **AI Instruction Generation:** Leverages Gemini (Google Generative AI) to generate chatbot instructions based on company content.
- **Data Storage:** Stores tenant and user data in MongoDB.
- **Vector Storage:** Uploads processed content chunks to Weaviate for semantic search.
- **Admin UI:** Multi-step web interface for URL selection, bot configuration, and deployment script generation.
- **Deployment:** Provides a script tag for embedding the chatbot on any website.

## Project Structure

- `index.py` — Flask app entry point and API routes.
- `urls.py` — Sitemap and URL extraction utilities.
- `scrape.py` — Web scraping and content structuring logic.
- `data_upload.py` — Tokenization and Weaviate upload utilities.
- `instructions.py` — Generates chatbot instructions using Gemini.
- `mongodb.py` — MongoDB connection and CRUD helpers.
- `static/` — Frontend JavaScript and assets.
- `templates/` — HTML templates for the admin panel.
- `requirements.txt` — Python dependencies.

## Setup

### Prerequisites

- Python 3.9+
- Chrome browser (for Selenium)
- MongoDB Atlas account
- Weaviate cloud instance
- Google Generative AI (Gemini) API key
- OpenAI API key (for embeddings)

### Installation

1. **Clone the repository:**
   ```
   git clone <repo-url>
   cd chatbot-admin-panel
   ```

2. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

3. **Configure API keys:**
   - Edit `api_info.py` and set your API keys and connection strings.

4. **Run the Flask app:**
   ```
   python index.py
   ```

5. **Access the admin panel:**
   - Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Usage

1. **Enter the company website URL.**
2. **Select URLs to include in the chatbot's knowledge base.**
3. **Configure bot and company details.**
4. **Submit and wait for processing (content scraping, instruction generation, and embedding).**
5. **Copy the generated script tag and embed it in your website to deploy the chatbot.**

## Environment Variables

All sensitive keys are stored in `api_info.py`. For production, consider using environment variables or a `.env` file.

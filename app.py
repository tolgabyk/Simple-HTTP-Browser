import aiohttp
import asyncio
from flask import Flask, request, render_template, jsonify, send_from_directory
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import uuid

app = Flask(__name__)

async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()

async def download_resource(session, url, resource_path):
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.read()
            with open(resource_path, 'wb') as file:
                file.write(content)
            return True
    except Exception as e:
        print(f"Error fetching resource {url}: {str(e)}")
        return False

def safe_file_name(url):
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    safe_filename = ''.join([c for c in filename if c.isalnum() or c in ('-', '_', '.')])
    return safe_filename or 'resource'

def update_links(soup, base_url):
    for tag in soup.find_all(['a', 'link', 'script', 'img', 'form']):
        src_attr = 'href' if tag.name in ['a', 'link', 'form'] else 'src'
        if src_attr in tag.attrs:
            original_url = tag[src_attr]
            if original_url.startswith('http'):  # Dış bağlantıları es geç
                continue
            new_url = urljoin(base_url, original_url)
            if tag.name == 'form':
                tag[src_attr] = f"/proxy?url={new_url}"
            else:
                tag[src_attr] = f"/proxy?url={new_url}"
    return soup

async def download_resources(session, base_url, html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    resource_folder = os.path.join('static', 'resources', str(uuid.uuid4()))
    os.makedirs(resource_folder, exist_ok=True)
    tasks = []

    for res in soup.find_all(['link', 'script', 'img']):
        src_attr = 'href' if res.name == 'link' else 'src'
        if src_attr in res.attrs:
            res_url = urljoin(base_url, res[src_attr])
            safe_path = safe_file_name(res_url)
            resource_path = os.path.join(resource_folder, safe_path)
            tasks.append((download_resource(session, res_url, resource_path), res, src_attr, resource_path))

    for task, res, src_attr, resource_path in tasks:
        success = await task
        if success:
            res[src_attr] = f"/{resource_path.replace(os.sep, '/')}"

    return soup.prettify()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/site_indir', methods=['POST'])
async def site_indir():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'URL cannot be empty'}), 400

    try:
        async with aiohttp.ClientSession() as session:
            html_content = await fetch(session, url)
            if html_content:
                base_url = urlparse(url).scheme + "://" + urlparse(url).netloc
                updated_html = update_links(BeautifulSoup(html_content, 'html.parser'), base_url)
                content = await download_resources(session, base_url, updated_html.prettify())
                return render_template('display.html', content=content)
            else:
                return jsonify({'error': 'Failed to fetch the content from the provided URL.'}), 500
    except Exception as e:
        return jsonify({'error': f"Error fetching data from URL: {str(e)}"}), 500

@app.route('/proxy')
async def proxy():
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400

    try:
        async with aiohttp.ClientSession() as session:
            html_content = await fetch(session, url)
            if html_content:
                base_url = urlparse(url).scheme + "://" + urlparse(url).netloc
                updated_html = update_links(BeautifulSoup(html_content, 'html.parser'), base_url)
                content = await download_resources(session, base_url, updated_html.prettify())
                return render_template('display.html', content=content)
            else:
                return "Failed to fetch content", 500
    except Exception as e:
        return str(e), 500

@app.route('/static/resources/<path:filename>')
def serve_resource(filename):
    return send_from_directory('static/resources', filename)

if __name__ == '__main__':
    app.run(debug=True)

import curses
import json
from utils import get_url_for_topic, topic_urls, menu, getUrls, get_summary, getArticleText, knn_search
import requests
from sentence_transformers import SentenceTransformer
from mattsollamatools import chunker

feed_url = "http://www.npr.org/rss/rss.php?id=1001"
urls = getUrls(feed_url, n=1)
model = SentenceTransformer('all-MiniLM-L6-v2')
allEmbeddings = []

for url in urls:
    url = url.strip()
    article={}
    article['embeddings'] = []
    article['url'] = url
    text = getArticleText(url)
    summary = get_summary(text)
    chunks = chunker(text)  # Use the chunk_text function from web_utils
    embeddings = model.encode(chunks)
    for (chunk, embedding) in zip(chunks, embeddings):
        item = {}
        item['source'] = chunk
        item['embedding'] = embedding.tolist()  # Convert NumPy array to list
        item['sourcelength'] = len(chunk)
        article['embeddings'].append(item)

    allEmbeddings.append(article)

    print(f"{url}")
    print(f"{summary}\n")

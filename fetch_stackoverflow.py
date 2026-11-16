import html
import os
import time
import re

import requests
from bs4 import BeautifulSoup


API = "https://api.stackexchange.com/2.3"
API_KEY = ""          
MAX_PAGES = 5         
TAGS = {
    "python": "data/issues/python",
    "javascript": "data/issues/javascript",
    "streamlit": "data/issues/streamlit",
}
QUERY = {"python": "error", "javascript": "error", "streamlit": "error"}


def call(path, **params):
    params["site"] = "stackoverflow"
    if API_KEY:
        params["key"] = API_KEY
    resp = requests.get(f"{API}/{path}", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    time.sleep(max(data.get("backoff", 0), 1))
    print("  requests left today:", data.get("quota_remaining"))
    return data


def to_text(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    for pre in soup.find_all("pre"):
        pre.replace_with("\n```\n" + pre.get_text() + "\n```\n")
    for code in soup.find_all("code"):
        code.replace_with("`" + code.get_text() + "`")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "h1", "h2", "h3", "blockquote"]):
        block.append("\n")
    return re.sub(r"\n{3,}", "\n\n", soup.get_text()).strip()


for tag, folder in TAGS.items():
    os.makedirs(folder, exist_ok=True)
    saved = 0
    for page in range(1, MAX_PAGES + 1):
        data = call(
            "search/advanced",
            accepted="True", tagged=tag, q=QUERY[tag], sort="relevance", order="desc",
            filter="withbody", pagesize=100, page=page,
        )
        questions = data["items"]
        if not questions:
            break

        ids = ";".join(str(q["accepted_answer_id"]) for q in questions)
        answers = call(f"answers/{ids}", filter="withbody", pagesize=100)
        answer_by_id = {a["answer_id"]: a for a in answers["items"]}

        for q in questions:
            ans = answer_by_id.get(q["accepted_answer_id"])
            if not ans:
                continue
            text = (
                f"Source: Stack Overflow (CC BY-SA)\n"
                f"URL: {q['link']}\n"
                f"Tags: {', '.join(q['tags'])}\n"
                f"Score: {q['score']}\n\n"
                f"# {html.unescape(q['title'])}\n\n"
                f"## Question\n{to_text(q['body'])}\n\n"
                f"## Accepted answer\n{to_text(ans['body'])}\n"
            )
            with open(f"{folder}/{q['question_id']}.md", "w", encoding="utf-8") as f:
                f.write(text)
            saved += 1

        if not data.get("has_more"):
            break
    print(f"{tag}: saved {saved} questions")
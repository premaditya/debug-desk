import os 
import re
from collections import Counter

from dotenv import load_dotenv

from bs4 import BeautifulSoup

from langchain_community.document_loaders import (
    PyPDFLoader,
    BSHTMLLoader,
    TextLoader
)


load_dotenv(".env")

DOCS = {
    "python": ("data/docs/python", ".txt", "3.13"),
    "javascript": ("data/docs/javascript", ".md", "MDN"),
    "java": ("data/docs/java", ".html", "21"),
    "mysql": ("data/docs/MySQL", ".pdf", "8.4"),
    "streamlit": ("data/docs/streamlit", ".md", "latest (oct 2026)")
}

DOCS_URLS = {
    "python": "https://docs.python.org/3.13/",
    "javascript": "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
    "java": "https://docs.oracle.com/en/java/javase/21/",
    "mysql": "https://dev.mysql.com/doc/refman/8.4/en/",
    "streamlit": "https://docs.streamlit.io/",
}

ISSUES = {
    "python": ("data/issues/python", "stackoverflow"),
    "javascript": ("data/issues/javascript", "stackoverflow"),
    "streamlit": ("data/issues/streamlit", "stackoverflow"),
    "java": ("data/issues/java", "stackoverflow"),
    "mysql": ("data/issues/MySQL", "stackoverflow")
}

MIN_CHARS = 200
MIN_ANSWER_CHARS = 150
MIN_SHORT_ANSWER_CHARS = 30


MYSQL_RANGES = [(5515, 5551), (2645, 2931), (2176, 2211), (2281, 2367), (2575, 2599)]
MYSQL_PAGE_OFFSET = 32


def mysql_manual_page(trimmed_page):
    remaining = trimmed_page
    for start, end in MYSQL_RANGES:
        length = end - start + 1
        if remaining <= length:
            return start + remaining - 1 - MYSQL_PAGE_OFFSET
        remaining -= length
    return None

def extract_title_section(path, ext,text = ""):

    title = os.path.splitext(os.path.basename(path))[0]
    section = ""

    try:
        if ext == ".html":
            with open(
                path,
                encoding="utf-8",
                errors = "ignore",
            ) as file:
                soup = BeautifulSoup(file.read(), "html.parser")

            if soup.title and soup.title.get_text(strip= True):

                title = soup.title.get_text(" ", strip = True)

            heading = soup.find(["h1", "h2"])
            if heading:
                section = heading.get_text(" ", strip=True)

        elif ext == ".md":
            if not text:
                with open(
                    path,
                    encoding = "utf-8",
                    errors = "ignore",
                ) as file:
                    text = file.read()

            headings = re.findall(
                r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$",
                text,
                re.MULTILINE
            )

            if headings:
                title = headings[0].strip()

            if len(headings) > 1:
                section = headings[1].strip()

        elif ext == ".txt":
            if not text:
                with open(
                    path,
                    encoding= "utf-8",
                    errors= "ignore",
                ) as file:

                    text = file.read()

            for line in text.splitlines():
                line = line.strip()

                if line:
                    title = line[:200]
                    break

    except (OSError, ValueError):
        pass

    return title,section


def load_docs():

    documents = []

    for tech, (folder, ext, version) in DOCS.items():

        if not os.path.isdir(folder):
            print(f"Skipping missing documentation folder: {folder}")
            continue

        print(f"\n Loading {tech} documentation....")

        for root, dirs, files in os.walk(folder):
            dirs.sort()

            for name in sorted(files):

                if not name.lower().endswith(ext):
                    continue

                path = os.path.join(root, name)
                normalized_path = path.replace("\\", "/")
                if "/class-use/" in normalized_path or name in ("package-use.html", "package-tree.html"):
                    continue

                try:
                    if ext == ".pdf":
                        loader = PyPDFLoader(path)
                    elif ext == ".html":
                        loader = BSHTMLLoader(path, open_encoding="utf-8")
                    elif ext in (".txt", ".md"):
                        loader = TextLoader(
                            path,
                            encoding= "utf-8",
                            autodetect_encoding= True,
                        )

                    else:
                        continue

                    loaded_docs = loader.load()

                    title, section = extract_title_section(
                        path,
                        ext
                    )

                    metadata = {
                        "technology": tech,
                        "source_type": "official_documentation",
                        "source_url": DOCS_URLS[tech],
                        "file_name": name,
                        "version": version
                    }

                    if title:
                        metadata["title"] = title

                    if section:
                        metadata["section"] = section

                    for doc in loaded_docs:

                        if len(doc.page_content.strip()) < MIN_CHARS:
                            continue

                        doc.metadata.update(metadata)
                        doc.metadata["source"] = normalized_path


                        if ext == ".pdf":
                            page_index = doc.metadata.get("page")

                            if page_index is not None:
                                doc.metadata["page"] = int(page_index) + 1

                            if tech == "mysql":
                                doc.metadata["official_doc_page"] = mysql_manual_page(doc.metadata["page"])

                        documents.append(doc)

                except Exception as error:

                    print(
                        f"Could not load {normalized_path}: "
                        f"{type(error).__name__}: {error}"
                    )

                    continue

    print("\n Documentation loading completed.")
    print("Documentation documents:", len(documents))

    return documents


def load_issues():

    documents = []
    short_documents = []

    for tech, (folder, source_type) in ISSUES.items():

        if not os.path.isdir(folder):
            print(f"Skipping missing issues folder: {folder}")
            continue

        print(f"\nLoading {tech} issues....")

        for name in sorted(os.listdir(folder)):

            if not name.lower().endswith(".md"):
                continue

            path = os.path.join(folder, name)
            normalized_path = path.replace("\\","/")

            try:

                loader = TextLoader(
                    path,
                    encoding= "utf-8",
                    autodetect_encoding= True,
                )

                loaded_docs = loader.load()

                if not loaded_docs:
                    continue

                doc = loaded_docs[0]
                text = doc.page_content

                is_short = False

                if source_type == "stackoverflow":

                    parts = text.split(
                        "## Accepted answer",
                        1,
                    )

                    if len(parts) < 2:
                        continue

                    answer = parts[1]

                    if len(answer.strip()) < MIN_SHORT_ANSWER_CHARS:
                        continue

                    is_short = len(answer.strip()) < MIN_ANSWER_CHARS

                match = re.search(
                    r"^\s*URL:\s*(\S.*?)\s*$",
                    text,
                    re.MULTILINE
                )

                source_url = (
                    match.group(1).strip()
                    if match
                    else ""
                )

                title, section = extract_title_section(
                    path,
                    ".md",
                    text,
                )

                header, sep, rest = text.partition("\n# ")
                tags = ""
                kept = []
                for line in header.split("\n"):
                    if line.startswith("Tags:"):
                        tags = line[5:].strip()
                    if not line.startswith(("Source:", "URL:", "Score:")):
                        kept.append(line)
                doc.page_content = ("\n".join(kept) + sep + rest).strip()

                metadata = {
                    "technology": tech,
                    "source_type": source_type,
                    "file_name": name,
                    "source": normalized_path,
                    "title": title,
                    "tags": tags,
                }

                if source_url:
                    metadata["source_url"] = source_url

                
                doc.metadata.update(metadata)
                (short_documents if is_short else documents).append(doc)

            except Exception as error:
                print(
                    f"Could not load {normalized_path}: "
                    f"{type(error).__name__}: {error}"
                )

                continue

    documents.extend(short_documents)

    print("\nIssue Loading completed.")
    print("Issues documents:", len(documents))

    return documents


def load_all():

    print("="*55)
    print("Starting DebugDesk document Loading")
    print("="*55)

    documentation = load_docs()

    issues = load_issues()

    documents = documentation + issues

    counts = Counter(
        (
            doc.metadata["technology"],
            doc.metadata["source_type"]
        )
        for doc in documents
    )

    print("\n" + "="*55)
    print("Document Loading Summary")
    print("="*55)

    for (tech, source_type), count in sorted(counts.items()):
        print(f"{tech:12} {source_type:25} {count}")

    print("\nTotal documents:", len(documents))

    print(
        "Combined document characters:",
        sum(len(doc.page_content) for doc in documents),
    )

    return documents




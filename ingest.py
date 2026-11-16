import os
import re
import time
import random
import json
import hashlib
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_google_genai.embeddings import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from loader import load_all


# Step 1: Load Configuration
load_dotenv(".env")

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY not found in .env")

INDEX_DIR = "chroma_db"
COLLECTION_NAME = "debugdesk"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MIN_CHARS = 60   # drops heading-only fragments

MAX_CHUNKS_PER_RUN = 1000
BATCH_SIZE = 10
DELAY_SECONDS = 10
MAX_RETRIES = 6

ISSUE_TYPES = ("github_issues", "stackoverflow")


# Step 2: Chunking
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

header_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
    strip_headers=False,
)


def clean_metadata(metadata):
    return {
        key: value
        for key, value in metadata.items()
        if isinstance(value, (str, int, float, bool))
    }


def chunk_document(doc):
    meta = clean_metadata(doc.metadata)
    text = doc.page_content.strip()

    file_name = meta.get("file_name", "")
    is_pdf = file_name.endswith(".pdf")
    is_md_doc = (
        meta.get("source_type") == "official_documentation"
        and file_name.endswith(".md")
    )

    pieces = []   # (chunk text, heading metadata)

    if is_md_doc:
        # Markdown docs: use the front matter title, then split by headings
        front = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", text, re.DOTALL)
        if front:
            found = re.search(r"^title:\s*(.+)$", front.group(1), re.MULTILINE)
            if found:
                meta["title"] = found.group(1).strip().strip("\"'")
            text = text[front.end():].strip()

        for part in header_splitter.split_text(text):
            for chunk in splitter.split_text(part.page_content):
                pieces.append((chunk, part.metadata))
    else:
        for chunk in splitter.split_text(text):
            pieces.append((chunk, {}))

    results = []

    for chunk, headers in pieces:
        if len(chunk) < MIN_CHARS:
            continue

        # Put the title and headings at the top of every chunk
        path = " > ".join(
            x for x in [meta.get("title"), headers.get("h2"), headers.get("h3")] if x
        )
        if path and not is_pdf and path not in chunk:
            chunk = f"{path}\n\n{chunk}"

        results.append({
            "content": chunk,
            "metadata": {**meta, **headers},
        })

    return results


def build_chunks(documents):
    """Returns (chunks, count_before_dedup, duplicates_removed)."""

    all_chunks = []
    for doc in documents:
        all_chunks.extend(chunk_document(doc))

    unique, seen = [], set()
    for chunk in all_chunks:
        normalized = re.sub(r"\s+", " ", chunk["content"]).strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(chunk)

    for number, chunk in enumerate(unique, start=1):
        chunk["id"] = f"chunk_{number:06d}"

    return unique, len(all_chunks), len(all_chunks) - len(unique)


# Step 3: Load documents and chunk them (or reuse the saved chunks)
CACHE_FILE = "chunks_cache.json"

if os.path.exists(CACHE_FILE):
    print("Reusing saved chunks from", CACHE_FILE)
    with open(CACHE_FILE, encoding="utf-8") as file:
        saved = json.load(file)

    chunk_ids = [item["id"] for item in saved]
    chunks = [
        Document(page_content=item["text"], metadata=item["metadata"])
        for item in saved
    ]

else:
    documents = load_all()

    chunk_data, _, _ = build_chunks(documents)

    chunk_ids = [item["id"] for item in chunk_data]
    chunks = [
        Document(page_content=item["content"], metadata=item["metadata"])
        for item in chunk_data
    ]

    with open(CACHE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            [
                {"id": cid, "text": chunk.page_content, "metadata": chunk.metadata}
                for cid, chunk in zip(chunk_ids, chunks)
            ],
            file,
        )
    print("Saved chunks to", CACHE_FILE)

print("Total chunks:", len(chunks))
print(
    "Combined chunk characters:",
    sum(len(chunk.page_content) for chunk in chunks),
)


# Step 4: Initialize Embeddings
embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    task_type="RETRIEVAL_DOCUMENT",
)


# Step 5: Initialize ChromaDB
vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=INDEX_DIR,
)

existing_ids = set(vectorstore.get(include=[])["ids"])

if existing_ids:
    print("Existing collection found. Loading it...")
    print("Already embedded:", len(existing_ids))

    stale = existing_ids - set(chunk_ids)
    if stale:
        raise ValueError(
            "Existing collection has chunks that are not in the current data. "
            "Did the loader, chunk size or overlap change? "
            "Use a new index directory."
        )


# Step 6: Identify Pending Chunks (issues first, then documentation)
pending = [
    (cid, chunk)
    for cid, chunk in zip(chunk_ids, chunks)
    if cid not in existing_ids
]

pending.sort(
    key=lambda item: 0 if item[1].metadata["source_type"] in ISSUE_TYPES else 1
)

print("Still to embed:", len(pending))

pending = pending[:MAX_CHUNKS_PER_RUN]
print("Embedding in this run:", len(pending))


# Step 7: Embed Documents in Batches
embedded_now = 0
stopped = False

for start in range(0, len(pending), BATCH_SIZE):
    batch = pending[start:start + BATCH_SIZE]
    batch_ids = [cid for cid, _ in batch]
    batch_docs = [chunk for _, chunk in batch]

    for attempt in range(MAX_RETRIES):
        try:
            vectorstore.add_documents(
                documents=batch_docs,
                ids=batch_ids,
            )

            embedded_now += len(batch)
            completed = len(existing_ids) + embedded_now
            print(f"Embedded {completed}/{len(chunks)} chunks")

            if start + len(batch) < len(pending):
                time.sleep(DELAY_SECONDS)

            break

        except Exception as exc:
            message = str(exc).lower()

            retryable = any(
                term in message
                for term in [
                    "429",
                    "resource_exhausted",
                    "rate limit",
                    "quota exceeded",
                    "too many requests",
                    "500",
                    "502",
                    "503",
                    "504",
                ]
            )

            if not retryable:
                raise

            if attempt == MAX_RETRIES - 1:
                print(
                    "\nAPI limit reached. Change the API key or wait for "
                    "the reset, then run this file again to continue."
                )
                stopped = True
                break

            wait = min(60, 10 * (2 ** attempt))
            wait += random.uniform(0, 3)

            print(
                f"Temporary API error. "
                f"Retrying in {wait:.1f}s "
                f"({attempt + 1}/{MAX_RETRIES})"
            )
            time.sleep(wait)

    if stopped:
        break


# Step 8: Summary
total_now = len(existing_ids) + embedded_now
print(f"\nEmbedded this run: {embedded_now}")
print(f"Total in database: {total_now}/{len(chunks)}")
print(f"Remaining: {len(chunks) - total_now}")
print("Index saved at:", INDEX_DIR)
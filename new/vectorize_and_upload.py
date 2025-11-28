import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

# ============= CONFIGURATION =============
QDRANT_HOST = "hopper.proxy.rlwy.net"
QDRANT_PORT = 48447
QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.cWl-rXCSkKbL9rIzNj00YIYFkMskD71UfoKfoECy7I0"
QDRANT_HTTPS = False

COLLECTION_NAME = "czech_constitutional_court"
EMBEDDING_MODEL = "Seznam/retromae-small-cs"
DENSE_VECTOR_SIZE = 256

# Context window for Seznam model is ~512 tokens, ~2000 chars safe
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 150
EMBEDDING_BATCH_SIZE = 32
QDRANT_UPSERT_BATCH = 100
MAX_WORKERS = 4

INPUT_FOLDER = "json-output"
CHECKPOINT_FILE = "upload_checkpoint.json"

# ============= LOGGING =============
def setup_logging():
    logger = logging.getLogger(__name__)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Full log
    file_handler = logging.FileHandler("upload_full.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Error log
    error_handler = logging.FileHandler("upload_errors.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

# ============= TEXT CHUNKING =============
def semantic_chunk(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Split text into semantic chunks respecting sentence boundaries.
    """
    if not text or len(text) < 100:
        return [text] if text else []

    # Split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [text] if text else []

    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_length + sentence_len + 1 > chunk_size:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                
                # Add overlap from previous chunk
                overlap_sentences = []
                overlap_len = 0
                for s in reversed(current_chunk):
                    if overlap_len + len(s) <= overlap:
                        overlap_sentences.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break
                
                current_chunk = overlap_sentences + [sentence]
                current_length = sum(len(s) for s in current_chunk) + len(current_chunk)
            else:
                # Single sentence too long, add it anyway
                chunks.append(sentence)
                current_chunk = []
                current_length = 0
        else:
            current_chunk.append(sentence)
            current_length += sentence_len + 1

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return [c for c in chunks if len(c) >= 50]

# ============= CHECKPOINT =============
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"processed_files": []}

def save_checkpoint(checkpoint):
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")

# ============= MAIN PIPELINE =============
class VectorizationPipeline:
    def __init__(self):
        logger.info("🚀 Czech Constitutional Court Vectorization Pipeline")
        
        logger.info(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        
        logger.info("🔗 Connecting to Qdrant...")
        self.client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            api_key=QDRANT_API_KEY,
            https=QDRANT_HTTPS,
            timeout=120,
        )
        
        self.checkpoint = load_checkpoint()
        self.stats = {
            'files_processed': 0,
            'chunks_created': 0,
            'chunks_uploaded': 0,
            'errors': 0
        }

    def setup_collection(self):
        """Create collection if it doesn't exist."""
        try:
            if not self.client.collection_exists(COLLECTION_NAME):
                logger.info(f"📦 Creating collection: {COLLECTION_NAME}")
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=DENSE_VECTOR_SIZE,
                        distance=Distance.COSINE
                    ),
                )
            else:
                logger.info(f"✅ Collection {COLLECTION_NAME} exists")
        except Exception as e:
            logger.error(f"Failed to setup collection: {e}")
            raise

    def process_file(self, filepath):
        """Process a single JSON file."""
        filename = os.path.basename(filepath)
        
        if filename in self.checkpoint['processed_files']:
            logger.info(f"⏭️  Skipping {filename} (already processed)")
            return 0
        
        try:
            # Load JSON
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            case_number = data.get('case_number', '')
            date = data.get('date', '')
            full_text = data.get('full_text', '')
            
            if not full_text:
                logger.warning(f"⚠️  {filename}: No text content")
                return 0
            
            # Create chunks
            chunks = semantic_chunk(full_text)
            
            if not chunks:
                logger.warning(f"⚠️  {filename}: No chunks created")
                return 0
            
            logger.info(f"✂️  {filename}: Created {len(chunks)} chunks")
            
            # Prepare points
            all_points = []
            chunk_texts = []
            
            for idx, chunk_text in enumerate(chunks):
                payload = {
                    'case_number': case_number,
                    'date': date,
                    'chunk_index': idx,
                    'total_chunks': len(chunks),
                    'chunk_text': chunk_text,
                    'filename': filename
                }
                
                # Chunk 0 gets the full text
                if idx == 0:
                    payload['full_text'] = full_text
                    payload['has_full_text'] = True
                else:
                    payload['has_full_text'] = False
                
                # Generate unique ID
                uid = f"{case_number}_{idx}"
                pid = int(hashlib.md5(uid.encode()).hexdigest(), 16) % (2**63 - 1)
                
                all_points.append((pid, payload))
                chunk_texts.append(chunk_text)
            
            # Embed chunks
            logger.info(f"🧠 {filename}: Embedding {len(chunk_texts)} chunks...")
            vectors = self.model.encode(
                chunk_texts,
                batch_size=EMBEDDING_BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True
            )
            
            # Create Qdrant points
            qdrant_points = [
                PointStruct(id=pid, vector=v.tolist(), payload=payload)
                for (pid, payload), v in zip(all_points, vectors)
            ]
            
            # Upload in batches
            uploaded = 0
            for i in range(0, len(qdrant_points), QDRANT_UPSERT_BATCH):
                batch = qdrant_points[i:i + QDRANT_UPSERT_BATCH]
                try:
                    self.client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=batch,
                        wait=True
                    )
                    uploaded += len(batch)
                except Exception as e:
                    logger.error(f"❌ {filename}: Batch upload failed: {e}")
                    self.stats['errors'] += 1
            
            logger.info(f"✅ {filename}: Uploaded {uploaded} chunks")
            
            # Update checkpoint
            self.checkpoint['processed_files'].append(filename)
            save_checkpoint(self.checkpoint)
            
            self.stats['files_processed'] += 1
            self.stats['chunks_created'] += len(chunks)
            self.stats['chunks_uploaded'] += uploaded
            
            return uploaded
            
        except Exception as e:
            logger.error(f"❌ {filename}: Processing failed: {e}")
            self.stats['errors'] += 1
            return 0

    def run(self):
        """Main execution."""
        start_time = time.time()
        
        self.setup_collection()
        
        # Get all JSON files
        json_files = sorted(Path(INPUT_FOLDER).glob("*.json"))
        
        if not json_files:
            logger.error(f"❌ No JSON files found in {INPUT_FOLDER}")
            return
        
        logger.info(f"📁 Found {len(json_files)} JSON files")
        
        # Process files in parallel
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.process_file, str(f)): f.name
                for f in json_files
            }
            
            for future in as_completed(futures):
                filename = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"❌ {filename}: Unexpected error: {e}")
                    self.stats['errors'] += 1
        
        # Final report
        elapsed = time.time() - start_time
        logger.info(
            f"\n✅ UPLOAD COMPLETE!\n"
            f"  Files processed: {self.stats['files_processed']}\n"
            f"  Chunks created: {self.stats['chunks_created']}\n"
            f"  Chunks uploaded: {self.stats['chunks_uploaded']}\n"
            f"  Errors: {self.stats['errors']}\n"
            f"  Elapsed: {int(elapsed)}s\n"
            f"  Avg per file: {elapsed/len(json_files):.1f}s"
        )

if __name__ == "__main__":
    pipeline = VectorizationPipeline()
    pipeline.run()

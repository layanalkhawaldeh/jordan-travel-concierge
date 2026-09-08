import os
import math
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import google.generativeai as genai
from sqlalchemy.orm import Session
from src.database import SessionLocal, DocumentChunkModel
import src.config as config

# Configure Gemini for embedding generation
if config.GEMINI_API_KEY and config.GEMINI_API_KEY.lower() != "mock":
    genai.configure(api_key=config.GEMINI_API_KEY)

def chunk_document(text: str) -> List[str]:
    """
    Chunk document semantically by paragraphs. 
    If a paragraph is too long, it splits it by words to keep chunks around 150-200 words.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_words = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_words = len(para.split())
        
        # If a single paragraph is extremely large, chunk it by words
        if para_words > 200:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_words = 0
            
            # Chunk the large paragraph by word groups with overlap
            words = para.split()
            for k in range(0, len(words), 150):
                chunks.append(" ".join(words[k:k+180]))
        else:
            if current_words + para_words > 200:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_words = para_words
            else:
                current_chunk.append(para)
                current_words += para_words
                
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks

def generate_embedding(text: str, is_query: bool = False) -> List[float]:
    """Generates embedding vector for a given text chunk or query."""
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY.lower() == "mock":
        # Return a deterministic mock vector if API key is mock
        return [0.1] * 768

    task_type = "retrieval_query" if is_query else "retrieval_document"
    try:
        response = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type=task_type
        )
        return response["embedding"]
    except Exception as e:
        print(f"[RAG embedding error] Could not get embedding from Gemini: {e}")
        # Return dummy vector to prevent failure
        return [0.0] * 768

def seed_knowledge_base():
    """Reads documents from knowledge_base directory, chunks, embeds, and indexes them in PostgreSQL."""
    db = SessionLocal()
    try:
        kb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")
        if not os.path.exists(kb_dir):
            print(f"[RAG Seeding] Knowledge base directory {kb_dir} does not exist.")
            return

        # Check if we already have indexed chunks
        existing_chunks_count = db.query(DocumentChunkModel).count()
        if existing_chunks_count > 0:
            print(f"[RAG Seeding] Database already seeded with {existing_chunks_count} chunks. Skipping re-indexing.")
            return

        print("[RAG Seeding] Indexing knowledge base documents...")
        for filename in os.listdir(kb_dir):
            if not filename.endswith(".txt"):
                continue
            
            filepath = os.path.join(kb_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            chunks = chunk_document(content)
            print(f"[RAG Seeding] Indexing {filename} -> Split into {len(chunks)} chunks.")
            
            for idx, chunk_text in enumerate(chunks):
                emb = generate_embedding(chunk_text, is_query=False)
                
                db_chunk = DocumentChunkModel(
                    document_name=filename,
                    text=chunk_text,
                    embedding=emb,
                    metadata_info={"source": filename, "chunk_index": idx}
                )
                db.add(db_chunk)
        
        db.commit()
        print("[RAG Seeding] Knowledge base indexed successfully!")
    except Exception as e:
        db.rollback()
        print(f"[RAG Seeding] Failed: {e}")
    finally:
        db.close()

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    v1_arr = np.array(v1)
    v2_arr = np.array(v2)
    dot = np.dot(v1_arr, v2_arr)
    norm1 = np.linalg.norm(v1_arr)
    norm2 = np.linalg.norm(v2_arr)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))

def retrieve_relevant_knowledge(query: str, limit: int = 3, threshold: float = 0.40) -> List[Dict[str, Any]]:
    """
    Generates embedding for query, pulls all chunks from database,
    calculates cosine similarity, and returns top matches above threshold.
    """
    db = SessionLocal()
    try:
        query_emb = generate_embedding(query, is_query=True)
        all_chunks = db.query(DocumentChunkModel).all()
        
        scored_chunks = []
        for chunk in all_chunks:
            # Parse embedding list from JSON column
            chunk_emb = chunk.embedding
            if not chunk_emb:
                continue
            
            sim = cosine_similarity(query_emb, chunk_emb)
            if sim >= threshold:
                scored_chunks.append({
                    "text": chunk.text,
                    "document_name": chunk.document_name,
                    "score": sim,
                    "metadata": chunk.metadata_info
                })
        
        # Sort by similarity score descending
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:limit]
    except Exception as e:
        print(f"[RAG Retrieval Error] {e}")
        return []
    finally:
        db.close()

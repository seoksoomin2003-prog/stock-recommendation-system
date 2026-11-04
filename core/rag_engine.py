import os
import json
from typing import List, Dict, Optional
try:
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_community.vectorstores import Chroma
    from langchain_ollama import OllamaEmbeddings
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.prompts import PromptTemplate
    from langchain_community.llms import Ollama
    HAS_LANGCHAIN = True
except ImportError:
    PyPDFLoader = None
    Chroma = None
    OllamaEmbeddings = None
    RecursiveCharacterTextSplitter = None
    PromptTemplate = None
    Ollama = None
    HAS_LANGCHAIN = False
from utils.config import OLLAMA_URL, OLLAMA_MODEL, RAG_SETTINGS
from utils.logger import setup_logger

logger = setup_logger("RAGEngine")

class RAGEngine:
    """
    Fundamental Alpha RAG Engine (V1)
    - Renaissance Technologies 수준의 고신뢰도 기반 퀀트 리서치 자동화
    - PDF 기반 기업 공시(10-K, 10-Q), 실적 발표문 분석
    - Hallucination 방지를 위한 엄격한 Grounding 시스템
    - 모든 출력 JSON 형식 준수
    """
    def __init__(self):
        self.embedding = None
        self.db_path = RAG_SETTINGS["db_path"]
        self.vector_db = None
        self.text_splitter = None
        self.llm = None
        self._initialized = False

    def _lazy_initialize(self):
        if self._initialized:
            return
            
        import utils.config
        from utils.memory_guard import MemoryGuard
        if not MemoryGuard.allow("rag"):
            logger.warning("[MEMORY_GUARD] RAG initialization blocked due to memory pressure.")
            self._initialized = True
            return

        if utils.config.APP_MODE == "local":
            logger.info("RAGEngine running in Local Mode. Skipping heavy resource load.")
            self._initialized = True
            return

        if not HAS_LANGCHAIN:
            logger.warning("LangChain libraries are NOT installed. RAGEngine running in mockup mode.")
            self._initialized = True
            return

        try:
            logger.info("Initializing Production RAG resources (Chroma DB & Embeddings)...")
            self.embedding = OllamaEmbeddings(
                model=RAG_SETTINGS["embedding_model"],
                base_url=OLLAMA_URL.replace("/api/generate", "")
            )
            if not os.path.exists(self.db_path):
                os.makedirs(self.db_path)
                
            self.vector_db = Chroma(
                persist_directory=self.db_path,
                embedding_function=self.embedding
            )
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=RAG_SETTINGS["chunk_size"],
                chunk_overlap=RAG_SETTINGS["chunk_overlap"],
                separators=["\n\n", "\n", " ", ""]
            )
            self.llm = Ollama(model=OLLAMA_MODEL, base_url=OLLAMA_URL.replace("/api/generate", ""))
        except Exception as e:
            logger.error(f"Failed to initialize RAG resources: {e}")
        self._initialized = True
        
    def ingest_pdf(self, file_path: str, metadata: Optional[Dict] = None) -> Dict:
        """
        PDF 문서를 로드하고 벡터 DB에 저장
        """
        self._lazy_initialize()
        if self.vector_db is None or self.text_splitter is None:
            logger.warning("RAG Ingestion bypassed (mock/local mode).")
            return {"status": "success", "chunks_processed": 0, "source": file_path, "mode": "local"}
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return {"status": "error", "message": "File not found"}
        
        logger.info(f"Ingesting PDF: {file_path}")
        
        try:
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            
            # Chunking
            chunks = self.text_splitter.split_documents(documents)
            
            # 메타데이터 추가 (티커, 보고서 유형 등)
            if metadata:
                for chunk in chunks:
                    chunk.metadata.update(metadata)
            
            # Vector DB 추가
            self.vector_db.add_documents(chunks)
            # self.vector_db.persist() # New versions of Chroma often persist automatically
            
            logger.info(f"Successfully ingested {len(chunks)} chunks from {file_path}")
            return {
                "status": "success", 
                "chunks_processed": len(chunks),
                "source": file_path
            }
        except Exception as e:
            logger.error(f"Error during ingestion: {str(e)}")
            return {"status": "error", "message": str(e)}

    def retrieve(self, query: str, k: int = None) -> List[Dict]:
        """
        관련 문맥 검색
        """
        self._lazy_initialize()
        if self.vector_db is None:
            logger.warning("RAG retrieve called in mock mode. Returning empty list.")
            return []
        k = k or RAG_SETTINGS["search_k"]
        results = self.vector_db.similarity_search_with_relevance_scores(query, k=k)
        
        # 임계값 기반 필터링
        threshold = RAG_SETTINGS["score_threshold"]
        filtered_results = [
            {"content": r[0].page_content, "metadata": r[0].metadata, "relevance": r[1]}
            for r in results if r[1] >= threshold
        ]
        
        return filtered_results

    def generate_fundamental_insight(self, ticker: str, query: str) -> Dict:
        """
        검색된 문맥을 바탕으로 Hallucination 없는 인사이트 생성
        - JSON 형식 반환
        """
        self._lazy_initialize()
        context_docs = self.retrieve(f"{ticker} {query}")
        
        if not context_docs:
            return {
                "ticker": ticker,
                "insight": "Information not available in current database.",
                "confidence": 0.0,
                "sources": []
            }
        
        context_text = "\n---\n".join([d['content'] for d in context_docs])
        
        prompt = f"""
[Role]
You are a Principal Quant Engineer and Fundamental Analyst. 
Provide a high-conviction analysis based ONLY on the provided context.

[Rules]
1. Answer ONLY using the context below.
2. If the context does not contain the answer, say "Information not available".
3. NO HALLUCINATIONS. Do not use external knowledge.
4. Output MUST be in JSON format.

[Context]
{context_text}

[Question]
{query} (Ticker: {ticker})

[Required JSON Format]
{{
    "ticker": "{ticker}",
    "summary": "Brief summary of the findings",
    "details": "Precise data points found",
    "sentiment": "positive/neutral/negative",
    "risk_factors": ["list of risks mentioned"],
    "confidence_score": 0.0-1.0
}}
"""
        try:
            response = self.llm.invoke(prompt)
            # JSON 파싱 시도 (LLM이 마크다운 등을 섞을 수 있으므로 정제 필요)
            parsed_json = self._parse_json_from_response(response)
            
            # 소스 추가
            parsed_json["sources"] = list(set([d['metadata'].get('source', 'unknown') for d in context_docs]))
            
            return parsed_json
        except Exception as e:
            logger.error(f"Error during insight generation: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _parse_json_from_response(self, text: str) -> Dict:
        """텍스트에서 JSON 블록 추출 및 파싱"""
        try:
            # ```json ... ``` 형태 제거 시도
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            return json.loads(text)
        except:
            # 최후의 수단: 단순히 문자열 그대로 반환하거나 기본 구조 반환
            return {
                "raw_text": text,
                "error": "Failed to parse JSON structure"
            }

if __name__ == "__main__":
    # 단위 테스트 코드 (예시)
    engine = RAGEngine()
    # print(engine.ingest_pdf("path/to/report.pdf", {"ticker": "AAPL"}))
    # print(engine.generate_fundamental_insight("AAPL", "What are the primary revenue drivers?"))

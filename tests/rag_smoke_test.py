#!/usr/bin/env python3
import sys
import os

# 현재 디렉토리와 core 디렉토리를 경로에 추가
sys.path.append(os.getcwd())

def smoke_test():
    print("Checking dependencies...")
    try:
        import langchain
        import langchain_community
        import chromadb
        import pypdf
        import langchain_ollama
        print("[SUCCESS] All dependencies are importable.")
    except ImportError as e:
        print(f"[FAILURE] Missing dependency: {str(e)}")
        print("Please install required packages using:")
        print("pip install langchain langchain-community langchain-ollama chromadb pypdf")
        return False

    print("\nAttempting to initialize RAGEngine...")
    try:
        from core.rag_engine import RAGEngine
        engine = RAGEngine()
        print("[SUCCESS] RAGEngine initialized successfully.")
        return True
    except Exception as e:
        print(f"[FAILURE] Initialization failed: {str(e)}")
        return False

if __name__ == "__main__":
    smoke_test()

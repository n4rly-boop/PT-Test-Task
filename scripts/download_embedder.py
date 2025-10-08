import os
from sentence_transformers import SentenceTransformer

def download_embedding_model():
    model_name = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
    
    print(f"Downloading embedding model: {model_name}")
    
    try:
        model = SentenceTransformer(model_name)
        print(f"Successfully downloaded and cached model: {model_name}")
        
        test_embedding = model.encode("This is a test sentence.")
        print(f"Model verification successful. Embedding dimension: {len(test_embedding)}")
        
    except Exception as e:
        print(f"Error downloading model {model_name}: {e}")
        raise

if __name__ == "__main__":
    download_embedding_model()

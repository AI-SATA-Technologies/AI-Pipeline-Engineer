import insightface
import faiss
import numpy as np
import os


class FaceRecognizer:
    def __init__(self, index_path='embeddings/face_index.bin', meta_path='embeddings/metadata.npy'):
        """
        Initialize FaceRecognizer with ArcFace R50 and FAISS vector search.
        """
        # Load recognition model (ArcFace R50)
        # Note: 'detection' is required by FaceAnalysis even if we use a separate detector
        self.app = insightface.app.FaceAnalysis(name='buffalo_l', allowed_modules=['detection', 'recognition'])
        self.app.prepare(ctx_id=0)
        
        self.index_path = index_path
        self.meta_path = meta_path
        
        # Load or initialize FAISS index
        if os.path.exists(index_path) and os.path.exists(meta_path):
            self.index = faiss.read_index(index_path)
            self.metadata = np.load(meta_path, allow_pickle=True).item()
        else:
            # IndexFlatIP is for Inner Product (effectively Cosine Similarity for normalized embeddings)
            self.index = faiss.IndexFlatIP(512) 
            self.metadata = {}

    def get_embedding(self, face_crop):
        """Extract 512-d normalized embedding from face crop."""
        faces = self.app.get(face_crop)
        if not faces:
            return None
        # Buffalo_L returns normed_embedding by default
        return faces[0].normed_embedding

    def search(self, embedding, threshold=0.45):
        """
        Search for the closest match in the FAISS index.
        Returns student_id if match found, else None.
        """
        if self.index.ntotal == 0:
            return None
            
        # Reshape embedding for FAISS
        query_vector = np.array([embedding]).astype('float32')
        
        # Search for top-1
        distances, indices = self.index.search(query_vector, 1)
        
        # In IndexFlatIP, higher distance means more similar (inner product)
        if distances[0][0] > threshold:
            idx = indices[0][0]
            return self.metadata.get(idx)
            
        return None

    def add_to_index(self, embedding, student_id):
        """Add a new student embedding to the index and save."""
        # FAISS index adds a copy of the embedding
        self.index.add(np.array([embedding]).astype('float32'))
        
        # Map current index size - 1 to student_id
        idx = self.index.ntotal - 1
        self.metadata[idx] = student_id
        
        # Persistence
        faiss.write_index(self.index, self.index_path)
        np.save(self.meta_path, self.metadata)
        print(f"Added student {student_id} to index. Total: {self.index.ntotal}")

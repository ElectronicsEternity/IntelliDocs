# ============================================
# Test OpenAI Embeddings
# ============================================

from app.rag.embedder import Embedder


def main():

    # Create embedder
    embedder = Embedder()

    # Request embedding directly from OpenAI
    response = embedder.client.embeddings.create(
        model="text-embedding-3-small",
        input="The employee shall be entitled to annual leave."
    )

    print("\n=== Full Response ===")
    print(response)

    print("\n")
    print("\n=== Response Metadata ===")
    print(f"Object: {response.object}")
    print(f"Model : {response.model}")

    print("\n=== Data List ===")
    print(f"Items in data: {len(response.data)}")

    item = response.data[0]

    print("\n=== First Data Item ===")
    print(item)

    print("\n=== Item Metadata ===")
    print(f"Index : {item.index}")
    print(f"Object: {item.object}")

    print("\n=== Embedding Stats ===")
    print(f"Dimensions: {len(item.embedding)}")

    print("\n=== First 10 Values ===")
    print(item.embedding[:10])

    print("\n=== Last 10 Values ===")
    print(item.embedding[-10:])

    print("\n=== Value Type ===")
    print(type(item.embedding))
    print(type(item.embedding[0]))


if __name__ == "__main__":
    main()
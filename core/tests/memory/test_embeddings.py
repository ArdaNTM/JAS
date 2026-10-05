from aura_core.memory.embeddings import OllamaEmbeddingProvider


def test_embedding_provider_defaults():
    provider = OllamaEmbeddingProvider()

    assert provider.model == "bge-m3"
    assert (
        provider.base_url
        == "http://127.0.0.1:11434"
    )

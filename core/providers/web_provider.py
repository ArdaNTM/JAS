from duckduckgo_search import DDGS
import logging

logger = logging.getLogger(__name__)

class DuckDuckGoWebProvider:
    """
    AURA için İnternet Arama Sağlayıcısı (Provider).
    Capability Sistemi üzerinden gelen 'web.search' taleplerini karşılar.
    """
    def __init__(self):
        self.name = "duckduckgo_web_provider"
        self.supported_capabilities = ["web.search", "internet.search"]
        self.ddgs = DDGS()

    def execute(self, capability: str, operation: str, parameters: dict) -> dict:
        if capability != "web.search":
            raise ValueError(f"Bu sağlayıcı {capability} yeteneğini desteklemiyor.")

        query = parameters.get("query")
        max_results = parameters.get("max_results", 3)
        
        logger.info(f"Web'de aranıyor: {query}")
        
        try:
            # İnternette gerçek zamanlı arama yapar
            results = self.ddgs.text(query, max_results=max_results)
            return {
                "status": "success",
                "data": list(results)
            }
        except Exception as e:
            logger.error(f"Web arama hatası: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
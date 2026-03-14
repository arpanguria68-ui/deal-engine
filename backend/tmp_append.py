filepath = r'f:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\app\core\reports\report_generator.py'
with open(filepath, 'a') as f:
    f.write('''\n
class KBReportEnricher:
    """Pull formatting standards and data from Knowledge Base."""
    
    def __init__(self, pageindex_client):
        self.kb = pageindex_client
        self.citations = []  # Accumulated references
    
    async def get_formatting_context(self, deal_name: str) -> dict:
        """Query KB for report format definitions and templates."""
        try:
            chunks = await self.kb.query(
                "investment memo format structure executive summary",
                top_k=3
            )
            for c in chunks:
                self.citations.append({
                    "source": c.metadata.get("filename", "KB Document"),
                    "page": c.page_number,
                    "relevance": c.relevance_score,
                    "excerpt": c.content[:200]
                })
            return {"formatting_guidance": [c.content for c in chunks]}
        except Exception as e:
            logger.warning(f"KB formatting query failed: {e}")
            return {"formatting_guidance": []}
    
    async def get_company_context(self, company: str, industry: str) -> dict:
        """Query KB for company/industry-specific data from uploaded docs."""
        try:
            chunks = await self.kb.query(
                f"{company} {industry} financial analysis market",
                top_k=5
            )
            for c in chunks:
                self.citations.append({
                    "source": c.metadata.get("filename", "KB Document"),
                    "page": c.page_number,
                    "relevance": c.relevance_score,
                    "excerpt": c.content[:200]
                })
            return {
                "kb_insights": [c.content for c in chunks],
                "kb_sources": [c.metadata for c in chunks]
            }
        except Exception as e:
            logger.warning(f"KB company query failed: {e}")
            return {"kb_insights": [], "kb_sources": []}
    
    def get_references(self) -> list:
        """Return deduplicated citation list for the references section."""
        seen = set()
        unique = []
        for c in self.citations:
            key = f"{c['source']}:p{c['page']}"
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return sorted(unique, key=lambda x: x.get('source', 'Unknown'))
''')

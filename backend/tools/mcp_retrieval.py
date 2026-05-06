"""
tools/mcp_retrieval.py

Pulls real prospect signals from Gmail and Google Drive via MCP.
Results are merged into the retrieval agent's output alongside mock data.
Each record carries a data_source field so the UI can badge them.
"""

import logging
import re
from typing import Any, Dict, List

import anthropic

logger = logging.getLogger("gtm.mcp_retrieval")

# MCP server URLs for connected services
GMAIL_MCP_URL  = "https://gmailmcp.googleapis.com/mcp/v1"
GDRIVE_MCP_URL = "https://drivemcp.googleapis.com/mcp/v1"


class MCPRetrievalTool:
    """
    Uses Claude + MCP servers to extract company intelligence
    from the user's Gmail and Google Drive.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    # ── Public entry point ────────────────────────────────────────────

    def fetch(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Given a planner output, search Gmail + Drive for relevant signals.
        Returns a list of enriched company records (may be empty on failure).
        """
        industry = plan.get("filters", {}).get("industry", "AI")
        region   = plan.get("filters", {}).get("region", "US")
        keywords = plan.get("filters", {}).get("keywords", [])

        results = []

        try:
            gmail_records = self._search_gmail(industry, region, keywords)
            results.extend(gmail_records)
            logger.info(f"MCP Gmail: {len(gmail_records)} records")
        except Exception as e:
            logger.warning(f"MCP Gmail failed: {e}")

        try:
            drive_records = self._search_drive(industry, region, keywords)
            results.extend(drive_records)
            logger.info(f"MCP Drive: {len(drive_records)} records")
        except Exception as e:
            logger.warning(f"MCP Drive failed: {e}")

        return results

    # ── Gmail search ──────────────────────────────────────────────────

    def _search_gmail(
        self, industry: str, region: str, keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Searches Gmail for emails mentioning target companies or industry signals.
        Asks Claude to extract structured company records from the email content.
        """
        kw_str = " OR ".join(keywords[:4]) if keywords else industry

        prompt = f"""Search Gmail for emails related to: {industry} companies in {region}.
Search terms to use: {kw_str}

For each relevant email found, extract any company mentioned and return a JSON array of records.
Each record must follow this exact schema:
{{
  "company": "Company Name",
  "industry": "{industry}",
  "region": "{region}",
  "employees": 0,
  "funding": "Unknown",
  "icp_score": 0.5,
  "confidence": 0.6,
  "signals": ["gmail_signal"],
  "insight": "one sentence insight from the email",
  "data_source": "gmail",
  "source_detail": "brief note on what the email contained"
}}

Rules:
- Only include real companies mentioned in actual emails
- If no relevant emails found, return an empty array []
- Return ONLY the JSON array, no other text
- Maximum 5 records
- Set confidence to 0.6 for all Gmail-sourced records
- Add signal "gmail_mention" to all records
- If email shows buying intent, add signal "high_intent"
- If email mentions hiring, add signal "hiring_aggressively"
- If email mentions funding, add signal "growth_funding"
"""

        return self._run_mcp_query(prompt, GMAIL_MCP_URL, "gmail-mcp", "gmail")

    # ── Google Drive search ───────────────────────────────────────────

    def _search_drive(
        self, industry: str, region: str, keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Searches Google Drive for documents containing company or industry intel.
        Asks Claude to extract structured company records from doc content.
        """
        kw_str = " ".join(keywords[:4]) if keywords else industry

        prompt = f"""Search Google Drive for documents related to: {industry} companies, prospects, or leads in {region}.
Search terms: {kw_str}

Look for: CRM exports, prospect lists, research docs, meeting notes, competitor analysis.

For each relevant company found in the documents, return a JSON array of records.
Each record must follow this exact schema:
{{
  "company": "Company Name",
  "industry": "{industry}",
  "region": "{region}",
  "employees": 0,
  "funding": "Unknown",
  "icp_score": 0.55,
  "confidence": 0.65,
  "signals": ["drive_signal"],
  "insight": "one sentence insight from the document",
  "data_source": "gdrive",
  "source_detail": "brief note on which document type contained this"
}}

Rules:
- Only include real companies from actual documents found
- If no relevant documents found, return an empty array []
- Return ONLY the JSON array, no other text
- Maximum 5 records
- Set confidence to 0.65 for all Drive-sourced records
- Add signal "drive_intel" to all records
- If doc is a CRM export or prospect list, add signal "crm_tracked"
- If doc mentions the company as a target or opportunity, add signal "sales_target"
- If doc mentions competitor displacement, add signal "churn_risk"
"""

        return self._run_mcp_query(prompt, GDRIVE_MCP_URL, "gdrive-mcp", "gdrive")

    # ── Shared MCP executor ───────────────────────────────────────────

    def _run_mcp_query(
        self,
        prompt: str,
        mcp_url: str,
        mcp_name: str,
        source_label: str,
    ) -> List[Dict[str, Any]]:
        """
        Calls Claude with an MCP server attached.
        Parses the JSON array response into company records.
        """
        response = self.client.beta.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
            mcp_servers=[
                {
                    "type": "url",
                    "url": mcp_url,
                    "name": mcp_name,
                }
            ],
            betas=["mcp-client-2025-04-04"],
        )

        # Extract text from response
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse JSON array from response
        records = self._parse_records(text, source_label)
        return records

    # ── Response parser ───────────────────────────────────────────────

    def _parse_records(self, text: str, source_label: str) -> List[Dict[str, Any]]:
        """
        Safely parses a JSON array from Claude's response.
        Returns empty list on any parse failure.
        """
        import json

        text = text.strip()

        # Strip markdown fences if present
        text = re.sub(r"```json|```", "", text).strip()

        # Find JSON array in the text
        start = text.find("[")
        end   = text.rfind("]")

        if start == -1 or end == -1:
            logger.warning(f"MCP {source_label}: no JSON array found in response")
            return []

        try:
            records = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning(f"MCP {source_label}: JSON parse error: {e}")
            return []

        # Validate and normalise each record
        clean = []
        for r in records:
            if not isinstance(r, dict):
                continue
            if not r.get("company"):
                continue

            # Ensure required fields exist with safe defaults
            r.setdefault("industry",     "AI")
            r.setdefault("region",       "US")
            r.setdefault("employees",    0)
            r.setdefault("funding",      "Unknown")
            r.setdefault("icp_score",    0.5)
            r.setdefault("confidence",   0.6)
            r.setdefault("signals",      [])
            r.setdefault("insight",      "")
            r.setdefault("data_source",  source_label)
            r.setdefault("source_detail","")

            # Ensure signals is a list
            if not isinstance(r["signals"], list):
                r["signals"] = [str(r["signals"])]

            # Clamp scores to valid range
            r["icp_score"]  = max(0.0, min(1.0, float(r["icp_score"])))
            r["confidence"] = max(0.0, min(1.0, float(r["confidence"])))

            clean.append(r)

        logger.info(f"MCP {source_label}: parsed {len(clean)} valid records")
        return clean
import httpx
import re
import html
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class TwitterAPIError(Exception):
    pass

class TwitterDownloader:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        # Enhanced regex for twitter.com and x.com
        self.url_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[^/]+/status/(\d+)(?:\S*)",
            re.IGNORECASE
        )
        self.tag_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([^/]{1,15})/",
            re.IGNORECASE
        )

    def extract_tweet_ids(self, text: str) -> List[str]:
        ids = self.url_pattern.findall(text)
        return list(dict.fromkeys(ids))  # Deduplicate

    def extract_tweet_tag(self, text: str) -> Optional[str]:
        match = self.tag_pattern.search(text)
        if match:
            return f"#{match.group(1)}"
        return None

    async def get_tweet_media(self, tweet_id: str) -> List[Dict[str, Any]]:
        """
        Fetch tweet media information using vxtwitter API (JSON).
        """
        api_url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
        
        try:
            logger.debug("Fetching tweet media tweet_id=%s", tweet_id)
            response = await self.client.get(api_url)
            response.raise_for_status()
            
            data = response.json()
            if 'media_extended' in data:
                logger.debug("Fetched tweet media tweet_id=%s media_count=%s", tweet_id, len(data["media_extended"]))
                return data['media_extended']
            
            logger.debug("Tweet API response has no media tweet_id=%s", tweet_id)
            return []
            
        except httpx.HTTPStatusError as e:
            # Try to extract error message from og:description if possible
            if e.response.status_code == 404:
                logger.info("Tweet not found or private tweet_id=%s", tweet_id)
                raise TwitterAPIError("Tweet not found or is private.")
            
            content = e.response.text
            match = re.search(r'<meta content="(.*?)" property="og:description" />', content)
            if match:
                raise TwitterAPIError(f"API Error: {html.unescape(match.group(1))}")
            
            raise TwitterAPIError(f"HTTP Error {e.response.status_code}")
        except Exception as e:
            logger.exception("Failed to fetch tweet media tweet_id=%s", tweet_id)
            raise TwitterAPIError(f"Unexpected error: {str(e)}")

    async def close(self):
        await self.client.aclose()

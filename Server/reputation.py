import os
import json
import aiohttp
import logging
import ipaddress

logger = logging.getLogger(__name__)

reputation_cache = {} # remember addresses to avoid repeating

VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
VTOTAL_IP_URL = "https://www.virustotal.com/api/v3/ip_addresses/{ip}"

async def check_ip_rep(ip: str):
    """
    The function checks an ip address using the virus total api.
    checks against a result cache and if its local before querying the API, to avoid hitting the limit.

    ip - the ip address to check.
    returns - (reputation, Reason) tuple, where reputation is a number and Reason is a string.
    """
    if ip in reputation_cache:
        return reputation_cache[ip]
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback:
            return (10, "Local IP")
    except ValueError:
        pass

    if not VIRUSTOTAL_API_KEY:
        logger.warning("Virus Total API key not set")
        return (0, "No API Key")

    headers = {"x-apikey": VIRUSTOTAL_API_KEY}
    url = VTOTAL_IP_URL.format(ip=ip)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                    reputation_result = data.get("data", {}).get("attributes", {}).get("reputation", 0)
                    result = (reputation_result, json.dumps(stats))
                    reputation_cache[ip] = result
                    return result
                elif resp.status == 404:
                    return (0, "Address not found in VirusTotal database")
                else:
                    logger.error(f"VirusTotal error {resp.status}: {await resp.text()}")
                    return (0, f"VT API returned status {resp.status}")
    except Exception as e:
        logger.error(f"Error querying VirusTotal: {e}")
        return (0, f"error {str(e)}")


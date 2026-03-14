from typing import Dict, Any, Optional

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter()


async def get_real_ip() -> Optional[str]:
    """Get real IP address (without proxy) for comparison."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.ipify.org?format=json")
            if response.status_code == 200:
                return response.json().get("ip")
    except Exception:
        pass
    return None


async def check_database(db: AsyncSession) -> Dict[str, Any]:
    """Check PostgreSQL database connectivity."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.close()
        return {"status": "healthy", "message": "Redis connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


async def check_selenium() -> Dict[str, Any]:
    """Check Selenium Grid connectivity."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.SELENIUM_HUB_URL}/status")
            if response.status_code == 200:
                data = response.json()
                ready = data.get("value", {}).get("ready", False)
                if ready:
                    return {"status": "healthy", "message": "Selenium Grid is ready"}
                return {"status": "degraded", "message": "Selenium Grid not ready"}
            return {"status": "unhealthy", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


async def check_tor_proxy() -> Dict[str, Any]:
    """Check Tor proxy connectivity."""
    try:
        proxy_url = f"http://{settings.TOR_PROXY_HOST}:{settings.TOR_HTTP_PORT}"
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=15.0,
        ) as client:
            response = await client.get("https://check.torproject.org/api/ip")
            if response.status_code == 200:
                data = response.json()
                is_tor = data.get("IsTor", False)
                if is_tor:
                    return {
                        "status": "healthy",
                        "message": "Tor proxy working",
                        "tor_ip": data.get("IP"),
                    }
                return {"status": "degraded", "message": "Proxy works but not using Tor"}
            return {"status": "unhealthy", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


async def check_anonymity_status() -> Dict[str, Any]:
    """
    Comprehensive anonymity status check.
    
    Verifies:
    - Tor proxy returns a different IP than real IP
    - Current IP is not in blacklist
    - Traffic is routed through verified Tor exit node
    """
    result = {
        "status": "unknown",
        "real_ip": None,
        "tor_ip": None,
        "is_tor_exit_node": False,
        "ip_hidden": False,
        "blacklist_safe": True,
        "warnings": [],
    }

    try:
        # Get real IP (direct connection)
        real_ip = await get_real_ip()
        result["real_ip"] = real_ip

        # Get Tor IP (through proxy)
        proxy_url = f"http://{settings.TOR_PROXY_HOST}:{settings.TOR_HTTP_PORT}"
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=15.0,
        ) as client:
            response = await client.get("https://check.torproject.org/api/ip")
            if response.status_code == 200:
                data = response.json()
                tor_ip = data.get("IP")
                is_tor = data.get("IsTor", False)

                result["tor_ip"] = tor_ip
                result["is_tor_exit_node"] = is_tor

                # Check if IPs are different (anonymity preserved)
                if real_ip and tor_ip:
                    result["ip_hidden"] = (real_ip != tor_ip)
                    if real_ip == tor_ip:
                        result["warnings"].append(
                            "CRITICAL: Tor IP matches real IP - anonymity compromised!"
                        )

                # Check against blacklist
                if tor_ip and settings.BLACKLISTED_IPS:
                    if tor_ip in settings.BLACKLISTED_IPS:
                        result["blacklist_safe"] = False
                        result["warnings"].append(
                            f"CRITICAL: Tor IP {tor_ip} is in blacklist!"
                        )

                # Determine overall status
                if is_tor and result["ip_hidden"] and result["blacklist_safe"]:
                    result["status"] = "anonymous"
                    result["message"] = "Full anonymity verified - using Tor exit node with hidden IP"
                elif is_tor and result["blacklist_safe"]:
                    result["status"] = "partial"
                    result["message"] = "Using Tor but could not verify IP hiding"
                elif result["ip_hidden"] and result["blacklist_safe"]:
                    result["status"] = "partial"
                    result["message"] = "IP hidden but not verified as Tor exit node"
                else:
                    result["status"] = "compromised"
                    result["message"] = "Anonymity may be compromised - check warnings"

            else:
                result["status"] = "error"
                result["message"] = f"Failed to check Tor: HTTP {response.status_code}"

    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Anonymity check failed: {str(e)}"

    return result


@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint.
    
    Checks connectivity to:
    - PostgreSQL database
    - Redis (Celery broker)
    - Selenium Grid
    - Tor Proxy
    - Anonymity Status
    """
    db_status = await check_database(db)
    redis_status = await check_redis()
    selenium_status = await check_selenium()
    tor_status = await check_tor_proxy()
    anonymity_status = await check_anonymity_status()

    services = {
        "database": db_status,
        "redis": redis_status,
        "selenium_grid": selenium_status,
        "tor_proxy": tor_status,
    }

    all_healthy = all(s["status"] == "healthy" for s in services.values())
    any_unhealthy = any(s["status"] == "unhealthy" for s in services.values())

    if all_healthy:
        overall_status = "healthy"
    elif any_unhealthy:
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "environment": settings.ENVIRONMENT,
        "services": services,
        "anonymity": anonymity_status,
    }


@router.get("/live")
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes liveness probe - checks if the service is running."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness_probe(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Kubernetes readiness probe - checks if the service can handle requests."""
    db_status = await check_database(db)
    redis_status = await check_redis()

    is_ready = (
        db_status["status"] == "healthy" and redis_status["status"] == "healthy"
    )

    return {
        "status": "ready" if is_ready else "not_ready",
        "database": db_status["status"],
        "redis": redis_status["status"],
    }


@router.get("/anonymity")
async def anonymity_check() -> Dict[str, Any]:
    """
    Dedicated anonymity status endpoint.
    
    Returns detailed information about:
    - Real IP vs Tor IP comparison
    - Tor exit node verification
    - Blacklist check status
    - Overall anonymity assessment
    
    Use this before scraping to ensure anonymity is preserved.
    """
    return await check_anonymity_status()

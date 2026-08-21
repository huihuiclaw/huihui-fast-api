"""AdMob earnings endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.services.admob import AdMobAPIError, AdMobClient, AdMobConfigError

router = APIRouter(prefix="/admob", tags=["admob"])


def _format_date(raw: str) -> str:
    """AdMob returns dates as `YYYYMMDD`; format as `MM/DD`."""
    return f"{raw[4:6]}/{raw[6:8]}" if len(raw) >= 8 else raw


def _parse_report(report: list[dict]) -> dict:
    """AdMob responses are `[header, *rows, footer]`. Aggregate and reshape."""
    rows: list[dict] = []
    totals_micros = 0
    total_impressions = 0
    total_clicks = 0

    for item in report[1:-1]:
        row = item.get("row", {})
        dv = row.get("dimensionValues", {}).get("DATE", {}).get("value", "")
        mv = row.get("metricValues", {})
        earnings_micros = int(mv.get("ESTIMATED_EARNINGS", {}).get("microsValue", 0))
        impressions = int(mv.get("IMPRESSIONS", {}).get("integerValue", 0))
        clicks = int(mv.get("CLICKS", {}).get("integerValue", 0))

        totals_micros += earnings_micros
        total_impressions += impressions
        total_clicks += clicks

        rows.append({
            "date": _format_date(dv),
            "earnings_usd": round(earnings_micros / 1_000_000, 2),
            "impressions": impressions,
            "clicks": clicks,
        })

    return {
        "rows": rows,
        "totals": {
            "earnings_usd": round(totals_micros / 1_000_000, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
        },
    }


@router.get("/earnings")
async def get_earnings(
    days: int = Query(default=7, ge=1, le=90, description="Number of trailing days"),
) -> dict:
    """Return AdMob earnings for the last `days` days, plus per-day rows and totals."""
    try:
        async with AdMobClient() as client:
            report = await client.generate_report(days=days)
    except AdMobConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AdMobAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    parsed = _parse_report(report)
    parsed["days"] = days
    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return parsed
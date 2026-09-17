"""Evidence scorecard for Beacon's owner-gated marketing department."""

from concurrent.futures import ThreadPoolExecutor

from modules.beacon.media_library import list_beacon_media_assets
from modules.sales.beacon_campaign import (
    facebook_posting_policy,
    list_beacon_campaign_performance_events,
    list_beacon_facebook_post_execution_events,
    list_beacon_manual_post_evidence,
)


def beacon_workforce_scorecard(limit=500):
    with ThreadPoolExecutor(max_workers=4) as pool:
        media_future = pool.submit(list_beacon_media_assets, limit=limit)
        manual_future = pool.submit(list_beacon_manual_post_evidence, limit=limit)
        performance_future = pool.submit(list_beacon_campaign_performance_events, limit=limit)
        execution_future = pool.submit(list_beacon_facebook_post_execution_events, limit=limit)
        media_result, media_status = media_future.result()
        manual_result, manual_status = manual_future.result()
        performance_result, performance_status = performance_future.result()
        execution_result, execution_status = execution_future.result()

    assets = media_result.get("assets", []) if media_status < 400 else []
    manual_posts = manual_result.get("manual_post_events", []) if manual_status < 400 else []
    performance = performance_result.get("performance_events", []) if performance_status < 400 else []
    executions = execution_result.get("execution_events", []) if execution_status < 400 else []
    production_manual = [row for row in manual_posts if not _test_record(row)]
    production_performance = [row for row in performance if not _test_record(row)]
    production_executions = [row for row in executions if not _test_record(row)]
    published = [row for row in production_executions if row.get("execution_status") == "facebook_page_post_sent"]
    approved_assets = [row for row in assets if row.get("effective_public_use_approved") and not _test_record(row)]
    qualified_leads = sum(int(row.get("qualified_buyer_leads") or 0) for row in production_performance)
    spend = sum(float(row.get("spend_amount") or 0) for row in production_performance)
    policy = facebook_posting_policy()
    configured = bool(policy.get("enabled") and policy.get("page_id_configured") and policy.get("page_access_token_configured"))
    progress = round(
        (30 if configured else 0)
        + min(len(approved_assets) / 10, 1) * 10
        + min(len(published) / 10, 1) * 20
        + min(len(production_performance) / 10, 1) * 25
        + min(qualified_leads / 20, 1) * 15
    )
    return {
        "success": all(code < 400 for code in (media_status, manual_status, performance_status, execution_status)),
        "status": "beacon_workforce_scorecard_ready",
        "scorecard": {
            "stage": "performance_learning" if production_performance else "owner_approved_posting",
            "progress_percent": progress,
            "facebook_configured": configured,
            "assets_total": len(assets),
            "approved_assets": len(approved_assets),
            "media_review_backlog": int((media_result.get("counts") or {}).get("needs_review") or 0),
            "production_manual_posts": len(production_manual),
            "production_posts_sent": len(published),
            "production_performance_events": len(production_performance),
            "qualified_buyer_leads": qualified_leads,
            "tracked_spend_zar": round(spend, 2),
            "test_execution_events": len(executions) - len(production_executions),
            "failed_production_posts": len([
                row for row in production_executions
                if row.get("execution_status") == "facebook_page_post_failed"
            ]),
            "scheduling_enabled": False,
            "paid_spend_enabled": False,
            "creative_provider_status": "planned_owner_gated_evaluation",
        },
        "source_statuses": {
            "media": media_status,
            "manual_posts": manual_status,
            "performance": performance_status,
            "facebook_executions": execution_status,
        },
    }


def _test_record(row):
    text = " ".join(str(value or "") for value in (row or {}).values()).lower()
    return any(marker in text for marker in ("test flow", "smoke", "delete after", "config-smoke", "-test-"))

from modules.pig_weights.pig_weights_service import get_active_pigs


def get_status():
    return {
        "module": "pig_weights",
        "status": "running"
    }


def list_active_pigs():
    pigs = get_active_pigs()
    return {
        "count": len(pigs),
        "pigs": pigs
    }
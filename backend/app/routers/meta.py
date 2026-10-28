from fastapi import APIRouter, Depends, HTTPException

from app.security import current_user

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])
DATA = {
    "institutions": ["SIAC", "ICC", "LCIA", "DIAC", "SIIA", "Ad hoc"],
    "case-statuses": ["active", "pending", "closed", "archived"],
    "dispute-categories": ["Construction", "Commercial", "Energy", "Investment", "Infrastructure", "Other"],
    "document-types": [
        "Arbitration Agreement",
        "Statement of Claim",
        "Statement of Defence",
        "Award",
        "Order",
        "Correspondence",
        "Evidence",
        "Template",
        "Other",
    ],
    "jurisdictions": ["India", "Singapore", "England and Wales", "International"],
}


@router.get("/{name}")
def meta(name: str, user=Depends(current_user)):
    if name not in DATA:
        raise HTTPException(404, "Metadata not found")
    return {"items": DATA[name]}

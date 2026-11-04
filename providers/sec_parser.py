"""Minimal Form 3/4/5 ownership XML parser; never fabricates transactions."""

import xml.etree.ElementTree as ET
from typing import Dict, List


def _text(node, path: str):
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def parse_ownership_xml(xml_text: str, security_id: str, cik: str, source_url: str,
                        accession_number: str = None) -> List[Dict]:
    """Extract non-derivative transactions from a genuine ownership document."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return []
    form = _text(root, "documentType")
    if form not in {"3", "4", "5"}:
        return []
    owner = root.find("reportingOwner")
    owner_id = _text(owner, "reportingOwnerId/rptOwnerCik") if owner is not None else None
    owner_name = _text(owner, "reportingOwnerId/rptOwnerName") if owner is not None else None
    title = _text(owner, "reportingOwnerRelationship/officerTitle") if owner is not None else None
    filed_at = _text(root, "periodOfReport")
    transactions = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        shares = _text(tx, "transactionAmounts/transactionShares/value")
        price = _text(tx, "transactionAmounts/transactionPricePerShare/value")
        code = _text(tx, "transactionCoding/transactionCode")
        disposition = _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        try:
            shares_num = float(shares) if shares else None
            price_num = float(price) if price else None
        except ValueError:
            continue
        transactions.append({
            "security_id": security_id, "cik": cik, "accession_number": accession_number, "filing_type": form,
            "filed_at": filed_at, "transaction_date": _text(tx, "transactionDate/value"),
            "insider_name": owner_name, "insider_cik": owner_id, "relationship_title": title,
            "transaction_code": code, "acquisition_disposition": disposition, "shares": shares_num,
            "price": price_num, "transaction_value": shares_num * price_num if shares_num is not None and price_num is not None else None,
            "shares_owned_after": _text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
            "source_url": source_url,
        })
    return transactions

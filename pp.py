# pp.py
# Process extracted OCR document data and save to database

from database import (
    init_database,
    insert_po,
    insert_grni,
    insert_invoice,
    insert_pard,
    insert_match_result,
    check_duplicate_invoice,
    get_dashboard_stats
)

# Initialize database when this module is loaded
init_database()


def process_document(doc_data, doc_type):
    """
    Process extracted data and save it to the database.

    Supported doc_type values:
        - PO
        - GRNI
        - INVOICE
        - PARD

    For invoices, duplicate checking is performed before insert.
    """

    if doc_data is None:
        print("No document data received.")
        return False

    if not doc_type:
        print("No document type received.")
        return False

    doc_type = doc_type.upper()

    try:
        if doc_type == "PO":
            success = insert_po(doc_data)

        elif doc_type == "GRNI":
            success = insert_grni(doc_data)

        elif doc_type == "INVOICE":
            # Required fields for duplicate checking
            inv_id = doc_data.get("inv_id")
            vendor = doc_data.get("vendor")

            if not inv_id:
                print("Invoice ID is missing from document data.")
                return False

            if not vendor:
                print("Vendor is missing from document data.")
                return False

            # IMPORTANT:
            # database.check_duplicate_invoice() accepts only 2 arguments:
            # check_duplicate_invoice(inv_id, vendor)
            if check_duplicate_invoice(inv_id, vendor):
                print(f"⚠️ DUPLICATE INVOICE DETECTED: {inv_id}")
                doc_data["is_duplicate"] = True
            else:
                doc_data["is_duplicate"] = False

            success = insert_invoice(doc_data)

        elif doc_type == "PARD":
            success = insert_pard(doc_data)

        else:
            print(f"Unsupported document type: {doc_type}")
            success = False

        return success

    except Exception as e:
        print(f"Error processing document type {doc_type}: {e}")
        raise


def save_match_result(inv_id, po_id, grni_id, pard_id, status, score, remark):
    """
    Save matching result to database.

    This function is used after 3-way matching:
        Invoice vs PO vs GRNI vs PARD
    """

    match_data = {
        "inv_id": inv_id,
        "po_id": po_id,
        "grni_id": grni_id,
        "pard_id": pard_id,
        "status": status,
        "score": score,
        "remark": remark
    }

    match_id = insert_match_result(match_data)

    # Queue routing is optional.
    # If route_to_queue exists in your project, you can enable this section.
    # For now, it is disabled to avoid NameError if route_to_queue is not defined.

    # if status == "MATCH":
    #     route_to_queue(match_data, "erp_queue")
    # elif status == "DISCREPANCY":
    #     route_to_queue(match_data, "review_queue")
    # else:
    #     route_to_queue(match_data, "pending_queue")

    return match_id


def get_stats():
    """
    Return dashboard statistics.
    """

    return get_dashboard_stats()
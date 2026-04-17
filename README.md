
1.models/invoice.py
Data model representing an invoice throughout the pipeline.
Contains all fields returned by Azure Document Intelligence prebuilt-invoice :
vendor, customer, references, dates, amounts, addresses, payment details, line items.
The to_dict() method converts the invoice into a dictionary for Excel export.
2.models/validation_result.py
Data model representing the result of a validation.
Contains is_valid (bool) and errors (list).
The add_error() method adds an error and automatically sets is_valid = False.
3.tools/ocr_extraction_tool.py
Sends the invoice PDF to Azure Document Intelligence (prebuilt-invoice model)
and fills the Invoice object with extracted data.
Fields are grouped by type : string, address, date, amount.
Checks the confidence score on required fields (VendorName, InvoiceDate, InvoiceTotal).
4.tools/validation_tool.py
Applies 4 business rules on every invoice :

Required fields present (vendor_name, invoice_date, total_amount)
Date format valid (YYYY-MM-DD, not in future, not older than 5 years)
All amounts positive
Mathematical consistency : Subtotal - Discount + Tax ≈ Total (tolerance 0.02)

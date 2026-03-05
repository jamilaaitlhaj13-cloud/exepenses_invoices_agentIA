This version of the project includes improvements compared to the previous implementation.

- Removed `print()` statements and replaced them with a centralized logging system that records execution traces into log files.

- Separated agent components to improve modularity and maintainability of the codebase.

- Discontinued manual prompt-based extraction since Azure Document Intelligence uses the **prebuilt-invoice** model for automatic invoice data extraction.

- Up to now, the development has focused on implementing the OCR agent responsible for automated invoice data extraction.

- The next planned step for the following week is to develop a mail agent to automate invoice retrieval.
